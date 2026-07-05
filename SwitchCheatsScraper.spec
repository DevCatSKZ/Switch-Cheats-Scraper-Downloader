# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Switch Cheats Scraper.

Build with:  pyinstaller SwitchCheatsScraper.spec
Produces a one-folder app in  dist/SwitchCheatsScraper/  (SwitchCheatsScraper.exe).

Playwright's node driver is bundled (collect_all). The actual browser binaries
are downloaded on first use into the per-user data folder / ms-playwright, so
the installer stays small; ship them alongside the exe to make it fully offline.
"""
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for pkg in ("playwright",):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

# Pure-python deps PyInstaller sometimes misses.
hiddenimports += [
    "lxml", "lxml.etree", "bs4", "PIL", "PIL.Image", "PIL.ImageTk",
    "charset_normalizer", "requests", "urllib3", "tqdm",
]

# Ship app.ico so the Tk window/taskbar icon matches the exe icon.
import os as _os
if _os.path.exists("app.ico"):
    datas += [("app.ico", ".")]

a = Analysis(
    ["SwitchCheatsScraper.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "numpy", "pandas", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="SwitchCheatsScraper",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # windowed GUI app (no console window)
    icon="app.ico" if __import__("os").path.exists("app.ico") else None,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name="SwitchCheatsScraper",
)
