"""Integration tests for the list_devices and list_people MCP tools."""

from __future__ import annotations

import httpx
import pytest

from tests.fixtures import DEVICES_PAYLOAD, PEOPLE_PAYLOAD


def _make_fing_transport(devices_payload, people_payload) -> httpx.MockTransport:
    """Return a MockTransport that simulates the Fing Local API."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/devices":
            return httpx.Response(200, json=devices_payload)
        if path == "/people":
            return httpx.Response(200, json=people_payload)
        return httpx.Response(404, text="Not found")

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def reset_server_caches():
    """Clear the lru_cache on server functions between tests."""
    import server

    server._get_config.cache_clear()
    server._get_client.cache_clear()
    yield
    server._get_config.cache_clear()
    server._get_client.cache_clear()


@pytest.fixture()
def fing_env(monkeypatch):
    """Provide minimal environment for the server config."""
    monkeypatch.setenv("FING_API_BASE_URL", "http://fing-agent:48080")
    monkeypatch.setenv("FING_API_KEY", "test-key")
    monkeypatch.setenv("FING_TIMEOUT", "5")
    monkeypatch.setenv("FING_RETRIES", "0")
    monkeypatch.delenv("OP_CONNECT_HOST", raising=False)
    monkeypatch.delenv("OP_CONNECT_TOKEN", raising=False)


def _patch_client(monkeypatch, transport: httpx.MockTransport):
    """Patch server._get_client to inject a mock transport."""
    import server

    def patched_get_client():
        cfg = server._get_config()
        return httpx.Client(
            base_url=cfg.fing_api_base_url,
            headers={"x-api-key": cfg.fing_api_key},
            timeout=cfg.fing_timeout,
            transport=transport,
        )

    monkeypatch.setattr(server, "_get_client", patched_get_client)


# ---------------------------------------------------------------------------
# list_devices
# ---------------------------------------------------------------------------


def test_list_devices_success(fing_env, monkeypatch):
    transport = _make_fing_transport(DEVICES_PAYLOAD, PEOPLE_PAYLOAD)
    _patch_client(monkeypatch, transport)

    import server

    result = server.list_devices()

    assert "devices" in result
    assert len(result["devices"]) == 1
    device = result["devices"][0]
    assert device["mac"] == "AA:BB:CC:DD:EE:FF"
    assert device["ip"] == "192.168.1.42"
    assert device["name"] == "my-laptop"


def test_list_devices_http_error(fing_env, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(handler)
    _patch_client(monkeypatch, transport)

    from fastmcp.exceptions import ToolError

    import server

    with pytest.raises(ToolError, match="HTTP 500"):
        server.list_devices()


def test_list_devices_network_error(fing_env, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    transport = httpx.MockTransport(handler)
    _patch_client(monkeypatch, transport)

    from fastmcp.exceptions import ToolError

    import server

    with pytest.raises(ToolError, match="Network error"):
        server.list_devices()


def test_list_devices_empty(fing_env, monkeypatch):
    transport = _make_fing_transport({"devices": []}, PEOPLE_PAYLOAD)
    _patch_client(monkeypatch, transport)

    import server

    result = server.list_devices()
    assert result == {"devices": []}


# ---------------------------------------------------------------------------
# list_people
# ---------------------------------------------------------------------------


def test_list_people_success(fing_env, monkeypatch):
    transport = _make_fing_transport(DEVICES_PAYLOAD, PEOPLE_PAYLOAD)
    _patch_client(monkeypatch, transport)

    import server

    result = server.list_people()

    assert "people" in result
    assert "presence" in result
    assert len(result["people"]) == 1
    person = result["people"][0]
    assert person["id"] == "person-1"
    assert person["name"] == "Alice"
    assert person["present"] is True


def test_list_people_http_error(fing_env, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Unauthorized")

    transport = httpx.MockTransport(handler)
    _patch_client(monkeypatch, transport)

    from fastmcp.exceptions import ToolError

    import server

    with pytest.raises(ToolError, match="HTTP 401"):
        server.list_people()


def test_list_people_empty(fing_env, monkeypatch):
    transport = _make_fing_transport(DEVICES_PAYLOAD, {"people": [], "presence": []})
    _patch_client(monkeypatch, transport)

    import server

    result = server.list_people()
    assert result == {"people": [], "presence": []}
