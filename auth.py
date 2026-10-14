"""Fail-closed bearer-token authentication for the HTTP/SSE transport.

The MCP endpoint is unauthenticated by default in FastMCP, so exposing it on
anything other than loopback would let any client on the network read the home
network inventory. This module adds a lightweight bearer-token check that
**fails closed**: when enabled it rejects every request that does not present
the configured token, and the server refuses to start the HTTP/SSE transport
unless a token is configured (or auth is explicitly disabled).

The ``stdio`` transport is intentionally not protected here — it is a local
child process spoken to over pipes, with no network surface to authenticate.
"""

from __future__ import annotations

import hmac

from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# Paths that must stay reachable without a token (container liveness probes).
_PUBLIC_PATHS = frozenset({"/healthz"})


def extract_bearer_token(authorization: str | None) -> str | None:
    """Return the token from an ``Authorization: Bearer <token>`` header.

    Returns ``None`` when the header is missing or not a well-formed bearer
    header. The ``Bearer`` scheme is matched case-insensitively, per RFC 6750.
    """
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def tokens_match(presented: str | None, expected: str) -> bool:
    """Constant-time comparison of a presented token against the expected one.

    Always fails when either value is empty, so a misconfigured empty token can
    never authenticate a request.
    """
    if not presented or not expected:
        return False
    return hmac.compare_digest(presented, expected)


class BearerTokenMiddleware:
    """ASGI middleware enforcing a static bearer token on HTTP/SSE requests.

    Non-HTTP scopes (e.g. ``lifespan``) and public paths pass straight through;
    every other request must present the matching bearer token or receive a
    ``401`` with a ``WWW-Authenticate`` challenge.
    """

    def __init__(self, app: ASGIApp, *, token: str) -> None:
        if not token:
            # Guard against wiring the middleware in without a real secret.
            raise ValueError("BearerTokenMiddleware requires a non-empty token")
        self._app = app
        self._token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        if scope.get("path") in _PUBLIC_PATHS:
            await self._app(scope, receive, send)
            return

        conn = HTTPConnection(scope)
        presented = extract_bearer_token(conn.headers.get("authorization"))
        if not tokens_match(presented, self._token):
            response = JSONResponse(
                {"error": "unauthorized", "detail": "missing or invalid bearer token"},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="fing-mcp"'},
            )
            await response(scope, receive, send)
            return

        await self._app(scope, receive, send)
