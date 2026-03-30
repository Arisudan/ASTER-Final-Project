import os
import pickle
import sqlite3
import subprocess
import threading
import time
from pathlib import Path

import eel
import pyttsx3
import speech_recognition as sr
from playsound import playsound

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "jarvis.db"
DEFAULT_SOUND_PATHS = [
    BASE_DIR / "www" / "assets" / "jarvis_start.mp3",
    BASE_DIR / "www" / "assets" / "Audio" / "start_sound.mp3",
    BASE_DIR / "www" / "assets" / "Audio" / "jarvis_start.mp3",
]


def db_init():
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_input TEXT,
                jarvis_response TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS face_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                encoding BLOB,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()


def log_conversation(user_input, jarvis_response):
    db_init()
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO conversations (user_input, jarvis_response) VALUES (?, ?)",
            (user_input, jarvis_response),
        )
        connection.commit()


def save_setting(key, value):
    db_init()
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        connection.commit()


def get_setting(key, default=None):
    db_init()
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default


def speak(text):
    if text is None:
        return

    message = str(text).strip()
    if not message:
        return

    try:
        engine = pyttsx3.init()
        voices = engine.getProperty("voices")
        if voices:
            engine.setProperty("voice", voices[0].id)
        engine.setProperty("rate", 180)
        engine.say(message)
        engine.runAndWait()
    except Exception:
        pass


@eel.expose
def takecommand():
    recognizer = sr.Recognizer()

    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=7)
        query = recognizer.recognize_google(audio)
        return query.lower().strip()
    except sr.WaitTimeoutError:
        return "none"
    except sr.UnknownValueError:
        return "none"
    except sr.RequestError:
        return "none"
    except Exception:
        return "none"


def playAssistantSound():
    def _play():
        for sound_path in DEFAULT_SOUND_PATHS:
            if sound_path.exists():
                try:
                    playsound(str(sound_path))
                except Exception:
                    pass
                break
        else:
            try:
                import winsound

                winsound.MessageBeep()
            except Exception:
                pass

    threading.Thread(target=_play, daemon=True).start()


def hotword():
    recognizer = sr.Recognizer()

    while True:
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.2)
                audio = recognizer.listen(source, timeout=1, phrase_time_limit=3)
            phrase = recognizer.recognize_google(audio).lower().strip()
            if "jarvis" in phrase:
                print("Hotword detected.")
        except sr.WaitTimeoutError:
            continue
        except sr.UnknownValueError:
            continue
        except sr.RequestError:
            time.sleep(2)
        except Exception:
            time.sleep(1)


def openai_query(prompt):
    prompt = str(prompt or "").strip()
    if not prompt:
        return ""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "OpenAI is not configured."

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.responses.create(model=model, input=prompt)
        text = getattr(response, "output_text", "")
        if text:
            return text.strip()
    except Exception:
        pass

    try:
        import openai

        openai.api_key = api_key
        completion = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are Jarvis, a concise car infotainment voice assistant."},
                {"role": "user", "content": prompt},
            ],
        )
        return completion["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return f"I could not generate a response. {exc}"


try:
    db_init()
except Exception:
    pass
