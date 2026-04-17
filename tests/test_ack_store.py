"""Tests for the AlertAckStore persistence layer."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# conftest.py injects the HA stubs (including Store) before these imports.
from custom_components.myopel.ack_store import AlertAckStore


@pytest.fixture
def store() -> AlertAckStore:
    """Fresh store backed by the in-memory Store stub."""
    return AlertAckStore(MagicMock(), entry_id="entry_test")


class TestLoadSave:

    async def test_load_empty(self, store: AlertAckStore) -> None:
        await store.async_load()
        assert store.acked_codes_for(trip_id=42) == []

    async def test_ack_then_load_roundtrip(self, store: AlertAckStore) -> None:
        await store.async_load()
        await store.async_ack(trip_id=42, code=52)
        await store.async_ack(trip_id=42, code=14)

        fresh = AlertAckStore(MagicMock(), entry_id="entry_test")
        fresh._store = store._store  # share backend to simulate persistence
        await fresh.async_load()
        assert fresh.acked_codes_for(42) == [14, 52]

    async def test_malformed_entries_are_skipped(self, store: AlertAckStore) -> None:
        store._store._data = {"acks": [[42, 52], ["bad", 14], [1], None, [1, "x"]]}
        await store.async_load()
        assert store.acked_codes_for(42) == [52]


class TestAckLifecycle:

    async def test_ack_returns_true_first_time(self, store: AlertAckStore) -> None:
        await store.async_load()
        assert await store.async_ack(1, 52) is True

    async def test_ack_returns_false_when_already_set(self, store: AlertAckStore) -> None:
        await store.async_load()
        await store.async_ack(1, 52)
        assert await store.async_ack(1, 52) is False

    async def test_is_acked_reflects_state(self, store: AlertAckStore) -> None:
        await store.async_load()
        await store.async_ack(7, 14)
        assert store.is_acked(7, 14) is True
        assert store.is_acked(7, 52) is False
        assert store.is_acked(8, 14) is False  # different trip

    async def test_ack_many_counts_only_new(self, store: AlertAckStore) -> None:
        await store.async_load()
        assert await store.async_ack_many(1, [52, 14]) == 2
        assert await store.async_ack_many(1, [14, 22]) == 1  # 14 already acked
        assert store.acked_codes_for(1) == [14, 22, 52]

    async def test_ack_many_skips_invalid_codes(self, store: AlertAckStore) -> None:
        await store.async_load()
        # Mix valid ints with garbage — the store should ignore the garbage.
        added = await store.async_ack_many(1, [52, "bad", None, 14])
        assert added == 2
        assert store.acked_codes_for(1) == [14, 52]


class TestUnackReset:

    async def test_unack_removes_only_that_pair(self, store: AlertAckStore) -> None:
        await store.async_load()
        await store.async_ack_many(1, [52, 14])
        assert await store.async_unack(1, 52) is True
        assert store.acked_codes_for(1) == [14]

    async def test_unack_returns_false_when_missing(self, store: AlertAckStore) -> None:
        await store.async_load()
        assert await store.async_unack(1, 99) is False

    async def test_reset_clears_everything(self, store: AlertAckStore) -> None:
        await store.async_load()
        await store.async_ack_many(1, [52, 14])
        await store.async_ack(2, 22)
        await store.async_reset()
        assert store.acked_codes_for(1) == []
        assert store.acked_codes_for(2) == []


class TestTripIdCoercion:

    async def test_none_trip_id_coerced_to_sentinel(self, store: AlertAckStore) -> None:
        await store.async_load()
        await store.async_ack(None, 52)
        assert store.is_acked(None, 52) is True
        # A real trip id should NOT collide with the sentinel bucket
        assert store.is_acked(0, 52) is False

    async def test_string_trip_id_coerced_to_int(self, store: AlertAckStore) -> None:
        await store.async_load()
        await store.async_ack("123", 52)
        assert store.is_acked(123, 52) is True

    async def test_invalid_trip_id_falls_to_sentinel(self, store: AlertAckStore) -> None:
        await store.async_load()
        await store.async_ack("not-a-number", 52)
        assert store.is_acked(None, 52) is True
