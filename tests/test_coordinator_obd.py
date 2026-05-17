"""Tests for the OBD coordinator: CSV parsing, persistence, file deletion."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_components.myopel.coordinator_obd import (
    MyOpelObdCoordinator,
    _compute_stats,
    _parse_csv_file,
    _slugify_pid,
)


# ── Test helpers ──────────────────────────────────────────────────────────────

CSV_HEADER = "Time;PID;Value;Unit;Lat;Lon\n"


def _write_csv(folder: Path, name: str, rows: list[tuple[float, str, float, str]]) -> Path:
    path = folder / name
    lines = [CSV_HEADER]
    for sec, pid, val, unit in rows:
        lines.append(f"{sec};{pid};{val};{unit};;\n")
    path.write_text("".join(lines), encoding="utf-8")
    return path


# ── Slugify ───────────────────────────────────────────────────────────────────

class TestSlugify:
    def test_simple_name(self):
        assert _slugify_pid("Giri motore") == "giri_motore"

    def test_with_brackets_and_special_chars(self):
        assert _slugify_pid(
            "[ECM] Soot clogging level"
        ) == "ecm_soot_clogging_level"

    def test_degrees_replaced(self):
        assert _slugify_pid("Temperatura °C") == "temperatura_degc"


# ── Pure compute_stats ───────────────────────────────────────────────────────

class TestComputeStats:
    def test_curated_pid_extraction(self, tmp_path):
        pids = {
            "Giri motore": [(0.0, 800.0), (1.0, 4000.0), (2.0, 2500.0)],
            "Distanza percorsa:": [(0.0, 0.0), (2.0, 12.3)],
        }
        result = _compute_stats(pids, {"Giri motore": "rpm"}, tmp_path / "x.csv")
        assert result["obd_trip_avg_rpm"] == int((800 + 4000 + 2500) / 3)
        assert result["obd_trip_max_rpm"] == 4000
        assert result["obd_trip_distance_km"] == 12.3

    def test_unknown_pid_lands_in_obd_pid_values(self, tmp_path):
        pids = {
            # engine-on window spans 0..2 seconds via the anchor PID
            "Giri motore": [(0.0, 800.0), (1.0, 4000.0), (2.0, 2000.0)],
            "Tensione del MAP": [(0.0, 1.2), (1.0, 2.4), (2.0, 1.8)],
        }
        result = _compute_stats(pids, {"Tensione del MAP": "V"}, tmp_path / "x.csv")
        slug = _slugify_pid("Tensione del MAP")
        extra = result["obd_pid_values"][slug]
        assert extra["min"] == 1.2
        assert extra["max"] == 2.4
        assert extra["last"] == 1.8
        assert extra["samples"] == 3
        catalog = result["_pid_catalog"][slug]
        assert catalog["name"] == "Tensione del MAP"
        assert catalog["unit"] == "V"
        assert catalog["kind"] == "number"

    def test_boolean_pid_detected(self, tmp_path):
        pids = {
            "Giri motore": [(0.0, 800.0), (1.0, 1500.0), (2.0, 2000.0)],
            "DPF active flag": [(0.0, 0.0), (1.0, 1.0), (2.0, 0.0)],
        }
        result = _compute_stats(pids, {}, tmp_path / "x.csv")
        slug = _slugify_pid("DPF active flag")
        assert result["_pid_catalog"][slug]["kind"] == "bool"
        assert result["obd_pid_values"][slug]["kind"] == "bool"

    def test_numeric_pid_with_unit_is_number(self, tmp_path):
        # A PID with a physical unit is always "number", even if all integer-valued.
        pids = {
            "Giri motore": [(0.0, 800.0), (1.0, 1500.0), (2.0, 2000.0)],
            "Temperatura": [(0.0, 20.0), (1.0, 55.0), (2.0, 90.0)],
        }
        result = _compute_stats(pids, {"Temperatura": "°C"}, tmp_path / "x.csv")
        slug = _slugify_pid("Temperatura")
        assert result["_pid_catalog"][slug]["kind"] == "number"

    def test_percentage_unit_never_boolean(self, tmp_path):
        # A PID in % must never be bool or discrete regardless of values seen.
        pids = {
            "Giri motore": [(0.0, 800.0), (1.0, 1500.0)],
            "Pedale freno": [(0.0, 0.0), (1.0, 1.0)],
        }
        result = _compute_stats(pids, {"Pedale freno": "%"}, tmp_path / "x.csv")
        slug = _slugify_pid("Pedale freno")
        assert result["_pid_catalog"][slug]["kind"] == "number"

    def test_discrete_unitless_integer_pid(self, tmp_path):
        # Unitless integer-valued PID with ≤ 32 unique values → discrete (e.g. gear)
        pids = {
            "Giri motore": [(0.0, 800.0), (1.0, 1500.0), (2.0, 2000.0)],
            "Engaged gear": [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0)],
        }
        result = _compute_stats(pids, {}, tmp_path / "x.csv")
        slug = _slugify_pid("Engaged gear")
        assert result["_pid_catalog"][slug]["kind"] == "discrete"

    def test_discrete_mode_used_as_state(self, tmp_path):
        # Mode (most frequent) is computed and stored for discrete PIDs.
        pids = {
            "Giri motore": [(0.0, 800.0), (1.0, 1000.0), (2.0, 900.0), (3.0, 850.0)],
            "Engaged gear": [(0.0, 3.0), (1.0, 4.0), (2.0, 3.0), (3.0, 3.0)],
        }
        result = _compute_stats(pids, {}, tmp_path / "x.csv")
        slug = _slugify_pid("Engaged gear")
        # Gear 3 appeared 3 times, gear 4 once → mode = 3
        assert result["obd_pid_values"][slug]["mode"] == 3.0

    def test_filename_timestamp_iso(self, tmp_path):
        pids = {"Giri motore": [(0.0, 800.0)]}
        path = tmp_path / "abc-20260517_014721.csv"
        path.touch()
        result = _compute_stats(pids, {}, path)
        assert result["obd_trip_start"] == "2026-05-17T01:47:21+00:00"

    def test_reliability_attrs_present(self, tmp_path):
        # A PID sampled at 0s and 50s in a 200s trip.
        pids = {
            "Giri motore": [(0.0, 800.0), (100.0, 1500.0), (200.0, 2000.0)],
            "Slow PID": [(0.0, 1.0), (50.0, 2.0)],
        }
        result = _compute_stats(pids, {"Slow PID": "V"}, tmp_path / "x.csv")
        slug = _slugify_pid("Slow PID")
        stats = result["obd_pid_values"][slug]
        assert "first_seen_s" in stats
        assert "last_seen_s" in stats
        assert "age_from_trip_end_s" in stats
        assert "coverage_pct" in stats
        assert "sample_rate_hz" in stats
        assert "is_stale" in stats

    def test_stale_pid_flagged(self, tmp_path):
        # Engine runs 0-200s; Slow PID last seen at 50s → age=150s > 60 → stale.
        pids = {
            "Giri motore": [(0.0, 800.0), (100.0, 1500.0), (200.0, 2000.0)],
            "Slow PID": [(0.0, 1.0), (50.0, 2.0)],
        }
        result = _compute_stats(pids, {"Slow PID": "V"}, tmp_path / "x.csv")
        slug = _slugify_pid("Slow PID")
        stats = result["obd_pid_values"][slug]
        assert stats["age_from_trip_end_s"] == 150.0
        assert stats["is_stale"] is True
        assert stats["coverage_pct"] == 25.0  # 50s covered / 200s total

    def test_fresh_pid_not_stale(self, tmp_path):
        # Engine runs 0-200s; Fresh PID last seen at 190s → age=10s ≤ 60 → not stale.
        pids = {
            "Giri motore": [(0.0, 800.0), (100.0, 1500.0), (200.0, 2000.0)],
            "Fresh PID": [(100.0, 5.0), (190.0, 6.0)],
        }
        result = _compute_stats(pids, {"Fresh PID": "V"}, tmp_path / "x.csv")
        slug = _slugify_pid("Fresh PID")
        stats = result["obd_pid_values"][slug]
        assert stats["age_from_trip_end_s"] == 10.0
        assert stats["is_stale"] is False

    def test_soot_outlier_filtered(self, tmp_path):
        # One valid reading (75%), one outlier (1076%). Only 75% should survive.
        pids = {
            "Giri motore": [(0.0, 800.0), (1.0, 1500.0)],
            "[ECM] Soot clogging level of diesel particulate filter": [
                (0.0, 75.0), (1.0, 1076.27),
            ],
        }
        result = _compute_stats(pids, {}, tmp_path / "x.csv")
        assert result["obd_trip_dpf_soot_pct"] == 75.0

    def test_dpf_since_regen_not_in_preset(self, tmp_path):
        # Broken PID was removed from the curated preset — its key must be absent.
        pids = {
            "Giri motore": [(0.0, 800.0)],
            "[ECM] Distance traveled since the last regeneration": [(0.0, 9999.0)],
        }
        result = _compute_stats(pids, {}, tmp_path / "x.csv")
        assert "obd_trip_dpf_since_regen_km" not in result


# ── End-to-end parse + persistence ───────────────────────────────────────────

class TestCoordinatorPersistence:
    def test_parse_persist_and_delete(self, tmp_path):
        # Write two CSVs
        f1 = _write_csv(tmp_path, "a-20260101_120000.csv", [
            (0.0, "Giri motore", 800.0, "rpm"),
            (1.0, "Distanza percorsa:", 5.5, "km"),
            (2.0, "Giri motore", 1500.0, "rpm"),
        ])
        f2 = _write_csv(tmp_path, "b-20260102_120000.csv", [
            (0.0, "Giri motore", 1000.0, "rpm"),
            (1.0, "Distanza percorsa:", 7.7, "km"),
            (2.0, "Giri motore", 2000.0, "rpm"),
        ])

        hass = MagicMock()
        hass.async_add_executor_job = lambda func, *a: _run_in_thread(func, *a)
        coord = MyOpelObdCoordinator(
            hass, str(tmp_path), scan_interval=60, entry_id="ent1",
            delete_after_parse=True,
        )

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coord.async_load_persisted())
            data = loop.run_until_complete(coord._async_update_data())
        finally:
            loop.close()

        # Latest = f2 (parsed second). Files have been deleted.
        assert data["obd_filename"] == "b-20260102_120000.csv"
        assert data["obd_trip_distance_km"] == 7.7
        assert not f1.exists()
        assert not f2.exists()

        # PID catalog populated.
        catalog = coord.discovered_pids
        assert _slugify_pid("Giri motore") in catalog
        assert _slugify_pid("Distanza percorsa:") in catalog

        # History contains both trips.
        assert len(coord._history) == 2

    def test_disabled_deletion_keeps_files(self, tmp_path):
        f1 = _write_csv(tmp_path, "a-20260101_120000.csv", [
            (0.0, "Giri motore", 800.0, "rpm"),
            (1.0, "Giri motore", 1500.0, "rpm"),
        ])

        hass = MagicMock()
        hass.async_add_executor_job = lambda func, *a: _run_in_thread(func, *a)
        coord = MyOpelObdCoordinator(
            hass, str(tmp_path), scan_interval=60, entry_id="ent2",
            delete_after_parse=False,
        )

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coord.async_load_persisted())
            loop.run_until_complete(coord._async_update_data())
        finally:
            loop.close()

        assert f1.exists()

    def test_persisted_data_survives_restart(self, tmp_path):
        _write_csv(tmp_path, "a-20260101_120000.csv", [
            (0.0, "Giri motore", 800.0, "rpm"),
            (1.0, "Distanza percorsa:", 5.5, "km"),
            (2.0, "Giri motore", 1500.0, "rpm"),
        ])

        hass = MagicMock()
        hass.async_add_executor_job = lambda func, *a: _run_in_thread(func, *a)

        # First "boot": parse and persist
        coord1 = MyOpelObdCoordinator(
            hass, str(tmp_path), 60, entry_id="restart_test",
            delete_after_parse=True,
        )
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coord1.async_load_persisted())
            loop.run_until_complete(coord1._async_update_data())
        finally:
            loop.close()

        # Pull the Store from coord1 and reuse the same in-memory backing for coord2.
        # The conftest Store keeps state on the instance — emulate persistence by
        # injecting the saved payload directly.
        saved_payload = coord1._store._data

        coord2 = MyOpelObdCoordinator(
            hass, str(tmp_path), 60, entry_id="restart_test",
            delete_after_parse=True,
        )
        coord2._store._data = saved_payload

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coord2.async_load_persisted())
        finally:
            loop.close()

        # No CSV on disk yet — but the latest trip survives.
        assert coord2.data["obd_trip_distance_km"] == 5.5
        assert coord2.discovered_pids  # PID catalog also persisted


def _run_in_thread(func, *args):
    """Synchronous shim for hass.async_add_executor_job in tests."""
    fut = asyncio.Future()
    try:
        fut.set_result(func(*args))
    except Exception as exc:
        fut.set_exception(exc)
    return fut
