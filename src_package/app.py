"""Compact Tkinter interface for the villager detector."""

from __future__ import annotations

import queue
import tkinter as tk
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from pydantic import ValidationError

from src_package.config import (
    PROJECT_ROOT,
    AppSettings,
    Region,
    load_settings,
    save_settings,
    validate_wav_file,
)
from src_package.models import DetectionResult
from src_package.services.screen_capture import (
    ScreenCapturer,
    describe_capture_geometry,
    is_blank_frame,
)

if TYPE_CHECKING:
    from src_package.services.monitor import DetectionMonitor


_FORM_FIELDS = (
    "x",
    "y",
    "width",
    "height",
    "reference_image",
    "confidence_threshold",
    "polling_interval_ms",
    "always_on_top",
    "warning_mode",
    "warning_wav",
)
_UI_STOP_TIMEOUT_SECONDS = 0.05


def _required(values: Mapping[str, str | bool], key: str) -> str | bool:
    try:
        return values[key]
    except KeyError as exc:
        raise ValueError(f"{key}: value is required") from exc


def _parse_int(values: Mapping[str, str | bool], key: str) -> int:
    value = _required(values, key)
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key}: enter a whole number") from exc


def _parse_float(values: Mapping[str, str | bool], key: str) -> float:
    value = _required(values, key)
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key}: enter a number") from exc


def _parse_bool(values: Mapping[str, str | bool], key: str) -> bool:
    value = _required(values, key)
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"{key}: enter true or false")


def settings_from_values(values: Mapping[str, str | bool]) -> AppSettings:
    """Parse form values into validated settings without rewriting path text."""
    reference_image = _required(values, "reference_image")
    warning_mode = _required(values, "warning_mode")
    warning_wav = _required(values, "warning_wav")
    if not isinstance(reference_image, str):
        raise ValueError("reference_image: enter a path")
    if not isinstance(warning_mode, str):
        raise ValueError("warning_mode: select a mode")
    if not isinstance(warning_wav, str):
        raise ValueError("warning_wav: enter a path")

    if warning_mode == "custom":
        entered_path = warning_wav.strip()
        candidate = Path(entered_path)
        resolved = candidate if candidate.is_absolute() else PROJECT_ROOT / candidate
        try:
            validate_wav_file(resolved)
        except ValueError as exc:
            raise ValueError(f"warning_wav: {exc}") from exc

    try:
        return AppSettings(
            region=Region(
                x=_parse_int(values, "x"),
                y=_parse_int(values, "y"),
                width=_parse_int(values, "width"),
                height=_parse_int(values, "height"),
            ),
            reference_image=reference_image,
            confidence_threshold=_parse_float(values, "confidence_threshold"),
            polling_interval_ms=_parse_int(values, "polling_interval_ms"),
            always_on_top=_parse_bool(values, "always_on_top"),
            warning_mode=warning_mode,  # type: ignore[arg-type]
            warning_wav=warning_wav,
        )
    except ValidationError as exc:
        error = exc.errors()[0]
        field = ".".join(str(part) for part in error["loc"])
        raise ValueError(f"{field}: {error['msg']}") from exc
    except TypeError as exc:
        raise ValueError("Settings contain an invalid value") from exc


def capture_probe_lines(settings: AppSettings) -> list[str]:
    """Capture the region once and report what the detector currently sees."""
    from src_package.services.template_matcher import TemplateMatcher

    frame = ScreenCapturer().capture(settings.region)
    height, width = frame.shape[:2]
    lines = [
        describe_capture_geometry(settings.region),
        f"Captured frame: {width}x{height} pixels",
    ]
    if is_blank_frame(frame):
        lines.append(
            "The captured region is entirely black. GPU fullscreen capture was "
            "unavailable; try Borderless Fullscreen or windowed mode."
        )
    result = TemplateMatcher(
        settings.reference_image_path, settings.confidence_threshold
    ).match(frame)
    lines.append(
        f"Best match: {result.score:.1%} "
        f"(threshold {settings.confidence_threshold:.0%})"
    )
    return lines


@dataclass(frozen=True, slots=True)
class _ResultEvent:
    generation: int
    result: DetectionResult


@dataclass(frozen=True, slots=True)
class _ErrorEvent:
    generation: int
    message: str


@dataclass(frozen=True, slots=True)
class _WarningEvent:
    generation: int
    message: str


_UIEvent = _ResultEvent | _ErrorEvent | _WarningEvent


class VillagerDetectorApp:
    """Own the form, monitor lifecycle, and main-thread event dispatch."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Villager Detector")
        self.root.minsize(470, 430)
        self._monitor: DetectionMonitor | None = None
        self._next_generation = 0
        self._active_generation: int | None = None
        self._closing = False
        self._events: queue.Queue[_UIEvent] = queue.Queue()
        self._variables: dict[str, tk.StringVar | tk.BooleanVar] = {
            "x": tk.StringVar(),
            "y": tk.StringVar(),
            "width": tk.StringVar(),
            "height": tk.StringVar(),
            "reference_image": tk.StringVar(),
            "confidence_threshold": tk.StringVar(),
            "polling_interval_ms": tk.StringVar(),
            "always_on_top": tk.BooleanVar(),
            "warning_mode": tk.StringVar(),
            "warning_wav": tk.StringVar(),
        }
        self._status_text = tk.StringVar(value="NOT MONITORING")
        self._confidence_text = tk.StringVar(value="Confidence: —")
        self._message_text = tk.StringVar(value="")

        self._configure_styles()
        self._build_ui()
        self._set_form(AppSettings())
        self._load_startup_settings()
        self._apply_topmost()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(50, self._poll_events)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.configure("Status.Neutral.TLabel", foreground="#555555", font=("Segoe UI", 18, "bold"))
        style.configure("Status.Available.TLabel", foreground="#16803a", font=("Segoe UI", 18, "bold"))
        style.configure("Status.Unavailable.TLabel", foreground="#b3261e", font=("Segoe UI", 18, "bold"))
        style.configure("Confidence.TLabel", font=("Segoe UI", 11))
        style.configure("Message.Info.TLabel", foreground="#555555", font=("Segoe UI", 9))
        style.configure("Message.Warning.TLabel", foreground="#8a4b00", font=("Segoe UI", 9))

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        status_frame = ttk.Frame(self.root, padding=(12, 10, 12, 6))
        status_frame.grid(row=0, column=0, sticky="ew")
        status_frame.columnconfigure(0, weight=1)
        self._status_label = ttk.Label(
            status_frame,
            textvariable=self._status_text,
            style="Status.Neutral.TLabel",
            anchor="center",
        )
        self._status_label.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            status_frame,
            textvariable=self._confidence_text,
            style="Confidence.TLabel",
            anchor="center",
        ).grid(row=1, column=0, sticky="ew", pady=(3, 0))
        self._message_label = ttk.Label(
            status_frame,
            textvariable=self._message_text,
            style="Message.Info.TLabel",
            anchor="center",
            justify="center",
            wraplength=430,
        )
        self._message_label.grid(row=2, column=0, sticky="ew", pady=(4, 0))

        settings = ttk.LabelFrame(self.root, text="Settings", padding=10)
        settings.grid(row=1, column=0, padx=12, pady=6, sticky="nsew")
        settings.columnconfigure(1, weight=1)
        settings.columnconfigure(3, weight=1)

        labels = (("X", "x"), ("Y", "y"), ("Width", "width"), ("Height", "height"))
        for index, (label, key) in enumerate(labels):
            row, pair = divmod(index, 2)
            column = pair * 2
            ttk.Label(settings, text=f"{label}:").grid(row=row, column=column, sticky="w", padx=(0, 5), pady=3)
            ttk.Entry(settings, textvariable=self._variables[key], width=10).grid(row=row, column=column + 1, sticky="ew", padx=(0, 10), pady=3)

        ttk.Button(settings, text="Select Region…", command=self._select_region).grid(row=2, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self._add_path_row(settings, 3, "Reference image:", "reference_image", self._browse_reference)
        ttk.Label(settings, text="Threshold:").grid(row=4, column=0, sticky="w", padx=(0, 5), pady=3)
        ttk.Entry(settings, textvariable=self._variables["confidence_threshold"], width=10).grid(row=4, column=1, sticky="ew", padx=(0, 10), pady=3)
        ttk.Label(settings, text="Interval (ms):").grid(row=4, column=2, sticky="w", padx=(0, 5), pady=3)
        ttk.Entry(settings, textvariable=self._variables["polling_interval_ms"], width=10).grid(row=4, column=3, sticky="ew", pady=3)

        ttk.Checkbutton(
            settings,
            text="Always on top",
            variable=self._variables["always_on_top"],
            command=self._apply_topmost,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Label(settings, text="Warning:").grid(row=5, column=2, sticky="w", padx=(0, 5), pady=3)
        ttk.Combobox(
            settings,
            textvariable=self._variables["warning_mode"],
            values=("disabled", "builtin", "custom"),
            state="readonly",
            width=12,
        ).grid(row=5, column=3, sticky="ew", pady=3)
        self._add_path_row(settings, 6, "Warning WAV:", "warning_wav", self._browse_wav)
        ttk.Button(
            settings,
            text="Test capture (check the chosen region now)",
            command=self._test_capture,
        ).grid(row=7, column=0, columnspan=4, sticky="ew", pady=(10, 0))

        buttons = ttk.Frame(self.root, padding=(12, 6, 12, 12))
        buttons.grid(row=2, column=0, sticky="ew")
        buttons.columnconfigure((0, 1, 2), weight=1)
        self._start_button = ttk.Button(buttons, text="Start", command=self._start)
        self._start_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self._stop_button = ttk.Button(buttons, text="Stop", command=self._stop, state="disabled")
        self._stop_button.grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(buttons, text="Save Settings", command=self._save).grid(row=0, column=2, sticky="ew", padx=(5, 0))

    def _add_path_row(
        self,
        parent: ttk.LabelFrame,
        row: int,
        label: str,
        key: str,
        command: object,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 5), pady=3)
        ttk.Entry(parent, textvariable=self._variables[key]).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(0, 5), pady=3)
        ttk.Button(parent, text="Browse…", command=command).grid(row=row, column=3, sticky="ew", pady=3)

    def _set_form(self, settings: AppSettings) -> None:
        entered = {
            "x": str(settings.region.x),
            "y": str(settings.region.y),
            "width": str(settings.region.width),
            "height": str(settings.region.height),
            "reference_image": settings.reference_image,
            "confidence_threshold": str(settings.confidence_threshold),
            "polling_interval_ms": str(settings.polling_interval_ms),
            "always_on_top": settings.always_on_top,
            "warning_mode": settings.warning_mode,
            "warning_wav": settings.warning_wav,
        }
        for key, value in entered.items():
            self._variables[key].set(value)

    def _form_values(self) -> dict[str, str | bool]:
        return {key: self._variables[key].get() for key in _FORM_FIELDS}

    def _validated_settings(self) -> AppSettings | None:
        try:
            return settings_from_values(self._form_values())
        except ValueError as exc:
            messagebox.showerror("Invalid settings", str(exc), parent=self.root)
            return None

    def _load_startup_settings(self) -> None:
        try:
            settings = load_settings()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Settings error", f"Could not load settings: {exc}", parent=self.root)
            return
        self._set_form(settings)

    def _save(self) -> bool:
        settings = self._validated_settings()
        if settings is None:
            return False
        try:
            save_settings(settings)
        except OSError as exc:
            messagebox.showerror("Save error", f"Could not save settings: {exc}", parent=self.root)
            return False
        return True

    def _test_capture(self) -> None:
        settings = self._validated_settings()
        if settings is None:
            return
        try:
            lines = capture_probe_lines(settings)
        except Exception as exc:
            messagebox.showerror("Test capture failed", str(exc), parent=self.root)
            return
        messagebox.showinfo("Test capture", "\n".join(lines), parent=self.root)

    def _start(self) -> None:
        if self._monitor is not None and not self._stop():
            return
        settings = self._validated_settings()
        if settings is None:
            return
        self._next_generation += 1
        generation = self._next_generation
        try:
            from src_package.services.monitor import DetectionMonitor

            save_settings(settings)
            monitor = DetectionMonitor(
                settings,
                lambda result: self._events.put(_ResultEvent(generation, result)),
                lambda message: self._events.put(_ErrorEvent(generation, message)),
                on_warning=lambda message: self._events.put(
                    _WarningEvent(generation, message)
                ),
            )
        except (ImportError, OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Start error", str(exc), parent=self.root)
            return

        self._monitor = monitor
        self._active_generation = generation
        self._status_text.set("MONITORING…")
        self._status_label.configure(style="Status.Neutral.TLabel")
        self._confidence_text.set("Confidence: —")
        self._set_message(describe_capture_geometry(settings.region), warning=False)
        self._set_running_controls(True)
        try:
            monitor.start()
        except Exception as exc:
            self._active_generation = None
            try:
                stopped = monitor.stop(timeout=_UI_STOP_TIMEOUT_SECONDS)
            except Exception:
                stopped = False
            if stopped:
                self._monitor = None
                self._set_stopped_state()
            else:
                self._status_text.set("STOPPING…")
                self._status_label.configure(style="Status.Neutral.TLabel")
                self._set_stopping_controls()
            messagebox.showerror("Start error", str(exc), parent=self.root)

    def _stop(self) -> bool:
        self._active_generation = None
        monitor = self._monitor
        if monitor is None:
            self._set_stopped_state()
            return True
        if not monitor.stop(timeout=_UI_STOP_TIMEOUT_SECONDS):
            self._status_text.set("STOPPING…")
            self._status_label.configure(style="Status.Neutral.TLabel")
            self._set_stopping_controls()
            return False
        self._monitor = None
        self._set_stopped_state()
        return True

    def _set_stopped_state(self) -> None:
        self._status_text.set("NOT MONITORING")
        self._status_label.configure(style="Status.Neutral.TLabel")
        self._confidence_text.set("Confidence: —")
        self._set_message("", warning=False)
        self._set_running_controls(False)

    def _set_message(self, message: str, *, warning: bool) -> None:
        self._message_text.set(message)
        style = "Message.Warning.TLabel" if warning else "Message.Info.TLabel"
        try:
            self._message_label.configure(style=style)
        except AttributeError:
            # Only reachable from tests that build the app without widgets.
            pass

    def _set_stopping_controls(self) -> None:
        self._start_button.configure(state="disabled")
        self._stop_button.configure(state="disabled")

    def _set_running_controls(self, running: bool) -> None:
        self._start_button.configure(state="disabled" if running else "normal")
        self._stop_button.configure(state="normal" if running else "disabled")

    def _poll_events(self) -> None:
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            if event.generation != self._active_generation:
                continue
            if isinstance(event, _ResultEvent):
                self._show_result(event.result)
            elif isinstance(event, _WarningEvent):
                self._set_message(event.message, warning=True)
            else:
                self._handle_worker_error(event.message)
        monitor = self._monitor
        if (
            monitor is not None
            and self._active_generation is None
            and not monitor.is_running
        ):
            self._monitor = None
            if self._closing:
                self.root.destroy()
                return
            self._set_stopped_state()
        self.root.after(50, self._poll_events)

    def _show_result(self, result: DetectionResult) -> None:
        if result.available:
            self._status_text.set("VILLAGER AVAILABLE")
            self._status_label.configure(style="Status.Available.TLabel")
        else:
            self._status_text.set("VILLAGER NOT AVAILABLE")
            self._status_label.configure(style="Status.Unavailable.TLabel")
        self._confidence_text.set(f"Confidence: {result.score:.1%}")

    def _handle_worker_error(self, message: str) -> None:
        self._active_generation = None
        if self._monitor is None or self._monitor.stop(
            timeout=_UI_STOP_TIMEOUT_SECONDS
        ):
            self._monitor = None
            self._set_stopped_state()
        else:
            self._status_text.set("STOPPING…")
            self._status_label.configure(style="Status.Neutral.TLabel")
            self._set_stopping_controls()
        messagebox.showerror("Monitoring error", message, parent=self.root)

    def _browse_reference(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="Select reference image",
            filetypes=(("Image files", "*.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")),
        )
        if selected:
            self._variables["reference_image"].set(selected)

    def _browse_wav(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="Select warning WAV",
            filetypes=(("WAV files", "*.wav"), ("All files", "*.*")),
        )
        if selected:
            self._variables["warning_wav"].set(selected)

    def _select_region(self) -> None:
        """Open a full-screen overlay to let the user click-drag a screen region."""
        selector = _RegionSelector(self.root)
        region = selector.run()
        if region is not None:
            x, y, width, height = region
            self._variables["x"].set(str(x))
            self._variables["y"].set(str(y))
            self._variables["width"].set(str(width))
            self._variables["height"].set(str(height))

    def _apply_topmost(self) -> None:
        self.root.attributes("-topmost", bool(self._variables["always_on_top"].get()))

    def _on_close(self) -> None:
        self._closing = True
        self._active_generation = None
        if self._stop():
            self.root.destroy()


class _RegionSelector:
    """Full-screen transparent overlay for click-drag region selection."""

    def __init__(self, parent: tk.Tk) -> None:
        self._parent = parent
        self._start_x = 0
        self._start_y = 0
        self._current_x = 0
        self._current_y = 0
        self._selecting = False
        self._result: tuple[int, int, int, int] | None = None
        self._overlay: tk.Toplevel | None = None
        self._canvas: tk.Canvas | None = None
        self._rect_id: int | None = None

    def run(self) -> tuple[int, int, int, int] | None:
        """Show the overlay and return (x, y, width, height) or None if cancelled."""
        self._overlay = tk.Toplevel(self._parent)
        self._overlay.attributes("-fullscreen", True)
        self._overlay.attributes("-alpha", 0.3)
        self._overlay.attributes("-topmost", True)
        self._overlay.configure(bg="black", cursor="crosshair")
        self._overlay.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._canvas = tk.Canvas(self._overlay, highlightthickness=0, bg="black")
        self._canvas.pack(fill="both", expand=True)

        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._overlay.bind("<Escape>", lambda e: self._on_cancel())

        self._parent.wait_window(self._overlay)
        return self._result

    def _on_press(self, event: tk.Event) -> None:
        self._start_x = event.x_root
        self._start_y = event.y_root
        self._current_x = event.x_root
        self._current_y = event.y_root
        self._selecting = True
        if self._canvas is not None:
            self._rect_id = self._canvas.create_rectangle(
                self._start_x, self._start_y, self._start_x, self._start_y,
                outline="red", width=2, fill="red", stipple="gray25"
            )

    def _on_drag(self, event: tk.Event) -> None:
        if not self._selecting or self._canvas is None or self._rect_id is None:
            return
        self._current_x = event.x_root
        self._current_y = event.y_root
        self._canvas.coords(self._rect_id, self._start_x, self._start_y, self._current_x, self._current_y)

    def _on_release(self, event: tk.Event) -> None:
        if not self._selecting:
            return
        self._selecting = False
        x1, y1 = self._start_x, self._start_y
        x2, y2 = self._current_x, self._current_y
        x = min(x1, x2)
        y = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        if width > 5 and height > 5:
            self._result = (x, y, width, height)
        self._close()

    def _on_cancel(self) -> None:
        self._result = None
        self._close()

    def _close(self) -> None:
        if self._overlay is not None:
            self._overlay.destroy()
            self._overlay = None


def main() -> int:
    """Create and run the PySide6 application."""
    from PySide6.QtWidgets import QApplication

    from src_package.ui.main_window import MainWindow
    from src_package.ui.theme import APP_STYLE_SHEET

    application = QApplication.instance() or QApplication([])
    application.setStyleSheet(APP_STYLE_SHEET)
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
