"""SQLite storage (Stages 1 and 6). Embeddings are stored encrypted."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime
import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases(
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_code TEXT UNIQUE, name TEXT NOT NULL,
  age INTEGER, gender TEXT, last_seen_place TEXT, last_seen_date TEXT, description TEXT,
  contact_name TEXT, contact_email TEXT, contact_phone TEXT,
  status TEXT DEFAULT 'active', created_at TEXT);
CREATE TABLE IF NOT EXISTS embeddings(
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_id INTEGER NOT NULL, photo_path TEXT,
  embedding BLOB NOT NULL, quality REAL, created_at TEXT,
  FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS sightings(
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_id INTEGER NOT NULL, score REAL NOT NULL,
  source_type TEXT, source_name TEXT, camera_name TEXT, lat REAL, lng REAL,
  frame_index INTEGER, seen_at TEXT, snapshot_path TEXT, status TEXT DEFAULT 'pending',
  reviewed_at TEXT, n_frames INTEGER DEFAULT 1,
  FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS alerts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, sighting_id INTEGER, to_email TEXT, subject TEXT,
  mode TEXT, status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, detail TEXT, created_at TEXT);
"""


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def conn():
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)


def q(sql, args=(), one=False):
    with conn() as c:
        rows = c.execute(sql, args).fetchall()
    return (rows[0] if rows else None) if one else rows


def x(sql, args=()):
    with conn() as c:
        cur = c.execute(sql, args)
        return cur.lastrowid


def audit(action, detail=""):
    x("INSERT INTO audit(action,detail,created_at) VALUES(?,?,?)", (action, detail, now()))


def get_setting(key, default=None):
    r = q("SELECT value FROM settings WHERE key=?", (key,), one=True)
    return r["value"] if r else default


def set_setting(key, value):
    x("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
      (key, str(value)))
