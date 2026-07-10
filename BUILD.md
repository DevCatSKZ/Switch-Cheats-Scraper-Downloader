# Building the EXE + Installer

The app is packaged with **PyInstaller** (one-folder `.exe`) and an **Inno Setup**
installer. A single script builds all three artifacts.

## Quick build

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

This produces:
- `dist\SwitchCheatsScraper\SwitchCheatsScraper.exe` — the runnable app
- `Output\SwitchCheatsScraper-Setup.exe` — the installer (if Inno Setup is installed)
- `Output\SwitchCheatsScraper-portable.zip` — the portable build (zipped `dist` folder)

## Requirements

- **Python 3.11–3.13** (recommended). PyInstaller wheels for brand-new Python
  releases can lag behind — if the build fails to install PyInstaller, use a
  3.12/3.13 virtual environment.
- **Inno Setup 6** for the installer: https://jrsoftware.org/isdl.php. Put
  `iscc.exe` on PATH, or let the script auto-detect the default install paths
  (`%ProgramFiles(x86)%`, `%ProgramFiles%`, or `%LOCALAPPDATA%\Programs\Inno Setup 6`).
  Inno 6 ships the language files used by the installer (English, German, Spanish,
  French, Italian, Japanese) in its `Languages\` folder.

## Manual steps (what build.ps1 does)

```powershell
py -m pip install -r requirements.txt pyinstaller
$env:PLAYWRIGHT_BROWSERS_PATH = "0"    # bundle the browser inside the app
py -m playwright install chromium      # only Chromium is bundled
py -m PyInstaller --noconfirm SwitchCheatsScraper.spec

# Strip any Firefox that Playwright's PyInstaller hook may have bundled,
# so only Chromium ships (Firefox is downloaded on demand at runtime):
Get-ChildItem "dist\SwitchCheatsScraper\_internal\playwright\driver\package\.local-browsers\firefox-*" `
  -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

iscc installer.iss                     # installer -> Output\SwitchCheatsScraper-Setup.exe
Compress-Archive -Path "dist\SwitchCheatsScraper" `
  -DestinationPath "Output\SwitchCheatsScraper-portable.zip" -Force
```

## Notes

- **Only Chromium is bundled** (the "Built-in" browser). **Firefox** is downloaded
  on demand into the per-user data folder the first time it is selected, and
  **Chrome** uses the user's installed Google Chrome — this keeps the app small
  (Setup ~254 MB, portable ~360 MB). Playwright's PyInstaller hook re-adds every
  browser present in the build environment, so `build.ps1` strips Firefox from
  `dist` after the build.
- **Multi-language:** `i18n.py` provides the 6-language interface and is bundled
  automatically (it is imported by `gui.py`). The installer has a **"Program
  language"** page that writes `default_lang.txt` next to the app, so a fresh
  install starts in the chosen language.
- **Entry point:** `SwitchCheatsScraper.py`. It launches the **modern
  Holo-Glass UI (`gui_modern.py`) by default**; `--classic` starts the classic
  single-window UI (from source: `python gui.py`). Both shells share 100% of
  the widgets/handlers (the section builders in `gui.py`) and are always
  bundled (spec `hiddenimports = ["gui", "gui_modern"]`).
- **Installer is PER-USER (no admin, no UAC):** `PrivilegesRequired=lowest`,
  default dir `{autopf}` → `%LOCALAPPDATA%\Programs\Switch Cheats Scraper &
  Downloader`. This is what enables the **silent self-update**: the app folder
  is writable, so updates install with `/SILENT` without elevation and the app
  restarts itself (see `_apply_installer_update` in `gui.py`; downloads are
  verified against GitHub's SHA-256 asset digest first).
- **User data:** When run as the packaged `.exe`, the app stores its database,
  downloads, settings and login profile **next to the executable** (portable).
  If that folder is read-only (a legacy Program Files install), it falls back
  to `%LOCALAPPDATA%\SwitchCheatsScraper`. From source it keeps everything
  next to the code.
- **Icon:** `app.ico` next to the spec brands the exe/installer (and the
  modern UI's header, loaded via PIL).
