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
        vault_resp = client.get("/v1/vaults", params={"filter": f"name eq \"{_odata_escape(vault_name)}\""})
        vault_resp.raise_for_status()
        vaults = vault_resp.json()
        if not vaults:
            raise ValueError(f"1Password vault not found: {vault_name!r}")
        vault_id = vaults[0]["id"]

        # Resolve item by title
        item_resp = client.get(
            f"/v1/vaults/{vault_id}/items",
            params={"filter": f"title eq \"{_odata_escape(item_name)}\""},
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
    """
    if raw.startswith("op://"):
        return _resolve_op_ref(raw, connect_host, connect_token)
    return raw


@dataclass
class FingConfig:
    """Runtime configuration for the Fing MCP server."""

    fing_api_base_url: str
    fing_api_key: str
    fing_timeout: float
    fing_retries: int
    op_connect_host: str
    op_connect_token: str


def load_config() -> FingConfig:
    """Build a :class:`FingConfig` from environment variables.

    Secret values may be provided as literal strings **or** as ``op://``
    references which will be resolved against the 1Password Connect server
    defined by ``OP_CONNECT_HOST`` / ``OP_CONNECT_TOKEN``.

    Required environment variables
    --------------------------------
    ``FING_API_BASE_URL``
        Base URL of the Fing Local API, e.g. ``http://192.168.1.1:48080``.
    ``FING_API_KEY``
        API key for the ``x-api-key`` header (may be an ``op://`` ref).
    ``FING_TIMEOUT``
        HTTP request timeout in seconds (default: ``10``).
    ``FING_RETRIES``
        Number of HTTP retries on transient failure (default: ``3``).
    ``OP_CONNECT_HOST``
        Base URL of the 1Password Connect REST API server.
    ``OP_CONNECT_TOKEN``
        Bearer token for the 1Password Connect server (may be an ``op://`` ref).
    """
    op_connect_host = os.environ.get("OP_CONNECT_HOST", "")
    op_connect_token = os.environ.get("OP_CONNECT_TOKEN", "")

    fing_api_key_raw = os.environ.get("FING_API_KEY", "")
    fing_api_key = _resolve_value(fing_api_key_raw, op_connect_host, op_connect_token)

    return FingConfig(
        fing_api_base_url=os.environ.get("FING_API_BASE_URL", "http://localhost:48080"),
        fing_api_key=fing_api_key,
        fing_timeout=float(os.environ.get("FING_TIMEOUT", "10")),
        fing_retries=int(os.environ.get("FING_RETRIES", "3")),
        op_connect_host=op_connect_host,
        op_connect_token=op_connect_token,
    )
