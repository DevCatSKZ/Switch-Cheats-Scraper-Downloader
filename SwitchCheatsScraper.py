#!/usr/bin/env python3
"""Switch Cheats Scraper & Downloader — application launcher (v1.0, by DevCatSKZ).

Start the app with:

    python SwitchCheatsScraper.py

or run the built ``SwitchCheatsScraper.exe``. This is the single, obvious entry
point (replaces the old ``python gui.py`` / ``scraper.py gui``).

When running as a packaged .exe it stores all data (database, downloads,
settings, login profile) next to the executable (portable). If that folder is
not writable (e.g. installed under Program Files), it falls back to the
per-user LOCALAPPDATA folder so the app still works.
"""
import os
import sys
from pathlib import Path


def _is_writable(d: Path) -> bool:
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def _data_dir() -> Path:
    """Where the packaged app stores its data.

    Primary: the folder that contains the .exe (portable — data stays with the
    program). Fallback: %LOCALAPPDATA%\\SwitchCheatsScraper when the exe folder
    is read-only. In development (not frozen): next to the code.
    """
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent
    exe_dir = Path(sys.executable).resolve().parent
    if _is_writable(exe_dir):
        return exe_dir
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / "SwitchCheatsScraper"


def main() -> None:
    data_dir = _data_dir()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    # Share the data folder with gui.py / playwright_scrape.py (read before they
    # compute their own paths).
    os.environ.setdefault("SCS_DATA_DIR", str(data_dir))
    if getattr(sys, "frozen", False):
        # Playwright browsers bundled next to the executable (installer ships
        # them); avoids any runtime download.
        os.environ.setdefault(
            "PLAYWRIGHT_BROWSERS_PATH",
            str(Path(sys.executable).resolve().parent / "ms-playwright"))

    from gui import run_gui
    run_gui()


if __name__ == "__main__":
    main()
