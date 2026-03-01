"""Build a standalone investment-mcp binary using PyInstaller."""

import argparse
import os
import platform
import shutil
import sys
from pathlib import Path


def get_project_root() -> Path:
    """Return the project root (parent of the scripts/ directory)."""
    return Path(__file__).resolve().parent.parent


def build(clean: bool = False) -> None:
    root = get_project_root()
    src = root / "src" / "investment_mcp"
    dist_dir = root / "dist"
    build_dir = root / "build"
    spec_file = root / "investment-mcp.spec"

    # --clean: remove previous build artifacts
    if clean:
        for path in (dist_dir, build_dir):
            if path.exists():
                print(f"Removing {path}")
                shutil.rmtree(path)
        if spec_file.exists():
            print(f"Removing {spec_file}")
            spec_file.unlink()

    entry_point = src / "server.py"
    if not entry_point.exists():
        print(f"Error: entry point not found: {entry_point}", file=sys.stderr)
        sys.exit(1)

    # Platform-specific path separator for --add-data
    sep = ";" if platform.system() == "Windows" else ":"

    # Collect --add-data entries
    add_data: list[str] = []

    knowledge_dir = src / "knowledge"
    if knowledge_dir.is_dir():
        for md_file in sorted(knowledge_dir.glob("*.md")):
            add_data.append(f"{md_file}{sep}investment_mcp/knowledge")

    templates_dir = src / "reports" / "templates"
    if templates_dir.is_dir():
        for html_file in sorted(templates_dir.glob("*.html")):
            add_data.append(f"{html_file}{sep}investment_mcp/reports/templates")

    # Hidden imports that PyInstaller may not detect automatically
    hidden_imports = [
        "fredapi",
        "yfinance",
        "plotly",
        "jinja2",
        "bs4",
        "aiohttp",
        "pydantic",
        "pydantic_settings",
        "dotenv",
        "pandas",
        "requests",
    ]

    # Assemble PyInstaller arguments
    args = [
        str(entry_point),
        "--onefile",
        "--name", "investment-mcp",
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir),
        "--specpath", str(root),
    ]

    for item in add_data:
        args.extend(["--add-data", item])

    for mod in hidden_imports:
        args.extend(["--hidden-import", mod])

    print("=" * 60)
    print("Building investment-mcp standalone binary")
    print(f"  Entry point : {entry_point}")
    print(f"  Data files  : {len(add_data)}")
    print(f"  Platform    : {platform.system()} ({platform.machine()})")
    print("=" * 60)

    import PyInstaller.__main__  # noqa: E402

    PyInstaller.__main__.run(args)

    # Build summary
    exe_name = "investment-mcp.exe" if platform.system() == "Windows" else "investment-mcp"
    output_path = dist_dir / exe_name

    print()
    print("=" * 60)
    if output_path.exists():
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print("Build succeeded!")
        print(f"  Output : {output_path}")
        print(f"  Size   : {size_mb:.1f} MB")
    else:
        print("Build finished but output binary was not found.")
        print(f"  Expected: {output_path}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build investment-mcp standalone binary")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove previous build artifacts before building",
    )
    args = parser.parse_args()
    build(clean=args.clean)


if __name__ == "__main__":
    main()
