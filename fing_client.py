"""Async HTTP client for the Fing Local API.

Contract (Fing Local API v1.1.0):

* Base URL ``http://<host>:<port>/1`` — default port ``49090``.
* Authentication is the ``auth`` **query parameter** (not a header).
* ``GET /1/devices`` — Fing Desktop, Fing Agent and Fingbox.
* ``GET /1/people``  — Fing Desktop only (503 elsewhere).
* Agent identity is published as UPnP XML on ``http://<host>:44444/``
  (Fingbox / Fing Agent only).

A single :class:`httpx.AsyncClient` is reused across calls (connection
pooling). The API key is never included in error messages.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, ValidationError

from config import FingConfig
from models import FingDevicesResponse, FingPeopleResponse


class FingAPIError(Exception):
    """A user-facing error talking to the Fing agent."""


_STATUS_HINTS: dict[int, str] = {
    400: "the request was rejected as malformed",
    401: "the API key was rejected — make sure FING_API_KEY matches the key shown under "
    "Agent Settings → Local API in Fing",
    404: "endpoint not found — check FING_API_BASE_URL points at the Fing Local API (default port 49090)",
    503: "the Fing agent is unavailable — it may not be running, still starting, or this "
    "agent type does not support the endpoint (/people requires Fing Desktop)",
}


class FingClient:
    """Thin, typed wrapper around the Fing Local API."""

    def __init__(self, cfg: FingConfig, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._cfg = cfg
        self._http = httpx.AsyncClient(
            timeout=cfg.fing_timeout,
            transport=transport or httpx.AsyncHTTPTransport(retries=cfg.fing_retries),
        )

    @property
    def api_root(self) -> str:
        return f"{self._cfg.fing_api_base_url}/1"

    @property
    def agent_info_url(self) -> str:
        parts = urlsplit(self._cfg.fing_api_base_url)
        host = parts.hostname or "localhost"
        if ":" in host:  # IPv6 literal
            host = f"[{host}]"
        return urlunsplit(
            (parts.scheme or "http", f"{host}:{self._cfg.fing_agent_info_port}", "/", "", "")
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------ core

    def _redact(self, text: str) -> str:
        key = self._cfg.fing_api_key
        return text.replace(key, "***") if key else text

    async def _request(self, url: str, *, params: dict[str, str] | None = None) -> httpx.Response:
        try:
            response = await self._http.get(url, params=params)
        except httpx.TimeoutException as exc:
            raise FingAPIError(
                f"Timed out after {self._cfg.fing_timeout:g}s contacting the Fing agent at "
                f"{self._cfg.fing_api_base_url}"
            ) from exc
        except httpx.RequestError as exc:
            raise FingAPIError(
                f"Could not reach the Fing agent at {self._cfg.fing_api_base_url} "
                f"({type(exc).__name__}: {self._redact(str(exc))}). Is Fing running with "
                "Local API enabled?"
            ) from exc

        if response.is_error:
            hint = _STATUS_HINTS.get(response.status_code, "unexpected error")
            body = self._redact(response.text[:200]).strip()
            detail = f" Response: {body}" if body else ""
            raise FingAPIError(
                f"Fing API returned HTTP {response.status_code} for {urlsplit(url).path}: {hint}.{detail}"
            )
        return response

    async def _get_model(self, path: str, model: type[BaseModel]) -> Any:
        if not self._cfg.fing_api_key:
            raise FingAPIError(
                "FING_API_KEY is not set. Enable Local API in Fing (Agent Settings → Local API) "
                "and put the key in your environment or .env file."
            )
        response = await self._request(
            f"{self.api_root}{path}", params={"auth": self._cfg.fing_api_key}
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise FingAPIError(f"Fing API returned non-JSON content for {path}") from exc
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise FingAPIError(f"Unexpected {path} response shape: {exc}") from exc

    # ------------------------------------------------------------- endpoints

    async def get_devices(self) -> FingDevicesResponse:
        return await self._get_model("/devices", FingDevicesResponse)

    async def get_people(self) -> FingPeopleResponse:
        return await self._get_model("/people", FingPeopleResponse)

    async def get_agent_info(self) -> dict[str, Any]:
        """Return agent identity parsed from the UPnP description on port 44444."""
        response = await self._request(self.agent_info_url)
        return parse_agent_info(response.text)


_UPNP_NS = {"u": "urn:schemas-upnp-org:device-1-0"}


def parse_agent_info(xml_text: str) -> dict[str, Any]:
    """Parse Fing's UPnP device description into a flat dict."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise FingAPIError("Agent info endpoint did not return valid UPnP XML") from exc

    def text(node: ET.Element | None, tag: str) -> str | None:
        if node is None:
            return None
        el = node.find(f"u:{tag}", _UPNP_NS)
        return el.text.strip() if el is not None and el.text else None

    info: dict[str, Any] = {
        "url_base": text(root, "URLBase"),
        "friendly_name": None,
        "model_name": None,
        "manufacturer": None,
        "device_type": None,
        "agent_id": None,
        "agent_state": None,
    }
    device = root.find("u:device", _UPNP_NS)
    if device is None:
        return info

    info["friendly_name"] = text(device, "friendlyName")
    info["model_name"] = text(device, "modelName")
    info["manufacturer"] = text(device, "manufacturer")
    device_type = text(device, "deviceType")
    if device_type:
        info["device_type"] = device_type.removeprefix("urn:fing:").removeprefix("urn:domotz:")

    for service in device.findall("u:serviceList/u:service", _UPNP_NS):
        stype = text(service, "serviceType") or ""
        for prefix in ("urn:fing:device:fingagent:mac:", "urn:domotz:device:fingbox:mac:"):
            if stype.startswith(prefix):
                info["agent_id"] = stype.removeprefix(prefix)
        if ":active:1" in stype:
            info["agent_state"] = "active"
        elif ":inactive:" in stype:
            info["agent_state"] = "inactive"
        elif ":unknown:1" in stype:
            info["agent_state"] = "unknown"
    return info
