"""Pytest fixtures: a mock Fing agent wired into the server's shared client."""

from __future__ import annotations

import copy
from collections.abc import Callable

import httpx
import pytest

from config import FingConfig
from fing_client import FingClient
from tests.fixtures import AGENT_INFO_XML, DEVICES_PAYLOAD, PEOPLE_PAYLOAD

TEST_KEY = "test-key-123"


def make_config(**overrides) -> FingConfig:
    values = dict(
        fing_api_base_url="http://fing.test:49090",
        fing_api_key=TEST_KEY,
        fing_timeout=5.0,
        fing_retries=0,
        op_connect_host="",
        op_connect_token="",
    )
    values.update(overrides)
    return FingConfig(**values)


class MockFing:
    """Simulates the Fing Local API; tests mutate attributes to change behaviour."""

    def __init__(self) -> None:
        self.devices = copy.deepcopy(DEVICES_PAYLOAD)
        self.people = copy.deepcopy(PEOPLE_PAYLOAD)
        self.people_status = 200
        self.agent_xml: str | None = AGENT_INFO_XML
        self.override: Callable[[httpx.Request], httpx.Response] | None = None
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.override:
            return self.override(request)
        if request.url.port == 44444:
            if self.agent_xml is None:
                raise httpx.ConnectError("connection refused")
            return httpx.Response(200, text=self.agent_xml)
        if request.url.params.get("auth") != TEST_KEY:
            return httpx.Response(401, json={"error": "unauthorized"})
        if request.url.path == "/1/devices":
            return httpx.Response(200, json=self.devices)
        if request.url.path == "/1/people":
            if self.people_status != 200:
                return httpx.Response(self.people_status, text="Service Unavailable")
            return httpx.Response(200, json=self.people)
        return httpx.Response(404, text="Not found")


@pytest.fixture()
def fing(monkeypatch):
    """Install a FingClient backed by MockFing as the server's shared client."""
    import server

    mock = MockFing()
    client = FingClient(make_config(), transport=httpx.MockTransport(mock))
    monkeypatch.setattr(server, "_client", client)
    yield mock
