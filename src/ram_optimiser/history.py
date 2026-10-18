"""Bounded, local SQLite history. No network or telemetry is used."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock

from .core import utc_timestamp
from .settings import data_directory

MAX_SAMPLES = 250_000
MAX_EVENTS = 20_000
SAMPLE_INTERVAL_SECONDS = 10


class HistoryStore:
    def __init__(self, path: Path | None = None, retention_days: int = 30):
        self.path = path or (data_directory() / "history.sqlite3")
        self.retention_days = max(1, int(retention_days))
        self._lock = RLock()
        self._ready = False

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path), timeout=5)
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()

    def _initialize(self):
        if self._ready:
            return
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS samples (id INTEGER PRIMARY KEY, at TEXT NOT NULL, ram REAL, cpu REAL, gpu REAL)")
            db.execute("CREATE TABLE IF NOT EXISTS boosts (id INTEGER PRIMARY KEY, at TEXT NOT NULL, mode TEXT, before_available INTEGER, after_available INTEGER, attempted INTEGER, succeeded INTEGER, failed INTEGER, duration REAL, details TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY, started TEXT NOT NULL, ended TEXT, game TEXT, seconds INTEGER)")
        self._ready = True

    def record_sample(self, ram: float | None, cpu: float | None, gpu: float | None):
        with self._lock:
            self._initialize()
            with self._connect() as db:
                now = datetime.now(timezone.utc)
                previous = db.execute("SELECT at FROM samples ORDER BY id DESC LIMIT 1").fetchone()
                if previous:
                    try:
                        if (now - datetime.fromisoformat(previous[0])).total_seconds() < SAMPLE_INTERVAL_SECONDS:
                            return False
                    except (TypeError, ValueError):
                        pass
                db.execute("INSERT INTO samples(at,ram,cpu,gpu) VALUES(?,?,?,?)", (now.isoformat(timespec="seconds"), ram, cpu, gpu))
                db.execute("DELETE FROM samples WHERE julianday(at) < julianday('now', ?)", (f"-{self.retention_days} days",))
                db.execute("DELETE FROM samples WHERE id NOT IN (SELECT id FROM samples ORDER BY id DESC LIMIT ?)", (MAX_SAMPLES,))
                db.execute("DELETE FROM boosts WHERE julianday(at) < julianday('now', ?)", (f"-{self.retention_days} days",))
                db.execute("DELETE FROM boosts WHERE id NOT IN (SELECT id FROM boosts ORDER BY id DESC LIMIT ?)", (MAX_EVENTS,))
                db.execute("DELETE FROM sessions WHERE ended IS NOT NULL AND julianday(started) < julianday('now', ?)", (f"-{self.retention_days} days",))
                db.execute("DELETE FROM sessions WHERE id NOT IN (SELECT id FROM sessions ORDER BY id DESC LIMIT ?)", (MAX_EVENTS,))
                return True

    def record_boost(self, mode: str, before: int | None, after: int | None,
                     attempted: int, succeeded: int, failed: int, duration: float, details=None):
        with self._lock:
            self._initialize()
            with self._connect() as db:
                db.execute("INSERT INTO boosts(at,mode,before_available,after_available,attempted,succeeded,failed,duration,details) VALUES(?,?,?,?,?,?,?,?,?)",
                           (utc_timestamp(), mode, before, after, attempted, succeeded, failed,
                            round(duration, 2), json.dumps(details or [], ensure_ascii=False)))
                db.execute("DELETE FROM boosts WHERE julianday(at) < julianday('now', ?)", (f"-{self.retention_days} days",))
                db.execute("DELETE FROM boosts WHERE id NOT IN (SELECT id FROM boosts ORDER BY id DESC LIMIT ?)", (MAX_EVENTS,))

    def start_session(self, game: str) -> int:
        with self._lock:
            self._initialize()
            with self._connect() as db:
                db.execute("DELETE FROM sessions WHERE ended IS NOT NULL AND julianday(started) < julianday('now', ?)", (f"-{self.retention_days} days",))
                db.execute("DELETE FROM sessions WHERE id NOT IN (SELECT id FROM sessions ORDER BY id DESC LIMIT ?)", (MAX_EVENTS,))
                cursor = db.execute("INSERT INTO sessions(started,game) VALUES(?,?)", (utc_timestamp(), game))
                return int(cursor.lastrowid)

    def end_session(self, session_id: int, seconds: int):
        with self._lock:
            self._initialize()
            with self._connect() as db:
                db.execute("UPDATE sessions SET ended=?,seconds=? WHERE id=?", (utc_timestamp(), max(0, int(seconds)), session_id))

    def recent_samples(self, limit: int = 120):
        with self._lock:
            self._initialize()
            with self._connect() as db:
                return list(reversed(db.execute("SELECT at,ram,cpu,gpu FROM samples ORDER BY id DESC LIMIT ?", (max(1, min(limit, MAX_SAMPLES)),)).fetchall()))

    def recent_boosts(self, limit: int = 30):
        with self._lock:
            self._initialize()
            with self._connect() as db:
                return db.execute("SELECT at,mode,before_available,after_available,attempted,succeeded,failed,duration FROM boosts ORDER BY id DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()

    def recent_sessions(self, limit: int = 30):
        with self._lock:
            self._initialize()
            with self._connect() as db:
                return db.execute("SELECT started,ended,game,seconds FROM sessions ORDER BY id DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()

    def clear(self):
        with self._lock:
            self._initialize()
            with self._connect() as db:
                for table in ("samples", "boosts", "sessions"):
                    db.execute(f"DELETE FROM {table}")
