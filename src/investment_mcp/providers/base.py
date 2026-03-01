"""Abstract base provider and registry for investment data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd


@dataclass
class Instrument:
    """A single trackable financial instrument or economic series."""

    id: str  # unique ID like "fred:DGS10" or "stock:FRO"
    name: str  # human-readable name "10-Year Treasury Yield"
    description: str  # longer description
    category: str  # "macro", "stock", "shipping"
    provider: str  # provider name "fred", "yahoo", "shipping"
    ticker: str  # raw ticker/series ID (DGS10, FRO, ^BDI)
    unit: str = ""  # "percent", "USD", "index"
    metadata: dict = field(default_factory=dict)  # extra info


class BaseProvider(ABC):
    """Abstract base class that every data provider must implement."""

    name: str  # provider identifier, set by subclasses

    @abstractmethod
    async def fetch(
        self,
        instrument: Instrument,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Fetch time-series data for an instrument.

        Args:
            instrument: The instrument to fetch data for.
            start_date: Start date in ISO format (YYYY-MM-DD).
            end_date: End date in ISO format (YYYY-MM-DD).

        Returns:
            DataFrame with a DatetimeIndex named ``date`` and one or more
            value columns.
        """

    @abstractmethod
    def list_instruments(self) -> list[Instrument]:
        """Return all instruments this provider supports."""

    async def get_latest(self, instrument: Instrument) -> dict | None:
        """Get the most recent data point for an instrument.

        Default implementation fetches the last 5 days and returns the
        latest available row as a dict.

        Args:
            instrument: The instrument to query.

        Returns:
            A dict of the latest row, or ``None`` if no data is available.
        """
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        df = await self.fetch(instrument, start, end)
        if df.empty:
            return None
        latest = df.iloc[-1]
        result = latest.to_dict()
        result["date"] = str(latest.name)
        return result


class ProviderRegistry:
    """Central registry that aggregates all data providers and their instruments."""

    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}
        self._instruments: dict[str, Instrument] = {}

    def register(self, provider: BaseProvider) -> None:
        """Register a provider and index its instruments.

        Args:
            provider: A concrete ``BaseProvider`` instance.

        Raises:
            ValueError: If a provider with the same name is already registered.
        """
        if provider.name in self._providers:
            raise ValueError(f"Provider '{provider.name}' is already registered")
        self._providers[provider.name] = provider
        for instrument in provider.list_instruments():
            self._instruments[instrument.id] = instrument

    def get_provider(self, name: str) -> BaseProvider:
        """Look up a provider by its unique name.

        Args:
            name: Provider identifier (e.g. ``"fred"``).

        Raises:
            KeyError: If the provider is not registered.
        """
        if name not in self._providers:
            raise KeyError(f"Provider '{name}' not found")
        return self._providers[name]

    def get_instrument(self, instrument_id: str) -> Instrument:
        """Look up an instrument by its full ID.

        Args:
            instrument_id: Fully-qualified ID (e.g. ``"fred:DGS10"``).

        Raises:
            KeyError: If the instrument is not registered.
        """
        if instrument_id not in self._instruments:
            raise KeyError(f"Instrument '{instrument_id}' not found")
        return self._instruments[instrument_id]

    def list_all_instruments(self) -> list[Instrument]:
        """Return every instrument across all registered providers."""
        return list(self._instruments.values())

    def list_by_category(self, category: str) -> list[Instrument]:
        """Return instruments filtered by category.

        Args:
            category: Category string (e.g. ``"macro"``, ``"stock"``).
        """
        return [i for i in self._instruments.values() if i.category == category]
