"""Offscreen tests for the geometry helper and Qt selector lifecycle."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPaintEvent
from PySide6.QtWidgets import QApplication

from src_package.config import Region
from src_package.ui.region_selector import RegionSelector, normalise_selection


def test_normalise_selection_left_to_right_top_to_bottom() -> None:
    assert normalise_selection(QPoint(10, 20), QPoint(110, 80)) == Region(
        x=10, y=20, width=100, height=60
    )


def test_normalise_selection_reverse_drag_in_both_axes() -> None:
    assert normalise_selection(QPoint(110, 80), QPoint(10, 20)) == Region(
        x=10, y=20, width=100, height=60
    )


def test_normalise_selection_rejects_width_exactly_five() -> None:
    assert normalise_selection(QPoint(10, 20), QPoint(15, 40)) is None


def test_normalise_selection_rejects_height_exactly_five() -> None:
    assert normalise_selection(QPoint(10, 20), QPoint(40, 25)) is None


def test_normalise_selection_returns_larger_region_with_global_coordinates() -> None:
    assert normalise_selection(QPoint(-900, -40), QPoint(-100, 260)) == Region(
        x=-900, y=-40, width=800, height=300
    )


def test_virtual_geometry_uses_qscreen_virtual_siblings(qapp: QApplication) -> None:
    selector = RegionSelector()

    class FakeScreen:
        def virtualSiblings(self) -> list[object]:
            return [
                type("Screen", (), {"geometry": lambda self: QRect(-100, 20, 200, 100)})(),
                type("Screen", (), {"geometry": lambda self: QRect(100, -30, 300, 200)})(),
            ]

    selector.screen = lambda: FakeScreen()  # type: ignore[method-assign]

    assert selector._virtual_geometry() == QRect(-100, -30, 500, 200)
    selector.deleteLater()
    qapp.processEvents()


def test_exec_selection_initialises_and_runs_modal_startup(qapp: QApplication) -> None:
    selector = RegionSelector()
    calls: list[str] = []
    selector._virtual_geometry = lambda: QRect(-10, -20, 300, 200)  # type: ignore[method-assign]
    selector.setGeometry = lambda geometry: calls.append(f"geometry:{geometry.getRect()}")  # type: ignore[method-assign]
    selector.show = lambda: calls.append("show")  # type: ignore[method-assign]
    selector.raise_ = lambda: calls.append("raise")  # type: ignore[method-assign]
    selector.activateWindow = lambda: calls.append("activate")  # type: ignore[method-assign]
    selector.exec = lambda: calls.append("exec")  # type: ignore[method-assign]

    assert selector.exec_selection() is None
    assert calls == ["geometry:(-10, -20, 300, 200)", "show", "raise", "activate", "exec"]
    selector.deleteLater()
    qapp.processEvents()


def _mouse_event(event_type: QMouseEvent.Type, point: QPoint) -> QMouseEvent:
    return QMouseEvent(
        event_type,
        point,
        point,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_mouse_release_emits_selected_region_and_accepts(qapp: QApplication) -> None:
    selector = RegionSelector()
    selected: list[Region] = []
    selector.region_selected.connect(selected.append)

    selector.mousePressEvent(_mouse_event(QMouseEvent.Type.MouseButtonPress, QPoint(50, 60)))
    selector.mouseMoveEvent(_mouse_event(QMouseEvent.Type.MouseMove, QPoint(10, 20)))
    selector.mouseReleaseEvent(_mouse_event(QMouseEvent.Type.MouseButtonRelease, QPoint(10, 20)))
    qapp.processEvents()

    assert selected == [Region(x=10, y=20, width=40, height=40)]
    assert selector.result() == 1  # QDialog.Accepted
    selector.deleteLater()
    qapp.processEvents()


def test_paint_event_draws_overlay_without_display(qapp: QApplication) -> None:
    selector = RegionSelector()
    selector.setGeometry(QRect(0, 0, 200, 100))
    selector._start = QPoint(10, 20)
    selector._current = QPoint(80, 60)

    selector.paintEvent(QPaintEvent(selector.rect()))
    selector.deleteLater()
    qapp.processEvents()


def test_escape_emits_cancelled_and_rejects_without_display(qapp: QApplication) -> None:
    selector = RegionSelector()
    cancelled: list[bool] = []
    selector.cancelled.connect(lambda: cancelled.append(True))

    event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Escape,
        Qt.KeyboardModifier.NoModifier,
    )
    selector.keyPressEvent(event)
    qapp.processEvents()

    assert cancelled == [True]
    assert selector.result() == 0  # QDialog.Rejected
    selector.deleteLater()
    qapp.processEvents()
