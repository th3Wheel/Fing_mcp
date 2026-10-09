"""Unit tests for the Pydantic models against the Fing v1.1.0 wire format."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from models import Device, FingDevicesResponse, FingPeopleResponse
from tests.fixtures import DEVICES_PAYLOAD, PEOPLE_PAYLOAD


def test_devices_response_parses_documented_example():
    resp = FingDevicesResponse.model_validate(DEVICES_PAYLOAD)
    assert resp.network_id == "wifi-12345812839223"
    d = resp.devices[0]
    assert d.ip == ["192.168.0.20"]
    assert d.state == "UP"
    assert d.make == "Google"
    assert d.contact_id == "67363e09-5ad6-40d0-883f-3e17254eec7a"
    assert d.first_seen == "2020-04-24T12:54:21.634Z"


def test_device_dump_uses_wire_names():
    d = Device.model_validate(DEVICES_PAYLOAD["devices"][0])
    dumped = d.model_dump(by_alias=True, exclude_none=True)
    assert set(dumped) == set(DEVICES_PAYLOAD["devices"][0])


def test_device_minimal():
    d = Device.model_validate({"mac": "AA", "ip": [], "state": "DOWN"})
    assert d.name is None and d.ip == []


@pytest.mark.parametrize(("raw", "expected"), [("10.0.0.1", ["10.0.0.1"]), (None, [])])
def test_device_ip_coercion(raw, expected):
    assert Device.model_validate({"mac": "AA", "ip": raw, "state": "UP"}).ip == expected


def test_device_state_normalised():
    assert Device.model_validate({"mac": "AA", "state": "up"}).state == "UP"


def test_device_requires_mac_and_state():
    with pytest.raises(ValidationError):
        Device.model_validate({"ip": ["1.2.3.4"]})


def test_unknown_fields_are_preserved():
    d = Device.model_validate({"mac": "AA", "state": "UP", "newField": 1})
    assert d.model_dump(by_alias=True)["newField"] == 1


def test_people_response():
    resp = FingPeopleResponse.model_validate(PEOPLE_PAYLOAD)
    assert resp.last_change_time == "2020-04-24T12:54:21.634Z"
    first = resp.people[0]
    assert first.contact_info.display_name == "Elenore"
    assert first.contact_info.contact_type == "COLLEAGUE"
    assert first.current_state == "ONLINE"
    assert first.presence_device_details == {}
    assert resp.people[1].current_state is None


def test_people_requires_contact_info():
    with pytest.raises(ValidationError):
        FingPeopleResponse.model_validate({"people": [{"currentState": "ONLINE"}]})
