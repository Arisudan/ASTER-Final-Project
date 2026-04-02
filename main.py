from __future__ import annotations

import base64
import os
import pickle
import queue
import random
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

import cv2
import eel
import numpy as np

from Engine import db
from Engine.Features import playAssistantSound, speak, start_audio_system, takecommand
from Engine.auth import recoganize
from Engine.command import allCommands
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
)

try:
    import face_recognition  # pyright: ignore[reportMissingImports]
except Exception:
    face_recognition = None

try:
    from deepface import DeepFace  # pyright: ignore[reportMissingImports]
except Exception:
    DeepFace = None

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PIN = "2468"
NAV_ORIGIN = (13.0827, 80.2707)

_wake_queue = None
_voice_queue: "queue.Queue[dict[str, Any]]" = queue.Queue()
_authenticated = threading.Event()
_auth_running = threading.Event()
_current_user: str | None = None
_active_app = ""

_camera_lock = threading.Lock()
_camera_capture: cv2.VideoCapture | None = None
_camera_owner: str | None = None
_camera_stop_event = threading.Event()

_vehicle_lock = threading.Lock()
_vehicle_state = {
    "speed": 0,
    "battery": 92.0,
    "gear": "P",
    "mode": "ambient",
}


def _call_js(function_name: str, *args) -> None:
    try:
        getattr(eel, function_name)(*args)
    except Exception:
        return


def _http_json(url: str) -> dict[str, Any] | list[Any]:
    request = Request(url, headers={"User-Agent": "ASTER/1.0"})
    with urlopen(request, timeout=8) as response:
        payload = response.read().decode("utf-8")
    import json

    return json.loads(payload)


def _camera_backends() -> list[int | None]:
    backends: list[int | None] = []
    for backend_name in ("CAP_DSHOW", "CAP_MSMF"):
        backend = getattr(cv2, backend_name, None)
        if backend is not None:
            backends.append(backend)
    backends.append(None)
    return backends


def _open_camera(camera_index: int = 0) -> cv2.VideoCapture | None:
    indices = [camera_index]
    if camera_index != 0:
        indices.append(0)
    indices.extend([1, 2])

    for index in indices:
        for backend in _camera_backends():
            capture = cv2.VideoCapture(index, backend) if backend is not None else cv2.VideoCapture(index)
            if capture is not None and capture.isOpened():
                try:
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
                    capture.set(cv2.CAP_PROP_FPS, 30)
                except Exception:
                    pass
                return capture
            if capture is not None:
                capture.release()
    return None


def _encode_frame(frame: np.ndarray) -> str:
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 72])
    if not ok:
        return ""
    image_b64 = base64.b64encode(buffer.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{image_b64}"


def _stop_camera_locked(owner: str | None = None) -> None:
    global _camera_capture, _camera_owner
    if owner is not None and _camera_owner not in (None, owner):
        return
    _camera_stop_event.set()
    if _camera_capture is not None:
        try:
            _camera_capture.release()
        except Exception:
            pass
    _camera_capture = None
    _camera_owner = None


def _claim_camera(owner: str, camera_index: int = 0) -> tuple[bool, str]:
    global _camera_capture, _camera_owner
    with _camera_lock:
        if _camera_owner and _camera_owner != owner:
            return False, f"Camera is busy with {_camera_owner}."

        if _camera_capture is None:
            capture = _open_camera(camera_index)
            if capture is None:
                return False, "Unable to open camera. Check permissions or close other camera apps."
            _camera_capture = capture
        _camera_owner = owner
        _camera_stop_event.clear()
        return True, "Camera ready"


def _release_camera(owner: str) -> None:
    with _camera_lock:
        _stop_camera_locked(owner)


def _load_known_face_profiles() -> tuple[list[str], list[np.ndarray]]:
    names: list[str] = []
    encodings: list[np.ndarray] = []
    for name, encoding_blob in db.fetch_face_profiles():
        try:
            loaded = pickle.loads(encoding_blob)
            if isinstance(loaded, list):
                for item in loaded:
                    arr = np.asarray(item, dtype=np.float64).flatten()
                    if arr.size > 0:
                        names.append(str(name))
                        encodings.append(arr)
            else:
                arr = np.asarray(loaded, dtype=np.float64).flatten()
                if arr.size > 0:
                    names.append(str(name))
                    encodings.append(arr)
        except Exception:
            continue
    return names, encodings


def _auth_result_success(user_name: str) -> dict[str, Any]:
    global _current_user
    _current_user = user_name
    _authenticated.set()
    playAssistantSound()
    _call_js("onFaceAuthSuccess", user_name)
    _call_js("setAuthStatus", f"Welcome {user_name}. Access granted.")
    return {"ok": True, "user": user_name}


def _auth_result_fail(message: str) -> dict[str, Any]:
    _call_js("onFaceAuthFailed", message)
    _call_js("setAuthStatus", message)
    return {"ok": False, "message": message}


def _face_auth_worker() -> None:
    try:
        camera_index = int(float(db.get_setting("driver_monitor_camera_index", "0") or 0))
        ready, message = _claim_camera("face-auth", camera_index)
        if not ready:
            _auth_result_fail(message)
            return

        _call_js("setAuthStatus", "Camera started. Scanning face...")
        known_names, known_encodings = _load_known_face_profiles()

        if not known_encodings:
            _auth_result_fail("No enrolled face profile found. Use PIN fallback.")
            return

        if face_recognition is None:
            _auth_result_fail("Face recognition package not available. Use PIN fallback.")
            return

        deadline = time.time() + 24
        authenticated_name = ""

        while time.time() < deadline and not _camera_stop_event.is_set():
            if _camera_capture is None:
                break

            success, frame = _camera_capture.read()
            if not success:
                continue

            preview = cv2.flip(frame, 1)
            _call_js("updateCameraFrame", "face-auth", _encode_frame(preview))

            rgb = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
            locations = face_recognition.face_locations(rgb)
            encodings = face_recognition.face_encodings(rgb, locations)

            for candidate in encodings:
                matches = face_recognition.compare_faces(known_encodings, candidate, tolerance=0.45)
                if True in matches:
                    distances = face_recognition.face_distance(known_encodings, candidate)
                    best_idx = int(np.argmin(distances))
                    if matches[best_idx]:
                        authenticated_name = known_names[best_idx]
                        break

            if authenticated_name:
                _auth_result_success(authenticated_name)
                return

        _auth_result_fail("Face not recognized. Enter PIN to continue.")
    except Exception as exc:
        db.log_event("warning", f"Face auth error: {exc}", source="auth")
        _auth_result_fail("Face scan failed. Please use PIN fallback.")
    finally:
        _release_camera("face-auth")
        _auth_running.clear()


def _voice_worker() -> None:
    while True:
        payload = _voice_queue.get()
        if payload is None:
            break

        source = payload.get("source", "voice")
        query = takecommand()
        if not query or query == "none":
            _call_js("setAuthStatus", "Voice command not detected.")
            continue

        response = _handle_voice_command(query)
        db.log_conversation(query, response, source=source)


def _wake_monitor() -> None:
    while True:
        if _wake_queue is None:
            return
        event = _wake_queue.get()
        if event is None:
            return
        if isinstance(event, dict) and event.get("type") == "wake" and _authenticated.is_set():
            _voice_queue.put({"source": "wake"})


def _handle_voice_command(query: str) -> str:
    normalized = str(query or "").strip().lower()

    if normalized.startswith("open music"):
        openApp("music")
        return "Opening music"

    if normalized.startswith("open maps"):
        openApp("maps")
        return "Opening maps"

    if normalized in {"go home", "open home", "dashboard"}:
        closeApp()
        return "Returning to dashboard"

    if normalized.startswith("play music"):
        playSpotify("")
        return "Playing music"

    if normalized.startswith("next song"):
        nextTrack()
        return "Skipping to next song"

    if normalized.startswith("play "):
        song = normalized.replace("play ", "", 1).strip()
        playSpotify(song)
        return f"Playing {song}"

    if normalized.startswith("navigate to "):
        place = normalized.replace("navigate to ", "", 1).strip()
        navigateTo(place)
        return f"Navigating to {place}"

    if normalized.startswith("start baby monitoring"):
        startBabyMonitoring()
        openApp("camera")
        return "Starting baby monitoring"

    if normalized.startswith("start emotion mode"):
        startEmotionDetection()
        openApp("emotion")
        return "Starting emotion detection"

    try:
        return allCommands(query, source="voice")
    except Exception:
        return "Command processed"


def _emotion_worker() -> None:
    camera_index = int(float(db.get_setting("driver_monitor_camera_index", "0") or 0))
    ready, message = _claim_camera("emotion", camera_index)
    if not ready:
        _call_js("setEmotionResult", {"ok": False, "message": message})
        return

    frames: list[np.ndarray] = []
    try:
        for _ in range(10):
            if _camera_capture is None or _camera_stop_event.is_set():
                break
            ok, frame = _camera_capture.read()
            if not ok:
                continue
            preview = cv2.flip(frame, 1)
            frames.append(preview)
            _call_js("updateCameraFrame", "baby-monitor", _encode_frame(preview))
            time.sleep(0.12)

        if not frames:
            _call_js("setEmotionResult", {"ok": False, "message": "No camera frames captured."})
            return

        mood_counts: dict[str, int] = {}
        for frame in frames:
            emotion = "neutral"
            if DeepFace is not None:
                try:
                    analysis = DeepFace.analyze(frame, actions=["emotion"], enforce_detection=False, silent=True)
                    if isinstance(analysis, list):
                        analysis = analysis[0]
                    emotion = str(analysis.get("dominant_emotion", "neutral")).lower()
                except Exception:
                    emotion = "neutral"
            mood_counts[emotion] = mood_counts.get(emotion, 0) + 1

        dominant = max(mood_counts.items(), key=lambda item: item[1])[0]
        mapping = {
            "happy": "upbeat driving hits",
            "sad": "calm lofi chill",
            "angry": "relaxing ambient music",
            "neutral": "daily mix",
        }
        query = mapping.get(dominant, "daily mix")
        play_result = spotify_play_music(query)

        result = {
            "ok": True,
            "emotion": dominant,
            "query": query,
            "spotify": play_result,
            "message": f"Detected {dominant}. Playing {query}.",
        }
        _call_js("setEmotionResult", result)
    finally:
        _release_camera("emotion")


def _camera_stream_worker(owner: str) -> None:
    while not _camera_stop_event.is_set():
        if _camera_capture is None:
            break
        ok, frame = _camera_capture.read()
        if not ok:
            continue
        preview = cv2.flip(frame, 1)
        _call_js("updateCameraFrame", owner, _encode_frame(preview))
        time.sleep(0.03)


def _vehicle_worker() -> None:
    while True:
        with _vehicle_lock:
            mode = _vehicle_state.get("mode", "ambient")
            speed = int(_vehicle_state.get("speed", 0))
            battery = float(_vehicle_state.get("battery", 92))
            if mode == "driving":
                speed = max(6, min(120, speed + random.randint(-2, 7)))
                battery = max(18.0, battery - 0.03)
            else:
                speed = max(0, speed - 8)
                battery = min(100.0, battery + 0.01)
            _vehicle_state["speed"] = speed
            _vehicle_state["battery"] = battery
            _vehicle_state["gear"] = "D" if speed > 0 else "P"
        time.sleep(1.0)


@eel.expose
def init() -> dict[str, Any]:
    try:
        subprocess.Popen([r"device.bat"], cwd=str(BASE_DIR), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        db.log_event("warning", f"ADB bootstrap failed: {exc}", source="bootstrap")

    _call_js("setAuthStatus", "System ready. Starting authentication...")
    return {"ok": True, "message": "Initialized"}


@eel.expose
def startFaceAuth() -> dict[str, Any]:
    if _auth_running.is_set():
        return {"ok": False, "message": "Face authentication already running."}
    _auth_running.set()
    threading.Thread(target=_face_auth_worker, daemon=True).start()
    return {"ok": True, "message": "Face authentication started."}


@eel.expose
def verifyPIN(pin: str) -> dict[str, Any]:
    entered = str(pin or "").strip()
    if entered == DEFAULT_PIN:
        return _auth_result_success("Driver")
    return _auth_result_fail("Invalid PIN. Please retry.")


@eel.expose
def openApp(appName: str) -> dict[str, Any]:
    global _active_app
    _active_app = str(appName or "").strip().lower()
    _call_js("setActiveApp", _active_app)
    with _vehicle_lock:
        _vehicle_state["mode"] = "driving"
    return {"ok": True, "activeApp": _active_app}


@eel.expose
def closeApp() -> dict[str, Any]:
    global _active_app
    _active_app = ""
    stopCamera()
    _call_js("setActiveApp", "")
    with _vehicle_lock:
        _vehicle_state["mode"] = "ambient"
    return {"ok": True}


@eel.expose
def startBabyMonitoring() -> dict[str, Any]:
    camera_index = int(float(db.get_setting("driver_monitor_camera_index", "0") or 0))
    ready, message = _claim_camera("baby-monitor", camera_index)
    if not ready:
        return {"ok": False, "message": message}

    threading.Thread(target=_camera_stream_worker, args=("baby-monitor",), daemon=True).start()
    return {"ok": True, "message": "Baby monitoring started."}


@eel.expose
def stopCamera() -> dict[str, Any]:
    _release_camera("baby-monitor")
    _release_camera("emotion")
    _release_camera("face-auth")
    return {"ok": True, "message": "Camera stopped."}


@eel.expose
def startEmotionDetection() -> dict[str, Any]:
    threading.Thread(target=_emotion_worker, daemon=True).start()
    return {"ok": True, "message": "Emotion detection started."}


@eel.expose
def playSpotify(query: str | None = None) -> dict[str, Any]:
    result = spotify_play_music(query)
    _call_js("setSpotifyState", result.get("state", result))
    return result


@eel.expose
def pauseSpotify() -> dict[str, Any]:
    result = spotify_pause_music()
    _call_js("setSpotifyState", result.get("state", result))
    return result


@eel.expose
def nextTrack() -> dict[str, Any]:
    result = spotify_next_track()
    _call_js("setSpotifyState", result.get("state", result))
    return result


@eel.expose
def prevTrack() -> dict[str, Any]:
    result = spotify_previous_track()
    _call_js("setSpotifyState", result.get("state", result))
    return result


@eel.expose
def setSpotifyVolume(level: int | str) -> dict[str, Any]:
    result = spotify_set_volume(level)
    _call_js("setSpotifyState", result.get("state", result))
    return result


@eel.expose
def getSpotifyState() -> dict[str, Any]:
    return get_spotify_state()


@eel.expose
def getCurrentTrack() -> dict[str, Any]:
    return get_spotify_current_track()


@eel.expose
def connectSpotify() -> dict[str, Any]:
    return connect_spotify()


@eel.expose
def getSpotifyAccessToken() -> str:
    return get_spotify_access_token()


@eel.expose
def navigateTo(place: str) -> dict[str, Any]:
    destination = str(place or "").strip()
    if not destination:
        return {"ok": False, "message": "Destination is empty."}

    try:
        encoded = quote_plus(destination)
        geo = _http_json(f"https://nominatim.openstreetmap.org/search?q={encoded}&format=json&limit=1")
        if not isinstance(geo, list) or not geo:
            return {"ok": False, "message": f"No route found for {destination}."}

        lat = float(geo[0]["lat"])
        lon = float(geo[0]["lon"])
        origin_lon, origin_lat = NAV_ORIGIN[1], NAV_ORIGIN[0]

        route_payload = _http_json(
            f"https://router.project-osrm.org/route/v1/driving/{origin_lon},{origin_lat};{lon},{lat}?overview=full&geometries=geojson"
        )
        routes = route_payload.get("routes", []) if isinstance(route_payload, dict) else []
        if not routes:
            return {"ok": False, "message": "Routing engine did not return a path."}

        coords = routes[0].get("geometry", {}).get("coordinates", [])
        route = [[float(coord[1]), float(coord[0])] for coord in coords]

        result = {
            "ok": True,
            "message": f"Navigating to {destination}",
            "destination": {"name": destination, "lat": lat, "lon": lon},
            "route": route,
        }
        _call_js("setNavigationResult", result)
        return result
    except Exception as exc:
        return {"ok": False, "message": f"Navigation failed: {exc}"}


@eel.expose
def takeCommand() -> str:
    _voice_queue.put({"source": "ui"})
    return "listening"


@eel.expose
def getSettings() -> dict[str, str]:
    if _current_user:
        return db.get_settings_for_user(_current_user)
    return db.get_all_settings()


@eel.expose
def saveSettings(settings: dict[str, Any]) -> dict[str, str]:
    if isinstance(settings, dict):
        db.save_settings(settings)
        if _current_user:
            db.save_settings_for_user(_current_user, settings)
    return getSettings()


def _start_background_threads() -> None:
    threading.Thread(target=_voice_worker, daemon=True).start()
    threading.Thread(target=_wake_monitor, daemon=True).start()
    threading.Thread(target=_vehicle_worker, daemon=True).start()


def start(wake_queue=None) -> None:
    global _wake_queue
    _wake_queue = wake_queue

    db.init_db()
    db.start_background_workers()
    start_audio_system()

    eel.init("www")
    _start_background_threads()

    os.system('start msedge.exe --app="http://localhost:8000/index.html"')
    eel.start("index.html", mode=None, host="localhost", block=True)
