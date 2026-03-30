from __future__ import annotations

import os
import random
import re
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

import cv2  # pyright: ignore[reportMissingImports]
import eel
import requests

from Engine import db
from Engine.Features import control_android_media, list_android_devices, open_android_app, send_sms, speak, takecommand as feature_takecommand
from Engine.ai_memory import generate_response
from Engine.spotify_backend import next_track as spotify_next_track
from Engine.spotify_backend import pause_music as spotify_pause_music
from Engine.spotify_backend import play_music as spotify_play_music
from Engine.spotify_backend import previous_track as spotify_previous_track


def takecommand():
    return feature_takecommand()


def _play_first_music_track():
    music_roots = [Path.home() / "Music", Path.cwd() / "music", Path.cwd() / "www" / "assets" / "music"]
    for music_root in music_roots:
        if not music_root.exists():
            continue
        tracks = []
        for extension in ("*.mp3", "*.wav", "*.m4a", "*.ogg"):
            tracks.extend(music_root.glob(extension))
        if tracks:
            try:
                os.startfile(str(tracks[0]))
                return f"Playing {tracks[0].stem}."
            except Exception:
                pass
        try:
            os.startfile(str(music_root))
            return "Opening music folder."
        except Exception:
            continue
    return "No music library found."


def _play_spotify_or_local(query: str | None = None):
    spotify_result = spotify_play_music(query)
    if isinstance(spotify_result, dict) and spotify_result.get("ok"):
        return spotify_result.get("message", "Playing music on Spotify.")
    if query and str(query).strip():
        return _play_first_music_track()
    return spotify_result.get("message", "Spotify playback is unavailable.") if isinstance(spotify_result, dict) else "Spotify playback is unavailable."


def _open_camera():
    try:
        os.system('start microsoft.windows.camera:')
        return "Opening camera."
    except Exception:
        pass

    capture = cv2.VideoCapture(0)
    if not capture.isOpened():
        return "Camera is not available."

    start_time = datetime.now()
    while True:
        success, frame = capture.read()
        if not success:
            break
        cv2.imshow("ASTER Camera", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
        if (datetime.now() - start_time).seconds > 15:
            break

    capture.release()
    cv2.destroyAllWindows()
    return "Camera closed."


def _navigation_simulation():
    webbrowser.open("https://www.google.com/maps")
    return "Starting navigation simulation on Google Maps."


def _extract_android_target(query_text: str) -> str:
    cleaned_query = query_text
    patterns = [
        r"^(?:open|launch|start)\s+(?:android\s+)?app\s+(.+)$",
        r"^(?:open|launch|start)\s+(.+?)\s+app$",
        r"^(?:open|launch|start)\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned_query)
        if match:
            return match.group(1).strip()
    return ""


def _parse_sms_command(query_text: str):
    sms_patterns = [
        r"^(?:send\s+)?sms(?:\s+to)?\s+(?P<number>[\d+()\- ]+)\s+(?P<message>.+)$",
        r"^(?:text|message)\s+(?P<number>[\d+()\- ]+)\s+(?P<message>.+)$",
    ]
    for pattern in sms_patterns:
        match = re.search(pattern, query_text)
        if match:
            return match.group("number").strip(), match.group("message").strip()
    return "", ""


@eel.expose
def allCommands(query, source="voice"):
    query_text = str(query or "").lower().strip()
    if not query_text or query_text == "none":
        return "none"

    response = ""
    try:
        if "open youtube" in query_text or query_text == "youtube":
            webbrowser.open("https://www.youtube.com")
            response = "Opening YouTube."

        elif "open google" in query_text or query_text == "google":
            webbrowser.open("https://www.google.com")
            response = "Opening Google."

        elif "open maps" in query_text or "maps" in query_text:
            webbrowser.open("https://www.google.com/maps")
            response = "Opening Maps."

        elif "what time is it" in query_text or query_text == "time" or query_text.startswith("time"):
            response = f"The time is {datetime.now().strftime('%I:%M %p')}"

        elif "connect spotify" in query_text or "spotify connect" in query_text:
            from Engine.spotify_backend import connect_spotify

            spotify_result = connect_spotify()
            response = spotify_result.get("message", "Spotify connection attempted.")

        elif "play music" in query_text or query_text == "music":
            response = _play_spotify_or_local()

        elif query_text.startswith("play "):
            response = _play_spotify_or_local(query_text.removeprefix("play ").strip())

        elif "pause music" in query_text or query_text == "pause music":
            spotify_result = spotify_pause_music()
            response = spotify_result.get("message", "Music paused.")

        elif "next song" in query_text or "next track" in query_text:
            spotify_result = spotify_next_track()
            response = spotify_result.get("message", "Skipped to next track.")

        elif "previous song" in query_text or "previous track" in query_text:
            spotify_result = spotify_previous_track()
            response = spotify_result.get("message", "Went to previous track.")

        elif "navigation" in query_text:
            response = _navigation_simulation()

        elif "adb devices" in query_text or "device status" in query_text:
            response = list_android_devices()

        elif "weather" in query_text:
            response = "Weather service unavailable."
            try:
                weather = requests.get("https://wttr.in/?format=j1", timeout=10)
                weather.raise_for_status()
                payload = weather.json()
                current = payload["current_condition"][0]
                temp_c = current.get("temp_C", "unknown")
                description = current.get("weatherDesc", [{}])[0].get("value", "clear")
                response = f"It is {temp_c} degree Celsius with {description}."
            except Exception:
                pass

        elif "tell me a joke" in query_text or "joke" in query_text:
            jokes = [
                "Why did the computer keep sneezing? It had a virus.",
                "Why do programmers prefer dark mode? Because light attracts bugs.",
                "I told my router a joke. It responded with a weak signal.",
            ]
            response = random.choice(jokes)

        elif "open camera" in query_text or query_text == "camera":
            response = _open_camera()

        elif "send message" in query_text or query_text.startswith("sms"):
            number, message = _parse_sms_command(query_text)
            response = send_sms(number, message)

        elif any(query_text.startswith(prefix) for prefix in ("open android app", "open app", "launch app", "launch ", "start app")):
            package = _extract_android_target(query_text)
            if not package:
                package = db.get_setting("android_default_package", "") or ""
            response = open_android_app(package)

        elif any(phrase in query_text for phrase in ("play media", "resume media", "media play", "play phone")):
            response = control_android_media("play_pause")

        elif any(phrase in query_text for phrase in ("pause media", "pause phone", "stop media")):
            response = control_android_media("pause")

        elif any(phrase in query_text for phrase in ("next track", "skip track", "media next")):
            response = control_android_media("next")

        elif any(phrase in query_text for phrase in ("previous track", "media previous", "back track")):
            response = control_android_media("previous")

        elif any(phrase in query_text for phrase in ("volume up", "increase volume", "louder")):
            response = control_android_media("volume_up")

        elif any(phrase in query_text for phrase in ("volume down", "decrease volume", "lower volume")):
            response = control_android_media("volume_down")

        elif "mute" in query_text:
            response = control_android_media("mute")

        elif "shutdown system" in query_text:
            response = "Shutting down the system."
            speak(response)
            db.log_conversation(query_text, response, source=source)
            os.system("shutdown /s /t 0")
            return response

        elif "call" in query_text:
            response = "Calling via ADB is not yet configured."

        else:
            response = generate_response(query_text)

        if response:
            speak(response)
        db.log_conversation(query_text, response, source=source)
        return response
    except Exception as exc:
        error_message = f"I could not complete that command. {exc}"
        speak(error_message)
        db.log_conversation(query_text, error_message, source=source)
        return error_message
