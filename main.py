from __future__ import annotations

import base64
from collections import Counter, deque
import os
import pickle
import queue
import re
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
from Engine.baby_monitor_dl import BabyMonitorDL
from Engine.Features import playAssistantSound, speak, start_audio_system, takecommand
from Engine.auth import recoganize
from Engine.command import allCommands
from Engine.spotify_backend import (
    connect_spotify,
    get_access_token as get_spotify_access_token,
    get_current_track as get_spotify_current_track,
    get_player_state as get_spotify_state,
    get_recently_played as get_spotify_recently_played,
    get_user_playlists as get_spotify_user_playlists,
    get_user_profile as get_spotify_user_profile,
    get_user_saved_tracks as get_spotify_user_saved_tracks,
    next_track as spotify_next_track,
    pause_music as spotify_pause_music,
    play_uri as spotify_play_uri,
    play_music as spotify_play_music,
    play_emotion_based_playlist as spotify_play_emotion_playlist,
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
_baby_monitor_running = threading.Event()
_emotion_running = threading.Event()
_baby_monitor_dl = BabyMonitorDL(db.get_all_settings())
_baby_last_state = {
    "wake_up": False,
    "moving": False,
    "outside": False,
    "ear": 0.0,
    "motion_score": 0.0,
    "message": "Baby monitor idle.",
}

# Environment controls state
_lights_state = {
    "on": False,
    "brightness": 0,
}

_climate_state = {
    "temperature": 22,
}

_voice_messages = []

_EMOTION_FALLBACK_MAPPINGS = {
    "happy": {
        "query": "upbeat feel good hits",
        "keywords": ["happy", "upbeat", "feel good", "cheerful", "joy", "positive", "dance", "party"],
    },
    "sad": {
        "query": "calm lo-fi chill",
        "keywords": ["sad", "melancholy", "blues", "lo-fi", "chill", "emotional", "ballad"],
    },
    "angry": {
        "query": "relaxing ambient piano",
        "keywords": ["calm", "relax", "ambient", "peaceful", "soothe", "meditation"],
    },
    "fear": {
        "query": "soothing instrumental",
        "keywords": ["soothe", "calm", "relax", "instrumental", "peaceful", "serene"],
    },
    "surprise": {
        "query": "fresh pop discoveries",
        "keywords": ["fresh", "new", "discovery", "pop", "trending", "hits"],
    },
    "disgust": {
        "query": "calm focus music",
        "keywords": ["calm", "focus", "concentrate", "study", "work", "ambient"],
    },
    "neutral": {
        "query": "daily mix",
        "keywords": ["favorite", "liked", "saved", "daily", "usual"],
    },
}




def _call_js(function_name: str, *args) -> None:
    try:
        getattr(eel, function_name)(*args)
    except Exception:
        return


def _read_int_setting(key: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(float(db.get_setting(key, str(default)) or default))
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _read_float_setting(key: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(db.get_setting(key, str(default)) or default)
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _emotion_query_for_label(label: str) -> str:
    emotion_data = _EMOTION_FALLBACK_MAPPINGS.get(str(label or "").strip().lower(), {})
    if isinstance(emotion_data, dict):
        return emotion_data.get("query", "daily mix")
    return str(emotion_data or "daily mix")


def _emotion_keywords_for_label(label: str) -> list[str]:
    emotion_data = _EMOTION_FALLBACK_MAPPINGS.get(str(label or "").strip().lower(), {})
    if isinstance(emotion_data, dict):
        return emotion_data.get("keywords", [])
    return []


def _emotion_confidence_from_analysis(analysis: dict[str, Any] | None) -> tuple[str, float]:
    if not analysis:
        return "neutral", 0.0

    emotion_map = analysis.get("emotion") if isinstance(analysis, dict) else None
    if not isinstance(emotion_map, dict) or not emotion_map:
        dominant = str(analysis.get("dominant_emotion", "neutral")).lower()
        return dominant, 0.0

    dominant, score = max(emotion_map.items(), key=lambda item: float(item[1] or 0.0))
    total = sum(max(0.0, float(value or 0.0)) for value in emotion_map.values())
    confidence = float(score or 0.0) / total if total > 0 else 0.0
    return str(dominant or "neutral").lower(), confidence



def _setting_bool(key: str, default: bool = False) -> bool:
    value = str(db.get_setting(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _http_json(url: str) -> dict[str, Any] | list[Any]:
    request = Request(url, headers={"User-Agent": "ASTER/1.0"})
    with urlopen(request, timeout=8) as response:
        payload = response.read().decode("utf-8")
    import json

    return json.loads(payload)


def _adb_base_command() -> list[str]:
    command = ["adb"]
    device_serial = str(db.get_setting("android_device_serial", "") or "").strip()
    if device_serial:
        command.extend(["-s", device_serial])
    return command


def _run_adb(arguments: list[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            _adb_base_command() + arguments,
            capture_output=True,
            text=True,
            check=False,
        )
        output = (result.stdout or "").strip() or (result.stderr or "").strip()
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "message": output,
            "stdout": (result.stdout or "").strip(),
            "stderr": (result.stderr or "").strip(),
        }
    except Exception as exc:
        return {"ok": False, "returncode": -1, "message": str(exc), "stdout": "", "stderr": str(exc)}


def _list_android_devices_structured() -> list[dict[str, str]]:
    result = _run_adb(["devices"])
    if not result.get("ok"):
        return []

    devices: list[dict[str, str]] = []
    for line in str(result.get("stdout", "")).splitlines():
        row = line.strip()
        if not row or row.lower().startswith("list of devices"):
            continue
        parts = row.split()
        if len(parts) >= 2:
            devices.append({"serial": parts[0], "status": parts[1]})
    return devices


def _camera_backends() -> list[int | None]:
    backends: list[int | None] = []
    for backend_name in ("CAP_DSHOW", "CAP_MSMF"):
        backend = getattr(cv2, backend_name, None)
        if backend is not None:
            backends.append(backend)
    backends.append(None)
    return backends


def _open_camera(camera_index: int = 0) -> cv2.VideoCapture | None:
    # Clamp persisted settings to realistic USB camera indexes.
    safe_index = int(camera_index) if isinstance(camera_index, int) else 0
    if safe_index < 0 or safe_index > 1:
        safe_index = 0

    indices = [safe_index]
    if safe_index != 0:
        indices.append(0)
    # Avoid probing many invalid indexes which can produce noisy driver errors.
    indices = list(dict.fromkeys(indices))

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


def _load_haar_cascade() -> cv2.CascadeClassifier | None:
    local_path = BASE_DIR / "Engine" / "auth" / "haarcascade_frontalface_default.xml"
    candidate_paths = [local_path, Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"]
    for path in candidate_paths:
        try:
            cascade = cv2.CascadeClassifier(str(path))
            if not cascade.empty():
                return cascade
        except Exception:
            continue
    return None


def _fallback_face_vector(frame_bgr: np.ndarray, cascade: cv2.CascadeClassifier | None) -> np.ndarray | None:
    if cascade is None:
        return None

    try:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(80, 80))
        if len(faces) == 0:
            return None
        x, y, width, height = faces[0]
        face = gray[y : y + height, x : x + width]
        normalized = cv2.resize(face, (64, 64), interpolation=cv2.INTER_AREA)
        return normalized.flatten().astype(np.float32)
    except Exception:
        return None


def _fallback_match_name(candidate: np.ndarray, known_names: list[str], known_encodings: list[np.ndarray]) -> str:
    best_name = ""
    best_score: float | None = None

    for name, encoding in zip(known_names, known_encodings):
        try:
            known = np.asarray(encoding, dtype=np.float32).flatten()
            if known.size != candidate.size:
                continue
            score = float(np.mean(np.abs(known - candidate)))
            if best_score is None or score < best_score:
                best_score = score
                best_name = str(name)
        except Exception:
            continue

    if best_name and best_score is not None and best_score <= 28.0:
        return best_name
    return ""


def _auth_result_success(user_name: str) -> dict[str, Any]:
    global _current_user
    _current_user = user_name
    _authenticated.set()
    playAssistantSound()
    speak(f"Welcome Back, {user_name}")
    _call_js("onFaceAuthSuccess", user_name)
    _call_js("setAuthStatus", f"Welcome {user_name}. Access granted.")
    return {"ok": True, "user": user_name}


def _auth_result_fail(message: str) -> dict[str, Any]:
    _call_js("onFaceAuthFailed", message)
    _call_js("setAuthStatus", message)
    return {"ok": False, "message": message}


def _face_auth_worker() -> None:
    try:
        _call_js("setAuthStatus", "Ready for Face Authentication")
        speak("Ready For Face Authentication")
        # `speak` is queued asynchronously; wait briefly so voice is heard before camera starts.
        time.sleep(2.0)

        camera_index = int(float(db.get_setting("driver_monitor_camera_index", "0") or 0))
        if camera_index < 0 or camera_index > 1:
            camera_index = 0
        ready, message = _claim_camera("face-auth", camera_index)
        if not ready:
            _auth_result_fail(message)
            return

        _call_js("setAuthStatus", "Camera started. Scanning face...")
        known_names, known_encodings = _load_known_face_profiles()

        recognition_available = face_recognition is not None and bool(known_encodings)
        fallback_available = bool(known_encodings)
        fallback_cascade = _load_haar_cascade() if fallback_available else None

        if not known_encodings:
            _call_js("setAuthStatus", "No enrolled face profile found. Showing camera preview. Use PIN fallback.")
        elif face_recognition is None:
            _call_js("setAuthStatus", "Advanced face package unavailable. Running basic face scan...")

        timeout_seconds = int(float(db.get_setting("face_auth_timeout_seconds", "24") or 24))
        if timeout_seconds < 8:
            timeout_seconds = 8
        deadline = time.time() + timeout_seconds
        authenticated_name = ""

        while time.time() < deadline and not _camera_stop_event.is_set():
            if _camera_capture is None:
                break

            success, frame = _camera_capture.read()
            if not success:
                continue

            preview = cv2.flip(frame, 1)
            _call_js("updateCameraFrame", "face-auth", _encode_frame(preview))

            if recognition_available:
                try:
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
                except Exception:
                    recognition_available = False
                    _call_js("setAuthStatus", "Primary face scan unstable. Continuing with basic fallback scan...")
            elif fallback_available:
                candidate = _fallback_face_vector(preview, fallback_cascade)
                if candidate is not None:
                    authenticated_name = _fallback_match_name(candidate, known_names, known_encodings)

            if authenticated_name:
                _auth_result_success(authenticated_name)
                return

        if not known_encodings:
            _auth_result_fail("No enrolled face profile found. Enter PIN to continue.")
        elif face_recognition is None:
            _auth_result_fail("Face package not available and fallback did not match. Enter PIN to continue.")
        else:
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

    if normalized.startswith("open camera") or normalized.startswith("open baby monitoring"):
        openApp("camera")
        startBabyMonitoring()
        return "Opening baby monitoring"

    if normalized.startswith("stop camera") or normalized.startswith("stop baby monitoring"):
        stopCamera()
        return "Stopping camera"

    if normalized.startswith("call "):
        number = "".join(ch for ch in normalized if ch.isdigit() or ch == "+")
        if not number:
            digits = re.findall(r"\d+", normalized)
            number = "".join(digits)
        if number:
            dialNumber(number)
            openApp("calls")
            return f"Calling {number}"

    if normalized in {"end call", "hang up", "hangup"}:
        endCall()
        return "Ending call"

    if normalized.startswith("open dialer"):
        openDialer()
        openApp("calls")
        return "Opening dialer"

    try:
        return allCommands(query, source="voice")
    except Exception:
        return "Command processed"


def _emotion_worker() -> None:
    _emotion_running.set()
    camera_index = int(float(db.get_setting("driver_monitor_camera_index", "0") or 0))
    if camera_index < 0 or camera_index > 1:
        camera_index = 0
    ready, message = _claim_camera("emotion", camera_index)
    if not ready:
        _call_js("setEmotionResult", {"ok": False, "message": message})
        _emotion_running.clear()
        return

    sample_target = _read_int_setting("emotion_sample_count", 12, 6, 24)
    confidence_threshold = _read_float_setting("emotion_confidence_threshold", 0.60, 0.45, 0.95)
    sample_interval = _read_float_setting("emotion_sample_interval_seconds", 0.18, 0.08, 0.5)
    autoplay_enabled = _setting_bool("emotion_auto_play_enabled", True)
    deadline = time.time() + max(5.0, min(30.0, sample_target * sample_interval + 5.0))

    emotion_samples: list[str] = []
    confidence_samples: list[float] = []
    emotion_confidence_map: dict[str, list[float]] = {}
    sample_count = 0

    _call_js(
        "setEmotionResult",
        {
            "ok": True,
            "stage": "analyzing",
            "emotion": "neutral",
            "smoothed_emotion": "neutral",
            "confidence": 0.0,
            "sample_count": 0,
            "sample_target": sample_target,
            "message": "Camera started. Analyzing expression...",
        },
    )

    try:
        while sample_count < sample_target and time.time() < deadline and not _camera_stop_event.is_set():
            if _camera_capture is None:
                break
            ok, frame = _camera_capture.read()
            if not ok:
                time.sleep(sample_interval)
                continue
            preview = cv2.flip(frame, 1)
            _call_js("updateCameraFrame", "emotion", _encode_frame(preview))
            emotion = "neutral"
            frame_confidence = 0.0
            if DeepFace is not None:
                try:
                    analysis = DeepFace.analyze(preview, actions=["emotion"], enforce_detection=False, silent=True)
                    if isinstance(analysis, list):
                        analysis = analysis[0] if analysis else {}
                    emotion, frame_confidence = _emotion_confidence_from_analysis(analysis if isinstance(analysis, dict) else {})
                except Exception:
                    emotion = "neutral"
                    frame_confidence = 0.0

            sample_count += 1
            emotion_samples.append(emotion)
            confidence_samples.append(frame_confidence)
            
            if emotion not in emotion_confidence_map:
                emotion_confidence_map[emotion] = []
            emotion_confidence_map[emotion].append(frame_confidence)

            most_common_emotion = Counter(emotion_samples).most_common(1)[0][0] if emotion_samples else "neutral"
            avg_confidence = sum(confidence_samples) / len(confidence_samples) if confidence_samples else 0.0

            status_message = (
                f"Analyzing expression... {most_common_emotion.title()} detected. "
                f"Sample {sample_count}/{sample_target}"
            )
            _call_js(
                "setEmotionResult",
                {
                    "ok": True,
                    "stage": "analyzing",
                    "emotion": emotion,
                    "smoothed_emotion": most_common_emotion,
                    "confidence": round(avg_confidence, 3),
                    "frame_confidence": round(frame_confidence, 3),
                    "sample_count": sample_count,
                    "sample_target": sample_target,
                    "message": status_message,
                },
            )

            time.sleep(sample_interval)

        if sample_count == 0:
            _call_js("setEmotionResult", {"ok": False, "message": "No camera frames captured."})
            return

        emotion_counts = Counter(emotion_samples)
        final_label = emotion_counts.most_common(1)[0][0] if emotion_counts else "neutral"
        
        final_emotion_confidences = emotion_confidence_map.get(final_label, [0.0])
        final_confidence = sum(final_emotion_confidences) / len(final_emotion_confidences) if final_emotion_confidences else 0.0
        
        overall_avg_confidence = sum(confidence_samples) / len(confidence_samples) if confidence_samples else 0.0
        final_confidence = max(final_confidence, overall_avg_confidence)

        query = _emotion_query_for_label(final_label)
        emotion_keywords = _emotion_keywords_for_label(final_label)
        play_result: dict[str, Any] | None = None
        
        if autoplay_enabled:
            # Keep Spotify wiring active even when confidence is low by falling back to a safe mix.
            playback_query = query if final_confidence >= confidence_threshold else _emotion_query_for_label("neutral")

            # Try emotion-based playlist first only when confidence is high enough.
            if emotion_keywords and final_confidence >= confidence_threshold:
                play_result = spotify_play_emotion_playlist(final_label, emotion_keywords)

            # Fallback to query-based playback whenever playlist mapping is unavailable.
            if not play_result or not play_result.get("ok"):
                play_result = spotify_play_music(playback_query)

        if play_result and play_result.get("ok"):
            track_name = play_result.get("track_name") or "music"
            playlist_name = play_result.get("playlist_name") or ""
            if playlist_name:
                message = f"Detected {final_label}. Playing '{track_name}' from '{playlist_name}'."
            elif final_confidence < confidence_threshold:
                message = (
                    f"Detected {final_label} with low confidence ({final_confidence:.0%}). "
                    "Playing neutral daily mix on Spotify."
                )
            else:
                message = f"Detected {final_label}. Playing {query}."
        elif autoplay_enabled:
            device_error = play_result and play_result.get("message") if play_result else "Spotify unavailable."
            if "No active Spotify device" in str(device_error):
                message = f"Detected {final_label} with {final_confidence:.0%} confidence. No active Spotify device. Open Spotify on a device first."
            else:
                message = f"Detected {final_label} with {final_confidence:.0%} confidence. Spotify autoplay unavailable: {device_error}"
        else:
            message = f"Detected {final_label} with {final_confidence:.0%} confidence. Autoplay is disabled."

        _call_js(
            "setEmotionResult",
            {
                "ok": True,
                "stage": "done",
                "emotion": final_label,
                "smoothed_emotion": final_label,
                "confidence": round(final_confidence, 3),
                "sample_count": sample_count,
                "sample_target": sample_target,
                "query": query,
                "spotify": play_result,
                "message": message,
            },
        )
    finally:
        _release_camera("emotion")
        _emotion_running.clear()


def _camera_stream_worker(owner: str, running_event: threading.Event) -> None:
    try:
        while not _camera_stop_event.is_set():
            if _camera_capture is None:
                break
            ok, frame = _camera_capture.read()
            if not ok:
                continue
            preview = cv2.flip(frame, 1)
            if owner == "baby-monitor" and _setting_bool("baby_monitor_dl_enabled", True):
                processed, result = _baby_monitor_dl.analyze_frame(preview)
                _baby_last_state.update(
                    {
                        "wake_up": bool(result.wake_up),
                        "moving": bool(result.moving),
                        "outside": bool(result.outside),
                        "ear": float(result.ear),
                        "motion_score": float(result.motion_score),
                        "message": str(result.message),
                    }
                )
                _call_js("setBabyMonitorState", dict(_baby_last_state))
                _call_js("updateCameraFrame", owner, _encode_frame(processed))
            else:
                _call_js("updateCameraFrame", owner, _encode_frame(preview))
            time.sleep(0.03)
    finally:
        running_event.clear()



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
    configured_pin = str(db.get_setting("security_pin", DEFAULT_PIN) or DEFAULT_PIN).strip()
    if entered == configured_pin:
        return _auth_result_success("Driver")
    return _auth_result_fail("Invalid PIN. Please retry.")


@eel.expose
def openApp(appName: str) -> dict[str, Any]:
    global _active_app
    _active_app = str(appName or "").strip().lower()
    _call_js("openAppFromBackend", _active_app)
    return {"ok": True, "activeApp": _active_app}


@eel.expose
def closeApp() -> dict[str, Any]:
    global _active_app
    _active_app = ""
    stopCamera()
    _call_js("closeAppFromBackend")
    return {"ok": True}


@eel.expose
def startBabyMonitoring() -> dict[str, Any]:
    if _baby_monitor_running.is_set():
        return {"ok": False, "message": "Baby monitoring is already running."}

    if _emotion_running.is_set():
        return {"ok": False, "message": "Emotion detection is using camera. Please wait."}

    camera_index = int(float(db.get_setting("driver_monitor_camera_index", "0") or 0))
    if camera_index < 0 or camera_index > 1:
        camera_index = 0
    ready, message = _claim_camera("baby-monitor", camera_index)
    if not ready:
        return {"ok": False, "message": message}

    _baby_monitor_running.set()
    threading.Thread(target=_camera_stream_worker, args=("baby-monitor", _baby_monitor_running), daemon=True).start()
    return {"ok": True, "message": "Baby monitoring started with deep-learning analysis."}


@eel.expose
def stopCamera() -> dict[str, Any]:
    _release_camera("baby-monitor")
    _release_camera("emotion")
    _release_camera("face-auth")
    _baby_monitor_running.clear()
    return {"ok": True, "message": "Camera stopped."}


@eel.expose
def getBabyMonitorState() -> dict[str, Any]:
    return dict(_baby_last_state)


@eel.expose
def setBabyMonitorRegion(points: list[list[float]]) -> dict[str, Any]:
    _baby_monitor_dl.set_region_points(points)
    return {
        "ok": True,
        "message": "Monitoring region updated.",
        "points": _baby_monitor_dl.get_region_points(),
    }


@eel.expose
def startEmotionDetection() -> dict[str, Any]:
    if _emotion_running.is_set():
        return {"ok": False, "message": "Emotion detection already running."}

    if _baby_monitor_running.is_set():
        _release_camera("baby-monitor")
        _baby_monitor_running.clear()
        time.sleep(0.12)

    threading.Thread(target=_emotion_worker, daemon=True).start()
    return {"ok": True, "message": "Emotion detection started."}


@eel.expose
def playSpotify(query: str | None = None) -> dict[str, Any]:
    result = spotify_play_music(query)
    _call_js("setSpotifyState", result.get("state", result))
    return result


@eel.expose
def playSpotifyUri(uri: str) -> dict[str, Any]:
    result = spotify_play_uri(uri)
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
def getSpotifyUserProfile() -> dict[str, Any]:
    return get_spotify_user_profile()


@eel.expose
def getSpotifyUserPlaylists() -> dict[str, Any]:
    return get_spotify_user_playlists(limit=50)


@eel.expose
def getSpotifyUserSavedTracks() -> dict[str, Any]:
    return get_spotify_user_saved_tracks(limit=50)


@eel.expose
def getSpotifyRecentlyPlayed() -> dict[str, Any]:
    return get_spotify_recently_played(limit=50)


@eel.expose
def getAndroidDevices() -> dict[str, Any]:
    devices = _list_android_devices_structured()
    if not devices:
        return {"ok": False, "devices": [], "message": "No Android devices detected. Connect device and enable USB debugging."}
    return {"ok": True, "devices": devices, "message": f"{len(devices)} Android device(s) ready."}


@eel.expose
def openDialer() -> dict[str, Any]:
    result = _run_adb(["shell", "am", "start", "-a", "android.intent.action.DIAL"])
    if result.get("ok"):
        return {"ok": True, "message": "Dialer opened on Android device."}
    return {"ok": False, "message": result.get("message") or "Unable to open Android dialer."}


@eel.expose
def dialNumber(number: str) -> dict[str, Any]:
    dial_number = str(number or "").strip()
    if not dial_number:
        return {"ok": False, "message": "Enter a valid phone number."}

    sanitized = "".join(ch for ch in dial_number if ch.isdigit() or ch == "+")
    if not sanitized:
        return {"ok": False, "message": "Phone number must contain digits."}

    result = _run_adb(["shell", "am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{sanitized}"])
    if result.get("ok"):
        return {"ok": True, "message": f"Calling {sanitized} via connected Android device."}

    fallback = _run_adb(["shell", "am", "start", "-a", "android.intent.action.DIAL", "-d", f"tel:{sanitized}"])
    if fallback.get("ok"):
        return {"ok": True, "message": f"Dialer opened with number {sanitized}."}

    return {"ok": False, "message": fallback.get("message") or result.get("message") or "Unable to place call."}


@eel.expose
def endCall() -> dict[str, Any]:
    result = _run_adb(["shell", "input", "keyevent", "6"])
    if result.get("ok"):
        return {"ok": True, "message": "Call end command sent."}
    return {"ok": False, "message": result.get("message") or "Unable to end call."}


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
        _baby_monitor_dl.update_settings(settings)
        if _current_user:
            db.save_settings_for_user(_current_user, settings)
    return getSettings()


@eel.expose
def getLightsState() -> dict[str, Any]:
    return {"ok": True, **_lights_state}


@eel.expose
def setLightsState(on: bool, brightness: int = 0) -> dict[str, Any]:
    _lights_state["on"] = bool(on)
    _lights_state["brightness"] = max(0, min(100, int(brightness)))
    return {"ok": True, **_lights_state}


@eel.expose
def getClimateState() -> dict[str, Any]:
    return {"ok": True, **_climate_state}


@eel.expose
def setClimateState(temperature: int) -> dict[str, Any]:
    _climate_state["temperature"] = max(16, min(30, int(temperature)))
    return {"ok": True, **_climate_state}


@eel.expose
def addVoiceMessage(message_type: str, message: str) -> dict[str, Any]:
    if message_type not in ["user", "assistant", "system"]:
        message_type = "system"
    _voice_messages.append({"type": message_type, "text": message, "timestamp": time.time()})
    if len(_voice_messages) > 100:
        _voice_messages.pop(0)
    return {"ok": True, "message_count": len(_voice_messages)}


@eel.expose
def getVoiceHistory() -> dict[str, Any]:
    return {"ok": True, "messages": _voice_messages[-20:]}


@eel.expose
def showNavigationDirections(destination: str, distance: str, eta: str, current_instruction: str = "", next_instruction: str = "") -> dict[str, Any]:
    directions = {
        "destination": destination,
        "total_distance": distance,
        "eta": eta,
        "current_instruction": current_instruction or "Starting navigation...",
        "current_distance": "0 m",
        "next_instruction": next_instruction or "Continue",
    }
    _call_js("showDirections", directions)
    return {"ok": True, **directions}


def _start_background_threads() -> None:
    threading.Thread(target=_voice_worker, daemon=True).start()
    threading.Thread(target=_wake_monitor, daemon=True).start()


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
