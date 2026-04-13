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
    BASE_DIR / "start_sound.mp3",
    BASE_DIR / "www" / "assets" / "jarvis_start.wav",
    BASE_DIR / "www" / "assets" / "jarvis_start.mp3",
    BASE_DIR / "www" / "assets" / "Audio" / "start_sound.mp3",
    BASE_DIR / "www" / "assets" / "Audio" / "jarvis_start.mp3",
]

_tts_queue: "queue.Queue[str | None]" = queue.Queue()
_sound_queue: "queue.Queue[str | None]" = queue.Queue()
_audio_started = False
_audio_lock = threading.Lock()
ANDROID_APP_ALIASES = {
    "youtube": "com.google.android.youtube",
    "google maps": "com.google.android.apps.maps",
    "maps": "com.google.android.apps.maps",
    "spotify": "com.spotify.music",
    "phone": "com.google.android.dialer",
    "messages": "com.google.android.apps.messaging",
    "whatsapp": "com.whatsapp",
    "camera": "com.android.camera",
    "chrome": "com.android.chrome",
    "gallery": "com.google.android.apps.photos",
}
MEDIA_KEYCODES = {
    "play": 126,
    "pause": 127,
    "play_pause": 85,
    "next": 87,
    "previous": 88,
    "stop": 86,
    "volume_up": 24,
    "volume_down": 25,
    "mute": 164,
}


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
    try:
        engine.setProperty("rate", int(db.get_setting("speech_rate", "180") or 180))
    except Exception:
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
                # winsound cannot reliably play MP3; restricting to WAV avoids system alert tones.
                if path.suffix.lower() == ".wav":
                    import winsound

                    winsound.PlaySound(str(path), winsound.SND_FILENAME)
        except Exception:
            # Do not emit system error beeps on audio playback failure.
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
def takecommand(timeout: int = 6, phrase_time_limit: int = 12, continuous: bool = False):
    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 1.3
    recognizer.non_speaking_duration = 0.7

    def _listen_once():
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.7)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        try:
            query = recognizer.recognize_google(audio)
            return query.lower().strip()
        except sr.RequestError:
            try:
                query = recognizer.recognize_sphinx(audio)
                return query.lower().strip()
            except Exception:
                return "none"
        except sr.UnknownValueError:
            try:
                query = recognizer.recognize_sphinx(audio)
                return query.lower().strip()
            except Exception:
                return "none"

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


def query_android_contacts(contact_name: str) -> list[dict[str, str]]:
    name = str(contact_name or "").strip().lower()
    if not name:
        return []

    try:
        result = _run_adb([
            "shell",
            "content",
            "query",
            "--uri",
            "content://com.android.contacts/data/phones",
            "--projection",
            "display_name:number",
        ])
    except Exception:
        return []

    if result.returncode != 0:
        return []

    contacts: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw_line in (result.stdout or "").splitlines():
        line = raw_line.strip()
        if line.startswith("Row:"):
            if current:
                contacts.append(current)
            current = {}
            continue
        if "display_name=" in line:
            current["name"] = line.split("display_name=", 1)[1].strip()
        elif "number=" in line:
            current["number"] = line.split("number=", 1)[1].strip()

    if current:
        contacts.append(current)

    matches: list[dict[str, str]] = []
    for contact in contacts:
        contact_name_value = str(contact.get("name") or "").lower()
        if name == contact_name_value or name in contact_name_value:
            matches.append(contact)
    return matches


def call_android_contact(contact_name: str):
    matches = query_android_contacts(contact_name)
    if not matches:
        return f"No exact contact match found for {contact_name}."

    target = matches[0]
    number = str(target.get("number") or "").strip()
    if not number:
        return f"Contact {target.get('name', contact_name)} has no phone number."

    sanitized = "".join(ch for ch in number if ch.isdigit() or ch == "+")
    if not sanitized:
        return f"Contact {target.get('name', contact_name)} has an invalid number."

    result = _run_adb(["shell", "am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{sanitized}"])
    if result.returncode == 0:
        return f"Calling {target.get('name', contact_name)}."

    fallback = _run_adb(["shell", "am", "start", "-a", "android.intent.action.DIAL", "-d", f"tel:{sanitized}"])
    if fallback.returncode == 0:
        return f"Dialer opened for {target.get('name', contact_name)}."

    return f"Unable to call {target.get('name', contact_name)}."


def call_android_number(phone_number: str):
    number = str(phone_number or "").strip()
    if not number:
        return "Please provide a valid phone number."

    sanitized = "".join(ch for ch in number if ch.isdigit() or ch == "+")
    if not sanitized:
        return "Phone number must contain digits."

    result = _run_adb(["shell", "am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{sanitized}"])
    if result.returncode == 0:
        return f"Calling {sanitized}."

    fallback = _run_adb(["shell", "am", "start", "-a", "android.intent.action.DIAL", "-d", f"tel:{sanitized}"])
    if fallback.returncode == 0:
        return f"Dialer opened with {sanitized}."

    return f"Unable to call {sanitized}."


def playAssistantSound():
    primary = BASE_DIR / "start_sound.mp3"
    if primary.exists():
        play_sound(primary)
        return

    for sound_path in DEFAULT_SOUND_PATHS:
        if sound_path.exists():
            play_sound(sound_path)
            return


def hotword(wake_queue=None):
    from Engine.hotword import hotword as hotword_process

    hotword_process(wake_queue)


def _adb_base_command() -> list[str]:
    command = ["adb"]
    device_serial = db.get_setting("android_device_serial", "")
    if device_serial:
        command.extend(["-s", device_serial.strip()])
    return command


def _run_adb(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(_adb_base_command() + arguments, capture_output=True, text=True, check=False)


def _resolve_android_package(package_name: str) -> str:
    resolved_name = str(package_name or "").strip()
    if not resolved_name:
        return ""

    alias = ANDROID_APP_ALIASES.get(resolved_name.lower())
    if alias:
        return alias
    return resolved_name


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


def list_android_devices():
    try:
        result = _run_adb(["devices"])
        if result.returncode != 0:
            return result.stderr.strip() or "Unable to list Android devices."
        return result.stdout.strip() or "No Android devices detected."
    except Exception as exc:
        return f"Unable to list Android devices. {exc}"


def open_android_app(package_name: str):
    package_name = _resolve_android_package(package_name)
    if not package_name:
        return "No Android package name was provided."

    commands = []
    if "/" in package_name:
        commands.append(["shell", "am", "start", "-n", package_name])

    commands.extend(
        [
            ["shell", "monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1"],
            ["shell", "cmd", "package", "resolve-activity", "--brief", package_name],
        ]
    )
    for command in commands:
        try:
            result = _run_adb(command)
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

    command = _adb_base_command() + [
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


def control_android_media(action: str):
    action_name = str(action or "").strip().lower().replace(" ", "_")
    keycode = MEDIA_KEYCODES.get(action_name)
    if keycode is None:
        return f"Unsupported media action: {action}."

    try:
        result = _run_adb(["shell", "input", "keyevent", str(keycode)])
        if result.returncode == 0:
            return f"Android media action {action_name} sent."
        error_text = result.stderr.strip() or result.stdout.strip()
        if error_text:
            return error_text
    except Exception as exc:
        return f"Android media control failed. {exc}"

    return "Android media control is unavailable on this device."


def open_android_app_by_name(app_name: str):
    return open_android_app(app_name)


def open_url(url: str):
    webbrowser.open(url)


def launch_camera_app():
    try:
        os.system('start microsoft.windows.camera:')
        return "Opening camera."
    except Exception:
        return "Camera launch failed."
