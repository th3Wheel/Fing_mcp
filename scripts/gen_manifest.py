"""Regenerate mcp.json from the tools registered in server.py.

Usage:  python scripts/gen_manifest.py          # write mcp.json
        python scripts/gen_manifest.py --check  # exit 1 if mcp.json is stale
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import server  # noqa: E402

MANIFEST = ROOT / "mcp.json"


async def build_manifest() -> dict:
    tools = sorted(await server.mcp.list_tools(), key=lambda t: t.name)
    return {
        "name": server.mcp.name,
        "version": server.__version__,
        "description": "Read-only MCP server for the Fing Local API: device inventory, presence and network summary.",
        "tools": [
            {
                "name": t.name,
                "description": (t.description or "").strip(),
                "annotations": t.annotations.model_dump(by_alias=True, exclude_none=True)
                if t.annotations
                else {},
                "inputSchema": t.parameters,
            }
            for t in tools
        ],
    }


def render(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, sort_keys=False) + "\n"


def main() -> int:
    text = render(asyncio.run(build_manifest()))
    if "--check" in sys.argv:
        if not MANIFEST.exists() or MANIFEST.read_text(encoding="utf-8") != text:
            print("mcp.json is out of date — run: python scripts/gen_manifest.py", file=sys.stderr)
            return 1
        print("mcp.json is up to date")
        return 0
    MANIFEST.write_text(text, encoding="utf-8")
    print(f"wrote {MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
