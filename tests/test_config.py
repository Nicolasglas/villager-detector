from collections.abc import Callable
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from src_package import config
from src_package.config import (
    AppSettings,
    PROJECT_ROOT,
    Region,
    load_settings,
    save_settings,
)


def test_default_settings_have_expected_threshold_and_positive_values() -> None:
    settings = AppSettings()

    assert settings.confidence_threshold == 0.85
    assert settings.region.width > 0
    assert settings.region.height > 0
    assert settings.polling_interval_ms > 0


def test_settings_do_not_expose_obs_configuration() -> None:
    obs_fields = {"capture_mode", "obs_host", "obs_port", "obs_source"}

    assert obs_fields.isdisjoint(AppSettings.model_fields)


@pytest.mark.parametrize("threshold", [-0.01, 1.01])
def test_confidence_threshold_outside_unit_interval_is_invalid(threshold: float) -> None:
    with pytest.raises(ValidationError):
        AppSettings(confidence_threshold=threshold)


@pytest.mark.parametrize(("field", "value"), [("width", 0), ("height", -1)])
def test_region_dimensions_must_be_positive(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Region(**{field: value})


def test_relative_media_paths_resolve_from_project_root() -> None:
    settings = AppSettings(reference_image="assets/icon.png", warning_wav="audio/warning.wav")

    assert settings.reference_image_path == PROJECT_ROOT / "assets/icon.png"
    assert settings.warning_wav_path == PROJECT_ROOT / "audio/warning.wav"


def test_frozen_project_root_is_the_executable_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = Path("C:/Apps/VillagerDetector/VillagerDetector.exe")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert config.resolve_project_root() == executable.parent


def test_frozen_default_settings_path_is_beside_executable() -> None:
    executable = Path("C:/Apps/VillagerDetector/VillagerDetector.exe")
    script = f"""
import sys
sys.frozen = True
sys.executable = {str(executable)!r}
from src_package import config
print(config.PROJECT_ROOT)
print(config._DEFAULT_SETTINGS_PATH)
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == [
        str(executable.parent),
        str(executable.parent / "settings.json"),
    ]


def test_absolute_media_paths_are_retained() -> None:
    image_path = Path("C:/images/icon.png")
    wav_path = Path("C:/audio/warning.wav")
    settings = AppSettings(reference_image=str(image_path), warning_wav=str(wav_path))

    assert settings.reference_image_path == image_path
    assert settings.warning_wav_path == wav_path


def test_settings_round_trip_utf8_and_remove_temporary_file(
    tmp_path: Path, wav_file_factory: Callable[[str], Path]
) -> None:
    path = tmp_path / "settings.json"
    wav_path = wav_file_factory("警告.wav")
    settings = AppSettings(
        reference_image="assets/村人.png",
        warning_mode="custom",
        warning_wav=str(wav_path),
    )

    save_settings(settings, path)

    assert load_settings(path) == settings
    assert "村人" in path.read_text(encoding="utf-8")
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_malformed_json_is_not_silently_reset(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ValueError):
        load_settings(path)


def test_invalid_saved_values_are_not_silently_reset(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"confidence_threshold": 2}', encoding="utf-8")

    with pytest.raises(ValidationError):
        load_settings(path)


@pytest.mark.parametrize(
    "document",
    [
        '{"unexpected": true}',
        '{"region": {"x": 0, "y": 0, "width": 4, "height": 3, "depth": 1}}',
    ],
)
def test_unknown_saved_keys_are_rejected(tmp_path: Path, document: str) -> None:
    path = tmp_path / "settings.json"
    path.write_text(document, encoding="utf-8")

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load_settings(path)


def test_custom_warning_rejects_malformed_wav_during_model_parsing(
    tmp_path: Path,
) -> None:
    malformed = tmp_path / "malformed.wav"
    malformed.write_bytes(b"not a wav")

    with pytest.raises(ValidationError, match="not a valid WAV"):
        AppSettings(warning_mode="custom", warning_wav=str(malformed))
