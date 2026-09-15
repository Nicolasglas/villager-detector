# Portable Share Package Design

## Goal
Create a local-only Windows portable ZIP that a recipient can unzip and run, while preserving the exact calibrated coordinates and configured reference image/sound and allowing the recipient to edit settings independently.

## Approach
Add a focused `build_share.py` packaging command. It consumes the already-built one-folder executable, validates the current `settings.json`, copies the configured reference image and custom WAV into a clean staging directory, rewrites only asset paths to safe package-relative names, preserves all coordinate values and other settings, writes usage/integrity files, and produces a ZIP.

The builder fails closed when required inputs are missing or invalid. It never reads `.env`, makes network requests, includes absolute source paths in the shared settings, or modifies the source settings file or existing distribution. The recipient can edit `settings.json` or use the app UI; changes are local to their extracted copy.

## Package contents

- `VillagerDetector.exe` and its existing `_internal` directory from the tested one-folder build.
- `settings.json` with the exact source region coordinates and other values, with bundled asset paths normalized to package-relative filenames.
- The configured reference image.
- The configured custom WAV when `warning_mode` is `custom`.
- `README.txt` explaining extraction, first run, settings editing, and that the package is Windows-only/local-only.
- `SHA256SUMS.txt` containing hashes for package files to support integrity checks.

## Security and error handling

- Resolve configured relative media paths from the source project root; preserve absolute paths only for locating input files, never in the output JSON.
- Require the executable, source settings, reference image, and custom WAV when configured. Reject missing, directory, unsupported, or invalid WAV files with actionable errors.
- Reject path traversal and symlink escapes when copying configured assets.
- Stage into a fresh temporary directory and create the ZIP only after all validation and copies succeed.
- Do not overwrite an existing output ZIP unless an explicit `--force` flag is supplied.

## Verification

Unit tests cover path normalization, coordinate preservation, asset copying, custom WAV requirements, missing-input failures, traversal protection, hash manifest creation, and refusal to overwrite. The narrow test suite and then the full `pytest` suite must pass. A real package build will be run using the existing `dist/VillagerDetector` executable folder; if the current configured image or WAV is absent, the builder must report that blocker rather than fabricate an asset.
