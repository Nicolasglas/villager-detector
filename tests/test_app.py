import queue
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
from PySide6.QtWidgets import QApplication

from src_package import app as app_module
from src_package import config as config_module
from src_package.app import settings_from_values
from src_package.config import AppSettings, Region


class _FakeValue:
    def __init__(self, value: object) -> None:
        self.value = value

    def get(self) -> object:
        return self.value

    def set(self, value: object) -> None:
        self.value = value


class _FakeWidget:
    def __init__(self) -> None:
        self.options: dict[str, object] = {}

    def configure(self, **options: object) -> None:
        self.options.update(options)


class _FakeRoot:
    def __init__(self) -> None:
        self.after_calls: list[tuple[int, object]] = []
        self.destroyed = False

    def after(self, delay: int, callback: object) -> None:
        self.after_calls.append((delay, callback))

    def destroy(self) -> None:
        self.destroyed = True


def bare_app() -> app_module.VillagerDetectorApp:
    app = app_module.VillagerDetectorApp.__new__(app_module.VillagerDetectorApp)
    app.root = _FakeRoot()  # type: ignore[assignment]
    app._events = queue.Queue()
    app._monitor = None
    app._next_generation = 0
    app._active_generation = None
    app._closing = False
    app._status_text = _FakeValue("NOT MONITORING")  # type: ignore[assignment]
    app._confidence_text = _FakeValue("Confidence: —")  # type: ignore[assignment]
    app._message_text = _FakeValue("")  # type: ignore[assignment]
    app._status_label = _FakeWidget()  # type: ignore[assignment]
    app._message_label = _FakeWidget()  # type: ignore[assignment]
    app._start_button = _FakeWidget()  # type: ignore[assignment]
    app._stop_button = _FakeWidget()  # type: ignore[assignment]
    return app


def form_values(**overrides: str | bool) -> dict[str, str | bool]:
    values: dict[str, str | bool] = {
        "x": "-12",
        "y": "34",
        "width": "640",
        "height": "360",
        "reference_image": "assets/villager icon.png",
        "confidence_threshold": "0.91",
        "polling_interval_ms": "175",
        "always_on_top": False,
        "warning_mode": "builtin",
        "warning_wav": "",
    }
    values.update(overrides)
    return values


def test_valid_mapping_preserves_exact_entered_values() -> None:
    values = form_values()

    settings = settings_from_values(values)

    assert settings.region.x == -12
    assert settings.region.y == 34
    assert settings.region.width == 640
    assert settings.region.height == 360
    assert settings.reference_image == "assets/villager icon.png"
    assert settings.confidence_threshold == 0.91
    assert settings.polling_interval_ms == 175
    assert settings.always_on_top is False
    assert settings.warning_mode == "builtin"
    assert settings.warning_wav == ""


def test_form_does_not_expose_obs_controls() -> None:
    obs_fields = {"capture_mode", "obs_port", "obs_source"}

    assert obs_fields.isdisjoint(app_module._FORM_FIELDS)


@pytest.mark.parametrize("field", ["x", "confidence_threshold", "polling_interval_ms"])
def test_invalid_numeric_input_is_a_concise_value_error(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        settings_from_values(form_values(**{field: "not-a-number"}))


def test_pydantic_range_failure_is_a_concise_value_error() -> None:
    with pytest.raises(ValueError, match="confidence_threshold"):
        settings_from_values(form_values(confidence_threshold="1.01"))


def test_custom_warning_requires_an_existing_wav(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_module, "PROJECT_ROOT", tmp_path)

    with pytest.raises(ValueError, match="existing .wav"):
        settings_from_values(
            form_values(warning_mode="custom", warning_wav="audio/missing.wav")
        )


def test_custom_warning_rejects_wrong_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_module, "PROJECT_ROOT", tmp_path)
    sound = tmp_path / "warning.mp3"
    sound.write_bytes(b"not audio")

    with pytest.raises(ValueError, match="existing .wav"):
        settings_from_values(
            form_values(warning_mode="custom", warning_wav=str(sound))
        )


def test_custom_warning_accepts_relative_existing_wav_without_rewriting_value(
    tmp_path: Path,
    wav_file_factory: Callable[[str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
    created = wav_file_factory("warning.wav")
    sound = tmp_path / "audio" / "warning.wav"
    sound.parent.mkdir()
    sound.write_bytes(created.read_bytes())

    settings = settings_from_values(
        form_values(warning_mode="custom", warning_wav="audio/warning.wav")
    )

    assert settings.warning_wav == "audio/warning.wav"


def test_custom_warning_rejects_malformed_wav(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_module, "PROJECT_ROOT", tmp_path)
    sound = tmp_path / "warning.wav"
    sound.write_bytes(b"RIFF")

    with pytest.raises(ValueError, match="valid WAV"):
        settings_from_values(
            form_values(warning_mode="custom", warning_wav=str(sound))
        )


@pytest.mark.parametrize("mode", ["builtin", "disabled"])
def test_non_custom_warning_modes_accept_an_empty_wav(mode: str) -> None:
    settings = settings_from_values(form_values(warning_mode=mode, warning_wav=""))

    assert settings.warning_mode == mode
    assert settings.warning_wav == ""


def test_entry_point_import_does_not_start_gui() -> None:
    import run

    assert run.main is app_module.main


def test_entry_point_qt_window_constructs_without_starting_event_loop(
    qapp: QApplication,
) -> None:
    from src_package.ui.main_window import MainWindow

    window = MainWindow()
    try:
        assert window.windowTitle() == "Villager Detector"
        assert QApplication.instance() is qapp
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()


def test_main_creates_shows_and_runs_the_qt_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import PySide6.QtWidgets as qt_widgets
    from src_package.ui import main_window as main_window_module
    from src_package.ui.theme import APP_STYLE_SHEET

    calls: list[object] = []

    class FakeApplication:
        @classmethod
        def instance(cls) -> None:
            calls.append("instance")
            return None

        def __init__(self, args: list[str]) -> None:
            calls.append(("construct", args))

        def setStyleSheet(self, stylesheet: str) -> None:
            calls.append(("stylesheet", stylesheet))

        def exec(self) -> int:
            calls.append("exec")
            return 23

    class FakeWindow:
        def __init__(self) -> None:
            calls.append("window")

        def show(self) -> None:
            calls.append("show")

    monkeypatch.setattr(qt_widgets, "QApplication", FakeApplication)
    monkeypatch.setattr(main_window_module, "MainWindow", FakeWindow)

    assert app_module.main() == 23
    assert calls == [
        "instance",
        ("construct", []),
        ("stylesheet", APP_STYLE_SHEET),
        "window",
        "show",
        "exec",
    ]


def test_queued_result_from_stopped_generation_is_ignored() -> None:
    app = bare_app()
    app._active_generation = 1
    app._events.put(
        app_module._ResultEvent(
            generation=1,
            result=app_module.DetectionResult(score=0.99, available=True),
        )
    )

    app._stop()
    app._poll_events()

    assert app._active_generation is None
    assert app._status_text.get() == "NOT MONITORING"
    assert app._confidence_text.get() == "Confidence: —"


def test_queued_error_from_replaced_generation_cannot_stop_current_monitor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = bare_app()
    current_monitor = object()
    app._monitor = current_monitor  # type: ignore[assignment]
    app._active_generation = 2
    app._status_text.set("MONITORING…")
    shown_errors: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        app_module.messagebox,
        "showerror",
        lambda *args, **kwargs: shown_errors.append(args),
    )
    app._events.put(app_module._ErrorEvent(generation=1, message="old failure"))

    app._poll_events()

    assert app._monitor is current_monitor
    assert app._active_generation == 2
    assert app._status_text.get() == "MONITORING…"
    assert shown_errors == []


def test_start_failure_restores_stopped_state_without_a_display(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = bare_app()
    app._validated_settings = lambda: AppSettings()  # type: ignore[method-assign]
    monkeypatch.setattr(app_module, "save_settings", lambda settings: None)
    monkeypatch.setattr(
        app_module, "describe_capture_geometry", lambda region: "Region (0, 0) 400x300"
    )
    shown_errors: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        app_module.messagebox,
        "showerror",
        lambda *args, **kwargs: shown_errors.append(args),
    )

    class FailingMonitor:
        stopped = False

        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def start(self) -> None:
            raise RuntimeError("thread unavailable")

        def stop(self, timeout: float = 1.0) -> bool:
            self.stopped = True
            return True

    fake_monitor_module = ModuleType("src_package.services.monitor")
    fake_monitor_module.DetectionMonitor = FailingMonitor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "src_package.services.monitor", fake_monitor_module)

    app._start()

    assert app._monitor is None
    assert app._active_generation is None
    assert app._status_text.get() == "NOT MONITORING"
    assert app._status_label.options["style"] == "Status.Neutral.TLabel"
    assert app._start_button.options["state"] == "normal"
    assert app._stop_button.options["state"] == "disabled"
    assert shown_errors == [("Start error", "thread unavailable")]


class _SlowMonitor:
    def __init__(self) -> None:
        self.running = True
        self.stop_calls = 0

    @property
    def is_running(self) -> bool:
        return self.running

    def stop(self, timeout: float = 1.0) -> bool:
        self.stop_calls += 1
        return not self.running


def test_incomplete_stop_retains_monitor_and_disables_restart_until_exit() -> None:
    app = bare_app()
    monitor = _SlowMonitor()
    app._monitor = monitor  # type: ignore[assignment]
    app._active_generation = 1

    assert app._stop() is False
    assert app._monitor is monitor
    assert app._status_text.get() == "STOPPING…"
    assert app._start_button.options["state"] == "disabled"
    assert app._stop_button.options["state"] == "disabled"

    app._validated_settings = lambda: pytest.fail("restart must remain blocked")  # type: ignore[method-assign]
    app._start()
    assert app._monitor is monitor
    assert monitor.stop_calls == 2

    monitor.running = False
    app._poll_events()

    assert app._monitor is None
    assert app._status_text.get() == "NOT MONITORING"
    assert app._start_button.options["state"] == "normal"


def test_close_waits_for_blocked_monitor_before_destroying_root() -> None:
    app = bare_app()
    monitor = _SlowMonitor()
    app._monitor = monitor  # type: ignore[assignment]

    app._on_close()

    assert app.root.destroyed is False  # type: ignore[attr-defined]
    assert app._monitor is monitor

    monitor.running = False
    app._poll_events()

    assert app.root.destroyed is True  # type: ignore[attr-defined]
    assert app._monitor is None


def test_active_warning_is_shown_as_a_non_fatal_message() -> None:
    app = bare_app()
    app._active_generation = 3
    app._monitor = _SlowMonitor()  # type: ignore[assignment]
    app._events.put(app_module._WarningEvent(generation=3, message="capture is black"))

    app._poll_events()

    assert app._message_text.get() == "capture is black"
    assert app._message_label.options["style"] == "Message.Warning.TLabel"
    assert app._monitor is not None
    assert app._active_generation == 3


def test_stale_warning_from_a_replaced_generation_is_ignored() -> None:
    app = bare_app()
    app._active_generation = 4
    app._monitor = _SlowMonitor()  # type: ignore[assignment]
    app._events.put(app_module._WarningEvent(generation=3, message="old warning"))

    app._poll_events()

    assert app._message_text.get() == ""


def test_stopping_clears_the_message_line() -> None:
    app = bare_app()
    app._message_text.set("capture is black")

    app._stop()

    assert app._message_text.get() == ""


def test_capture_probe_flags_a_black_frame_and_reports_the_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import numpy as np

    from src_package.services import template_matcher as matcher_module

    black = np.zeros((20, 30, 4), dtype=np.uint8)

    class FakeCapturer:
        def capture(self, region: Region) -> np.ndarray:
            return black

    class FakeMatcher:
        def __init__(self, path: Path, threshold: float) -> None:
            pass

        def match(self, frame: np.ndarray) -> app_module.DetectionResult:
            return app_module.DetectionResult(score=0.9, available=True)

    monkeypatch.setattr(app_module, "ScreenCapturer", FakeCapturer)
    monkeypatch.setattr(
        app_module, "describe_capture_geometry", lambda region: "Region on monitor 2"
    )
    monkeypatch.setattr(matcher_module, "TemplateMatcher", FakeMatcher)

    lines = app_module.capture_probe_lines(
        AppSettings(region=Region(x=0, y=0, width=30, height=20))
    )

    assert lines == [
        "Region on monitor 2",
        "Captured frame: 30x20 pixels",
        "The captured region is entirely black. GPU fullscreen capture was "
        "unavailable; try Borderless Fullscreen or windowed mode.",
        "Best match: 90.0% (threshold 85%)",
    ]


def test_capture_probe_omits_the_black_note_for_a_visible_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import numpy as np

    from src_package.services import template_matcher as matcher_module

    visible = np.full((20, 30, 4), 120, dtype=np.uint8)

    class FakeCapturer:
        def capture(self, region: Region) -> np.ndarray:
            return visible

    class FakeMatcher:
        def __init__(self, path: Path, threshold: float) -> None:
            pass

        def match(self, frame: np.ndarray) -> app_module.DetectionResult:
            return app_module.DetectionResult(score=0.42, available=False)

    monkeypatch.setattr(app_module, "ScreenCapturer", FakeCapturer)
    monkeypatch.setattr(app_module, "describe_capture_geometry", lambda region: "Region on monitor 2")
    monkeypatch.setattr(matcher_module, "TemplateMatcher", FakeMatcher)

    lines = app_module.capture_probe_lines(
        AppSettings(region=Region(x=0, y=0, width=30, height=20))
    )

    joined = "\n".join(lines)
    assert "entirely black" not in joined
    assert joined.endswith("Best match: 42.0% (threshold 85%)")
