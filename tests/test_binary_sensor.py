"""Tests for the dedicated MyOpel binary-sensor platform."""
from __future__ import annotations

from custom_components.myopel.binary_sensor import MyOpelAlertActiveBinarySensor
from tests.conftest import DataUpdateCoordinator


def test_alert_binary_sensor_state_and_metadata():
    coordinator = DataUpdateCoordinator()
    coordinator.data = {
        "last_trip_has_unack_alerts": True,
        "last_trip_has_alerts": True,
        "last_trip_id": 42,
        "last_trip_alerts_raw": [52],
        "last_trip_unack_alerts_raw": [52],
    }
    sensor = MyOpelAlertActiveBinarySensor(coordinator, "TESTVIN123456", "entry")

    assert sensor.is_on is True
    assert sensor.icon == "mdi:alert-circle"
    assert sensor._attr_unique_id == "entry_last_trip_has_alerts"
    assert sensor.extra_state_attributes["trip_id"] == 42
