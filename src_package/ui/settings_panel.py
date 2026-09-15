"""Presentation-only settings drawer for the detector configuration."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,

    QGroupBox,
    QHBoxLayout,
    QLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src_package.app import settings_from_values
from src_package.config import AppSettings
from src_package.ui.theme import (
    ACCENT_BLUE,
    BORDER,
    GROUP_BOX_RADIUS,
    PRIMARY_TEXT,
    SECONDARY_TEXT,
    SURFACE,
    VALIDATION_ERROR,
)


class _WheelPassthroughMixin:
    """Leave wheel events for the settings scroll area to consume."""

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt API
        event.ignore()


class _ScrollFriendlySpinBox(_WheelPassthroughMixin, QSpinBox):
    pass


class _ScrollFriendlyDoubleSpinBox(_WheelPassthroughMixin, QDoubleSpinBox):
    pass


class _ScrollFriendlyComboBox(_WheelPassthroughMixin, QComboBox):
    pass


class SettingsPanel(QWidget):
    """A validated, scrollable right-side settings drawer.

    The panel owns no detector or screen-capture behavior. Its action signals
    are handled by the main window.
    """

    saved = Signal(AppSettings)
    closed = Signal()
    test_capture_requested = Signal(AppSettings)
    select_region_requested = Signal()

    def __init__(self, initial_settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPanel")
        self.setWindowTitle("Settings")
        self.setAccessibleName("Detector settings")
        self.setMinimumSize(0, 0)
        self._build_ui(initial_settings)

    def _build_ui(self, initial: AppSettings) -> None:
        outer = QVBoxLayout(self)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(14)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        title = QLabel("Settings")
        title.setObjectName("settingsTitle")
        title.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {PRIMARY_TEXT};")
        title_block.addWidget(title)
        subtitle = QLabel("Tune detection, alerts, and window behavior")
        subtitle.setObjectName("settingsSubtitle")
        subtitle.setStyleSheet(f"color: {SECONDARY_TEXT};")
        title_block.addWidget(subtitle)
        header.addLayout(title_block)
        header.addStretch()
        self.close_button = QPushButton("Close")
        self.close_button.setObjectName("closeButton")
        self.close_button.setAccessibleName("Close settings")
        self.close_button.clicked.connect(self.closed)
        header.addWidget(self.close_button)
        outer.addLayout(header)

        self.validation_error = QLabel("")
        self.validation_error.setObjectName("validationError")
        self.validation_error.setAccessibleName("Settings validation error")
        self.validation_error.setWordWrap(True)
        self.validation_error.setStyleSheet(f"color: {VALIDATION_ERROR}; font-weight: 600;")
        self.validation_error.hide()
        outer.addWidget(self.validation_error)

        content = QWidget()
        content.setObjectName("settingsContent")
        form = QVBoxLayout(content)
        form.setContentsMargins(2, 2, 2, 2)
        form.setSpacing(12)

        window = self._section("Window", "windowSection")
        window_form = self._form(window)
        self.always_on_top = QCheckBox("Keep detector window above other windows")
        self.always_on_top.setObjectName("alwaysOnTopField")
        self.always_on_top.setAccessibleName("Always on top")
        window_form.addWidget(self.always_on_top)
        form.addWidget(window)

        detection = self._section("Detection", "detectionSection")
        detection_form = self._form(detection)
        self.x = self._spin("xField", -1000000, 1000000)
        self.y = self._spin("yField", -1000000, 1000000)
        self.width = self._spin("widthField", -1000000, 1000000)
        self.height = self._spin("heightField", -1000000, 1000000)
        self.reference_image = self._path_row("referenceImageField", "Browse reference image")
        for label, widget in (("X", self.x), ("Y", self.y), ("Width", self.width), ("Height", self.height), ("Reference image", self.reference_image)):
            detection_form.addWidget(self._labeled(label, widget))

        capture = self._section("Capture region", "captureRegionSection")
        capture_form = self._form(capture)
        self.select_region_button = QPushButton("Select Region")
        self.select_region_button.setObjectName("selectRegionButton")
        self.select_region_button.setAccessibleName("Select capture region")
        self.select_region_button.clicked.connect(self.select_region_requested)
        capture_form.addWidget(self.select_region_button)
        form.addWidget(capture)

        alerts = self._section("Alerts", "alertsSection")
        alerts_form = self._form(alerts)
        self.confidence_threshold = _ScrollFriendlyDoubleSpinBox()
        self.confidence_threshold.setObjectName("confidenceThresholdField")
        self.confidence_threshold.setAccessibleName("Confidence threshold")
        self.confidence_threshold.setRange(-1_000_000.0, 1_000_000.0)
        self.confidence_threshold.setDecimals(6)
        self.confidence_threshold.setSingleStep(0.01)
        self.polling_interval_ms = self._spin("pollingIntervalField", -1000000, 1000000)
        self.warning_mode = _ScrollFriendlyComboBox()
        self.warning_mode.setObjectName("warningModeField")
        self.warning_mode.setAccessibleName("Warning mode")
        self.warning_mode.addItem("Disabled", "disabled")
        self.warning_mode.addItem("Built-in", "builtin")
        self.warning_mode.addItem("Custom", "custom")
        self.warning_wav = self._path_row("warningWavField", "Browse warning WAV")
        warning_browse = self.warning_wav.findChild(QPushButton, "warningWavFieldBrowseButton")
        if warning_browse is not None:
            warning_browse.clicked.connect(self._use_custom_warning_mode)
        alerts_form.addWidget(self._labeled("Confidence threshold", self.confidence_threshold))
        alerts_form.addWidget(self._labeled("Polling interval (ms)", self.polling_interval_ms))
        alerts_form.addWidget(self._labeled("Warning mode", self.warning_mode))
        alerts_form.addWidget(self._labeled("Warning WAV", self.warning_wav))

        form.addWidget(detection)
        form.addWidget(alerts)

        form.addWidget(capture)
        form.addStretch()
        scroll_area = QScrollArea()
        scroll_area.setObjectName("settingsScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setWidget(content)
        outer.addWidget(scroll_area, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        self.test_capture_button = QPushButton("Test Capture")
        self.test_capture_button.setObjectName("testCaptureButton")
        self.test_capture_button.setAccessibleName("Test capture")
        self.test_capture_button.clicked.connect(self._test_capture)
        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("saveButton")
        self.save_button.setAccessibleName("Save settings")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._save)
        actions.addWidget(self.test_capture_button)
        actions.addWidget(self.save_button)
        outer.addLayout(actions)
        self._set_values(initial)

    @staticmethod
    def _section(title: str, object_name: str) -> QGroupBox:
        box = QGroupBox(title)
        box.setObjectName(object_name)
        box.setStyleSheet(
            f"QGroupBox {{ background: {SURFACE}; border: 1px solid {BORDER}; "
            f"border-radius: {GROUP_BOX_RADIUS}px; margin-top: 10px; padding: 12px 12px 10px; }}"
            f"QGroupBox::title {{ color: {PRIMARY_TEXT}; subcontrol-origin: margin; "
            f"left: 10px; padding: 0 4px; font-weight: 700; }}"
        )
        return box

    @staticmethod
    def _form(parent: QWidget) -> QVBoxLayout:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        return layout

    @staticmethod
    def _labeled(label: str, field: QWidget) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        caption = QLabel(label)
        caption.setObjectName(field.objectName() + "Label")
        caption.setStyleSheet(f"color: {SECONDARY_TEXT};")
        layout.addWidget(caption)
        layout.addWidget(field)
        return wrapper

    @staticmethod
    def _spin(name: str, minimum: int, maximum: int) -> QSpinBox:
        field = _ScrollFriendlySpinBox()
        field.setObjectName(name)
        field.setAccessibleName(name.removesuffix("Field").replace("_", " ").title())
        field.setRange(minimum, maximum)
        return field

    @staticmethod
    def _path_row(name: str, dialog_title: str) -> QWidget:
        row = QWidget()
        row.setObjectName(name + "Row")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        field = QLineEdit()
        field.setObjectName(name)
        field.setAccessibleName(name.removesuffix("Field").replace("_", " ").title())
        browse = QPushButton("Browse")
        browse.setObjectName(name + "BrowseButton")
        browse.setAccessibleName(dialog_title)
        browse.clicked.connect(lambda: SettingsPanel._browse_into(field, dialog_title))
        layout.addWidget(field, 1)
        layout.addWidget(browse)
        return row

    @staticmethod
    def _browse_into(field: QLineEdit, title: str) -> None:
        selected, _ = QFileDialog.getOpenFileName(field, title)
        if selected:
            field.setText(selected)

    def _use_custom_warning_mode(self) -> None:
        """Make selecting a warning file activate that file as the alert source."""
        self.warning_mode.setCurrentIndex(self.warning_mode.findData("custom"))

    def _set_values(self, settings: AppSettings) -> None:
        self.x.setValue(settings.region.x)
        self.y.setValue(settings.region.y)
        self.width.setValue(settings.region.width)
        self.height.setValue(settings.region.height)
        self.reference_image.findChild(QLineEdit).setText(settings.reference_image)  # type: ignore[union-attr]
        self.confidence_threshold.setValue(settings.confidence_threshold)
        self.polling_interval_ms.setValue(settings.polling_interval_ms)
        self.always_on_top.setChecked(settings.always_on_top)
        self.warning_mode.setCurrentIndex(self.warning_mode.findData(settings.warning_mode))
        self.warning_wav.findChild(QLineEdit).setText(settings.warning_wav)  # type: ignore[union-attr]

    @staticmethod
    def _text(field: QWidget) -> str:
        if isinstance(field, (QSpinBox, QDoubleSpinBox)):
            return field.lineEdit().text()
        if isinstance(field, QLineEdit):
            return field.text()
        raise TypeError(f"Unsupported field: {field!r}")

    def _form_values(self) -> dict[str, str | bool]:
        return {
            "x": self._text(self.x),
            "y": self._text(self.y),
            "width": self._text(self.width),
            "height": self._text(self.height),
            "reference_image": self.reference_image.findChild(QLineEdit).text(),  # type: ignore[union-attr]
            "confidence_threshold": self._text(self.confidence_threshold),
            "polling_interval_ms": self._text(self.polling_interval_ms),
            "always_on_top": self.always_on_top.isChecked(),
            "warning_mode": self.warning_mode.currentData(),
            "warning_wav": self.warning_wav.findChild(QLineEdit).text(),  # type: ignore[union-attr]
        }

    def current_settings(self) -> AppSettings:
        return settings_from_values(self._form_values())

    def validate_current_settings(self) -> AppSettings | None:
        """Validate the visible form and show any error inline."""
        return self._validate()

    def _validate(self) -> AppSettings | None:
        try:
            settings = self.current_settings()
        except ValueError as exc:
            self.validation_error.setText(str(exc))
            self.validation_error.show()
            return None
        self.validation_error.clear()
        self.validation_error.hide()
        return settings

    def _save(self) -> None:
        settings = self._validate()
        if settings is not None:
            self.saved.emit(settings)

    def _test_capture(self) -> None:
        settings = self._validate()
        if settings is not None:
            self.test_capture_requested.emit(settings)


__all__ = ["SettingsPanel"]
