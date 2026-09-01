"""Unit tests for models.py — Pydantic model validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from models import (
    Device,
    FingDevicesResponse,
    FingPeopleResponse,
    PeoplePresence,
    Person,
)
from tests.fixtures import DEVICES_PAYLOAD, PEOPLE_PAYLOAD

# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------


def test_device_full():
    d = Device(
        mac="AA:BB:CC:DD:EE:FF",
        ip="192.168.1.1",
        name="router",
        vendor="Netgear",
        type="router",
        state="up",
        lastSeen="2024-01-01T00:00:00Z",
    )
    assert d.mac == "AA:BB:CC:DD:EE:FF"
    assert d.last_seen == "2024-01-01T00:00:00Z"


def test_device_minimal():
    d = Device(mac="AA:BB:CC:DD:EE:FF")
    assert d.mac == "AA:BB:CC:DD:EE:FF"
    assert d.ip is None
    assert d.name is None


def test_device_missing_mac():
    with pytest.raises(ValidationError):
        Device()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Person
# ---------------------------------------------------------------------------


def test_person_full():
    p = Person(id="p1", name="Bob", present=True, lastSeen="2024-01-01T00:00:00Z")
    assert p.id == "p1"
    assert p.present is True
    assert p.last_seen == "2024-01-01T00:00:00Z"


def test_person_minimal():
    p = Person(id="p2")
    assert p.name is None
    assert p.present is None


def test_person_missing_id():
    with pytest.raises(ValidationError):
        Person()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# PeoplePresence
# ---------------------------------------------------------------------------


def test_people_presence_full():
    pp = PeoplePresence(
        personId="p1",
        mac="AA:BB:CC:DD:EE:FF",
        present=True,
        lastSeen="2024-01-01T00:00:00Z",
    )
    assert pp.person_id == "p1"
    assert pp.present is True


def test_people_presence_missing_required():
    with pytest.raises(ValidationError):
        PeoplePresence(mac="AA:BB:CC:DD:EE:FF")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# FingDevicesResponse
# ---------------------------------------------------------------------------


def test_fing_devices_response_from_payload():
    resp = FingDevicesResponse.model_validate(DEVICES_PAYLOAD)
    assert len(resp.devices) == 1
    assert resp.devices[0].mac == "AA:BB:CC:DD:EE:FF"


def test_fing_devices_response_empty():
    resp = FingDevicesResponse(devices=[])
    assert resp.devices == []


def test_fing_devices_response_default_empty():
    resp = FingDevicesResponse()
    assert resp.devices == []


# ---------------------------------------------------------------------------
# FingPeopleResponse
# ---------------------------------------------------------------------------


def test_fing_people_response_from_payload():
    resp = FingPeopleResponse.model_validate(PEOPLE_PAYLOAD)
    assert len(resp.people) == 1
    assert len(resp.presence) == 1
    assert resp.people[0].name == "Alice"
    assert resp.presence[0].person_id == "person-1"


def test_fing_people_response_empty():
    resp = FingPeopleResponse()
    assert resp.people == []
    assert resp.presence == []
