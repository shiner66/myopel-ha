"""Tests for imap_fetcher helpers.

The IMAP I/O itself isn't exercised — we only cover the pure-Python helpers
that guard against snapshot accumulation, which is where the oscillating
sensor bug originated.
"""
from __future__ import annotations

from pathlib import Path

# conftest.py stubs HA modules so this import succeeds without homeassistant.
from custom_components.myopel.imap_fetcher import _cleanup_stale_snapshots


class TestCleanupStaleSnapshots:

    def test_removes_other_myop_files(self, tmp_path: Path):
        keep = tmp_path / "current.myop"
        old_a = tmp_path / "old-a.myop"
        old_b = tmp_path / "old-b.myop"
        for p in (keep, old_a, old_b):
            p.write_bytes(b"snapshot")

        removed = _cleanup_stale_snapshots(tmp_path, keep.name)

        assert removed == 2
        assert keep.exists()
        assert not old_a.exists()
        assert not old_b.exists()

    def test_does_not_touch_non_myop_files(self, tmp_path: Path):
        keep = tmp_path / "current.myop"
        unrelated = tmp_path / "trips.json"
        export = tmp_path / "trips.export"
        for p in (keep, unrelated, export):
            p.write_bytes(b"data")

        _cleanup_stale_snapshots(tmp_path, keep.name)

        assert keep.exists()
        assert unrelated.exists()
        assert export.exists()

    def test_nothing_to_remove_when_only_target_exists(self, tmp_path: Path):
        keep = tmp_path / "current.myop"
        keep.write_bytes(b"snapshot")

        removed = _cleanup_stale_snapshots(tmp_path, keep.name)

        assert removed == 0
        assert keep.exists()

    def test_missing_target_still_cleans_others(self, tmp_path: Path):
        """If the target file isn't on disk (e.g. payload write failed earlier),
        we still drop every other .myop sitting around — they're definitely stale."""
        old = tmp_path / "old.myop"
        old.write_bytes(b"snapshot")

        removed = _cleanup_stale_snapshots(tmp_path, "current.myop")

        assert removed == 1
        assert not old.exists()
