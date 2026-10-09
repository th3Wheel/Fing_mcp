"""Typed Pydantic models for the Fing Local API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Device(BaseModel):
    """Represents a device discovered by Fing."""

    mac: str = Field(description="MAC address of the device")
    ip: str | None = Field(default=None, description="IP address of the device")
    name: str | None = Field(default=None, description="Friendly name of the device")
    vendor: str | None = Field(default=None, description="Hardware vendor of the device")
    type: str | None = Field(default=None, description="Device type")
    state: str | None = Field(default=None, description="Current state (up/down)")
    last_seen: str | None = Field(default=None, alias="lastSeen", description="ISO-8601 timestamp of last seen")

    model_config = {"populate_by_name": True}


class Person(BaseModel):
    """Represents a person tracked by Fing."""

    id: str = Field(description="Unique person identifier")
    name: str | None = Field(default=None, description="Person's display name")
    present: bool | None = Field(default=None, description="Whether the person is currently present")
    last_seen: str | None = Field(default=None, alias="lastSeen", description="ISO-8601 timestamp of last seen")

    model_config = {"populate_by_name": True}


class PeoplePresence(BaseModel):
    """Represents a presence event for a person."""

    person_id: str = Field(alias="personId", description="ID of the associated person")
    mac: str | None = Field(default=None, description="MAC address associated with this presence")
    present: bool = Field(description="Whether the device is present")
    last_seen: str | None = Field(default=None, alias="lastSeen", description="ISO-8601 timestamp of last seen")

    model_config = {"populate_by_name": True}


class FingDevicesResponse(BaseModel):
    """Top-level response from GET /devices."""

    devices: list[Device] = Field(default_factory=list, description="List of discovered devices")


class FingPeopleResponse(BaseModel):
    """Top-level response from GET /people."""

    people: list[Person] = Field(default_factory=list, description="List of tracked people")
    presence: list[PeoplePresence] = Field(default_factory=list, description="Presence records for each person")
