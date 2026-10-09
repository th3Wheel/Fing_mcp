"""FastMCP server wrapping the Fing Local API.

Tools
-----
list_devices         — devices from ``GET /1/devices`` with optional filters.
get_device           — look up one device by MAC, IP or name.
get_network_summary  — counts by state / type / make, newest and recently changed devices.
list_people          — contacts and presence from ``GET /1/people`` (Fing Desktop only).
get_agent_status     — connectivity self-test plus UPnP agent identity.

Run with ``python server.py`` (stdio, for VS Code / Claude Desktop) or set
``MCP_TRANSPORT=http`` to serve streamable HTTP on ``MCP_HOST:MCP_PORT``.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import sys
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from config import load_config
from fing_client import FingAPIError, FingClient
from models import (
    AgentStatus,
    Device,
    DeviceListResult,
    DeviceLookupResult,
    NetworkSummary,
    PeopleListResult,
    output_schema,
)

__version__ = "1.1.0"

log = logging.getLogger("fing-mcp")

_client: FingClient | None = None


def _get_client() -> FingClient:
    """Return the shared Fing client, building it from the environment on first use."""
    global _client
    if _client is None:
        try:
            cfg = load_config()
        except Exception as exc:  # config/1Password errors become actionable tool errors
            raise ToolError(f"Fing MCP configuration error: {exc}") from exc
        _client = FingClient(cfg)
    return _client


async def _close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


@asynccontextmanager
async def _lifespan(_server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    try:
        yield {}
    finally:
        await _close_client()


mcp = FastMCP(
    name="fing-mcp",
    instructions=(
        "Read-only access to the Fing Local API on the user's home network. "
        "Use list_devices / get_device for inventory and online state, get_network_summary for an "
        "overview, list_people for presence (Fing Desktop only), and get_agent_status to diagnose "
        "connectivity. Device state is 'UP' (online) or 'DOWN' (offline); timestamps are ISO-8601 UTC."
    ),
    version=__version__,
    lifespan=_lifespan,
)

_READ_ONLY = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False}


# --------------------------------------------------------------------- helpers


async def _call(coro_factory):
    """Run a Fing client call, converting API errors into MCP ToolErrors."""
    client = _get_client()
    try:
        return await coro_factory(client)
    except FingAPIError as exc:
        raise ToolError(str(exc)) from exc


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _ip_sort_key(device: Device) -> tuple:
    """Sort IPv4 numerically, then IPv6, then devices without an IP; tie-break on MAC."""
    for raw in device.ip:
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            continue
        return (ip.version, int(ip), device.mac)
    return (99, 0, device.mac)


_MAC_STRIP = re.compile(r"[^0-9a-fA-F]")


def _norm_mac(value: str) -> str:
    return _MAC_STRIP.sub("", value).upper()


def _dump_device(device: Device) -> dict[str, Any]:
    return device.model_dump(by_alias=True, exclude_none=True)


def _sorted_devices(devices: list[Device]) -> list[Device]:
    return sorted(devices, key=_ip_sort_key)


# ----------------------------------------------------------------------- tools


@mcp.tool(
    name="list_devices", annotations=_READ_ONLY, output_schema=output_schema(DeviceListResult)
)
async def list_devices(
    state: Annotated[
        Literal["UP", "DOWN"] | None,
        Field(description="Only devices that are online (UP) or offline (DOWN)"),
    ] = None,
    search: Annotated[
        str | None,
        Field(
            description="Case-insensitive substring matched against name, make, model, type, IP and MAC"
        ),
    ] = None,
    device_type: Annotated[
        str | None, Field(description="Exact Fing device type, e.g. STREAMING_DONGLE, PHONE, LIGHT")
    ] = None,
    changed_within_hours: Annotated[
        float | None,
        Field(gt=0, description="Only devices whose state changed in the last N hours"),
    ] = None,
    new_within_hours: Annotated[
        float | None, Field(gt=0, description="Only devices first seen in the last N hours")
    ] = None,
) -> dict[str, Any]:
    """List devices discovered by the Fing agent, sorted by IP address.

    Returns the network ID, the total device count, how many matched the
    filters, and the matching devices with their MAC, IPs, state, name, type,
    make, model, owner contactId and first_seen / last_changed timestamps.
    """
    resp = await _call(lambda c: c.get_devices())
    now = datetime.now(UTC)
    devices = resp.devices

    if state:
        devices = [d for d in devices if d.state == state]
    if device_type:
        devices = [d for d in devices if (d.type or "").upper() == device_type.upper()]
    if search:
        needle = search.lower()
        mac_needle = _norm_mac(search)

        def matches(d: Device) -> bool:
            hay = " ".join(filter(None, [d.name, d.make, d.model, d.type, d.mac, *d.ip])).lower()
            return needle in hay or (len(mac_needle) >= 4 and mac_needle in _norm_mac(d.mac))

        devices = [d for d in devices if matches(d)]
    if changed_within_hours:
        cutoff = now - timedelta(hours=changed_within_hours)
        devices = [d for d in devices if (t := _parse_time(d.last_changed)) and t >= cutoff]
    if new_within_hours:
        cutoff = now - timedelta(hours=new_within_hours)
        devices = [d for d in devices if (t := _parse_time(d.first_seen)) and t >= cutoff]

    return {
        "networkId": resp.network_id,
        "total": len(resp.devices),
        "count": len(devices),
        "devices": [_dump_device(d) for d in _sorted_devices(devices)],
    }


@mcp.tool(
    name="get_device", annotations=_READ_ONLY, output_schema=output_schema(DeviceLookupResult)
)
async def get_device(
    identifier: Annotated[
        str,
        Field(
            min_length=1,
            description="MAC address (any separator), IP address, or device name (exact or partial)",
        ),
    ],
) -> dict[str, Any]:
    """Look up a single device by MAC, IP or name.

    Exact MAC / IP / name matches win; otherwise partial name matches are
    returned. If the device has an owner and the agent is Fing Desktop, the
    owner's display name is included as ``ownerName``.
    """
    resp = await _call(lambda c: c.get_devices())
    ident = identifier.strip()
    mac = _norm_mac(ident)

    exact = [
        d
        for d in resp.devices
        if (len(mac) == 12 and _norm_mac(d.mac) == mac)
        or ident in d.ip
        or (d.name or "").lower() == ident.lower()
    ]
    found = exact or [d for d in resp.devices if ident.lower() in (d.name or "").lower()]
    if not found:
        raise ToolError(
            f"No device matches {identifier!r}. Use list_devices with a search term to browse."
        )

    owners: dict[str, str] = {}
    if any(d.contact_id for d in found):
        try:
            people = await _get_client().get_people()
            owners = {
                p.contact_info.contact_id: p.contact_info.display_name
                for p in people.people
                if p.contact_info.display_name
            }
        except FingAPIError:
            pass  # /people is Fing Desktop only; owner names are best-effort

    results = []
    for d in _sorted_devices(found):
        item = _dump_device(d)
        if d.contact_id and d.contact_id in owners:
            item["ownerName"] = owners[d.contact_id]
        results.append(item)

    return {
        "query": identifier,
        "match": "exact" if exact else "partial",
        "count": len(results),
        "devices": results,
    }


@mcp.tool(
    name="get_network_summary", annotations=_READ_ONLY, output_schema=output_schema(NetworkSummary)
)
async def get_network_summary(
    top: Annotated[
        int, Field(ge=1, le=50, description="How many recent / new devices to include")
    ] = 10,
) -> dict[str, Any]:
    """Summarise the network: online/offline counts, breakdown by type and make,
    devices with no name or make (possible unknowns), and the most recently
    changed and newest devices."""
    resp = await _call(lambda c: c.get_devices())
    devices = resp.devices

    def brief(d: Device) -> dict[str, Any]:
        return {
            k: v
            for k, v in {
                "mac": d.mac,
                "ip": d.ip,
                "name": d.name,
                "state": d.state,
                "make": d.make,
                "first_seen": d.first_seen,
                "last_changed": d.last_changed,
            }.items()
            if v not in (None, [])
        }

    epoch = datetime.min.replace(tzinfo=UTC)
    recent = sorted(
        devices, key=lambda d: (_parse_time(d.last_changed) or epoch, d.mac), reverse=True
    )
    newest = sorted(
        devices, key=lambda d: (_parse_time(d.first_seen) or epoch, d.mac), reverse=True
    )
    unknown = [d for d in devices if not d.name and not d.make]

    def ranked(counter: Counter) -> dict[str, int]:
        return dict(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))

    return {
        "networkId": resp.network_id,
        "total": len(devices),
        "online": sum(d.state == "UP" for d in devices),
        "offline": sum(d.state == "DOWN" for d in devices),
        "byType": ranked(Counter(d.type or "UNKNOWN" for d in devices)),
        "byMake": ranked(Counter(d.make or "Unknown" for d in devices)),
        "unidentifiedCount": len(unknown),
        "unidentified": [brief(d) for d in _sorted_devices(unknown)][:top],
        "recentlyChanged": [brief(d) for d in recent if d.last_changed][:top],
        "newest": [brief(d) for d in newest if d.first_seen][:top],
    }


@mcp.tool(name="list_people", annotations=_READ_ONLY, output_schema=output_schema(PeopleListResult))
async def list_people(
    state: Annotated[
        Literal["ONLINE", "OFFLINE"] | None,
        Field(description="Only people currently ONLINE or OFFLINE"),
    ] = None,
    include_pictures: Annotated[
        bool, Field(description="Include base64 avatar image data (large; off by default)")
    ] = False,
) -> dict[str, Any]:
    """List people (Fing contacts) and their presence. Requires Fing Desktop as the agent."""
    resp = await _call(lambda c: c.get_people())
    people = resp.people
    if state:
        people = [p for p in people if p.current_state == state]
    people = sorted(
        people,
        key=lambda p: ((p.contact_info.display_name or "").lower(), p.contact_info.contact_id),
    )

    exclude: dict[str, Any] | None = (
        None if include_pictures else {"contact_info": {"picture_image_data"}}
    )
    return {
        "networkId": resp.network_id,
        "lastChangeTime": resp.last_change_time,
        "count": len(people),
        "people": [p.model_dump(by_alias=True, exclude_none=True, exclude=exclude) for p in people],
    }


@mcp.tool(name="get_agent_status", annotations=_READ_ONLY, output_schema=output_schema(AgentStatus))
async def get_agent_status() -> dict[str, Any]:
    """Diagnose the connection to Fing: checks the Local API (/devices and /people)
    and reads the agent's UPnP identity (Fingbox / Fing Agent only). Never fails —
    each check reports ok or the error it hit, including configuration errors."""
    status: dict[str, Any] = {"serverVersion": __version__}
    try:
        client = _get_client()
    except ToolError as exc:
        skipped = {"ok": False, "error": "skipped: fix the configuration error first"}
        status["config"] = {"ok": False, "error": str(exc)}
        status.update(devicesEndpoint=skipped, peopleEndpoint=skipped, agentInfo=skipped)
        return status
    status["apiBaseUrl"] = client.api_root
    status["config"] = {"ok": True}

    try:
        devices = await client.get_devices()
        status["devicesEndpoint"] = {
            "ok": True,
            "networkId": devices.network_id,
            "deviceCount": len(devices.devices),
        }
    except FingAPIError as exc:
        status["devicesEndpoint"] = {"ok": False, "error": str(exc)}

    try:
        people = await client.get_people()
        status["peopleEndpoint"] = {"ok": True, "peopleCount": len(people.people)}
    except FingAPIError as exc:
        status["peopleEndpoint"] = {"ok": False, "error": str(exc)}

    try:
        status["agentInfo"] = {"ok": True, **await client.get_agent_info()}
    except FingAPIError as exc:
        status["agentInfo"] = {
            "ok": False,
            "error": f"{exc} (UPnP agent info is only published by Fingbox and Fing Agent, not Fing Desktop)",
        }
    return status


# ------------------------------------------------------------------ http extras


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request: Request) -> JSONResponse:
    """Liveness probe for the HTTP transport (does not call Fing)."""
    return JSONResponse({"status": "ok", "version": __version__})


# ------------------------------------------------------------------------ main


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), stream=sys.stderr)
    # httpx logs full request URLs at INFO, and the Fing key travels in the query string.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    if not os.environ.get("FING_API_KEY"):
        log.warning("FING_API_KEY is not set; tools will fail until it is configured.")

    transport = os.environ.get("MCP_TRANSPORT", "stdio").strip().lower()
    if transport == "stdio":
        mcp.run(show_banner=False)
    elif transport in {"http", "streamable-http", "sse"}:
        mcp.run(
            transport=transport,
            host=os.environ.get("MCP_HOST", "127.0.0.1"),
            port=int(os.environ.get("MCP_PORT", "8000")),
            show_banner=False,
        )
    else:
        raise SystemExit(f"Unknown MCP_TRANSPORT {transport!r}; use stdio, http or sse.")


if __name__ == "__main__":
    main()
