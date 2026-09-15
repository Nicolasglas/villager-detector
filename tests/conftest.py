"""Shared pytest support for local media and offscreen Qt tests."""

import os
import wave
from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Reuse one offscreen QApplication without entering its event loop."""

    return QApplication.instance() or QApplication([])


@pytest.fixture
def wav_file_factory(tmp_path: Path) -> Callable[[str], Path]:
    """Create a minimal structurally valid mono PCM WAV."""

    def create(name: str = "warning.wav") -> Path:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(1)
            wav_file.setframerate(8_000)
            wav_file.writeframes(b"\x80")
        return path

    return create
