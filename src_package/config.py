from pathlib import Path
import sys
from typing import Literal
import wave

from pydantic import BaseModel, ConfigDict, Field, model_validator

def resolve_project_root() -> Path:
    """Return the writable app directory for source and frozen builds."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = resolve_project_root()
_DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "settings.json"


class Region(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int = 0
    y: int = 0
    width: int = Field(default=400, gt=0)
    height: int = Field(default=300, gt=0)


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region: Region = Field(default_factory=Region)
    reference_image: str = "reference_icon.png"
    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    polling_interval_ms: int = Field(default=250, ge=50, le=10_000)
    always_on_top: bool = True
    warning_mode: Literal["disabled", "builtin", "custom"] = "builtin"
    warning_wav: str = ""

    @model_validator(mode="after")
    def validate_custom_warning(self) -> "AppSettings":
        if self.warning_mode == "custom":
            validate_wav_file(self.warning_wav_path)
        return self

    @staticmethod
    def _resolve_project_path(value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def reference_image_path(self) -> Path:
        return self._resolve_project_path(self.reference_image)

    @property
    def warning_wav_path(self) -> Path:
        return self._resolve_project_path(self.warning_wav)


def validate_wav_file(path: Path) -> Path:
    """Return a valid local WAV path or raise a concise validation error."""
    if path.suffix.lower() != ".wav" or not path.is_file():
        raise ValueError("Custom warning must be an existing .wav file")
    try:
        with wave.open(str(path), "rb") as wav_file:
            if (
                wav_file.getnchannels() <= 0
                or wav_file.getsampwidth() <= 0
                or wav_file.getframerate() <= 0
            ):
                raise ValueError("Custom warning WAV has invalid audio parameters")
            wav_file.readframes(1)
    except (EOFError, OSError, wave.Error) as exc:
        raise ValueError(f"Custom warning is not a valid WAV file: {path}") from exc
    return path


def load_settings(path: Path | None = None) -> AppSettings:
    settings_path = path if path is not None else _DEFAULT_SETTINGS_PATH
    if not settings_path.exists():
        return AppSettings()
    return AppSettings.model_validate_json(settings_path.read_text(encoding="utf-8"))


def save_settings(settings: AppSettings, path: Path | None = None) -> None:
    settings_path = path if path is not None else _DEFAULT_SETTINGS_PATH
    temporary_path = settings_path.with_suffix(settings_path.suffix + ".tmp")
    temporary_path.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
    temporary_path.replace(settings_path)
