"""Binary sensor platform for the MyOpel integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MyOpelCoordinator
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the MyOpel alert binary sensor."""
    coordinator: MyOpelCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    vin = coordinator.data.get("vin", "unknown")
    async_add_entities(
        [MyOpelAlertActiveBinarySensor(coordinator, vin, entry.entry_id)]
    )


class MyOpelAlertActiveBinarySensor(
    CoordinatorEntity[MyOpelCoordinator], BinarySensorEntity
):
    """Report unacknowledged alerts from the latest trip."""

    _attr_has_entity_name = True
    _attr_name = "Ultimo viaggio – Alert presenti"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: MyOpelCoordinator,
        vin: str,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._vin = vin
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_last_trip_has_alerts"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, vin)},
            name=f"Opel ({vin[-6:]})",
            manufacturer="Opel",
            model="MyOpel Export",
            serial_number=vin,
        )

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.data)

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("last_trip_has_unack_alerts", False))

    @property
    def icon(self) -> str:
        if self.is_on:
            return "mdi:alert-circle"
        if self.coordinator.data.get("last_trip_has_alerts"):
            return "mdi:alert-circle-check-outline"
        return "mdi:alert-circle-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {
            "vin": self._vin,
            "entry_id": self._entry_id,
            "trip_id": data.get("last_trip_id"),
            "all_codes": data.get("last_trip_alerts_raw") or [],
            "unacknowledged_codes": data.get("last_trip_unack_alerts_raw") or [],
            "acknowledged_codes": data.get("last_trip_acked_alerts_raw") or [],
            "has_any_alerts": bool(data.get("last_trip_has_alerts")),
            "acknowledged_labels": data.get("last_trip_acked_alert_codes"),
            "unacknowledged_labels": data.get("last_trip_unack_alert_codes"),
            "code_labels": data.get("last_trip_alert_labels") or {},
        }
