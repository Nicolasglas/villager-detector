"""Stoppable background screen-detection monitor."""

import re
import threading
from collections.abc import Callable

from src_package.config import AppSettings
from src_package.models import DetectionResult
from src_package.services.alerts import AvailabilityTransition, play_warning
from src_package.services.screen_capture import ScreenCapturer, is_blank_frame
from src_package.services.template_matcher import TemplateMatcher

_BLANK_WARNING_SECONDS = 2.0
_BLANK_WARNING_TEXT = (
    "Captured region is black in every frame. The GPU capture backend for "
    "exclusive-fullscreen applications was unavailable; switch the game to "
    "Borderless Fullscreen (or windowed), then restart monitoring."
)
class DetectionMonitor:
    """Capture and match on one daemon thread without touching UI objects."""

    def __init__(
        self,
        settings: AppSettings,
        on_result: Callable[[DetectionResult], None],
        on_error: Callable[[str], None],
        *,
        on_warning: Callable[[str], None] | None = None,
        capturer: ScreenCapturer | None = None,
        matcher: TemplateMatcher | None = None,
    ) -> None:
        self._settings = settings
        self._on_result = on_result
        self._on_error = on_error
        self._on_warning = on_warning
        self._capturer = capturer if capturer is not None else ScreenCapturer()
        self._matcher = (
            matcher
            if matcher is not None
            else TemplateMatcher(
                settings.reference_image_path,
                settings.confidence_threshold,
            )
        )
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lifecycle_lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def start(self) -> None:
        """Start one worker; repeated calls while running are harmless."""
        with self._lifecycle_lock:
            if self.is_running:
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="detection-monitor",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 1.0) -> bool:
        """Signal the worker and report whether it has actually exited."""
        with self._lifecycle_lock:
            self._stop_event.set()
            thread = self._thread
            if thread is None:
                return True
            if thread is threading.current_thread():
                return False
            thread.join(timeout=max(0.0, timeout))
            return not thread.is_alive()

    def _run(self) -> None:
        transition = AvailabilityTransition()
        interval_seconds = self._settings.polling_interval_ms / 1000.0
        blank_threshold = max(
            2, int(round(_BLANK_WARNING_SECONDS / max(interval_seconds, 0.05)))
        )
        blank_streak = 0
        blank_warned = False

        while not self._stop_event.is_set():
            try:
                frame = self._capturer.capture(self._settings.region)
            except Exception as exc:
                self._fail("capture", exc)
                return

            try:
                if is_blank_frame(frame):
                    blank_streak += 1
                    if blank_streak >= blank_threshold and not blank_warned:
                        blank_warned = True
                        self._warn(_BLANK_WARNING_TEXT)
                else:
                    blank_streak = 0
                    blank_warned = False
            except Exception as exc:
                self._fail("capture inspection", exc)
                return

            try:
                result = self._matcher.match(frame)
            except Exception as exc:
                self._fail("match", exc)
                return

            try:
                self._on_result(result)
            except Exception as exc:
                self._fail("result callback", exc)
                return

            if transition.update(result.available):
                try:
                    play_warning(self._settings)
                except Exception as exc:
                    self._fail("warning", exc)
                    return

            if self._stop_event.wait(interval_seconds):
                return

    def _warn(self, message: str) -> None:
        """Publish a non-fatal warning; a broken UI callback is still an error."""
        if self._on_warning is None:
            return
        try:
            self._on_warning(message)
        except Exception as exc:
            self._fail("warning callback", exc)

    def _fail(self, stage: str, exc: Exception) -> None:
        self._stop_event.set()
        self._on_error(
            f"Monitoring stopped: {stage} failed: {self._safe_exception_detail(exc)}"
        )

    @staticmethod
    def _safe_exception_detail(exc: Exception) -> str:
        """Keep one actionable line while redacting common credential forms."""
        detail = " ".join(str(exc).split()) or type(exc).__name__
        detail = re.sub(
            r"(?i)\b(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*[^\s,;]+",
            r"\1=[REDACTED]",
            detail,
        )
        return detail[:240]
