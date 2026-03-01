"""MCP report tool handlers — generate_report and generate_dashboard."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from mcp.types import TextContent

from investment_mcp.cache.store import DataCache
from investment_mcp.config import get_config
from investment_mcp.providers.base import Instrument, ProviderRegistry
from investment_mcp.reports.generator import ChartBuilder, ReportGenerator

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "reports" / "templates"

# FRED series ID → yield-curve maturity label (sorted by tenor)
_YIELD_CURVE_MAP: dict[str, str] = {
    "fred:DGS2": "2Y",
    "fred:DGS10": "10Y",
    "fred:DGS30": "30Y",
}
_MATURITY_ORDER = ["2Y", "5Y", "10Y", "20Y", "30Y"]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

async def _fetch_or_cached(
    registry: ProviderRegistry,
    cache: DataCache,
    instrument_id: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Return cached data if fresh, otherwise fetch from provider and cache."""
    if cache.is_fresh(instrument_id):
        df = cache.get_series(instrument_id, start_date, end_date)
        if not df.empty:
            return df

    instrument = registry.get_instrument(instrument_id)
    provider = registry.get_provider(instrument.provider)
    df = await provider.fetch(instrument, start_date, end_date)

    if not df.empty:
        cache.store_series(instrument_id, df, instrument.provider)

    return df


def _build_summary_card(instrument: Instrument, latest_data: dict | None) -> dict:
    """Format a summary card dict for the dashboard template.

    Returns a dict with ``label``, ``value``, and optional ``change`` keys
    matching what ``dashboard.html`` expects.
    """
    if latest_data is None:
        return {"label": instrument.name, "value": "N/A", "change": None}

    raw = latest_data.get("value") or latest_data.get("close")
    if raw is not None:
        formatted = f"{float(raw):,.2f}"
        if instrument.unit == "percent":
            formatted += "%"
    else:
        formatted = "N/A"

    return {
        "label": instrument.name,
        "value": formatted,
        "change": latest_data.get("change"),
    }


def _pick_value_column(df: pd.DataFrame) -> str:
    """Choose the best single-value column from a DataFrame."""
    for candidate in ("value", "close", "Close"):
        if candidate in df.columns:
            return candidate
    return df.columns[0]


def _has_ohlc(df: pd.DataFrame) -> bool:
    """Return True if the DataFrame contains open/high/low/close columns."""
    lower_cols = {c.lower() for c in df.columns}
    return {"open", "high", "low", "close"}.issubset(lower_cols)


def _compute_stats(df: pd.DataFrame) -> dict:
    """Compute summary statistics expected by ``detail.html``."""
    empty = {"current": None, "min": None, "max": None, "mean": None, "pct_change": None}
    if df.empty:
        return empty

    col = df.columns[0]
    values = df[col].dropna()
    if values.empty:
        return empty

    current = float(values.iloc[-1])
    first = float(values.iloc[0])
    pct_change = ((current - first) / first * 100.0) if first != 0 else None

    return {
        "current": current,
        "min": float(values.min()),
        "max": float(values.max()),
        "mean": float(values.mean()),
        "pct_change": pct_change,
    }


def _recent_data_rows(df: pd.DataFrame, n: int = 20) -> list[dict]:
    """Extract the last *n* rows as dicts for the recent-data table."""
    if df.empty:
        return []

    col = df.columns[0]
    tail = df.tail(n).copy()
    tail["_change"] = tail[col].diff()

    rows: list[dict] = []
    for dt, row in tail.iterrows():
        rows.append({
            "date": str(dt.date()) if hasattr(dt, "date") else str(dt),
            "value": float(row[col]) if pd.notna(row[col]) else 0.0,
            "change": float(row["_change"]) if pd.notna(row["_change"]) else None,
        })
    return rows


def _safe_div_id(instrument_id: str) -> str:
    """Turn an instrument ID into a valid HTML element id."""
    return "chart-" + instrument_id.replace(":", "-").replace(".", "-")


# ------------------------------------------------------------------
# Public handlers
# ------------------------------------------------------------------

async def handle_generate_report(
    registry: ProviderRegistry,
    cache: DataCache,
    arguments: dict,
) -> list[TextContent]:
    """Generate an interactive HTML report for selected instruments.

    Arguments
    ---------
    instrument_ids : list[str], optional
        Instruments to include.  Defaults to *all* registered instruments.
    report_type : str, optional
        ``"dashboard"`` (overview page) or ``"detail"`` (per-instrument pages).
        Defaults to ``"dashboard"``.
    """
    config = get_config()
    docs_dir = config.docs_dir
    report_type = arguments.get("report_type", "dashboard")
    instrument_ids: list[str] = arguments.get("instrument_ids") or [
        inst.id for inst in registry.list_all_instruments()
    ]

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (
        datetime.now() - timedelta(days=config.default_lookback_years * 365)
    ).strftime("%Y-%m-%d")

    generator = ReportGenerator(_TEMPLATE_DIR)
    generated_paths: list[str] = []
    errors: list[str] = []

    # ── Dashboard report ──────────────────────────────────────────
    if report_type == "dashboard":
        charts: list[dict] = []
        summary_cards: list[dict] = []

        for inst_id in instrument_ids:
            try:
                instrument = registry.get_instrument(inst_id)
                df = await _fetch_or_cached(registry, cache, inst_id, start_date, end_date)

                if df.empty:
                    errors.append(f"{inst_id}: no data")
                    continue

                latest = cache.get_latest(inst_id)
                summary_cards.append(_build_summary_card(instrument, latest))

                value_col = _pick_value_column(df)
                chart_df = df[[value_col]].dropna()
                chart_json = ChartBuilder.build_line_chart(
                    chart_df, instrument.name, instrument.unit or "Value",
                )

                charts.append({
                    "div_id": _safe_div_id(inst_id),
                    "title": instrument.name,
                    "section": instrument.category,
                    "plotly_json": chart_json,
                })
            except Exception as exc:
                logger.warning("Skipping %s: %s", inst_id, exc)
                errors.append(f"{inst_id}: {exc}")

        output_path = docs_dir / "report.html"
        generator.generate_dashboard(charts, summary_cards, output_path)
        generated_paths.append(str(output_path))

    # ── Detail reports ────────────────────────────────────────────
    elif report_type == "detail":
        for inst_id in instrument_ids:
            try:
                instrument = registry.get_instrument(inst_id)
                df = await _fetch_or_cached(registry, cache, inst_id, start_date, end_date)

                if df.empty:
                    errors.append(f"{inst_id}: no data")
                    continue

                value_col = _pick_value_column(df)
                chart_df = df[[value_col]].dropna()

                if _has_ohlc(df):
                    chart_json = ChartBuilder.build_candlestick_chart(df, instrument.name)
                else:
                    chart_json = ChartBuilder.build_line_chart(
                        chart_df, instrument.name, instrument.unit or "Value",
                    )

                stats = _compute_stats(chart_df)
                recent = _recent_data_rows(chart_df)

                safe_name = inst_id.replace(":", "-").replace(".", "-")
                output_path = docs_dir / f"{safe_name}.html"
                generator.generate_detail(
                    instrument={
                        "name": instrument.name,
                        "symbol": instrument.ticker,
                        "description": instrument.description,
                    },
                    chart_json=chart_json,
                    stats=stats,
                    recent_data=recent,
                    output_path=output_path,
                )
                generated_paths.append(str(output_path))
            except Exception as exc:
                logger.warning("Skipping %s: %s", inst_id, exc)
                errors.append(f"{inst_id}: {exc}")

    # ── Summary ───────────────────────────────────────────────────
    parts = [f"Generated {len(generated_paths)} report(s)."]
    if generated_paths:
        parts.append("Files: " + ", ".join(generated_paths))
    if errors:
        parts.append(f"Errors ({len(errors)}): " + "; ".join(errors))

    return [TextContent(type="text", text="\n".join(parts))]


async def handle_generate_dashboard(
    registry: ProviderRegistry,
    cache: DataCache,
    arguments: dict,
) -> list[TextContent]:
    """Generate the main overview dashboard with ALL tracked instruments.

    Creates ``docs/index.html`` containing summary cards, per-section charts,
    and a yield-curve snapshot (if Treasury data is available).
    """
    config = get_config()
    docs_dir = config.docs_dir

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (
        datetime.now() - timedelta(days=config.default_lookback_years * 365)
    ).strftime("%Y-%m-%d")

    generator = ReportGenerator(_TEMPLATE_DIR)
    all_instruments = registry.list_all_instruments()

    charts: list[dict] = []
    summary_cards: list[dict] = []
    yield_data: dict[str, float] = {}
    errors: list[str] = []
    included: list[str] = []

    for instrument in all_instruments:
        try:
            df = await _fetch_or_cached(
                registry, cache, instrument.id, start_date, end_date,
            )

            if df.empty:
                errors.append(f"{instrument.id}: no data")
                continue

            included.append(instrument.name)

            # Summary card
            latest = cache.get_latest(instrument.id)
            summary_cards.append(_build_summary_card(instrument, latest))

            # Collect yield-curve data points
            if instrument.id in _YIELD_CURVE_MAP and latest:
                yval = latest.get("value") or latest.get("close")
                if yval is not None:
                    yield_data[_YIELD_CURVE_MAP[instrument.id]] = float(yval)

            # Build per-instrument chart
            value_col = _pick_value_column(df)
            chart_df = df[[value_col]].dropna()

            if _has_ohlc(df) and instrument.category in ("tanker", "stock", "shipping"):
                chart_json = ChartBuilder.build_candlestick_chart(df, instrument.name)
            else:
                chart_json = ChartBuilder.build_line_chart(
                    chart_df, instrument.name, instrument.unit or "Value",
                )

            charts.append({
                "div_id": _safe_div_id(instrument.id),
                "title": instrument.name,
                "section": instrument.category,
                "plotly_json": chart_json,
            })
        except Exception as exc:
            logger.warning("Skipping %s: %s", instrument.id, exc)
            errors.append(f"{instrument.id}: {exc}")

    # Yield-curve snapshot (macro section)
    if yield_data:
        sorted_yields = {k: yield_data[k] for k in _MATURITY_ORDER if k in yield_data}
        if sorted_yields:
            yc_json = ChartBuilder.build_yield_curve_snapshot(sorted_yields, end_date)
            charts.append({
                "div_id": "chart-yield-curve",
                "title": "Yield Curve",
                "section": "macro",
                "plotly_json": yc_json,
            })

    output_path = docs_dir / "index.html"
    generator.generate_dashboard(charts, summary_cards, output_path)

    parts = [
        f"Dashboard generated: {output_path}",
        f"Instruments included ({len(included)}): {', '.join(included)}",
        f"Charts: {len(charts)}, Summary cards: {len(summary_cards)}",
    ]
    if errors:
        parts.append(f"Errors ({len(errors)}): " + "; ".join(errors))

    return [TextContent(type="text", text="\n".join(parts))]
