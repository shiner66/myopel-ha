"""Sensor platform for MyOpel integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from .const import CONF_TIME_OFFSET, DEFAULT_TIME_OFFSET
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from . import MyOpelCoordinator


@dataclass(frozen=True, kw_only=True)
class MyOpelSensorDescription(SensorEntityDescription):
    """Extended description for MyOpel sensors."""
    data_key: str
    icon: str = "mdi:car"


SENSOR_DESCRIPTIONS: tuple[MyOpelSensorDescription, ...] = (
    # ── Vehicle state ────────────────────────────────────────────────────────
    MyOpelSensorDescription(
        key="mileage_km",
        data_key="mileage_km",
        name="Chilometraggio",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
    ),
    MyOpelSensorDescription(
        key="fuel_level_pct",
        data_key="fuel_level_pct",
        name="Livello carburante",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gas-station",
    ),
    MyOpelSensorDescription(
        key="fuel_autonomy_km",
        data_key="fuel_autonomy_km",
        name="Autonomia carburante",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:road-variant",
    ),
    # ── Last trip ────────────────────────────────────────────────────────────
    MyOpelSensorDescription(
        key="last_trip_distance_km",
        data_key="last_trip_distance_km",
        name="Ultimo viaggio – Distanza",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:map-marker-distance",
    ),
    MyOpelSensorDescription(
        key="last_trip_duration_min",
        data_key="last_trip_duration_min",
        name="Ultimo viaggio – Durata",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
    ),
    MyOpelSensorDescription(
        key="last_trip_fuel_consumption_l",
        data_key="last_trip_fuel_consumption_l",
        name="Ultimo viaggio – Carburante consumato",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.VOLUME,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fuel",
    ),
    MyOpelSensorDescription(
        key="last_trip_fuel_consumption_kmpl",
        data_key="last_trip_fuel_consumption_kmpl",
        name="Ultimo viaggio – Consumo medio",
        native_unit_of_measurement="km/L",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-line",
    ),
    MyOpelSensorDescription(
        key="last_trip_price_fuel",
        data_key="last_trip_price_fuel",
        name="Prezzo carburante",
        native_unit_of_measurement="€/L",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:currency-eur",
    ),
    MyOpelSensorDescription(
        key="last_trip_start",
        data_key="last_trip_start",
        name="Ultimo viaggio – Inizio",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-start",
    ),
    MyOpelSensorDescription(
        key="last_trip_end",
        data_key="last_trip_end",
        name="Ultimo viaggio – Fine",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-end",
    ),
    MyOpelSensorDescription(
        key="last_trip_avg_speed",
        data_key="last_trip_avg_speed",
        name="Ultimo viaggio – Velocità media",
        native_unit_of_measurement="km/h",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
    ),
    MyOpelSensorDescription(
        key="last_trip_cost",
        data_key="last_trip_cost",
        name="Ultimo viaggio – Costo stimato",
        native_unit_of_measurement="€",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:currency-eur",
    ),
    MyOpelSensorDescription(
        key="last_trip_alert_count",
        data_key="last_trip_alert_count",
        name="Ultimo viaggio – Alert",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:alert-circle-outline",
    ),
    MyOpelSensorDescription(
        key="last_trip_alert_codes",
        data_key="last_trip_alert_codes",
        name="Ultimo viaggio – Alert attivi",
        icon="mdi:alert-box-outline",
    ),
    # ── Maintenance ──────────────────────────────────────────────────────────
    MyOpelSensorDescription(
        key="days_until_maintenance",
        data_key="days_until_maintenance",
        name="Giorni alla manutenzione",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:wrench-clock",
    ),
    MyOpelSensorDescription(
        key="distance_to_maintenance_km",
        data_key="distance_to_maintenance_km",
        name="Km alla manutenzione",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:wrench",
    ),
    # ── All-time aggregates ──────────────────────────────────────────────────
    MyOpelSensorDescription(
        key="total_trips",
        data_key="total_trips",
        name="Totale – Viaggi",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
    ),
    MyOpelSensorDescription(
        key="total_distance_km",
        data_key="total_distance_km",
        name="Totale – Distanza",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:map-marker-path",
    ),
    MyOpelSensorDescription(
        key="total_travel_time_h",
        data_key="total_travel_time_h",
        name="Totale – Ore di guida",
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:steering",
    ),
    MyOpelSensorDescription(
        key="total_fuel_l",
        data_key="total_fuel_l",
        name="Totale – Carburante consumato",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.VOLUME,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:fuel",
    ),
    MyOpelSensorDescription(
        key="total_fuel_kmpl",
        data_key="total_fuel_kmpl",
        name="Totale – Consumo medio",
        native_unit_of_measurement="km/L",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-line",
    ),
    MyOpelSensorDescription(
        key="total_avg_speed",
        data_key="total_avg_speed",
        name="Totale – Velocità media",
        native_unit_of_measurement="km/h",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
    ),
    MyOpelSensorDescription(
        key="total_cost_eur",
        data_key="total_cost_eur",
        name="Totale – Costo stimato",
        native_unit_of_measurement="€",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:cash",
    ),
    MyOpelSensorDescription(
        key="total_alert_count",
        data_key="total_alert_count",
        name="Totale – Alert",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:alert-circle",
    ),
    MyOpelSensorDescription(
        key="all_alert_codes_summary",
        data_key="all_alert_codes_summary",
        name="Totale – Riepilogo codici alert",
        icon="mdi:alert-box",
    ),
    # ── Monthly aggregates (mese corrente) ──────────────────────────────────
    MyOpelSensorDescription(
        key="month_trip_count",
        data_key="month_trip_count",
        name="Mese corrente – Viaggi",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-month",
    ),
    MyOpelSensorDescription(
        key="month_distance_km",
        data_key="month_distance_km",
        name="Mese corrente – Distanza",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:map-marker-distance",
    ),
    MyOpelSensorDescription(
        key="month_duration_min",
        data_key="month_duration_min",
        name="Mese corrente – Durata guida",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
    ),
    MyOpelSensorDescription(
        key="month_fuel_l",
        data_key="month_fuel_l",
        name="Mese corrente – Carburante totale",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.VOLUME,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fuel",
    ),
    MyOpelSensorDescription(
        key="month_fuel_kmpl",
        data_key="month_fuel_kmpl",
        name="Mese corrente – Consumo medio",
        native_unit_of_measurement="km/L",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-line",
    ),
    MyOpelSensorDescription(
        key="month_avg_speed",
        data_key="month_avg_speed",
        name="Mese corrente – Velocità media",
        native_unit_of_measurement="km/h",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
    ),
    MyOpelSensorDescription(
        key="month_cost_eur",
        data_key="month_cost_eur",
        name="Mese corrente – Costo stimato",
        native_unit_of_measurement="€",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cash",
    ),
    MyOpelSensorDescription(
        key="month_alert_count",
        data_key="month_alert_count",
        name="Mese corrente – Alert",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:alert-circle-outline",
    ),
    MyOpelSensorDescription(
        key="month_alert_codes_summary",
        data_key="month_alert_codes_summary",
        name="Mese corrente – Codici alert",
        icon="mdi:alert-box-outline",
    ),
    # ── Dall'ultimo rifornimento ─────────────────────────────────────────────
    MyOpelSensorDescription(
        key="refuel_trip_count",
        data_key="refuel_trip_count",
        name="Rifornimento – Viaggi",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gas-station",
    ),
    MyOpelSensorDescription(
        key="refuel_distance_km",
        data_key="refuel_distance_km",
        name="Rifornimento – Distanza",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:map-marker-distance",
    ),
    MyOpelSensorDescription(
        key="refuel_duration_h",
        data_key="refuel_duration_h",
        name="Rifornimento – Ore di guida",
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
    ),
    MyOpelSensorDescription(
        key="refuel_fuel_l",
        data_key="refuel_fuel_l",
        name="Rifornimento – Carburante consumato",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.VOLUME,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fuel",
    ),
    MyOpelSensorDescription(
        key="refuel_kmpl",
        data_key="refuel_kmpl",
        name="Rifornimento – Consumo medio",
        native_unit_of_measurement="km/L",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-line",
    ),
    MyOpelSensorDescription(
        key="refuel_cost_eur",
        data_key="refuel_cost_eur",
        name="Rifornimento – Costo stimato",
        native_unit_of_measurement="€",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cash",
    ),
    MyOpelSensorDescription(
        key="refuel_avg_speed",
        data_key="refuel_avg_speed",
        name="Rifornimento – Velocità media",
        native_unit_of_measurement="km/h",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
    ),
    MyOpelSensorDescription(
        key="refuel_date",
        data_key="refuel_date",
        name="Rifornimento – Data ultimo rifornimento",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:gas-station-outline",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MyOpel sensors and the alert binary sensor."""
    coordinator: MyOpelCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    vin = coordinator.data.get("vin", "unknown")

    entities: list = [
        MyOpelSensor(coordinator, description, vin, entry)
        for description in SENSOR_DESCRIPTIONS
    ]
    entities.append(MyOpelAlertActiveBinarySensor(coordinator, vin, entry.entry_id))
    async_add_entities(entities)


class MyOpelSensor(CoordinatorEntity[MyOpelCoordinator], SensorEntity):
    """Representation of a MyOpel sensor."""

    entity_description: MyOpelSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MyOpelCoordinator,
        description: MyOpelSensorDescription,
        vin: str,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._vin = vin
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, vin)},
            name=f"Opel ({vin[-6:]})",
            manufacturer="Opel",
            model="MyOpel Export",
            serial_number=vin,
        )

    @property
    def available(self) -> bool:
        """Unavailable until at least one .myop file has been parsed."""
        return super().available and bool(self.coordinator.data)

    @property
    def native_value(self) -> Any:
        """Return current sensor value."""
        value = self.coordinator.data.get(self.entity_description.data_key)

        # Convert ISO timestamp strings to datetime objects for timestamp sensors.
        # NOTE: Stellantis/.myop files mark timestamps with "Z" (UTC) but the value is always
        # in the server's local wall-clock time — even in summer. The server does NOT adjust
        # for DST. The offset is user-configurable: 1 = CET (winter), 2 = CEST (summer).
        if (
            self.entity_description.device_class == SensorDeviceClass.TIMESTAMP
            and isinstance(value, str)
        ):
            from datetime import datetime, timezone, timedelta
            try:
                offset_hours = self._entry.options.get(
                    CONF_TIME_OFFSET,
                    self._entry.data.get(CONF_TIME_OFFSET, DEFAULT_TIME_OFFSET),
                )
                naive = datetime.fromisoformat(value.rstrip("Z"))
                tz = timezone(timedelta(hours=int(offset_hours)))
                return naive.replace(tzinfo=tz)
            except (ValueError, AttributeError):
                return None

        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose full VIN so the Lovelace card can build image proxy URLs."""
        return {"vin": self._vin}


class MyOpelAlertActiveBinarySensor(CoordinatorEntity[MyOpelCoordinator], BinarySensorEntity):
    """Binary sensor: ON if the last trip had any active alerts."""

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
        return bool(self.coordinator.data.get("last_trip_has_alerts", False))

    @property
    def icon(self) -> str:
        return "mdi:alert-circle" if self.is_on else "mdi:alert-circle-outline"
