"""FastMCP server wrapping the Fing Local API.

Tools
-----
list_devices  — return all devices from ``GET /devices``.
list_people   — return all people from ``GET /people``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from config import FingConfig, load_config
from models import FingDevicesResponse, FingPeopleResponse

mcp = FastMCP(
    name="fing-mcp",
    instructions=(
        "Provides typed, deterministic access to the Fing Local API for device inventory, "
        "people presence, and network monitoring."
    ),
    version="1.0.0",
)


@lru_cache(maxsize=1)
def _get_config() -> FingConfig:
    """Return the singleton runtime configuration."""
    return load_config()


def _build_client(cfg: FingConfig) -> httpx.Client:
    """Build a synchronous HTTPX client configured for the Fing API."""
    transport = httpx.HTTPTransport(retries=cfg.fing_retries)
    return httpx.Client(
        base_url=cfg.fing_api_base_url,
        headers={"x-api-key": cfg.fing_api_key},
        timeout=cfg.fing_timeout,
        transport=transport,
    )


def _get(path: str) -> Any:
    """Perform a GET request and return the parsed JSON payload.

    Raises:
        ToolError: On HTTP errors or unexpected response format.
    """
    cfg = _get_config()
    try:
        with _build_client(cfg) as client:
            response = client.get(path)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise ToolError(
            f"Fing API returned HTTP {exc.response.status_code} for {path}: "
            f"{exc.response.text[:200]}"
        ) from exc
    except httpx.RequestError as exc:
        raise ToolError(f"Network error contacting Fing API at {path}: {exc}") from exc


@mcp.tool(
    name="list_devices",
    description="Return the list of devices discovered by the Fing agent.",
)
def list_devices() -> dict[str, Any]:
    """Fetch and return the Fing /devices endpoint.

    Returns a JSON-serialisable dict whose keys are sorted for deterministic
    output.

    Returns:
        Parsed ``FingDevicesResponse`` as a sorted-key dictionary.

    Raises:
        ToolError: On HTTP or validation errors.
    """
    raw = _get("/devices")
    try:
        parsed = FingDevicesResponse.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"Unexpected /devices response shape: {exc}") from exc
    return json.loads(parsed.model_dump_json(by_alias=True))


@mcp.tool(
    name="list_people",
    description="Return the list of people and their presence tracked by the Fing agent.",
)
def list_people() -> dict[str, Any]:
    """Fetch and return the Fing /people endpoint.

    Returns a JSON-serialisable dict whose keys are sorted for deterministic
    output.

    Returns:
        Parsed ``FingPeopleResponse`` as a sorted-key dictionary.

    Raises:
        ToolError: On HTTP or validation errors.
    """
    raw = _get("/people")
    try:
        parsed = FingPeopleResponse.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"Unexpected /people response shape: {exc}") from exc
    return json.loads(parsed.model_dump_json(by_alias=True))


if __name__ == "__main__":
    mcp.run()
