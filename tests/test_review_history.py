import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from review_history import save_snapshot, estimate_from_snapshots

class ReviewHistoryTests(unittest.TestCase):
    def test_requires_30_day_history(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "counts.sqlite"
            now = datetime(2026, 10, 22, tzinfo=timezone.utc)
            save_snapshot(db, "123", 50, now)
            self.assertIsNone(estimate_from_snapshots(db, "123", as_of=now))
            save_snapshot(db, "123", 20, now - timedelta(days=30))
            estimate = estimate_from_snapshots(db, "123", 10, now)
            self.assertEqual(estimate["estimated_new_reviews_30d"], 30)
            self.assertEqual(estimate["estimated_sales_30d"], 300)

    def test_does_not_extrapolate_lifetime_count(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "counts.sqlite"
            now = datetime(2026, 10, 22, tzinfo=timezone.utc)
            save_snapshot(db, "123", 9000, now - timedelta(days=3))
            save_snapshot(db, "123", 9010, now)
            self.assertIsNone(estimate_from_snapshots(db, "123", 10, now))

    def test_rejects_unknown_count(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                save_snapshot(Path(directory) / "counts.sqlite", "123", None)

if __name__ == "__main__":
    unittest.main()
