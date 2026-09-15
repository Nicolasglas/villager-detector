"""Offscreen presentation tests for the settings drawer."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QObject, QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QScrollArea

from src_package.config import AppSettings, Region
from src_package.ui.settings_panel import SettingsPanel


@pytest.fixture
def initial() -> AppSettings:
    return AppSettings(
        region=Region(x=-12, y=34, width=640, height=360),
        reference_image="assets/villager icon.png",
        confidence_threshold=0.91,
        polling_interval_ms=175,
        always_on_top=False,
        warning_mode="builtin",
        warning_wav="",
    )


@pytest.fixture
def panel(qapp: QApplication, initial: AppSettings) -> SettingsPanel:
    widget = SettingsPanel(initial)
    widget.show()
    qapp.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    qapp.processEvents()


def test_all_ten_fields_are_present(panel: SettingsPanel) -> None:
    for name in (
        "xField", "yField", "widthField", "heightField", "referenceImageField",
        "confidenceThresholdField", "pollingIntervalField", "alwaysOnTopField",
        "warningModeField", "warningWavField",
    ):
        assert panel.findChild(QObject, name) is not None


def test_window_section_is_above_scrollable_details(panel: SettingsPanel) -> None:
    window_section = panel.findChild(QObject, "windowSection")
    detection_section = panel.findChild(QObject, "detectionSection")

    assert window_section is not None
    assert detection_section is not None
    assert window_section.geometry().top() < detection_section.geometry().top()


def test_detection_and_alerts_sections_stack_for_narrow_windows(panel: SettingsPanel) -> None:
    detection_section = panel.findChild(QObject, "detectionSection")
    alerts_section = panel.findChild(QObject, "alertsSection")

    assert detection_section is not None
    assert alerts_section is not None
    assert detection_section.geometry().top() < alerts_section.geometry().top()


def test_initial_app_settings_values_are_loaded(panel: SettingsPanel) -> None:
    assert panel.x.value() == -12
    assert panel.y.value() == 34
    assert panel.width.value() == 640
    assert panel.height.value() == 360
    assert panel.reference_image.findChild(QObject, "referenceImageField").text() == "assets/villager icon.png"  # type: ignore[union-attr]
    assert panel.confidence_threshold.value() == pytest.approx(0.91)
    assert panel.polling_interval_ms.value() == 175
    assert not panel.always_on_top.isChecked()
    assert panel.warning_mode.currentData() == "builtin"
    assert panel.warning_wav.findChild(QObject, "warningWavField").text() == ""  # type: ignore[union-attr]


def test_valid_values_round_trip_through_existing_parser(panel: SettingsPanel) -> None:
    settings = panel.current_settings()
    assert settings == AppSettings(
        region=Region(x=-12, y=34, width=640, height=360),
        reference_image="assets/villager icon.png",
        confidence_threshold=0.91,
        polling_interval_ms=175,
        always_on_top=False,
        warning_mode="builtin",
        warning_wav="",
    )


def test_invalid_numeric_value_shows_error_and_does_not_emit_saved(panel: SettingsPanel) -> None:
    saved: list[AppSettings] = []
    panel.saved.connect(saved.append)
    panel.x.lineEdit().setText("not-a-number")

    panel.save_button.click()

    assert not saved
    assert panel.validation_error.isVisible()
    assert "x:" in panel.validation_error.text()


def test_invalid_custom_wav_shows_error_and_does_not_emit_saved(panel: SettingsPanel) -> None:
    saved: list[AppSettings] = []
    panel.saved.connect(saved.append)
    panel.warning_mode.setCurrentIndex(panel.warning_mode.findData("custom"))
    panel.warning_wav.findChild(QObject, "warningWavField").setText("missing.wav")  # type: ignore[union-attr]

    panel.save_button.click()

    assert not saved
    assert panel.validation_error.isVisible()
    assert "warning_wav:" in panel.validation_error.text()


def test_valid_save_emits_app_settings_and_clears_error(panel: SettingsPanel) -> None:
    saved: list[AppSettings] = []
    panel.saved.connect(saved.append)
    panel.x.lineEdit().setText("-12")
    panel.save_button.click()

    assert saved and isinstance(saved[0], AppSettings)
    assert saved[0].region.x == -12
    assert not panel.validation_error.isVisible()


def test_valid_test_capture_emits_app_settings(panel: SettingsPanel) -> None:
    requested: list[AppSettings] = []
    panel.test_capture_requested.connect(requested.append)

    panel.test_capture_button.click()

    assert len(requested) == 1
    assert requested[0].reference_image == "assets/villager icon.png"


def test_close_emits_closed(panel: SettingsPanel) -> None:
    closed: list[bool] = []
    panel.closed.connect(lambda: closed.append(True))

    panel.close_button.click()

    assert closed == [True]

def test_select_region_emits_signal_without_capture(panel: SettingsPanel) -> None:
    selected: list[bool] = []
    panel.select_region_requested.connect(lambda: selected.append(True))

    panel.select_region_button.click()

    assert selected == [True]


def test_browsing_warning_wav_selects_custom_mode(
    panel: SettingsPanel, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = "C:/audio/custom.wav"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (selected, "WAV files (*.wav)"))

    panel.warning_wav.findChild(QObject, "warningWavFieldBrowseButton").click()  # type: ignore[union-attr]

    assert panel.warning_wav.findChild(QObject, "warningWavField").text() == selected  # type: ignore[union-attr]
    assert panel.warning_mode.currentData() == "custom"


def _wheel_event(delta: int = 120) -> QWheelEvent:
    return QWheelEvent(
        QPointF(2, 2),
        QPointF(2, 2),
        QPoint(0, 0),
        QPoint(0, delta),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


def test_wheel_over_numeric_fields_does_not_change_values(panel: SettingsPanel) -> None:
    for field in (panel.x, panel.confidence_threshold):
        original = field.value()
        QApplication.sendEvent(field, _wheel_event())
        assert field.value() == original


def test_wheel_over_combo_field_does_not_change_value(panel: SettingsPanel) -> None:
    original = panel.warning_mode.currentData()

    QApplication.sendEvent(panel.warning_mode, _wheel_event())

    assert panel.warning_mode.currentData() == original


def test_settings_panel_has_scroll_container(panel: SettingsPanel) -> None:
    scroll_area = panel.findChild(QScrollArea, "settingsScrollArea")

    assert scroll_area is not None
    assert scroll_area.widgetResizable()
    assert scroll_area.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert panel.minimumSize().isEmpty()


def test_keyboard_editing_and_stepping_still_work_after_wheel_override(panel: SettingsPanel) -> None:
    panel.x.setValue(34)
    panel.x.lineEdit().selectAll()
    QTest.keyClicks(panel.x.lineEdit(), "99")
    assert panel.x.value() == 99

    panel.x.setFocus()
    QTest.keyClick(panel.x, Qt.Key.Key_Up)
    assert panel.x.value() == 100
