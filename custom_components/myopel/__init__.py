"""MyOpel integration for Home Assistant."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.persistent_notification import async_create as pn_create
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .ack_store import AlertAckStore
from .alerts import ALERT_CODES
from .const import (
    ATTR_ALERT_CODE, ATTR_ENTRY_ID, ATTR_TRIP_ID,
    CONF_FILE_PATH, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN,
    SERVICE_ACK_ALERT, SERVICE_ACK_ALL_ALERTS, SERVICE_RESET_ACKS, SERVICE_UNACK_ALERT,
)
from .const import (
    CONF_IMAP_SERVER, CONF_IMAP_PORT, CONF_IMAP_USERNAME, CONF_IMAP_PASSWORD,
    CONF_IMAP_FOLDER, CONF_IMAP_SENDER, CONF_IMAP_INTERVAL, CONF_IMAP_DISABLED,
)
from .const import (
    CONF_MIN_TRIP_DISTANCE, CONF_MIN_TRIP_DISTANCE_ENABLED, DEFAULT_MIN_TRIP_DISTANCE,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = ["sensor"]


def _read_manifest_version() -> str:
    """Read the integration version from manifest.json (single source of truth)."""
    manifest_path = Path(__file__).with_name("manifest.json")
    try:
        with manifest_path.open("r", encoding="utf-8") as fh:
            return json.load(fh).get("version", "0.0.0")
    except (OSError, json.JSONDecodeError):
        return "0.0.0"


INTEGRATION_VERSION = _read_manifest_version()


def _alert_label(code: int) -> str:
    """Return a human-readable alert name for the given Opel alert code."""
    return ALERT_CODES.get(code, f"Codice {code}")
_CARD_JS_URL = f"/myopel/{INTEGRATION_VERSION}/myopel-card.js"


# ── Watchdog file handler ─────────────────────────────────────────────────────

class _TripFileHandler:
    """Watchdog event handler that triggers a coordinator refresh on file changes."""

    def __init__(self, coordinator: "MyOpelCoordinator") -> None:
        self._coordinator = coordinator

    def _trigger(self) -> None:
        asyncio.run_coroutine_threadsafe(
            self._coordinator.async_request_refresh(),
            self._coordinator.hass.loop,
        )

    @staticmethod
    def _is_relevant(path: str) -> bool:
        name = os.path.basename(path)
        return name in ("trips.json", "trips.export") or name.endswith(".myop")

    def dispatch(self, path: str) -> None:
        if self._is_relevant(path):
            _LOGGER.debug("MyOpel: rilevata modifica file %s, aggiorno dati", path)
            self._trigger()


def _make_watchdog_handler(coordinator: "MyOpelCoordinator"):
    """Build a watchdog FileSystemEventHandler wired to the coordinator."""
    try:
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        return None

    trip_handler = _TripFileHandler(coordinator)

    class _Handler(FileSystemEventHandler):
        def on_modified(self, event):
            if not event.is_directory:
                trip_handler.dispatch(event.src_path)

        def on_created(self, event):
            if not event.is_directory:
                trip_handler.dispatch(event.src_path)

        def on_moved(self, event):
            # Atomic writes (iOS Shortcuts, many editors) rename a temp file
            # to the final name — fires on_moved, not on_modified/on_created
            if not event.is_directory:
                trip_handler.dispatch(event.dest_path)

    return _Handler()


# ── Setup / Teardown ──────────────────────────────────────────────────────────

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register Lovelace card JS and visual3D proxy endpoint."""
    js_file = os.path.join(os.path.dirname(__file__), "frontend", "myopel-card.js")
    registered = hass.data.get("frontend_extra_module_url", {})
    urls = getattr(registered, "urls", set())
    if _CARD_JS_URL not in urls:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(_CARD_JS_URL, js_file, False)]
        )
        add_extra_js_url(hass, _CARD_JS_URL)
        _LOGGER.debug("MyOpel: card JS registrata su %s", _CARD_JS_URL)

    return True


class _NoFileYet(Exception):
    """Raised when the folder exists but contains no .myop or trips.json — not a fatal error."""


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MyOpel from a config entry."""
    # options can override data for file_path (hot-reload on path change)
    file_path = entry.options.get(CONF_FILE_PATH, entry.data[CONF_FILE_PATH])
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    min_dist_enabled = entry.options.get(CONF_MIN_TRIP_DISTANCE_ENABLED, False)
    min_dist = entry.options.get(CONF_MIN_TRIP_DISTANCE, DEFAULT_MIN_TRIP_DISTANCE) if min_dist_enabled else 0.0

    ack_store = AlertAckStore(hass, entry.entry_id)
    await ack_store.async_load()

    coordinator = MyOpelCoordinator(hass, file_path, scan_interval, min_dist, ack_store=ack_store)

    # ── Watchdog observer ────────────────────────────────────────────────────
    observer = None
    try:
        from watchdog.observers import Observer

        folder = Path(file_path)
        folder.mkdir(parents=True, exist_ok=True)

        handler = _make_watchdog_handler(coordinator)
        if handler is not None:
            observer = Observer()
            observer.schedule(handler, str(folder), recursive=False)
            observer.start()
            _LOGGER.debug("MyOpel: watchdog avviato su %s", folder)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("MyOpel: watchdog non disponibile, uso solo polling (%s)", exc)
        observer = None

    # ── IMAP fetcher ─────────────────────────────────────────────────────────
    imap_fetcher = None
    imap_disabled = entry.options.get(CONF_IMAP_DISABLED, False)
    # IMAP settings: options take precedence over original data (allows hot-update)
    imap_server = entry.options.get(CONF_IMAP_SERVER, entry.data.get(CONF_IMAP_SERVER, ""))
    if not imap_disabled and imap_server:
        from .imap_fetcher import MyOpelImapFetcher

        def _get(key, default=None):
            return entry.options.get(key, entry.data.get(key, default))

        from .const import DEFAULT_IMAP_PORT, DEFAULT_IMAP_FOLDER, DEFAULT_IMAP_INTERVAL
        imap_config = {
            CONF_IMAP_SERVER: imap_server,
            CONF_IMAP_PORT: _get(CONF_IMAP_PORT, DEFAULT_IMAP_PORT),
            CONF_IMAP_USERNAME: _get(CONF_IMAP_USERNAME, ""),
            CONF_IMAP_PASSWORD: _get(CONF_IMAP_PASSWORD, ""),
            CONF_IMAP_FOLDER: _get(CONF_IMAP_FOLDER, DEFAULT_IMAP_FOLDER),
            CONF_IMAP_SENDER: _get(CONF_IMAP_SENDER, ""),
            CONF_IMAP_INTERVAL: _get(CONF_IMAP_INTERVAL, DEFAULT_IMAP_INTERVAL),
        }
        imap_fetcher = MyOpelImapFetcher(
            hass, imap_config, file_path, coordinator,
            on_no_idle=lambda: pn_create(
                hass,
                title="MyOpel – IMAP IDLE non supportato",
                message=(
                    f"Il server IMAP **{imap_server}** non supporta "
                    "IMAP IDLE (RFC 2177).\n\n"
                    "L'integrazione continuerà a controllare la posta ogni "
                    f"{imap_config.get(CONF_IMAP_INTERVAL, 300)} secondi tramite polling.\n\n"
                    "Per ricevere aggiornamenti in tempo reale considera di usare Gmail, "
                    "iCloud o un altro provider che supporta IDLE."
                ),
                notification_id="myopel_imap_no_idle",
            ),
        )
        await imap_fetcher.async_start()

    # First refresh: tolerates empty folder (returns {}) so setup never fails
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "imap_fetcher": imap_fetcher,
        "observer": observer,
        "ack_store": ack_store,
    }

    # If the entry was created before we had a real VIN (folder was empty),
    # register a one-shot listener that fixes title and unique_id on first real data.
    if entry.unique_id is None or "unknown" in entry.title.lower():
        _register_vin_updater(hass, entry, coordinator)

    _async_register_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


# ── Services ─────────────────────────────────────────────────────────────────

_ACK_SERVICE_SCHEMA = vol.Schema({
    vol.Required(ATTR_ALERT_CODE): vol.All(vol.Coerce(int), vol.Range(min=0, max=999)),
    vol.Optional(ATTR_TRIP_ID): vol.Any(None, vol.Coerce(int)),
    vol.Optional(ATTR_ENTRY_ID): cv.string,
})

_ACK_ALL_SERVICE_SCHEMA = vol.Schema({
    vol.Optional(ATTR_ENTRY_ID): cv.string,
    vol.Optional(ATTR_TRIP_ID): vol.Any(None, vol.Coerce(int)),
})

_RESET_SERVICE_SCHEMA = vol.Schema({
    vol.Optional(ATTR_ENTRY_ID): cv.string,
})


def _iter_entries(hass: HomeAssistant, entry_id: str | None):
    """Yield the (entry_id, entry_data) pairs targeted by a service call."""
    all_entries: dict = hass.data.get(DOMAIN, {})
    if entry_id:
        if entry_id in all_entries:
            yield entry_id, all_entries[entry_id]
        return
    yield from all_entries.items()


def _async_register_services(hass: HomeAssistant) -> None:
    """Register MyOpel services idempotently."""
    if hass.services.has_service(DOMAIN, SERVICE_ACK_ALERT):
        return

    async def _handle_ack(call: ServiceCall) -> None:
        code = int(call.data[ATTR_ALERT_CODE])
        trip_id = call.data.get(ATTR_TRIP_ID)
        entry_id = call.data.get(ATTR_ENTRY_ID)
        for eid, ed in _iter_entries(hass, entry_id):
            ack_store: AlertAckStore | None = ed.get("ack_store")
            coordinator: MyOpelCoordinator | None = ed.get("coordinator")
            if ack_store is None:
                continue
            tid = trip_id if trip_id is not None else (
                coordinator.data.get("last_trip_id") if coordinator and coordinator.data else None
            )
            added = await ack_store.async_ack(tid, code)
            if added and coordinator is not None:
                await coordinator.async_request_refresh()
            _LOGGER.debug("%s: ack code=%s trip=%s entry=%s (new=%s)",
                          DOMAIN, code, tid, eid, added)

    async def _handle_ack_all(call: ServiceCall) -> None:
        entry_id = call.data.get(ATTR_ENTRY_ID)
        trip_id_override = call.data.get(ATTR_TRIP_ID)
        for eid, ed in _iter_entries(hass, entry_id):
            ack_store: AlertAckStore | None = ed.get("ack_store")
            coordinator: MyOpelCoordinator | None = ed.get("coordinator")
            if ack_store is None or coordinator is None or not coordinator.data:
                continue
            tid = trip_id_override if trip_id_override is not None else coordinator.data.get("last_trip_id")
            codes = coordinator.data.get("last_trip_alerts_raw") or []
            if not codes:
                continue
            added = await ack_store.async_ack_many(tid, codes)
            if added:
                await coordinator.async_request_refresh()
            _LOGGER.debug("%s: ack_all trip=%s entry=%s added=%d", DOMAIN, tid, eid, added)

    async def _handle_reset(call: ServiceCall) -> None:
        entry_id = call.data.get(ATTR_ENTRY_ID)
        for eid, ed in _iter_entries(hass, entry_id):
            ack_store: AlertAckStore | None = ed.get("ack_store")
            coordinator: MyOpelCoordinator | None = ed.get("coordinator")
            if ack_store is None:
                continue
            await ack_store.async_reset()
            if coordinator is not None:
                await coordinator.async_request_refresh()
            _LOGGER.debug("%s: reset ack per entry=%s", DOMAIN, eid)

    async def _handle_unack(call: ServiceCall) -> None:
        code = int(call.data[ATTR_ALERT_CODE])
        trip_id = call.data.get(ATTR_TRIP_ID)
        entry_id = call.data.get(ATTR_ENTRY_ID)
        for eid, ed in _iter_entries(hass, entry_id):
            ack_store: AlertAckStore | None = ed.get("ack_store")
            coordinator: MyOpelCoordinator | None = ed.get("coordinator")
            if ack_store is None:
                continue
            tid = trip_id if trip_id is not None else (
                coordinator.data.get("last_trip_id") if coordinator and coordinator.data else None
            )
            removed = await ack_store.async_unack(tid, code)
            if removed and coordinator is not None:
                await coordinator.async_request_refresh()
            _LOGGER.debug("%s: unack code=%s trip=%s entry=%s (removed=%s)",
                          DOMAIN, code, tid, eid, removed)

    hass.services.async_register(DOMAIN, SERVICE_ACK_ALERT, _handle_ack, schema=_ACK_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_ACK_ALL_ALERTS, _handle_ack_all, schema=_ACK_ALL_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_UNACK_ALERT, _handle_unack, schema=_ACK_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RESET_ACKS, _handle_reset, schema=_RESET_SERVICE_SCHEMA)


def _register_vin_updater(hass: HomeAssistant, entry: ConfigEntry, coordinator) -> None:
    """Listen for coordinator updates; when VIN is known, update entry title/unique_id."""

    @callback
    def _on_update() -> None:
        vin = coordinator.data.get("vin") if coordinator.data else None
        if not vin or vin == "unknown":
            return
        vin_short = vin[-6:]
        hass.config_entries.async_update_entry(
            entry,
            title=f"Opel ({vin_short})",
            unique_id=vin,
        )
        _LOGGER.info("MyOpel: entry aggiornata con VIN reale %s", vin)
        unsub()

    unsub = coordinator.async_add_listener(_on_update)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})

    imap_fetcher = entry_data.get("imap_fetcher")
    if imap_fetcher:
        imap_fetcher.async_stop()

    observer = entry_data.get("observer")
    if observer and observer.is_alive():
        observer.stop()
        await hass.async_add_executor_job(observer.join)
        _LOGGER.debug("MyOpel: watchdog fermato")

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


# ── Coordinator ───────────────────────────────────────────────────────────────

class MyOpelCoordinator(DataUpdateCoordinator):
    """Coordinator that reads the .myop / trips.json file and extracts latest vehicle data."""

    def __init__(
        self,
        hass: HomeAssistant,
        file_path: str,
        scan_interval: int,
        min_trip_distance: float = 0.0,
        ack_store: AlertAckStore | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.file_path = file_path
        self.min_trip_distance = min_trip_distance
        self.ack_store = ack_store

    async def _async_update_data(self) -> dict:
        """Read and parse the trip data file."""
        try:
            return await self.hass.async_add_executor_job(self._parse_file)
        except _NoFileYet:
            _LOGGER.debug("MyOpel: nessun file .myop/trips.json ancora, in attesa...")
            return {}
        except (json.JSONDecodeError, KeyError, IndexError) as err:
            raise UpdateFailed(f"Error parsing trip file: {err}") from err

    def _parse_file(self) -> dict:
        folder = Path(self.file_path)
        folder.mkdir(parents=True, exist_ok=True)

        # Accept .myop (legacy), trips.json, trips.export (iOS Shortcuts); pick newest
        candidates = list(folder.glob("*.myop")) + list(folder.glob("trips.json")) + (
            [folder / "trips.export"] if (folder / "trips.export").is_file() else []
        )
        if not candidates:
            raise _NoFileYet
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        path = candidates[0]
        _LOGGER.debug("MyOpel: lettura file %s", path.name)

        raw = json.loads(path.read_text(encoding="utf-8"))

        vehicle = raw[0]
        vin = vehicle.get("vin", "unknown")
        trips = vehicle.get("trips", [])

        if not trips:
            raise UpdateFailed("No trips found in file")

        # Sort trips by end date descending
        def end_date(t):
            return t.get("end", {}).get("date") or ""

        sorted_trips = sorted(trips, key=end_date, reverse=True)

        # Apply minimum distance filter to ALL calculations
        min_d = self.min_trip_distance
        if min_d > 0:
            filtered_trips = [t for t in trips if t.get("distance", 0) >= min_d]
            filtered_sorted = [t for t in sorted_trips if t.get("distance", 0) >= min_d]
        else:
            filtered_trips = trips
            filtered_sorted = sorted_trips

        # Latest trip = most recent qualifying trip (fall back to absolute latest if none qualify)
        latest = filtered_sorted[0] if filtered_sorted else sorted_trips[0]

        # Aggregate stats across filtered trips only
        total_distance = sum(t.get("distance", 0) for t in filtered_trips)
        total_travel_time_s = sum(t.get("travelTime", 0) for t in filtered_trips)
        total_raw_fuel = [
            t.get("fuelConsumption")
            for t in filtered_trips
            if t.get("fuelConsumption") is not None
        ]

        start_info = latest.get("start", {})
        end_info = latest.get("end", {})

        # fuelConsumption è in unità proprietarie Stellantis.
        # Correlazione verificata: trip 20/03/2026, 11,9 km → fuelConsumption=532536
        # App mostra 0,5 l (22,3 km/l) → 532536 / 1_000_000 = 0,5326 L ✓
        FUEL_DIVISOR = 1_000_000
        raw_consumption = latest.get("fuelConsumption")
        trip_distance = latest.get("distance", 0)
        trip_time_s = latest.get("travelTime", 0)
        fuel_consumption_l = None
        fuel_consumption_kmpl = None
        last_trip_avg_speed = None
        last_trip_cost = None
        if raw_consumption is not None:
            fuel_consumption_l = round(raw_consumption / FUEL_DIVISOR, 2)
            if trip_distance and trip_distance > 0 and fuel_consumption_l > 0:
                fuel_consumption_kmpl = round(trip_distance / fuel_consumption_l, 1)
        if trip_distance > 0 and trip_time_s > 0:
            last_trip_avg_speed = round(trip_distance / (trip_time_s / 3600), 1)
        if fuel_consumption_l and latest.get("priceFuel"):
            last_trip_cost = round(fuel_consumption_l * latest["priceFuel"], 2)

        # Total fuel across all trips
        total_fuel_l = (
            round(sum(total_raw_fuel) / FUEL_DIVISOR, 2) if total_raw_fuel else None
        )
        total_fuel_kmpl = (
            round(total_distance / total_fuel_l, 1)
            if total_fuel_l and total_distance and total_fuel_l > 0
            else None
        )
        # Total cost (filtered trips only)
        total_cost_eur = round(sum(
            (t.get("fuelConsumption", 0) / FUEL_DIVISOR) * t["priceFuel"]
            for t in filtered_trips
            if t.get("fuelConsumption") and t.get("priceFuel")
        ), 2) or None

        # ── Alerts ───────────────────────────────────────────────────────────
        last_trip_alerts: list[int] = [int(c) for c in (latest.get("alerts") or []) if isinstance(c, int)]
        last_trip_id = latest.get("id")
        last_trip_alert_count = len(last_trip_alerts)
        last_trip_has_alerts = bool(last_trip_alerts)
        last_trip_alert_codes = (
            ", ".join(_alert_label(c) for c in sorted(set(last_trip_alerts)))
            if last_trip_alerts else "Nessuno"
        )

        # Split alerts into acknowledged / unacknowledged via the ack store.
        acked_codes_for_trip = (
            set(self.ack_store.acked_codes_for(last_trip_id))
            if self.ack_store is not None else set()
        )
        unique_alert_codes = sorted(set(last_trip_alerts))
        last_trip_acked_alerts = sorted(c for c in unique_alert_codes if c in acked_codes_for_trip)
        last_trip_unack_alerts = sorted(c for c in unique_alert_codes if c not in acked_codes_for_trip)
        last_trip_unack_alert_count = sum(
            1 for c in last_trip_alerts if c not in acked_codes_for_trip
        )
        last_trip_has_unack_alerts = bool(last_trip_unack_alerts)
        last_trip_unack_alert_codes = (
            ", ".join(_alert_label(c) for c in last_trip_unack_alerts)
            if last_trip_unack_alerts else "Nessuno"
        )
        last_trip_acked_alert_codes = (
            ", ".join(_alert_label(c) for c in last_trip_acked_alerts)
            if last_trip_acked_alerts else "Nessuno"
        )
        last_trip_alert_labels = {str(c): _alert_label(c) for c in unique_alert_codes}

        # All-time alert frequency across filtered trips
        all_alert_codes: list[int] = []
        for t in filtered_trips:
            all_alert_codes.extend(t.get("alerts") or [])
        total_alert_count = len(all_alert_codes)
        alert_freq = Counter(all_alert_codes)
        all_alert_codes_summary = (
            ", ".join(f"{_alert_label(code)}×{cnt}" for code, cnt in alert_freq.most_common())
            if alert_freq else "Nessuno"
        )

        # Total average speed (filtered)
        total_avg_speed = (
            round(total_distance / (total_travel_time_s / 3600), 1)
            if total_travel_time_s > 0 and total_distance > 0 else None
        )

        # ── Since last refueling ──────────────────────────────────────────────
        chron_trips = sorted(filtered_trips, key=end_date)
        refuel_idx = 0
        for i in range(1, len(chron_trips)):
            prev_level = chron_trips[i - 1].get("fuelLevel")
            curr_level = chron_trips[i].get("fuelLevel")
            if prev_level is not None and curr_level is not None:
                if curr_level > prev_level + 5:
                    refuel_idx = i
        refuel_trips = chron_trips[refuel_idx:]
        refuel_date = chron_trips[refuel_idx - 1].get("end", {}).get("date") if refuel_idx > 0 else None

        refuel_dist = round(sum(t.get("distance", 0) for t in refuel_trips), 1)
        refuel_time_s = sum(t.get("travelTime", 0) for t in refuel_trips)
        refuel_raw_fuel = [t.get("fuelConsumption") for t in refuel_trips if t.get("fuelConsumption") is not None]
        refuel_fuel_l = round(sum(refuel_raw_fuel) / FUEL_DIVISOR, 2) if refuel_raw_fuel else None
        refuel_kmpl = (
            round(refuel_dist / refuel_fuel_l, 1)
            if refuel_fuel_l and refuel_dist and refuel_fuel_l > 0 else None
        )
        refuel_cost = round(sum(
            (t.get("fuelConsumption", 0) / FUEL_DIVISOR) * t["priceFuel"]
            for t in refuel_trips
            if t.get("fuelConsumption") and t.get("priceFuel")
        ), 2) or None
        refuel_avg_speed = (
            round(refuel_dist / (refuel_time_s / 3600), 1)
            if refuel_time_s > 0 and refuel_dist > 0 else None
        )

        # ── Monthly aggregates (current calendar month) ─────────────────────
        now_utc = datetime.now(tz=timezone.utc)
        current_year = now_utc.year
        current_month = now_utc.month

        monthly_trips: list[dict] = []
        for t in filtered_trips:
            raw_date = (t.get("end") or {}).get("date")
            if not raw_date:
                continue
            try:
                dt = datetime.fromisoformat(raw_date.rstrip("Z")).replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                continue
            if dt.year == current_year and dt.month == current_month:
                monthly_trips.append(t)

        month_trip_count = len(monthly_trips)
        month_distance_km = round(sum(t.get("distance", 0) for t in monthly_trips), 1)
        month_time_s = sum(t.get("travelTime", 0) for t in monthly_trips)
        month_duration_min = round(month_time_s / 60, 1)
        month_avg_speed = (
            round(month_distance_km / (month_time_s / 3600), 1)
            if month_time_s > 0 and month_distance_km > 0 else None
        )

        month_raw_consumption = [
            t.get("fuelConsumption")
            for t in monthly_trips
            if t.get("fuelConsumption") is not None
        ]
        month_fuel_l = (
            round(sum(month_raw_consumption) / 1_000_000, 2) if month_raw_consumption else None
        )
        month_fuel_kmpl = (
            round(month_distance_km / month_fuel_l, 1)
            if month_fuel_l and month_distance_km and month_fuel_l > 0
            else None
        )
        month_cost_eur = round(sum(
            (t.get("fuelConsumption", 0) / 1_000_000) * t["priceFuel"]
            for t in monthly_trips
            if t.get("fuelConsumption") and t.get("priceFuel")
        ), 2) or None

        month_alerts: list[int] = []
        for t in monthly_trips:
            month_alerts.extend(t.get("alerts") or [])
        month_alert_count = len(month_alerts)
        month_alert_freq = Counter(month_alerts)
        month_alert_codes_summary = (
            ", ".join(f"{_alert_label(code)}×{cnt}" for code, cnt in month_alert_freq.most_common())
            if month_alert_freq else "Nessuno"
        )

        return {
            "vin": vin,
            # --- Last trip ---
            "last_trip_id": latest.get("id"),
            "last_trip_start": start_info.get("date"),
            "last_trip_end": end_info.get("date"),
            "last_trip_distance_km": round(trip_distance, 2),
            "last_trip_duration_min": round(latest.get("travelTime", 0) / 60, 1),
            "last_trip_fuel_consumption_l": fuel_consumption_l,
            "last_trip_fuel_consumption_kmpl": fuel_consumption_kmpl,
            "last_trip_price_fuel": latest.get("priceFuel"),
            "last_trip_avg_speed": last_trip_avg_speed,
            "last_trip_cost": last_trip_cost,
            # --- Last trip alerts ---
            "last_trip_alert_count": last_trip_alert_count,
            "last_trip_alert_codes": last_trip_alert_codes,
            "last_trip_has_alerts": last_trip_has_alerts,
            "last_trip_alerts_raw": unique_alert_codes,
            "last_trip_unack_alerts_raw": last_trip_unack_alerts,
            "last_trip_acked_alerts_raw": last_trip_acked_alerts,
            "last_trip_unack_alert_count": last_trip_unack_alert_count,
            "last_trip_unack_alert_codes": last_trip_unack_alert_codes,
            "last_trip_acked_alert_codes": last_trip_acked_alert_codes,
            "last_trip_has_unack_alerts": last_trip_has_unack_alerts,
            "last_trip_alert_labels": last_trip_alert_labels,
            # --- Vehicle state (from latest trip end) ---
            "mileage_km": end_info.get("mileage"),
            "fuel_level_pct": latest.get("fuelLevel"),
            "fuel_autonomy_km": latest.get("fuelAutonomy"),
            # --- Maintenance ---
            "days_until_maintenance": latest.get("daysUntilNextMaintenance"),
            "distance_to_maintenance_km": (
                int(latest["distanceToNextMaintenance"])
                if latest.get("distanceToNextMaintenance") is not None else None
            ),
            "maintenance_passed": latest.get("maintenancePassed"),
            # --- All-time aggregates ---
            "total_trips": len(filtered_trips),
            "total_distance_km": round(total_distance, 1),
            "total_travel_time_h": round(total_travel_time_s / 3600, 1),
            "total_fuel_l": total_fuel_l,
            "total_fuel_kmpl": total_fuel_kmpl,
            "total_avg_speed": total_avg_speed,
            "total_cost_eur": total_cost_eur,
            "total_alert_count": total_alert_count,
            "all_alert_codes_summary": all_alert_codes_summary,
            # --- Monthly aggregates (current month) ---
            "month_trip_count": month_trip_count,
            "month_distance_km": month_distance_km,
            "month_duration_min": month_duration_min,
            "month_avg_speed": month_avg_speed,
            "month_fuel_l": month_fuel_l,
            "month_fuel_kmpl": month_fuel_kmpl,
            "month_cost_eur": month_cost_eur,
            "month_alert_count": month_alert_count,
            "month_alert_codes_summary": month_alert_codes_summary,
            # --- Since last refueling ---
            "refuel_trip_count": len(refuel_trips),
            "refuel_distance_km": refuel_dist,
            "refuel_duration_h": round(refuel_time_s / 3600, 1),
            "refuel_fuel_l": refuel_fuel_l,
            "refuel_kmpl": refuel_kmpl,
            "refuel_cost_eur": refuel_cost,
            "refuel_avg_speed": refuel_avg_speed,
            "refuel_date": refuel_date,
        }
