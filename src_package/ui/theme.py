"""Shared visual tokens and the application stylesheet."""

SHELL_BACKGROUND = "#EAF4FF"
TITLE_BAR = "#F5F9FE"
SURFACE = "#FFFFFF"
PRIMARY_TEXT = "#101D3A"
SECONDARY_TEXT = "#586987"
ACCENT_BLUE = "#2368D5"
AVAILABLE_GREEN = "#29A66A"
UNAVAILABLE_RED = "#C84D58"
VALIDATION_ERROR = "#B3261E"
DISABLED_SURFACE = "#E7EEF8"
BORDER = "#D7E4F2"
SUBTLE_SURFACE = "#F7FAFE"
OUTER_RADIUS = 18
GROUP_BOX_RADIUS = 12
CONTROL_RADIUS = 10
SHELL_MARGIN = 18
SURFACE_PADDING = 22
CONTROL_HEIGHT = 42

APP_STYLE_SHEET = f"""
QWidget {{
    background: {SHELL_BACKGROUND};
    color: {PRIMARY_TEXT};
    font-family: \"Segoe UI Variable\", \"Segoe UI\";
    font-size: 13px;
}}
QMainWindow, QDialog {{
    background: {SHELL_BACKGROUND};
}}
QFrame#contentSurface {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {OUTER_RADIUS}px;
}}
QPushButton, QToolButton {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {CONTROL_RADIUS}px;
    min-height: {CONTROL_HEIGHT}px;
    padding: 0 16px;
    color: {PRIMARY_TEXT};
    font-weight: 600;
}}
QPushButton:hover, QToolButton:hover {{
    background: {SUBTLE_SURFACE};
    border-color: {ACCENT_BLUE};
}}
QPushButton:focus-visible, QToolButton:focus-visible {{
    border: 2px solid {ACCENT_BLUE};
}}
QPushButton:disabled, QToolButton:disabled {{
    background: {DISABLED_SURFACE};
    color: {SECONDARY_TEXT};
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {CONTROL_RADIUS}px;
    min-height: 36px;
    padding: 0 10px;
    selection-background-color: {ACCENT_BLUE};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 2px solid {ACCENT_BLUE};
}}
QPushButton#startButton, QPushButton#stopButton {{
    min-height: 48px;
    font-size: 14px;
}}
QPushButton#startButton {{
    background: {ACCENT_BLUE};
    border-color: {ACCENT_BLUE};
    color: {SURFACE};
}}
QPushButton#startButton:hover {{
    background: #1D59B8;
    border-color: #1D59B8;
}}
QPushButton#startButton:disabled {{
    background: {DISABLED_SURFACE};
    border-color: {BORDER};
    color: {SECONDARY_TEXT};
}}
QPushButton#settingsButton {{
    min-width: 40px;
    max-width: 40px;
    min-height: 40px;
    max-height: 40px;
    padding: 0;
    font-size: 18px;
}}
QWidget#settingsPanel {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {OUTER_RADIUS}px;
}}
QScrollArea#settingsScrollArea, QWidget#settingsContent {{
    background: {SURFACE};
}}
"""
