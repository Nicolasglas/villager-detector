"""PySide6 main window integrating the detector UI and monitor lifecycle."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QPoint, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src_package.app import capture_probe_lines, load_settings, save_settings
from src_package.config import AppSettings, Region
from src_package.models import DetectionResult
from src_package.services.monitor import DetectionMonitor
from src_package.ui.region_selector import RegionSelector
from src_package.ui.settings_panel import SettingsPanel
from src_package.ui.status_widget import StatusWidget
from src_package.ui.theme import ACCENT_BLUE, PRIMARY_TEXT, SHELL_MARGIN, SURFACE_PADDING

_UI_STOP_TIMEOUT_SECONDS = 0.05


@dataclass(frozen=True, slots=True)
class _ResultEvent:
    generation: int
    result: DetectionResult


@dataclass(frozen=True, slots=True)
class _WarningEvent:
    generation: int
    message: str


@dataclass(frozen=True, slots=True)
class _ErrorEvent:
    generation: int
    message: str


class _MonitorSignals(QObject):
    """Cross-thread boundary for monitor callbacks."""

    result = Signal(object)
    warning = Signal(object)
    error = Signal(object)


class MainWindow(QMainWindow):
    """Own the presentation widgets and safely control one monitor at a time."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mainWindow")
        self.setWindowTitle("Villager Detector")
        self.setMinimumSize(0, 0)
        self._monitor: DetectionMonitor | None = None
        self._next_generation = 0
        self._active_generation: int | None = None
        self._closing = False
        self._pending_error: str | None = None
        self._signals = _MonitorSignals(self)
        self._signals.result.connect(self._on_result_event, Qt.ConnectionType.QueuedConnection)
        self._signals.warning.connect(self._on_warning_event, Qt.ConnectionType.QueuedConnection)
        self._signals.error.connect(self._on_error_event, Qt.ConnectionType.QueuedConnection)
        self._stop_timer = QTimer(self)
        self._stop_timer.setInterval(25)
        self._stop_timer.timeout.connect(self._finish_pending_stop)

        try:
            initial = load_settings()
            self._settings_load_error = ""
        except (OSError, ValueError) as exc:
            initial = AppSettings()
            self._settings_load_error = str(exc)

        self.status_widget = StatusWidget(self)
        self.settings_panel = SettingsPanel(initial, self)
        self.settings_panel.hide()
        self.region_selector: RegionSelector | None = None
        self._build_ui()
        self.settings_panel.saved.connect(self._save_settings)
        self.settings_panel.closed.connect(self.close_settings)
        self.settings_panel.test_capture_requested.connect(self._test_capture)
        self.settings_panel.select_region_requested.connect(self._select_region)
        self._apply_always_on_top(initial.always_on_top)
        if self._settings_load_error:
            QMessageBox.critical(self, "Settings error", f"Could not load settings: {self._settings_load_error}")

    def _build_ui(self) -> None:
        shell = QWidget(self)
        shell.setObjectName("shell")
        outer = QVBoxLayout(shell)
        outer.setContentsMargins(SHELL_MARGIN, 14, SHELL_MARGIN, SHELL_MARGIN)
        outer.setSpacing(12)

        title_bar = QHBoxLayout()
        feather = QLabel("✦")
        feather.setAccessibleName("Villager Detector mark")
        feather.setStyleSheet(f"color: {ACCENT_BLUE}; font-size: 22px; font-weight: 700;")
        title = QLabel("Villager Detector")
        title.setStyleSheet(f"color: {PRIMARY_TEXT}; font-size: 17px; font-weight: 700;")
        title_bar.addWidget(feather)
        title_bar.addWidget(title)
        title_bar.addStretch()
        outer.addLayout(title_bar)

        surface = QFrame()
        surface.setObjectName("contentSurface")
        surface_layout = QVBoxLayout(surface)
        surface_layout.setContentsMargins(SURFACE_PADDING, 16, SURFACE_PADDING, SURFACE_PADDING)
        surface_layout.setSpacing(14)
        surface_header = QHBoxLayout()
        surface_header.addStretch()
        self.settings_button = QPushButton("⚙")
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.setAccessibleName("Open settings")
        self.settings_button.setToolTip("Open settings")
        self.settings_button.clicked.connect(self.open_settings)
        surface_header.addWidget(self.settings_button)
        surface_layout.addLayout(surface_header)
        surface_layout.addWidget(self.status_widget, 1)
        controls = QHBoxLayout()
        self.start_button = QPushButton("Start monitoring")
        self.start_button.setObjectName("startButton")
        self.start_button.setAccessibleName("Start monitoring")
        self.start_button.clicked.connect(self.start_monitoring)
        self.stop_button = QPushButton("Stop monitoring")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setAccessibleName("Stop monitoring")
        self.stop_button.clicked.connect(self.stop_monitoring)
        self.stop_button.setEnabled(False)
        controls.setSpacing(12)
        controls.addWidget(self.start_button, 1)
        controls.addWidget(self.stop_button, 1)
        surface_layout.addLayout(controls)
        outer.addWidget(surface, 1)
        self._content_surface = surface
        self.setCentralWidget(shell)
        self._position_settings_panel()

    def open_settings(self) -> None:
        self._position_settings_panel()
        self.settings_panel.show()
        self.settings_panel.raise_()

    def close_settings(self) -> None:
        self.settings_panel.hide()

    def _position_settings_panel(self) -> None:
        """Keep the drawer inside the content surface as the window changes."""
        if not hasattr(self, "_content_surface"):
            return
        origin = self._content_surface.mapTo(self, QPoint(0, 0))
        available = self._content_surface.height()
        width = self._content_surface.width()
        self.settings_panel.setGeometry(
            origin.x(),
            origin.y(),
            width,
            available,
        )

    def resizeEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        self._position_settings_panel()
        super().resizeEvent(event)  # type: ignore[arg-type]

    def _save_settings(self, settings: AppSettings) -> None:
        try:
            save_settings(settings)
        except OSError as exc:
            QMessageBox.critical(self, "Save error", f"Could not save settings: {exc}")
            return
        self._apply_always_on_top(settings.always_on_top)
        self.close_settings()

    def _apply_always_on_top(self, enabled: bool) -> None:
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        if self.isVisible():
            self.show()

    def start_monitoring(self) -> None:
        if self._monitor is not None:
            if not self.stop_monitoring():
                return
        try:
            settings = self.settings_panel.validate_current_settings()
        except ValueError:
            self.open_settings()
            return
        if settings is None:
            self.open_settings()
            return
        try:
            save_settings(settings)
        except OSError as exc:
            QMessageBox.critical(self, "Start error", f"Could not save settings: {exc}")
            return

        self._next_generation += 1
        generation = self._next_generation
        try:
            monitor = DetectionMonitor(
                settings,
                lambda result, gen=generation: self._signals.result.emit(_ResultEvent(gen, result)),
                lambda message, gen=generation: self._signals.error.emit(_ErrorEvent(gen, message)),
                on_warning=lambda message, gen=generation: self._signals.warning.emit(_WarningEvent(gen, message)),
            )
        except (OSError, ValueError, RuntimeError, ImportError) as exc:
            QMessageBox.critical(self, "Start error", str(exc))
            return
        self._monitor = monitor
        self._active_generation = generation
        self._pending_error = None
        self.status_widget.set_monitoring()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        try:
            monitor.start()
        except Exception as exc:
            self._active_generation = None
            self._stop_or_wait(monitor)
            QMessageBox.critical(self, "Start error", str(exc))

    def stop_monitoring(self) -> bool:
        self._active_generation = None
        monitor = self._monitor
        if monitor is None:
            self._set_stopped()
            return True
        return self._stop_or_wait(monitor)

    def _stop_or_wait(self, monitor: DetectionMonitor) -> bool:
        try:
            stopped = monitor.stop(timeout=_UI_STOP_TIMEOUT_SECONDS)
        except Exception as exc:
            stopped = True
            self._pending_error = str(exc)
        if stopped:
            if self._monitor is monitor:
                self._monitor = None
            if self._pending_error:
                self.status_widget.set_error(self._pending_error)
                self._pending_error = None
                self.start_button.setEnabled(True)
                self.stop_button.setEnabled(False)
            else:
                self._set_stopped()
            return True
        self.status_widget.set_stopping()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        if not self._stop_timer.isActive():
            self._stop_timer.start()
        return False

    def _finish_pending_stop(self) -> None:
        monitor = self._monitor
        if monitor is None:
            self._stop_timer.stop()
            self._set_stopped()
            self._destroy_if_closing()
            return
        if monitor.is_running:
            return
        self._stop_timer.stop()
        self._monitor = None
        if self._pending_error:
            self.status_widget.set_error(self._pending_error)
            self._pending_error = None
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
        else:
            self._set_stopped()
        self._destroy_if_closing()

    def _set_stopped(self) -> None:
        self.status_widget.set_not_monitoring()
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self._destroy_if_closing()

    def _destroy_if_closing(self) -> None:
        if self._closing and self._monitor is None:
            self._stop_timer.stop()
            self.close()
            self.deleteLater()

    def _on_result_event(self, event: _ResultEvent) -> None:
        if event.generation == self._active_generation:
            self.status_widget.set_result(event.result)

    def _on_warning_event(self, event: _WarningEvent) -> None:
        if event.generation == self._active_generation:
            self.status_widget.description_label.setText(event.message)

    def _on_error_event(self, event: _ErrorEvent) -> None:
        if event.generation != self._active_generation:
            return
        self._active_generation = None
        self._pending_error = event.message
        monitor = self._monitor
        if monitor is None:
            self._pending_error = None
            self.status_widget.set_error(event.message)
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            return
        self._stop_or_wait(monitor)

    def _test_capture(self, settings: AppSettings) -> None:
        try:
            lines = capture_probe_lines(settings)
        except Exception as exc:
            QMessageBox.critical(self, "Test capture failed", str(exc))
            return
        QMessageBox.information(self, "Test capture", "\n".join(lines))

    def _select_region(self) -> None:
        selector = RegionSelector(self)
        self.region_selector = selector
        region = selector.exec_selection()
        if region is not None:
            self.settings_panel.x.setValue(region.x)
            self.settings_panel.y.setValue(region.y)
            self.settings_panel.width.setValue(region.width)
            self.settings_panel.height.setValue(region.height)

    def closeEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        self._closing = True
        if self._monitor is None:
            event.accept()  # type: ignore[union-attr]
            return
        if self.stop_monitoring():
            event.accept()  # type: ignore[union-attr]
        else:
            event.ignore()  # type: ignore[union-attr]


__all__ = ["MainWindow"]
