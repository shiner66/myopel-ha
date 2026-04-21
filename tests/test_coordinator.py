"""Tests for MyOpelCoordinator._parse_file — trip merging across snapshots.

These tests focus on the multi-file merge behaviour introduced to fix the
oscillating fuel-level bug: the MyOpel IMAP feed sends one snapshot per email,
and when several snapshots coexist in the drop folder the coordinator must
deterministically use the union of their trips instead of whichever file
happens to have the highest mtime at refresh time.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# conftest.py stubs HA modules before this import.
from custom_components.myopel import MyOpelCoordinator, _NoFileYet


def _write_snapshot(folder: Path, name: str, vin: str, trips: list[dict], mtime: float) -> Path:
    """Write a .myop-style snapshot and set its mtime (controls merge order)."""
    path = folder / name
    path.write_text(json.dumps([{"vin": vin, "trips": trips}]), encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def _make_coordinator(folder: Path) -> MyOpelCoordinator:
    return MyOpelCoordinator(
        hass=MagicMock(),
        file_path=str(folder),
        scan_interval=300,
        min_trip_distance=0.0,
        ack_store=None,
    )


def _trip(tid: int, end: str, fuel_level: int, distance: float = 5.0) -> dict:
    """Build a minimal trip record for testing."""
    return {
        "id": tid,
        "start": {"date": end.replace("T10", "T09"), "mileage": 1000 + tid},
        "end": {"date": end, "mileage": 1000 + tid + int(distance)},
        "distance": distance,
        "travelTime": 600,
        "fuelLevel": fuel_level,
        "fuelAutonomy": fuel_level * 10,
    }


# ── Baseline: single-file parse still works ──────────────────────────────────

class TestSingleFile:

    def test_single_file_latest_trip_wins(self, tmp_path: Path):
        _write_snapshot(
            tmp_path, "a.myop", "VIN123",
            trips=[
                _trip(1, "2024-04-20T10:00:00Z", fuel_level=55),
                _trip(2, "2024-04-21T10:00:00Z", fuel_level=47),
            ],
            mtime=1000,
        )
        data = _make_coordinator(tmp_path)._parse_file()
        assert data["vin"] == "VIN123"
        assert data["last_trip_id"] == 2
        assert data["fuel_level_pct"] == 47

    def test_empty_folder_raises_nofile(self, tmp_path: Path):
        with pytest.raises(_NoFileYet):
            _make_coordinator(tmp_path)._parse_file()


# ── Multi-file merge: the fuel-oscillation bug fix ───────────────────────────

class TestMultiFileMerge:

    def test_latest_trip_picked_across_all_files_regardless_of_mtime(self, tmp_path: Path):
        """Newest trip must come from the union of trips, not from newest file.

        Regression for the oscillating sensor bug: if an older snapshot had
        the most recently modified mtime (because the IMAP poll re-wrote it
        last), we used to surface its stale "last trip" fuel level.
        """
        # File B is newer by mtime but contains only an older trip
        _write_snapshot(
            tmp_path, "a.myop", "VIN",
            trips=[_trip(10, "2024-04-21T18:00:00Z", fuel_level=62)],
            mtime=1000,  # older mtime
        )
        _write_snapshot(
            tmp_path, "b.myop", "VIN",
            trips=[_trip(9, "2024-04-20T09:00:00Z", fuel_level=47)],
            mtime=2000,  # newer mtime — used to "win" and surface 47%
        )
        data = _make_coordinator(tmp_path)._parse_file()
        # The truly latest trip by end date is in the older-mtime file
        assert data["last_trip_id"] == 10
        assert data["fuel_level_pct"] == 62
        assert data["total_trips"] == 2

    def test_overlapping_trip_ids_later_file_wins(self, tmp_path: Path):
        """When the same trip id appears in two snapshots, the newer-mtime
        file's copy wins (most recent reported state)."""
        _write_snapshot(
            tmp_path, "old.myop", "VIN",
            trips=[_trip(5, "2024-04-21T10:00:00Z", fuel_level=40)],
            mtime=1000,
        )
        _write_snapshot(
            tmp_path, "new.myop", "VIN",
            trips=[_trip(5, "2024-04-21T10:00:00Z", fuel_level=55)],
            mtime=2000,
        )
        data = _make_coordinator(tmp_path)._parse_file()
        assert data["total_trips"] == 1
        assert data["fuel_level_pct"] == 55

    def test_malformed_file_is_skipped(self, tmp_path: Path):
        (tmp_path / "broken.myop").write_text("{not valid json", encoding="utf-8")
        _write_snapshot(
            tmp_path, "ok.myop", "VIN",
            trips=[_trip(1, "2024-04-21T10:00:00Z", fuel_level=70)],
            mtime=2000,
        )
        data = _make_coordinator(tmp_path)._parse_file()
        assert data["fuel_level_pct"] == 70
        assert data["total_trips"] == 1

    def test_trip_without_id_is_skipped(self, tmp_path: Path):
        _write_snapshot(
            tmp_path, "a.myop", "VIN",
            trips=[
                {"end": {"date": "2024-04-21T10:00:00Z"}, "fuelLevel": 99},  # no id
                _trip(1, "2024-04-21T09:00:00Z", fuel_level=50),
            ],
            mtime=1000,
        )
        data = _make_coordinator(tmp_path)._parse_file()
        assert data["total_trips"] == 1
        assert data["last_trip_id"] == 1
        assert data["fuel_level_pct"] == 50
