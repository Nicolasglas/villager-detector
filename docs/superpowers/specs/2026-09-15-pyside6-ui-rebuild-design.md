# PySide6 UI rebuild design

## Design read

This is a modern Windows desktop utility for a local screen-monitoring tool. The visual language is calm, spacious, blue-white, and status-led. The main screen should answer what the detector is doing immediately. Configuration is secondary and lives behind a settings cog.

## Goals

- Replace the Tkinter presentation layer with PySide6.
- Match the supplied reference: rounded white surface, pale blue shell, custom title bar, central status, and top-right settings control.
- Preserve the existing detector engine and local-only behaviour.
- Preserve `settings.json` compatibility and all current validation rules.
- Preserve monitoring, capture, matching, warning sounds, always-on-top, test capture, region selection, and close behaviour.
- Improve state visibility, keyboard focus, DPI handling, and future maintainability.

## Non-goals

- No change to OpenCV matching or screen-capture algorithms.
- No network, API, LLM, telemetry, or cloud functionality.
- No database or settings-schema migration.
- No unrelated refactoring.
- No deletion of the old Tkinter implementation until the PySide6 version is verified.

## Architecture

The existing services remain authoritative:

- `src_package/config.py`: settings models, path resolution, load/save, validation.
- `src_package/models.py`: detection result model.
- `src_package/services/`: capture, matching, monitoring, and alerts.

The PySide6 UI becomes a presentation and event-dispatch layer:

- `src_package/app.py`: application entry point and Qt application setup.
- `src_package/ui/main_window.py`: main window, title bar, state composition, lifecycle.
- `src_package/ui/status_widget.py`: central monitoring status and confidence presentation.
- `src_package/ui/settings_panel.py`: settings drawer and form controls.
- `src_package/ui/region_selector.py`: full-screen drag selection overlay.
- `src_package/ui/theme.py`: colours, typography, dimensions, and shared stylesheet.

The monitor runs away from the Qt GUI thread. Worker events are delivered through Qt signals or a safe queued callback. The GUI thread owns all widgets. Stopping and close behaviour must remain bounded and must not freeze the interface.

## Main window

Use a frameless, rounded Qt window only if reliable resize, drag, minimise, maximise, close, and always-on-top behaviour can be implemented and tested. Otherwise retain the native title bar while keeping the custom content shell. The safer implementation should be preferred over pixel-perfect chrome.

The application surface uses:

- pale blue outer background
- white content surface
- soft blue title bar
- rounded corners
- Segoe UI or Segoe UI Variable fallback
- restrained blue accent
- semantic green, red, amber, and neutral states
- no gradients, glow effects, or decorative animation

The title bar contains the feather mark and `Villager Detector` on the left and window controls on the right. The settings cog sits in the content area at the top-right.

## Main status experience

The initial layout is centered and spacious:

1. State icon, using a local vector or Qt-drawn symbol.
2. Large status heading.
3. Short explanatory message.
4. Confidence score when a detection result exists.
5. Wide Start and Stop controls.

Supported states:

- Not monitoring: Start enabled, Stop disabled.
- Monitoring: Start disabled, Stop enabled.
- Villager available: positive semantic colour and confidence.
- Villager not available: warning semantic colour and confidence.
- Stopping: both actions disabled while shutdown completes.
- Error: clear error message, monitoring stopped, settings still accessible.

Button labels and existing command semantics remain stable unless a test or accessibility requirement requires a non-breaking presentation adjustment.

## Settings drawer

The cog opens a right-side panel inside the main window. The first implementation may use an immediate open/close transition. Animation is optional and must not block interaction or violate reduced-motion preferences.

The panel contains all current settings, grouped as:

### Detection

- Reference image path and Browse action.
- Confidence threshold.
- Polling interval.
- Test capture.

### Capture region

- X, Y, Width, Height.
- Select region action.
- Existing physical-pixel semantics and validation.

### Alerts

- Warning mode: disabled, builtin, custom.
- Warning WAV path and Browse action.

### Window

- Always on top.

The Save Settings action is placed at the bottom of the drawer. Existing errors should become inline field or panel messages where practical; exceptional OS and capture failures may remain dialogs with clear titles.

## Region selector

Rebuild the current full-screen overlay as a Qt topmost transparent overlay. Preserve:

- drag from any direction
- physical screen coordinates
- minimum selection size
- Escape cancellation
- return of `(x, y, width, height)`

The selector must work with the existing capture service and multi-monitor coordinates. It must not write screenshots to disk.

## Styling tokens

Initial tokens, subject to visual verification:

- shell background: `#EAF4FF`
- title bar: `#F5F9FE`
- surface: `#FFFFFF`
- primary text: `#101D3A`
- secondary text: `#586987`
- blue accent: `#2368D5`
- available: `#29A66A`
- unavailable: `#C84D58`
- disabled surface: `#E7EEF8`
- border: `#D7E4F2`
- outer radius: 18px
- control radius: 12px

These are design starting points, not claims about exact sampled pixels.

## Error handling and lifecycle

- Do not catch broad exceptions without preserving a user-visible error and useful diagnostic context.
- Keep validation failures local to the settings panel when possible.
- Preserve existing monitor generation or stale-event protection.
- Stop the monitor before destroying the Qt application.
- Do not allow worker callbacks to update widgets directly from a non-GUI thread.
- Preserve the current behaviour for initial unavailable results and warning transitions.

## Testing

Add or update focused tests for:

- Qt application and main-window construction.
- Settings drawer open and close.
- Settings values round-trip through existing `AppSettings` validation.
- Start, stop, and stopping lifecycle.
- Detection result state presentation.
- Worker error handling.
- Region selector output and cancellation where feasible without requiring a physical display.
- Close while monitoring.

Run the focused tests first, then the complete pytest suite. Launch the application for manual verification of initial, monitoring, available, unavailable, stopping, error, settings, region-selection, always-on-top, and close states.

## Migration and rollback

Keep the existing Tkinter implementation in a clearly separated backup or version-control state until PySide6 passes tests and manual smoke verification. Do not remove it in the first implementation slice. The first slice should make the PySide6 path runnable while leaving the detector services unchanged.

## Acceptance criteria

- The app launches with the PySide6 UI.
- The main screen visually follows the supplied reference.
- All existing settings are available behind the cog.
- Existing settings files load and save without schema changes.
- Start, Stop, Test capture, Browse actions, region selection, alerts, and always-on-top still work.
- The GUI remains responsive while monitoring.
- Full pytest passes, or any pre-existing failures are explicitly identified.
- No network or secret access is introduced.
