<!-- Language: English (below) · Deutsch (further down) -->
**🇬🇧 English** · [🇩🇪 Deutsch](#-anleitung-deutsch)

# Building the EXE + Installer

The app is packaged with **PyInstaller** (one-folder `.exe`) and an optional
**Inno Setup** installer.

## Quick build

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

This produces:
- `dist\SwitchCheatsScraper\SwitchCheatsScraper.exe` — the runnable app
- `Output\SwitchCheatsScraper-Setup.exe` — the installer (if Inno Setup is installed)

## Requirements

- **Python 3.11–3.13** (recommended). PyInstaller wheels for brand-new Python
  releases (e.g. 3.14) can lag behind — if the build fails to install
  PyInstaller, use a 3.12/3.13 virtual environment.
- **Inno Setup 6** for the installer (optional): https://jrsoftware.org/isdl.php
  (put `iscc.exe` on PATH, or the script auto-detects the default install path).

## Manual steps (what build.ps1 does)

```powershell
py -m pip install -r requirements.txt pyinstaller
$env:PLAYWRIGHT_BROWSERS_PATH = "0"    # bundle browsers inside the app
py -m playwright install chromium firefox
py -m PyInstaller --noconfirm SwitchCheatsScraper.spec
iscc installer.iss                     # optional installer
```

## Notes

- **Entry point:** `SwitchCheatsScraper.py` (this replaces the old
  `python gui.py` / `scraper.py gui`). During development you can still just run
  `python SwitchCheatsScraper.py`.
- **User data:** When run as the packaged `.exe`, the app stores its database,
  downloads, settings and login profile **next to the executable** (portable).
  If that folder is read-only (e.g. installed under Program Files as admin), it
  falls back to `%LOCALAPPDATA%\SwitchCheatsScraper`. The installer therefore
  installs **per-user** by default (a writable location). From source it keeps
  everything next to the code, exactly as before.
- **Playwright browsers:** Bundled when built via `build.ps1` (with
  `PLAYWRIGHT_BROWSERS_PATH=0`). If not bundled, the app auto-downloads them on
  first browser use into the data folder.
- **Icon:** Drop an `app.ico` next to the spec to brand the exe/installer.

---

<a id="-anleitung-deutsch"></a>
[🇬🇧 English](#building-the-exe--installer) · **🇩🇪 Deutsch**

# EXE + Installer bauen

Die App wird mit **PyInstaller** (Ein-Ordner-`.exe`) und einem optionalen
**Inno-Setup**-Installer paketiert.

## Schnell-Build

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

Das erzeugt:
- `dist\SwitchCheatsScraper\SwitchCheatsScraper.exe` — die lauffähige App
- `Output\SwitchCheatsScraper-Setup.exe` — den Installer (falls Inno Setup installiert ist)

## Voraussetzungen

- **Python 3.11–3.13** (empfohlen). PyInstaller-Wheels für brandneue
  Python-Versionen (z. B. 3.14) können hinterherhinken — schlägt die Installation
  von PyInstaller fehl, nutze eine 3.12/3.13-Umgebung (virtuelle Umgebung).
- **Inno Setup 6** für den Installer (optional): https://jrsoftware.org/isdl.php
  (`iscc.exe` in den PATH legen, oder das Skript erkennt den Standard-Installationspfad automatisch).

## Manuelle Schritte (was build.ps1 macht)

```powershell
py -m pip install -r requirements.txt pyinstaller
$env:PLAYWRIGHT_BROWSERS_PATH = "0"    # Browser in die App einbetten
py -m playwright install chromium firefox
py -m PyInstaller --noconfirm SwitchCheatsScraper.spec
iscc installer.iss                     # optionaler Installer
```

## Hinweise

- **Einstiegspunkt:** `SwitchCheatsScraper.py` (ersetzt das alte
  `python gui.py` / `scraper.py gui`). Während der Entwicklung kannst du weiterhin
  einfach `python SwitchCheatsScraper.py` starten.
- **Benutzerdaten:** Als paketierte `.exe` speichert die App Datenbank,
  Downloads, Einstellungen und Login-Profil **neben der ausführbaren Datei**
  (portabel). Ist dieser Ordner schreibgeschützt (z. B. Installation unter
  „Programme" mit Adminrechten), weicht sie auf `%LOCALAPPDATA%\SwitchCheatsScraper`
  aus. Der Installer installiert daher standardmäßig **pro Benutzer** (an einen
  beschreibbaren Ort). Aus dem Quellcode heraus bleibt alles neben dem Code,
  genau wie bisher.
- **Playwright-Browser:** Werden beim Build über `build.ps1` eingebettet (mit
  `PLAYWRIGHT_BROWSERS_PATH=0`). Ohne Einbettung lädt die App sie beim ersten
  Browser-Gebrauch automatisch in den Datenordner.
- **Icon:** Lege eine `app.ico` neben die Spec, um exe/Installer zu branden.
