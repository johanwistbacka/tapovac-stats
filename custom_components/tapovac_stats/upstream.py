"""Read-only adapter for TapoVac-ADV's internal coordinator data."""
from __future__ import annotations

from dataclasses import dataclass
import math
from collections.abc import Mapping


class UpstreamUnavailable(ValueError):
    """The source is unavailable, not loaded, or incompatible."""


@dataclass(frozen=True)
class RoomSnapshot:
    source_entry_id: str
    map_id: int
    room_id: int
    name: str
    last_cleaned: int | None
    coverage: float | None
    clean_times: tuple[int, ...] | None


def _timestamp(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UpstreamUnavailable("Invalid clean timestamp")
    if not math.isfinite(value) or value <= 0 or int(value) != value:
        raise UpstreamUnavailable("Invalid clean timestamp")
    return int(value)


def read_rooms(source: object, source_entry_id: str) -> tuple[RoomSnapshot, ...]:
    """Copy active-map rooms; never mutate or query the robot.

    An absent room key in an available log means no registered runs. A missing
    log means unknown counts, preserving last-clean information if available.
    """
    if not getattr(source, "last_update_success", False):
        raise UpstreamUnavailable("TapoVac-ADV is unavailable")
    if not getattr(source, "_freshness_loaded", False):
        raise UpstreamUnavailable("Room history has not loaded")
    map_id = getattr(source, "map_id", None)
    if isinstance(map_id, bool) or not isinstance(map_id, int):
        raise UpstreamUnavailable("Active map is unavailable")
    freshness = getattr(source, "rooms_last_cleaned", None)
    log = getattr(source, "rooms_clean_log", None)
    if not isinstance(freshness, Mapping):
        raise UpstreamUnavailable("Unsupported room freshness structure")
    if log is not None and not isinstance(log, Mapping):
        raise UpstreamUnavailable("Unsupported clean log structure")
    try:
        rooms = source.rooms_named()
    except (AttributeError, TypeError) as exc:
        raise UpstreamUnavailable("Unsupported room source") from exc
    if not isinstance(rooms, list):
        raise UpstreamUnavailable("Unsupported room list")
    result = []
    seen = set()
    for room in rooms:
        if not isinstance(room, Mapping):
            raise UpstreamUnavailable("Invalid room")
        rid = room.get("id")
        if isinstance(rid, bool) or not isinstance(rid, int) or rid in seen:
            raise UpstreamUnavailable("Invalid or duplicate room ID")
        seen.add(rid)
        key = f"{map_id}:{rid}"
        latest = freshness.get(key, {})
        if not isinstance(latest, Mapping):
            raise UpstreamUnavailable("Invalid room freshness")
        times = None
        if log is not None:
            raw_times = log.get(key, [])
            if not isinstance(raw_times, (list, tuple)):
                raise UpstreamUnavailable("Invalid room clean log")
            times = tuple(sorted({_timestamp(t) for t in raw_times}))
        last = latest.get("last_cleaned")
        last = None if last is None or last == 0 else _timestamp(last)
        if times:
            last = max(last or 0, times[-1])
        coverage = latest.get("coverage")
        if coverage is not None and (
            isinstance(coverage, bool) or not isinstance(coverage, (int, float))
            or not math.isfinite(coverage) or not 0 <= coverage <= 100
        ):
            raise UpstreamUnavailable("Invalid room coverage")
        name = room.get("name_text")
        result.append(RoomSnapshot(source_entry_id, map_id, rid,
                                   name.strip() if isinstance(name, str) and name.strip() else f"Room {rid}",
                                   last, coverage, times))
    return tuple(result)
