"""OBD coordinator for MyOpel — reads CarScanner CSV exports.

Behaviour:
- Reads every new `*.csv` in the configured folder (oldest → newest), computes
  trip stats for ALL PIDs found, and persists the result to HA storage.
- After a successful parse the CSV is deleted (configurable) so files don't
  accumulate.
- The latest parsed trip survives HA restarts even if the folder is empty.
- A short history of recent trips is kept in storage for future aggregations.
- The set of discovered PID names is persisted, so the options flow can offer
  the user a multi-select of every PID that has ever been seen.
"""
from __future__ import annotations

import csv
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    OBD_HISTORY_MAX_TRIPS,
    OBD_STORAGE_KEY_TPL,
    OBD_STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

# PIDs used to determine the engine-on window (reliable OBD, not GPS).
# First match wins. ECM profile names listed after Italian generic names.
_ENGINE_ANCHOR_PIDS = (
    "Giri motore",
    "[ECM] Crankshaft speed",
    "Velocità veicolo",
    "[ECM] Vehicle speed",
    "Distanza percorsa:",
)

# Curated "preset" PIDs that get well-known sensor keys. Other PIDs are exposed
# under a slugified key (see `_slugify_pid`) and only become sensors if the user
# enables them from the options flow.
#   coordinator data key → (PID name(s) in CSV, aggregation)
# A tuple of names means "try in order, use first found" — supports both
# Italian generic OBD2 names and English ECM profile names.
# aggregations: "last", "max", "min", "mean", "first"
_PID_MAP: dict[str, tuple[str | tuple[str, ...], str]] = {
    # ── Basic trip ────────────────────────────────────────────────────────────
    "obd_trip_distance_km":           ("Distanza percorsa:",                                              "last"),
    "obd_trip_avg_speed_kmh":         ("Velocità (GPS)",                                                  "mean"),
    "obd_trip_max_speed_kmh":         ("Velocità (GPS)",                                                  "max"),
    # ── Engine ───────────────────────────────────────────────────────────────
    "obd_trip_avg_rpm":               (("Giri motore", "[ECM] Crankshaft speed"),                        "mean"),
    "obd_trip_max_rpm":               (("Giri motore", "[ECM] Crankshaft speed"),                        "max"),
    "obd_trip_coolant_temp_max_c":    (("Temperatura liquido raffreddamento motore",
                                        "[ECM] Coolant temperature, corrected"),                          "max"),
    "obd_trip_oil_temp_max_c":        ("[ECM] Oil temperature",                                          "max"),
    "obd_trip_odometer_km":           ("[ECM] Total mileage",                                            "last"),
    "obd_trip_air_temp_c":            (("Temperatura d'aria ambiente", "[ECM] Outside air temperature"), "first"),
    # ── DPF / emissions ──────────────────────────────────────────────────────
    "obd_trip_dpf_soot_pct":          ("[ECM] Soot clogging level of diesel particulate filter",         "last"),
    "obd_trip_dpf_closed_soot":       ("[ECM] Closed loop soot load assessment of the diesel particulate filter", "last"),
    "obd_trip_dpf_regen_active":      ("[ECM] DPF regeneration status",                                  "max"),
    "obd_trip_dpf_regen_enable":      ("[ECM] Regeneration enable",                                      "max"),
    "obd_trip_dpf_regen_capability":  ("[ECM] Long-term regeneration capability",                        "last"),
    "obd_trip_dpf_regen_capability_st": ("[ECM] Short-term regeneration capability",                     "last"),
    "obd_trip_dpf_since_regen_km":    ("[ECM] Distance traveled since the last regeneration",            "last"),
    "obd_trip_dpf_avg_regen_km":      ("[ECM] Average mileage for the last 10 regenerations",            "last"),
    "obd_trip_dpf_replace_km":        ("[ECM] Mileage remaining before diesel particulate filter replacement", "last"),
    "obd_trip_adblue_vol_l":          ("[ECM] Volume of urea solution measured in urea tank",            "last"),
    "obd_trip_adblue_range_km":       ("[ECM] Vehicle mileage remaining before filling the tank with urea solution", "last"),
    "obd_trip_exhaust_before_cat_c":  ("[ECM] Exhaust gas temperature before pre-catalytic converter",  "max"),
    "obd_trip_exhaust_after_cat_c":   ("[ECM] Exhaust gas temperature after pre-catalytic converter",   "max"),
    "obd_trip_nox_cat_temp_max_c":    ("[ECM] Temperature of the NOx catalytic converter",              "max"),
    # ── Diagnostics ──────────────────────────────────────────────────────────
    "obd_trip_battery_startup_v":     ("[ECM] Minimum battery voltage at startup",                       "last"),
    "obd_trip_oil_dilution_pct":      ("[ECM] Evaluation of the degree of dilution of motor oil",        "last"),
    "obd_trip_ss_state":              ("[ECM] Stop and Start function state",                             "last"),
}

# Reverse lookup: PID name → list of (data_key, agg)
_NAME_TO_KEYS: dict[str, list[tuple[str, str]]] = {}
for _k, (_pid_spec, _a) in _PID_MAP.items():
    for _n in ((_pid_spec,) if isinstance(_pid_spec, str) else _pid_spec):
        _NAME_TO_KEYS.setdefault(_n, []).append((_k, _a))

# LTS metadata for curated sensors: key → (display name, unit).
# Keys absent from this dict are skipped (boolean labels, odometer).
_LTS_META: dict[str, tuple[str, str | None]] = {
    "obd_trip_distance_km":          ("OBD – Distanza viaggio",           "km"),
    "obd_trip_avg_speed_kmh":        ("OBD – Velocità media GPS",         "km/h"),
    "obd_trip_max_speed_kmh":        ("OBD – Velocità massima GPS",       "km/h"),
    "obd_trip_avg_rpm":              ("OBD – Giri motore medi",           "rpm"),
    "obd_trip_max_rpm":              ("OBD – Giri motore massimi",        "rpm"),
    "obd_trip_coolant_temp_max_c":   ("OBD – Temp. raffreddamento max",   "°C"),
    "obd_trip_oil_temp_max_c":       ("OBD – Temperatura olio max",       "°C"),
    "obd_trip_fuel_consumed_l":      ("OBD – Carburante consumato",       "L"),
    "obd_trip_consumption_l100km":   ("OBD – Consumo medio",              "L/100km"),
    "obd_trip_air_temp_c":           ("OBD – Temperatura aria esterna",   "°C"),
    "obd_trip_dpf_soot_pct":              ("OBD – DPF intasamento",              "%"),
    "obd_trip_dpf_regen_capability":      ("OBD – Capacità rigenerazione DPF",   "%"),
    "obd_trip_dpf_regen_capability_st":   ("OBD – Cap. rigenerazione breve",     "%"),
    "obd_trip_dpf_since_regen_km":        ("OBD – Distanza ultima rigenerazione", "km"),
    "obd_trip_dpf_avg_regen_km":          ("OBD – Media km rigenerazione DPF",   "km"),
    "obd_trip_dpf_replace_km":            ("OBD – km rimanenti sostituzione DPF","km"),
    "obd_trip_adblue_vol_l":              ("OBD – AdBlue nel serbatoio",         "L"),
    "obd_trip_adblue_range_km":           ("OBD – Autonomia AdBlue",             "km"),
    "obd_trip_dpf_closed_soot":           ("OBD – Soot closed-loop DPF",         "g/L"),
    "obd_trip_exhaust_before_cat_c":      ("OBD – Temp. gas scarico pre-cat max","°C"),
    "obd_trip_exhaust_after_cat_c":       ("OBD – Temp. gas scarico max",        "°C"),
    "obd_trip_nox_cat_temp_max_c":        ("OBD – Temp. cat. NOx max",           "°C"),
    "obd_trip_battery_startup_v":         ("OBD – Tensione avviamento batteria", "V"),
    "obd_trip_oil_dilution_pct":          ("OBD – Diluizione olio",              "%"),
}


# ── RBS (byte-swap) fixes ─────────────────────────────────────────────────────
#
# CarScanner's "MD1CS003" profile for the Peugeot/Citroën 1.5 BlueHDi sets
# RBS=true on several 2-byte PIDs where the actual ECU stream is big-endian.
# The result is a CSV value of (B*256+A)*MUL/DIV instead of (A*256+B)*MUL/DIV.
# Given only the decoded CSV value and the formula constants, we can recover
# the no-RBS value by: rounding back to the 16-bit raw, swapping bytes, and
# re-applying the formula.
#
# Users opt-in per PID via the options flow. Defaults to empty (= no fixing)
# so users on other ECUs / profiles are not affected.

_RBS_FIXES: dict[str, dict[str, float]] = {
    "[ECM] Distance traveled since the last regeneration": {
        "div": 16.0, "mul": 1.0, "ofs": 0.0,
    },
    "[ECM] Set value of turbo boost pressure": {
        "div": 1.0, "mul": 1.0, "ofs": 0.0,
    },
    "[ECM] EGR valve position": {
        "div": 100.0, "mul": 1.0, "ofs": 0.0,
    },
    "[ECM] Air metering valve position": {
        "div": 100.0, "mul": 1.0, "ofs": 0.0,
    },
    "[ECM] NOx content measured at the inlet of the NOx catalytic converter": {
        "div": 1.0, "mul": 0.1, "ofs": 0.0,
    },
    "[ECM] Open loop soot load assessment of the diesel particulate filter": {
        "div": 1024.0, "mul": 1.0, "ofs": 0.0,
    },
    "[ECM] Soot clogging level of diesel particulate filter": {
        "div": 10.24, "mul": 1.0, "ofs": 0.0,
    },
    "[ECM] Average mileage for the last 10 regenerations": {
        "div": 16.0, "mul": 1.0, "ofs": 0.0,
    },
    "[ECM] Total mass of additive accumulated in the diesel particulate filter": {
        "div": 128.0, "mul": 1.0, "ofs": 0.0,
    },
    "[ECM] Mileage remaining before diesel particulate filter replacement": {
        "div": 1.0, "mul": 16.0, "ofs": 0.0,
    },
    "[ECM] Exhaust gas pressure at the outlet of the particulate filter": {
        "div": 999.999952502551, "mul": 1.0, "ofs": 0.0,
    },
}


def _rbs_swap_value(value: float, div: float, mul: float, ofs: float) -> float:
    """Reverse a CarScanner byte-swap mistake on a 2-byte PID.

    Given the (wrong) CSV value `v = (B*256+A) * mul/div + ofs`, recover
    `(A*256+B) * mul/div + ofs`. Returns the input unchanged if the implied
    raw value does not fit into a uint16 — defensive no-op for non-2-byte
    PIDs accidentally enabled.
    """
    raw = round((value - ofs) * div / mul)
    if raw < 0:
        # CarScanner may have interpreted the 2-byte register as signed int16
        raw += 0x10000
    if not 0 <= raw <= 0xFFFF:
        return value
    swapped = ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)
    return swapped * mul / div + ofs


# ── Helpers ──────────────────────────────────────────────────────────────────

# Patterns tried in order to extract a recording timestamp from the filename.
# Each group tuple must be (Y, M, D, H, Min, S).
_FNAME_DATE_RE = [
    re.compile(r"(\d{4})(\d{2})(\d{2})[_T](\d{2})(\d{2})(\d{2})"),   # 20260520_183532
    re.compile(r"(\d{4})-(\d{2})-(\d{2})[ _](\d{2})-(\d{2})-(\d{2})"),# 2026-05-19 21-16-39
    re.compile(r"(\d{4})-(\d{2})-(\d{2})[T _](\d{2}):(\d{2}):(\d{2})"),# ISO with colons
]


def _csv_recording_key(path: Path) -> tuple[datetime, float]:
    """Sortable key: (recorded_at_utc, mtime_fallback).

    Tries to extract the recording date from the filename so that files are
    always processed in strict chronological order regardless of when they
    were copied to the folder.  Falls back to mtime if no pattern matches.
    """
    for pattern in _FNAME_DATE_RE:
        m = pattern.search(path.stem)
        if m:
            try:
                return (
                    datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                             int(m.group(4)), int(m.group(5)), int(m.group(6)),
                             tzinfo=timezone.utc),
                    0.0,
                )
            except ValueError:
                pass
    return (datetime.min.replace(tzinfo=timezone.utc), path.stat().st_mtime)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify_pid(name: str) -> str:
    """Stable slug for a PID name, usable as a sensor key suffix."""
    s = name.lower().strip()
    s = s.replace("°", "deg").replace("²", "2").replace("µ", "u")
    s = _SLUG_RE.sub("_", s).strip("_")
    return s or "pid"


class _NoObdFileYet(Exception):
    """Raised when the folder has no CSV files — not a fatal error."""


# ── Coordinator ──────────────────────────────────────────────────────────────

class MyOpelObdCoordinator(DataUpdateCoordinator):
    """Coordinator that reads CarScanner CSV exports and persists trip stats."""

    def __init__(
        self,
        hass: HomeAssistant,
        folder_path: str,
        scan_interval: int,
        entry_id: str,
        delete_after_parse: bool = True,
        rbs_fix_pids: list[str] | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="myopel_obd",
            update_interval=timedelta(seconds=scan_interval),
        )
        # DataUpdateCoordinator already stores hass, but the test stub does not;
        # set it explicitly so async_add_executor_job is reachable in tests too.
        self.hass = hass
        self.folder_path = folder_path
        self.entry_id = entry_id
        self.delete_after_parse = delete_after_parse
        self.rbs_fix_pids: list[str] = rbs_fix_pids or []
        self._store: Store = Store(
            hass, OBD_STORAGE_VERSION, OBD_STORAGE_KEY_TPL.format(entry_id=entry_id)
        )
        # In-memory mirror of the persisted store:
        #   "latest":   dict with the most recent parsed trip's data
        #   "history":  list[dict] with up to OBD_HISTORY_MAX_TRIPS recent trips
        #   "pids":     dict[slug -> {"name": str, "unit": str|None}]
        self._latest: dict[str, Any] = {}
        self._history: list[dict[str, Any]] = []
        self._discovered_pids: dict[str, dict[str, Any]] = {}

    @property
    def discovered_pids(self) -> dict[str, dict[str, Any]]:
        """Return the catalog of every PID ever seen (slug → metadata)."""
        return dict(self._discovered_pids)

    async def async_load_persisted(self) -> None:
        """Load the persisted trip data into memory (call once at setup)."""
        data = await self._store.async_load() or {}
        self._latest = data.get("latest") or {}
        self._history = data.get("history") or []
        self._discovered_pids = data.get("pids") or {}
        # Seed coordinator data so sensors are populated immediately, even
        # before the first refresh (and before any new CSV arrives).
        if self._latest:
            self.data = self._latest
        _LOGGER.debug(
            "%s OBD: caricati %d viaggi, %d PID dal persistente",
            DOMAIN, len(self._history), len(self._discovered_pids),
        )

    async def _async_save(self) -> None:
        await self._store.async_save({
            "latest": self._latest,
            "history": self._history[-OBD_HISTORY_MAX_TRIPS:],
            "pids": self._discovered_pids,
        })

    async def _async_inject_trip_statistics(self, trip_data: dict[str, Any]) -> None:
        """Inject one LTS data point per curated numeric sensor for the parsed trip."""
        from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
        from homeassistant.components.recorder.statistics import async_add_external_statistics

        ts_str = trip_data.get("obd_trip_start")
        if not ts_str:
            return
        try:
            t_bucket = datetime.fromisoformat(ts_str).replace(
                minute=0, second=0, microsecond=0
            )
        except ValueError:
            return

        pid_values = trip_data.get("obd_pid_values") or {}

        for sensor_key, (lts_name, lts_unit) in _LTS_META.items():
            value = trip_data.get(sensor_key)
            if value is None:
                continue
            # Use per-PID min/max/mean from generic stats when available.
            # Computed keys (e.g. fuel totals) are not in _PID_MAP so fall back
            # to the curated scalar for all three stat fields.
            pid_name_agg = _PID_MAP.get(sensor_key)
            if pid_name_agg:
                _pid_spec = pid_name_agg[0]
                # _pid_spec may be str or tuple[str, ...]; use first name for slug
                _pid_primary = _pid_spec if isinstance(_pid_spec, str) else _pid_spec[0]
                pid_stats = pid_values.get(_slugify_pid(_pid_primary)) or {}
            else:
                pid_stats = {}
            v = float(value)
            mean = pid_stats.get("mean", v)
            min_val = pid_stats.get("min", v)
            max_val = pid_stats.get("max", v)

            stat_id = f"{DOMAIN}:{self.entry_id}_{sensor_key}"
            metadata = StatisticMetaData(
                has_mean=True,
                has_sum=False,
                name=lts_name,
                source=DOMAIN,
                statistic_id=stat_id,
                unit_of_measurement=lts_unit,
            )
            async_add_external_statistics(
                self.hass,
                metadata,
                [StatisticData(start=t_bucket, mean=mean, min=min_val, max=max_val)],
            )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            parsed = await self.hass.async_add_executor_job(self._parse_pending_csvs)
        except _NoObdFileYet:
            _LOGGER.debug("MyOpel OBD: nessun nuovo CSV in %s", self.folder_path)
            return self._latest
        except Exception as err:
            raise UpdateFailed(f"OBD CSV parse error: {err}") from err

        if not parsed:
            return self._latest

        # Inter-file regen detection: if the first "distance since regen" value
        # in this trip is less than the last known value, a regen occurred between
        # log files (or was already completed when recording started).
        _dist_slug = _slugify_pid("[ECM] Distance traveled since the last regeneration")
        _prev_dist = self._latest.get("obd_trip_dpf_since_regen_km")
        for trip in parsed:
            _pid_stats = trip.get("obd_pid_values", {}).get(_dist_slug, {})
            _trip_first_dist = _pid_stats.get("first")
            if (
                _prev_dist is not None
                and _trip_first_dist is not None
                and _trip_first_dist < _prev_dist * 0.5
                and trip.get("obd_dpf_regen_state") in ("idle", "post_regen")
            ):
                trip["obd_dpf_regen_state"] = "post_regen"
            _prev_dist = trip.get("obd_trip_dpf_since_regen_km", _prev_dist)

        # Update history + latest + pid catalog; inject LTS while obd_pid_values
        # is still present (before the catalog pop strips the per-trip dicts).
        for trip in parsed:
            self._history.append(trip)
            for slug, meta in (trip.get("_pid_catalog") or {}).items():
                prev = self._discovered_pids.get(slug)
                # Kind demotes toward "number" if ever seen as number.
                # bool < discrete < number (in terms of promotion).
                kind = _merge_kind(prev.get("kind") if prev else None,
                                   meta.get("kind", "number"))
                if prev is None or (not prev.get("unit") and meta.get("unit")) \
                        or prev.get("kind") != kind:
                    self._discovered_pids[slug] = {
                        "name": meta.get("name", slug),
                        "unit": prev.get("unit") if prev and prev.get("unit") else meta.get("unit"),
                        "kind": kind,
                    }
            try:
                await self._async_inject_trip_statistics(trip)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning(
                    "MyOpel OBD: LTS injection failed for %s: %s",
                    trip.get("obd_filename"), exc,
                )
        # Drop the catalog from per-trip dicts before persisting (lives at top level)
        for trip in parsed:
            trip.pop("_pid_catalog", None)

        self._history = self._history[-OBD_HISTORY_MAX_TRIPS:]
        self._latest = parsed[-1]
        await self._async_save()
        return self._latest

    # ── CSV parsing ──────────────────────────────────────────────────────────

    def _parse_pending_csvs(self) -> list[dict[str, Any]]:
        folder = Path(self.folder_path)
        folder.mkdir(parents=True, exist_ok=True)

        csvs = sorted(folder.glob("*.csv"), key=_csv_recording_key)
        if not csvs:
            raise _NoObdFileYet

        results: list[dict[str, Any]] = []
        for path in csvs:
            try:
                result = _parse_csv_file(path, self.rbs_fix_pids)
            except UpdateFailed:
                _LOGGER.warning("MyOpel OBD: %s vuoto o malformato, ignoro", path.name)
                continue
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "MyOpel OBD: errore parsing %s (%s), file lasciato sul disco",
                    path.name, err,
                )
                continue

            results.append(result)
            if self.delete_after_parse:
                try:
                    path.unlink()
                    _LOGGER.debug("MyOpel OBD: %s elaborato e rimosso", path.name)
                except OSError as err:
                    _LOGGER.warning(
                        "MyOpel OBD: impossibile rimuovere %s (%s)", path.name, err,
                    )
        return results


# ── Parsing primitives (module-level for testability) ────────────────────────

def _parse_csv_file(
    path: Path,
    rbs_fix_pids: list[str] | None = None,
) -> dict[str, Any]:
    active_rbs: dict[str, dict[str, float]] = {}
    if rbs_fix_pids:
        for pid_name in rbs_fix_pids:
            if pid_name in _RBS_FIXES:
                active_rbs[pid_name] = _RBS_FIXES[pid_name]

    pids: dict[str, list[tuple[float, float]]] = {}
    units: dict[str, str] = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh, delimiter=";")
        next(reader, None)
        for row in reader:
            if len(row) < 4:
                continue
            try:
                sec = float(row[0])
                pid = row[1]
                val = float(row[2])
            except (ValueError, IndexError):
                continue
            if pid in active_rbs:
                fix = active_rbs[pid]
                val = _rbs_swap_value(val, fix["div"], fix["mul"], fix["ofs"])
            pids.setdefault(pid, []).append((sec, val))
            unit = row[3].strip() if len(row) > 3 else ""
            if unit and pid not in units:
                units[pid] = unit

    if not pids:
        raise UpdateFailed("OBD CSV is empty")
    return _compute_stats(pids, units, path)


def _compute_stats(
    pids: dict[str, list[tuple[float, float]]],
    units: dict[str, str],
    path: Path,
) -> dict[str, Any]:
    # Determine engine-on window from anchor PIDs
    t_start: float | None = None
    t_end: float | None = None
    for anchor in _ENGINE_ANCHOR_PIDS:
        recs = pids.get(anchor)
        if recs:
            t_start = min(s for s, _ in recs)
            t_end = max(s for s, _ in recs)
            break
    if t_start is None:
        all_secs = [s for recs in pids.values() for s, _ in recs]
        t_start = min(all_secs) if all_secs else 0.0
        t_end = max(all_secs) if all_secs else 0.0

    duration_s = (t_end or 0.0) - (t_start or 0.0)

    def _vals(pid_name: str) -> list[float]:
        return [v for s, v in pids.get(pid_name, [])
                if t_start <= s <= (t_end or s)]

    result: dict[str, Any] = {
        "obd_filename": path.name,
        "obd_trip_duration_min": round(duration_s / 60.0, 1),
    }

    # ── Curated sensor values ────────────────────────────────────────────────
    _SOOT_MAX = 150.0
    for key, (pid_spec, agg) in _PID_MAP.items():
        pid_names = (pid_spec,) if isinstance(pid_spec, str) else pid_spec
        vals: list[float] = []
        for pid_name in pid_names:
            vals = _vals(pid_name)
            if vals:
                break
        if not vals:
            result[key] = None
            continue
        if key == "obd_trip_dpf_soot_pct":
            vals = [v for v in vals if v <= _SOOT_MAX]
            if not vals:
                result[key] = None
                continue
        result[key] = round(_aggregate(vals, agg), 2 if key.endswith("_km") else 1)

    # Odometer-based trip distance fallback: when "Distanza percorsa:" is absent
    # (which is the common case), derive trip distance from first↔last odometer.
    if result.get("obd_trip_distance_km") is None:
        odo_recs = pids.get("[ECM] Total mileage", [])
        odo_in_window = [(s, v) for s, v in odo_recs if t_start <= s <= (t_end or s)]
        if len(odo_in_window) >= 2:
            odo_delta = odo_in_window[-1][1] - odo_in_window[0][1]
            if odo_delta >= 0:
                result["obd_trip_distance_km"] = round(odo_delta, 2)

    # ── Fuel consumption via trapezoid integration ────────────────────────────
    _FUEL_PID = "Consumo istantaneo di carburante calcolato"
    total_l = _trapezoid_integrate_lph(
        pids.get(_FUEL_PID) or [], t_start, t_end or t_start
    )
    result["obd_trip_fuel_consumed_l"] = round(total_l, 3) if total_l is not None else None
    dist = result.get("obd_trip_distance_km")
    if total_l is not None and dist and dist > 0:
        result["obd_trip_consumption_l100km"] = round(total_l / dist * 100.0, 2)
    else:
        result["obd_trip_consumption_l100km"] = None

    # Coerce integer-like quantities
    for k in ("obd_trip_odometer_km", "obd_trip_avg_rpm", "obd_trip_max_rpm"):
        if result.get(k) is not None:
            result[k] = int(result[k])

    # ── DPF regeneration state inference ────────────────────────────────────
    # Based on real log analysis: combining regen_status, EGT and soot readings
    # is more reliable than any single PID.
    _regen_status_vals = _vals("[ECM] DPF regeneration status")
    _egt_after_vals    = _vals("[ECM] Exhaust gas temperature after pre-catalytic converter")
    _nox_cat_vals      = _vals("[ECM] Temperature of the NOx catalytic converter")
    _soot_closed_vals  = _vals("[ECM] Closed loop soot load assessment of the diesel particulate filter")
    # Use ALL recs for dist-since-regen, not just the window: the very first
    # reading may arrive before the Crankshaft anchor locks in the window.
    _dist_regen_recs   = sorted(
        pids.get("[ECM] Distance traveled since the last regeneration", []),
        key=lambda x: x[0],
    )

    _regen_enable_vals = _vals("[ECM] Regeneration enable")
    _regen_requested = bool(_regen_status_vals and max(_regen_status_vals) >= 1)
    # Regeneration enable: if PID absent treat as "don't gate" (not all profiles log it)
    _regen_enabled   = (not _regen_enable_vals) or max(_regen_enable_vals) >= 1
    _thermal_regen   = bool(
        (_egt_after_vals and max(_egt_after_vals) > 550)
        or (_nox_cat_vals and max(_nox_cat_vals) > 550)
    )
    _regen_active = _regen_requested and _regen_enabled and _thermal_regen

    # Within-file detection: distance counter reset (dropped by ≥90% from a
    # non-trivial starting value) signals a completed regeneration.
    _dist_reset_in_trip = False
    if len(_dist_regen_recs) >= 2:
        _d_first = _dist_regen_recs[0][1]
        if _d_first > 20:
            for _, _dv in _dist_regen_recs[1:]:
                if _dv < _d_first * 0.1:
                    _dist_reset_in_trip = True
                    break

    _soot_end = _soot_closed_vals[-1] if _soot_closed_vals else None
    _dist_end = _dist_regen_recs[-1][1] if _dist_regen_recs else None

    # Detect post-regen cooldown that started before recording: dist counter
    # opens at 0 (or near-0) and EGT is still high → regen completed just
    # before this log began. Works even when RBS correction is disabled.
    _cooldown_started = (
        bool(_dist_regen_recs) and _dist_regen_recs[0][1] < 1.0
        and _thermal_regen and not _regen_requested
    )

    if _regen_active and (_dist_reset_in_trip or (_soot_end is not None and _soot_end <= 0.5)):
        _regen_state = "completed"
    elif _regen_active:
        _regen_state = "active"
    elif _regen_requested and not _thermal_regen:
        _regen_state = "requested"
    elif (_dist_end is not None and _dist_end < 20 and not _regen_active) or _cooldown_started:
        _regen_state = "post_regen"
    else:
        _regen_state = "idle"
    result["obd_dpf_regen_state"] = _regen_state

    # ── Generic stats for every PID (slug-keyed) ─────────────────────────────
    pid_catalog: dict[str, dict[str, Any]] = {}
    extra: dict[str, dict[str, Any]] = {}
    for pid_name, recs in pids.items():
        window_recs = [(s, v) for s, v in recs if t_start <= s <= (t_end or s)]
        vals = [v for _, v in window_recs]
        if not vals:
            continue
        slug = _slugify_pid(pid_name)
        unit = units.get(pid_name)
        kind = _classify_pid(vals, unit)
        mode_val = _mode(vals)

        times = [s for s, _ in window_recs]
        t_first = times[0]
        t_last = times[-1]
        covered_span = t_last - t_first
        age_from_end = (t_end or t_start) - t_last
        cov_pct = round(covered_span / max(duration_s, 1.0) * 100.0, 1) if duration_s > 0 else 0.0
        rate_hz = round(len(vals) / max(covered_span, 1.0), 3)

        pid_catalog[slug] = {"name": pid_name, "unit": unit, "kind": kind}
        extra[slug] = {
            "last": round(vals[-1], 3),
            "first": round(vals[0], 3),
            "min": round(min(vals), 3),
            "max": round(max(vals), 3),
            "mean": round(sum(vals) / len(vals), 3),
            "mode": mode_val,
            "samples": len(vals),
            "kind": kind,
            "first_seen_s": round(t_first - t_start, 1),
            "last_seen_s": round(t_last - t_start, 1),
            "age_from_trip_end_s": round(age_from_end, 1),
            "coverage_pct": cov_pct,
            "sample_rate_hz": rate_hz,
            "is_stale": age_from_end > 60.0,
        }
    result["obd_pid_values"] = extra
    result["_pid_catalog"] = pid_catalog

    # ── Trip start timestamp from filename pattern YYYYMMDD_HHMMSS ───────────
    m = re.search(r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})", path.stem)
    if m:
        try:
            result["obd_trip_start"] = datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                int(m.group(4)), int(m.group(5)), int(m.group(6)),
                tzinfo=timezone.utc,
            ).isoformat()
        except ValueError:
            result["obd_trip_start"] = None
    else:
        result["obd_trip_start"] = None

    return result


def _mode(vals: list[float]) -> float:
    """Return the most frequently occurring value. Ties broken by first seen."""
    counts: dict[float, int] = {}
    for v in vals:
        counts[v] = counts.get(v, 0) + 1
    return max(counts, key=lambda k: counts[k])


_KIND_RANK = {"bool": 0, "discrete": 1, "number": 2}


def _merge_kind(prev: str | None, new: str) -> str:
    """Return the higher-rank kind (promotes toward 'number' on any conflict)."""
    if prev is None:
        return new
    return max(prev, new, key=lambda k: _KIND_RANK.get(k, 2))


def _classify_pid(vals: list[float], unit: str | None) -> str:
    """Return the PID kind: 'bool', 'discrete', or 'number'.

    - bool:     all samples are 0 or 1 AND the PID has no physical unit
    - discrete: all samples are integer-valued AND ≤ 32 distinct values
                AND the PID has no physical unit (e.g. gear, mode flag)
    - number:   everything else — any PID with a unit is always number
    """
    has_unit = bool(unit)  # any non-empty unit string means physical quantity
    if not has_unit and all(v in (0.0, 1.0) for v in vals):
        return "bool"
    unique = set(vals)
    if not has_unit and all(v == int(v) for v in unique) and len(unique) <= 32:
        return "discrete"
    return "number"


def _trapezoid_integrate_lph(
    recs: list[tuple[float, float]],
    t_start: float,
    t_end: float,
    max_lph: float = 200.0,
) -> float | None:
    """Time-integrate L/h samples inside the engine window → total litres.

    Uses the trapezoid rule so uneven sampling doesn't bias the result.
    Samples outside the window or above max_lph are discarded.
    Returns None when fewer than two valid samples exist.
    """
    window = sorted(
        ((t, v) for t, v in recs if t_start <= t <= t_end and 0.0 <= v < max_lph),
        key=lambda r: r[0],
    )
    if len(window) < 2:
        return None
    return sum(
        (window[i][1] + window[i + 1][1]) / 2.0
        * (window[i + 1][0] - window[i][0])
        / 3600.0
        for i in range(len(window) - 1)
    )


def _aggregate(vals: list[float], agg: str) -> float:
    if agg == "last":
        return vals[-1]
    if agg == "first":
        return vals[0]
    if agg == "max":
        return max(vals)
    if agg == "min":
        return min(vals)
    return sum(vals) / len(vals)
