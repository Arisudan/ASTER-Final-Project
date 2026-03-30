from __future__ import annotations

import os
import queue
import subprocess
import threading
from pathlib import Path

import eel

from Engine import db
from Engine.Features import playAssistantSound, speak, start_audio_system, takecommand
from Engine.auth import recoganize
from Engine.command import allCommands
from Vision.driver_monitor import start_driver_monitor

BASE_DIR = Path(__file__).resolve().parent
_wake_queue = None
_voice_queue: "queue.Queue[dict]" = queue.Queue()
_authenticated = threading.Event()


def _call_js(function_name: str, *args):
    try:
        return getattr(eel, function_name)(*args)
    except Exception:
        return None


def _voice_worker() -> None:
    while True:
        job = _voice_queue.get()
        if job is None:
            break

        source = job.get("source", "voice")
        _call_js("showAlert", "Listening for a command")
        query = takecommand()
        if not query or query == "none":
            _call_js("updateCommand", "No command detected.", "Try again.")
            continue

        _call_js("updateCommand", query, "Processing...")
        response = allCommands(query, source=source)
        _call_js("updateCommand", query, response)


def _wake_monitor() -> None:
    while True:
        if _wake_queue is None:
            break

        event = _wake_queue.get()
        if event is None:
            break

        if isinstance(event, dict) and event.get("type") == "wake":
            _call_js("triggerWakeAnimation", event.get("source", "wake"))
            _call_js("showAlert", "Wake word detected")
            if _authenticated.is_set():
                _voice_queue.put({"source": "wake"})


def _start_background_threads() -> None:
    threading.Thread(target=_voice_worker, daemon=True).start()
    threading.Thread(target=_wake_monitor, daemon=True).start()


@eel.expose
def takeCommand():
    _voice_queue.put({"source": "ui"})
    return "listening"


@eel.expose
def init():
    try:
        subprocess.call([r"device.bat"], cwd=str(BASE_DIR))
    except Exception as exc:
        db.log_event("warning", f"ADB bootstrap failed: {exc}", source="bootstrap")

    _call_js("hideLoader")
    speak("Ready for Face Authentication")
    _call_js("showAlert", "Ready for Face Authentication")

    flag = recoganize.AuthenticateFace()
    if flag == 1:
        _authenticated.set()
        _call_js("hideFaceAuth")
        speak("Face Authentication Successful")
        _call_js("hideFaceAuthSuccess")
        speak("Hello, Welcome Sir, How can i help you?")
        _call_js("hideStart")
        playAssistantSound()

        threading.Thread(
            target=start_driver_monitor,
            args=(lambda message: _call_js("showAlert", message),),
            daemon=True,
        ).start()
    else:
        speak("Face Authentication Fail")
        _call_js("showAlert", "Face authentication failed")


def start(wake_queue=None):
    global _wake_queue
    _wake_queue = wake_queue

    db.init_db()
    db.start_background_workers()
    start_audio_system()

    eel.init("www")
    _start_background_threads()

    os.system('start msedge.exe --app="http://localhost:8000/index.html"')
    eel.start("index.html", mode=None, host="localhost", block=True)
