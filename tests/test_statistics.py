"""Synthetic fixtures only; run with python -m unittest discover -s tests."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import TestCase
from zoneinfo import ZoneInfo

from custom_components.tapovac_stats.statistics import calculate, newest_first
from custom_components.tapovac_stats.upstream import RoomSnapshot, UpstreamUnavailable, read_rooms


class StatisticsTests(TestCase):
    zone = ZoneInfo("Europe/Stockholm")

    def room(self, times=None, last=None, name="Kök", rid=1):
        return RoomSnapshot("source", 1, rid, name, last, 80, times)

    def test_boundaries_deduplication_and_future(self):
        now = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
        week = int((now - timedelta(hours=168)).timestamp())
        midnight = int(datetime(2026, 11, 15, tzinfo=self.zone).timestamp())
        times = (week - 1, week, midnight - 1, midnight, midnight, int(now.timestamp()) + 1)
        result = calculate(self.room(times), now, self.zone)
        self.assertEqual((result.today, result.last_seven_days), (1, 3))

    def test_dst_local_day_and_elapsed_week(self):
        for month, day, day_hours in ((3, 29, 23), (10, 25, 25)):
            now = datetime(2026, month, day, 23, 59, tzinfo=self.zone)
            midnight = now.replace(hour=0, minute=0)
            next_midnight = (midnight + timedelta(days=1))
            self.assertEqual((next_midnight.timestamp() - midnight.timestamp()) / 3600, day_hours)
            boundary = int(now.timestamp() - 168 * 3600)
            result = calculate(self.room((boundary - 1, boundary, int(midnight.timestamp()))), now, self.zone)
            self.assertEqual((result.today, result.last_seven_days), (1, 2))

    def test_unknown_and_empty_are_different(self):
        now = datetime.now(timezone.utc)
        self.assertIsNone(calculate(self.room(), now, self.zone).today)
        self.assertEqual(calculate(self.room(()), now, self.zone).today, 0)

    def test_sort_unknown_last_and_tied_names(self):
        now = datetime.now(timezone.utc)
        rows = [calculate(self.room(last=t, name=n, rid=i), now, self.zone)
                for i, (t, n) in enumerate(((None, "A"), (100, "B"), (100, "A"), (200, "C")))]
        self.assertEqual([r.room.name for r in newest_first(rows)], ["C", "A", "B", "A"])

    def test_naive_now_rejected(self):
        with self.assertRaises(ValueError):
            calculate(self.room(), datetime(2026, 1, 1), self.zone)


class AdapterTests(TestCase):
    def source(self):
        return SimpleNamespace(last_update_success=True, _freshness_loaded=True, map_id=1,
                               rooms_named=lambda: [{"id": 1, "name_text": "Kök"}, {"id": 2, "name_text": "Kök"}],
                               rooms_last_cleaned={"1:1": {"last_cleaned": 100, "coverage": 80}},
                               rooms_clean_log={"1:1": [100, 100, 200], "2:1": [300]})

    def test_copies_log_and_preserves_room_identity(self):
        source = self.source()
        rooms = read_rooms(source, "source")
        self.assertEqual(rooms[0].clean_times, (100, 200))
        self.assertEqual(rooms[0].last_cleaned, 200)
        self.assertEqual(rooms[1].clean_times, ())
        source.rooms_clean_log["1:1"].append(400)
        self.assertEqual(rooms[0].clean_times, (100, 200))
        self.assertNotEqual(rooms[0].room_id, rooms[1].room_id)

    def test_missing_log_keeps_latest_but_unknown_counts(self):
        source = self.source()
        del source.rooms_clean_log
        room = read_rooms(source, "source")[0]
        self.assertIsNone(room.clean_times)
        self.assertEqual(room.last_cleaned, 100)

    def test_unavailable_unloaded_and_malformed(self):
        for field, value in (("last_update_success", False), ("_freshness_loaded", False),
                             ("map_id", None), ("rooms_clean_log", []),
                             ("rooms_clean_log", {"1:1": [True]})):
            with self.subTest(field=field, value=value):
                source = self.source()
                setattr(source, field, value)
                with self.assertRaises(UpstreamUnavailable):
                    read_rooms(source, "source")
