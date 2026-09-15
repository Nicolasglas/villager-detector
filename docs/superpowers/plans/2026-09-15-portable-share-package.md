# Portable Share Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a secure local-only Windows ZIP containing the tested EXE, exact settings coordinates, configured image, and configured sound.

**Architecture:** Add a focused `build_share.py` module that validates inputs, stages a clean package, copies the EXE folder and configured assets, normalizes media paths in a copied settings JSON, writes documentation and SHA-256 hashes, then creates a ZIP. Existing runtime behavior remains unchanged; the builder refuses unsafe or incomplete inputs.

**Tech Stack:** Python 3.11+, pathlib, tempfile, shutil, zipfile, hashlib, Pydantic settings model, pytest.

**Spec:** `docs/superpowers/specs/2026-09-15-portable-share-package-design.md`

## Global Constraints

- Windows portable ZIP; no installer, admin rights, registry writes, network calls, or secrets.
- Preserve exact `region.x`, `region.y`, `region.width`, and `region.height` values from the source settings.
- Copy the configured reference image and custom WAV when configured; fail if required assets are missing or invalid.
- Never expose original absolute media paths in the shared `settings.json`.
- Never modify the source settings or existing `dist/VillagerDetector` folder.
- Do not overwrite an existing output ZIP without `--force`.

---

### Task 1: Add package-builder validation and staging logic

**Files:**
- Create: `build_share.py`
- Test: `tests/test_build_share.py`

**Interfaces:**
- Produces `build_share_package(source_app_dir: Path, source_settings_path: Path, output_zip: Path, *, force: bool = False) -> Path`.
- Produces `SharePackageError` for actionable validation failures.
- Keeps `main(argv: Sequence[str] | None = None) -> int` as the CLI entry point.

- [ ] **Step 1: Write failing tests** for preserving coordinates, normalizing copied asset paths, copying custom WAV, missing asset failure, path traversal failure, and refusing overwrite.
- [ ] **Step 2: Run `pytest tests/test_build_share.py -v` and confirm the new builder symbols are missing.
- [ ] **Step 3: Implement validation and staging with `Path.resolve(strict=True)`, source-root containment checks, `tempfile.TemporaryDirectory`, and `shutil.copytree`/`copy2`.
- [ ] **Step 4: Implement JSON rewriting by copying the Pydantic-validated settings data and changing only `reference_image` and custom `warning_wav` to safe package-relative filenames; leave region values unchanged.
- [ ] **Step 5: Implement ZIP creation with stable relative archive names and `SHA256SUMS.txt` hashes for all files except the hash manifest itself.
- [ ] **Step 6: Run the focused tests and confirm they pass.

### Task 2: Add CLI and recipient documentation

**Files:**
- Modify: `build_share.py`
- Modify: `README.md`
- Test: `tests/test_build_share.py`

**Interfaces:**
- CLI command: `python build_share.py --source-app-dir dist/VillagerDetector --settings settings.json --output dist/VillagerDetector-Share.zip`.
- `--force` explicitly permits replacing the requested output ZIP.

- [ ] **Step 1: Add CLI tests for default paths, explicit paths, `--force`, and non-zero failure output.
- [ ] **Step 2: Add `argparse` CLI handling and concise stderr errors without tracebacks for expected input failures.
- [ ] **Step 3: Add `README.txt` generation describing extraction, running `VillagerDetector.exe`, editing `settings.json`, and asset requirements.
- [ ] **Step 4: Document the share-build command and security behavior in `README.md`.
- [ ] **Step 5: Run `pytest tests/test_build_share.py -v`.

### Task 3: Build and verify the real share artifact

**Files:**
- Generated: `dist/VillagerDetector-Share.zip` only if all configured assets exist.

- [ ] **Step 1: Run `pytest` for the full suite.
- [ ] **Step 2: Run the share-builder against the existing EXE folder and current settings.
- [ ] **Step 3: Inspect the ZIP listing and extracted `settings.json`; verify coordinates, relative paths, copied image/WAV, README, and hashes.
- [ ] **Step 4: If the configured image or custom WAV is missing, report the exact blocker and do not create a fabricated package.
