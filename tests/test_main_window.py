"""Offscreen integration tests for the PySide6 main window."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from src_package.config import AppSettings, Region
from src_package.models import DetectionResult
from src_package.ui import main_window as module
from src_package.ui.main_window import MainWindow


@pytest.fixture
def window(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> MainWindow:
    monkeypatch.setattr(module, "load_settings", lambda: AppSettings())
    widget = MainWindow()
    widget.show()
    qapp.processEvents()
    yield widget
    widget._monitor = None
    widget.close()
    widget.deleteLater()
    qapp.processEvents()


class FakeMonitor:
    instances: list["FakeMonitor"] = []

    def __init__(self, settings: AppSettings, on_result, on_error, *, on_warning=None):
        self.settings = settings
        self.on_result = on_result
        self.on_error = on_error
        self.on_warning = on_warning
        self.running = False
        self.stop_result = True
        self.started = False
        self.__class__.instances.append(self)

    @property
    def is_running(self) -> bool:
        return self.running

    def start(self) -> None:
        self.started = True
        self.running = True

    def stop(self, timeout: float = 1.0) -> bool:
        if self.stop_result:
            self.running = False
        return self.stop_result


def test_constructs_with_defaults_and_drawer_is_hidden(window: MainWindow) -> None:
    assert window.settings_panel.parent() is window
    assert not window.settings_panel.isWindow()
    assert window.settings_panel.isHidden()
    assert window.settings_panel.x.value() == 0
    assert window.status_widget.heading_label.text() == "Not monitoring"


def test_cog_and_close_toggle_drawer(window: MainWindow) -> None:
    assert window.settings_button.parent() is window._content_surface
    window.settings_button.click()
    assert window.settings_panel.isVisible()
    surface_rect = window._content_surface.rect()
    assert window.settings_panel.geometry().right() <= surface_rect.right() + window._content_surface.mapTo(window, surface_rect.topLeft()).x()
    window.close_settings()
    assert window.settings_panel.isHidden()


def test_drawer_repositions_with_main_window_resize(window: MainWindow) -> None:
    window.resize(900, 700)
    QApplication.processEvents()
    window.open_settings()
    first = window.settings_panel.geometry()
    window.resize(1100, 760)
    QApplication.processEvents()
    second = window.settings_panel.geometry()
    assert second.x() == first.x()
    assert second.width() > first.width()
    assert second.height() != 0
    assert second.right() <= window.width()


def test_settings_drawer_uses_the_full_content_surface_width(window: MainWindow) -> None:
    window.open_settings()

    assert window.settings_panel.geometry().width() == window._content_surface.geometry().width()


def test_primary_controls_have_accessible_names(window: MainWindow) -> None:
    assert window.start_button.accessibleName() == "Start monitoring"
    assert window.stop_button.accessibleName() == "Stop monitoring"


def test_start_validates_saves_constructs_and_starts(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    saved: list[AppSettings] = []
    monkeypatch.setattr(module, "save_settings", saved.append)
    FakeMonitor.instances.clear()
    monkeypatch.setattr(module, "DetectionMonitor", FakeMonitor)
    window.start_monitoring()
    assert len(saved) == 1
    assert FakeMonitor.instances[0].started
    assert window.stop_button.isEnabled()


def test_start_invalid_form_shows_inline_validation(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "save_settings", lambda settings: pytest.fail("invalid settings were saved"))
    window.settings_panel.x.lineEdit().setText("not-a-number")
    window.start_monitoring()
    assert window.settings_panel.validation_error.isVisible()
    assert "x:" in window.settings_panel.validation_error.text()


def test_result_updates_status(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "save_settings", lambda settings: None)
    monkeypatch.setattr(module, "DetectionMonitor", FakeMonitor)
    FakeMonitor.instances.clear()
    window.start_monitoring()
    monitor = FakeMonitor.instances[0]
    monitor.on_result(DetectionResult(score=0.93, available=True))
    QApplication.processEvents()
    assert window.status_widget.heading_label.text() == "Villager available"
    assert "93.0%" in window.status_widget.confidence_label.text()


def test_warning_is_non_fatal(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "save_settings", lambda settings: None)
    monkeypatch.setattr(module, "DetectionMonitor", FakeMonitor)
    FakeMonitor.instances.clear()
    window.start_monitoring()
    monitor = FakeMonitor.instances[0]
    monitor.on_warning("capture is black")
    QApplication.processEvents()
    assert window.status_widget.description_label.text() == "capture is black"
    assert window._monitor is monitor


def test_stale_generation_event_is_ignored(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "save_settings", lambda settings: None)
    monkeypatch.setattr(module, "DetectionMonitor", FakeMonitor)
    FakeMonitor.instances.clear()
    window.start_monitoring()
    generation = window._active_generation
    window._on_result_event(module._ResultEvent(generation - 1, DetectionResult(1, True)))  # type: ignore[operator]
    assert window.status_widget.heading_label.text() == "Monitoring"


def test_stop_enters_stopping_then_stopped(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "save_settings", lambda settings: None)
    monkeypatch.setattr(module, "DetectionMonitor", FakeMonitor)
    FakeMonitor.instances.clear()
    window.start_monitoring()
    monitor = FakeMonitor.instances[0]
    monitor.stop_result = False
    assert window.stop_monitoring() is False
    assert window.status_widget.heading_label.text() == "Stopping"
    monitor.stop_result = True
    monitor.running = False
    window._finish_pending_stop()
    assert window.status_widget.heading_label.text() == "Not monitoring"


def test_error_stops_and_displays_error(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "save_settings", lambda settings: None)
    monkeypatch.setattr(module, "DetectionMonitor", FakeMonitor)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: QMessageBox.StandardButton.Ok)
    FakeMonitor.instances.clear()
    window.start_monitoring()
    monitor = FakeMonitor.instances[0]
    monitor.on_error("broken capture")
    QApplication.processEvents()
    assert window.status_widget.heading_label.text() == "Detection stopped"
    assert not monitor.running


def test_test_capture_uses_existing_helper(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[AppSettings] = []
    monkeypatch.setattr(module, "capture_probe_lines", lambda settings: calls.append(settings) or ["probe ok"])
    monkeypatch.setattr(QMessageBox, "information", lambda *args: QMessageBox.StandardButton.Ok)
    window.open_settings()
    window.settings_panel.test_capture_button.click()
    assert len(calls) == 1


def test_region_selection_updates_fields(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSelector:
        def __init__(self, parent):
            pass
        def exec_selection(self):
            return Region(x=-3, y=4, width=50, height=60)
    monkeypatch.setattr(module, "RegionSelector", FakeSelector)
    window.open_settings()
    window.settings_panel.select_region_button.click()
    assert (window.settings_panel.x.value(), window.settings_panel.y.value()) == (-3, 4)
    assert (window.settings_panel.width.value(), window.settings_panel.height.value()) == (50, 60)


def test_blocked_close_waits_without_destroying(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "save_settings", lambda settings: None)
    monkeypatch.setattr(module, "DetectionMonitor", FakeMonitor)
    FakeMonitor.instances.clear()
    window.start_monitoring()
    monitor = FakeMonitor.instances[0]
    monitor.stop_result = False
    window.close()
    assert not window.isHidden()
    monitor.running = False
    window._finish_pending_stop()
    assert window._monitor is None


def test_always_on_top_flag_follows_settings(window: MainWindow) -> None:
    assert bool(window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    window.settings_panel.always_on_top.setChecked(False)
    window._apply_always_on_top(False)
    assert not bool(window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)


def test_startup_load_failure_keeps_defaults_and_reports_error(monkeypatch: pytest.MonkeyPatch, qapp: QApplication) -> None:
    monkeypatch.setattr(module, "load_settings", lambda: (_ for _ in ()).throw(OSError("settings unreadable")))
    messages: list[str] = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: messages.append(str(args[2])) or QMessageBox.StandardButton.Ok)
    widget = MainWindow()
    try:
        assert widget.settings_panel.x.value() == 0
        assert messages and "settings unreadable" in messages[0]
    finally:
        widget.close()
        widget.deleteLater()
        qapp.processEvents()


def test_save_failure_is_reported_and_drawer_remains_open(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(module, "save_settings", lambda settings: (_ for _ in ()).throw(OSError("disk full")))
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: messages.append(str(args[2])) or QMessageBox.StandardButton.Ok)
    window.open_settings()
    window.settings_panel.save_button.click()
    assert messages and "disk full" in messages[0]
    assert window.settings_panel.isVisible()


def test_monitor_start_failure_is_reported_and_monitor_is_stopped(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingMonitor(FakeMonitor):
        def start(self) -> None:
            raise RuntimeError("thread could not start")

    monkeypatch.setattr(module, "save_settings", lambda settings: None)
    monkeypatch.setattr(module, "DetectionMonitor", FailingMonitor)
    messages: list[str] = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: messages.append(str(args[2])) or QMessageBox.StandardButton.Ok)
    window.start_monitoring()
    assert messages and "thread could not start" in messages[0]
    assert window._monitor is None
