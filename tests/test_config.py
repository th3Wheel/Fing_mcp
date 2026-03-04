"""Unit tests for config.py — config loader and op:// resolution."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from config import _resolve_op_ref, _resolve_value, load_config

# ---------------------------------------------------------------------------
# _resolve_value
# ---------------------------------------------------------------------------


def test_resolve_value_passthrough():
    """Non-op:// values are returned unchanged."""
    assert _resolve_value("my-secret", "", "") == "my-secret"


def test_resolve_value_empty_string():
    assert _resolve_value("", "", "") == ""


# ---------------------------------------------------------------------------
# _resolve_op_ref helpers
# ---------------------------------------------------------------------------


def _make_handler(
    vault_name: str,
    item_name: str,
    field_label: str,
    field_value: str,
    *,
    vault_id: str = "vault-uuid-1",
    item_id: str = "item-uuid-1",
    empty_vaults: bool = False,
    empty_items: bool = False,
    empty_fields: bool = False,
):
    """Return an httpx mock handler for a 1Password Connect server."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path == "/v1/vaults":
            if empty_vaults:
                return httpx.Response(200, json=[])
            return httpx.Response(200, json=[{"id": vault_id, "name": vault_name}])

        if path == f"/v1/vaults/{vault_id}/items":
            if empty_items:
                return httpx.Response(200, json=[])
            return httpx.Response(200, json=[{"id": item_id, "title": item_name}])

        if path == f"/v1/vaults/{vault_id}/items/{item_id}":
            fields = [] if empty_fields else [{"id": field_label, "label": field_label, "value": field_value}]
            return httpx.Response(200, json={"id": item_id, "title": item_name, "fields": fields})

        return httpx.Response(404, text="Not found")

    return handler


# ---------------------------------------------------------------------------
# _resolve_op_ref
# ---------------------------------------------------------------------------


def test_resolve_op_ref_success():
    """Happy-path resolution of an op:// reference."""
    transport = httpx.MockTransport(
        _make_handler("MyVault", "MyItem", "password", "s3cr3t")
    )
    _orig_client = httpx.Client

    def patched_client(**kwargs):
        kwargs["transport"] = transport
        return _orig_client(**kwargs)

    with patch("config.httpx.Client", side_effect=patched_client):
        result = _resolve_op_ref(
            "op://MyVault/MyItem/password",
            connect_host="http://connect:8080",
            connect_token="token",
        )
    assert result == "s3cr3t"


def test_resolve_op_ref_invalid_ref():
    with pytest.raises(ValueError, match="Invalid op://"):
        _resolve_op_ref("not-an-op-ref", "", "")


def test_resolve_op_ref_vault_not_found():
    transport = httpx.MockTransport(_make_handler("X", "X", "x", "x", empty_vaults=True))
    _orig_client = httpx.Client

    def patched_client(**kwargs):
        kwargs["transport"] = transport
        return _orig_client(**kwargs)

    with patch("config.httpx.Client", side_effect=patched_client):
        with pytest.raises(ValueError, match="vault not found"):
            _resolve_op_ref("op://NoVault/Item/field", "http://connect", "token")


def test_resolve_op_ref_item_not_found():
    transport = httpx.MockTransport(_make_handler("MyVault", "X", "x", "x", empty_items=True))
    _orig_client = httpx.Client

    def patched_client(**kwargs):
        kwargs["transport"] = transport
        return _orig_client(**kwargs)

    with patch("config.httpx.Client", side_effect=patched_client):
        with pytest.raises(ValueError, match="item not found"):
            _resolve_op_ref("op://MyVault/NoItem/field", "http://connect", "token")


def test_resolve_op_ref_field_not_found():
    transport = httpx.MockTransport(
        _make_handler("MyVault", "MyItem", "password", "x", empty_fields=True)
    )
    _orig_client = httpx.Client

    def patched_client(**kwargs):
        kwargs["transport"] = transport
        return _orig_client(**kwargs)

    with patch("config.httpx.Client", side_effect=patched_client):
        with pytest.raises(ValueError, match="Field"):
            _resolve_op_ref("op://MyVault/MyItem/missing", "http://connect", "token")


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


def test_load_config_defaults(monkeypatch):
    monkeypatch.delenv("FING_API_BASE_URL", raising=False)
    monkeypatch.delenv("FING_API_KEY", raising=False)
    monkeypatch.delenv("FING_TIMEOUT", raising=False)
    monkeypatch.delenv("FING_RETRIES", raising=False)
    monkeypatch.delenv("OP_CONNECT_HOST", raising=False)
    monkeypatch.delenv("OP_CONNECT_TOKEN", raising=False)

    cfg = load_config()

    assert cfg.fing_api_base_url == "http://localhost:48080"
    assert cfg.fing_api_key == ""
    assert cfg.fing_timeout == 10.0
    assert cfg.fing_retries == 3
    assert cfg.op_connect_host == ""
    assert cfg.op_connect_token == ""


def test_load_config_custom_values(monkeypatch):
    monkeypatch.setenv("FING_API_BASE_URL", "http://192.168.1.1:48080")
    monkeypatch.setenv("FING_API_KEY", "my-key")
    monkeypatch.setenv("FING_TIMEOUT", "5")
    monkeypatch.setenv("FING_RETRIES", "2")
    monkeypatch.setenv("OP_CONNECT_HOST", "http://connect:8080")
    monkeypatch.setenv("OP_CONNECT_TOKEN", "tok")

    cfg = load_config()

    assert cfg.fing_api_base_url == "http://192.168.1.1:48080"
    assert cfg.fing_api_key == "my-key"
    assert cfg.fing_timeout == 5.0
    assert cfg.fing_retries == 2

