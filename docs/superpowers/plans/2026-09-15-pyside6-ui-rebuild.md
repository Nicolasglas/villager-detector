# PySide6 UI Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Tkinter presentation layer with a tested PySide6 desktop UI that matches the supplied blue-white reference while preserving the local detector engine and settings format.

**Architecture:** Keep `AppSettings`, `DetectionResult`, `DetectionMonitor`, screen capture, template matching, alerts, and path handling unchanged. Build a Qt presentation layer with a main window, status widget, settings drawer, and region selector. Deliver monitor events to Qt widgets through queued signals and keep all widget access on the GUI thread.

**Tech Stack:** Python 3.11+, PySide6, existing OpenCV/mss/dxcam/Pydantic services, pytest, PyInstaller.

**Spec:** `docs/superpowers/specs/2026-09-15-pyside6-ui-rebuild-design.md`

## Global Constraints

- Work only inside `C:\2nd_Brain\Projects\Villager detector`.
- Preserve `settings.json` compatibility and all existing validation rules.
- Do not change OpenCV matching, screen capture, monitoring, warning, or path-resolution behaviour.
- Keep the application local-only: no network, API, LLM, telemetry, or cloud features.
- Do not read or expose `.env`, credentials, or secret files.
- Do not delete the Tkinter implementation until the PySide6 version passes tests and manual smoke verification.
- Do not install dependencies without explicit approval; PySide6 is the only new runtime dependency proposed.
- Do not use frameless window chrome unless resize, drag, minimise, maximise, close, and always-on-top behaviour are tested.
- Do not update widgets from the monitor worker thread.
- Preserve stale-generation protection and bounded monitor shutdown.

---

### Task 1: Establish the PySide6 dependency and UI package boundary

**Files:**
- Modify: `pyproject.toml:9-15`
- Modify: `src_package/app.py`
- Create: `src_package/ui/__init__.py`
- Create: `src_package/ui/theme.py`
- Test: `tests/test_app.py`

**Interfaces:**
- `src_package.app.main() -> None` creates a `QApplication`, constructs `MainWindow`, shows it, and enters the Qt event loop.
- `src_package.ui.theme` exports `APP_STYLE_SHEET: str` and named colour/dimension constants.

- [ ] **Step 1: Confirm dependency state before editing**

Run:

```bash
python -m pip show PySide6
```

Expected: either an installed PySide6 version or a not-found result. If not installed, stop before installation and request approval to install the declared dependency.

- [ ] **Step 2: Add the dependency after approval**

Add exactly one runtime dependency to the existing list:

```toml
"PySide6",
```

Do not change existing pinned dependency versions.

- [ ] **Step 3: Add the UI package and theme constants**

Create `src_package/ui/__init__.py` as a package marker. Define the reference-derived tokens in `theme.py`, including `SHELL_BACKGROUND`, `SURFACE`, `TITLE_BAR`, `PRIMARY_TEXT`, `SECONDARY_TEXT`, `ACCENT_BLUE`, `AVAILABLE_GREEN`, `UNAVAILABLE_RED`, `DISABLED_SURFACE`, `BORDER`, `OUTER_RADIUS`, and `CONTROL_RADIUS`. Build a single Qt stylesheet from those constants. Use Segoe UI Variable with Segoe UI fallback.

- [ ] **Step 4: Add the minimal Qt entry point**

Replace Tkinter startup in `src_package/app.py` with a Qt entry point that imports `MainWindow` lazily, creates the application, applies `APP_STYLE_SHEET`, shows the window, and returns the event-loop exit code through `raise SystemExit(main())` only in the module guard. Keep `settings_from_values()` and `capture_probe_lines()` available from `src_package.app` until tests and callers are migrated.

- [ ] **Step 5: Run import and entry-point checks**

Run:

```bash
pytest tests/test_app.py::test_entry_point_import_does_not_start_tkinter -q
```

Expected: the test will require updating because it currently asserts Tkinter-era behaviour. Do not ignore it. Replace it with a test that imports `run` without starting the event loop and asserts `run.main is app_module.main`.

---

### Task 2: Build the reusable status widget

**Files:**
- Create: `src_package/ui/status_widget.py`
- Test: `tests/test_status_widget.py`

**Interfaces:**
- `StatusWidget(QWidget)` exposes `set_not_monitoring() -> None`, `set_monitoring() -> None`, `set_result(result: DetectionResult) -> None`, `set_stopping() -> None`, `set_error(message: str) -> None`, and `clear_message() -> None`.
- `StatusWidget` emits no detector-side effects. It only presents state.

- [ ] **Step 1: Write state-presentation tests**

Use a `QApplication` fixture that sets `QT_QPA_PLATFORM=offscreen` before creating the application. Assert that each setter updates accessible names or object names for the heading, description, and confidence label. Assert that `set_result(DetectionResult(score=0.91, available=True))` displays `91.0%` and the available text, while an unavailable result displays the unavailable text.

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
pytest tests/test_status_widget.py -q
```

Expected: FAIL because `StatusWidget` does not exist yet.

- [ ] **Step 3: Implement the widget**

Use a vertical layout with a state icon, heading, supporting message, and confidence label. Implement a small `QWidget` or `QPainter` icon rather than adding an icon dependency. Keep the widget centred, avoid fixed window-sized geometry, and use accessible names. Set `QSizePolicy.Expanding` where the layout needs to stretch.

- [ ] **Step 4: Run the focused tests**

Run:

```bash
pytest tests/test_status_widget.py -q
```

Expected: PASS.

---

### Task 3: Build the settings drawer using existing validation

**Files:**
- Create: `src_package/ui/settings_panel.py`
- Modify: `src_package/app.py` only if shared parsing must be moved without changing its signature
- Test: `tests/test_settings_panel.py`

**Interfaces:**
- `SettingsPanel(QWidget)` accepts `initial_settings: AppSettings` and emits `saved(settings: AppSettings)`, `closed()`, and `test_capture_requested(settings: AppSettings)` signals.
- `SettingsPanel.current_settings() -> AppSettings` validates by calling the existing `settings_from_values()` function or an extracted equivalent with the same error messages.

- [ ] **Step 1: Write form and validation tests**

Test that the panel contains all ten existing form keys: `x`, `y`, `width`, `height`, `reference_image`, `confidence_threshold`, `polling_interval_ms`, `always_on_top`, `warning_mode`, and `warning_wav`. Test that valid values produce the same `AppSettings` values as the current `settings_from_values()`. Test that invalid numeric values and invalid custom WAV paths produce a visible panel error and do not emit `saved`.

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
pytest tests/test_settings_panel.py -q
```

Expected: FAIL because `SettingsPanel` does not exist yet.

- [ ] **Step 3: Implement grouped settings**

Use a scrollable right-side panel with sections named Detection, Capture region, Alerts, and Window. Put labels above fields. Use `QLineEdit`, `QDoubleSpinBox` or a validated line edit for threshold, `QSpinBox` for interval and dimensions, `QComboBox` for warning mode, `QCheckBox` for always-on-top, and file dialogs for image/WAV selection. Preserve entered path text exactly. Put Save Settings at the bottom and expose a close button.

- [ ] **Step 4: Implement Test capture and region-selection hooks**

Emit `test_capture_requested(current_settings())` after validation. Emit a `select_region_requested()` signal from the Select Region control. Do not perform screen capture directly inside the panel.

- [ ] **Step 5: Run focused tests**

Run:

```bash
pytest tests/test_settings_panel.py -q
pytest tests/test_config.py -q
```

Expected: PASS, with the existing configuration tests unchanged.

---

### Task 4: Rebuild the region selector as a Qt overlay

**Files:**
- Create: `src_package/ui/region_selector.py`
- Test: `tests/test_region_selector.py`

**Interfaces:**
- `RegionSelector(QDialog)` emits `region_selected(region: Region)` and `cancelled()`.
- `RegionSelector.exec_selection() -> Region | None` returns a logical `Region` with physical screen coordinates.

- [ ] **Step 1: Write geometry tests independent of a display**

Test a pure helper such as `normalise_selection(start: QPoint, end: QPoint) -> Region | None`. Assert both drag directions, rejection when width or height is 5 pixels or less, and correct `(x, y, width, height)` values.

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
pytest tests/test_region_selector.py -q
```

Expected: FAIL because the selector helper does not exist.

- [ ] **Step 3: Implement the overlay**

Create a topmost translucent full-screen dialog across the virtual desktop. Use a transparent `QWidget` with mouse press, move, and release handling. Draw the darkened overlay, selection rectangle, dimensions, and Escape cancellation in `paintEvent`. Return physical global coordinates and do not save frames to disk.

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest tests/test_region_selector.py -q
```

Expected: PASS.

---

### Task 5: Build the main window and connect the lifecycle

**Files:**
- Create: `src_package/ui/main_window.py`
- Modify: `src_package/app.py`
- Modify: `run.py` only if the entry-point contract requires it
- Test: `tests/test_main_window.py`

**Interfaces:**
- `MainWindow(QMainWindow)` owns `StatusWidget`, `SettingsPanel`, and monitor lifecycle.
- `MainWindow.start_monitoring() -> None`, `stop_monitoring() -> None`, `open_settings() -> None`, and `close_settings() -> None` are GUI-thread methods.
- Internal queued event signals carry `DetectionResult`, warning strings, and error strings.

- [ ] **Step 1: Write construction and settings tests**

Test that a `MainWindow` can be constructed with a temporary settings path or injected settings loader. Assert that the settings drawer starts hidden, the cog opens it, the close button hides it, and all primary controls have accessible names.

- [ ] **Step 2: Add monitor event adapters**

Create Qt signals on the window or a small `QObject` bridge. Construct `DetectionMonitor` with callbacks that emit queued Qt signals rather than touching widgets. Preserve the existing generation integer and ignore events from inactive generations.

- [ ] **Step 3: Implement the reference layout**

Create the pale blue shell, rounded white surface, title bar, feather mark, app name, window controls, top-right settings cog, centred status widget, and two wide Start/Stop buttons. Prefer native title-bar behaviour initially. Add custom chrome only after the functional UI is verified.

- [ ] **Step 4: Wire settings and actions**

Connect Start to validation, save, monitor construction, and `monitor.start()`. Connect Stop to bounded `monitor.stop(timeout=0.05)` and a stopping state. Connect Save Settings to existing atomic `save_settings()`. Connect Test capture to `capture_probe_lines()` and show its lines in a Qt message dialog. Connect region selection to update the panel fields.

- [ ] **Step 5: Implement close lifecycle**

On close, mark the window as closing, stop the monitor, and destroy the window only after the monitor has exited. If stopping is incomplete, keep the window responsive and finish cleanup from a queued timer or monitor-finished signal.

- [ ] **Step 6: Run focused tests**

Run:

```bash
pytest tests/test_main_window.py -q
pytest tests/test_app.py -q
```

Expected: PASS after replacing Tkinter-specific construction tests with Qt offscreen tests while retaining all settings and lifecycle assertions.

---

### Task 6: Add Qt test fixtures and migrate app tests without weakening coverage

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_app.py`
- Create: `tests/test_qt_helpers.py` only if fixture helpers need their own module

**Interfaces:**
- `qapp` fixture returns one `QApplication` for the test session or module.
- Existing pure settings, capture probe, stale-event, and lifecycle assertions remain covered.

- [ ] **Step 1: Add an offscreen Qt fixture**

Set `QT_QPA_PLATFORM` to `offscreen` before importing or constructing Qt widgets. Reuse one `QApplication` instance and avoid calling `exec()` in tests.

- [ ] **Step 2: Port behaviour assertions**

Replace fake Tk widgets with assertions against status widget text, button enabled states, settings panel visibility, and signal emissions. Keep pure parsing tests unchanged where possible. Do not remove tests for stale generations, incomplete stops, close waits, warnings, capture probe output, or custom WAV validation.

- [ ] **Step 3: Run the full current suite**

Run:

```bash
pytest -q
```

Expected: all tests pass, or any environment-specific Qt failure is isolated and reported rather than hidden.

---

### Task 7: Apply visual polish and optional custom chrome

**Files:**
- Modify: `src_package/ui/theme.py`
- Modify: `src_package/ui/main_window.py`
- Modify: `src_package/ui/status_widget.py`
- Modify: `src_package/ui/settings_panel.py`
- Test: `tests/test_main_window.py`

**Interfaces:**
- No detector or settings interfaces change.

- [ ] **Step 1: Inspect the running application**

Launch with:

```bash
python run.py
```

Inspect initial, settings-open, monitoring, available, unavailable, stopping, validation-error, region-selector, and always-on-top states. Check at normal and high-DPI Windows scaling if available.

- [ ] **Step 2: Tune only shared design tokens**

Adjust spacing, colours, typography, radii, and control sizes from `theme.py`. Keep the central status dominant and keep the settings panel visually secondary. Avoid gradients, glows, decorative animation, and dense bordered form rows.

- [ ] **Step 3: Add custom title bar only if native chrome is insufficient**

If custom chrome is implemented, add explicit tests or manual checks for drag, resize, minimise, maximise, restore, close, and always-on-top. If any behaviour is unreliable, retain the native title bar.

- [ ] **Step 4: Re-run tests**

Run:

```bash
pytest -q
```

Expected: PASS.

---

### Task 8: Verify packaging and documentation

**Files:**
- Modify: `build_exe.py` only if PySide6 requires an explicit packaging hook
- Modify: `README.md`
- Test: `tests/test_build_exe.py`

**Interfaces:**
- Packaged launch remains `dist\\VillagerDetector\\VillagerDetector.exe`.
- Settings continue to be stored beside the executable.

- [ ] **Step 1: Update the README run instructions**

Document that the UI uses PySide6, retain the local-only statement, preserve the existing calibration and warning-sound instructions, and explain that settings are available from the cog.

- [ ] **Step 2: Run the build tests**

Run:

```bash
pytest tests/test_build_exe.py -q
```

Expected: PASS.

- [ ] **Step 3: Build the executable only after the source tests pass**

Run:

```bash
python build_exe.py
```

Expected: the existing one-folder output is rebuilt without changing the settings location.

- [ ] **Step 4: Smoke-test the packaged executable**

Launch `dist/VillagerDetector/VillagerDetector.exe`, verify the main window, settings drawer, settings load/save, and close behaviour. Do not claim packaging success unless the executable actually launches.

---

## Final verification

Run:

```bash
pytest -q
python run.py
```

Verify manually:

- Initial Not Monitoring state.
- Start and Stop state transitions.
- Available and unavailable result presentation.
- Confidence formatting.
- Settings cog open and close.
- All existing settings present.
- Save Settings and reload.
- Test capture.
- Region selection and Escape cancellation.
- Warning messages.
- Always-on-top.
- Close while monitoring.
- No horizontal clipping at the supported minimum window size.
- No network activity or secret access introduced.
