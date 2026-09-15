# Villager Availability Detector Design

## Purpose

Create a small Windows desktop program that continuously checks a fixed Age of Empires UI region for a user-provided villager or engineer icon. The program is visual-only: it must not click, type, control the game, or transmit data.

## User interface

The Tkinter window provides:

- A large green `VILLAGER AVAILABLE` state when the icon is detected.
- A large red `VILLAGER NOT AVAILABLE` state when it is not detected.
- The current OpenCV template-matching confidence score.
- Start and Stop controls.
- An always-on-top option.
- Editable settings for screen-region X, Y, width, and height.
- A reference-image path and file browser.
- A confidence threshold with a default of `0.85`.
- A polling interval in milliseconds.
- Warning-sound controls: disabled, built-in Windows alert, or custom WAV file.
- A Save Settings action.

The UI must remain responsive while monitoring.

## Architecture

The application uses small, focused modules:

- `config.py`: validates and atomically saves non-secret settings in `settings.json`, resolving paths from the project root.
- `models.py`: contains detection-state data models.
- `services/screen_capture.py`: captures only the configured rectangle with MSS.
- `services/template_matcher.py`: loads the reference icon and calculates the best normalized OpenCV template-match score.
- `services/monitor.py`: coordinates capture and matching on a background thread and publishes results to the UI.
- `services/alerts.py`: plays either a built-in Windows sound or a selected WAV file.
- `app.py`: owns the Tkinter interface, validates user input, starts and stops monitoring, and updates widgets on the Tkinter thread.

## Detection flow

1. The user chooses a cropped reference icon and configures a screen rectangle.
2. On Start, the app validates all settings and loads the reference image.
3. MSS repeatedly captures only the configured rectangle.
4. Both images are represented in grayscale for lightweight matching.
5. `cv2.matchTemplate` with `TM_CCOEFF_NORMED` produces a confidence score from the best match.
6. A score greater than or equal to the configured threshold maps to `VILLAGER AVAILABLE`; a lower score maps to `VILLAGER NOT AVAILABLE`.
7. The UI receives results through a thread-safe queue and updates the status and confidence.
8. A warning plays once when the state transitions from available to unavailable. It does not repeat while the state remains unavailable. The initial unavailable reading does not play a warning because no loss transition has occurred.

## Configuration

`settings.json` stores only non-secret preferences:

- Region coordinates and dimensions.
- Reference-image path.
- Confidence threshold.
- Polling interval.
- Always-on-top preference.
- Warning mode.
- Optional custom WAV path.

Invalid settings produce a visible error instead of silently falling back. Writes use a temporary file followed by replacement. The reference filename remains easy to change either in the UI or directly in `settings.json`.

## Error handling

The program reports clear errors for:

- Missing or unreadable reference images.
- A reference image larger than the configured capture region.
- Invalid coordinates, dimensions, thresholds, or intervals.
- Missing or invalid custom WAV files.
- Screen-capture failures.

A monitoring failure stops monitoring safely and leaves the UI usable for correction and restart. Errors must not be hidden by broad exception handling.

## Dependencies and privacy

Runtime dependencies are limited to OpenCV and MSS. Tkinter and `winsound` come from the Windows Python standard library. The application uses no LLM, external API, telemetry, or network connection. Captured frames remain in memory and are not saved.

## Testing

Automated tests will cover:

- Valid and invalid configuration values.
- Settings serialization and atomic persistence behavior.
- Exact and absent synthetic template matches.
- Rejection when the template is larger than the source image.
- Threshold-to-state conversion.
- Warning only on an available-to-unavailable transition.

A smoke check will import and construct the application without starting continuous capture. Real in-game accuracy still requires the user-provided reference image and calibration of the screen rectangle and threshold on the user’s display.

## Acceptance criteria

- The app captures only the configured screen rectangle.
- It continuously displays one of the two required states and a confidence score.
- Green represents detected; red represents not detected.
- Threshold, capture interval, screen region, reference image, topmost behavior, and warning settings are editable.
- Built-in and custom WAV warnings are supported.
- A warning plays once per available-to-unavailable transition.
- Monitoring never sends input to the game.
- All automated tests pass.
