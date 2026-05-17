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
# First match wins.
_ENGINE_ANCHOR_PIDS = ("Giri motore", "Distanza percorsa:", "Velocità veicolo")

# Curated "preset" PIDs that get well-known sensor keys. Other PIDs are exposed
# under a slugified key (see `_slugify_pid`) and only become sensors if the user
# enables them from the options flow.
#   coordinator data key → (PID name in CSV, aggregation, unit hint)
# aggregations: "last", "max", "min", "mean", "first"
_PID_MAP: dict[str, tuple[str, str]] = {
    # ── Basic trip ────────────────────────────────────────────────────────────
    "obd_trip_distance_km":           ("Distanza percorsa:",                                              "last"),
    "obd_trip_avg_speed_kmh":         ("Velocità (GPS)",                                                  "mean"),
    "obd_trip_max_speed_kmh":         ("Velocità (GPS)",                                                  "max"),
    # ── Engine ───────────────────────────────────────────────────────────────
    "obd_trip_avg_rpm":               ("Giri motore",                                                     "mean"),
    "obd_trip_max_rpm":               ("Giri motore",                                                     "max"),
    "obd_trip_coolant_temp_max_c":    ("Temperatura liquido raffreddamento motore",                       "max"),
    "obd_trip_oil_temp_max_c":        ("[ECM] Oil temperature",                                           "max"),
    "obd_trip_avg_fuel_lph":          ("Consumo istantaneo di carburante calcolato",                      "mean"),
    "obd_trip_odometer_km":           ("[ECM] Total mileage",                                             "last"),
    "obd_trip_air_temp_c":            ("Temperatura d'aria ambiente",                                     "first"),
    # ── DPF / emissions ──────────────────────────────────────────────────────
    "obd_trip_dpf_soot_pct":          ("[ECM] Soot clogging level of diesel particulate filter",          "last"),
    "obd_trip_dpf_regen_active":      ("[ECM] DPF regeneration status",                                   "max"),
    "obd_trip_dpf_since_regen_km":    ("[ECM] Distance traveled since the last regeneration",             "last"),
    "obd_trip_dpf_regen_capability":  ("[ECM] Long-term regeneration capability",                         "last"),
    "obd_trip_adblue_vol_l":          ("[ECM] Volume of urea solution measured in urea tank",             "last"),
    "obd_trip_exhaust_after_cat_c":   ("[ECM] Exhaust gas temperature after pre-catalytic converter",     "max"),
    # ── Diagnostics ──────────────────────────────────────────────────────────
    "obd_trip_battery_startup_v":     ("[ECM] Minimum battery voltage at startup",                        "last"),
    "obd_trip_ss_switch":             ("[ECM] Stop and Start switch",                                     "last"),
    "obd_trip_oil_dilution_pct":      ("[ECM] Evaluation of the degree of dilution of motor oil",         "last"),
}

# Reverse lookup: PID name → list of (data_key, agg)
_NAME_TO_KEYS: dict[str, list[tuple[str, str]]] = {}
for _k, (_n, _a) in _PID_MAP.items():
    _NAME_TO_KEYS.setdefault(_n, []).append((_k, _a))


# ── Helpers ──────────────────────────────────────────────────────────────────

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

        # Update history + latest + pid catalog
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

        csvs = sorted(folder.glob("*.csv"), key=lambda p: p.stat().st_mtime)
        if not csvs:
            raise _NoObdFileYet

        results: list[dict[str, Any]] = []
        for path in csvs:
            try:
                result = _parse_csv_file(path)
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

def _parse_csv_file(path: Path) -> dict[str, Any]:
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
    _FUEL_MAX = 200.0
    for key, (pid_name, agg) in _PID_MAP.items():
        vals = _vals(pid_name)
        if not vals:
            result[key] = None
            continue
        if key == "obd_trip_avg_fuel_lph":
            vals = [v for v in vals if v < _FUEL_MAX]
            if not vals:
                result[key] = None
                continue
        result[key] = round(_aggregate(vals, agg), 2 if key.endswith(("_km", "_lph")) else 1)

    # Coerce integer-like quantities
    for k in ("obd_trip_odometer_km", "obd_trip_avg_rpm", "obd_trip_max_rpm"):
        if result.get(k) is not None:
            result[k] = int(result[k])

    # ── Generic stats for every PID (slug-keyed) ─────────────────────────────
    pid_catalog: dict[str, dict[str, Any]] = {}
    extra: dict[str, dict[str, Any]] = {}
    for pid_name, recs in pids.items():
        vals = [v for s, v in recs if t_start <= s <= (t_end or s)]
        if not vals:
            continue
        slug = _slugify_pid(pid_name)
        unit = units.get(pid_name)
        kind = _classify_pid(vals, unit)
        mode_val = _mode(vals)
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
