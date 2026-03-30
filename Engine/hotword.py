from __future__ import annotations

import os
import struct
import time
from typing import Optional

import speech_recognition as sr

try:
    import pvporcupine  # pyright: ignore[reportMissingImports]
except Exception:
    pvporcupine = None

try:
    import pyaudio  # pyright: ignore[reportMissingImports]
except Exception:
    pyaudio = None

from Engine import db


def _fallback_hotword_loop(wake_queue):
    recognizer = sr.Recognizer()
    db.log_event("info", "Hotword fallback loop started", source="hotword")
    while True:
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.2)
                audio = recognizer.listen(source, timeout=1, phrase_time_limit=3)
            phrase = recognizer.recognize_google(audio).lower().strip()
            if "jarvis" in phrase:
                wake_queue.put({"type": "wake", "source": "fallback"})
        except sr.WaitTimeoutError:
            continue
        except sr.UnknownValueError:
            continue
        except sr.RequestError:
            time.sleep(1)
        except Exception:
            time.sleep(1)


def _porcupine_hotword_loop(wake_queue):
    access_key = os.getenv("PORCUPINE_ACCESS_KEY")
    keyword_paths = [path.strip() for path in os.getenv("PORCUPINE_KEYWORD_PATHS", "").split(os.pathsep) if path.strip()]

    if not access_key:
        return _fallback_hotword_loop(wake_queue)

    if not keyword_paths:
        keyword_paths = []

    try:
        porcupine = pvporcupine.create(access_key=access_key, keywords=["jarvis"] if not keyword_paths else None, keyword_paths=keyword_paths or None)
    except Exception:
        return _fallback_hotword_loop(wake_queue)

    if pyaudio is None:
        porcupine.delete()
        return _fallback_hotword_loop(wake_queue)

    pa = pyaudio.PyAudio()
    stream = pa.open(
        rate=porcupine.sample_rate,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=porcupine.frame_length,
    )

    db.log_event("info", "Porcupine hotword loop started", source="hotword")
    try:
        while True:
            pcm = stream.read(porcupine.frame_length, exception_on_overflow=False)
            audio_buffer = struct.unpack_from("h" * porcupine.frame_length, pcm)
            keyword_index = porcupine.process(audio_buffer)
            if keyword_index >= 0:
                wake_queue.put({"type": "wake", "source": "porcupine"})
    finally:
        try:
            stream.close()
            pa.terminate()
        finally:
            porcupine.delete()


def hotword(wake_queue):
    db.log_event("info", "Hotword process starting", source="hotword")
    try:
        _porcupine_hotword_loop(wake_queue)
    except Exception as exc:
        db.log_event("error", f"Hotword loop failed: {exc}", source="hotword")
        _fallback_hotword_loop(wake_queue)
