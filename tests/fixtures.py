"""Shared payloads mirroring the Fing Local API v1.1.0 wire format."""

from __future__ import annotations

from typing import Any

NETWORK_ID = "wifi-12345812839223"
OWNER_ID = "67363e09-5ad6-40d0-883f-3e17254eec7a"

DEVICES_PAYLOAD: dict[str, Any] = {
    "networkId": NETWORK_ID,
    "devices": [
        {
            "mac": "00:11:22:33:44:55",
            "ip": ["192.168.0.20"],
            "state": "UP",
            "name": "Bedroom Chromecast",
            "type": "STREAMING_DONGLE",
            "make": "Google",
            "model": "Chromecast",
            "contactId": OWNER_ID,
            "first_seen": "2020-04-24T12:54:21.634Z",
            "last_changed": "2020-06-11T12:01:23.164Z",
        },
        {
            "mac": "AA:BB:CC:DD:EE:01",
            "ip": ["192.168.0.3"],
            "state": "DOWN",
            "name": "Garage WLED",
            "type": "LIGHT",
            "make": "Espressif",
            "first_seen": "2021-01-01T00:00:00Z",
            "last_changed": "2021-02-01T00:00:00Z",
        },
        {
            "mac": "AA:BB:CC:DD:EE:02",
            "ip": [],
            "state": "UP",
        },
    ],
}

PEOPLE_PAYLOAD: dict[str, Any] = {
    "networkId": NETWORK_ID,
    "lastChangeTime": "2020-04-24T12:54:21.634Z",
    "people": [
        {
            "stateChangeTime": "2020-04-24T12:54:21.634Z",
            "contactInfo": {
                "contactId": OWNER_ID,
                "displayName": "Elenore",
                "contactType": "COLLEAGUE",
                "pictureImageData": "iVBORw0KGgo=",
            },
            "currentState": "ONLINE",
            "presenceDeviceDetails": {},
        },
        {
            "stateChangeTime": "2020-04-25T08:00:00Z",
            "contactInfo": {"contactId": "c2", "displayName": "Bob", "contactType": "FAMILY"},
        },
    ],
}

AGENT_INFO_XML = """<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <URLBase>http://192.168.0.2:44444</URLBase>
  <device>
    <deviceType>urn:fing:device:fingagent:1</deviceType>
    <friendlyName>Fing Agent (proxmox)</friendlyName>
    <manufacturer>Fing</manufacturer>
    <modelName>Fing Agent</modelName>
    <serviceList>
      <service><serviceType>urn:fing:device:fingagent:mac:0A1B2C3D4E5F</serviceType></service>
      <service><serviceType>urn:fing:service:state:active:1</serviceType></service>
    </serviceList>
  </device>
</root>
"""
