"""Shared fixtures for the Fing MCP test suite."""

from __future__ import annotations

from typing import Any

DEVICES_PAYLOAD: dict[str, Any] = {
    "devices": [
        {
            "mac": "AA:BB:CC:DD:EE:FF",
            "ip": "192.168.1.42",
            "name": "my-laptop",
            "vendor": "Apple",
            "type": "laptop",
            "state": "up",
            "lastSeen": "2024-01-01T00:00:00Z",
        }
    ]
}

PEOPLE_PAYLOAD: dict[str, Any] = {
    "people": [
        {
            "id": "person-1",
            "name": "Alice",
            "present": True,
            "lastSeen": "2024-01-01T00:00:00Z",
        }
    ],
    "presence": [
        {
            "personId": "person-1",
            "mac": "AA:BB:CC:DD:EE:FF",
            "present": True,
            "lastSeen": "2024-01-01T00:00:00Z",
        }
    ],
}
