from __future__ import annotations

import random
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
from Engine.Features import list_android_devices
from Engine.spotify_backend import (
    connect_spotify,
    get_access_token as get_spotify_access_token,
    get_current_track as get_spotify_current_track,
    get_player_state as get_spotify_state,
    next_track as spotify_next_track,
    pause_music as spotify_pause_music,
    play_music as spotify_play_music,
    previous_track as spotify_previous_track,
    set_volume as spotify_set_volume,
    transfer_playback_to_device,
    toggle_repeat as spotify_toggle_repeat,
    toggle_shuffle as spotify_toggle_shuffle,
)
from Vision.driver_monitor import DriverMonitorConfig, start_driver_monitor

BASE_DIR = Path(__file__).resolve().parent
_wake_queue = None
_voice_queue: "queue.Queue[dict]" = queue.Queue()
_authenticated = threading.Event()
_current_user: str | None = None
_auth_started = threading.Event()
_vehicle_lock = threading.Lock()
_vehicle_state = {
    "mode": "ambient",
    "speed": 0,
    "battery": 91.0,
    "gear": "P",
    "lights_on": False,
    "climate_on": False,
    "autopilot": "Standby",
    "drive_mode": "Dark+",
}


def _parse_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _parse_int(value: object, default: int) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _call_js(function_name: str, *args):
    try:
        return getattr(eel, function_name)(*args)
    except Exception:
        return None


def _vehicle_snapshot() -> dict[str, object]:
    with _vehicle_lock:
        snapshot = dict(_vehicle_state)
        snapshot["battery"] = round(float(snapshot.get("battery", 0.0)), 1)
        snapshot["speed"] = int(snapshot.get("speed", 0))
        snapshot["lights_on"] = bool(snapshot.get("lights_on", False))
        snapshot["climate_on"] = bool(snapshot.get("climate_on", False))
        return snapshot


def _advance_vehicle_state(mode: str | None = None) -> dict[str, object]:
    with _vehicle_lock:
        active_mode = "driving" if mode == "driving" else "ambient"
        _vehicle_state["mode"] = active_mode
        if active_mode == "driving":
            _vehicle_state["speed"] = min(116, max(18, int(_vehicle_state["speed"]) + random.randint(-2, 8)))
            _vehicle_state["battery"] = max(30.0, float(_vehicle_state["battery"]) - 0.1)
            _vehicle_state["gear"] = "D"
            _vehicle_state["autopilot"] = "Engaged"
            _vehicle_state["drive_mode"] = "Dark"
        else:
            _vehicle_state["speed"] = max(0, int(_vehicle_state["speed"]) - 12)
            _vehicle_state["gear"] = "P"
            _vehicle_state["autopilot"] = "Standby"
            _vehicle_state["drive_mode"] = "Dark+"
        return _vehicle_snapshot()


def _merge_vehicle_state(payload: dict[str, object]) -> dict[str, object]:
    with _vehicle_lock:
        if "mode" in payload:
            _vehicle_state["mode"] = "driving" if str(payload["mode"]) == "driving" else "ambient"
        if "speed" in payload:
            try:
                _vehicle_state["speed"] = max(0, min(120, int(float(payload["speed"]))))
            except Exception:
                pass
        if "battery" in payload:
            try:
                _vehicle_state["battery"] = max(0.0, min(100.0, float(payload["battery"])))
            except Exception:
                pass
        if "gear" in payload:
            gear = str(payload["gear"]).upper().strip()[:1]
            if gear in {"P", "R", "N", "D"}:
                _vehicle_state["gear"] = gear
        if "lights_on" in payload:
            _vehicle_state["lights_on"] = bool(payload["lights_on"])
        if "climate_on" in payload:
            _vehicle_state["climate_on"] = bool(payload["climate_on"])
        if "autopilot" in payload:
            _vehicle_state["autopilot"] = str(payload["autopilot"] or "Standby")
        if "drive_mode" in payload:
            _vehicle_state["drive_mode"] = str(payload["drive_mode"] or "Dark+")
        return _vehicle_snapshot()


def _voice_worker() -> None:
    while True:
        job = _voice_queue.get()
        if job is None:
            break

        source = job.get("source", "voice")
        _call_js("toggleMode", "driving")
        _call_js("showAlert", "Listening for a command")
        query = takecommand()
        if not query or query == "none":
            _call_js("updateCommand", "No command detected.", "Try again.")
            _call_js("toggleMode", "ambient")
            continue

        _call_js("updateCommand", query, "Processing...")
        response = allCommands(query, source=source)
        _call_js("updateCommand", query, response)
        _call_js("toggleMode", "ambient")


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


def _handle_authentication_result(flag) -> None:
    global _current_user

    if flag not in (0, 1, None, "", False):
        _current_user = str(flag)
        _authenticated.set()
        _call_js("hideFaceAuth")
        settings = db.get_settings_for_user(_current_user)
        assistant_name = settings.get("assistant_name", db.get_setting("assistant_name", "ASTER") or "ASTER") or "ASTER"
        speak("Face Authentication Successful")
        _call_js("hideFaceAuthSuccess")
        speak(f"Hello, welcome. {assistant_name} is ready. How can I help you?")
        _call_js("hideStart")
        _call_js("toggleMode", "ambient")
        playAssistantSound()

        if _parse_bool(settings.get("driver_monitor_enabled", True), True):
            driver_monitor_config = DriverMonitorConfig(
                model_name=str(settings.get("driver_monitor_model", "yolov8n.pt") or "yolov8n.pt"),
                confidence_threshold=_parse_float(settings.get("driver_monitor_confidence", 0.35), 0.35),
                frame_stride=max(1, _parse_int(settings.get("driver_monitor_frame_stride", 3), 3)),
                drowsiness_alert_seconds=max(1.0, _parse_float(settings.get("driver_monitor_alert_seconds", 4.0), 4.0)),
                camera_index=_parse_int(settings.get("driver_monitor_camera_index", 0), 0),
            )

            threading.Thread(
                target=start_driver_monitor,
                args=(lambda message: _call_js("showAlert", message), driver_monitor_config),
                daemon=True,
            ).start()
    else:
        _current_user = None
        speak("Face Authentication Fail")
        _call_js("showAlert", "Face authentication failed")


def _auth_worker() -> None:
    try:
        _call_js("updateAuthStatus", "Starting camera check...")
        flag = recoganize.AuthenticateFace()
    except Exception as exc:
        db.log_event("warning", f"Face authentication worker failed: {exc}", source="auth")
        flag = 0
    try:
        _handle_authentication_result(flag)
    finally:
        _auth_started.clear()


@eel.expose
def takeCommand():
    _voice_queue.put({"source": "ui"})
    return "listening"


@eel.expose
def getSettings():
    if _current_user:
        return db.get_settings_for_user(_current_user)
    return db.get_all_settings()


@eel.expose
def saveSettings(settings):
    if isinstance(settings, dict):
        db.save_settings(settings)
        if _current_user:
            db.save_settings_for_user(_current_user, settings)
    return getSettings()


@eel.expose
def getCurrentUser():
    return _current_user or ""


@eel.expose
def listSettingsPresets():
    return db.list_settings_presets()


@eel.expose
def deleteSettingsPreset(user_name):
    db.delete_settings_preset(user_name)
    return db.list_settings_presets()


@eel.expose
def saveCurrentUserPreset(settings):
    if isinstance(settings, dict) and _current_user:
        db.save_settings(settings)
        db.save_settings_for_user(_current_user, settings)
    return getSettings()


@eel.expose
def getVehicleState():
    return _vehicle_snapshot()


@eel.expose
def advanceVehicleState(mode=None):
    return _advance_vehicle_state(str(mode or "ambient"))


@eel.expose
def setVehicleState(state):
    if isinstance(state, dict):
        return _merge_vehicle_state(state)
    return _vehicle_snapshot()


@eel.expose
def applySettingsPreset(user_name):
    target_user = str(user_name or "").strip()
    if not target_user:
        return getSettings()

    settings = db.get_settings_for_user(target_user)
    db.save_settings(settings)
    return settings


@eel.expose
def listFaceProfiles():
    return db.fetch_face_profile_summaries()


@eel.expose
def deleteFaceProfile(profile_id):
    db.delete_face_profile(profile_id)
    return db.fetch_face_profile_summaries()


@eel.expose
def getAndroidDevices():
    return list_android_devices()


@eel.expose
def connectSpotify():
    return connect_spotify()


@eel.expose
def getSpotifyAccessToken():
    return get_spotify_access_token()


@eel.expose
def getSpotifyState():
    return get_spotify_state()


@eel.expose
def getCurrentTrack():
    return get_spotify_current_track()


@eel.expose
def playSpotify(query=None):
    return spotify_play_music(query)


@eel.expose
def pauseSpotify():
    return spotify_pause_music()


@eel.expose
def nextTrack():
    return spotify_next_track()


@eel.expose
def prevTrack():
    return spotify_previous_track()


@eel.expose
def setSpotifyVolume(level):
    return spotify_set_volume(level)


@eel.expose
def transferSpotifyPlayback(device_id):
    return transfer_playback_to_device(device_id)


@eel.expose
def setSpotifyShuffle(enabled):
    return spotify_toggle_shuffle(bool(enabled))


@eel.expose
def setSpotifyRepeat(mode):
    return spotify_toggle_repeat(mode)


@eel.expose
def init():
    global _current_user
    try:
        subprocess.Popen([r"device.bat"], cwd=str(BASE_DIR), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        db.log_event("warning", f"ADB bootstrap failed: {exc}", source="bootstrap")

    _call_js("hideLoader")
    speak("Ready for Face Authentication")
    _call_js("showAlert", "Ready for Face Authentication")

    if not _auth_started.is_set():
        _auth_started.set()
        threading.Thread(target=_auth_worker, daemon=True).start()


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
