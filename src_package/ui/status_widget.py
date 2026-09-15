"""Reusable, presentation-only status widget for the detector screen."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from src_package.models import DetectionResult
from src_package.ui import theme


class _StatusIcon(QWidget):
    """Small dependency-free status icon rendered with QPainter."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusIcon")
        self.setAccessibleName("Detection status icon")
        self.setFixedSize(72, 72)
        self._state = "neutral"
        self._color = QColor(theme.ACCENT_BLUE)

    def set_state(self, state: str, color: str) -> None:
        self._state = state
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        radius = min(self.width(), self.height()) // 2 - 6
        painter.setPen(QPen(self._color, 3))
        painter.setBrush(QColor(self._color).lighter(185))
        painter.drawEllipse(center, radius, radius)

        painter.setPen(QPen(self._color, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        if self._state == "available":
            painter.drawLine(center.x() - 13, center.y(), center.x() - 3, center.y() + 10)
            painter.drawLine(center.x() - 3, center.y() + 10, center.x() + 16, center.y() - 12)
        elif self._state == "unavailable":
            painter.drawLine(center.x() - 12, center.y() - 12, center.x() + 12, center.y() + 12)
            painter.drawLine(center.x() + 12, center.y() - 12, center.x() - 12, center.y() + 12)
        elif self._state == "error":
            painter.drawLine(center.x(), center.y() - 14, center.x(), center.y() + 5)
            painter.drawPoint(center.x(), center.y() + 14)
        elif self._state == "stopping":
            painter.drawRect(center.x() - 10, center.y() - 10, 20, 20)
        else:
            painter.drawEllipse(center, 4, 4)
        painter.end()


class StatusWidget(QWidget):
    """Display the detector state without performing detector-side work."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusWidget")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.icon = _StatusIcon(self)
        self.heading_label = QLabel(self)
        self.heading_label.setObjectName("statusHeading")
        self.heading_label.setAccessibleName("Status heading")
        self.heading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.heading_label.setWordWrap(True)
        self.heading_label.setStyleSheet(
            f"color: {theme.PRIMARY_TEXT}; font-size: 24px; font-weight: 700;"
        )

        self.description_label = QLabel(self)
        self.description_label.setObjectName("statusDescription")
        self.description_label.setAccessibleName("Status description")
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet(f"color: {theme.SECONDARY_TEXT};")

        self.confidence_label = QLabel(self)
        self.confidence_label.setObjectName("statusConfidence")
        self.confidence_label.setAccessibleName("Detection confidence")
        self.confidence_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.confidence_label.setStyleSheet(f"color: {theme.SECONDARY_TEXT};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.heading_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.description_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.confidence_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.set_not_monitoring()

    def _set_state(self, heading: str, description: str, state: str, color: str, confidence: str = "") -> None:
        self.heading_label.setText(heading)
        self.description_label.setText(description)
        self.confidence_label.setText(confidence)
        self.icon.set_state(state, color)

    def set_not_monitoring(self) -> None:
        self._set_state(
            "Not monitoring",
            "Press Start to begin detecting.",
            "neutral",
            theme.ACCENT_BLUE,
        )

    def set_monitoring(self) -> None:
        self._set_state(
            "Monitoring",
            "Watching the selected screen region.",
            "neutral",
            theme.ACCENT_BLUE,
        )

    def set_result(self, result: DetectionResult) -> None:
        if result.available:
            self._set_state(
                "Villager available",
                "The target icon was detected.",
                "available",
                theme.AVAILABLE_GREEN,
                f"Confidence: {result.score:.1%}",
            )
        else:
            self._set_state(
                "Villager not available",
                "The target icon is not currently visible.",
                "unavailable",
                theme.UNAVAILABLE_RED,
                f"Confidence: {result.score:.1%}",
            )

    def set_stopping(self) -> None:
        self._set_state(
            "Stopping",
            "Finishing the current capture.",
            "stopping",
            theme.ACCENT_BLUE,
        )

    def set_error(self, message: str) -> None:
        self._set_state("Detection stopped", message, "error", theme.UNAVAILABLE_RED)

    def clear_message(self) -> None:
        self.description_label.clear()
        self.confidence_label.clear()
