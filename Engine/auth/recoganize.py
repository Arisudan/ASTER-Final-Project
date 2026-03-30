import os
import pickle
import time
from pathlib import Path

import cv2  # pyright: ignore[reportMissingImports]

try:
    import face_recognition  # pyright: ignore[reportMissingImports]
except Exception:
    face_recognition = None

try:
    from deepface import DeepFace  # pyright: ignore[reportMissingImports]
except Exception:
    DeepFace = None

import sqlite3

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / "jarvis.db"
SAMPLES_DIR = Path(__file__).resolve().parent / "samples"
KNOWN_IMAGE_DIRS = [SAMPLES_DIR, Path(__file__).resolve().parent / "known_faces"]


def _load_db_profiles():
    profiles = []
    if not DB_PATH.exists():
        return profiles

    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT name, encoding FROM face_profiles ORDER BY id ASC")
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            return profiles

    for name, encoding_blob in rows:
        try:
            encodings = pickle.loads(encoding_blob)
            if isinstance(encodings, list):
                for item in encodings:
                    profiles.append((name, item))
            else:
                profiles.append((name, encodings))
        except Exception:
            continue

    return profiles


def _load_image_profiles():
    profiles = []
    if face_recognition is None:
        return profiles

    for folder in KNOWN_IMAGE_DIRS:
        if not folder.exists():
            continue
        for image_path in folder.glob("*.*"):
            if image_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp"}:
                continue
            try:
                image = face_recognition.load_image_file(str(image_path))
                encodings = face_recognition.face_encodings(image)
                if encodings:
                    profiles.append((image_path.stem, encodings[0]))
            except Exception:
                continue
    return profiles


def _draw_label(frame, left, top, right, bottom, label):
    cv2.rectangle(frame, (left, top), (right, bottom), (0, 212, 255), 2)
    cv2.rectangle(frame, (left, bottom - 35), (right, bottom), (0, 212, 255), cv2.FILLED)
    cv2.putText(frame, label, (left + 6, bottom - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (10, 14, 26), 2)


def AuthenticateFace():
    if face_recognition is None and DeepFace is None:
        print("Face authentication libraries are not installed.")
        return 0

    known_profiles = _load_db_profiles()
    if not known_profiles:
        known_profiles = _load_image_profiles()

    if not known_profiles:
        print("No enrolled face profile was found.")

    known_names = [item[0] for item in known_profiles]
    known_encodings = [item[1] for item in known_profiles]

    capture = cv2.VideoCapture(0)
    if not capture.isOpened():
        print("Unable to open camera.")
        return 0

    start_time = time.time()
    timeout_seconds = 30

    try:
        while True:
            success, frame = capture.read()
            if not success:
                continue

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_locations = []
            face_encodings = []
            face_names = []

            if face_recognition is not None:
                face_locations = face_recognition.face_locations(rgb_frame)
                face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

                for face_encoding, face_location in zip(face_encodings, face_locations):
                    matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.45)
                    name = "Unknown"

                    if True in matches:
                        distances = face_recognition.face_distance(known_encodings, face_encoding)
                        best_match_index = distances.argmin()
                        if matches[best_match_index]:
                            name = known_names[best_match_index]

                    face_names.append(name)

                    top, right, bottom, left = face_location[0], face_location[1], face_location[2], face_location[3]
                    _draw_label(frame, left, top, right, bottom, name)

                    if name != "Unknown":
                        capture.release()
                        cv2.destroyAllWindows()
                        return 1
            else:
                if DeepFace is not None and known_encodings:
                    pass

            cv2.putText(frame, "Jarvis Face Scan Active", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 212, 255), 2)
            cv2.putText(frame, "Press Q to quit", (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (123, 47, 255), 2)
            cv2.imshow("Jarvis Face Authentication", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

            if time.time() - start_time > timeout_seconds:
                break
    except Exception as exc:
        print(f"Face authentication failed: {exc}")
    finally:
        capture.release()
        cv2.destroyAllWindows()

    return 0
