#!/usr/bin/env python3
"""Fetch financial data for all instruments and regenerate HTML reports.

Intended to run as a standalone script (CI or local):
    python scripts/fetch_data.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Ensure the project root is on sys.path when running outside an installed env
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT / ".env")

from investment_mcp.cache.store import DataCache
from investment_mcp.config import get_config
from investment_mcp.providers.base import ProviderRegistry
from investment_mcp.providers.fred import FredProvider
from investment_mcp.providers.shipping import ShippingProvider
from investment_mcp.providers.yahoo import YahooProvider
from investment_mcp.reports.generator import ChartBuilder, ReportGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _build_registry() -> ProviderRegistry:
    """Create and populate the provider registry."""
    cfg = get_config()
    registry = ProviderRegistry()

    # FRED (requires API key)
    fred_key = cfg.fred_api_key or os.getenv("FRED_API_KEY", "")
    if fred_key:
        registry.register(FredProvider(api_key=fred_key))
    else:
        logger.warning("No FRED API key configured — skipping FRED provider")

    # Yahoo Finance (no key needed)
    registry.register(YahooProvider())

    # Shipping indices
    registry.register(ShippingProvider())

    return registry


async def _fetch_all(registry: ProviderRegistry, cache: DataCache) -> dict[str, bool]:
    """Fetch data for every instrument and cache it.

    Returns a mapping of instrument_id → success boolean.
    """
    cfg = get_config()
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=365 * cfg.default_lookback_years)).strftime("%Y-%m-%d")

    results: dict[str, bool] = {}

    for instrument in registry.list_all_instruments():
        try:
            provider = registry.get_provider(instrument.provider)
            logger.info("Fetching %s (%s) …", instrument.id, instrument.name)
            df = await provider.fetch(instrument, start_date, end_date)

            if df.empty:
                logger.warning("  → no data returned for %s", instrument.id)
                results[instrument.id] = False
                continue

            cache.store_series(instrument.id, df, source=instrument.provider)
            logger.info("  → cached %d rows", len(df))
            results[instrument.id] = True
        except Exception:
            logger.exception("  → FAILED to fetch %s", instrument.id)
            results[instrument.id] = False

    return results


def _compute_stats(cache: DataCache, instrument_id: str) -> dict[str, Any]:
    """Compute summary statistics from cached data."""
    df = cache.get_series(instrument_id)
    if df.empty:
        return {"current": None, "min": None, "max": None, "mean": None, "pct_change": None}

    col = "close" if "close" in df.columns else "value"
    if col not in df.columns:
        return {"current": None, "min": None, "max": None, "mean": None, "pct_change": None}

    series = df[col].dropna()
    if series.empty:
        return {"current": None, "min": None, "max": None, "mean": None, "pct_change": None}

    pct_change = None
    if len(series) >= 2 and series.iloc[-2] != 0:
        pct_change = ((series.iloc[-1] - series.iloc[-2]) / series.iloc[-2]) * 100

    return {
        "current": float(series.iloc[-1]),
        "min": float(series.min()),
        "max": float(series.max()),
        "mean": float(series.mean()),
        "pct_change": float(pct_change) if pct_change is not None else None,
    }


def _generate_reports(
    registry: ProviderRegistry,
    cache: DataCache,
    fetch_results: dict[str, bool],
) -> int:
    """Generate dashboard and detail HTML reports. Returns count of pages written."""
    cfg = get_config()
    docs_dir = cfg.docs_dir
    template_dir = Path(__file__).resolve().parent.parent / "src" / "investment_mcp" / "reports" / "templates"
    gen = ReportGenerator(template_dir)
    chart_builder = ChartBuilder()
    count = 0

    # -- Detail pages for each instrument --------------------------------
    report_links: list[dict[str, str]] = []

    for instrument in registry.list_all_instruments():
        if not fetch_results.get(instrument.id, False):
            continue

        df = cache.get_series(instrument.id)
        if df.empty:
            continue

        # Build chart
        col = "close" if "close" in df.columns else "value"
        if col not in df.columns:
            continue

        chart_df = df[[col]].dropna()
        chart_json = chart_builder.build_line_chart(
            chart_df,
            title=instrument.name,
            y_label=instrument.unit or "Value",
        )

        stats = _compute_stats(cache, instrument.id)

        # Build recent_data rows with date, value, change
        col = "close" if "close" in df.columns else "value"
        recent = df[[col]].dropna().tail(10)
        recent_data = []
        prev_val = None
        for date_idx, row in recent.iterrows():
            val = float(row[col])
            change = (val - prev_val) if prev_val is not None else None
            recent_data.append({
                "date": str(date_idx)[:10],
                "value": val,
                "change": change,
            })
            prev_val = val

        # Sanitise instrument id for filename
        safe_id = instrument.id.replace(":", "_").replace("^", "")
        output_path = docs_dir / "reports" / f"{safe_id}.html"

        gen.generate_detail(
            instrument={"name": instrument.name, "symbol": instrument.ticker},
            chart_json=chart_json,
            stats=stats,
            recent_data=recent_data,
            output_path=output_path,
        )
        logger.info("  wrote %s", output_path)
        count += 1

        report_links.append({
            "title": instrument.name,
            "url": f"reports/{safe_id}.html",
            "description": instrument.description,
        })

    # -- Dashboard (index.html) ------------------------------------------
    charts: list[dict[str, str]] = []
    summary_cards: list[dict[str, str]] = []

    # Map provider/category to dashboard section names expected by the template
    SECTION_MAP = {"macro": "macro", "stock": "tanker", "shipping": "shipping"}

    for instrument in registry.list_all_instruments():
        if not fetch_results.get(instrument.id, False):
            continue

        df = cache.get_series(instrument.id)
        col = "close" if "close" in df.columns else "value"
        if col not in df.columns or df.empty:
            continue

        chart_df = df[[col]].dropna()
        chart_json = chart_builder.build_line_chart(
            chart_df, title=instrument.name, y_label=instrument.unit or "Value"
        )
        safe_id = instrument.id.replace(":", "_").replace("^", "")
        section = SECTION_MAP.get(instrument.category, "macro")
        charts.append({
            "div_id": f"chart-{safe_id}",
            "title": instrument.name,
            "plotly_json": chart_json,
            "section": section,
        })

        latest = chart_df.iloc[-1][col] if not chart_df.empty else None
        if latest is not None:
            summary_cards.append({"label": instrument.name, "value": f"{latest:,.2f}"})

    if charts:
        gen.generate_dashboard(
            charts=charts,
            summary_cards=summary_cards,
            output_path=docs_dir / "index.html",
        )
        logger.info("  wrote %s", docs_dir / "index.html")
        count += 1

    return count


async def main() -> None:
    """Entry point: fetch all data, generate all reports."""
    logger.info("=== Investment MCP — Data Fetch & Report Generation ===")

    cfg = get_config()
    cache = DataCache(cfg.cache_dir / "investment.db")
    registry = _build_registry()

    instruments = registry.list_all_instruments()
    logger.info("Registered %d instruments across %d providers", len(instruments), len(set(i.provider for i in instruments)))

    # Fetch
    fetch_results = await _fetch_all(registry, cache)
    ok = sum(1 for v in fetch_results.values() if v)
    fail = len(fetch_results) - ok
    logger.info("Fetch complete: %d succeeded, %d failed", ok, fail)

    # Generate reports
    pages = _generate_reports(registry, cache, fetch_results)
    logger.info("Generated %d report pages in %s", pages, cfg.docs_dir)

    logger.info("=== Done ===")


if __name__ == "__main__":
    asyncio.run(main())
