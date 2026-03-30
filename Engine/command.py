import os
import random
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

import cv2  # pyright: ignore[reportMissingImports]
import eel
import requests

from Engine.Features import openai_query, log_conversation, speak, takecommand as feature_takecommand


@eel.expose
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


@eel.expose
def allCommands(query):
    query_text = str(query or "").lower().strip()
    if not query_text or query_text == "none":
        return "none"

    response = ""

    try:
        if "open youtube" in query_text or query_text == "youtube":
            webbrowser.open("https://www.youtube.com")
            response = "Opening YouTube."

        elif "what time is it" in query_text or query_text == "time" or "time" in query_text:
            response = f"The time is {datetime.now().strftime('%I:%M %p')}"

        elif "play music" in query_text or "music" in query_text:
            response = _play_first_music_track()

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

        elif "open camera" in query_text or "camera" in query_text:
            response = _open_camera()

        elif "send message" in query_text or "sms" in query_text:
            response = "Message sending is a placeholder for ADB integration."

        elif "open maps" in query_text or "maps" in query_text:
            webbrowser.open("https://www.google.com/maps")
            response = "Opening Maps."

        elif "call" in query_text:
            response = "Calling via ADB is not yet configured."

        elif "open settings" in query_text or "settings" in query_text:
            response = "Settings panel is not implemented yet."

        else:
            response = openai_query(query_text)
            if not response:
                response = "I am ready."

        speak(response)
        log_conversation(query_text, response)
        return response
    except Exception as exc:
        error_message = f"I could not complete that command. {exc}"
        speak(error_message)
        log_conversation(query_text, error_message)
        return error_message
