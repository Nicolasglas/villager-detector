from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from src_package.config import AppSettings
from src_package.services import alerts
from src_package.services.alerts import AvailabilityTransition, play_warning


@pytest.mark.parametrize(
    ("states", "warnings"),
    [
        ([False], [False]),
        ([False, False, False], [False, False, False]),
        ([True, False], [False, True]),
        ([True, False, False], [False, True, False]),
        ([True, False, True, False], [False, True, False, True]),
    ],
)
def test_availability_transition_warns_only_on_true_to_false(
    states: list[bool], warnings: list[bool]
) -> None:
    transition = AvailabilityTransition()

    assert [transition.update(state) for state in states] == warnings


class FakeWinSound:
    SND_FILENAME = 1
    SND_ASYNC = 2

    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def MessageBeep(self) -> None:
        self.calls.append(("beep",))

    def PlaySound(self, path: str, flags: int) -> None:
        self.calls.append(("play", path, flags))


def test_disabled_warning_has_no_sound_side_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeWinSound()
    monkeypatch.setattr(alerts, "winsound", fake)
    settings = AppSettings(warning_mode="disabled", warning_wav="missing.wav")

    play_warning(settings)

    assert fake.calls == []


def test_builtin_warning_dispatches_message_beep(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeWinSound()
    monkeypatch.setattr(alerts, "winsound", fake)

    play_warning(AppSettings(warning_mode="builtin"))

    assert fake.calls == [("beep",)]


def test_custom_warning_plays_existing_wav_asynchronously(
    wav_file_factory: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    wav_path = wav_file_factory("alert.WAV")
    fake = FakeWinSound()
    monkeypatch.setattr(alerts, "winsound", fake)

    play_warning(AppSettings(warning_mode="custom", warning_wav=str(wav_path)))

    assert fake.calls == [("play", str(wav_path.resolve()), 3)]


@pytest.mark.parametrize("filename", ["missing.wav", "alert.mp3"])
def test_custom_warning_rejects_missing_or_non_wav_file(
    tmp_path: Path, filename: str
) -> None:
    candidate = tmp_path / filename
    if candidate.suffix == ".mp3":
        candidate.write_bytes(b"not wav")

    with pytest.raises(ValueError, match="existing .wav"):
        AppSettings(warning_mode="custom", warning_wav=str(candidate))


def test_custom_warning_revalidates_wav_before_playback(
    wav_file_factory: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = wav_file_factory("alert.wav")
    settings = AppSettings(warning_mode="custom", warning_wav=str(candidate))
    candidate.write_bytes(b"corrupt after settings validation")
    monkeypatch.setattr(alerts, "winsound", SimpleNamespace())

    with pytest.raises(ValueError, match="not a valid WAV"):
        play_warning(settings)
