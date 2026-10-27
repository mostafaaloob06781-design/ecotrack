import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

DB_PATH = os.environ.get("DB_PATH", "ecotrack.db")
TZ = ZoneInfo(os.environ.get("APP_TZ", "Africa/Cairo"))

def now() -> datetime:
    """Current local time (naive) — all timestamps in the DB are local to APP_TZ."""
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  pw_hash BLOB NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('restaurant','beneficiary')),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS offers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  restaurant_id INTEGER NOT NULL REFERENCES users(id),
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  meal_type TEXT NOT NULL CHECK (meal_type IN ('lunch','dinner','snacks','desserts')),
  qty_total INTEGER NOT NULL CHECK (qty_total > 0),
  qty_left INTEGER NOT NULL CHECK (qty_left >= 0),
  original_price REAL NOT NULL CHECK (original_price >= 0),
  discount_pct INTEGER NOT NULL CHECK (discount_pct BETWEEN 0 AND 100),
  pickup_by TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  offer_id INTEGER NOT NULL REFERENCES offers(id),
  user_id INTEGER NOT NULL REFERENCES users(id),
  qty INTEGER NOT NULL CHECK (qty > 0),
  status TEXT NOT NULL DEFAULT 'reserved' CHECK (status IN ('reserved','collected','cancelled')),
  created_at TEXT NOT NULL
);
"""

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as db:
        db.executescript(SCHEMA)
