"""Contract tests — the committed mcp.json manifest must match the live server."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.gen_manifest import build_manifest, render

MANIFEST_PATH = Path(__file__).parent.parent / "mcp.json"
EXPECTED_TOOLS = {
    "list_devices",
    "get_device",
    "get_network_summary",
    "list_people",
    "get_agent_status",
}


async def test_manifest_is_up_to_date():
    expected = render(await build_manifest())
    assert MANIFEST_PATH.read_text(encoding="utf-8") == expected, (
        "mcp.json is stale — run `python scripts/gen_manifest.py`"
    )


def test_manifest_declares_expected_tools():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert {t["name"] for t in manifest["tools"]} == EXPECTED_TOOLS
    for tool in manifest["tools"]:
        assert tool["description"], f"{tool['name']} has no description"
        assert tool["annotations"]["readOnlyHint"] is True
        assert tool["inputSchema"]["type"] == "object"
