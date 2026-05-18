"""Tests for MyOpelSensor — focus on timestamp conversion and time_offset option."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

# conftest.py injects HA stubs before these imports run.
from custom_components.myopel.const import (
    CONF_TIME_OFFSET,
    DEFAULT_TIME_OFFSET,
)
from custom_components.myopel.sensor import (
    MyOpelObdExtraPidSensor,
    MyOpelObdSensor,
    MyOpelSensor,
    MyOpelSensorDescription,
)
from tests.conftest import (
    ConfigEntry,
    CoordinatorEntity,
    DataUpdateCoordinator,
    SensorDeviceClass,
    SensorStateClass,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_description(
    key: str = "last_trip_start",
    device_class: SensorDeviceClass | None = SensorDeviceClass.TIMESTAMP,
) -> MyOpelSensorDescription:
    return MyOpelSensorDescription(
        key=key,
        data_key=key,
        name="Test sensor",
        device_class=device_class,
    )


def _make_sensor(
    data: dict,
    options: dict | None = None,
    entry_data: dict | None = None,
    description: MyOpelSensorDescription | None = None,
) -> MyOpelSensor:
    coord = DataUpdateCoordinator()
    coord.data = data
    entry = ConfigEntry(
        data=entry_data or {"file_path": "/config/myopel/"},
        options=options or {},
    )
    desc = description or _make_description()
    return MyOpelSensor(coord, desc, "TESTVINARGSTEST", entry)


# ── Timestamp conversion tests ────────────────────────────────────────────────

class TestNativeValueTimestamp:

    def test_default_offset_applies_utc_plus1(self):
        """With no options set, timestamps get UTC+1 (CET winter default)."""
        sensor = _make_sensor({"last_trip_start": "2024-01-15T10:30:00Z"})
        result = sensor.native_value
        assert isinstance(result, datetime)
        assert result == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone(timedelta(hours=1)))
        assert result.utcoffset() == timedelta(hours=1)

    def test_offset_2_from_options(self):
        """When options.time_offset=2, timestamps get UTC+2 (CEST summer)."""
        sensor = _make_sensor(
            {"last_trip_start": "2024-07-15T10:30:00Z"},
            options={CONF_TIME_OFFSET: 2},
        )
        result = sensor.native_value
        assert isinstance(result, datetime)
        assert result.utcoffset() == timedelta(hours=2)
        assert result == datetime(2024, 7, 15, 10, 30, 0, tzinfo=timezone(timedelta(hours=2)))

    def test_options_offset_overrides_data_offset(self):
        """entry.options takes precedence over entry.data for time_offset."""
        sensor = _make_sensor(
            {"last_trip_start": "2024-07-01T08:00:00Z"},
            entry_data={"file_path": "/config/myopel/", CONF_TIME_OFFSET: 1},
            options={CONF_TIME_OFFSET: 2},
        )
        result = sensor.native_value
        assert result.utcoffset() == timedelta(hours=2)

    def test_offset_fallback_to_entry_data(self):
        """When options has no time_offset, entry.data is used as fallback."""
        sensor = _make_sensor(
            {"last_trip_start": "2024-07-01T08:00:00Z"},
            entry_data={"file_path": "/config/myopel/", CONF_TIME_OFFSET: 2},
            options={},
        )
        result = sensor.native_value
        assert result.utcoffset() == timedelta(hours=2)

    def test_offset_zero(self):
        """Offset=0 treats timestamps as plain UTC."""
        sensor = _make_sensor(
            {"last_trip_start": "2024-03-10T12:00:00Z"},
            options={CONF_TIME_OFFSET: 0},
        )
        result = sensor.native_value
        assert result.utcoffset() == timedelta(0)

    def test_timestamp_preserves_wall_clock_value(self):
        """The wall-clock time in the timestamp is preserved regardless of offset."""
        raw = "2024-08-20T09:45:00Z"
        for offset in (1, 2):
            sensor = _make_sensor({"last_trip_start": raw}, options={CONF_TIME_OFFSET: offset})
            result = sensor.native_value
            assert result.hour == 9
            assert result.minute == 45

    def test_invalid_timestamp_returns_none(self):
        """Malformed timestamp strings return None without raising."""
        sensor = _make_sensor({"last_trip_start": "not-a-date"})
        assert sensor.native_value is None

    def test_none_value_returns_none(self):
        """None coordinator value passes through as None (non-string check)."""
        sensor = _make_sensor({"last_trip_start": None})
        assert sensor.native_value is None

    def test_missing_key_returns_none(self):
        """Missing key in coordinator.data returns None."""
        sensor = _make_sensor({})
        assert sensor.native_value is None

    def test_end_timestamp_also_converted(self):
        """last_trip_end uses the same offset logic."""
        sensor = _make_sensor(
            {"last_trip_end": "2024-01-10T11:00:00Z"},
            options={CONF_TIME_OFFSET: 1},
            description=_make_description(
                key="last_trip_end",
                device_class=SensorDeviceClass.TIMESTAMP,
            ),
        )
        result = sensor.native_value
        assert isinstance(result, datetime)
        assert result.utcoffset() == timedelta(hours=1)


# ── Non-timestamp sensor tests ────────────────────────────────────────────────

class TestNativeValueNonTimestamp:

    def test_numeric_value_passed_through(self):
        """Non-timestamp sensors return the raw value unchanged."""
        desc = _make_description(key="mileage_km", device_class=SensorDeviceClass.DISTANCE)
        sensor = _make_sensor({"mileage_km": 12345.6}, description=desc)
        assert sensor.native_value == 12345.6

    def test_none_value_passed_through(self):
        """None is passed through for non-timestamp sensors."""
        desc = _make_description(key="mileage_km", device_class=SensorDeviceClass.DISTANCE)
        sensor = _make_sensor({"mileage_km": None}, description=desc)
        assert sensor.native_value is None

    def test_no_device_class_passed_through(self):
        """Sensors with no device_class return the raw value."""
        desc = _make_description(key="last_trip_alert_count", device_class=None)
        sensor = _make_sensor({"last_trip_alert_count": 3}, description=desc)
        assert sensor.native_value == 3


# ── Sensor metadata tests ─────────────────────────────────────────────────────

class TestSensorMetadata:

    def test_unique_id_format(self):
        """Unique ID is {entry_id}_{sensor_key}."""
        sensor = _make_sensor({})
        assert sensor._attr_unique_id == "test_entry_id_last_trip_start"

    def test_extra_state_attributes_exposes_vin(self):
        """extra_state_attributes always exposes the VIN."""
        sensor = _make_sensor({})
        attrs = sensor.extra_state_attributes
        assert attrs == {"vin": "TESTVINARGSTEST"}

    def test_available_false_when_no_data(self):
        """Sensor is unavailable when coordinator.data is empty/falsy."""
        sensor = _make_sensor({})
        assert sensor.available is False

    def test_available_true_when_data_present(self):
        """Sensor is available when coordinator.data is non-empty."""
        sensor = _make_sensor({"mileage_km": 100})
        assert sensor.available is True



class TestObdDpfRegenActive:
    """DPF regen status is a multi-value code — pass the number through unchanged."""

    def _make_regen_sensor(self, raw):
        coord = DataUpdateCoordinator()
        coord.data = {"obd_trip_dpf_regen_active": raw}
        entry = ConfigEntry()
        desc = MyOpelSensorDescription(
            key="obd_trip_dpf_regen_active",
            data_key="obd_trip_dpf_regen_active",
            name="OBD – DPF rigenerazione attiva",
        )
        return MyOpelObdSensor(coord, desc, "VIN", entry)

    def test_zero_passes_through(self):
        assert self._make_regen_sensor(0).native_value == 0

    def test_one_passes_through(self):
        assert self._make_regen_sensor(1).native_value == 1

    def test_six_passes_through(self):
        # ECU can report codes like 6 (post-regen / completed state)
        assert self._make_regen_sensor(6).native_value == 6

    def test_float_passes_through(self):
        # _compute_stats stores aggregations as floats (e.g. 6.0)
        assert self._make_regen_sensor(6.0).native_value == 6.0


# ── OBD extra PID sensor ──────────────────────────────────────────────────────

class TestObdExtraPidSensor:
    def _make_extra(self, data):
        coord = DataUpdateCoordinator()
        coord.data = data
        entry = ConfigEntry()
        meta = {"name": "Tensione del MAP", "unit": "V"}
        return MyOpelObdExtraPidSensor(coord, "tensione_del_map", meta, "VIN12345", entry)

    def test_native_value_uses_last(self):
        sensor = self._make_extra({
            "obd_pid_values": {
                "tensione_del_map": {"last": 2.4, "min": 1.0, "max": 3.0, "mean": 2.0,
                                     "first": 1.0, "samples": 5}
            }
        })
        assert sensor.native_value == 2.4

    def test_attributes_include_min_max_mean(self):
        sensor = self._make_extra({
            "obd_pid_values": {
                "tensione_del_map": {
                    "last": 2.4, "min": 1.0, "max": 3.0, "mean": 2.0,
                    "first": 1.0, "samples": 5,
                    "first_seen_s": 0.0, "last_seen_s": 50.0,
                    "age_from_trip_end_s": 150.0, "coverage_pct": 25.0,
                    "sample_rate_hz": 0.04, "is_stale": True,
                }
            }
        })
        attrs = sensor.extra_state_attributes
        assert attrs["min"] == 1.0
        assert attrs["max"] == 3.0
        assert attrs["mean"] == 2.0
        assert attrs["pid_name"] == "Tensione del MAP"
        assert attrs["coverage_pct"] == 25.0
        assert attrs["is_stale"] is True
        assert attrs["age_from_trip_end_s"] == 150.0

    def test_unavailable_when_slug_missing(self):
        sensor = self._make_extra({"obd_pid_values": {}})
        assert sensor.native_value is None
        assert sensor.available is False

    def test_boolean_pid_rendered_as_label(self):
        coord = DataUpdateCoordinator()
        coord.data = {
            "obd_pid_values": {
                "flag_pid": {"last": 1.0, "min": 0.0, "max": 1.0, "mean": 0.5,
                             "first": 0.0, "samples": 4, "kind": "bool"}
            }
        }
        entry = ConfigEntry()
        meta = {"name": "Flag PID", "unit": None, "kind": "bool"}
        sensor = MyOpelObdExtraPidSensor(coord, "flag_pid", meta, "VIN", entry)
        assert sensor.native_value == "Sì"
        assert sensor._attr_native_unit_of_measurement is None

        # Same sensor with raw 0 → "No"
        coord.data["obd_pid_values"]["flag_pid"]["last"] = 0.0
        assert sensor.native_value == "No"
