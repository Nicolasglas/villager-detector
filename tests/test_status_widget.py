"""Focused presentation tests for StatusWidget."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from src_package.models import DetectionResult
from src_package.ui.status_widget import StatusWidget


@pytest.fixture
def widget(qapp: QApplication) -> StatusWidget:
    status = StatusWidget()
    status.show()
    qapp.processEvents()
    yield status
    status.close()
    status.deleteLater()
    qapp.processEvents()


def text(widget: StatusWidget) -> tuple[str, str, str]:
    return (
        widget.heading_label.text(),
        widget.description_label.text(),
        widget.confidence_label.text(),
    )


def test_construction_has_accessible_named_parts(widget: StatusWidget) -> None:
    assert widget.objectName() == "statusWidget"
    assert widget.icon.objectName() == "statusIcon"
    assert widget.heading_label.objectName() == "statusHeading"
    assert widget.description_label.objectName() == "statusDescription"
    assert widget.confidence_label.objectName() == "statusConfidence"
    assert text(widget) == ("Not monitoring", "Press Start to begin detecting.", "")


def test_set_not_monitoring(widget: StatusWidget) -> None:
    widget.set_not_monitoring()
    assert text(widget) == ("Not monitoring", "Press Start to begin detecting.", "")


def test_set_monitoring(widget: StatusWidget) -> None:
    widget.set_monitoring()
    assert text(widget) == (
        "Monitoring",
        "Watching the selected screen region.",
        "",
    )


def test_available_result_displays_percentage(widget: StatusWidget) -> None:
    widget.set_result(DetectionResult(score=0.91, available=True))
    assert text(widget) == (
        "Villager available",
        "The target icon was detected.",
        "Confidence: 91.0%",
    )


def test_unavailable_result_displays_state_and_confidence(widget: StatusWidget) -> None:
    widget.set_result(DetectionResult(score=0.42, available=False))
    assert text(widget) == (
        "Villager not available",
        "The target icon is not currently visible.",
        "Confidence: 42.0%",
    )


def test_set_stopping(widget: StatusWidget) -> None:
    widget.set_stopping()
    assert text(widget) == ("Stopping", "Finishing the current capture.", "")


def test_set_error_uses_supplied_message(widget: StatusWidget) -> None:
    widget.set_error("Capture permission was denied.")
    assert text(widget) == ("Detection stopped", "Capture permission was denied.", "")


def test_clear_message_clears_description_and_confidence(widget: StatusWidget) -> None:
    widget.set_result(DetectionResult(score=0.91, available=True))
    widget.clear_message()
    assert text(widget) == ("Villager available", "", "")
