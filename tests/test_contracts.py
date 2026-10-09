"""Contract tests — the committed mcp.json manifest must match the live server."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

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


def test_manifest_declares_output_schemas():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for tool in manifest["tools"]:
        schema = tool["outputSchema"]
        assert schema and schema["type"] == "object", f"{tool['name']} has no outputSchema"


async def _outputs():
    """Real output of every tool against the mock Fing agent."""
    import server

    return {
        "list_devices": await server.list_devices(),
        "get_device": await server.get_device("192.168.0.20"),
        "get_network_summary": await server.get_network_summary(),
        "list_people": await server.list_people(include_pictures=True),
        "get_agent_status": await server.get_agent_status(),
    }


async def test_tool_output_matches_published_schema(fing):
    tools = {t.name: t for t in await __import__("server").mcp.list_tools()}
    outputs = await _outputs()
    assert set(outputs) == EXPECTED_TOOLS
    for name, output in outputs.items():
        jsonschema.validate(output, tools[name].output_schema)


async def test_agent_status_failure_output_matches_schema(fing):
    import server

    fing.people_status = 503
    fing.agent_xml = None
    tool = await server.mcp.get_tool("get_agent_status")
    jsonschema.validate(await server.get_agent_status(), tool.output_schema)
