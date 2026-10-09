"""Unit tests for fing_client.py."""

from __future__ import annotations

import pytest

from fing_client import FingAPIError, FingClient, parse_agent_info
from tests.conftest import make_config
from tests.fixtures import AGENT_INFO_XML


@pytest.mark.parametrize(
    ("base", "expected"),
    [
        ("http://192.168.1.10:49090", "http://192.168.1.10:44444/"),
        ("https://fing.lan", "https://fing.lan:44444/"),
        ("http://[fe80::1]:49090", "http://[fe80::1]:44444/"),
    ],
)
async def test_agent_info_url(base, expected):
    client = FingClient(make_config(fing_api_base_url=base))
    try:
        assert client.agent_info_url == expected
        assert client.api_root == f"{base}/1"
    finally:
        await client.aclose()


def test_parse_agent_info():
    info = parse_agent_info(AGENT_INFO_XML)
    assert info == {
        "url_base": "http://192.168.0.2:44444",
        "friendly_name": "Fing Agent (proxmox)",
        "model_name": "Fing Agent",
        "manufacturer": "Fing",
        "device_type": "device:fingagent:1",
        "agent_id": "0A1B2C3D4E5F",
        "agent_state": "active",
    }


def test_parse_agent_info_without_device():
    info = parse_agent_info('<root xmlns="urn:schemas-upnp-org:device-1-0"/>')
    assert info["friendly_name"] is None


def test_parse_agent_info_invalid():
    with pytest.raises(FingAPIError, match="UPnP"):
        parse_agent_info("not xml")


def test_config_repr_hides_key():
    assert "test-key-123" not in repr(make_config())
