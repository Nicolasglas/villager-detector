# Villager Detector

A small Windows desktop utility that watches one configured UI region and uses local OpenCV template matching to report whether a villager/engineer icon is available.

Everything stays on the local computer: there is no LLM, no API or network service, no game input or keyboard/mouse control, and no frame/image writing. The app only captures the selected screen rectangle into memory, compares it with a user-supplied reference image, displays the result, and optionally plays a warning sound.

## Requirements and installation

- Windows
- Python 3.11 or newer

From this project directory, install the package and its dependencies:

```console
python -m pip install -e .
```

## Reference image and capture region

1. Take a tightly cropped image of the villager/engineer icon exactly as it appears at the display scale used while playing. PNG is recommended; JPG, JPEG, and BMP are also accepted.
2. Save it anywhere locally. Enter its path in **Reference image**, or select it with **Browse…**. A relative path starts at the project directory when running from source, or the folder containing `VillagerDetector.exe` when packaged.
3. Set **X**, **Y**, **Width**, and **Height** in physical screen pixels so the rectangle contains only the target UI region where the icon can appear. Keep this region as small and stable as practical, but at least as large as the reference image.

## Run

The app uses a PySide6 desktop UI. From the project directory, launch it with:

```console
python run.py
```

The main window starts with the detector status and monitoring controls. Click
the **⚙ cog** button in the upper-right of the content panel to open the
settings drawer, where you can configure the reference image, capture region,
threshold, polling interval, always-on-top behavior, and warning sound. Save
Settings writes the values to `settings.json`; Start monitoring also validates
and saves them before monitoring begins.

## Windows EXE

A prebuilt one-folder application is located at:

```text
dist\VillagerDetector\VillagerDetector.exe
```

Keep the entire `VillagerDetector` folder together. Double-click
`VillagerDetector.exe` to run it; Python does not need to be installed on the
computer running the packaged app. `settings.json` is stored beside the EXE.

To install the exact tested build dependencies and rebuild from source:

```console
python -m pip install -e ".[dev]"
python build_exe.py
```

The build replaces generated files under `build\` and
`dist\VillagerDetector\`.

## Create a shareable portable ZIP

After building the one-folder application, create a clean package containing
the current settings, configured reference image, and configured custom WAV:

```console
python build_share.py
```

This writes `dist\VillagerDetector-Share.zip`. It preserves the exact X, Y,
Width, and Height values from the source `settings.json`, copies configured
media into the ZIP, and replaces only the media paths with safe package-relative
paths. Absolute source paths are not written into the shared settings. The
builder fails instead of creating a broken package when the executable,
settings, reference image, or configured custom WAV is missing or invalid.

Use `--force` only when intentionally replacing an existing share ZIP:

```console
python build_share.py --force
```

The package is local-only and contains no API keys or network service. Send the
ZIP, then have the recipient extract the whole folder and run
`VillagerDetector.exe`. They can edit `settings.json` or use the Settings UI;
their changes stay in their extracted copy.

- **Start** validates and saves the current settings, then begins monitoring.
- **Stop** stops monitoring without closing the app.
- **Save Settings** validates and writes the form values to `settings.json` without starting monitoring.
- **Always on top** keeps the detector window above other windows.
- **Test capture** grabs the chosen region once and reports what the detector would currently see there.

The status is **green** when the best template-match score meets the threshold (`VILLAGER AVAILABLE`) and **red** when it does not (`VILLAGER NOT AVAILABLE`). The current normalized match score is shown as a confidence percentage below the status.

A small message line under the confidence shows where the capture region sits in physical screen coordinates (which monitor it is on, and whether it extends past that monitor's edge). **Test capture** captures the chosen region once and reports its dimensions, whether the frame is entirely black, and the current match score — handy for calibrating the region and reference without starting continuous monitoring.

## Calibration

The default confidence threshold is `0.85`. For practical calibration, try values around `0.8`–`0.9`: raise the threshold to reduce false positives or lower it to reduce false negatives. The default polling interval is `250` ms; this controls the delay between checks and accepts values from 50 to 10,000 ms.

Real-game accuracy is not guaranteed by the bundled code alone. It requires your own reference image and local calibration for the game's resolution, UI scale, display scaling, colors, and capture region.

## Warning sound

Choose **disabled**, **builtin**, or **custom**. The built-in option uses the Windows system beep. Custom mode requires an existing `.wav` file selected in **Warning WAV**.

A warning plays once when state changes from available to unavailable. It does not repeat while the state remains unavailable, and an initial unavailable result does not warn.

## Troubleshooting

- **Missing or unreadable image:** verify the reference path, file extension, and read permissions. Relative paths start at the project directory in source mode and the EXE folder in packaged mode. Use **Browse…** to avoid typing mistakes.
- **Region outside every monitor:** the detector refuses (rather than silently returning black) when the X/Y/width/height rectangle does not overlap any physical monitor, and prints the detected monitor layout so you can correct the coordinates.
- **Detector can't see a fullscreen game:** normal desktop capture uses MSS/GDI. If it returns black, the detector automatically tries DXcam/Windows Desktop Duplication, which supports exclusive-fullscreen Direct3D applications. If the GPU backend is unavailable or the game/driver blocks capture, the message line warns you and **Test capture** reports that fullscreen capture was unavailable. For **Age of Empires IV**, Borderless or Windowed mode remains the most reliable option.
- **Template larger than the capture:** increase the region width/height or crop the reference more tightly. Both template dimensions must fit inside the captured region.
- **Display scaling or window movement:** X/Y/width/height are physical pixels. Keep the game window and target UI in a fixed position, and recapture/recalibrate the reference after changing resolution, DPI/display scaling, UI scale, monitor, or window position.
- **False positives:** tighten the capture region, use a cleaner/more distinctive reference, or raise the threshold toward `0.9`.
- **False negatives:** confirm the reference matches the current appearance and scale, ensure the full icon is inside the region, or lower the threshold toward `0.8`.
