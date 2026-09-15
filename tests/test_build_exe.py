"""Build-script behaviour tests that never invoke PyInstaller."""

from pathlib import Path

from build_exe import _backup_settings, _restore_settings


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_backup_and_restore_preserves_existing_user_settings(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _write(dist, "settings.json", "user-calibrated")

    backup = _backup_settings(dist)

    assert backup is not None
    assert backup.read_text(encoding="utf-8") == "user-calibrated"

    # Simulate the rebuild wiping the app folder, then reseeding defaults.
    _write(dist, "settings.json", "default-seed")
    _restore_settings(backup, dist)

    assert (dist / "settings.json").read_text(encoding="utf-8") == "user-calibrated"
    assert not backup.exists()


def test_backup_is_skipped_when_no_settings_exists(tmp_path: Path) -> None:
    dist = tmp_path / "dist"

    assert _backup_settings(dist) is None