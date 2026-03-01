"""Shipping market data provider (Baltic indices via yfinance with fallback).

Shipping indices like the Baltic Dry Index (BDI) are available through Yahoo
Finance with limited history.  Other benchmarks — VLCC spot rates (TD3C),
Capesize 5TC, etc. — are behind the Baltic Exchange paywall or Clarksons
Platou and are *not* freely available.  This provider covers what can be
obtained from free public sources and degrades gracefully when data is
unavailable (returns an empty DataFrame rather than raising).

Users who need proprietary series should subclass or extend this provider
with their own API keys / data feeds.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial

import pandas as pd

from investment_mcp.providers.base import BaseProvider, Instrument

logger = logging.getLogger(__name__)

# ── Instrument catalogue ────────────────────────────────────────────────
_INSTRUMENTS: list[Instrument] = [
    Instrument(
        id="shipping:BDI",
        name="Baltic Dry Index",
        description=(
            "Composite index of dry-bulk shipping rates across Capesize, "
            "Panamax, and Supramax vessel classes.  Published daily by the "
            "Baltic Exchange."
        ),
        category="shipping",
        provider="shipping",
        ticker="^BDI",
        unit="index",
    ),
    Instrument(
        id="shipping:BDIY",
        name="Baltic Dirty Tanker Index",
        description=(
            "Composite index tracking dirty (crude-oil) tanker freight "
            "rates on key global routes.  Availability from free sources "
            "is limited; data may be sparse or unavailable."
        ),
        category="shipping",
        provider="shipping",
        ticker="^BDIY",
        unit="index",
        metadata={"note": "Limited free-source availability"},
    ),
]

_INSTRUMENT_MAP: dict[str, Instrument] = {inst.id: inst for inst in _INSTRUMENTS}


class ShippingProvider(BaseProvider):
    """Provider for shipping market indices.

    Data pipeline:
        1. Try **yfinance** (Yahoo Finance) — works for ``^BDI`` and
           sometimes ``^BDIY``.
        2. If yfinance returns no data, call ``_fetch_fallback()`` which is
           a placeholder for future web-scraping sources.
        3. Return whatever data is available (may be an empty DataFrame).
    """

    name: str = "shipping"

    # ── Public interface ────────────────────────────────────────────────

    def list_instruments(self) -> list[Instrument]:
        """Return all shipping instruments this provider supports."""
        return list(_INSTRUMENTS)

    async def fetch(
        self,
        instrument: Instrument,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Fetch time-series data for a shipping instrument.

        Tries yfinance first, then a fallback scraping stub.  Blocking
        I/O is offloaded to the default executor so the event loop stays
        responsive.

        Args:
            instrument: The shipping instrument to fetch.
            start_date: ISO start date (YYYY-MM-DD).
            end_date: ISO end date (YYYY-MM-DD).

        Returns:
            DataFrame with a DatetimeIndex named ``date`` and a ``value``
            column.  May be empty if no data source succeeds.
        """
        if instrument.id not in _INSTRUMENT_MAP:
            logger.error("Unknown instrument: %s", instrument.id)
            return pd.DataFrame(columns=["value"])

        loop = asyncio.get_running_loop()

        # 1. Try yfinance
        df = await loop.run_in_executor(
            None,
            partial(self._fetch_from_yfinance, instrument, start_date, end_date),
        )

        if not df.empty:
            return df

        # 2. Fallback (placeholder for future scraping sources)
        logger.info(
            "yfinance returned no data for %s; trying fallback", instrument.id
        )
        df = await loop.run_in_executor(
            None,
            partial(self._fetch_fallback, instrument, start_date, end_date),
        )

        if df.empty:
            logger.warning(
                "No data available for %s between %s and %s.  "
                "Shipping data coverage varies by source — consider adding "
                "a custom data feed for this instrument.",
                instrument.id,
                start_date,
                end_date,
            )

        return df

    # ── Private helpers ─────────────────────────────────────────────────

    def _fetch_from_yfinance(
        self,
        instrument: Instrument,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Download data via yfinance (blocking).

        Args:
            instrument: Target instrument (uses ``instrument.ticker``).
            start_date: ISO start date.
            end_date: ISO end date.

        Returns:
            Normalised DataFrame, or empty DataFrame on failure.
        """
        try:
            import yfinance as yf  # noqa: WPS433 — lazy import
        except ImportError:
            logger.warning(
                "yfinance is not installed; skipping Yahoo Finance source"
            )
            return pd.DataFrame(columns=["value"])

        try:
            ticker = yf.Ticker(instrument.ticker)
            hist = ticker.history(start=start_date, end=end_date)

            if hist is None or hist.empty:
                logger.debug(
                    "yfinance returned empty result for %s", instrument.ticker
                )
                return pd.DataFrame(columns=["value"])

            # Normalise to a single 'value' column (use Close price)
            df = hist[["Close"]].copy()
            df.columns = ["value"]
            df.index.name = "date"
            df.index = pd.to_datetime(df.index)

            # Basic quality check
            if df["value"].isna().all():
                logger.warning(
                    "All values are NaN for %s — data quality issue",
                    instrument.ticker,
                )
                return pd.DataFrame(columns=["value"])

            na_pct = df["value"].isna().mean()
            if na_pct > 0.3:
                logger.warning(
                    "%.0f%% of values are NaN for %s — data may be unreliable",
                    na_pct * 100,
                    instrument.ticker,
                )

            return df

        except Exception:
            logger.exception(
                "yfinance fetch failed for %s", instrument.ticker
            )
            return pd.DataFrame(columns=["value"])

    def _fetch_fallback(
        self,
        instrument: Instrument,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Fallback data source (placeholder).

        This method is a stub for future web-scraping or alternative-API
        integrations (e.g. investing.com, Trading Economics, Dryad Global).
        Currently it returns an empty DataFrame.

        To add a real scraping source, implement the fetch logic here using
        ``requests`` + ``BeautifulSoup`` (or similar) and return a DataFrame
        with a DatetimeIndex named ``date`` and a ``value`` column.

        Args:
            instrument: Target instrument.
            start_date: ISO start date.
            end_date: ISO end date.

        Returns:
            Empty DataFrame (no fallback source implemented yet).
        """
        logger.warning(
            "No fallback data source implemented for %s.  "
            "To add one, override ShippingProvider._fetch_fallback().",
            instrument.id,
        )
        return pd.DataFrame(columns=["value"])
