from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

import cv2

try:
    from ultralytics import YOLO  # pyright: ignore[reportMissingImports]
except Exception:
    YOLO = None

from Engine import db


@dataclass
class DriverMonitorConfig:
    model_name: str = "yolov8n-pose.pt"
    confidence_threshold: float = 0.35
    frame_stride: int = 3
    drowsiness_alert_seconds: float = 3.0
    camera_index: int = 0


_MODEL_CACHE: dict[str, object] = {}


def _load_yolo_model(model_name: str):
    if YOLO is None:
        raise RuntimeError("ultralytics is not installed")

    normalized_name = str(model_name or "yolov8n.pt").strip() or "yolov8n.pt"
    if normalized_name not in _MODEL_CACHE:
        _MODEL_CACHE[normalized_name] = YOLO(normalized_name)
    return _MODEL_CACHE[normalized_name]


def _class_name(model, class_index: int) -> str:
    names = getattr(model, "names", {}) or {}
    if isinstance(names, dict):
        return str(names.get(class_index, class_index))
    if isinstance(names, (list, tuple)) and 0 <= class_index < len(names):
        return str(names[class_index])
    return str(class_index)


def _point_from_keypoints(keypoints, index: int):
    if keypoints is None:
        return None

    try:
        point = keypoints[index]
    except Exception:
        return None

    try:
        x, y = float(point[0]), float(point[1])
        confidence = float(point[2]) if len(point) > 2 else 1.0
    except Exception:
        return None

    return x, y, confidence


def _distance(first_point, second_point) -> float:
    return float(((first_point[0] - second_point[0]) ** 2 + (first_point[1] - second_point[1]) ** 2) ** 0.5)


def _angle_degrees(first_point, second_point) -> float:
    dx = second_point[0] - first_point[0]
    dy = second_point[1] - first_point[1]
    if dx == 0 and dy == 0:
        return 0.0
    import math

    return abs(math.degrees(math.atan2(dy, dx)))


def _midpoint(first_point, second_point):
    return ((first_point[0] + second_point[0]) / 2.0, (first_point[1] + second_point[1]) / 2.0)


def _extract_pose_metrics(box, keypoints):
    if keypoints is None:
        return None

    nose = _point_from_keypoints(keypoints, 0)
    left_eye = _point_from_keypoints(keypoints, 1)
    right_eye = _point_from_keypoints(keypoints, 2)
    left_ear = _point_from_keypoints(keypoints, 3)
    right_ear = _point_from_keypoints(keypoints, 4)
    left_shoulder = _point_from_keypoints(keypoints, 5)
    right_shoulder = _point_from_keypoints(keypoints, 6)
    left_hip = _point_from_keypoints(keypoints, 11)
    right_hip = _point_from_keypoints(keypoints, 12)

    if nose is None or left_shoulder is None or right_shoulder is None or left_hip is None or right_hip is None:
        return None

    if min(nose[2], left_shoulder[2], right_shoulder[2], left_hip[2], right_hip[2]) < 0.20:
        return None

    shoulder_center = _midpoint(left_shoulder, right_shoulder)
    hip_center = _midpoint(left_hip, right_hip)
    torso_height = max(1.0, _distance(shoulder_center, hip_center))

    head_height_ratio = (shoulder_center[1] - nose[1]) / torso_height
    torso_lean_angle = _angle_degrees(shoulder_center, hip_center)

    head_tilt_angle = 0.0
    eye_pair = None
    if left_eye is not None and right_eye is not None and min(left_eye[2], right_eye[2]) >= 0.20:
        eye_pair = (left_eye, right_eye)
    elif left_ear is not None and right_ear is not None and min(left_ear[2], right_ear[2]) >= 0.20:
        eye_pair = (left_ear, right_ear)

    if eye_pair is not None:
        head_tilt_angle = abs(_angle_degrees(eye_pair[0], eye_pair[1]) - 180.0)

    return {
        "nose": nose,
        "shoulder_center": shoulder_center,
        "hip_center": hip_center,
        "head_height_ratio": head_height_ratio,
        "torso_lean_angle": torso_lean_angle,
        "head_tilt_angle": head_tilt_angle,
        "torso_height": torso_height,
    }


def _collect_keypoints(result, index: int):
    if getattr(result, "keypoints", None) is None:
        return None

    try:
        xy_points = result.keypoints.xy[index].tolist()
    except Exception:
        return None

    confidence_points = None
    try:
        confidence_points = result.keypoints.conf[index].tolist()
    except Exception:
        confidence_points = [1.0] * len(xy_points)

    collected = []
    for point, confidence in zip(xy_points, confidence_points):
        try:
            collected.append((float(point[0]), float(point[1]), float(confidence)))
        except Exception:
            collected.append((0.0, 0.0, 0.0))
    return collected


def _intersection_area(first_box, second_box) -> float:
    x1 = max(first_box[0], second_box[0])
    y1 = max(first_box[1], second_box[1])
    x2 = min(first_box[2], second_box[2])
    y2 = min(first_box[3], second_box[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    return float((x2 - x1) * (y2 - y1))


def _box_area(box) -> float:
    return max(0.0, float((box[2] - box[0]) * (box[3] - box[1])))


def _emit_alert(alert_callback: Callable[[str], None], message: str, level: str = "warning") -> None:
    alert_callback(message)
    db.log_event(level, message, source="driver-monitor")


def _yolo_driver_monitor(alert_callback: Callable[[str], None], config: DriverMonitorConfig) -> None:
    model = _load_yolo_model(config.model_name)

    capture = cv2.VideoCapture(config.camera_index)
    if not capture.isOpened():
        db.log_event("warning", "Driver monitor camera unavailable", source="driver-monitor")
        return

    frame_index = 0
    drowsy_since = None
    last_alert_at = 0.0
    alert_cooldown_seconds = max(2.0, config.drowsiness_alert_seconds)
    baseline_head_ratio = None
    baseline_updates = 0

    try:
        while True:
            success, frame = capture.read()
            if not success:
                time.sleep(0.1)
                continue

            frame_index += 1
            if frame_index % max(1, int(config.frame_stride)) != 0:
                cv2.imshow("Driver Monitor", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue

            results = model.predict(frame, imgsz=640, conf=config.confidence_threshold, verbose=False)
            detections = results[0].boxes if results else None
            drowsiness_score = 0.0
            pose_metrics = None
            if detections is not None:
                for index, box in enumerate(detections):
                    class_index = int(box.cls[0]) if getattr(box, "cls", None) is not None else -1
                    confidence = float(box.conf[0]) if getattr(box, "conf", None) is not None else 0.0
                    if confidence < config.confidence_threshold:
                        continue

                    if class_index != 0:
                        continue

                    xyxy = box.xyxy[0].tolist()
                    keypoints = _collect_keypoints(results[0], index)

                    label = _class_name(model, class_index)
                    x1, y1, x2, y2 = map(int, xyxy)
                    color = (0, 212, 255)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(
                        frame,
                        f"{label} {confidence:.2f}",
                        (x1, max(20, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        color,
                        2,
                    )

                    metrics = _extract_pose_metrics(xyxy, keypoints)
                    if metrics is None:
                        continue

                    pose_metrics = metrics
                    torso_center = metrics["shoulder_center"]
                    hip_center = metrics["hip_center"]
                    nose = metrics["nose"]

                    cv2.circle(frame, tuple(map(int, nose[:2])), 4, (51, 255, 218), -1)
                    cv2.circle(frame, tuple(map(int, torso_center)), 4, (255, 120, 0), -1)
                    cv2.circle(frame, tuple(map(int, hip_center)), 4, (255, 120, 0), -1)
                    cv2.line(frame, tuple(map(int, torso_center)), tuple(map(int, hip_center)), (0, 212, 255), 2)

                    if baseline_head_ratio is None:
                        baseline_head_ratio = metrics["head_height_ratio"]
                        baseline_updates = 1
                    else:
                        if metrics["head_height_ratio"] >= baseline_head_ratio * 0.9:
                            baseline_head_ratio = (baseline_head_ratio * baseline_updates + metrics["head_height_ratio"]) / (baseline_updates + 1)
                            baseline_updates += 1

                    if baseline_head_ratio is not None:
                        head_drop = baseline_head_ratio - metrics["head_height_ratio"]
                        if head_drop > 0.10:
                            drowsiness_score += 0.55
                        if metrics["torso_lean_angle"] > 18.0:
                            drowsiness_score += 0.30
                        if metrics["head_tilt_angle"] > 18.0:
                            drowsiness_score += 0.15
                        if metrics["head_height_ratio"] < baseline_head_ratio * 0.82:
                            drowsiness_score += 0.25

                    status_line = (
                        f"Head {metrics['head_height_ratio']:.2f} | "
                        f"Lean {metrics['torso_lean_angle']:.1f} | "
                        f"Tilt {metrics['head_tilt_angle']:.1f}"
                    )
                    cv2.putText(frame, status_line, (18, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (123, 47, 255), 2)

                    break

            now = time.time()
            if pose_metrics is None:
                drowsy_since = None
                status_text = "Driver pose not visible"
            else:
                if drowsiness_score >= 0.6:
                    if drowsy_since is None:
                        drowsy_since = now
                    elif now - drowsy_since >= config.drowsiness_alert_seconds and now - last_alert_at >= alert_cooldown_seconds:
                        _emit_alert(alert_callback, "Drowsiness detected. Please sit upright and take a break if needed.")
                        last_alert_at = now
                        drowsy_since = now
                    status_text = f"Drowsiness risk {drowsiness_score:.2f}"
                else:
                    drowsy_since = None
                    status_text = f"Driver OK {drowsiness_score:.2f}"

            cv2.putText(frame, status_text, (18, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 212, 255), 2)
            cv2.putText(frame, "Press Q to quit", (18, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (123, 47, 255), 2)

            cv2.imshow("Driver Monitor", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        capture.release()
        cv2.destroyAllWindows()


def start_driver_monitor(alert_callback: Callable[[str], None], config: Optional[DriverMonitorConfig] = None) -> None:
    config = config or DriverMonitorConfig()
    try:
        _yolo_driver_monitor(alert_callback, config)
    except Exception as exc:
        db.log_event("error", f"Driver monitor failed: {exc}", source="driver-monitor")
