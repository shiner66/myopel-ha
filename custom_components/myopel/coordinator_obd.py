"""OBD coordinator for MyOpel — reads CarScanner CSV exports."""
from __future__ import annotations

import csv
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

# PIDs used to determine the engine-on window (reliable OBD, not GPS).
# First match wins.
_ENGINE_ANCHOR_PIDS = ("Giri motore", "Distanza percorsa:", "Velocità veicolo")

# Map from coordinator data key → (PID name in CSV, aggregation)
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


class _NoObdFileYet(Exception):
    """Raised when the folder has no CSV files — not a fatal error."""


class MyOpelObdCoordinator(DataUpdateCoordinator):
    """Coordinator that reads the most recent CarScanner CSV and extracts trip stats."""

    def __init__(
        self,
        hass: HomeAssistant,
        folder_path: str,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="myopel_obd",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.folder_path = folder_path
        # (path_str, mtime) of the last successfully parsed file; avoids
        # re-reading an unchanged CSV on every polling cycle.
        self._last_parsed: tuple[str, float] | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.hass.async_add_executor_job(self._parse_latest_csv)
        except _NoObdFileYet:
            _LOGGER.debug("MyOpel OBD: nessun CSV ancora in %s", self.folder_path)
            return {}
        except Exception as err:
            raise UpdateFailed(f"OBD CSV parse error: {err}") from err

    def _parse_latest_csv(self) -> dict[str, Any]:
        folder = Path(self.folder_path)
        folder.mkdir(parents=True, exist_ok=True)

        csvs = sorted(folder.glob("*.csv"), key=lambda p: p.stat().st_mtime)
        if not csvs:
            raise _NoObdFileYet

        path = csvs[-1]
        mtime = path.stat().st_mtime
        if self._last_parsed == (str(path), mtime):
            _LOGGER.debug("MyOpel OBD: %s invariato, skip rielaborazione", path.name)
            return self.data or {}

        _LOGGER.debug("MyOpel OBD: lettura %s", path.name)

        pids: dict[str, list[tuple[float, float, float | None, float | None]]] = {}
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
                    lat = float(row[4]) if len(row) > 4 and row[4].strip() else None
                    lon = float(row[5]) if len(row) > 5 and row[5].strip() else None
                except (ValueError, IndexError):
                    continue
                pids.setdefault(pid, []).append((sec, val, lat, lon))

        if not pids:
            raise UpdateFailed("OBD CSV is empty")

        result = _compute_stats(pids, path)
        self._last_parsed = (str(path), mtime)
        return result


# ── Stats computation ────────────────────────────────────────────────────────

def _compute_stats(
    pids: dict[str, list[tuple[float, float, float | None, float | None]]],
    path: Path,
) -> dict[str, Any]:
    # Determine engine-on window from anchor PIDs
    t_start: float | None = None
    t_end: float | None = None
    for anchor in _ENGINE_ANCHOR_PIDS:
        recs = pids.get(anchor)
        if recs:
            t_start = min(s for s, _, _, _ in recs)
            t_end   = max(s for s, _, _, _ in recs)
            break
    if t_start is None:
        all_secs = [s for recs in pids.values() for s, _, _, _ in recs]
        t_start = min(all_secs) if all_secs else 0.0
        t_end   = max(all_secs) if all_secs else 0.0

    duration_s = (t_end or 0.0) - (t_start or 0.0)

    def _vals(pid_name: str) -> list[float]:
        return [v for s, v, _, _ in pids.get(pid_name, [])
                if t_start <= s <= (t_end or s)]

    result: dict[str, Any] = {
        "obd_filename": path.name,
        "obd_trip_duration_min": round(duration_s / 60.0, 1),
    }

    # Fuel flow readings saturate at ~255 on many ECUs; cap before averaging.
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
        if agg == "last":
            raw = vals[-1]
        elif agg == "first":
            raw = vals[0]
        elif agg == "max":
            raw = max(vals)
        elif agg == "min":
            raw = min(vals)
        else:  # mean
            raw = sum(vals) / len(vals)
        result[key] = round(raw, 2 if key.endswith(("_km", "_lph")) else 1)

    # Coerce odometer and RPM to int
    if result.get("obd_trip_odometer_km") is not None:
        result["obd_trip_odometer_km"] = int(result["obd_trip_odometer_km"])
    if result.get("obd_trip_avg_rpm") is not None:
        result["obd_trip_avg_rpm"] = int(result["obd_trip_avg_rpm"])
    if result.get("obd_trip_max_rpm") is not None:
        result["obd_trip_max_rpm"] = int(result["obd_trip_max_rpm"])

    # Trip start timestamp from filename pattern YYYYMMDD_HHMMSS
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
