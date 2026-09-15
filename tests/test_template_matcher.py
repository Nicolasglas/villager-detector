from pathlib import Path

import cv2
import numpy as np
import pytest

from src_package.services.template_matcher import TemplateMatcher


def _pattern() -> np.ndarray:
    """Return a deterministic, non-uniform grayscale template."""
    rows, columns = np.indices((7, 9))
    return ((rows * 37 + columns * 19 + rows * columns * 11) % 256).astype(
        np.uint8
    )


def _write_template(path: Path) -> np.ndarray:
    template = _pattern()
    assert cv2.imwrite(str(path), template)
    return template


def test_exact_embedded_match_is_available(tmp_path: Path) -> None:
    reference_path = tmp_path / "reference.png"
    template = _write_template(reference_path)
    frame_gray = np.zeros((24, 28), dtype=np.uint8)
    frame_gray[10:17, 12:21] = template
    frame_bgr = cv2.cvtColor(frame_gray, cv2.COLOR_GRAY2BGR)

    result = TemplateMatcher(reference_path, threshold=0.99).match(frame_bgr)

    assert result.score == pytest.approx(1.0, abs=1e-6)
    assert result.available is True


def test_absent_pattern_scores_below_threshold(tmp_path: Path) -> None:
    reference_path = tmp_path / "reference.png"
    _write_template(reference_path)
    frame_gray = np.random.default_rng(1729).integers(
        0, 256, size=(30, 34), dtype=np.uint8
    )
    frame_bgr = cv2.cvtColor(frame_gray, cv2.COLOR_GRAY2BGR)

    result = TemplateMatcher(reference_path, threshold=0.99).match(frame_bgr)

    assert result.score < 0.99
    assert result.available is False


def test_score_equal_to_threshold_is_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference_path = tmp_path / "reference.png"
    _write_template(reference_path)
    monkeypatch.setattr(cv2, "minMaxLoc", lambda matches: (0.0, 0.7, None, None))

    result = TemplateMatcher(reference_path, threshold=0.7).match(_pattern())

    assert result.score == 0.7
    assert result.available is True


@pytest.mark.parametrize("threshold", [-0.01, 1.01, float("nan"), float("inf")])
def test_threshold_outside_finite_unit_interval_is_rejected(
    tmp_path: Path, threshold: float
) -> None:
    reference_path = tmp_path / "reference.png"
    _write_template(reference_path)

    with pytest.raises(ValueError, match="between 0 and 1"):
        TemplateMatcher(reference_path, threshold=threshold)


def test_template_larger_than_frame_is_rejected(tmp_path: Path) -> None:
    reference_path = tmp_path / "reference.png"
    _write_template(reference_path)
    frame_bgr = np.zeros((6, 9, 3), dtype=np.uint8)

    with pytest.raises(ValueError, match="smaller than the template"):
        TemplateMatcher(reference_path, threshold=0.8).match(frame_bgr)


def test_unreadable_reference_is_rejected(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.png"

    with pytest.raises(ValueError, match="reference image"):
        TemplateMatcher(missing_path, threshold=0.8)


@pytest.mark.parametrize(
    "template", [np.zeros((10, 10), dtype=np.uint8), np.eye(10, dtype=np.uint8)]
)
def test_uniform_or_near_zero_variance_reference_is_rejected(
    tmp_path: Path, template: np.ndarray
) -> None:
    reference_path = tmp_path / "flat.png"
    assert cv2.imwrite(str(reference_path), template)

    with pytest.raises(ValueError, match="uniform or near-uniform"):
        TemplateMatcher(reference_path, threshold=0.8)


@pytest.mark.parametrize(
    ("raw_score", "expected"),
    [(float("nan"), -1.0), (float("inf"), -1.0), (1.5, 1.0), (-1.5, -1.0)],
)
def test_non_finite_scores_are_sanitized_and_finite_scores_are_clamped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_score: float,
    expected: float,
) -> None:
    reference_path = tmp_path / "reference.png"
    _write_template(reference_path)
    monkeypatch.setattr(
        cv2, "minMaxLoc", lambda matches: (0.0, raw_score, None, None)
    )

    result = TemplateMatcher(reference_path, threshold=0.5).match(_pattern())

    assert result.score == expected
    assert result.available is (expected >= 0.5)


def test_bgra_frame_is_converted_and_matched(tmp_path: Path) -> None:
    reference_path = tmp_path / "reference.png"
    template = _write_template(reference_path)
    frame_bgra = cv2.cvtColor(template, cv2.COLOR_GRAY2BGRA)
    frame_bgra[:, :, 3] = np.arange(template.shape[1], dtype=np.uint8)

    result = TemplateMatcher(reference_path, threshold=0.99).match(frame_bgra)

    assert result.score == pytest.approx(1.0, abs=1e-6)
    assert result.available is True


@pytest.mark.parametrize(
    "frame",
    [
        np.zeros((7,), dtype=np.uint8),
        np.zeros((7, 9, 2), dtype=np.uint8),
        np.zeros((7, 9, 5), dtype=np.uint8),
    ],
)
def test_unsupported_frame_shapes_are_rejected(
    tmp_path: Path, frame: np.ndarray
) -> None:
    reference_path = tmp_path / "reference.png"
    _write_template(reference_path)

    with pytest.raises(ValueError, match="shape"):
        TemplateMatcher(reference_path, threshold=0.8).match(frame)
