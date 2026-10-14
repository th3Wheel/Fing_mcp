"""End-to-end tests of the MCP tools against a mock Fing agent."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

import server
from tests.conftest import TEST_KEY

# ------------------------------------------------------------------ list_devices


async def test_list_devices_returns_all_sorted_by_ip(fing):
    result = await server.list_devices()
    assert result["networkId"] == "wifi-12345812839223"
    assert result["total"] == result["count"] == 3
    assert [d["mac"] for d in result["devices"]] == [
        "AA:BB:CC:DD:EE:01",  # 192.168.0.3
        "00:11:22:33:44:55",  # 192.168.0.20 (numeric, not lexical, order)
        "AA:BB:CC:DD:EE:02",  # no IP last
    ]
    chromecast = result["devices"][1]
    assert chromecast["ip"] == ["192.168.0.20"]
    assert chromecast["contactId"] == "67363e09-5ad6-40d0-883f-3e17254eec7a"
    assert chromecast["first_seen"] == "2020-04-24T12:54:21.634Z"
    assert "model" not in result["devices"][2]  # None fields are omitted


async def test_list_devices_sends_auth_as_query_param(fing):
    await server.list_devices()
    req = fing.requests[-1]
    assert str(req.url).startswith("http://fing.test:49090/1/devices")
    assert req.url.params["auth"] == TEST_KEY
    assert "x-api-key" not in req.headers


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"state": "DOWN"}, ["AA:BB:CC:DD:EE:01"]),
        ({"search": "chromecast"}, ["00:11:22:33:44:55"]),
        ({"search": "aabbccddee02"}, ["AA:BB:CC:DD:EE:02"]),
        ({"search": "192.168.0.3"}, ["AA:BB:CC:DD:EE:01"]),
        ({"device_type": "light"}, ["AA:BB:CC:DD:EE:01"]),
        ({"state": "UP", "search": "garage"}, []),
    ],
)
async def test_list_devices_filters(fing, kwargs, expected):
    result = await server.list_devices(**kwargs)
    assert [d["mac"] for d in result["devices"]] == expected
    assert result["total"] == 3


async def test_list_devices_time_filters(fing):
    recent = (datetime.now(UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    fing.devices["devices"][2]["first_seen"] = recent
    fing.devices["devices"][2]["last_changed"] = recent

    new = await server.list_devices(new_within_hours=24)
    changed = await server.list_devices(changed_within_hours=24)
    assert [d["mac"] for d in new["devices"]] == ["AA:BB:CC:DD:EE:02"]
    assert [d["mac"] for d in changed["devices"]] == ["AA:BB:CC:DD:EE:02"]


async def test_list_devices_empty(fing):
    fing.devices = {"networkId": "n", "devices": []}
    assert await server.list_devices() == {"networkId": "n", "total": 0, "count": 0, "devices": []}


@pytest.mark.parametrize(
    ("status", "needle"),
    [(401, "API key was rejected"), (503, "unavailable"), (500, "HTTP 500")],
)
async def test_list_devices_http_errors(fing, status, needle):
    fing.override = lambda r: httpx.Response(status, text=f"err {r.url.params.get('auth')}")
    with pytest.raises(ToolError, match=needle) as exc:
        await server.list_devices()
    assert TEST_KEY not in str(exc.value)  # key echoed by the server is redacted


async def test_list_devices_network_error(fing):
    def boom(request):
        raise httpx.ConnectError("Connection refused")

    fing.override = boom
    with pytest.raises(ToolError, match="Could not reach the Fing agent"):
        await server.list_devices()


async def test_list_devices_non_json(fing):
    fing.override = lambda r: httpx.Response(200, text="<html>login</html>")
    with pytest.raises(ToolError, match="non-JSON"):
        await server.list_devices()


async def test_list_devices_bad_shape(fing):
    fing.override = lambda r: httpx.Response(200, json={"devices": [{"ip": ["1.2.3.4"]}]})
    with pytest.raises(ToolError, match="Unexpected /devices response shape"):
        await server.list_devices()


async def test_missing_api_key(monkeypatch):
    monkeypatch.setattr(server, "_client", None)
    monkeypatch.delenv("FING_API_KEY", raising=False)
    try:
        with pytest.raises(ToolError, match="FING_API_KEY is not set"):
            await server.list_devices()
    finally:
        await server._close_client()


async def test_bad_config_is_tool_error(monkeypatch):
    monkeypatch.setattr(server, "_client", None)
    monkeypatch.setenv("FING_API_KEY", "op://Vault/Item")
    monkeypatch.delenv("OP_CONNECT_HOST", raising=False)
    with pytest.raises(ToolError, match="configuration error.*OP_CONNECT_HOST"):
        await server.list_devices()


# -------------------------------------------------------------------- get_device


@pytest.mark.parametrize(
    "identifier",
    [
        "00:11:22:33:44:55",
        "00-11-22-33-44-55",
        "001122334455",
        "192.168.0.20",
        "bedroom chromecast",
    ],
)
async def test_get_device_exact(fing, identifier):
    result = await server.get_device(identifier)
    assert result["match"] == "exact"
    assert result["count"] == 1
    assert result["devices"][0]["mac"] == "00:11:22:33:44:55"
    assert result["devices"][0]["ownerName"] == "Elenore"


async def test_get_device_partial(fing):
    result = await server.get_device("garage")
    assert result["match"] == "partial"
    assert result["devices"][0]["name"] == "Garage WLED"


async def test_get_device_owner_lookup_is_best_effort(fing):
    fing.people_status = 503  # Fing Agent / Fingbox: no /people
    result = await server.get_device("192.168.0.20")
    assert "ownerName" not in result["devices"][0]


async def test_get_device_not_found(fing):
    with pytest.raises(ToolError, match="No device matches"):
        await server.get_device("toaster")


# ----------------------------------------------------------- get_network_summary


async def test_network_summary(fing):
    s = await server.get_network_summary()
    assert (s["total"], s["online"], s["offline"]) == (3, 2, 1)
    assert s["byType"] == {"LIGHT": 1, "STREAMING_DONGLE": 1, "UNKNOWN": 1}
    assert s["unidentifiedCount"] == 1
    assert s["unidentified"][0]["mac"] == "AA:BB:CC:DD:EE:02"
    assert [d["mac"] for d in s["recentlyChanged"]] == ["AA:BB:CC:DD:EE:01", "00:11:22:33:44:55"]
    assert [d["mac"] for d in s["newest"]] == ["AA:BB:CC:DD:EE:01", "00:11:22:33:44:55"]


# ------------------------------------------------------------------- list_people


async def test_list_people(fing):
    result = await server.list_people()
    assert result["count"] == 2
    assert [p["contactInfo"]["displayName"] for p in result["people"]] == ["Bob", "Elenore"]
    elenore = result["people"][1]
    assert elenore["currentState"] == "ONLINE"
    assert "pictureImageData" not in elenore["contactInfo"]
    assert "currentState" not in result["people"][0]  # no presence device assigned


async def test_list_people_filters_and_pictures(fing):
    result = await server.list_people(state="ONLINE", include_pictures=True)
    assert result["count"] == 1
    assert result["people"][0]["contactInfo"]["pictureImageData"] == "iVBORw0KGgo="


async def test_list_people_unsupported_agent(fing):
    fing.people_status = 503
    with pytest.raises(ToolError, match="requires Fing Desktop"):
        await server.list_people()


# -------------------------------------------------------------- get_agent_status


async def test_agent_status_all_ok(fing):
    s = await server.get_agent_status()
    assert s["apiBaseUrl"] == "http://fing.test:49090/1"
    assert s["devicesEndpoint"] == {
        "ok": True,
        "networkId": "wifi-12345812839223",
        "deviceCount": 3,
    }
    assert s["peopleEndpoint"] == {"ok": True, "peopleCount": 2}
    assert s["agentInfo"]["ok"] is True
    assert s["agentInfo"]["agent_id"] == "0A1B2C3D4E5F"
    assert s["agentInfo"]["agent_state"] == "active"
    assert fing.requests[-1].url.port == 44444


async def test_agent_status_never_raises(fing):
    fing.people_status = 503
    fing.agent_xml = None
    s = await server.get_agent_status()
    assert s["devicesEndpoint"]["ok"] is True
    assert s["peopleEndpoint"]["ok"] is False
    assert s["agentInfo"]["ok"] is False
    assert "Fing Desktop" in s["agentInfo"]["error"]


# ------------------------------------------------------- over the MCP protocol


async def test_tools_callable_over_mcp_protocol(fing):
    async with Client(server.mcp) as client:
        result = await client.call_tool("list_devices", {"state": "UP"})
        assert result.structured_content["count"] == 2
        with pytest.raises(ToolError, match="No device matches"):
            await client.call_tool("get_device", {"identifier": "nope"})


async def test_healthz_route():
    transport = httpx.ASGITransport(app=server.mcp.http_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://mcp") as http:
        resp = await http.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_agent_status_reports_config_errors(monkeypatch):
    monkeypatch.setattr(server, "_client", None)
    monkeypatch.setenv("FING_TIMEOUT", "fast")
    s = await server.get_agent_status()
    assert s["config"]["ok"] is False
    assert "FING_TIMEOUT" in s["config"]["error"]
    assert s["devicesEndpoint"]["ok"] is False
    assert "apiBaseUrl" not in s
