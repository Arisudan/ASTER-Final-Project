import os
import pickle
import json
import re
import time
from pathlib import Path

import cv2  # pyright: ignore[reportMissingImports]
import numpy as np
import eel

try:
    import face_recognition  # pyright: ignore[reportMissingImports]
except Exception:
    face_recognition = None

try:
    from deepface import DeepFace  # pyright: ignore[reportMissingImports]
except Exception:
    DeepFace = None

from Engine import db

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / "jarvis.db"
SAMPLES_DIR = Path(__file__).resolve().parent / "samples"
KNOWN_IMAGE_DIRS = [SAMPLES_DIR, Path(__file__).resolve().parent / "known_faces"]
CASCADE_PATH = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
LEGACY_SAMPLES_DIR = SAMPLES_DIR
LEGACY_TRAINER_DIR = Path(__file__).resolve().parent / "trainer"
LEGACY_TRAINER_PATH = LEGACY_TRAINER_DIR / "trainer.yml"
LEGACY_LABELS_PATH = LEGACY_TRAINER_DIR / "labels.json"
LEGACY_FACE_AUTH_ENV = "ENABLE_LEGACY_FACE_PIPELINE"


def _camera_backends():
    backends = []
    for backend_name in ("CAP_DSHOW", "CAP_MSMF"):
        backend = getattr(cv2, backend_name, None)
        if backend is not None:
            backends.append(backend)
    backends.append(None)
    return backends


def _open_camera(indices=(0, 1), width=1280, height=720):
    """Try multiple camera backends/indexes to improve startup reliability on Windows."""
    for index in indices:
        for backend in _camera_backends():
            capture = cv2.VideoCapture(index, backend) if backend is not None else cv2.VideoCapture(index)
            if capture is not None and capture.isOpened():
                try:
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                    capture.set(cv2.CAP_PROP_FPS, 30)
                except Exception:
                    pass
                return capture
            if capture is not None:
                capture.release()
    return None


def _load_db_profiles():
    profiles = []
    for name, encoding_blob in db.fetch_face_profiles():
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


def _legacy_face_recognizer_available() -> bool:
    return bool(getattr(cv2, "face", None) and hasattr(cv2.face, "LBPHFaceRecognizer_create"))


def _legacy_cascade_path() -> Path:
    return Path(__file__).resolve().parent / "haarcascade_frontalface_default.xml"


def _load_legacy_cascade():
    cascade = cv2.CascadeClassifier(str(_legacy_cascade_path()))
    if cascade.empty():
        cascade = cv2.CascadeClassifier(str(CASCADE_PATH))
    return cascade if not cascade.empty() else None


def _legacy_label_map() -> dict[str, str]:
    if not LEGACY_LABELS_PATH.exists():
        return {}

    try:
        payload = json.loads(LEGACY_LABELS_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return {str(key): str(value) for key, value in payload.items()}
    except Exception:
        pass

    return {}


def _save_legacy_label_map(label_map: dict[str, str]) -> None:
    LEGACY_TRAINER_DIR.mkdir(parents=True, exist_ok=True)
    LEGACY_LABELS_PATH.write_text(json.dumps(label_map, indent=2, sort_keys=True), encoding="utf-8")


def _ensure_legacy_label(profile_name: str) -> int:
    label_map = _legacy_label_map()
    for label, name in label_map.items():
        if name == profile_name:
            return int(label)

    next_label = max((int(label) for label in label_map.keys() if str(label).isdigit()), default=0) + 1
    label_map[str(next_label)] = profile_name
    _save_legacy_label_map(label_map)
    return next_label


def _legacy_name_for_label(label_id: int) -> str:
    return _legacy_label_map().get(str(label_id), str(label_id))


def _legacy_samples_enabled() -> bool:
    return str(os.getenv(LEGACY_FACE_AUTH_ENV, "0")).strip().lower() in {"1", "true", "yes", "on"}


def _legacy_capture_samples(profile_name: str, sample_count: int = 25, timeout_seconds: int = 45) -> int:
    if not _legacy_face_recognizer_available():
        return 0

    detector = _load_legacy_cascade()
    if detector is None:
        return 0

    capture = _open_camera()
    if capture is None or not capture.isOpened():
        return 0

    LEGACY_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    label_id = _ensure_legacy_label(profile_name)
    count = 0
    start_time = time.time()

    try:
        while True:
            success, frame = capture.read()
            if not success:
                continue

            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            min_width = max(80, int(0.1 * capture.get(3)))
            min_height = max(80, int(0.1 * capture.get(4)))
            faces = detector.detectMultiScale(gray_frame, scaleFactor=1.3, minNeighbors=5, minSize=(min_width, min_height))

            for (x, y, width, height) in faces:
                count += 1
                sample_path = LEGACY_SAMPLES_DIR / f"face.{label_id}.{count}.jpg"
                cv2.imwrite(str(sample_path), gray_frame[y : y + height, x : x + width])
                cv2.rectangle(frame, (x, y), (x + width, y + height), (0, 212, 255), 2)
                cv2.putText(frame, f"Capturing {profile_name} ({count}/{sample_count})", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 212, 255), 2)
                if count >= sample_count:
                    cv2.imshow("ASTER Face Enrollment", frame)
                    cv2.waitKey(300)
                    return count

            cv2.putText(frame, f"Capturing {profile_name} ({count}/{sample_count})", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 212, 255), 2)
            cv2.putText(frame, "Press Q to cancel", (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (123, 47, 255), 2)
            cv2.imshow("ASTER Face Enrollment", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

            if time.time() - start_time > timeout_seconds:
                break
    finally:
        capture.release()
        cv2.destroyAllWindows()

    return count


def _legacy_train_model() -> bool:
    if not _legacy_face_recognizer_available():
        return False

    detector = _load_legacy_cascade()
    if detector is None:
        return False

    image_paths = sorted(LEGACY_SAMPLES_DIR.glob("face.*.jpg"))
    face_samples = []
    ids = []

    for image_path in image_paths:
        parts = image_path.stem.split(".")
        if len(parts) < 3 or not parts[1].isdigit():
            continue

        label_id = int(parts[1])
        image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            continue

        faces = detector.detectMultiScale(image, scaleFactor=1.3, minNeighbors=5)
        if not len(faces):
            face_samples.append(image)
            ids.append(label_id)
            continue

        for (x, y, width, height) in faces:
            face_samples.append(image[y : y + height, x : x + width])
            ids.append(label_id)

    if not face_samples:
        return False

    LEGACY_TRAINER_DIR.mkdir(parents=True, exist_ok=True)
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.train(face_samples, np.array(ids))
    recognizer.write(str(LEGACY_TRAINER_PATH))
    return True


def _legacy_authenticate(timeout_seconds: int = 30):
    if not _legacy_face_recognizer_available() or not LEGACY_TRAINER_PATH.exists():
        return 0

    detector = _load_legacy_cascade()
    if detector is None:
        return 0

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(str(LEGACY_TRAINER_PATH))

    capture = _open_camera()
    if capture is None or not capture.isOpened():
        return 0

    start_time = time.time()

    try:
        while True:
            success, frame = capture.read()
            if not success:
                continue

            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            min_width = max(80, int(0.1 * capture.get(3)))
            min_height = max(80, int(0.1 * capture.get(4)))
            faces = detector.detectMultiScale(gray_frame, scaleFactor=1.2, minNeighbors=5, minSize=(min_width, min_height))

            for (x, y, width, height) in faces:
                label_id, accuracy = recognizer.predict(gray_frame[y : y + height, x : x + width])
                name = _legacy_name_for_label(label_id)
                _draw_label(frame, x, y, x + width, y + height, name)

                if accuracy < 100 and name != "unknown":
                    capture.release()
                    cv2.destroyAllWindows()
                    return name

            cv2.putText(frame, "ASTER Face Scan Active", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 212, 255), 2)
            cv2.putText(frame, "Press Q to quit", (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (123, 47, 255), 2)
            cv2.imshow("ASTER Face Authentication", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

            if time.time() - start_time > timeout_seconds:
                break
    finally:
        capture.release()
        cv2.destroyAllWindows()

    return 0


def _load_haar_cascade():
    cascade = cv2.CascadeClassifier(str(CASCADE_PATH))
    return cascade if not cascade.empty() else None


def _extract_face_region(frame, cascade=None):
    if cascade is None:
        cascade = _load_haar_cascade()

    if cascade is None:
        return None, None

    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(gray_frame, scaleFactor=1.2, minNeighbors=5, minSize=(80, 80))
    if len(faces) == 0:
        return None, None

    x, y, width, height = faces[0]
    face_region = gray_frame[y : y + height, x : x + width]
    return (x, y, width, height), face_region


def _fallback_face_vector(face_region):
    if face_region is None:
        return None
    normalized = cv2.resize(face_region, (64, 64), interpolation=cv2.INTER_AREA)
    return normalized.flatten().astype(np.float32)


def _compare_fallback_vectors(candidate, known_profiles):
    if candidate is None or not known_profiles:
        return None

    best_name = None
    best_score = None

    for name, encoding in known_profiles:
        try:
            known_vector = np.asarray(encoding, dtype=np.float32).flatten()
            if known_vector.size != candidate.size:
                continue
            score = float(np.mean(np.abs(known_vector - candidate)))
            if best_score is None or score < best_score:
                best_score = score
                best_name = name
        except Exception:
            continue

    if best_name is not None and best_score is not None and best_score <= 28.0:
        return best_name
    return None


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


def _capture_face_encoding(window_title, instruction_text, timeout_seconds=45):
    if face_recognition is None:
        cascade = _load_haar_cascade()
        if cascade is None:
            return None

        capture = _open_camera()
        if capture is None or not capture.isOpened():
            return None

        start_time = time.time()

        try:
            while True:
                success, frame = capture.read()
                if not success:
                    continue

                face_box, face_region = _extract_face_region(frame, cascade)
                if face_box is not None and face_region is not None:
                    x, y, width, height = face_box
                    _draw_label(frame, x, y, x + width, y + height, "Capture")
                    cv2.putText(frame, instruction_text, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 212, 255), 2)
                    cv2.imshow(window_title, frame)
                    cv2.waitKey(500)
                    return _fallback_face_vector(face_region)

                cv2.putText(frame, instruction_text, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 212, 255), 2)
                cv2.putText(frame, "Press Q to cancel", (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (123, 47, 255), 2)
                cv2.imshow(window_title, frame)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

                if time.time() - start_time > timeout_seconds:
                    break
        finally:
            capture.release()
            cv2.destroyAllWindows()

        return None

    capture = _open_camera()
    if capture is None or not capture.isOpened():
        return None

    start_time = time.time()

    try:
        while True:
            success, frame = capture.read()
            if not success:
                continue

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_frame)
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

            for face_location, face_encoding in zip(face_locations, face_encodings):
                top, right, bottom, left = face_location[0], face_location[1], face_location[2], face_location[3]
                _draw_label(frame, left, top, right, bottom, "Capture")
                cv2.putText(frame, instruction_text, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 212, 255), 2)
                cv2.imshow(window_title, frame)
                cv2.waitKey(500)
                return face_encoding

            cv2.putText(frame, instruction_text, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 212, 255), 2)
            cv2.putText(frame, "Press Q to cancel", (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (123, 47, 255), 2)
            cv2.imshow(window_title, frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

            if time.time() - start_time > timeout_seconds:
                break
    finally:
        capture.release()
        cv2.destroyAllWindows()

    return None


def _capture_multiple_encodings(window_title, instruction_text, sample_count=3, timeout_seconds=60):
    captured_samples = []
    deadline = time.time() + timeout_seconds

    while len(captured_samples) < sample_count and time.time() < deadline:
        encoding = _capture_face_encoding(window_title, f"{instruction_text} ({len(captured_samples) + 1}/{sample_count})", 20)
        if encoding is None:
            continue
        captured_samples.append(encoding)

    if not captured_samples:
        return None

    return captured_samples


def EnrollFace(name):
    profile_name = str(name or "").strip()
    if not profile_name:
        return 0

    encodings = _capture_multiple_encodings(
        "ASTER Face Enrollment",
        f"Enroll {profile_name}: look at the camera",
        sample_count=3,
        timeout_seconds=90,
    )
    if not encodings:
        return 0

    try:
        db.save_face_profile(profile_name, pickle.dumps(encodings))

        if face_recognition is None or _legacy_samples_enabled():
            legacy_samples = _legacy_capture_samples(profile_name)
            if legacy_samples:
                _legacy_train_model()

        return 1
    except Exception as exc:
        print(f"Failed to save face profile: {exc}")
        return 0


@eel.expose
def enrollFace(name):
    return EnrollFace(name)


def AuthenticateFace():
    known_profiles = _load_db_profiles()
    if not known_profiles:
        known_profiles = _load_image_profiles()

    if not known_profiles:
        legacy_result = _legacy_authenticate()
        if legacy_result not in (0, None, "", False):
            return legacy_result

        print("No enrolled face profile was found.")
        try:
            eel.showEnrollment()
        except Exception:
            pass
        return 0

    known_names = [item[0] for item in known_profiles]
    known_encodings = [item[1] for item in known_profiles]

    capture = _open_camera()
    if capture is None or not capture.isOpened():
        print("Unable to open camera.")
        try:
            eel.updateAuthStatus("Camera not available. Check permissions or close other camera apps.")
        except Exception:
            pass
        return 0

    start_time = time.time()
    timeout_seconds = 30

    try:
        while True:
            success, frame = capture.read()
            if not success:
                continue

            if face_recognition is not None:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
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

                    top, right, bottom, left = face_location[0], face_location[1], face_location[2], face_location[3]
                    _draw_label(frame, left, top, right, bottom, name)

                    if name != "Unknown":
                        capture.release()
                        cv2.destroyAllWindows()
                        return name
            else:
                cascade = _load_haar_cascade()
                face_box, face_region = _extract_face_region(frame, cascade)
                if face_box is not None and face_region is not None:
                    candidate_vector = _fallback_face_vector(face_region)
                    if candidate_vector is not None:
                        name = _compare_fallback_vectors(candidate_vector, known_profiles) or "Unknown"
                        x, y, width, height = face_box
                        _draw_label(frame, x, y, x + width, y + height, name)
                        if name != "Unknown":
                            capture.release()
                            cv2.destroyAllWindows()
                            return name

            cv2.putText(frame, "ASTER Face Scan Active", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 212, 255), 2)
            cv2.putText(frame, "Press Q to quit", (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (123, 47, 255), 2)
            cv2.imshow("ASTER Face Authentication", frame)

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
