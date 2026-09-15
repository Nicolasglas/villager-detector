"""Availability transitions and Windows warning dispatch."""

try:
    import winsound
except ImportError:  # pragma: no cover - exercised only off Windows
    winsound = None  # type: ignore[assignment]

from src_package.config import AppSettings, validate_wav_file


class AvailabilityTransition:
    """Report each transition from available to unavailable exactly once."""

    def __init__(self) -> None:
        self._previous: bool | None = None

    def update(self, available: bool) -> bool:
        should_warn = self._previous is True and available is False
        self._previous = available
        return should_warn


def play_warning(settings: AppSettings) -> None:
    """Play the warning selected in settings without blocking the caller."""
    if settings.warning_mode == "disabled":
        return
    if winsound is None:
        raise RuntimeError("Warning sounds are unavailable on this platform")
    if settings.warning_mode == "builtin":
        winsound.MessageBeep()
        return

    wav_path = validate_wav_file(settings.warning_wav_path.resolve())
    winsound.PlaySound(
        str(wav_path),
        winsound.SND_FILENAME | winsound.SND_ASYNC,
    )
