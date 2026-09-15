# Villager Availability Detector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight local Windows UI that monitors one screen rectangle and reports whether a supplied villager icon is present.

**Architecture:** A Tkinter UI runs on the main thread while a stoppable worker captures a configured region with MSS and matches a cached grayscale template with OpenCV. Pydantic validates persistent settings, and an isolated transition tracker triggers `winsound` once when detection changes from available to unavailable.

**Tech Stack:** Python 3.11+, OpenCV, MSS, Pydantic 2, Tkinter, winsound, pytest

**Spec:** `docs/superpowers/specs/2026-09-14-villager-detector-design.md`

## Global Constraints

- Windows desktop application; Python 3.11 or newer.
- Capture only the configured screen rectangle.
- Use `cv2.matchTemplate(..., cv2.TM_CCOEFF_NORMED)` on grayscale images.
- Default confidence threshold is exactly `0.85`.
- Never click, type, control the game, save captured frames, or use the network.
- Store only non-secret preferences in project-root `settings.json`.
- Play a warning once only on an available-to-unavailable transition.
- The initial unavailable result must not warn.
- No Git commits: the project directory is not a Git repository.

---

### Task 1: Project configuration and validated settings

**Files:**
- Create: `pyproject.toml`
- Create: `src_package/__init__.py`
- Create: `src_package/config.py`
- Create: `settings.json`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces: `PROJECT_ROOT: Path`, `Region`, `AppSettings`, `load_settings(path: Path | None = None) -> AppSettings`, and `save_settings(settings: AppSettings, path: Path | None = None) -> None`.

- [ ] **Step 1: Write failing configuration tests**

Test that `AppSettings()` has threshold `0.85`, positive region dimensions and polling interval, rejects thresholds outside `0.0..1.0`, rejects non-positive dimensions, round-trips JSON in UTF-8, and leaves no temporary file after `save_settings`.

- [ ] **Step 2: Run the narrow test**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL because `src_package.config` does not exist.

- [ ] **Step 3: Add dependencies and settings implementation**

Use these models and signatures:

```python
class Region(BaseModel):
    x: int = 0
    y: int = 0
    width: int = Field(default=400, gt=0)
    height: int = Field(default=300, gt=0)

class AppSettings(BaseModel):
    region: Region = Field(default_factory=Region)
    reference_image: str = "reference_icon.png"
    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    polling_interval_ms: int = Field(default=250, ge=50, le=10_000)
    always_on_top: bool = True
    warning_mode: Literal["disabled", "builtin", "custom"] = "builtin"
    warning_wav: str = ""
```

Resolve relative image and WAV paths from `PROJECT_ROOT`. Save with `model_dump_json(indent=2)`, UTF-8, a sibling temporary file, then `Path.replace`. Do not silently replace malformed existing JSON.

- [ ] **Step 4: Run configuration tests**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS.

### Task 2: Template matching and detection state

**Files:**
- Create: `src_package/models.py`
- Create: `src_package/services/__init__.py`
- Create: `src_package/services/template_matcher.py`
- Create: `tests/test_template_matcher.py`

**Interfaces:**
- Produces: `DetectionResult(score: float, available: bool)` and `TemplateMatcher(reference_path: Path, threshold: float)` with `match(frame_bgr: numpy.ndarray) -> DetectionResult`.

- [ ] **Step 1: Write failing synthetic-image tests**

Generate non-uniform NumPy patterns, place a pattern inside a larger source image, and assert an exact match is available with a near-1 score. Test an absent pattern is below threshold and a template larger than the frame raises `ValueError` with a clear message.

- [ ] **Step 2: Run the matcher tests**

Run: `python -m pytest tests/test_template_matcher.py -v`
Expected: FAIL because matcher modules do not exist.

- [ ] **Step 3: Implement the matcher**

Load the template once with `cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)`. Reject unreadable or empty templates. Convert BGR/BGRA frames with `cv2.cvtColor`, reject undersized frames, calculate the maximum score using `cv2.minMaxLoc(cv2.matchTemplate(..., cv2.TM_CCOEFF_NORMED))`, clamp non-finite values safely, and compare with `>= threshold`.

- [ ] **Step 4: Run matcher tests**

Run: `python -m pytest tests/test_template_matcher.py -v`
Expected: PASS.

### Task 3: Capture, monitoring, and alert transitions

**Files:**
- Create: `src_package/services/screen_capture.py`
- Create: `src_package/services/alerts.py`
- Create: `src_package/services/monitor.py`
- Create: `tests/test_alerts.py`
- Create: `tests/test_monitor.py`

**Interfaces:**
- Consumes: `Region`, `AppSettings`, `DetectionResult`, and `TemplateMatcher.match`.
- Produces: `ScreenCapturer.capture(region: Region) -> numpy.ndarray`, `AvailabilityTransition.update(available: bool) -> bool`, `play_warning(settings: AppSettings) -> None`, and `DetectionMonitor(settings, on_result, on_error)` with `start()`, `stop()`, and `is_running`.

- [ ] **Step 1: Write failing transition and monitor tests**

Verify transition sequences: initial false does not warn; true then false warns once; repeated false does not warn; true then false warns again. Use fake capturer and matcher objects to verify the monitor publishes results and stops promptly without accessing the real screen.

- [ ] **Step 2: Run service tests**

Run: `python -m pytest tests/test_alerts.py tests/test_monitor.py -v`
Expected: FAIL because service implementations do not exist.

- [ ] **Step 3: Implement capture, warning, and monitor services**

`ScreenCapturer` passes exactly `{left: x, top: y, width, height}` to MSS and returns the BGRA NumPy array. `AvailabilityTransition` stores `bool | None` and returns true only for a prior `True` followed by `False`. `play_warning` uses `winsound.MessageBeep` for built-in mode and asynchronous `winsound.PlaySound` with `SND_FILENAME | SND_ASYNC` for custom mode. `DetectionMonitor` owns a daemon thread and `threading.Event`; it invokes callbacks but never touches Tkinter widgets directly.

- [ ] **Step 4: Run service tests**

Run: `python -m pytest tests/test_alerts.py tests/test_monitor.py -v`
Expected: PASS.

### Task 4: Tkinter application

**Files:**
- Create: `src_package/app.py`
- Create: `run.py`
- Create: `tests/test_app.py`

**Interfaces:**
- Consumes: configuration and monitoring interfaces from Tasks 1-3.
- Produces: `VillagerDetectorApp(root: tkinter.Tk)` and `main() -> None`.

- [ ] **Step 1: Write failing UI-independent tests**

Extract and test `settings_from_values(values: Mapping[str, str | bool]) -> AppSettings` so invalid numeric values and missing custom WAV paths report useful `ValueError` messages. Test that valid form values map to the exact region, threshold, interval, topmost, and warning settings.

- [ ] **Step 2: Run application tests**

Run: `python -m pytest tests/test_app.py -v`
Expected: FAIL because `src_package.app` does not exist.

- [ ] **Step 3: Implement the responsive UI**

Build a compact Tkinter window with a large status label, confidence label, region fields, reference browser, threshold and interval fields, topmost checkbox, warning-mode selector, WAV browser, Save, Start, and Stop buttons. Queue worker callbacks with `queue.Queue`; drain them using `root.after`. Use green for available, red for unavailable, and neutral grey before monitoring. Validate and save before Start, stop the worker before replacing it, and stop cleanly on window close.

- [ ] **Step 4: Add the entry point**

`run.py` imports and calls `src_package.app.main`. Use a guarded `if __name__ == "__main__":` entry point.

- [ ] **Step 5: Run application tests**

Run: `python -m pytest tests/test_app.py -v`
Expected: PASS.

### Task 5: Documentation and full verification

**Files:**
- Create: `README.md`
- Create: `.gitignore`
- Modify only if defects are found: source and test files from Tasks 1-4.

**Interfaces:**
- Consumes: the complete application.
- Produces: installation, reference-image, coordinate-calibration, launch, and troubleshooting instructions.

- [ ] **Step 1: Document setup and use**

Explain `python -m pip install -e .`, placing or browsing to a cropped icon image, setting physical-pixel X/Y/width/height, launching with `python run.py`, interpreting confidence, tuning `0.85`, and selecting warning behavior. State explicitly that the app is local-only and input-free.

- [ ] **Step 2: Run the full automated suite**

Run: `python -m pytest -v`
Expected: all tests PASS.

- [ ] **Step 3: Run static compilation**

Run: `python -m compileall -q src_package run.py`
Expected: exit code 0.

- [ ] **Step 4: Run an import smoke check**

Run: `python -c "from src_package.app import VillagerDetectorApp; from src_package.services.template_matcher import TemplateMatcher; print('imports ok')"`
Expected: prints `imports ok` and exits 0 without capturing the screen or opening a window.

- [ ] **Step 5: Report manual limitation**

State that live in-game detection cannot be calibrated until the user supplies the reference icon and region coordinates. Do not claim real-game accuracy from synthetic tests.
