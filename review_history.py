"""Persistent review-count snapshots and conservative monthly growth estimates.

Only verified numeric review counts are recorded. Unknown remains unknown.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

def save_snapshot(db_path, product_id, review_count, observed_at=None):
    if not str(product_id).isdigit() or review_count is None:
        raise ValueError("Valid product ID and observed review count required")
    count = int(review_count)
    if count < 0 or float(review_count) != count:
        raise ValueError("Review count must be a nonnegative integer")
    observed_at = observed_at or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        raise ValueError("Timestamp must be timezone-aware")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS review_snapshots (
            product_id TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            review_count INTEGER NOT NULL,
            PRIMARY KEY(product_id, observed_at)
        )""")
        conn.execute(
            "INSERT OR REPLACE INTO review_snapshots VALUES (?, ?, ?)",
            (str(product_id), observed_at.astimezone(timezone.utc).isoformat(), count)
        )

def estimate_from_snapshots(db_path, product_id, multiplier=10, as_of=None):
    if not 1 <= multiplier <= 100:
        raise ValueError("Invalid multiplier")
    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        raise ValueError("Timestamp must be timezone-aware")
    if not Path(db_path).exists():
        return None
    with sqlite3.connect(db_path) as conn:
        try:
            rows = conn.execute(
                "SELECT observed_at, review_count FROM review_snapshots WHERE product_id=? AND observed_at<=? ORDER BY observed_at",
                (str(product_id), as_of.astimezone(timezone.utc).isoformat())
            ).fetchall()
        except sqlite3.OperationalError:
            return None
    if len(rows) < 2:
        return None
    # A genuine 30-day estimate requires an observed baseline at least 30 days old.
    cutoff = as_of - timedelta(days=30)
    baseline = [(datetime.fromisoformat(t), c) for t, c in rows if datetime.fromisoformat(t) <= cutoff]
    if not baseline:
        return None
    previous_time, previous = baseline[-1]
    last_time, latest = datetime.fromisoformat(rows[-1][0]), rows[-1][1]
    if last_time <= previous_time:
        return None
    # If baseline is older than 30 days, interpolate average daily growth; label estimate.
    days = (last_time - previous_time).total_seconds() / 86400
    growth = max(0, latest - previous)
    monthly_reviews = growth * 30 / days
    return {
        "reviews_start": previous,
        "reviews_latest": latest,
        "observed_days": round(days, 1),
        "estimated_new_reviews_30d": round(monthly_reviews, 1),
        "estimated_sales_30d": round(monthly_reviews * multiplier),
        "multiplier": multiplier,
        "is_estimate": True,
    }
