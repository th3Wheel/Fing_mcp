"""Typed Pydantic models for the Fing Local API (v1.1.0).

Field names and aliases follow the published contract at
https://www.fing.com/integrations/local-api/ and the reference client used by
Home Assistant (``fing_agent_api``). Note that the ``/devices`` payload uses
snake_case timestamps (``first_seen``, ``last_changed``) while ``/people``
uses camelCase — the aliases below mirror the wire format exactly.

Unknown fields are preserved (``extra="allow"``) so a newer Fing agent that
adds fields does not break validation.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _FingModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")


class Device(_FingModel):
    """A device discovered by the Fing agent."""

    mac: str = Field(description="MAC address of the device")
    ip: list[str] = Field(default_factory=list, description="IP addresses assigned to the device")
    state: str = Field(description="Presence state: 'UP' (online) or 'DOWN' (offline)")
    name: str | None = Field(default=None, description="Friendly name of the device")
    type: str | None = Field(default=None, description="Fing device type, e.g. STREAMING_DONGLE")
    make: str | None = Field(default=None, description="Device manufacturer")
    model: str | None = Field(default=None, description="Device model")
    contact_id: str | None = Field(
        default=None,
        alias="contactId",
        description="ID of the Fing contact (person) who owns this device",
    )
    first_seen: str | None = Field(
        default=None, description="ISO-8601 time the device was first seen"
    )
    last_changed: str | None = Field(
        default=None, description="ISO-8601 time of the last state change"
    )

    @field_validator("ip", mode="before")
    @classmethod
    def _coerce_ip(cls, value: Any) -> Any:
        """Accept a bare string or null defensively; the contract says list[str]."""
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("state", mode="before")
    @classmethod
    def _normalise_state(cls, value: Any) -> Any:
        return value.upper() if isinstance(value, str) else value


class FingDevicesResponse(_FingModel):
    """Top-level response from ``GET /1/devices``."""

    network_id: str | None = Field(
        default=None, alias="networkId", description="Fing network identifier"
    )
    devices: list[Device] = Field(
        default_factory=list, description="Devices discovered on the network"
    )


class ContactInfo(_FingModel):
    """Identity details of a Fing contact."""

    contact_id: str = Field(alias="contactId", description="Unique contact identifier (UUID)")
    display_name: str | None = Field(
        default=None, alias="displayName", description="Contact display name"
    )
    contact_type: str | None = Field(
        default=None, alias="contactType", description="Contact type, e.g. FAMILY"
    )
    picture_url: str | None = Field(
        default=None, alias="pictureUrl", description="Avatar URL, if any"
    )
    picture_image_data: str | None = Field(
        default=None, alias="pictureImageData", description="Base64-encoded avatar image, if any"
    )


class Contact(_FingModel):
    """A person tracked by Fing, with their presence state."""

    state_change_time: str | None = Field(
        default=None, alias="stateChangeTime", description="ISO-8601 time presence last changed"
    )
    contact_info: ContactInfo = Field(alias="contactInfo", description="Identity details")
    current_state: str | None = Field(
        default=None,
        alias="currentState",
        description="'ONLINE' or 'OFFLINE'; absent when no presence device is assigned",
    )
    presence_device_details: dict[str, Any] | None = Field(
        default=None, alias="presenceDeviceDetails", description="Device used to infer presence"
    )


class FingPeopleResponse(_FingModel):
    """Top-level response from ``GET /1/people`` (Fing Desktop only)."""

    network_id: str | None = Field(
        default=None, alias="networkId", description="Fing network identifier"
    )
    last_change_time: str | None = Field(
        default=None,
        alias="lastChangeTime",
        description="ISO-8601 time of the last presence change",
    )
    people: list[Contact] = Field(default_factory=list, description="Contacts and their presence")


# ---------------------------------------------------------------------------
# Tool output models
#
# Tools return plain dicts keyed by the wire (alias) names with None values
# omitted; these models exist to publish an accurate ``outputSchema`` for each
# tool (see ``output_schema()``) and are checked against real tool output in
# tests/test_contracts.py.
# ---------------------------------------------------------------------------


class DeviceListResult(_FingModel):
    network_id: str | None = Field(default=None, alias="networkId")
    total: int = Field(description="Devices on the network before filtering")
    count: int = Field(description="Devices matching the filters")
    devices: list[Device]


class DeviceWithOwner(Device):
    owner_name: str | None = Field(
        default=None, alias="ownerName", description="Display name of the owning contact"
    )


class DeviceLookupResult(_FingModel):
    query: str
    match: Literal["exact", "partial"]
    count: int
    devices: list[DeviceWithOwner]


class DeviceBrief(_FingModel):
    mac: str
    ip: list[str] = Field(default_factory=list)
    name: str | None = None
    state: str
    make: str | None = None
    first_seen: str | None = None
    last_changed: str | None = None


class NetworkSummary(_FingModel):
    network_id: str | None = Field(default=None, alias="networkId")
    total: int
    online: int
    offline: int
    by_type: dict[str, int] = Field(alias="byType", description="Device count per Fing type")
    by_make: dict[str, int] = Field(alias="byMake", description="Device count per manufacturer")
    unidentified_count: int = Field(alias="unidentifiedCount")
    unidentified: list[DeviceBrief] = Field(description="Devices with neither name nor make")
    recently_changed: list[DeviceBrief] = Field(alias="recentlyChanged")
    newest: list[DeviceBrief]


class PeopleListResult(_FingModel):
    network_id: str | None = Field(default=None, alias="networkId")
    last_change_time: str | None = Field(default=None, alias="lastChangeTime")
    count: int
    people: list[Contact]


class CheckResult(_FingModel):
    """Outcome of one diagnostic check; extra keys carry check-specific detail."""

    ok: bool
    error: str | None = None


class AgentStatus(_FingModel):
    server_version: str = Field(alias="serverVersion")
    api_base_url: str | None = Field(default=None, alias="apiBaseUrl")
    config: CheckResult
    devices_endpoint: CheckResult = Field(alias="devicesEndpoint")
    people_endpoint: CheckResult = Field(alias="peopleEndpoint")
    agent_info: CheckResult = Field(alias="agentInfo")


def output_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema for a tool result, using wire names and treating defaulted fields as optional."""
    return model.model_json_schema(by_alias=True, mode="validation")
