from __future__ import annotations

import json
from pathlib import Path
import zipfile
import wave

import pytest

from build_share import SharePackageError, build_share_package


def _wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8000)
        wav_file.writeframes(b"\x00\x00")


def _source(tmp_path: Path, *, custom_sound: bool = True) -> tuple[Path, Path]:
    root = tmp_path / "source"
    app = root / "dist" / "VillagerDetector"
    app.mkdir(parents=True)
    (app / "VillagerDetector.exe").write_bytes(b"exe")
    (app / "_internal").mkdir()
    (app / "_internal" / "runtime.dll").write_bytes(b"runtime")
    image = root / "reference icon.png"
    image.write_bytes(b"png")
    sound = root / "warning.wav"
    _wav(sound)
    settings = root / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "region": {"x": 123, "y": -45, "width": 67, "height": 89},
                "reference_image": image.name,
                "confidence_threshold": 0.85,
                "polling_interval_ms": 250,
                "always_on_top": True,
                "warning_mode": "custom" if custom_sound else "builtin",
                "warning_wav": sound.name if custom_sound else "",
            }
        ),
        encoding="utf-8",
    )
    return app, settings


def test_package_preserves_coordinates_and_bundles_assets(tmp_path: Path) -> None:
    app, settings = _source(tmp_path)
    output = tmp_path / "share.zip"

    build_share_package(app, settings, output)

    with zipfile.ZipFile(output) as archive:
        files = set(archive.namelist())
        document = json.loads(archive.read("VillagerDetector/settings.json"))
        assert document["region"] == {"x": 123, "y": -45, "width": 67, "height": 89}
        assert document["reference_image"] == "assets/reference.png"
        assert document["warning_wav"] == "assets/warning.wav"
        assert "VillagerDetector/assets/reference.png" in files
        assert "VillagerDetector/assets/warning.wav" in files
        assert "VillagerDetector/README.txt" in files
        assert "VillagerDetector/SHA256SUMS.txt" in files
        assert str(settings.parent) not in archive.read("VillagerDetector/settings.json").decode()


def test_package_requires_reference_image(tmp_path: Path) -> None:
    app, settings = _source(tmp_path)
    settings.write_text(settings.read_text(encoding="utf-8").replace("reference icon.png", "missing.png"), encoding="utf-8")

    with pytest.raises(SharePackageError, match="reference image"):
        build_share_package(app, settings, tmp_path / "share.zip")


def test_package_requires_custom_wav(tmp_path: Path) -> None:
    app, settings = _source(tmp_path)
    settings.write_text(settings.read_text(encoding="utf-8").replace("warning.wav", "missing.wav"), encoding="utf-8")

    with pytest.raises(SharePackageError, match="custom warning WAV"):
        build_share_package(app, settings, tmp_path / "share.zip")


def test_package_rejects_relative_asset_escape(tmp_path: Path) -> None:
    app, settings = _source(tmp_path)
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"png")
    settings.write_text(
        settings.read_text(encoding="utf-8").replace("reference icon.png", "../outside.png"),
        encoding="utf-8",
    )

    with pytest.raises(SharePackageError, match="inside the settings directory"):
        build_share_package(app, settings, tmp_path / "share.zip")


def test_package_refuses_existing_output_without_force(tmp_path: Path) -> None:
    app, settings = _source(tmp_path)
    output = tmp_path / "share.zip"
    output.write_bytes(b"existing")

    with pytest.raises(SharePackageError, match="already exists"):
        build_share_package(app, settings, output)


def test_builtin_mode_does_not_require_or_bundle_wav(tmp_path: Path) -> None:
    app, settings = _source(tmp_path, custom_sound=False)

    output = build_share_package(app, settings, tmp_path / "share.zip")

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        document = json.loads(archive.read("VillagerDetector/settings.json"))
        assert document["warning_mode"] == "builtin"
        assert document["warning_wav"] == ""
        assert not any(name.endswith("warning.wav") for name in names)


def test_cli_source_paths_are_not_written_to_settings(tmp_path: Path) -> None:
    app, settings = _source(tmp_path)
    output = tmp_path / "share.zip"

    build_share_package(app, settings, output)

    with zipfile.ZipFile(output) as archive:
        document = archive.read("VillagerDetector/settings.json").decode("utf-8")
        assert str(tmp_path) not in document
