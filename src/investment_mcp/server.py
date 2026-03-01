"""
Investment MCP Server — main entry point.

Exposes financial data tools, report generation, and knowledge management
via the Model Context Protocol (MCP).
"""

import asyncio
import logging
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    Resource,
    ResourceTemplate,
)

from investment_mcp.config import get_config, InstrumentDef
from investment_mcp.providers.base import ProviderRegistry
from investment_mcp.cache.store import DataCache

logger = logging.getLogger(__name__)

# Global instances
app = Server("investment-mcp")
registry = ProviderRegistry()
cache: DataCache | None = None


def _init_providers() -> None:
    """Register all data providers."""
    from investment_mcp.providers.fred import FredProvider
    from investment_mcp.providers.yahoo import YahooProvider
    from investment_mcp.providers.shipping import ShippingProvider

    config = get_config()

    registry.register(FredProvider(api_key=config.fred_api_key))
    registry.register(YahooProvider())
    registry.register(ShippingProvider())

    logger.info(
        "Registered %d providers with %d instruments",
        len(registry._providers),
        len(registry.list_all_instruments()),
    )


def _init_cache() -> DataCache:
    """Initialize the data cache."""
    config = get_config()
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = config.cache_dir / "data_cache.db"
    return DataCache(db_path)


# ---------------------------------------------------------------------------
# Tool listing
# ---------------------------------------------------------------------------

@app.list_tools()
async def list_tools() -> list[Tool]:
    """Return all available MCP tools."""
    return [
        # Data tools
        Tool(
            name="list_instruments",
            description="List all available financial instruments with metadata. Optionally filter by category (macro, stock, shipping).",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Filter by category: macro, stock, shipping. Omit for all.",
                        "enum": ["macro", "stock", "shipping"],
                    }
                },
            },
        ),
        Tool(
            name="get_historical_data",
            description="Fetch historical time series data for a financial instrument. Returns date and value columns.",
            inputSchema={
                "type": "object",
                "properties": {
                    "instrument_id": {
                        "type": "string",
                        "description": "Instrument ID (e.g., 'fred:DGS10', 'stock:FRO', 'shipping:BDI')",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format. Defaults to 10 years ago.",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date in YYYY-MM-DD format. Defaults to today.",
                    },
                },
                "required": ["instrument_id"],
            },
        ),
        Tool(
            name="get_latest",
            description="Get the most recent data point for a financial instrument.",
            inputSchema={
                "type": "object",
                "properties": {
                    "instrument_id": {
                        "type": "string",
                        "description": "Instrument ID (e.g., 'fred:DGS10', 'stock:FRO')",
                    }
                },
                "required": ["instrument_id"],
            },
        ),
        Tool(
            name="compare_instruments",
            description="Get normalized comparison data for multiple instruments over the same time range.",
            inputSchema={
                "type": "object",
                "properties": {
                    "instrument_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of instrument IDs to compare",
                    },
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                },
                "required": ["instrument_ids"],
            },
        ),
        # Report tools
        Tool(
            name="generate_report",
            description="Generate an interactive HTML report with Plotly charts for selected instruments.",
            inputSchema={
                "type": "object",
                "properties": {
                    "instrument_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Instruments to include. Omit for all.",
                    },
                    "report_type": {
                        "type": "string",
                        "enum": ["dashboard", "detail"],
                        "description": "Report type: dashboard (overview) or detail (single instrument)",
                    },
                },
            },
        ),
        Tool(
            name="generate_dashboard",
            description="Generate a full overview dashboard with all tracked instruments.",
            inputSchema={"type": "object", "properties": {}},
        ),
        # Knowledge & notes tools
        Tool(
            name="get_knowledge",
            description="Retrieve a financial analysis knowledge file for context. Topics: vlcc_analysis, macro_indicators, shipping_market, yield_curve_analysis, tanker_company_profiles",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Knowledge topic name (without .md extension)",
                    }
                },
                "required": ["topic"],
            },
        ),
        Tool(
            name="list_knowledge",
            description="List all available financial analysis knowledge files.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="save_note",
            description="Save a conversation summary or analysis note as a markdown file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Note title (used for filename and heading)",
                    },
                    "content": {
                        "type": "string",
                        "description": "Markdown content of the note",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for categorization (e.g., 'vlcc', 'macro', 'analysis')",
                    },
                },
                "required": ["title", "content"],
            },
        ),
        Tool(
            name="search_notes",
            description="Full-text search through saved analysis notes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query string",
                    }
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="list_notes",
            description="List all saved analysis notes with dates, titles, and tags.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Route tool calls to implementations."""
    global cache

    if cache is None:
        cache = _init_cache()

    try:
        if name == "list_instruments":
            from investment_mcp.tools.data_tools import handle_list_instruments
            return await handle_list_instruments(registry, arguments)

        elif name == "get_historical_data":
            from investment_mcp.tools.data_tools import handle_get_historical_data
            return await handle_get_historical_data(registry, cache, arguments)

        elif name == "get_latest":
            from investment_mcp.tools.data_tools import handle_get_latest
            return await handle_get_latest(registry, cache, arguments)

        elif name == "compare_instruments":
            from investment_mcp.tools.data_tools import handle_compare_instruments
            return await handle_compare_instruments(registry, cache, arguments)

        elif name == "generate_report":
            from investment_mcp.tools.report_tools import handle_generate_report
            return await handle_generate_report(registry, cache, arguments)

        elif name == "generate_dashboard":
            from investment_mcp.tools.report_tools import handle_generate_dashboard
            return await handle_generate_dashboard(registry, cache, arguments)

        elif name == "get_knowledge":
            from investment_mcp.tools.note_tools import handle_get_knowledge
            return await handle_get_knowledge(arguments)

        elif name == "list_knowledge":
            from investment_mcp.tools.note_tools import handle_list_knowledge
            return await handle_list_knowledge()

        elif name == "save_note":
            from investment_mcp.tools.note_tools import handle_save_note
            return await handle_save_note(arguments)

        elif name == "search_notes":
            from investment_mcp.tools.note_tools import handle_search_notes
            return await handle_search_notes(arguments)

        elif name == "list_notes":
            from investment_mcp.tools.note_tools import handle_list_notes
            return await handle_list_notes()

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.exception("Tool %s failed", name)
        return [TextContent(type="text", text=f"Error: {e}")]


# ---------------------------------------------------------------------------
# Resource listing (knowledge files)
# ---------------------------------------------------------------------------

@app.list_resources()
async def list_resources() -> list[Resource]:
    """Expose knowledge files as MCP resources."""
    config = get_config()
    resources = []
    knowledge_dir = config.knowledge_dir

    if knowledge_dir.exists():
        for md_file in sorted(knowledge_dir.glob("*.md")):
            resources.append(
                Resource(
                    uri=f"knowledge://{md_file.stem}",
                    name=md_file.stem.replace("_", " ").title(),
                    description=f"Financial analysis knowledge: {md_file.stem}",
                    mimeType="text/markdown",
                )
            )

    return resources


@app.read_resource()
async def read_resource(uri: str) -> str:
    """Read a knowledge resource by URI."""
    config = get_config()

    if uri.startswith("knowledge://"):
        topic = uri.replace("knowledge://", "")
        file_path = config.knowledge_dir / f"{topic}.md"
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
        raise FileNotFoundError(f"Knowledge file not found: {topic}")

    raise ValueError(f"Unknown resource URI scheme: {uri}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the MCP server via stdio transport."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    logger.info("Starting Investment MCP Server v0.1.0")
    _init_providers()

    async def _run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())

    asyncio.run(_run())


if __name__ == "__main__":
    main()
