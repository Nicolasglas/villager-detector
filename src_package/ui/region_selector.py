"""Full-screen Qt overlay used to select a physical screen region."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QDialog

from src_package.config import Region
from src_package.ui import theme


_MINIMUM_SELECTION_SIZE = 5


def normalise_selection(start: QPoint, end: QPoint) -> Region | None:
    """Convert two global points into a valid logical capture region.

    The points are deliberately treated as global screen coordinates.  This
    keeps negative coordinates on monitors left/above the primary display and
    avoids changing the physical-pixel contract used by the capture service.
    """
    x = min(start.x(), end.x())
    y = min(start.y(), end.y())
    width = abs(end.x() - start.x())
    height = abs(end.y() - start.y())
    if width <= _MINIMUM_SELECTION_SIZE or height <= _MINIMUM_SELECTION_SIZE:
        return None
    return Region(x=x, y=y, width=width, height=height)


class RegionSelector(QDialog):
    """Topmost translucent overlay for click-drag region selection."""

    region_selected = Signal(Region)
    cancelled = Signal()

    def __init__(self, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("regionSelector")
        self.setWindowTitle("Select capture region")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self._start: QPoint | None = None
        self._current: QPoint | None = None
        self._result: Region | None = None
        self._selecting = False

    def _virtual_geometry(self) -> QRect:
        """Return the union of all screens in global Qt coordinates."""
        screens = self.screen().virtualSiblings() if self.screen() else []
        if not screens and self.windowHandle() and self.windowHandle().screen():
            screens = self.windowHandle().screen().virtualSiblings()
        if not screens:
            from PySide6.QtWidgets import QApplication

            screens = QApplication.screens()
        if not screens:
            return QRect(0, 0, 1, 1)
        geometry = screens[0].geometry()
        for screen in screens[1:]:
            geometry = geometry.united(screen.geometry())
        return geometry


    def exec_selection(self) -> Region | None:
        """Show the selector modally and return the selected region."""
        self._result = None
        self._start = None
        self._current = None
        self._selecting = False
        self.setGeometry(self._virtual_geometry())
        self.show()
        self.raise_()
        self.activateWindow()
        self.exec()
        return self._result

    def mousePressEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:  # type: ignore[union-attr]
            self._start = event.globalPosition().toPoint()  # type: ignore[union-attr]
            self._current = self._start
            self._selecting = True
            self.update()
        else:
            super().mousePressEvent(event)  # type: ignore[arg-type]

    def mouseMoveEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        if self._selecting:
            self._current = event.globalPosition().toPoint()  # type: ignore[union-attr]
            self.update()
        else:
            super().mouseMoveEvent(event)  # type: ignore[arg-type]

    def mouseReleaseEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        if event.button() != Qt.MouseButton.LeftButton or not self._selecting:
            super().mouseReleaseEvent(event)  # type: ignore[arg-type]
            return
        self._current = event.globalPosition().toPoint()  # type: ignore[union-attr]
        self._selecting = False
        self._result = normalise_selection(self._start, self._current) if self._start else None
        if self._result is not None:
            self.region_selected.emit(self._result)
        self.accept()

    def keyPressEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        if event.key() == Qt.Key.Key_Escape:  # type: ignore[union-attr]
            self._on_cancel()
        else:
            super().keyPressEvent(event)  # type: ignore[arg-type]

    def reject(self) -> None:
        """Treat all dialog rejection paths as cancellation."""
        if self._result is None:
            self.cancelled.emit()
        super().reject()

    def _on_cancel(self) -> None:
        self._result = None
        self._start = None
        self._current = None
        self._selecting = False
        self.cancelled.emit()
        super().reject()

    def _selection_rect(self) -> QRect | None:
        if self._start is None or self._current is None:
            return None
        start = self._start - self.geometry().topLeft()
        end = self._current - self.geometry().topLeft()
        return QRect(start, end).normalized()

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 150))
        selection = self._selection_rect()
        if selection is not None:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(selection, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor(theme.ACCENT_BLUE), 2))
            painter.setBrush(QColor(theme.ACCENT_BLUE).lighter(170))
            painter.drawRect(selection)
            if self._start is not None and self._current is not None:
                width = abs(self._current.x() - self._start.x())
                height = abs(self._current.y() - self._start.y())
                label = f"{width} × {height}"
                painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                text_rect = painter.fontMetrics().boundingRect(label).adjusted(-8, -4, 8, 4)
                text_rect.moveTopLeft(selection.topLeft() + QPoint(8, 8))
                painter.fillRect(text_rect, QColor(16, 29, 58, 220))
                painter.setPen(Qt.GlobalColor.white)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.end()
