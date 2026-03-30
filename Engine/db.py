from __future__ import annotations

import queue
import sqlite3
import threading
from pathlib import Path
from typing import Iterable, Optional

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "jarvis.db"

_log_queue: "queue.Queue[tuple[str, str, str, Optional[str]]]" = queue.Queue()
_started = False
_lock = threading.Lock()


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_db() -> None:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_input TEXT NOT NULL,
                jarvis_response TEXT NOT NULL,
                source TEXT DEFAULT 'voice',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS face_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                encoding BLOB NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                source TEXT DEFAULT 'system',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conversation_columns = _table_columns(connection, "conversations")
        if "source" not in conversation_columns:
            try:
                cursor.execute("ALTER TABLE conversations ADD COLUMN source TEXT DEFAULT 'voice'")
            except sqlite3.OperationalError:
                pass

        log_columns = _table_columns(connection, "logs")
        if "source" not in log_columns:
            try:
                cursor.execute("ALTER TABLE logs ADD COLUMN source TEXT DEFAULT 'system'")
            except sqlite3.OperationalError:
                pass

        conversation_columns = _table_columns(connection, "conversations")
        log_columns = _table_columns(connection, "logs")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_timestamp ON conversations(timestamp)")
        if "source" in conversation_columns:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_source ON conversations(source)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_face_profiles_name ON face_profiles(name)")
        connection.commit()


def _log_worker() -> None:
    while True:
        item = _log_queue.get()
        if item is None:
            break

        kind, first, second, source = item
        try:
            with get_connection() as connection:
                cursor = connection.cursor()
                if kind == "conversation":
                    columns = _table_columns(connection, "conversations")
                    if "source" in columns:
                        cursor.execute(
                            "INSERT INTO conversations (user_input, jarvis_response, source) VALUES (?, ?, ?)",
                            (first, second, source or "voice"),
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO conversations (user_input, jarvis_response) VALUES (?, ?)",
                            (first, second),
                        )
                elif kind == "event":
                    columns = _table_columns(connection, "logs")
                    if "source" in columns:
                        cursor.execute(
                            "INSERT INTO logs (level, message, source) VALUES (?, ?, ?)",
                            (first, second, source or "system"),
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO logs (level, message) VALUES (?, ?)",
                            (first, second),
                        )
                connection.commit()
        except Exception:
            continue


def start_background_workers() -> None:
    global _started
    with _lock:
        if _started:
            return
        init_db()
        threading.Thread(target=_log_worker, daemon=True).start()
        _started = True


def stop_background_workers() -> None:
    if _started:
        _log_queue.put(None)


def log_event(level: str, message: str, source: str = "system") -> None:
    start_background_workers()
    _log_queue.put(("event", level.upper(), message, source))


def log_conversation(user_input: str, jarvis_response: str, source: str = "voice") -> None:
    start_background_workers()
    _log_queue.put(("conversation", user_input, jarvis_response, source))


def save_setting(key: str, value: str) -> None:
    init_db()
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        connection.commit()


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    init_db()
    with get_connection() as connection:
        row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default


def save_face_profile(name: str, encoding_blob: bytes) -> None:
    init_db()
    with get_connection() as connection:
        connection.execute("INSERT INTO face_profiles (name, encoding) VALUES (?, ?)", (name, encoding_blob))
        connection.commit()


def fetch_face_profiles() -> list[tuple[str, bytes]]:
    init_db()
    with get_connection() as connection:
        rows = connection.execute("SELECT name, encoding FROM face_profiles ORDER BY id ASC").fetchall()
        return [(row[0], row[1]) for row in rows]


def fetch_recent_conversations(limit: int = 20) -> list[tuple[str, str, str]]:
    init_db()
    with get_connection() as connection:
        columns = _table_columns(connection, "conversations")
        if "source" in columns:
            rows = connection.execute(
                "SELECT user_input, jarvis_response, source FROM conversations ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [(row[0], row[1], row[2]) for row in reversed(rows)]

        rows = connection.execute(
            "SELECT user_input, jarvis_response FROM conversations ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [(row[0], row[1], "voice") for row in reversed(rows)]


def fetch_recent_logs(limit: int = 25) -> list[tuple[str, str, str]]:
    init_db()
    with get_connection() as connection:
        columns = _table_columns(connection, "logs")
        if "source" in columns:
            rows = connection.execute(
                "SELECT level, message, source FROM logs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [(row[0], row[1], row[2]) for row in rows]

        rows = connection.execute(
            "SELECT level, message FROM logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [(row[0], row[1], "system") for row in rows]
