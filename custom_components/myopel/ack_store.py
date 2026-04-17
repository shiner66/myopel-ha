"""Persistence for acknowledged MyOpel alerts.

An acknowledgment is a `(trip_id, alert_code)` pair. When a trip containing
that alert is the latest one, the alert is considered "silenced" for
automation purposes, but remains visible in the Lovelace card so the user
can still review it. A new trip with the same code is NOT auto-acknowledged:
the acknowledgment is tied to the specific trip_id it was seen in.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import ACK_STORAGE_KEY_TPL, ACK_STORAGE_VERSION, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Sentinel trip_id for "no trip id available" (acknowledgments for alerts
# coming from a trip that lacks an `id` field).
_NO_TRIP: int = -1


def _normalize_trip_id(trip_id: Any) -> int:
    """Coerce trip_id to int, using sentinel when missing/invalid."""
    try:
        return int(trip_id) if trip_id is not None else _NO_TRIP
    except (TypeError, ValueError):
        return _NO_TRIP


class AlertAckStore:
    """Persistent set of acknowledged (trip_id, alert_code) pairs per config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store = Store(
            hass,
            ACK_STORAGE_VERSION,
            ACK_STORAGE_KEY_TPL.format(entry_id=entry_id),
        )
        self._acks: set[tuple[int, int]] = set()

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        raw = data.get("acks", []) or []
        acks: set[tuple[int, int]] = set()
        for item in raw:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            trip_id, code = item
            if not isinstance(code, int):
                continue
            acks.add((_normalize_trip_id(trip_id), code))
        self._acks = acks
        _LOGGER.debug("%s: caricati %d ack alert", DOMAIN, len(self._acks))

    async def async_save(self) -> None:
        await self._store.async_save(
            {"acks": [[t, c] for (t, c) in sorted(self._acks)]}
        )

    def is_acked(self, trip_id: Any, code: int) -> bool:
        return (_normalize_trip_id(trip_id), int(code)) in self._acks

    def acked_codes_for(self, trip_id: Any) -> list[int]:
        tid = _normalize_trip_id(trip_id)
        return sorted({c for (t, c) in self._acks if t == tid})

    async def async_ack(self, trip_id: Any, code: int) -> bool:
        """Acknowledge a single (trip_id, code) pair. Returns True if newly added."""
        key = (_normalize_trip_id(trip_id), int(code))
        if key in self._acks:
            return False
        self._acks.add(key)
        await self.async_save()
        return True

    async def async_unack(self, trip_id: Any, code: int) -> bool:
        """Remove a single ack. Returns True if something was removed."""
        key = (_normalize_trip_id(trip_id), int(code))
        if key not in self._acks:
            return False
        self._acks.discard(key)
        await self.async_save()
        return True

    async def async_ack_many(self, trip_id: Any, codes: list[int]) -> int:
        """Acknowledge multiple codes for a trip. Returns number of NEW acks."""
        tid = _normalize_trip_id(trip_id)
        before = len(self._acks)
        for code in codes:
            try:
                self._acks.add((tid, int(code)))
            except (TypeError, ValueError):
                continue
        added = len(self._acks) - before
        if added:
            await self.async_save()
        return added

    async def async_reset(self) -> None:
        self._acks.clear()
        await self.async_save()
