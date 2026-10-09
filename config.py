"""Configuration loader for the Fing MCP server.

Resolves op:// secret references at runtime using the 1Password Connect REST
API, then exposes typed settings to the rest of the application.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import httpx

# Matches op://<vault>/<item>[/<field>]
_OP_REF_RE = re.compile(r"^op://(?P<vault>[^/]+)/(?P<item>[^/]+)(?:/(?P<field>[^/]+))?$")


def _odata_escape(value: str) -> str:
    """Escape a string value for use inside an OData eq filter.

    Doubles any single quotes to prevent filter injection.
    """
    return value.replace("'", "''").replace('"', '\\"')


def _resolve_op_ref(ref: str, connect_host: str, connect_token: str) -> str:
    """Resolve a single op:// reference to its plaintext value.

    Args:
        ref: An op:// secret reference such as ``op://vault/item/field``.
        connect_host: Base URL of the 1Password Connect server (no trailing slash).
        connect_token: Bearer token for the Connect server.

    Returns:
        The plaintext secret value.

    Raises:
        ValueError: If ``ref`` is not a valid op:// reference.
        httpx.HTTPStatusError: If the Connect server returns a non-2xx response.
    """
    match = _OP_REF_RE.match(ref)
    if match is None:
        raise ValueError(f"Invalid op:// reference: {ref!r}")

    vault_name = match.group("vault")
    item_name = match.group("item")
    field_name = match.group("field") or "password"

    headers = {"Authorization": f"Bearer {connect_token}"}

    with httpx.Client(base_url=connect_host, headers=headers, timeout=10.0) as client:
        # Resolve vault UUID by name
        vault_resp = client.get(
            "/v1/vaults", params={"filter": f'name eq "{_odata_escape(vault_name)}"'}
        )
        vault_resp.raise_for_status()
        vaults = vault_resp.json()
        if not vaults:
            raise ValueError(f"1Password vault not found: {vault_name!r}")
        vault_id = vaults[0]["id"]

        # Resolve item by title
        item_resp = client.get(
            f"/v1/vaults/{vault_id}/items",
            params={"filter": f'title eq "{_odata_escape(item_name)}"'},
        )
        item_resp.raise_for_status()
        items = item_resp.json()
        if not items:
            raise ValueError(f"1Password item not found: {item_name!r}")
        item_id = items[0]["id"]

        # Fetch full item to read field value
        detail_resp = client.get(f"/v1/vaults/{vault_id}/items/{item_id}")
        detail_resp.raise_for_status()
        detail = detail_resp.json()

    for f in detail.get("fields", []):
        if f.get("label") == field_name or f.get("id") == field_name:
            return f.get("value", "")

    raise ValueError(f"Field {field_name!r} not found in 1Password item {item_name!r}")


def _resolve_value(raw: str, connect_host: str, connect_token: str) -> str:
    """Return the resolved value of *raw*.

    If *raw* begins with ``op://`` it is resolved via 1Password Connect;
    otherwise it is returned as-is.

    Raises:
        ValueError: If *raw* is an ``op://`` reference but 1Password Connect
            is not configured.
    """
    if raw.startswith("op://"):
        if not connect_host or not connect_token:
            raise ValueError(
                "FING_API_KEY is an op:// reference but OP_CONNECT_HOST and OP_CONNECT_TOKEN "
                "are not both set. Either configure 1Password Connect or supply the key directly."
            )
        return _resolve_op_ref(raw, connect_host.rstrip("/"), connect_token)
    return raw


def _normalise_base_url(raw: str) -> str:
    """Strip whitespace, trailing slashes and an optional ``/1`` API-version suffix."""
    url = raw.strip().rstrip("/")
    if url.endswith("/1"):
        url = url[:-2]
    if "://" not in url:
        url = f"http://{url}"
    return url


def _env_number(name: str, default: str, cast: type[float] | type[int]) -> float | int:
    raw = os.environ.get(name, default).strip() or default
    try:
        value = cast(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a {cast.__name__}, got {raw!r}") from exc
    if value < 0:
        raise ValueError(f"{name} must not be negative, got {raw!r}")
    return value


DEFAULT_FING_API_BASE_URL = "http://localhost:49090"
DEFAULT_AGENT_INFO_PORT = 44444


@dataclass(frozen=True)
class FingConfig:
    """Runtime configuration for the Fing MCP server."""

    fing_api_base_url: str
    fing_api_key: str
    fing_timeout: float
    fing_retries: int
    op_connect_host: str
    op_connect_token: str
    fing_agent_info_port: int = DEFAULT_AGENT_INFO_PORT

    def __repr__(self) -> str:  # never leak secrets into logs/tracebacks
        return (
            f"FingConfig(fing_api_base_url={self.fing_api_base_url!r}, "
            f"fing_api_key={'***' if self.fing_api_key else ''!r}, "
            f"fing_timeout={self.fing_timeout}, fing_retries={self.fing_retries}, "
            f"op_connect_host={self.op_connect_host!r}, fing_agent_info_port={self.fing_agent_info_port})"
        )


def load_config() -> FingConfig:
    """Build a :class:`FingConfig` from environment variables.

    ``FING_API_KEY`` may be a literal value **or** an ``op://vault/item[/field]``
    reference, resolved at startup against the 1Password Connect server given
    by ``OP_CONNECT_HOST`` / ``OP_CONNECT_TOKEN``.

    Environment variables (all optional unless noted)
    -------------------------------------------------
    ``FING_API_KEY`` (required to call Fing)
        Local API key from Fing → Agent Settings → Local API.
    ``FING_API_BASE_URL``
        Host and port of the Fing agent, default ``http://localhost:49090``.
        A trailing ``/1`` is accepted and stripped.
    ``FING_TIMEOUT``
        HTTP timeout in seconds (default ``10``).
    ``FING_RETRIES``
        Connection retries on transient failures (default ``2``).
    ``FING_AGENT_INFO_PORT``
        UPnP agent-info port used by ``get_agent_info`` (default ``44444``).
    ``OP_CONNECT_HOST`` / ``OP_CONNECT_TOKEN``
        1Password Connect URL and bearer token. The token must be a literal
        value — it cannot itself be an ``op://`` reference.
    """
    op_connect_host = os.environ.get("OP_CONNECT_HOST", "").strip()
    op_connect_token = os.environ.get("OP_CONNECT_TOKEN", "").strip()

    fing_api_key_raw = os.environ.get("FING_API_KEY", "").strip()
    fing_api_key = _resolve_value(fing_api_key_raw, op_connect_host, op_connect_token)

    return FingConfig(
        fing_api_base_url=_normalise_base_url(
            os.environ.get("FING_API_BASE_URL", "").strip() or DEFAULT_FING_API_BASE_URL
        ),
        fing_api_key=fing_api_key,
        fing_timeout=float(_env_number("FING_TIMEOUT", "10", float)),
        fing_retries=int(_env_number("FING_RETRIES", "2", int)),
        op_connect_host=op_connect_host,
        op_connect_token=op_connect_token,
        fing_agent_info_port=int(
            _env_number("FING_AGENT_INFO_PORT", str(DEFAULT_AGENT_INFO_PORT), int)
        ),
    )
