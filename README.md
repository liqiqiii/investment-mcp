# 📈 Investment MCP Server

> Personal investment analysis toolkit — macroeconomic data, shipping markets, and tanker equities via the [Model Context Protocol](https://modelcontextprotocol.io/).

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-compatible-8A2BE2)](https://modelcontextprotocol.io/)

---

## 🖥️ Live Dashboard

**👉 [liqiqiii.github.io/investment-mcp](https://liqiqiii.github.io/investment-mcp/)**

The dashboard updates automatically on weekdays via GitHub Actions. Open it on your phone or desktop for an at-a-glance view of all tracked instruments with interactive Plotly charts.

| Report | Link |
|--------|------|
| **Full Dashboard** | [liqiqiii.github.io/investment-mcp](https://liqiqiii.github.io/investment-mcp/) |
| Frontline (FRO) | [Detail page](https://liqiqiii.github.io/investment-mcp/reports/stock_FRO.html) |
| DHT Holdings (DHT) | [Detail page](https://liqiqiii.github.io/investment-mcp/reports/stock_DHT.html) |
| International Seaways (INSW) | [Detail page](https://liqiqiii.github.io/investment-mcp/reports/stock_INSW.html) |
| Teekay Tankers (TNK) | [Detail page](https://liqiqiii.github.io/investment-mcp/reports/stock_TNK.html) |
| Nordic American Tankers (NAT) | [Detail page](https://liqiqiii.github.io/investment-mcp/reports/stock_NAT.html) |
| Scorpio Tankers (STNG) | [Detail page](https://liqiqiii.github.io/investment-mcp/reports/stock_STNG.html) |
| TORM PLC (TRMD) | [Detail page](https://liqiqiii.github.io/investment-mcp/reports/stock_TRMD.html) |

> **Macro data** (Treasury yields, CPI, GDP) will appear once a [free FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html) is configured.

---

## Overview

Investment MCP Server is an MCP-compatible server that surfaces financial market data, interactive charting, and a curated knowledge base to any MCP client (Claude Desktop, VS Code Copilot, etc.). It is designed for individual investors who track:

- **Macro indicators** — Treasury yields, the Fed Funds Rate, CPI, and GDP via FRED.
- **Tanker equities** — VLCC, Suezmax, and product tanker stocks (Frontline, DHT, Scorpio Tankers, and more) via Yahoo Finance.
- **Shipping indices** — Baltic Dry Index and Baltic Dirty Tanker Index.

Data is fetched on demand, cached locally in SQLite, and can be rendered into interactive Plotly dashboards deployed to GitHub Pages.

---

## Features

- **11 MCP tools** for data retrieval, report generation, and knowledge management
- **Interactive Plotly charts** — responsive, mobile-friendly HTML reports
- **Daily data** from FRED, Yahoo Finance, and shipping market sources
- **Auto-deployed GitHub Pages dashboard** for at-a-glance portfolio views
- **Financial analysis knowledge base** — curated markdown skill files on VLCC analysis, yield curves, and more
- **Conversation auto-summarization** — save and search analysis notes across sessions
- **Distributable as a standalone binary** via PyInstaller
- **Extensible provider plugin architecture** — add new data sources by subclassing `BaseProvider`

---

## Quick Start

### Prerequisites

- Python 3.11 or later
- A free [FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html)

### Install

```bash
git clone https://github.com/liqiqiii/investment-mcp.git
cd investment-mcp
pip install -e .
```

### Configure

Copy the example environment file and fill in your API key:

```bash
cp .env.example .env
```

```dotenv
# .env
INVESTMENT_FRED_API_KEY=your_fred_api_key_here
```

### Run

```bash
investment-mcp
```

The server starts and communicates over **stdio** — connect it to any MCP client as shown below.

---

## MCP Client Configuration

### Claude Desktop

Add to your `claude_desktop_config.json`:

```jsonc
{
  "mcpServers": {
    "investment-mcp": {
      "command": "investment-mcp",
      "env": {
        "INVESTMENT_FRED_API_KEY": "your_fred_api_key_here"
      }
    }
  }
}
```

### VS Code / GitHub Copilot

Add to your VS Code `settings.json`:

```jsonc
{
  "mcp": {
    "servers": {
      "investment-mcp": {
        "command": "investment-mcp",
        "env": {
          "INVESTMENT_FRED_API_KEY": "your_fred_api_key_here"
        }
      }
    }
  }
}
```

### Generic stdio Transport

Any MCP client that supports the stdio transport can launch the server:

```jsonc
{
  "command": "investment-mcp",
  "transport": "stdio",
  "env": {
    "INVESTMENT_FRED_API_KEY": "your_fred_api_key_here"
  }
}
```

> **Tip:** If you installed with `pip install -e .`, the `investment-mcp` entry point is on your PATH. Otherwise, use the full path to the executable or `python -m investment_mcp.server`.

---

## Available Tools

| # | Tool | Description | Required Params |
|---|------|-------------|-----------------|
| 1 | `list_instruments` | List all tracked instruments; optionally filter by category (`macro`, `stock`, `shipping`). | — |
| 2 | `get_historical_data` | Fetch historical time-series data for an instrument. | `instrument_id` |
| 3 | `get_latest` | Get the most recent data point for an instrument. | `instrument_id` |
| 4 | `compare_instruments` | Normalized comparison of multiple instruments over the same time range. | `instrument_ids` |
| 5 | `generate_report` | Generate an interactive HTML report with Plotly charts. | — |
| 6 | `generate_dashboard` | Generate a full overview dashboard for all tracked instruments. | — |
| 7 | `get_knowledge` | Retrieve a knowledge-base article by topic name. | `topic` |
| 8 | `list_knowledge` | List all available knowledge-base articles. | — |
| 9 | `save_note` | Save a conversation summary or analysis note as markdown. | `title`, `content` |
| 10 | `search_notes` | Full-text search through saved analysis notes. | `query` |
| 11 | `list_notes` | List all saved notes with dates, titles, and tags. | — |

### Instrument ID Format

Instrument IDs follow the pattern `<provider>:<ticker>`:

```
fred:DGS10      — 10-Year Treasury Yield (FRED)
stock:FRO       — Frontline PLC (Yahoo Finance)
shipping:BDI    — Baltic Dry Index (Shipping)
```

---

## Tracked Instruments

### Macro (FRED)

| ID | Name | Description | Unit |
|----|------|-------------|------|
| `fred:DGS10` | 10-Year Treasury Yield | Constant maturity 10-year Treasury rate | percent |
| `fred:DGS30` | 30-Year Treasury Yield | Constant maturity 30-year Treasury rate | percent |
| `fred:DGS2` | 2-Year Treasury Yield | Constant maturity 2-year Treasury rate | percent |
| `fred:DFF` | Federal Funds Rate | Effective federal funds rate | percent |
| `fred:CPIAUCSL` | Consumer Price Index | CPI for All Urban Consumers | index |
| `fred:GDP` | Gross Domestic Product | U.S. GDP | billions USD |

### Tanker Stocks (Yahoo Finance)

| ID | Name | Description | Currency |
|----|------|-------------|----------|
| `stock:FRO` | Frontline PLC | International tanker shipping | USD |
| `stock:DHT` | DHT Holdings | Crude oil transportation | USD |
| `stock:INSW` | International Seaways | Tanker shipping | USD |
| `stock:TNK` | Teekay Tankers | Crude and product tankers | USD |
| `stock:NAT` | Nordic American Tankers | Suezmax crude oil tankers | USD |
| `stock:STNG` | Scorpio Tankers | Product tanker shipping | USD |
| `stock:EURN` | Euronav | Crude oil tanker shipping | USD |
| `stock:HAFN` | Hafnia | Product/chemical tankers (Oslo) | NOK |
| `stock:TRMD` | TORM PLC | Product tanker shipping | USD |

### Shipping Indices

| ID | Name | Description |
|----|------|-------------|
| `shipping:BDI` | Baltic Dry Index | Composite dry-bulk shipping rate index |
| `shipping:BDIY` | Baltic Dirty Tanker Index | Dirty (crude-oil) tanker freight rates |

---

## GitHub Pages Dashboard

The live dashboard is at **[liqiqiii.github.io/investment-mcp](https://liqiqiii.github.io/investment-mcp/)** — see the top of this README for all links.

### How It Works

1. `scripts/fetch_data.py` pulls daily data from all providers and generates HTML reports into `docs/`.
2. The `update_data.yml` GitHub Actions workflow runs this automatically every weekday at 6 AM UTC.
3. The `deploy_pages.yml` workflow deploys `docs/` to GitHub Pages whenever it changes.

### Manual Refresh

```bash
python scripts/fetch_data.py    # Fetch data + regenerate all reports
git add docs/ && git commit -m "Update dashboard" && git push
```

Generated reports are self-contained HTML files with embedded Plotly.js — no server required.

---

## Binary Distribution

You can package the server as a standalone executable using PyInstaller so it runs without a Python installation.

### Build

```bash
pip install -e ".[dev]"
pyinstaller --onefile --name investment-mcp src/investment_mcp/server.py
```

The binary is output to `dist/investment-mcp` (or `dist\investment-mcp.exe` on Windows).

### Run

```bash
# Linux / macOS
./dist/investment-mcp

# Windows
dist\investment-mcp.exe
```

Point your MCP client configuration at the binary path instead of the `investment-mcp` entry point.

---

## Extending

### Adding a New Data Provider

1. **Create a provider module** in `src/investment_mcp/providers/`:

```python
from investment_mcp.providers.base import BaseProvider, Instrument

class MyProvider(BaseProvider):
    name: str = "myprovider"

    def list_instruments(self) -> list[Instrument]:
        return [
            Instrument(
                id="myprovider:TICKER",
                name="My Instrument",
                description="Description here",
                category="custom",
                provider="myprovider",
                ticker="TICKER",
                unit="USD",
            ),
        ]

    async def fetch(self, instrument, start_date, end_date):
        # Return a pandas DataFrame with a DatetimeIndex and value columns
        ...
```

2. **Register the provider** in `server.py` → `_init_providers()`:

```python
from investment_mcp.providers.my_provider import MyProvider
registry.register(MyProvider())
```

The new instruments will automatically appear in `list_instruments` and be available to all data and report tools.

---

## Knowledge Base

The built-in knowledge base provides curated analysis frameworks as MCP resources. Access them with the `get_knowledge` tool or browse via `list_knowledge`.

| File | Topic |
|------|-------|
| `vlcc_analysis.md` | VLCC fleet dynamics, order book, scrapping trends |
| `macro_indicators.md` | Key macro indicators and their market impact |
| `shipping_market.md` | Shipping market structure and rate drivers |
| `yield_curve_analysis.md` | Yield curve interpretation and recession signals |
| `tanker_company_profiles.md` | Profiles of tracked tanker companies |

Knowledge files are stored in `src/investment_mcp/knowledge/` and are also exposed as MCP resources under the `knowledge://` URI scheme.

---

## Project Structure

```
investment-mcp/
├── .env.example                  # Environment variable template
├── .github/workflows/            # CI / GitHub Pages deployment
├── docs/reports/                 # Generated HTML reports (gitkeep)
├── pyproject.toml                # Build config, dependencies, entry points
├── src/investment_mcp/
│   ├── __init__.py
│   ├── server.py                 # MCP server entry point & tool definitions
│   ├── config.py                 # Settings, instrument registry
│   ├── cache/
│   │   └── store.py              # SQLite data cache
│   ├── knowledge/                # Curated markdown skill files
│   │   ├── macro_indicators.md
│   │   ├── shipping_market.md
│   │   ├── tanker_company_profiles.md
│   │   ├── vlcc_analysis.md
│   │   └── yield_curve_analysis.md
│   ├── notes/                    # Saved analysis notes (user-generated)
│   ├── providers/
│   │   ├── base.py               # BaseProvider ABC & ProviderRegistry
│   │   ├── fred.py               # FRED economic data provider
│   │   ├── yahoo.py              # Yahoo Finance stock provider
│   │   └── shipping.py           # Shipping index provider
│   ├── reports/                  # Report generation (Plotly/Jinja2)
│   └── tools/
│       ├── data_tools.py         # list_instruments, get_historical_data, etc.
│       ├── report_tools.py       # generate_report, generate_dashboard
│       └── note_tools.py         # Knowledge & notes tools
└── tests/                        # pytest test suite
```

---

## License

This project is licensed under the [MIT License](LICENSE).
