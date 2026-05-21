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
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_OBD_ENABLED_PIDS, DOMAIN
from . import MyOpelCoordinator
from .coordinator_obd import MyOpelObdCoordinator


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
        state_class=None,
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
    MyOpelSensorDescription(
        key="last_trip_unack_alert_count",
        data_key="last_trip_unack_alert_count",
        name="Ultimo viaggio – Alert non letti",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:bell-alert-outline",
    ),
    MyOpelSensorDescription(
        key="last_trip_unack_alert_codes",
        data_key="last_trip_unack_alert_codes",
        name="Ultimo viaggio – Alert non letti (codici)",
        icon="mdi:bell-alert",
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
        state_class=None,
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
    MyOpelSensorDescription(
        key="month_unack_alert_count",
        data_key="month_unack_alert_count",
        name="Mese corrente – Alert non letti",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:bell-alert-outline",
    ),
    # ── Today aggregates (oggi) ─────────────────────────────────────────────
    MyOpelSensorDescription(
        key="today_trip_count",
        data_key="today_trip_count",
        name="Oggi – Viaggi",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-today",
    ),
    MyOpelSensorDescription(
        key="today_distance_km",
        data_key="today_distance_km",
        name="Oggi – Distanza",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:map-marker-distance",
    ),
    MyOpelSensorDescription(
        key="today_duration_min",
        data_key="today_duration_min",
        name="Oggi – Durata guida",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
    ),
    MyOpelSensorDescription(
        key="today_fuel_l",
        data_key="today_fuel_l",
        name="Oggi – Carburante totale",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.VOLUME,
        state_class=None,
        icon="mdi:fuel",
    ),
    MyOpelSensorDescription(
        key="today_fuel_kmpl",
        data_key="today_fuel_kmpl",
        name="Oggi – Consumo medio",
        native_unit_of_measurement="km/L",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-line",
    ),
    MyOpelSensorDescription(
        key="today_avg_speed",
        data_key="today_avg_speed",
        name="Oggi – Velocità media",
        native_unit_of_measurement="km/h",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
    ),
    MyOpelSensorDescription(
        key="today_cost_eur",
        data_key="today_cost_eur",
        name="Oggi – Costo stimato",
        native_unit_of_measurement="€",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cash",
    ),
    MyOpelSensorDescription(
        key="today_alert_count",
        data_key="today_alert_count",
        name="Oggi – Alert",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:alert-circle-outline",
    ),
    MyOpelSensorDescription(
        key="today_alert_codes_summary",
        data_key="today_alert_codes_summary",
        name="Oggi – Codici alert",
        icon="mdi:alert-box-outline",
    ),
    MyOpelSensorDescription(
        key="today_unack_alert_count",
        data_key="today_unack_alert_count",
        name="Oggi – Alert non letti",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:bell-alert-outline",
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
        state_class=None,
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


OBD_SENSOR_DESCRIPTIONS: tuple[MyOpelSensorDescription, ...] = (
    MyOpelSensorDescription(
        key="obd_trip_distance_km",
        data_key="obd_trip_distance_km",
        name="OBD – Distanza viaggio",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:map-marker-distance",
    ),
    MyOpelSensorDescription(
        key="obd_trip_duration_min",
        data_key="obd_trip_duration_min",
        name="OBD – Durata viaggio",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
    ),
    MyOpelSensorDescription(
        key="obd_trip_avg_speed_kmh",
        data_key="obd_trip_avg_speed_kmh",
        name="OBD – Velocità media GPS",
        native_unit_of_measurement="km/h",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
    ),
    MyOpelSensorDescription(
        key="obd_trip_max_speed_kmh",
        data_key="obd_trip_max_speed_kmh",
        name="OBD – Velocità massima GPS",
        native_unit_of_measurement="km/h",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
    ),
    MyOpelSensorDescription(
        key="obd_trip_avg_rpm",
        data_key="obd_trip_avg_rpm",
        name="OBD – Giri motore medi",
        native_unit_of_measurement="rpm",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:engine",
    ),
    MyOpelSensorDescription(
        key="obd_trip_max_rpm",
        data_key="obd_trip_max_rpm",
        name="OBD – Giri motore massimi",
        native_unit_of_measurement="rpm",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:engine",
    ),
    MyOpelSensorDescription(
        key="obd_trip_coolant_temp_max_c",
        data_key="obd_trip_coolant_temp_max_c",
        name="OBD – Temp. raffreddamento max",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
    ),
    MyOpelSensorDescription(
        key="obd_trip_oil_temp_max_c",
        data_key="obd_trip_oil_temp_max_c",
        name="OBD – Temperatura olio max",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:oil-temperature",
    ),
    MyOpelSensorDescription(
        key="obd_trip_fuel_consumed_l",
        data_key="obd_trip_fuel_consumed_l",
        name="OBD – Carburante consumato",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.VOLUME,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fuel",
    ),
    MyOpelSensorDescription(
        key="obd_trip_consumption_l100km",
        data_key="obd_trip_consumption_l100km",
        name="OBD – Consumo medio",
        native_unit_of_measurement="L/100km",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
    ),
    MyOpelSensorDescription(
        key="obd_trip_odometer_km",
        data_key="obd_trip_odometer_km",
        name="OBD – Chilometraggio ECU",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
    ),
    MyOpelSensorDescription(
        key="obd_trip_air_temp_c",
        data_key="obd_trip_air_temp_c",
        name="OBD – Temperatura aria esterna",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
    ),
    MyOpelSensorDescription(
        key="obd_trip_start",
        data_key="obd_trip_start",
        name="OBD – Inizio viaggio",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-start",
    ),
    # ── DPF / emissions ──────────────────────────────────────────────────────
    MyOpelSensorDescription(
        key="obd_trip_dpf_soot_pct",
        data_key="obd_trip_dpf_soot_pct",
        name="OBD – DPF intasamento",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:air-filter",
    ),
    MyOpelSensorDescription(
        key="obd_trip_dpf_regen_active",
        data_key="obd_trip_dpf_regen_active",
        name="OBD – DPF rigenerazione attiva",
        icon="mdi:fire",
    ),
    MyOpelSensorDescription(
        key="obd_trip_dpf_regen_capability",
        data_key="obd_trip_dpf_regen_capability",
        name="OBD – Capacità rigenerazione DPF",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-bar",
    ),
    MyOpelSensorDescription(
        key="obd_trip_dpf_regen_capability_st",
        data_key="obd_trip_dpf_regen_capability_st",
        name="OBD – Cap rigenerazione breve",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-bar",
    ),
    MyOpelSensorDescription(
        key="obd_trip_dpf_since_regen_km",
        data_key="obd_trip_dpf_since_regen_km",
        name="OBD – Distanza ultima regen",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fire-off",
    ),
    MyOpelSensorDescription(
        key="obd_trip_dpf_avg_regen_km",
        data_key="obd_trip_dpf_avg_regen_km",
        name="OBD – Media km regen DPF",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-timeline-variant",
    ),
    MyOpelSensorDescription(
        key="obd_trip_dpf_replace_km",
        data_key="obd_trip_dpf_replace_km",
        name="OBD – Vita residua DPF",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:filter-remove",
    ),
    MyOpelSensorDescription(
        key="obd_trip_adblue_vol_l",
        data_key="obd_trip_adblue_vol_l",
        name="OBD – AdBlue nel serbatoio",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.VOLUME,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water",
    ),
    MyOpelSensorDescription(
        key="obd_trip_adblue_range_km",
        data_key="obd_trip_adblue_range_km",
        name="OBD – Autonomia AdBlue",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
    ),
    MyOpelSensorDescription(
        key="obd_trip_exhaust_after_cat_c",
        data_key="obd_trip_exhaust_after_cat_c",
        name="OBD – Temp. gas scarico max",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-high",
    ),
    # ── Diagnostics ──────────────────────────────────────────────────────────
    MyOpelSensorDescription(
        key="obd_trip_battery_startup_v",
        data_key="obd_trip_battery_startup_v",
        name="OBD – Tensione avviamento batteria",
        native_unit_of_measurement="V",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-low",
    ),
    MyOpelSensorDescription(
        key="obd_trip_oil_dilution_pct",
        data_key="obd_trip_oil_dilution_pct",
        name="OBD – Diluizione olio",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:oil",
    ),
    MyOpelSensorDescription(
        key="obd_trip_ss_state",
        data_key="obd_trip_ss_state",
        name="OBD – Stato Stop-Start",
        icon="mdi:engine-off",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MyOpel sensors and the alert binary sensor."""
    coordinator: MyOpelCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    vin = coordinator.data.get("vin", "unknown") if coordinator.data else "unknown"

    entities: list = [
        MyOpelSensor(coordinator, description, vin, entry)
        for description in SENSOR_DESCRIPTIONS
    ]
    entities.append(MyOpelAlertActiveBinarySensor(coordinator, vin, entry.entry_id))

    obd_coordinator: MyOpelObdCoordinator | None = (
        hass.data[DOMAIN][entry.entry_id].get("obd_coordinator")
    )
    if obd_coordinator is not None:
        entities.extend(
            MyOpelObdSensor(obd_coordinator, description, vin, entry)
            for description in OBD_SENSOR_DESCRIPTIONS
        )
        enabled_pids = entry.options.get(CONF_OBD_ENABLED_PIDS, []) or []
        catalog = obd_coordinator.discovered_pids
        for slug in enabled_pids:
            meta = catalog.get(slug)
            if meta is None:
                continue
            entities.append(
                MyOpelObdExtraPidSensor(obd_coordinator, slug, meta, vin, entry)
            )

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

    _ALERT_ATTR_SCOPE: dict[str, str] = {
        "last_trip_alert_codes": "last_trip",
        "last_trip_alert_count": "last_trip",
        "last_trip_unack_alert_codes": "last_trip",
        "last_trip_unack_alert_count": "last_trip",
        "month_alert_count": "month",
        "month_alert_codes_summary": "month",
        "month_unack_alert_count": "month",
        "total_alert_count": "total",
        "all_alert_codes_summary": "total",
        "today_alert_count": "today",
        "today_alert_codes_summary": "today",
        "today_unack_alert_count": "today",
    }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose VIN plus, on alert-related sensors, raw acked/unacked code lists."""
        attrs: dict[str, Any] = {"vin": self._vin}
        data = self.coordinator.data or {}
        key = self.entity_description.data_key
        scope = self._ALERT_ATTR_SCOPE.get(key)
        if scope is None:
            return attrs
        attrs["entry_id"] = self._entry.entry_id
        attrs["scope"] = scope
        if scope == "last_trip":
            attrs["trip_id"] = data.get("last_trip_id")
            attrs["all_codes"] = data.get("last_trip_alerts_raw") or []
            attrs["unacknowledged_codes"] = data.get("last_trip_unack_alerts_raw") or []
            attrs["acknowledged_codes"] = data.get("last_trip_acked_alerts_raw") or []
            attrs["acknowledged_labels"] = data.get("last_trip_acked_alert_codes")
            attrs["code_labels"] = data.get("last_trip_alert_labels") or {}
        else:
            attrs["all_codes"] = data.get(f"{scope}_alerts_raw") or []
            attrs["unacknowledged_codes"] = data.get(f"{scope}_unack_alerts_raw") or []
            attrs["acknowledged_codes"] = data.get(f"{scope}_acked_alerts_raw") or []
            attrs["acknowledged_labels"] = data.get(f"{scope}_acked_alert_codes")
            attrs["code_labels"] = data.get(f"{scope}_alert_labels") or {}
            attrs["code_to_trips"] = data.get(f"{scope}_code_to_trips") or {}
        return attrs


class MyOpelAlertActiveBinarySensor(CoordinatorEntity[MyOpelCoordinator], BinarySensorEntity):
    """Binary sensor: ON when the last trip has unacknowledged alerts.

    Acknowledged alerts remain visible via the `acknowledged_codes` attribute
    (and the Lovelace card) but no longer trigger the "problem" state.
    """

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
        # Off but we still have acked alerts → muted icon so the user sees
        # there's history to review.
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


_OBD_LABELED: dict[str, tuple[str, str]] = {
    # No entries currently — obd_trip_dpf_regen_active is a multi-value
    # status code (0=off, 1=pre-cond, 2=active, 4=inhibited, 6=post-regen…)
    # so showing the raw number is more informative than a Sì/No label.
}


def _as_label(value: Any, labels: tuple[str, str]) -> str | None:
    """Render a 0/1-style OBD value as one of two labels."""
    if value is None:
        return None
    try:
        return labels[0] if int(float(value)) == 0 else labels[1]
    except (TypeError, ValueError):
        return None


class MyOpelObdSensor(CoordinatorEntity[MyOpelObdCoordinator], SensorEntity):
    """Sensor sourced from a CarScanner OBD CSV export."""

    entity_description: MyOpelSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MyOpelObdCoordinator,
        description: MyOpelSensorDescription,
        vin: str,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._vin = vin
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_obd_{description.key}"
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
    def native_value(self) -> Any:
        value = self.coordinator.data.get(self.entity_description.data_key)
        if (
            self.entity_description.device_class == SensorDeviceClass.TIMESTAMP
            and isinstance(value, str)
        ):
            from datetime import datetime, timezone
            try:
                return datetime.fromisoformat(value.rstrip("Z")).replace(tzinfo=timezone.utc)
            except (ValueError, AttributeError):
                return None
        # Boolean-like OBD PIDs: expose a label instead of the raw 0/1 float.
        # Stop&Start switch is inverted (raw 0 = system enabled).
        labels = _OBD_LABELED.get(self.entity_description.data_key)
        if labels is not None:
            return _as_label(value, labels)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "vin": self._vin,
            "obd_filename": (self.coordinator.data or {}).get("obd_filename"),
        }


class MyOpelObdExtraPidSensor(CoordinatorEntity[MyOpelObdCoordinator], SensorEntity):
    """Generic sensor for an arbitrary OBD PID enabled from the options flow."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MyOpelObdCoordinator,
        slug: str,
        meta: dict[str, Any],
        vin: str,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._slug = slug
        self._vin = vin
        self._entry = entry
        self._name = meta.get("name", slug)
        self._kind = meta.get("kind", "number")
        self._attr_name = f"OBD – {self._name}"
        self._attr_unique_id = f"{entry.entry_id}_obd_pid_{slug}"
        unit = meta.get("unit") or None
        # Boolean/discrete PIDs have no meaningful HA unit or state class.
        self._attr_native_unit_of_measurement = None if self._kind in ("bool", "discrete") else unit
        self._attr_icon = {
            "bool": "mdi:toggle-switch",
            "discrete": "mdi:counter",
        }.get(self._kind, "mdi:gauge")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, vin)},
            name=f"Opel ({vin[-6:]})",
            manufacturer="Opel",
            model="MyOpel Export",
            serial_number=vin,
        )

    def _stats(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        pid_values = data.get("obd_pid_values") or {}
        entry = pid_values.get(self._slug)
        return entry if isinstance(entry, dict) else None

    @property
    def available(self) -> bool:
        return super().available and self._stats() is not None

    @property
    def native_value(self) -> Any:
        stats = self._stats()
        if not stats:
            return None
        if self._kind == "bool":
            return _as_label(stats.get("last"), ("No", "Sì"))
        if self._kind == "discrete":
            # Mode = most frequently occurring value across the trip.
            # More meaningful than last/max for discrete states (gear, selector…).
            mode = stats.get("mode")
            return int(mode) if mode is not None else None
        return stats.get("last")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        stats = self._stats() or {}
        return {
            "vin": self._vin,
            "pid_name": self._name,
            "kind": self._kind,
            "last": stats.get("last"),
            "first": stats.get("first"),
            "min": stats.get("min"),
            "max": stats.get("max"),
            "mean": stats.get("mean"),
            "mode": stats.get("mode"),
            "samples": stats.get("samples"),
            "first_seen_s": stats.get("first_seen_s"),
            "last_seen_s": stats.get("last_seen_s"),
            "age_from_trip_end_s": stats.get("age_from_trip_end_s"),
            "coverage_pct": stats.get("coverage_pct"),
            "sample_rate_hz": stats.get("sample_rate_hz"),
            "is_stale": stats.get("is_stale"),
            "obd_filename": (self.coordinator.data or {}).get("obd_filename"),
        }
