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
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS allowed_chats (chat_id INTEGER PRIMARY KEY)"
    )
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS settings ("
        "chat_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT, "
        "PRIMARY KEY (chat_id, key))"
    )
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS style ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, "
        "added TEXT DEFAULT CURRENT_TIMESTAMP)"
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


# --- Разрешённые группы ---

def add_chat(chat_id: int) -> None:
    _conn.execute(
        "INSERT OR IGNORE INTO allowed_chats (chat_id) VALUES (?)", (chat_id,)
    )
    _conn.commit()


def remove_chat(chat_id: int) -> None:
    _conn.execute("DELETE FROM allowed_chats WHERE chat_id = ?", (chat_id,))
    _conn.commit()


def is_chat_allowed(chat_id: int) -> bool:
    row = _conn.execute(
        "SELECT 1 FROM allowed_chats WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    return row is not None


def all_chats() -> list[int]:
    return [r[0] for r in _conn.execute("SELECT chat_id FROM allowed_chats")]


# --- Настройки чата (модель ИИ, интернет и т.п.) ---

def get_setting(chat_id: int, key: str, default: str = "") -> str:
    row = _conn.execute(
        "SELECT value FROM settings WHERE chat_id = ? AND key = ?", (chat_id, key)
    ).fetchone()
    return row[0] if row else default


def set_setting(chat_id: int, key: str, value: str) -> None:
    _conn.execute(
        "INSERT OR REPLACE INTO settings (chat_id, key, value) VALUES (?, ?, ?)",
        (chat_id, key, value),
    )
    _conn.commit()


# --- Стиль Далера (примеры текстов для ИИ) ---

def add_style(text: str) -> int:
    _conn.execute("INSERT INTO style (text) VALUES (?)", (text,))
    _conn.commit()
    return style_count()


def get_style(max_chars: int = 8000) -> str:
    rows = [r[0] for r in _conn.execute("SELECT text FROM style ORDER BY id DESC")]
    out: list[str] = []
    total = 0
    for t in rows:  # новые важнее; набираем, пока влезает
        if total + len(t) > max_chars:
            break
        out.append(t)
        total += len(t)
    return "\n\n---\n\n".join(reversed(out))


def style_count() -> int:
    return _conn.execute("SELECT COUNT(*) FROM style").fetchone()[0]


def clear_style() -> None:
    _conn.execute("DELETE FROM style")
    _conn.commit()
