"""Хранилище «уже виденных» элементов (SQLite) — чтобы не слать повторные уведомления."""
import sqlite3

import config

_conn: sqlite3.Connection | None = None


def init() -> None:
    global _conn
    _conn = sqlite3.connect(config.DB_PATH)
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS seen ("
        "source TEXT NOT NULL, item_id TEXT NOT NULL, "
        "PRIMARY KEY (source, item_id))"
    )
    _conn.commit()


def is_seen(source: str, item_id: str) -> bool:
    row = _conn.execute(
        "SELECT 1 FROM seen WHERE source = ? AND item_id = ?", (source, item_id)
    ).fetchone()
    return row is not None


def mark_seen(source: str, item_id: str) -> None:
    _conn.execute(
        "INSERT OR IGNORE INTO seen (source, item_id) VALUES (?, ?)", (source, item_id)
    )
    _conn.commit()


def has_any(source: str) -> bool:
    """Был ли уже первый прогон по этому источнику (есть ли хоть одна запись)."""
    row = _conn.execute(
        "SELECT 1 FROM seen WHERE source = ? LIMIT 1", (source,)
    ).fetchone()
    return row is not None
