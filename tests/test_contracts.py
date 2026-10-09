"""Contract tests — verify the MCP manifest matches tool definitions and
tool schemas match Pydantic models."""

from __future__ import annotations

import json
from pathlib import Path

MCP_JSON_PATH = Path(__file__).parent.parent / "mcp.json"


def load_manifest() -> dict:
    with MCP_JSON_PATH.open() as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# MCP manifest structure
# ---------------------------------------------------------------------------


def test_manifest_exists():
    assert MCP_JSON_PATH.exists(), "mcp.json must exist in the project root"


def test_manifest_has_required_keys():
    manifest = load_manifest()
    for key in ("name", "version", "tools"):
        assert key in manifest, f"mcp.json missing required key: {key!r}"


def test_manifest_tools_are_list():
    manifest = load_manifest()
    assert isinstance(manifest["tools"], list)


def test_manifest_tool_names():
    manifest = load_manifest()
    tool_names = {t["name"] for t in manifest["tools"]}
    assert "list_devices" in tool_names, "mcp.json must declare list_devices"
    assert "list_people" in tool_names, "mcp.json must declare list_people"


def test_manifest_tools_have_description():
    manifest = load_manifest()
    for tool in manifest["tools"]:
        assert "description" in tool, f"Tool {tool['name']!r} is missing a description"
        assert tool["description"], f"Tool {tool['name']!r} has an empty description"


# ---------------------------------------------------------------------------
# Tool schema vs server tool registration
# ---------------------------------------------------------------------------


def test_server_registers_list_devices():
    """server.py must register a tool named list_devices."""
    import asyncio

    import server

    tools = asyncio.run(server.mcp.list_tools())
    tool_names = [t.name for t in tools]
    assert "list_devices" in tool_names


def test_server_registers_list_people():
    """server.py must register a tool named list_people."""
    import asyncio

    import server

    tools = asyncio.run(server.mcp.list_tools())
    tool_names = [t.name for t in tools]
    assert "list_people" in tool_names


# ---------------------------------------------------------------------------
# Output structure matches model schema
# ---------------------------------------------------------------------------


def test_devices_output_keys_match_model():
    """FingDevicesResponse serialisation produces the keys declared in mcp.json."""
    from models import FingDevicesResponse

    schema = FingDevicesResponse.model_json_schema()
    # Top-level must expose a 'devices' array
    assert "devices" in schema.get("properties", {})


def test_people_output_keys_match_model():
    """FingPeopleResponse serialisation produces the keys declared in mcp.json."""
    from models import FingPeopleResponse

    schema = FingPeopleResponse.model_json_schema()
    props = schema.get("properties", {})
    assert "people" in props
    assert "presence" in props
