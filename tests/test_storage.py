"""Tests for the SQLite storage. Run with:  python -m unittest"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import settings
import storage

SHIP = {"mmsi": 1, "name": "TEST", "category": "Lasteskip", "lat": 60.4, "lon": 5.3,
        "speed": 10.0, "co2_kg_h": 600.0}
OTHER = {**SHIP, "mmsi": 2, "category": "Tankskip", "lat": 60.5}


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.dict(os.environ, {"DB_PATH": os.path.join(self.tmp.name, "test.db")})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("TURSO_DATABASE_URL", None)  # always test against a local file
        self.conn = storage.connect()
        self.now = datetime.now(timezone.utc)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def count(self, table):
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def test_first_snapshot_counts_collect_interval(self):
        hours = storage.save_snapshot(self.conn, self.now, [SHIP])
        self.assertAlmostEqual(hours, settings.COLLECT_MINUTES / 60)

    def test_snapshot_counts_time_since_previous(self):
        storage.save_snapshot(self.conn, self.now - timedelta(minutes=7), [SHIP])
        hours = storage.save_snapshot(self.conn, self.now, [SHIP])
        self.assertAlmostEqual(hours, 7 / 60)

    def test_long_gap_is_not_counted(self):
        storage.save_snapshot(self.conn, self.now - timedelta(hours=3), [SHIP])
        hours = storage.save_snapshot(self.conn, self.now, [SHIP])
        self.assertAlmostEqual(hours, settings.COLLECT_MINUTES / 60)

    def test_hourly_totals_add_up_snapshots(self):
        first = self.now - timedelta(minutes=6)
        storage.save_snapshot(self.conn, first, [SHIP, OTHER])
        storage.save_snapshot(self.conn, self.now, [SHIP])
        first_kg = 600 * settings.COLLECT_MINUTES / 60  # per ship
        second_kg = 600 * 6 / 60
        rows = storage.hourly(self.conn, days=1)
        by_category = {}
        for _, category, kg in rows:
            by_category[category] = by_category.get(category, 0) + kg
        self.assertAlmostEqual(by_category["Lasteskip"], first_kg + second_kg)
        self.assertAlmostEqual(by_category["Tankskip"], first_kg)
        # The summaries match the raw positions
        raw = self.conn.execute("SELECT SUM(co2_kg) FROM positions").fetchone()[0]
        self.assertAlmostEqual(sum(by_category.values()), raw)

    def test_heat_points_sum_per_cell_and_filter_by_category(self):
        storage.save_snapshot(self.conn, self.now - timedelta(minutes=10), [SHIP])
        storage.save_snapshot(self.conn, self.now, [SHIP])
        points = storage.heat_points(self.conn, 1, ["Lasteskip"])
        self.assertEqual(len(points), 1)  # same cell both times
        lat, lon, kg = points[0]
        self.assertAlmostEqual(lat, 60.4, places=2)
        self.assertAlmostEqual(lon, 5.3, places=2)
        self.assertEqual(storage.heat_points(self.conn, 1, ["Tankskip"]), [])
        self.assertEqual(storage.heat_points(self.conn, 1, []), [])

    def test_snapshot_without_ships(self):
        storage.save_snapshot(self.conn, self.now, [])
        self.assertEqual(self.count("snapshots"), 1)
        self.assertEqual(self.count("hourly_totals"), 0)

    def test_old_data_is_deleted_everywhere(self):
        storage.save_snapshot(self.conn, self.now - timedelta(days=40), [SHIP])
        storage.save_snapshot(self.conn, self.now, [SHIP])
        storage.delete_older_than(self.conn, 30)
        for table in ("snapshots", "positions", "hourly_totals", "heat_cells"):
            self.assertEqual(self.count(table), 1, table)

    def test_coverage(self):
        storage.save_snapshot(self.conn, self.now - timedelta(minutes=10), [SHIP])
        storage.save_snapshot(self.conn, self.now, [SHIP])
        n, first, last, hours = storage.coverage(self.conn, 1)
        self.assertEqual(n, 2)
        self.assertAlmostEqual(hours, (settings.COLLECT_MINUTES + 10) / 60)


if __name__ == "__main__":
    unittest.main()
