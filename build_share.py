"""Build a portable Villager Detector share ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from collections.abc import Sequence
import wave
import zipfile

from src_package.config import AppSettings

APP_NAME = "VillagerDetector"
DEFAULT_SOURCE_APP_DIR = Path("dist") / APP_NAME
DEFAULT_SETTINGS_PATH = Path("settings.json")
DEFAULT_OUTPUT_ZIP = Path("dist") / f"{APP_NAME}-Share.zip"


class SharePackageError(RuntimeError):
    """Raised when a share package cannot be built safely."""


def _required_file(path: Path, description: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise SharePackageError(f"Missing {description}: {path}") from exc
    if not resolved.is_file():
        raise SharePackageError(f"{description} is not a file: {path}")
    return resolved


def _resolve_asset(value: str, settings_root: Path, description: str) -> Path:
    candidate = Path(value)
    path = candidate if candidate.is_absolute() else settings_root / candidate
    resolved = _required_file(path, description)
    if not candidate.is_absolute():
        root = settings_root.resolve()
        if root != resolved.parent and root not in resolved.parents:
            raise SharePackageError(
                f"{description} must remain inside the settings directory: {value}"
            )
    return resolved


def _validate_wav(path: Path) -> None:
    try:
        with wave.open(str(path), "rb") as wav_file:
            if (
                wav_file.getnchannels() <= 0
                or wav_file.getsampwidth() <= 0
                or wav_file.getframerate() <= 0
            ):
                raise SharePackageError(f"Custom warning WAV has invalid audio parameters: {path}")
    except (EOFError, OSError, wave.Error) as exc:
        raise SharePackageError(f"Custom warning is not a valid WAV file: {path}") from exc


def _copy_asset(source: Path, stage: Path, label: str) -> str:
    destination_name = Path("assets") / f"{label}{source.suffix.lower()}"
    destination = stage / destination_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination_name.as_posix()


def _copy_app_folder(source_app_dir: Path, stage: Path) -> None:
    source = _required_file(source_app_dir / f"{APP_NAME}.exe", "application executable")
    app_root = source_app_dir.resolve()
    for item in app_root.rglob("*"):
        relative = item.relative_to(app_root)
        if relative == Path("settings.json") or not item.is_file():
            continue
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)
    if not (stage / source.name).is_file():
        raise SharePackageError(f"Could not stage application executable: {source}")


def _write_readme(stage: Path) -> None:
    (stage / "README.txt").write_text(
        "Villager Detector portable package\n"
        "=================================\n\n"
        "Run VillagerDetector.exe on Windows. Python is not required.\n\n"
        "The included settings.json contains the supplied screen coordinates and\n"
        "the bundled reference image/sound paths. You can edit settings.json or\n"
        "change settings in the application; changes apply only to this copy.\n\n"
        "Keep the executable, _internal folder, settings.json, and assets folder\n"
        "together. This application captures and processes frames locally and\n"
        "does not use a network service. SHA256SUMS.txt contains integrity hashes.\n",
        encoding="utf-8",
    )


def _write_hashes(stage: Path) -> None:
    files = sorted(
        path for path in stage.rglob("*") if path.is_file() and path.name != "SHA256SUMS.txt"
    )
    lines = []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(stage).as_posix()}")
    (stage / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_share_settings(path: Path) -> AppSettings:
    """Validate settings without assuming the source file is project-rooted."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        validation_data = dict(raw)
        if validation_data.get("warning_mode") == "custom":
            validation_data["warning_mode"] = "builtin"
            validation_data["warning_wav"] = ""
        settings = AppSettings.model_validate(validation_data)
    except (OSError, ValueError, TypeError) as exc:
        raise SharePackageError(f"Could not validate settings: {exc}") from exc
    if raw.get("warning_mode") == "custom":
        settings.warning_mode = "custom"
        settings.warning_wav = str(raw.get("warning_wav", ""))
    return settings


def build_share_package(
    source_app_dir: Path = DEFAULT_SOURCE_APP_DIR,
    source_settings_path: Path = DEFAULT_SETTINGS_PATH,
    output_zip: Path = DEFAULT_OUTPUT_ZIP,
    *,
    force: bool = False,
) -> Path:
    """Create a clean portable ZIP without modifying source files."""
    source_app_dir = source_app_dir.resolve()
    source_settings_path = _required_file(source_settings_path, "settings file")
    output_zip = output_zip.resolve()
    if output_zip.exists() and not force:
        raise SharePackageError(f"Output already exists; use --force to replace it: {output_zip}")

    settings = _load_share_settings(source_settings_path)
    reference = _resolve_asset(
        settings.reference_image, source_settings_path.parent, "reference image"
    )
    if settings.warning_mode == "custom":
        warning_wav = _resolve_asset(
            settings.warning_wav, source_settings_path.parent, "custom warning WAV"
        )
        _validate_wav(warning_wav)
    else:
        warning_wav = None

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="villager-detector-share-") as temporary:
        stage = Path(temporary) / APP_NAME
        stage.mkdir()
        _copy_app_folder(source_app_dir, stage)
        reference_path = _copy_asset(reference, stage, "reference")
        warning_path = _copy_asset(warning_wav, stage, "warning") if warning_wav else ""

        settings_data = settings.model_dump(mode="json")
        settings_data["reference_image"] = reference_path
        if settings.warning_mode == "custom":
            settings_data["warning_wav"] = warning_path
        (stage / "settings.json").write_text(
            json.dumps(settings_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        _write_readme(stage)
        _write_hashes(stage)

        temporary_zip = output_zip.with_suffix(output_zip.suffix + ".tmp")
        if temporary_zip.exists():
            temporary_zip.unlink()
        with zipfile.ZipFile(temporary_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(stage.parent).as_posix())
        if output_zip.exists():
            output_zip.unlink()
        temporary_zip.replace(output_zip)
    return output_zip


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-app-dir", type=Path, default=DEFAULT_SOURCE_APP_DIR)
    parser.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_ZIP)
    parser.add_argument("--force", action="store_true", help="replace an existing output ZIP")
    args = parser.parse_args(argv)
    try:
        output = build_share_package(
            args.source_app_dir, args.settings, args.output, force=args.force
        )
    except SharePackageError as exc:
        parser.exit(1, f"Share package not built: {exc}\n")
    print(f"Built share package: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
