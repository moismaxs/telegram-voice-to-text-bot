"""Минимальная аналитика: кто пользуется ботом и сколько расшифровок.

SQLite через stdlib, без новых зависимостей. Файл лежит в персистентном
/data (Amvera) и переживает пересборки. Храним только user_id, имя и
счётчики — ни войсы, ни тексты не сохраняются.
"""
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

log = logging.getLogger(__name__)

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def db_path() -> Path:
    if settings.DB_PATH:
        return Path(settings.DB_PATH)
    if Path("/data").is_dir():
        return Path("/data/voices.db")
    return Path("voices.db")


def init_db() -> Path:
    global _conn
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(path), check_same_thread=False)
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id    INTEGER PRIMARY KEY,
            username   TEXT,
            full_name  TEXT,
            first_seen TEXT NOT NULL,
            last_seen  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ts           TEXT NOT NULL,
            user_id      INTEGER NOT NULL,
            chat_id      INTEGER NOT NULL,
            chat_type    TEXT NOT NULL,
            kind         TEXT NOT NULL,
            duration_sec INTEGER,
            ok           INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
        """
    )
    _conn.commit()
    return path


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def track_user(user_id: int, username: str | None, full_name: str) -> None:
    if _conn is None:
        return
    now = _now()
    with _lock:
        _conn.execute(
            """
            INSERT INTO users (user_id, username, full_name, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                full_name=excluded.full_name,
                last_seen=excluded.last_seen
            """,
            (user_id, username, full_name, now, now),
        )
        _conn.commit()


def track_event(
    user_id: int, chat_id: int, chat_type: str,
    kind: str, duration: int | None, ok: bool,
) -> None:
    if _conn is None:
        return
    with _lock:
        _conn.execute(
            "INSERT INTO events (ts, user_id, chat_id, chat_type, kind, duration_sec, ok)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), user_id, chat_id, chat_type, kind, duration, int(ok)),
        )
        _conn.commit()


def get_stats() -> dict:
    """Сводка для /stats. Всё в UTC."""
    if _conn is None:
        return {}
    with _lock:
        q = _conn.execute
        users_total = q("SELECT COUNT(*) FROM users").fetchone()[0]
        users_today = q(
            "SELECT COUNT(*) FROM users WHERE date(first_seen) = date('now')"
        ).fetchone()[0]
        tr_total = q("SELECT COUNT(*) FROM events WHERE ok = 1").fetchone()[0]
        tr_today = q(
            "SELECT COUNT(*) FROM events WHERE ok = 1 AND date(ts) = date('now')"
        ).fetchone()[0]
        tr_week = q(
            "SELECT COUNT(*) FROM events WHERE ok = 1 AND date(ts) >= date('now', '-6 days')"
        ).fetchone()[0]
        errors = q("SELECT COUNT(*) FROM events WHERE ok = 0").fetchone()[0]
        avg_dur = q(
            "SELECT COALESCE(AVG(duration_sec), 0) FROM events WHERE ok = 1"
        ).fetchone()[0]
    return {
        "users_total": users_total,
        "users_today": users_today,
        "tr_total": tr_total,
        "tr_today": tr_today,
        "tr_week": tr_week,
        "errors": errors,
        "avg_dur": round(avg_dur or 0),
    }
