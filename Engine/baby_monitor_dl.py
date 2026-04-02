from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

try:
    import mediapipe as mp  # pyright: ignore[reportMissingImports]
except Exception:
    mp = None


@dataclass
class BabyMonitorResult:
    wake_up: bool
    moving: bool
    outside: bool
    ear: float
    motion_score: float
    message: str


class BabyMonitorDL:
    """Deep-learning style baby monitor pipeline inspired by the requested reference repo.

    Features:
    1. Wake-up detection via EAR (Eye Aspect Ratio) from face mesh landmarks.
    2. Moving detection via pose landmark motion over time.
    3. Outside-region detection via polygon containment on body landmarks.
    """

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or {}
        self._has_mediapipe = mp is not None

        self._eye_threshold = float(self.settings.get("baby_eye_ear_threshold", 0.18) or 0.18)
        self._motion_threshold = float(self.settings.get("baby_motion_threshold", 0.012) or 0.012)
        self._outside_frames = int(float(self.settings.get("baby_outside_frames", 8) or 8))

        self._outside_counter = 0
        self._prev_pose: np.ndarray | None = None
        self._last_alert_at = 0.0

        # Default polygon region (normalized points) as in the reference concept.
        self._region_points = [
            [0.08, 0.12],
            [0.92, 0.12],
            [0.92, 0.92],
            [0.08, 0.92],
        ]

        if self._has_mediapipe:
            self._face_mesh = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._pose = mp.solutions.pose.Pose(
                static_image_mode=False,
                model_complexity=1,
                enable_segmentation=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        else:
            self._face_mesh = None
            self._pose = None

    def set_region_points(self, points: list[list[float]]) -> None:
        cleaned: list[list[float]] = []
        for point in points or []:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                continue
            try:
                x = max(0.0, min(1.0, float(point[0])))
                y = max(0.0, min(1.0, float(point[1])))
                cleaned.append([x, y])
            except Exception:
                continue

        if len(cleaned) >= 3:
            self._region_points = cleaned

    def get_region_points(self) -> list[list[float]]:
        return list(self._region_points)

    def update_settings(self, settings: dict[str, Any]) -> None:
        self.settings.update(settings)
        self._eye_threshold = float(self.settings.get("baby_eye_ear_threshold", self._eye_threshold) or self._eye_threshold)
        self._motion_threshold = float(self.settings.get("baby_motion_threshold", self._motion_threshold) or self._motion_threshold)
        self._outside_frames = int(float(self.settings.get("baby_outside_frames", self._outside_frames) or self._outside_frames))

    def _norm_to_px(self, x: float, y: float, w: int, h: int) -> tuple[int, int]:
        px = max(0, min(w - 1, int(x * w)))
        py = max(0, min(h - 1, int(y * h)))
        return px, py

    def _euclidean(self, a: tuple[int, int], b: tuple[int, int]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def _compute_ear(self, face_landmarks: Any, w: int, h: int) -> float:
        # Same landmark groups concept used by reference project.
        left = [362, 385, 387, 263, 373, 380]
        right = [33, 160, 158, 133, 153, 144]

        def eye_ear(indices: list[int]) -> float:
            pts = []
            for idx in indices:
                lm = face_landmarks.landmark[idx]
                pts.append(self._norm_to_px(lm.x, lm.y, w, h))
            p1, p2, p3, p4, p5, p6 = pts
            vertical = self._euclidean(p2, p6) + self._euclidean(p3, p5)
            horizontal = max(self._euclidean(p1, p4), 1.0)
            return vertical / (2.0 * horizontal)

        return float((eye_ear(left) + eye_ear(right)) / 2.0)

    def _motion_from_pose(self, pose_lms: Any) -> float:
        points = []
        for lm in pose_lms.landmark:
            points.append([lm.x, lm.y, lm.z])
        current = np.array(points, dtype=np.float32)

        score = 0.0
        if self._prev_pose is not None and self._prev_pose.shape == current.shape:
            deltas = np.abs(current - self._prev_pose)
            score = float(np.mean(deltas))

        self._prev_pose = current
        return score

    def _outside_region(self, pose_lms: Any, frame_shape: tuple[int, int, int]) -> bool:
        h, w = frame_shape[:2]
        polygon = np.array([self._norm_to_px(p[0], p[1], w, h) for p in self._region_points], dtype=np.int32)

        # Nose + shoulders + hips for robust body-area containment.
        check_indices = [0, 11, 12, 23, 24]

        outside = False
        for idx in check_indices:
            lm = pose_lms.landmark[idx]
            px, py = self._norm_to_px(lm.x, lm.y, w, h)
            if cv2.pointPolygonTest(polygon, (float(px), float(py)), False) < 0:
                outside = True
                break

        if outside:
            self._outside_counter += 1
        else:
            self._outside_counter = 0

        return self._outside_counter >= self._outside_frames

    def _draw_region(self, frame: np.ndarray) -> None:
        h, w = frame.shape[:2]
        polygon = np.array([self._norm_to_px(p[0], p[1], w, h) for p in self._region_points], dtype=np.int32)
        cv2.polylines(frame, [polygon], True, (255, 140, 0), 2)

    def analyze_frame(self, frame: np.ndarray) -> tuple[np.ndarray, BabyMonitorResult]:
        view = frame.copy()
        self._draw_region(view)

        if not self._has_mediapipe:
            result = BabyMonitorResult(
                wake_up=False,
                moving=False,
                outside=False,
                ear=0.0,
                motion_score=0.0,
                message="MediaPipe not available. Running camera stream only.",
            )
            return view, result

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_results = self._face_mesh.process(rgb) if self._face_mesh is not None else None
        pose_results = self._pose.process(rgb) if self._pose is not None else None

        ear = 0.0
        wake_up = False
        moving = False
        outside = False

        if face_results and face_results.multi_face_landmarks:
            ear = self._compute_ear(face_results.multi_face_landmarks[0], frame.shape[1], frame.shape[0])
            wake_up = ear > self._eye_threshold

        if pose_results and pose_results.pose_landmarks:
            motion = self._motion_from_pose(pose_results.pose_landmarks)
            moving = motion > self._motion_threshold
            outside = self._outside_region(pose_results.pose_landmarks, frame.shape)
        else:
            motion = 0.0

        label = f"WAKE:{'YES' if wake_up else 'NO'} | MOVE:{'YES' if moving else 'NO'} | OUTSIDE:{'YES' if outside else 'NO'}"
        cv2.putText(view, label, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 220, 255), 2)
        cv2.putText(view, f"EAR:{ear:.3f} MOTION:{motion:.4f}", (12, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.54, (120, 255, 120), 2)

        result = BabyMonitorResult(
            wake_up=wake_up,
            moving=moving,
            outside=outside,
            ear=ear,
            motion_score=motion,
            message=label,
        )
        return view, result

    def should_alert(self, cooldown_seconds: int = 15) -> bool:
        now = time.time()
        if now - self._last_alert_at < cooldown_seconds:
            return False
        self._last_alert_at = now
        return True
