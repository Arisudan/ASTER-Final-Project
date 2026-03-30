from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

import cv2

try:
    import numpy as np
except Exception:
    np = None

from Engine import db


@dataclass
class DriverMonitorConfig:
    closed_eye_alert_seconds: float = 3.0
    camera_index: int = 0


def _load_cascade(name: str):
    path = cv2.data.haarcascades + name
    cascade = cv2.CascadeClassifier(path)
    return cascade if not cascade.empty() else None


def _fallback_eye_monitor(alert_callback: Callable[[str], None], config: DriverMonitorConfig) -> None:
    face_cascade = _load_cascade("haarcascade_frontalface_default.xml")
    eye_cascade = _load_cascade("haarcascade_eye_tree_eyeglasses.xml") or _load_cascade("haarcascade_eye.xml")
    if face_cascade is None or eye_cascade is None:
        db.log_event("warning", "Driver monitor cascades unavailable", source="driver-monitor")
        return

    capture = cv2.VideoCapture(config.camera_index)
    if not capture.isOpened():
        db.log_event("warning", "Driver monitor camera unavailable", source="driver-monitor")
        return

    eyes_closed_since = None
    try:
        while True:
            success, frame = capture.read()
            if not success:
                time.sleep(0.1)
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(120, 120))
            eyes_open = False

            for (x, y, w, h) in faces[:1]:
                roi = gray[y : y + h, x : x + w]
                eyes = eye_cascade.detectMultiScale(roi, 1.1, 8, minSize=(20, 20))
                eyes_open = len(eyes) > 0
                color = (0, 212, 255) if eyes_open else (0, 0, 255)
                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                for (ex, ey, ew, eh) in eyes[:2]:
                    cv2.rectangle(frame, (x + ex, y + ey), (x + ex + ew, y + ey + eh), (0, 255, 0), 2)

            if eyes_open:
                eyes_closed_since = None
            else:
                if eyes_closed_since is None:
                    eyes_closed_since = time.time()
                elif time.time() - eyes_closed_since > config.closed_eye_alert_seconds:
                    alert_callback("Drowsiness detected. Please stay alert.")
                    db.log_event("warning", "Driver drowsiness detected", source="driver-monitor")
                    eyes_closed_since = time.time()

            cv2.imshow("Driver Monitor", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        capture.release()
        cv2.destroyAllWindows()


def start_driver_monitor(alert_callback: Callable[[str], None], config: Optional[DriverMonitorConfig] = None) -> None:
    config = config or DriverMonitorConfig()
    try:
        _fallback_eye_monitor(alert_callback, config)
    except Exception as exc:
        db.log_event("error", f"Driver monitor failed: {exc}", source="driver-monitor")
