"""Home Assistant module stubs for testing without the full HA runtime.

All stubs are injected into sys.modules at import time so that
custom_components.myopel.* can be imported without a real HA installation.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from unittest.mock import MagicMock

import pytest


# ── Enum stubs ────────────────────────────────────────────────────────────────

class SensorDeviceClass(str, Enum):
    DISTANCE = "distance"
    DURATION = "duration"
    ENERGY = "energy"
    TIMESTAMP = "timestamp"
    VOLUME = "volume"


class SensorStateClass(str, Enum):
    MEASUREMENT = "measurement"
    TOTAL = "total"
    TOTAL_INCREASING = "total_increasing"


class BinarySensorDeviceClass(str, Enum):
    PROBLEM = "problem"


class UnitOfLength(str, Enum):
    KILOMETERS = "km"
    MILES = "mi"


class UnitOfTime(str, Enum):
    MINUTES = "min"
    SECONDS = "s"
    HOURS = "h"
    DAYS = "d"


class UnitOfVolume(str, Enum):
    LITERS = "L"


PERCENTAGE = "%"


# ── Dataclass stubs ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SensorEntityDescription:
    key: str = ""
    name: str = ""
    native_unit_of_measurement: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    icon: str = ""


@dataclass
class DeviceInfo:
    identifiers: set = field(default_factory=set)
    name: str = ""
    manufacturer: str = ""
    model: str = ""
    serial_number: str = ""


# ── Entity base stubs ─────────────────────────────────────────────────────────

class SensorEntity:
    pass


class BinarySensorEntity:
    pass


class CoordinatorEntity:
    def __init__(self, coordinator: Any) -> None:
        self.coordinator = coordinator

    def __class_getitem__(cls, item: Any) -> type:
        return cls

    @property
    def available(self) -> bool:
        return True


class DataUpdateCoordinator:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.data: dict = {}


class UpdateFailed(Exception):
    pass


# ── Config entry stub ─────────────────────────────────────────────────────────

class ConfigEntry:
    def __init__(
        self,
        data: dict | None = None,
        options: dict | None = None,
        entry_id: str = "test_entry_id",
    ) -> None:
        self.data = data or {}
        self.options = options or {}
        self.entry_id = entry_id


# ── Selector stubs ────────────────────────────────────────────────────────────

class NumberSelectorMode(str, Enum):
    BOX = "box"
    SLIDER = "slider"


@dataclass
class NumberSelectorConfig:
    min: float = 0
    max: float = 100
    step: float = 1
    mode: NumberSelectorMode = NumberSelectorMode.BOX


class NumberSelector:
    def __init__(self, config: NumberSelectorConfig | None = None) -> None:
        self.config = config


# ── Other stubs ───────────────────────────────────────────────────────────────

class Store:
    """In-memory stand-in for homeassistant.helpers.storage.Store."""

    def __init__(self, hass: Any, version: int, key: str) -> None:
        self._hass = hass
        self._version = version
        self._key = key
        self._data: Any = None

    async def async_load(self) -> Any:
        return self._data

    async def async_save(self, data: Any) -> None:
        self._data = data


class StaticPathConfig:
    pass


class FlowResult(dict):
    pass


def callback(func: Any) -> Any:
    return func


# ── sys.modules injection ─────────────────────────────────────────────────────

def _make(overrides: dict) -> MagicMock:
    """Return a MagicMock with the given attribute overrides applied."""
    m = MagicMock()
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


_STUBS: dict[str, Any] = {
    "homeassistant": MagicMock(),
    "homeassistant.components": MagicMock(),
    "homeassistant.components.sensor": _make({
        "SensorDeviceClass": SensorDeviceClass,
        "SensorEntity": SensorEntity,
        "SensorEntityDescription": SensorEntityDescription,
        "SensorStateClass": SensorStateClass,
    }),
    "homeassistant.components.binary_sensor": _make({
        "BinarySensorDeviceClass": BinarySensorDeviceClass,
        "BinarySensorEntity": BinarySensorEntity,
    }),
    "homeassistant.components.frontend": MagicMock(),
    "homeassistant.components.http": _make({"StaticPathConfig": StaticPathConfig}),
    "homeassistant.components.persistent_notification": MagicMock(),
    "homeassistant.config_entries": _make({
        "ConfigEntry": ConfigEntry,
        "ConfigFlow": MagicMock,
        "OptionsFlow": MagicMock,
    }),
    "homeassistant.const": _make({
        "PERCENTAGE": PERCENTAGE,
        "UnitOfLength": UnitOfLength,
        "UnitOfTime": UnitOfTime,
        "UnitOfVolume": UnitOfVolume,
    }),
    "homeassistant.core": _make({
        "HomeAssistant": MagicMock,
        "callback": callback,
    }),
    "homeassistant.data_entry_flow": _make({"FlowResult": FlowResult}),
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.entity": _make({"DeviceInfo": DeviceInfo}),
    "homeassistant.helpers.entity_platform": MagicMock(),
    "homeassistant.helpers.event": _make({
        "async_track_time_interval": lambda *a, **kw: (lambda: None),
    }),
    "homeassistant.helpers.selector": _make({
        "NumberSelector": NumberSelector,
        "NumberSelectorConfig": NumberSelectorConfig,
        "NumberSelectorMode": NumberSelectorMode,
    }),
    "homeassistant.helpers.storage": _make({"Store": Store}),
    "homeassistant.helpers.update_coordinator": _make({
        "CoordinatorEntity": CoordinatorEntity,
        "DataUpdateCoordinator": DataUpdateCoordinator,
        "UpdateFailed": UpdateFailed,
    }),
    "watchdog": MagicMock(),
    "watchdog.events": MagicMock(),
    "watchdog.observers": MagicMock(),
}

for _mod_name, _mod in _STUBS.items():
    sys.modules.setdefault(_mod_name, _mod)


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def mock_config_entry() -> ConfigEntry:
    """Config entry with realistic default options."""
    return ConfigEntry(
        data={"file_path": "/config/myopel/"},
        options={},
    )


@pytest.fixture
def mock_coordinator() -> DataUpdateCoordinator:
    """Coordinator with empty data."""
    coord = DataUpdateCoordinator()
    coord.data = {}
    return coord
