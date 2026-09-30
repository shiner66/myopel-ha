"""Validation helpers for MyOpel trip snapshots."""
from __future__ import annotations

import json
import math
from typing import Any


class InvalidSnapshotError(ValueError):
    """Raised when a JSON document is not a supported MyOpel snapshot."""


_NUMERIC_TRIP_FIELDS = (
    "distance",
    "travelTime",
    "fuelConsumption",
    "priceFuel",
    "fuelLevel",
    "fuelAutonomy",
    "daysUntilNextMaintenance",
    "distanceToNextMaintenance",
)


def _normalize_number(value: Any) -> int | float | None:
    """Normalize a finite JSON number, including numeric strings."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def _normalize_trip(trip: dict[str, Any]) -> dict[str, Any] | None:
    """Return a coordinator-safe trip, or ``None`` for a malformed record."""
    trip_id = trip.get("id")
    if trip_id is not None and (
        isinstance(trip_id, bool) or not isinstance(trip_id, (int, str))
    ):
        return None

    normalized = dict(trip)
    for endpoint_key in ("start", "end"):
        endpoint = trip.get(endpoint_key, {})
        if not isinstance(endpoint, dict):
            return None
        endpoint = dict(endpoint)
        date = endpoint.get("date")
        if date is not None and not isinstance(date, str):
            return None
        mileage = endpoint.get("mileage")
        if mileage is not None:
            normalized_mileage = _normalize_number(mileage)
            if normalized_mileage is None:
                return None
            endpoint["mileage"] = normalized_mileage
        normalized[endpoint_key] = endpoint

    for field in _NUMERIC_TRIP_FIELDS:
        value = trip.get(field)
        if value is None:
            continue
        normalized_value = _normalize_number(value)
        if normalized_value is None:
            return None
        normalized[field] = normalized_value

    alerts = trip.get("alerts")
    if alerts is not None and not isinstance(alerts, list):
        return None
    return normalized


def normalize_vin(value: Any) -> str | None:
    """Return a normalized VIN, or ``None`` when the value is unusable."""
    if not isinstance(value, str):
        return None
    vin = value.strip().upper()
    return vin or None


def parse_snapshot(
    content: str | bytes,
    *,
    require_trips: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    """Parse and validate a MyOpel JSON snapshot.

    The export is a list whose first item describes one vehicle.  Individual
    trips without an id are tolerated here and ignored by the coordinator, but
    an IMAP attachment can require at least one usable trip before it replaces
    the last known-good file.
    """
    raw = json.loads(content)
    if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
        raise InvalidSnapshotError("invalid snapshot root")

    vehicle = raw[0]
    vin = normalize_vin(vehicle.get("vin"))
    trips = vehicle.get("trips")
    if vin is None or not isinstance(trips, list):
        raise InvalidSnapshotError("missing VIN or trips list")
    if any(not isinstance(trip, dict) for trip in trips):
        raise InvalidSnapshotError("invalid trip item")
    normalized_trips = [
        normalized
        for trip in trips
        if (normalized := _normalize_trip(trip)) is not None
    ]
    if trips and not normalized_trips:
        raise InvalidSnapshotError("snapshot has no valid trip items")
    if require_trips and not any(
        trip.get("id") is not None for trip in normalized_trips
    ):
        raise InvalidSnapshotError("snapshot has no usable trips")

    return vin, normalized_trips
