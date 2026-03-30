from __future__ import annotations

import os
import random
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

import cv2  # pyright: ignore[reportMissingImports]
import eel
import requests

from Engine import db
from Engine.Features import open_android_app, send_sms, speak, takecommand as feature_takecommand
from Engine.ai_memory import generate_response


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
        cv2.imshow("Jarvis Camera", frame)
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

        elif "play music" in query_text or query_text == "music":
            response = _play_first_music_track()

        elif "navigation" in query_text:
            response = _navigation_simulation()

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

        elif "send message" in query_text or "sms" in query_text:
            response = send_sms("", "")

        elif "open android app" in query_text or query_text.startswith("open app "):
            package = query_text.replace("open android app", "").replace("open app", "").strip()
            response = open_android_app(package)

        elif "shutdown system" in query_text:
            response = "Shutting down the system."
            speak(response)
            db.log_conversation(query_text, response, source=source)
            os.system("shutdown /s /t 0")
            return response

        elif "call" in query_text:
            response = "Calling via ADB is not yet configured."

        elif "volume up" in query_text:
            response = "Volume up is not yet configured."

        elif "volume down" in query_text:
            response = "Volume down is not yet configured."

        elif "mute" in query_text:
            response = "Mute is not yet configured."

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
