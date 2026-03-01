"""Configuration for Investment MCP Server.

Loads settings from environment variables (prefixed INVESTMENT_) and .env file.
Provides instrument registry for FRED series, stock tickers, and shipping indices.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Package / project path anchors
# ---------------------------------------------------------------------------
_PACKAGE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _PACKAGE_DIR.parent.parent  # src/investment_mcp -> src -> project root


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
class Settings(BaseSettings):
    """Application settings populated from environment variables and .env."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="INVESTMENT_")

    # --- API keys ---
    fred_api_key: str = ""

    # --- Directories ---
    cache_dir: Path = Path.home() / ".investment-mcp" / "cache"
    notes_dir: Path = _PACKAGE_DIR / "notes"
    knowledge_dir: Path = _PACKAGE_DIR / "knowledge"
    docs_dir: Path = _PROJECT_ROOT / "docs"

    # --- GitHub Pages ---
    github_pages_repo: str | None = None

    # --- Data defaults ---
    default_lookback_years: int = 10
    data_interval: str = "1d"


# ---------------------------------------------------------------------------
# Instrument registry
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Instrument:
    """Metadata for a tracked financial instrument or economic series."""

    id: str
    name: str
    description: str
    category: str
    provider: str


@dataclass(frozen=True)
class InstrumentRegistry:
    """Registry of all tracked instruments, organised by category."""

    fred_series: tuple[Instrument, ...] = field(default_factory=tuple)
    stock_tickers: tuple[Instrument, ...] = field(default_factory=tuple)
    shipping_indices: tuple[Instrument, ...] = field(default_factory=tuple)

    @property
    def all_instruments(self) -> tuple[Instrument, ...]:
        return self.fred_series + self.stock_tickers + self.shipping_indices


# --- Default instrument instances ---

FRED_SERIES: tuple[Instrument, ...] = (
    Instrument("DGS10", "10-Year Treasury Yield", "Constant maturity 10-year Treasury rate", "macro", "fred"),
    Instrument("DGS30", "30-Year Treasury Yield", "Constant maturity 30-year Treasury rate", "macro", "fred"),
    Instrument("DGS2", "2-Year Treasury Yield", "Constant maturity 2-year Treasury rate", "macro", "fred"),
    Instrument("DFF", "Federal Funds Rate", "Effective federal funds rate", "macro", "fred"),
    Instrument("CPIAUCSL", "CPI", "Consumer Price Index for All Urban Consumers", "macro", "fred"),
    Instrument("GDP", "GDP", "Gross Domestic Product", "macro", "fred"),
)

STOCK_TICKERS: tuple[Instrument, ...] = (
    Instrument("FRO", "Frontline", "VLCC/Suezmax tanker operator", "tanker", "yfinance"),
    Instrument("DHT", "DHT Holdings", "VLCC tanker operator", "tanker", "yfinance"),
    Instrument("INSW", "International Seaways", "Crude and product tanker operator", "tanker", "yfinance"),
    Instrument("TNK", "Teekay Tankers", "Crude tanker operator (mid-size)", "tanker", "yfinance"),
    Instrument("NAT", "Nordic American Tankers", "Suezmax tanker operator", "tanker", "yfinance"),
    Instrument("STNG", "Scorpio Tankers", "Product tanker operator", "tanker", "yfinance"),
    Instrument("EURN", "Euronav", "VLCC/Suezmax tanker operator", "tanker", "yfinance"),
    Instrument("HAFN.OL", "Hafnia", "Product/chemical tanker operator (Oslo)", "tanker", "yfinance"),
    Instrument("TRMD", "TORM", "Product tanker operator", "tanker", "yfinance"),
)

SHIPPING_INDICES: tuple[Instrument, ...] = (
    Instrument("^BDI", "Baltic Dry Index", "Composite shipping cost index for dry bulk", "shipping", "yfinance"),
)

DEFAULT_REGISTRY = InstrumentRegistry(
    fred_series=FRED_SERIES,
    stock_tickers=STOCK_TICKERS,
    shipping_indices=SHIPPING_INDICES,
)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_config() -> Settings:
    """Return a singleton Settings instance."""
    return Settings()


def get_registry() -> InstrumentRegistry:
    """Return the default instrument registry."""
    return DEFAULT_REGISTRY
