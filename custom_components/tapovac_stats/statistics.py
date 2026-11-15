"""Room statistics independent of Home Assistant."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .upstream import RoomSnapshot


@dataclass(frozen=True)
class RoomStatistics:
    room: RoomSnapshot
    last_cleaned: datetime | None
    today: int | None
    last_seven_days: int | None


def calculate(room: RoomSnapshot, now: datetime, local_zone: ZoneInfo) -> RoomStatistics:
    """Count registered runs, including lower boundaries and excluding future runs.

    Today uses local midnight. Seven days means 168 elapsed hours, including
    across daylight saving transitions. Missing history produces unknown counts.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    utc_now = now.astimezone(timezone.utc)
    midnight = utc_now.astimezone(local_zone).replace(hour=0, minute=0, second=0, microsecond=0)
    today_start = midnight.timestamp()
    week_start = (utc_now - timedelta(hours=168)).timestamp()
    end = utc_now.timestamp()
    times = room.clean_times
    last = room.last_cleaned
    last_dt = datetime.fromtimestamp(last, timezone.utc) if last is not None and last <= end else None
    return RoomStatistics(
        room, last_dt,
        None if times is None else sum(today_start <= t <= end for t in set(times)),
        None if times is None else sum(week_start <= t <= end for t in set(times)),
    )


def newest_first(rows: list[RoomStatistics]) -> list[RoomStatistics]:
    """Sort known timestamps first; names break ties without implying run order."""
    return sorted(rows, key=lambda row: (
        -(row.last_cleaned.timestamp() if row.last_cleaned else float("-inf")),
        row.room.name.casefold(), row.room.map_id, row.room.room_id,
    ))
