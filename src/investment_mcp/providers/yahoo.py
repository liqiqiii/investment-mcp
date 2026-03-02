"""Yahoo Finance data provider using yfinance."""

from __future__ import annotations

import asyncio
import functools
import logging

import pandas as pd
import yfinance as yf

from investment_mcp.providers.base import BaseProvider, Instrument

logger = logging.getLogger(__name__)


class YahooProvider(BaseProvider):
    """Fetches daily stock data from Yahoo Finance via the yfinance library."""

    name: str = "yahoo"

    def __init__(self) -> None:
        self._instruments: list[Instrument] = [
            Instrument(
                id="stock:FRO",
                name="Frontline PLC",
                description="Frontline PLC — international tanker shipping",
                category="stock",
                provider="yahoo",
                ticker="FRO",
                unit="USD",
            ),
            Instrument(
                id="stock:DHT",
                name="DHT Holdings",
                description="DHT Holdings — crude oil transportation",
                category="stock",
                provider="yahoo",
                ticker="DHT",
                unit="USD",
            ),
            Instrument(
                id="stock:INSW",
                name="International Seaways",
                description="International Seaways — tanker shipping",
                category="stock",
                provider="yahoo",
                ticker="INSW",
                unit="USD",
            ),
            Instrument(
                id="stock:TNK",
                name="Teekay Tankers",
                description="Teekay Tankers — crude and product tankers",
                category="stock",
                provider="yahoo",
                ticker="TNK",
                unit="USD",
            ),
            Instrument(
                id="stock:NAT",
                name="Nordic American Tankers",
                description="Nordic American Tankers — suezmax crude oil tankers",
                category="stock",
                provider="yahoo",
                ticker="NAT",
                unit="USD",
            ),
            Instrument(
                id="stock:STNG",
                name="Scorpio Tankers",
                description="Scorpio Tankers — product tanker shipping",
                category="stock",
                provider="yahoo",
                ticker="STNG",
                unit="USD",
            ),
            Instrument(
                id="stock:EURN",
                name="Euronav",
                description="Euronav — crude oil tanker shipping",
                category="stock",
                provider="yahoo",
                ticker="EURN",
                unit="USD",
            ),
            Instrument(
                id="stock:HAFN",
                name="Hafnia",
                description="Hafnia — product and chemical tankers (Oslo)",
                category="stock",
                provider="yahoo",
                ticker="HAFN.OL",
                unit="NOK",
                metadata={"exchange": "Oslo"},
            ),
            Instrument(
                id="stock:TRMD",
                name="TORM PLC",
                description="TORM PLC — product tanker shipping",
                category="stock",
                provider="yahoo",
                ticker="TRMD",
                unit="USD",
            ),
            Instrument(
                id="macro:TNX",
                name="10-Year Treasury Yield",
                description="US 10-Year Treasury Yield (via Yahoo Finance ^TNX)",
                category="macro",
                provider="yahoo",
                ticker="^TNX",
                unit="percent",
            ),
            Instrument(
                id="macro:TYX",
                name="30-Year Treasury Yield",
                description="US 30-Year Treasury Yield (via Yahoo Finance ^TYX)",
                category="macro",
                provider="yahoo",
                ticker="^TYX",
                unit="percent",
            ),
            Instrument(
                id="stock:IAU",
                name="iShares Gold Trust",
                description="iShares Gold Trust — gold ETF",
                category="stock",
                provider="yahoo",
                ticker="IAU",
                unit="USD",
                metadata={"type": "etf"},
            ),
            Instrument(
                id="stock:TSM",
                name="TSMC",
                description="TSMC — semiconductor manufacturing",
                category="stock",
                provider="yahoo",
                ticker="TSM",
                unit="USD",
            ),
            Instrument(
                id="stock:GOOGL",
                name="Alphabet Inc",
                description="Alphabet Inc — technology conglomerate",
                category="stock",
                provider="yahoo",
                ticker="GOOGL",
                unit="USD",
            ),
            Instrument(
                id="stock:MSFT",
                name="Microsoft Corp",
                description="Microsoft Corp — technology company",
                category="stock",
                provider="yahoo",
                ticker="MSFT",
                unit="USD",
            ),
        ]

    def list_instruments(self) -> list[Instrument]:
        """Return all instruments this provider supports."""
        return list(self._instruments)

    async def fetch(
        self,
        instrument: Instrument,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Fetch daily OHLCV data from Yahoo Finance.

        Args:
            instrument: The instrument to fetch data for.
            start_date: Start date in ISO format (YYYY-MM-DD).
            end_date: End date in ISO format (YYYY-MM-DD).

        Returns:
            DataFrame with DatetimeIndex named ``date`` and columns
            open, high, low, close, volume, value.
        """
        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(
            None,
            functools.partial(
                self._download, instrument.ticker, start_date, end_date
            ),
        )
        return df

    @staticmethod
    def _download(ticker: str, start: str, end: str) -> pd.DataFrame:
        """Blocking helper that calls yfinance and normalises the result."""
        try:
            t = yf.Ticker(ticker)
            df = t.history(start=start, end=end, interval="1d")
        except Exception:
            logger.exception("yfinance error for %s", ticker)
            return pd.DataFrame()

        if df is None or df.empty:
            logger.warning("No data returned for %s (%s – %s)", ticker, start, end)
            return pd.DataFrame()

        # Normalise column names to lowercase
        df.columns = [c.lower().replace(" ", "_") for c in df.columns]

        # Keep only OHLCV columns that exist
        keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
        df = df[keep].copy()

        # Add a 'value' column mirroring 'close' for compatibility
        if "close" in df.columns:
            df["value"] = df["close"]

        # Strip timezone info from the DatetimeIndex
        if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        df.index.name = "date"
        return df
