"""MCP tool handlers for financial data retrieval and comparison."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd
from mcp.types import TextContent

from investment_mcp.providers.base import Instrument, ProviderRegistry
from investment_mcp.cache.store import DataCache

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_date_range() -> tuple[str, str]:
    """Return (start_date, end_date) defaulting to 10 years ago → today."""
    end = datetime.now()
    start = end - timedelta(days=365 * 10)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _text(content: str) -> list[TextContent]:
    return [TextContent(type="text", text=content)]


def _primary_value_column(df: pd.DataFrame) -> str:
    """Pick the best single-value column from a DataFrame."""
    for col in ("value", "close", "Close"):
        if col in df.columns:
            return col
    # Fall back to first numeric column
    numerics = df.select_dtypes(include="number").columns
    if len(numerics):
        return str(numerics[0])
    raise ValueError("No numeric column found in data")


async def _fetch_with_cache(
    registry: ProviderRegistry,
    cache: DataCache,
    instrument_id: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Return data for *instrument_id*, using cache when fresh."""
    instrument = registry.get_instrument(instrument_id)
    provider = registry.get_provider(instrument.provider)

    if cache.is_fresh(instrument_id):
        cached = cache.get_series(instrument_id, start_date, end_date)
        if not cached.empty:
            logger.info("Cache hit for %s", instrument_id)
            return cached

    logger.info("Fetching %s from provider %s", instrument_id, provider.name)
    df = await provider.fetch(instrument, start_date, end_date)

    if not df.empty:
        cache.store_series(instrument_id, df, source=provider.name)

    return df


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

async def handle_list_instruments(
    registry: ProviderRegistry,
    arguments: dict,
) -> list[TextContent]:
    """List available instruments, optionally filtered by category."""
    category = arguments.get("category")

    if category:
        instruments = registry.list_by_category(category)
    else:
        instruments = registry.list_all_instruments()

    if not instruments:
        return _text("No instruments found.")

    # Group by category
    groups: dict[str, list[Instrument]] = defaultdict(list)
    for inst in instruments:
        groups[inst.category].append(inst)

    lines: list[str] = ["# Available Instruments", ""]
    for cat in sorted(groups):
        lines.append(f"## {cat.upper()}")
        lines.append("")
        lines.append(f"{'ID':<25} {'Name':<30} {'Description'}")
        lines.append(f"{'─' * 25} {'─' * 30} {'─' * 40}")
        for inst in sorted(groups[cat], key=lambda i: i.id):
            lines.append(f"{inst.id:<25} {inst.name:<30} {inst.description}")
        lines.append("")

    lines.append(f"Total: {len(instruments)} instruments")
    return _text("\n".join(lines))


async def handle_get_historical_data(
    registry: ProviderRegistry,
    cache: DataCache,
    arguments: dict,
) -> list[TextContent]:
    """Fetch historical time series for a single instrument."""
    instrument_id = arguments.get("instrument_id")
    if not instrument_id:
        return _text("Error: instrument_id is required.")

    default_start, default_end = _default_date_range()
    start_date = arguments.get("start_date", default_start)
    end_date = arguments.get("end_date", default_end)

    try:
        instrument = registry.get_instrument(instrument_id)
    except KeyError:
        return _text(f"Error: Instrument '{instrument_id}' not found.")

    try:
        df = await _fetch_with_cache(registry, cache, instrument_id, start_date, end_date)
    except Exception as exc:
        logger.exception("Failed to fetch %s", instrument_id)
        return _text(f"Error fetching data for {instrument_id}: {exc}")

    if df.empty:
        return _text(f"No data available for {instrument.name} ({instrument_id}) in the requested range.")

    # Determine the value column
    try:
        val_col = _primary_value_column(df)
    except ValueError:
        return _text(f"Data retrieved for {instrument_id} but no numeric column found.")

    values = df[val_col].dropna()

    # Build output
    lines: list[str] = [
        f"# {instrument.name}",
        f"ID: {instrument.id}  |  Category: {instrument.category}  |  Provider: {instrument.provider}",
        f"Unit: {instrument.unit or 'N/A'}",
        "",
        f"**Date range:** {df.index.min().strftime('%Y-%m-%d')} → {df.index.max().strftime('%Y-%m-%d')}",
        f"**Data points:** {len(df)}",
        "",
    ]

    # Last 10 data points table
    tail = df.tail(10)
    lines.append("## Latest Data Points")
    lines.append("")
    lines.append(f"{'Date':<12} {val_col.title():>14}")
    lines.append(f"{'─' * 12} {'─' * 14}")
    for dt, row in tail.iterrows():
        date_str = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)
        val = row[val_col]
        val_str = f"{val:>14.4f}" if pd.notna(val) else f"{'N/A':>14}"
        lines.append(f"{date_str:<12} {val_str}")
    lines.append("")

    # Basic statistics
    if not values.empty:
        lines.append("## Statistics")
        lines.append("")
        lines.append(f"  Min:     {values.min():.4f}")
        lines.append(f"  Max:     {values.max():.4f}")
        lines.append(f"  Mean:    {values.mean():.4f}")
        lines.append(f"  Current: {values.iloc[-1]:.4f}")

    return _text("\n".join(lines))


async def handle_get_latest(
    registry: ProviderRegistry,
    cache: DataCache,
    arguments: dict,
) -> list[TextContent]:
    """Return the most recent data point for an instrument."""
    instrument_id = arguments.get("instrument_id")
    if not instrument_id:
        return _text("Error: instrument_id is required.")

    try:
        instrument = registry.get_instrument(instrument_id)
    except KeyError:
        return _text(f"Error: Instrument '{instrument_id}' not found.")

    provider = registry.get_provider(instrument.provider)

    # Try provider's get_latest first (fetches last 5 days)
    try:
        latest = await provider.get_latest(instrument)
    except Exception as exc:
        logger.exception("Provider get_latest failed for %s", instrument_id)
        latest = None

    # Fall back to cache
    if latest is None:
        latest = cache.get_latest(instrument_id)

    if latest is None:
        return _text(f"No recent data available for {instrument.name} ({instrument_id}).")

    lines: list[str] = [
        f"# Latest: {instrument.name}",
        f"ID: {instrument.id}  |  Category: {instrument.category}",
        "",
    ]

    date_val = latest.get("date", "N/A")
    lines.append(f"**Date:** {date_val}")
    lines.append("")

    # Show all available fields
    skip_keys = {"date", "instrument_id"}
    for key, val in sorted(latest.items()):
        if key in skip_keys:
            continue
        if val is None:
            continue
        if isinstance(val, float):
            lines.append(f"  {key:<12} {val:.4f}")
        else:
            lines.append(f"  {key:<12} {val}")

    return _text("\n".join(lines))


async def handle_compare_instruments(
    registry: ProviderRegistry,
    cache: DataCache,
    arguments: dict,
) -> list[TextContent]:
    """Compare multiple instruments with normalized returns and correlations."""
    instrument_ids = arguments.get("instrument_ids")
    if not instrument_ids or not isinstance(instrument_ids, list) or len(instrument_ids) < 2:
        return _text("Error: instrument_ids must be a list of at least 2 instrument IDs.")

    default_start, default_end = _default_date_range()
    start_date = arguments.get("start_date", default_start)
    end_date = arguments.get("end_date", default_end)

    # Fetch data for each instrument
    series: dict[str, pd.Series] = {}
    instruments: dict[str, Instrument] = {}
    errors: list[str] = []

    for iid in instrument_ids:
        try:
            instrument = registry.get_instrument(iid)
            instruments[iid] = instrument
            df = await _fetch_with_cache(registry, cache, iid, start_date, end_date)
            if df.empty:
                errors.append(f"{iid}: no data")
                continue
            val_col = _primary_value_column(df)
            series[iid] = df[val_col].dropna()
        except KeyError:
            errors.append(f"{iid}: instrument not found")
        except Exception as exc:
            errors.append(f"{iid}: {exc}")

    if len(series) < 2:
        msg = "Not enough data to compare. " + "; ".join(errors) if errors else "Not enough data to compare."
        return _text(msg)

    lines: list[str] = [
        "# Instrument Comparison",
        f"Period: {start_date} → {end_date}",
        "",
    ]

    if errors:
        lines.append("**Warnings:** " + "; ".join(errors))
        lines.append("")

    # Summary table: latest value & period return
    lines.append("## Summary")
    lines.append("")
    lines.append(f"{'Instrument':<25} {'Name':<25} {'Latest':>12} {'Period Return':>14}")
    lines.append(f"{'─' * 25} {'─' * 25} {'─' * 12} {'─' * 14}")

    for iid, s in series.items():
        name = instruments[iid].name if iid in instruments else iid
        latest_val = s.iloc[-1]
        first_val = s.iloc[0]
        pct_return = ((latest_val - first_val) / first_val) * 100 if first_val != 0 else float("nan")
        lines.append(
            f"{iid:<25} {name:<25} {latest_val:>12.4f} {pct_return:>13.2f}%"
        )
    lines.append("")

    # Normalized percentage change from start
    combined = pd.DataFrame(series)
    normalized = combined.apply(
        lambda col: ((col / col.dropna().iloc[0]) - 1) * 100 if not col.dropna().empty else col
    )

    # Show last 10 rows of normalized data
    tail = normalized.tail(10)
    lines.append("## Normalized Returns (% change from start)")
    lines.append("")

    header = f"{'Date':<12}"
    for iid in tail.columns:
        label = iid if len(iid) <= 14 else iid[:12] + ".."
        header += f" {label:>14}"
    lines.append(header)
    lines.append(f"{'─' * 12}" + "".join(f" {'─' * 14}" for _ in tail.columns))

    for dt, row in tail.iterrows():
        date_str = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)
        row_str = f"{date_str:<12}"
        for iid in tail.columns:
            val = row[iid]
            row_str += f" {val:>14.2f}" if pd.notna(val) else f" {'N/A':>14}"
        lines.append(row_str)
    lines.append("")

    # Correlation matrix
    if len(series) >= 2:
        corr = combined.corr()
        lines.append("## Correlation Matrix")
        lines.append("")
        header = f"{'':>25}"
        for iid in corr.columns:
            label = iid if len(iid) <= 12 else iid[:10] + ".."
            header += f" {label:>12}"
        lines.append(header)
        lines.append(f"{'─' * 25}" + "".join(f" {'─' * 12}" for _ in corr.columns))

        for row_id in corr.index:
            label = row_id if len(row_id) <= 25 else row_id[:23] + ".."
            row_str = f"{label:>25}"
            for col_id in corr.columns:
                val = corr.loc[row_id, col_id]
                row_str += f" {val:>12.4f}" if pd.notna(val) else f" {'N/A':>12}"
            lines.append(row_str)

    return _text("\n".join(lines))
