"""FRED (Federal Reserve Economic Data) provider."""

from __future__ import annotations

import asyncio
from functools import partial

import pandas as pd
from fredapi import Fred

from investment_mcp.providers.base import BaseProvider, Instrument


class FredProvider(BaseProvider):
    """Data provider that fetches economic series from the FRED API."""

    name: str = "fred"

    _INSTRUMENTS = [
        Instrument(
            id="fred:DGS10",
            name="10-Year Treasury Yield",
            description="Constant maturity 10-year Treasury rate",
            category="macro",
            provider="fred",
            ticker="DGS10",
            unit="percent",
        ),
        Instrument(
            id="fred:DGS30",
            name="30-Year Treasury Yield",
            description="Constant maturity 30-year Treasury rate",
            category="macro",
            provider="fred",
            ticker="DGS30",
            unit="percent",
        ),
        Instrument(
            id="fred:DGS2",
            name="2-Year Treasury Yield",
            description="Constant maturity 2-year Treasury rate",
            category="macro",
            provider="fred",
            ticker="DGS2",
            unit="percent",
        ),
        Instrument(
            id="fred:DFF",
            name="Federal Funds Rate",
            description="Effective federal funds rate",
            category="macro",
            provider="fred",
            ticker="DFF",
            unit="percent",
        ),
        Instrument(
            id="fred:CPIAUCSL",
            name="Consumer Price Index",
            description="Consumer Price Index for All Urban Consumers",
            category="macro",
            provider="fred",
            ticker="CPIAUCSL",
            unit="index",
        ),
        Instrument(
            id="fred:GDP",
            name="Gross Domestic Product",
            description="Gross Domestic Product",
            category="macro",
            provider="fred",
            ticker="GDP",
            unit="billions_usd",
        ),
    ]

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = Fred(api_key=api_key)
        self._instruments = list(self._INSTRUMENTS)

    async def fetch(
        self,
        instrument: Instrument,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Fetch a FRED series as a DataFrame with a DatetimeIndex and 'value' column.

        The blocking ``fredapi`` call is executed in an asyncio executor so
        the event loop is never blocked.

        Args:
            instrument: The FRED instrument to fetch.
            start_date: Start date in ISO format (YYYY-MM-DD).
            end_date: End date in ISO format (YYYY-MM-DD).

        Returns:
            DataFrame with DatetimeIndex named ``date`` and a ``value`` column.
            Rows where FRED returned NaN (e.g. holidays) are dropped.
        """
        loop = asyncio.get_event_loop()
        series: pd.Series = await loop.run_in_executor(
            None,
            partial(
                self._client.get_series,
                instrument.ticker,
                observation_start=start_date,
                observation_end=end_date,
            ),
        )

        df = series.to_frame(name="value")
        df.index.name = "date"
        df = df.dropna(subset=["value"])
        return df

    def list_instruments(self) -> list[Instrument]:
        """Return all FRED instruments supported by this provider."""
        return list(self._instruments)
