import threading
import time
from collections.abc import Callable

import numpy as np
import pytest

from src_package.config import AppSettings, Region
from src_package.models import DetectionResult
from src_package.services import monitor as monitor_module
from src_package.services import screen_capture
from src_package.services.monitor import DetectionMonitor
from src_package.services.screen_capture import ScreenCapturer


class FakeShot:
    def __init__(self, pixels: np.ndarray) -> None:
        self.pixels = pixels

    def __array__(self, dtype: object = None, copy: object = None) -> np.ndarray:
        return np.asarray(self.pixels, dtype=dtype)


class FakeMssSession:
    def __init__(
        self, pixels: np.ndarray, monitors: list[dict[str, int]] | None = None
    ) -> None:
        self.pixels = pixels
        self.rectangles: list[dict[str, int]] = []
        self.monitors = (
            monitors
            if monitors is not None
            else [
                {"left": -1920, "top": 0, "width": 3840, "height": 1080},
                {"left": -1920, "top": 0, "width": 1920, "height": 1080},
                {"left": 0, "top": 0, "width": 1920, "height": 1080},
            ]
        )

    def __enter__(self) -> "FakeMssSession":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def grab(self, rectangle: dict[str, int]) -> FakeShot:
        self.rectangles.append(rectangle)
        return FakeShot(self.pixels)


def test_screen_capturer_grabs_only_the_exact_configured_rectangle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = np.arange(4 * 3 * 4, dtype=np.uint8).reshape((3, 4, 4))
    session = FakeMssSession(source)
    monkeypatch.setattr(screen_capture.mss, "MSS", lambda: session)

    captured = ScreenCapturer().capture(Region(x=-20, y=35, width=4, height=3))
    source[0, 0, 0] = 255

    assert session.rectangles == [
        {"left": -20, "top": 35, "width": 4, "height": 3}
    ]
    assert captured.shape == (3, 4, 4)
    assert captured[0, 0, 0] == 0


def test_screen_capturer_discards_pixels_outside_requested_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = np.arange(6 * 7 * 4, dtype=np.uint8).reshape((6, 7, 4))
    session = FakeMssSession(source)
    monkeypatch.setattr(screen_capture.mss, "MSS", lambda: session)

    captured = ScreenCapturer().capture(Region(x=10, y=20, width=4, height=3))

    assert captured.shape == (3, 4, 4)
    assert np.array_equal(captured, source[:3, :4])


def test_screen_capturer_uses_dxcam_when_mss_returns_black(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCamera:
        def __init__(self) -> None:
            self.regions: list[tuple[int, int, int, int]] = []

        def grab(
            self,
            region: tuple[int, int, int, int],
            new_frame_only: bool,
        ) -> np.ndarray:
            self.regions.append(region)
            assert new_frame_only is False
            return np.full((3, 4, 4), 200, dtype=np.uint8)

    class FakeDxcam:
        def __init__(self) -> None:
            self.camera = FakeCamera()
            self.arguments: dict[str, object] | None = None

        def create(self, **kwargs: object) -> FakeCamera:
            self.arguments = kwargs
            return self.camera

    session = FakeMssSession(np.zeros((3, 4, 4), dtype=np.uint8))
    fake_dxcam = FakeDxcam()
    monkeypatch.setattr(screen_capture.mss, "MSS", lambda: session)
    monkeypatch.setattr(screen_capture, "dxcam", fake_dxcam)

    captured = ScreenCapturer().capture(Region(x=10, y=20, width=4, height=3))

    assert captured.max() == 200
    assert fake_dxcam.arguments == {"output_idx": 1, "output_color": "BGRA"}
    assert fake_dxcam.camera.regions == [(10, 20, 14, 23)]


def test_screen_capturer_converts_global_coordinates_for_dxcam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCamera:
        def __init__(self) -> None:
            self.region: tuple[int, int, int, int] | None = None

        def grab(
            self,
            region: tuple[int, int, int, int],
            new_frame_only: bool,
        ) -> np.ndarray:
            self.region = region
            assert new_frame_only is False
            return np.full((3, 4, 4), 200, dtype=np.uint8)

    class FakeDxcam:
        def __init__(self) -> None:
            self.camera = FakeCamera()

        def create(self, **kwargs: object) -> FakeCamera:
            return self.camera

    session = FakeMssSession(
        np.zeros((3, 4, 4), dtype=np.uint8),
        monitors=[
            {"left": -1920, "top": 0, "width": 3840, "height": 1080},
            {"left": -1920, "top": 0, "width": 1920, "height": 1080},
        ],
    )
    fake_dxcam = FakeDxcam()
    monkeypatch.setattr(screen_capture.mss, "MSS", lambda: session)
    monkeypatch.setattr(screen_capture, "dxcam", fake_dxcam)

    ScreenCapturer().capture(Region(x=-1910, y=20, width=4, height=3))

    assert fake_dxcam.camera.region == (10, 20, 14, 23)


def test_screen_capturer_keeps_mss_frame_when_dxcam_has_no_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeDxcam:
        def create(self, **kwargs: object) -> object:
            return self

        def grab(self, region: tuple[int, int, int, int]) -> None:
            return None

    session = FakeMssSession(np.zeros((3, 4, 4), dtype=np.uint8))
    monkeypatch.setattr(screen_capture.mss, "MSS", lambda: session)
    monkeypatch.setattr(screen_capture, "dxcam", FakeDxcam())

    captured = ScreenCapturer().capture(Region(x=10, y=20, width=4, height=3))

    assert np.array_equal(captured, np.zeros((3, 4, 4), dtype=np.uint8))


def test_screen_capturer_refuses_a_region_off_every_monitor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeMssSession(np.zeros((3, 4, 4), dtype=np.uint8))
    monkeypatch.setattr(screen_capture.mss, "MSS", lambda: session)

    with pytest.raises(screen_capture.ScreenRegionError, match="outside every monitor"):
        ScreenCapturer().capture(Region(x=6000, y=6000, width=4, height=3))

    assert session.rectangles == []


def test_list_monitors_skips_the_all_monitors_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeMssSession(
        np.zeros((3, 4, 4), dtype=np.uint8),
        monitors=[
            {"left": -1920, "top": 0, "width": 3840, "height": 1080},
            {"left": -1920, "top": 0, "width": 1920, "height": 1080},
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
        ],
    )
    monkeypatch.setattr(screen_capture.mss, "MSS", lambda: session)

    monitors = screen_capture.list_monitors()

    assert [monitor.index for monitor in monitors] == [1, 2]
    assert monitors[0].describe() == "monitor 1 at (-1920, 0) 1920x1080"


def test_monitor_for_region_prefers_the_containing_then_the_most_overlapped() -> None:
    left = screen_capture.MonitorGeometry(1, -1920, 0, 1920, 1080)
    right = screen_capture.MonitorGeometry(2, 0, 0, 1920, 1080)

    assert (
        screen_capture.monitor_for_region(Region(x=10, y=10, width=50, height=50), [left, right])
        is right
    )
    assert (
        screen_capture.monitor_for_region(Region(x=-100, y=10, width=180, height=50), [left, right])
        is left
    )
    assert screen_capture.monitor_for_region(Region(x=0, y=5000, width=10, height=10), [left, right]) is None


def test_is_blank_frame_detects_only_black_frames() -> None:
    assert screen_capture.is_blank_frame(np.zeros((3, 3, 4), dtype=np.uint8)) is True
    black_bgra = np.zeros((3, 3, 4), dtype=np.uint8)
    black_bgra[..., 3] = 255
    assert screen_capture.is_blank_frame(black_bgra) is True
    nearly_black = np.zeros((3, 3, 4), dtype=np.uint8)
    nearly_black[1, 1, 0] = 4
    assert screen_capture.is_blank_frame(nearly_black) is True
    lit = np.zeros((3, 3, 4), dtype=np.uint8)
    lit[2, 2, 0] = 200
    assert screen_capture.is_blank_frame(lit) is False


def test_is_blank_frame_rejects_an_empty_image() -> None:
    with pytest.raises(ValueError, match="non-empty image array"):
        screen_capture.is_blank_frame(np.zeros((0, 0, 4), dtype=np.uint8))


def test_describe_capture_geometry_reports_the_owning_monitor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        screen_capture,
        "list_monitors",
        lambda: [screen_capture.MonitorGeometry(1, 0, 0, 1920, 1080)],
    )

    description = screen_capture.describe_capture_geometry(
        Region(x=0, y=0, width=400, height=300)
    )

    assert description == "Region (0, 0) 400x300 on monitor 1 at (0, 0) 1920x1080"


def test_describe_capture_geometry_flags_a_region_past_the_monitor_edge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        screen_capture,
        "list_monitors",
        lambda: [screen_capture.MonitorGeometry(1, 0, 0, 1920, 1080)],
    )

    description = screen_capture.describe_capture_geometry(
        Region(x=1900, y=1000, width=400, height=300)
    )

    assert description.endswith("monitor 1 at (0, 0) 1920x1080, region extends past that monitor's edge")


class FakeCapturer:
    def __init__(self, frames: list[object] | None = None) -> None:
        self.frames = frames or [np.zeros((2, 2, 4), dtype=np.uint8)]
        self.calls: list[Region] = []
        self.index = 0

    def capture(self, region: Region) -> np.ndarray:
        self.calls.append(region)
        item = self.frames[min(self.index, len(self.frames) - 1)]
        self.index += 1
        if isinstance(item, BaseException):
            raise item
        assert isinstance(item, np.ndarray)
        return item


class FakeMatcher:
    def __init__(self, results: list[object]) -> None:
        self.results = results
        self.index = 0

    def match(self, frame: np.ndarray) -> DetectionResult:
        item = self.results[min(self.index, len(self.results) - 1)]
        self.index += 1
        if isinstance(item, BaseException):
            raise item
        assert isinstance(item, DetectionResult)
        return item


def _settings(interval_ms: int = 50) -> AppSettings:
    return AppSettings(
        region=Region(x=11, y=22, width=33, height=44),
        polling_interval_ms=interval_ms,
        warning_mode="builtin",
    )


def test_monitor_publishes_results_and_warns_on_loss_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published: list[DetectionResult] = []
    warnings: list[str] = []
    got_two = threading.Event()

    def on_result(result: DetectionResult) -> None:
        published.append(result)
        if len(published) == 2:
            got_two.set()

    monkeypatch.setattr(
        monitor_module, "play_warning", lambda settings: warnings.append("warning")
    )
    capturer = FakeCapturer()
    matcher = FakeMatcher(
        [
            DetectionResult(score=0.97, available=True),
            DetectionResult(score=0.21, available=False),
        ]
    )
    monitor = DetectionMonitor(
        _settings(), on_result, pytest.fail, capturer=capturer, matcher=matcher
    )

    monitor.start()
    assert got_two.wait(1.0)
    monitor.stop()

    assert published[:2] == [
        DetectionResult(score=0.97, available=True),
        DetectionResult(score=0.21, available=False),
    ]
    assert warnings == ["warning"]
    assert capturer.calls[:2] == [_settings().region, _settings().region]
    assert monitor.is_running is False


def test_stop_interrupts_a_long_polling_wait_promptly() -> None:
    published = threading.Event()
    monitor = DetectionMonitor(
        _settings(interval_ms=10_000),
        lambda result: published.set(),
        pytest.fail,
        capturer=FakeCapturer(),
        matcher=FakeMatcher([DetectionResult(score=0.9, available=True)]),
    )

    monitor.start()
    assert published.wait(1.0)
    started = time.monotonic()
    monitor.stop()
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert monitor.is_running is False


class BlockingCapturer(FakeCapturer):
    def __init__(self) -> None:
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def capture(self, region: Region) -> np.ndarray:
        self.entered.set()
        assert self.release.wait(1.0)
        return super().capture(region)


def test_stop_reports_incomplete_while_capture_is_blocked_and_completes_later() -> None:
    capturer = BlockingCapturer()
    monitor = DetectionMonitor(
        _settings(),
        lambda result: None,
        pytest.fail,
        capturer=capturer,
        matcher=FakeMatcher([DetectionResult(score=0.9, available=True)]),
    )

    monitor.start()
    assert capturer.entered.wait(1.0)

    assert monitor.stop(timeout=0.01) is False
    assert monitor.is_running is True

    capturer.release.set()
    assert monitor.stop(timeout=1.0) is True
    assert monitor.is_running is False


def test_duplicate_start_does_not_create_a_second_worker() -> None:
    capturer = BlockingCapturer()
    monitor = DetectionMonitor(
        _settings(),
        lambda result: None,
        pytest.fail,
        capturer=capturer,
        matcher=FakeMatcher([DetectionResult(score=0.9, available=True)]),
    )

    monitor.start()
    assert capturer.entered.wait(1.0)
    monitor.start()
    capturer.release.set()
    monitor.stop()

    assert len(capturer.calls) == 1


@pytest.mark.parametrize("failure_stage", ["capture", "match", "warning"])
def test_worker_failure_reports_safe_stage_and_stops(
    failure_stage: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    errors: list[str] = []
    failed = threading.Event()

    def on_error(message: str) -> None:
        errors.append(message)
        failed.set()

    capturer = FakeCapturer(
        [RuntimeError("private capture detail")]
        if failure_stage == "capture"
        else None
    )
    matcher = FakeMatcher(
        [RuntimeError("private match detail")]
        if failure_stage == "match"
        else (
            [
                DetectionResult(score=0.9, available=True),
                DetectionResult(score=0.1, available=False),
            ]
            if failure_stage == "warning"
            else [DetectionResult(score=0.9, available=True)]
        )
    )

    def warning(settings: AppSettings) -> None:
        if failure_stage == "warning":
            raise RuntimeError("private warning detail")

    monkeypatch.setattr(monitor_module, "play_warning", warning)
    monitor = DetectionMonitor(
        _settings(), lambda result: None, on_error, capturer=capturer, matcher=matcher
    )

    monitor.start()
    assert failed.wait(1.0)
    monitor.stop()

    expected_detail = {
        "capture": "private capture detail",
        "match": "private match detail",
        "warning": "private warning detail",
    }[failure_stage]
    assert errors == [
        f"Monitoring stopped: {failure_stage} failed: {expected_detail}"
    ]
    assert monitor.is_running is False


def test_result_callback_failure_is_reported_and_stops_worker() -> None:
    errors: list[str] = []
    failed = threading.Event()

    def on_result(result: DetectionResult) -> None:
        raise RuntimeError("private callback detail")

    def on_error(message: str) -> None:
        errors.append(message)
        failed.set()

    monitor = DetectionMonitor(
        _settings(),
        on_result,
        on_error,
        capturer=FakeCapturer(),
        matcher=FakeMatcher([DetectionResult(score=0.9, available=True)]),
    )

    monitor.start()
    assert failed.wait(1.0)
    monitor.stop()

    assert errors == [
        "Monitoring stopped: result callback failed: private callback detail"
    ]
    assert monitor.is_running is False


def test_start_cannot_replace_worker_while_stop_is_in_progress() -> None:
    published = threading.Event()
    monitor = DetectionMonitor(
        _settings(interval_ms=10_000),
        lambda result: published.set(),
        pytest.fail,
        capturer=FakeCapturer(),
        matcher=FakeMatcher([DetectionResult(score=0.9, available=True)]),
    )
    monitor.start()
    assert published.wait(1.0)

    old_thread = monitor._thread
    assert old_thread is not None
    original_join = old_thread.join
    old_worker_reaped = threading.Event()
    allow_stop_to_return = threading.Event()

    def controlled_join(timeout: float | None = None) -> None:
        original_join(timeout)
        old_worker_reaped.set()
        assert allow_stop_to_return.wait(1.0)

    old_thread.join = controlled_join  # type: ignore[method-assign]
    stop_thread = threading.Thread(target=monitor.stop)
    stop_thread.start()
    assert old_worker_reaped.wait(1.0)

    start_returned = threading.Event()

    def concurrent_start() -> None:
        monitor.start()
        start_returned.set()

    start_thread = threading.Thread(target=concurrent_start)
    start_thread.start()

    assert not start_returned.wait(0.1)
    assert monitor._thread is old_thread

    allow_stop_to_return.set()
    stop_thread.join(timeout=1.0)
    start_thread.join(timeout=1.0)
    assert not stop_thread.is_alive()
    assert not start_thread.is_alive()
    assert start_returned.is_set()
    assert monitor._thread is not old_thread

    monitor.stop()


def test_stop_called_from_result_callback_does_not_join_current_thread() -> None:
    stopped = threading.Event()
    errors: list[str] = []
    monitor: DetectionMonitor

    def stop_from_worker(result: DetectionResult) -> None:
        monitor.stop()
        stopped.set()

    monitor = DetectionMonitor(
        _settings(),
        stop_from_worker,
        errors.append,
        capturer=FakeCapturer(),
        matcher=FakeMatcher([DetectionResult(score=0.9, available=True)]),
    )

    monitor.start()
    assert stopped.wait(1.0)
    monitor.stop()

    assert errors == []
    assert monitor.is_running is False


def test_error_detail_is_single_line_bounded_and_redacts_credentials() -> None:
    detail = DetectionMonitor._safe_exception_detail(
        RuntimeError("capture denied\n token=abc123 password:letmein")
    )

    assert detail == "capture denied token=[REDACTED] password=[REDACTED]"
    assert "\n" not in detail


def _black_frame() -> np.ndarray:
    return np.zeros((2, 2, 4), dtype=np.uint8)


def _lit_frame() -> np.ndarray:
    return np.full((2, 2, 4), 200, dtype=np.uint8)


def test_monitor_warns_once_while_the_capture_stays_black(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(monitor_module, "_BLANK_WARNING_SECONDS", 0.05)
    warnings: list[str] = []
    published = threading.Event()
    results: list[DetectionResult] = []

    def on_result(result: DetectionResult) -> None:
        results.append(result)
        if len(results) == 6:
            published.set()

    monitor = DetectionMonitor(
        _settings(interval_ms=50),
        on_result,
        pytest.fail,
        on_warning=warnings.append,
        capturer=FakeCapturer([_black_frame()]),
        matcher=FakeMatcher([DetectionResult(score=-1.0, available=False)]),
    )

    monitor.start()
    assert published.wait(2.0)
    monitor.stop()

    assert warnings == [monitor_module._BLANK_WARNING_TEXT]
    assert "exclusive" in warnings[0]


def test_monitor_warns_again_after_real_frames_reset_the_black_streak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(monitor_module, "_BLANK_WARNING_SECONDS", 0.05)
    warnings: list[str] = []
    warned_twice = threading.Event()

    def on_warning(message: str) -> None:
        warnings.append(message)
        if len(warnings) == 2:
            warned_twice.set()

    monitor = DetectionMonitor(
        _settings(interval_ms=50),
        lambda result: None,
        pytest.fail,
        on_warning=on_warning,
        capturer=FakeCapturer(
            [
                _black_frame(),
                _black_frame(),
                _lit_frame(),
                _black_frame(),
                _black_frame(),
            ]
        ),
        matcher=FakeMatcher([DetectionResult(score=0.9, available=True)]),
    )

    monitor.start()
    assert warned_twice.wait(2.0)
    monitor.stop()

    assert warnings == [monitor_module._BLANK_WARNING_TEXT] * 2
    assert monitor.is_running is False


def test_monitor_without_a_warning_callback_still_monitors_black_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(monitor_module, "_BLANK_WARNING_SECONDS", 0.05)
    published = threading.Event()
    monitor = DetectionMonitor(
        _settings(interval_ms=50),
        lambda result: published.set(),
        pytest.fail,
        capturer=FakeCapturer([_black_frame()]),
        matcher=FakeMatcher([DetectionResult(score=-1.0, available=False)]),
    )

    monitor.start()
    assert published.wait(2.0)
    monitor.stop()

    assert monitor.is_running is False


def test_warning_callback_failure_is_reported_and_stops_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(monitor_module, "_BLANK_WARNING_SECONDS", 0.05)
    errors: list[str] = []
    failed = threading.Event()

    def on_warning(message: str) -> None:
        raise RuntimeError("private warning callback detail")

    def on_error(message: str) -> None:
        errors.append(message)
        failed.set()

    monitor = DetectionMonitor(
        _settings(interval_ms=50),
        lambda result: None,
        on_error,
        on_warning=on_warning,
        capturer=FakeCapturer([_black_frame()]),
        matcher=FakeMatcher([DetectionResult(score=-1.0, available=False)]),
    )

    monitor.start()
    assert failed.wait(2.0)
    monitor.stop()

    assert errors == [
        "Monitoring stopped: warning callback failed: private warning callback detail"
    ]
