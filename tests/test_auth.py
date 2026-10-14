"""Tests for the fail-closed HTTP/SSE bearer-token auth layer."""

from __future__ import annotations

import httpx
import pytest
from starlette.middleware import Middleware

import server
from auth import BearerTokenMiddleware, extract_bearer_token, tokens_match

TOKEN = "s3cr3t-token"

# --------------------------------------------------------------- unit helpers


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Bearer abc", "abc"),
        ("bearer abc", "abc"),  # scheme is case-insensitive
        ("Bearer   abc  ", "abc"),
        ("Basic abc", None),  # wrong scheme
        ("Bearer ", None),  # empty token
        ("abc", None),  # no scheme
        ("", None),
        (None, None),
    ],
)
def test_extract_bearer_token(header, expected):
    assert extract_bearer_token(header) == expected


@pytest.mark.parametrize(
    ("presented", "expected", "result"),
    [
        ("abc", "abc", True),
        ("abc", "xyz", False),
        ("", "abc", False),
        (None, "abc", False),
        ("abc", "", False),  # empty expected never authenticates
    ],
)
def test_tokens_match(presented, expected, result):
    assert tokens_match(presented, expected) is result


def test_middleware_requires_token():
    with pytest.raises(ValueError, match="non-empty token"):
        BearerTokenMiddleware(lambda s, r, x: None, token="")


# ------------------------------------------------------------ ASGI behaviour


@pytest.fixture()
def http_client():
    app = server.mcp.http_app(middleware=[Middleware(BearerTokenMiddleware, token=TOKEN)])
    transport = httpx.ASGITransport(app=app)
    return app, transport


async def test_healthz_is_public(http_client):
    app, transport = http_client
    async with app.router.lifespan_context({}):
        async with httpx.AsyncClient(transport=transport, base_url="http://mcp") as c:
            resp = await c.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_mcp_rejected_without_token(http_client):
    app, transport = http_client
    async with app.router.lifespan_context({}):
        async with httpx.AsyncClient(transport=transport, base_url="http://mcp") as c:
            resp = await c.post("/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"].startswith("Bearer")
    assert resp.json()["error"] == "unauthorized"


async def test_mcp_rejected_with_wrong_token(http_client):
    app, transport = http_client
    async with app.router.lifespan_context({}):
        async with httpx.AsyncClient(transport=transport, base_url="http://mcp") as c:
            resp = await c.post(
                "/mcp/",
                json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
                headers={"Authorization": "Bearer wrong"},
            )
    assert resp.status_code == 401


async def test_mcp_accepts_valid_token(http_client):
    app, transport = http_client
    async with app.router.lifespan_context({}):
        async with httpx.AsyncClient(transport=transport, base_url="http://mcp") as c:
            resp = await c.post(
                "/mcp/",
                json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
                headers={
                    "Authorization": f"Bearer {TOKEN}",
                    "Accept": "application/json, text/event-stream",
                },
            )
    # A valid token passes the auth layer: the MCP app handles the request and
    # no longer returns 401.
    assert resp.status_code != 401


# ---------------------------------------------------- fail-closed startup wiring


def test_http_middleware_fails_closed_without_token(monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("MCP_AUTH_DISABLED", raising=False)
    with pytest.raises(SystemExit, match="without authentication"):
        server._http_middleware()


def test_http_middleware_builds_with_token(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", TOKEN)
    monkeypatch.delenv("MCP_AUTH_DISABLED", raising=False)
    middleware = server._http_middleware()
    assert len(middleware) == 1


def test_http_middleware_can_be_disabled(monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("MCP_AUTH_DISABLED", "1")
    assert server._http_middleware() == []
