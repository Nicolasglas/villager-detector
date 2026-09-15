"""OpenCV template matching for captured frames."""

import math
from pathlib import Path

import cv2
import numpy as np

from src_package.models import DetectionResult


class TemplateMatcher:
    """Match one grayscale reference image against successive frames."""

    def __init__(self, reference_path: Path, threshold: float) -> None:
        if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
            raise ValueError("Template matching threshold must be between 0 and 1")
        template_gray = cv2.imread(str(reference_path), cv2.IMREAD_GRAYSCALE)
        if template_gray is None or template_gray.size == 0:
            raise ValueError(f"Could not read reference image: {reference_path}")
        if float(np.var(template_gray)) < 1.0:
            raise ValueError(
                "Reference image must contain visible variation; uniform or "
                "near-uniform templates cannot be matched reliably"
            )

        self._template_gray = template_gray
        self._threshold = threshold

    def match(self, frame_bgr: np.ndarray) -> DetectionResult:
        """Return the best normalized match and its threshold state."""
        frame_gray = self._to_grayscale(frame_bgr)
        template_height, template_width = self._template_gray.shape
        frame_height, frame_width = frame_gray.shape
        if frame_height < template_height or frame_width < template_width:
            raise ValueError("Frame is smaller than the template")

        matches = cv2.matchTemplate(
            frame_gray,
            self._template_gray,
            cv2.TM_CCOEFF_NORMED,
        )
        _, maximum_score, _, _ = cv2.minMaxLoc(matches)
        score = float(maximum_score)
        if not math.isfinite(score):
            score = -1.0
        else:
            score = max(-1.0, min(1.0, score))

        return DetectionResult(score=score, available=score >= self._threshold)

    @staticmethod
    def _to_grayscale(frame_bgr: np.ndarray) -> np.ndarray:
        if not isinstance(frame_bgr, np.ndarray):
            raise ValueError("Frame must be a NumPy array with a supported shape")
        if frame_bgr.ndim == 2:
            return frame_bgr
        if frame_bgr.ndim == 3 and frame_bgr.shape[2] == 3:
            return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        if frame_bgr.ndim == 3 and frame_bgr.shape[2] == 4:
            return cv2.cvtColor(frame_bgr, cv2.COLOR_BGRA2GRAY)
        raise ValueError(f"Unsupported frame shape: {frame_bgr.shape}")
