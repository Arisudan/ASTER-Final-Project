from __future__ import annotations

import os
import queue
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

import eel
import pyttsx3
import speech_recognition as sr

try:
    from playsound import playsound  # pyright: ignore[reportMissingImports]
except Exception:
    playsound = None

from Engine import db

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOUND_PATHS = [
    BASE_DIR / "www" / "assets" / "jarvis_start.wav",
    BASE_DIR / "www" / "assets" / "jarvis_start.mp3",
    BASE_DIR / "www" / "assets" / "Audio" / "start_sound.mp3",
    BASE_DIR / "www" / "assets" / "Audio" / "jarvis_start.mp3",
]

_tts_queue: "queue.Queue[str | None]" = queue.Queue()
_sound_queue: "queue.Queue[str | None]" = queue.Queue()
_audio_started = False
_audio_lock = threading.Lock()


def db_init():
    db.init_db()


def log_conversation(user_input, jarvis_response):
    db.log_conversation(str(user_input), str(jarvis_response))


def save_face_profile(name, encoding):
    db.save_face_profile(str(name), encoding)


def save_setting(key, value):
    db.save_setting(str(key), str(value))


def get_setting(key, default=None):
    return db.get_setting(str(key), default)


def _tts_worker() -> None:
    engine = pyttsx3.init()
    voices = engine.getProperty("voices") or []
    if voices:
        engine.setProperty("voice", voices[0].id)
    engine.setProperty("rate", 180)

    while True:
        text = _tts_queue.get()
        if text is None:
            break

        try:
            engine.say(text)
            engine.runAndWait()
        except Exception:
            continue


def _sound_worker() -> None:
    while True:
        sound_path = _sound_queue.get()
        if sound_path is None:
            break

        path = Path(sound_path)
        if not path.exists():
            continue

        try:
            if playsound is not None:
                playsound(str(path))
            else:
                import winsound

                winsound.PlaySound(str(path), winsound.SND_FILENAME)
        except Exception:
            try:
                import winsound

                winsound.MessageBeep()
            except Exception:
                pass


def start_audio_system() -> None:
    global _audio_started
    with _audio_lock:
        if _audio_started:
            return
        threading.Thread(target=_tts_worker, daemon=True).start()
        threading.Thread(target=_sound_worker, daemon=True).start()
        _audio_started = True


def stop_audio_system() -> None:
    if _audio_started:
        _tts_queue.put(None)
        _sound_queue.put(None)


def speak(text):
    if text is None:
        return

    message = str(text).strip()
    if not message:
        return

    start_audio_system()
    _tts_queue.put(message)


def play_sound(path: Path | str) -> None:
    start_audio_system()
    _sound_queue.put(str(path))


@eel.expose
def takecommand(timeout: int = 5, phrase_time_limit: int = 7, continuous: bool = False):
    recognizer = sr.Recognizer()

    def _listen_once():
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        query = recognizer.recognize_google(audio)
        return query.lower().strip()

    try:
        if continuous:
            while True:
                try:
                    return _listen_once()
                except sr.UnknownValueError:
                    continue
        return _listen_once()
    except sr.WaitTimeoutError:
        return "none"
    except sr.UnknownValueError:
        return "none"
    except sr.RequestError:
        return "none"
    except Exception:
        return "none"


def playAssistantSound():
    for sound_path in DEFAULT_SOUND_PATHS:
        if sound_path.exists():
            play_sound(sound_path)
            return
    try:
        import winsound

        winsound.MessageBeep()
    except Exception:
        pass


def hotword(wake_queue=None):
    from Engine.hotword import hotword as hotword_process

    hotword_process(wake_queue)


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
                {"role": "system", "content": "You are JARVIS, a concise car infotainment voice assistant."},
                {"role": "user", "content": prompt},
            ],
        )
        return completion["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return f"I could not generate a response. {exc}"


def open_android_app(package_name: str):
    package_name = str(package_name or "").strip()
    if not package_name:
        return "No Android package name was provided."

    commands = [
        ["adb", "shell", "monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1"],
        ["adb", "shell", "am", "start", "-n", package_name],
    ]
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return f"Opening Android app {package_name}."
        except Exception:
            continue
    return f"Unable to open Android app {package_name}."


def send_sms(number: str, message: str):
    number = str(number or "").strip()
    message = str(message or "").strip()
    if not number or not message:
        return "Please provide a number and a message."

    command = [
        "adb",
        "shell",
        "am",
        "start",
        "-a",
        "android.intent.action.SENDTO",
        "-d",
        f"sms:{number}",
        "--es",
        "sms_body",
        message,
        "--ez",
        "exit_on_sent",
        "true",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return f"SMS intent sent to {number}."
    except Exception:
        pass
    return "SMS sending is unavailable on this device."


def open_url(url: str):
    webbrowser.open(url)


def launch_camera_app():
    try:
        os.system('start microsoft.windows.camera:')
        return "Opening camera."
    except Exception:
        return "Camera launch failed."
