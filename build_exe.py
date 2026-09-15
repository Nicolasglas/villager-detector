"""Build the one-folder Windows Villager Detector executable."""

from pathlib import Path
import shutil

import PyInstaller.__main__


PROJECT_ROOT = Path(__file__).resolve().parent
APP_NAME = "VillagerDetector"
DIST_APP_DIR = PROJECT_ROOT / "dist" / APP_NAME
_BACKUP_SUFFIX = ".buildbackup"


def _backup_settings(dist_app_dir: Path = DIST_APP_DIR) -> Path | None:
    """Copy a user's existing settings beside the app so a rebuild can restore it.

    PyInstaller's COLLECT removes the whole app output directory, so anything
    in it (including a calibrated ``settings.json``) would be lost on rebuild.
    """
    source = dist_app_dir / "settings.json"
    if not source.exists():
        return None
    # Keep the backup outside the directory PyInstaller's COLLECT removes.
    backup = dist_app_dir.parent / Path(dist_app_dir.name + source.name + _BACKUP_SUFFIX)
    shutil.copy2(source, backup)
    print(f"Backed up settings: {backup}")
    return backup


def _restore_settings(backup: Path | None, dist_app_dir: Path = DIST_APP_DIR) -> None:
    """Put a previously backed-up settings file back next to the app."""
    if backup is None:
        return
    backup.replace(dist_app_dir / "settings.json")
    print(f"Restored user settings: {dist_app_dir / 'settings.json'}")


def _seed_default_settings(dist_app_dir: Path = DIST_APP_DIR) -> None:
    """Create packaged defaults when no user settings were available."""
    destination = dist_app_dir / "settings.json"
    if not destination.exists():
        shutil.copy2(PROJECT_ROOT / "settings.json", destination)
        print(f"Copied default settings: {destination}")


def main() -> None:
    """Build the windowed application, preserving a calibrated settings file."""
    backup = _backup_settings()
    try:
        PyInstaller.__main__.run(
            [
                str(PROJECT_ROOT / "run.py"),
                "--name",
                APP_NAME,
                "--onedir",
                "--windowed",
                "--noconfirm",
                "--clean",
                "--distpath",
                str(PROJECT_ROOT / "dist"),
                "--workpath",
                str(PROJECT_ROOT / "build"),
                "--specpath",
                str(PROJECT_ROOT / "build"),
                "--paths",
                str(PROJECT_ROOT),
            ]
        )
    finally:
        _restore_settings(backup)
        if backup is None:
            _seed_default_settings()

    print(f"Built: {DIST_APP_DIR / (APP_NAME + '.exe')}")


if __name__ == "__main__":
    main()