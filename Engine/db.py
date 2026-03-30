from __future__ import annotations

import queue
import sqlite3
import threading
import json
from pathlib import Path
from typing import Iterable, Optional

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "jarvis.db"
DEFAULT_SETTINGS = {
    "assistant_name": "ASTER",
    "wake_word_enabled": "true",
    "driver_monitor_enabled": "true",
    "driver_monitor_model": "yolov8n-pose.pt",
    "driver_monitor_confidence": "0.35",
    "driver_monitor_alert_seconds": "3.0",
    "driver_monitor_frame_stride": "3",
    "driver_monitor_camera_index": "0",
    "android_device_serial": "",
    "android_default_package": "",
    "speech_rate": "180",
}

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
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS settings_presets (
                user_name TEXT PRIMARY KEY,
                settings_json TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_settings_presets_updated_at ON settings_presets(updated_at)")
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


def get_all_settings() -> dict[str, str]:
    init_db()
    settings = dict(DEFAULT_SETTINGS)
    with get_connection() as connection:
        rows = connection.execute("SELECT key, value FROM settings").fetchall()
        for key, value in rows:
            settings[str(key)] = str(value)
    return settings


def save_settings(settings: dict[str, object]) -> None:
    init_db()
    with get_connection() as connection:
        for key, value in settings.items():
            connection.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(key), str(value)),
            )
        connection.commit()


def get_settings_for_user(user_name: str) -> dict[str, str]:
    init_db()
    resolved_name = str(user_name or "").strip()
    if not resolved_name:
        return get_all_settings()

    settings = dict(DEFAULT_SETTINGS)
    with get_connection() as connection:
        rows = connection.execute("SELECT key, value FROM settings").fetchall()
        for key, value in rows:
            settings[str(key)] = str(value)

        row = connection.execute(
            "SELECT settings_json FROM settings_presets WHERE user_name = ?",
            (resolved_name,),
        ).fetchone()
        if row and row[0]:
            try:
                preset_settings = json.loads(row[0])
                if isinstance(preset_settings, dict):
                    for key, value in preset_settings.items():
                        settings[str(key)] = str(value)
            except Exception:
                pass

    return settings


def save_settings_for_user(user_name: str, settings: dict[str, object]) -> None:
    init_db()
    resolved_name = str(user_name or "").strip()
    if not resolved_name:
        return

    with get_connection() as connection:
        payload = json.dumps({str(key): str(value) for key, value in settings.items()})
        connection.execute(
            """
            INSERT INTO settings_presets (user_name, settings_json, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(user_name) DO UPDATE SET
                settings_json = excluded.settings_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (resolved_name, payload),
        )
        connection.commit()


def list_settings_presets() -> list[dict[str, object]]:
    init_db()
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT user_name, created_at, updated_at FROM settings_presets ORDER BY updated_at DESC, user_name ASC"
        ).fetchall()
        return [
            {"user_name": row[0], "created_at": row[1], "updated_at": row[2]}
            for row in rows
        ]


def delete_settings_preset(user_name: str) -> None:
    init_db()
    resolved_name = str(user_name or "").strip()
    if not resolved_name:
        return

    with get_connection() as connection:
        connection.execute("DELETE FROM settings_presets WHERE user_name = ?", (resolved_name,))
        connection.commit()


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


def fetch_face_profile_summaries() -> list[dict[str, object]]:
    init_db()
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, name, created_at FROM face_profiles ORDER BY id ASC"
        ).fetchall()
        return [
            {"id": row[0], "name": row[1], "created_at": row[2]}
            for row in rows
        ]


def delete_face_profile(profile_id: int) -> None:
    init_db()
    with get_connection() as connection:
        connection.execute("DELETE FROM face_profiles WHERE id = ?", (int(profile_id),))
        connection.commit()


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
