"""Knowledge and note management tools for the Investment MCP Server.

Provides handlers for reading knowledge files, saving analysis notes,
and searching through saved notes.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from mcp.types import TextContent

from investment_mcp.config import get_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert *text* to a lowercase, hyphen-separated, filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def _parse_frontmatter(content: str) -> dict[str, str | list[str]]:
    """Parse simple YAML-like frontmatter delimited by ``---``."""
    meta: dict[str, str | list[str]] = {}
    if not content.startswith("---"):
        return meta

    end = content.find("---", 3)
    if end == -1:
        return meta

    for line in content[3:end].strip().splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key] = [v.strip().strip("\"'") for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key] = value
    return meta


def _update_index(notes_dir: Path) -> None:
    """Regenerate ``index.md`` listing all notes in *notes_dir*."""
    notes = sorted(
        [f for f in notes_dir.glob("*.md") if f.name != "index.md"],
        reverse=True,
    )

    lines = ["# Notes Index", "", f"_Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_", ""]

    for note_path in notes:
        meta = _parse_frontmatter(note_path.read_text(encoding="utf-8"))
        title = meta.get("title", note_path.stem)
        date = meta.get("date", "unknown")
        tags = meta.get("tags", [])
        tag_str = f"  `{'`, `'.join(tags)}`" if tags else ""
        lines.append(f"- **[{title}]({note_path.name})** — {date}{tag_str}")

    lines.append("")
    (notes_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Knowledge handlers
# ---------------------------------------------------------------------------

async def handle_get_knowledge(arguments: dict) -> list[TextContent]:
    """Retrieve a knowledge file by topic name."""
    topic: str = arguments["topic"]
    config = get_config()
    file_path = config.knowledge_dir / f"{topic}.md"

    if not file_path.exists():
        available = [f.stem for f in config.knowledge_dir.glob("*.md")] if config.knowledge_dir.exists() else []
        msg = f"Knowledge topic '{topic}' not found."
        if available:
            msg += f" Available topics: {', '.join(sorted(available))}"
        return [TextContent(type="text", text=msg)]

    content = file_path.read_text(encoding="utf-8")
    return [TextContent(type="text", text=content)]


async def handle_list_knowledge() -> list[TextContent]:
    """List all available knowledge files."""
    config = get_config()
    knowledge_dir = config.knowledge_dir

    if not knowledge_dir.exists():
        return [TextContent(type="text", text="No knowledge directory found.")]

    files = sorted(knowledge_dir.glob("*.md"))
    if not files:
        return [TextContent(type="text", text="No knowledge files available.")]

    lines = ["# Available Knowledge Files", ""]
    for f in files:
        size_kb = f.stat().st_size / 1024
        name = f.stem.replace("_", " ").title()
        lines.append(f"- **{name}** (`{f.stem}`) — {size_kb:.1f} KB")

    lines.append(f"\nTotal: {len(files)} files")
    return [TextContent(type="text", text="\n".join(lines))]


# ---------------------------------------------------------------------------
# Note handlers
# ---------------------------------------------------------------------------

async def handle_save_note(arguments: dict) -> list[TextContent]:
    """Save a new analysis note with frontmatter."""
    title: str = arguments["title"]
    content: str = arguments["content"]
    tags: list[str] = arguments.get("tags", [])

    config = get_config()
    notes_dir = config.notes_dir
    notes_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = _slugify(title)
    filename = f"{date_str}_{slug}.md"
    file_path = notes_dir / filename

    # Build frontmatter
    tag_line = f"tags: [{', '.join(tags)}]" if tags else "tags: []"
    note_text = (
        f"---\n"
        f"title: {title}\n"
        f"date: {date_str}\n"
        f"{tag_line}\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"{content}\n"
    )

    file_path.write_text(note_text, encoding="utf-8")
    logger.info("Saved note: %s", file_path)

    _update_index(notes_dir)

    return [TextContent(type="text", text=f"Note saved: {filename}\nPath: {file_path}")]


async def handle_search_notes(arguments: dict) -> list[TextContent]:
    """Search notes by case-insensitive substring match."""
    query: str = arguments["query"]
    config = get_config()
    notes_dir = config.notes_dir

    if not notes_dir.exists():
        return [TextContent(type="text", text="No notes directory found.")]

    query_lower = query.lower()
    results: list[str] = []

    for note_path in sorted(notes_dir.glob("*.md")):
        if note_path.name == "index.md":
            continue

        content = note_path.read_text(encoding="utf-8")
        name_match = query_lower in note_path.stem.lower()
        content_lower = content.lower()
        content_match = query_lower in content_lower

        if not (name_match or content_match):
            continue

        meta = _parse_frontmatter(content)
        title = meta.get("title", note_path.stem)
        date = meta.get("date", "unknown")

        # Extract snippet around first content match
        snippet = ""
        if content_match:
            idx = content_lower.index(query_lower)
            start = max(0, idx - 50)
            end = min(len(content), idx + len(query) + 50)
            raw = content[start:end].replace("\n", " ").strip()
            if start > 0:
                raw = "…" + raw
            if end < len(content):
                raw = raw + "…"
            snippet = f"\n  > {raw}"

        results.append(f"- **{title}** ({date}) — `{note_path.name}`{snippet}")

    if not results:
        return [TextContent(type="text", text=f"No notes matching '{query}'.")]

    header = f"# Search results for '{query}'\n\nFound {len(results)} note(s):\n"
    return [TextContent(type="text", text=header + "\n".join(results))]


async def handle_list_notes() -> list[TextContent]:
    """List all saved notes sorted by date (newest first)."""
    config = get_config()
    notes_dir = config.notes_dir

    if not notes_dir.exists():
        return [TextContent(type="text", text="No notes directory found.")]

    note_files = [f for f in notes_dir.glob("*.md") if f.name != "index.md"]
    if not note_files:
        return [TextContent(type="text", text="No notes saved yet.")]

    # Parse metadata and sort by date descending
    entries: list[tuple[str, str, str, list[str]]] = []
    for f in note_files:
        meta = _parse_frontmatter(f.read_text(encoding="utf-8"))
        title = meta.get("title", f.stem)
        date = meta.get("date", "unknown")
        tags = meta.get("tags", [])
        if isinstance(tags, str):
            tags = [tags] if tags else []
        entries.append((date, title, f.name, tags))

    entries.sort(key=lambda e: e[0], reverse=True)

    lines = ["# Saved Notes", ""]
    for date, title, fname, tags in entries:
        tag_str = f"  `{'`, `'.join(tags)}`" if tags else ""
        lines.append(f"- **{title}** — {date} (`{fname}`){tag_str}")

    lines.append(f"\nTotal: {len(entries)} notes")
    return [TextContent(type="text", text="\n".join(lines))]
