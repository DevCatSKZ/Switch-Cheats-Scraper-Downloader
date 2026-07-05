#!/usr/bin/env python3
"""
Graphical interface for the CheatSlips scraper.

Provides:
  - A "Scrape all" button that runs the metadata scraper in the background and
    streams progress into a log box (with a progress bar and a Stop button).
  - A searchable database view (downloaded status, game name, version, title id,
    build id, upload date, cheat count) backed by the same SQLite database
    (cheats.db) that the `metadata` command maintains. The downloaded status is
    reconciled against the actual .txt files on disk.
  - A cheat-names panel that lists every cheat of the selected build.
  - CSV export of the (filtered) database.
  - An API download section: enter your cheatslips email + password (or an API
    token) and cheat files are downloaded via the official API - no browser.

Run it with:  python scraper.py gui      (or)  python gui.py
"""

from __future__ import annotations

import json
import queue
import re
import shutil
import os
import sys
import threading
import tkinter as tk
import time
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from scraper import (
    APP_NAME,
    APP_VERSION,
    APP_AUTHOR,
    DEVCAT_CHEATS_ASSET,
    DEVCAT_DB_ASSET,
    DEVCAT_DATA_TAG,
    PROGRAM_SETUP_ASSET,
    PROGRAM_PORTABLE_ASSET,
    devcat_asset_url,
    download_file,
    fetch_github_release,
    find_release_asset,
    version_is_newer,
    CheatslipsAPI,
    CheatslipsMetadataScraper,
    GameDatabase,
    check_cheatslips_online,
    export_cheats_to_sd,
    export_cheats_to_zip,
    import_cheats_from_zip,
    import_database,
    detect_sd_roots,
    looks_like_sd_root,
    is_placeholder_build_id,
    is_valid_cheat_content,
    title_id_kind,
    base_title_id,
    resolve_base_title_id,
    api_download_from_db,
    download_build_list,
    download_with_quota_reset,
    missing_build_pairs,
    download_gbatemp_archive,
    download_hamlet_titledb_archive,
    download_hamlet_60fps_archive,
    download_sthetix_archive,
    download_breeze_archive,
    download_chansey_archive,
    download_mynx_archive,
    download_ibnux_archive,
    download_titledb_cheats,
    enable_file_logging,
    enrich_info_with_api,
    export_rows_csv,
    fill_missing_names,
    recount_cheats_from_disk,
    find_empty_cheat_files,
    parse_valid_cheats,
    fix_title_id_names,
    import_disk_titles_to_db,
    remove_placeholder_builds,
    fill_missing_versions,
    fill_versions_from_titledb,
    fill_regions_from_titledb,
    fill_descriptions_from_titledb,
    parse_cheat_names_from_content,
    refresh_titles_from_api,
    scan_downloaded_build_ids,
    cleanup_invalid_cheat_entries,
    cleanup_titles_folder,
    save_cheat_merged,
)
from tkinter import simpledialog

try:
    from PIL import Image, ImageTk
    _PIL_OK = True
except Exception:
    _PIL_OK = False

try:
    import browser_scrape as _browser_scrape
    _BROWSER_OK = True
except Exception:
    _browser_scrape = None
    _BROWSER_OK = False

try:
    import playwright_scrape as _pw_scrape
    _PW_OK = True
except Exception:
    _pw_scrape = None
    _PW_OK = False

_HERE = Path(__file__).resolve().parent


def _data_dir() -> Path:
    """Where the app stores its data (DB, settings, downloads, caches, login).

    Running from source: next to the code (unchanged, dev-friendly). Running as
    a packaged .exe: **next to the executable** (portable) — or, if that folder
    is read-only, ``%LOCALAPPDATA%\\SwitchCheatsScraper``. The launcher sets
    SCS_DATA_DIR; we honour it so all parts of the app agree.
    """
    env = os.environ.get("SCS_DATA_DIR")
    if env:
        d = Path(env)
    elif getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        try:
            exe_dir.mkdir(parents=True, exist_ok=True)
            probe = exe_dir / ".write_test"
            probe.write_text("ok", encoding="utf-8"); probe.unlink()
            d = exe_dir
        except Exception:
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            d = Path(base) / "SwitchCheatsScraper"
    else:
        d = _HERE
    try:
        d.mkdir(parents=True, exist_ok=True)
        os.environ["SCS_DATA_DIR"] = str(d)   # share with playwright_scrape etc.
    except Exception:
        pass
    return d


DATA_DIR = _data_dir()
DEFAULT_DB = str(DATA_DIR / "cheats.db")
DEFAULT_OUTPUT = str(DATA_DIR / "cheatsdownload")
COVERS_DIR = str(DATA_DIR / "coversdownload")
LOG_FILE = str(DATA_DIR / "scraper.log")
SETTINGS_FILE = str(DATA_DIR / "settings.json")
# Bookkeeping for the self-updater: the first-run baseline plus the last
# accepted upload times, so a re-uploaded release/data asset (a fix without a
# version bump) is detected. Lives in the data dir, so it survives app updates.
UPDATE_STATE_FILE = str(DATA_DIR / "update_state.json")

# Locally cached titledb region files used to look up game descriptions offline
# (English regions — descriptions there are in English). Filled by "Fill Names".
_TITLEDB_DESC_REGIONS = ["US.en", "GB.en", "AU.en"]

# Browser choices for the quota-reset / browser-download flow (display -> kind).
_BROWSER_KINDS = {
    "Built-in": "builtin",   # Playwright's bundled Chromium
    "Chrome": "chrome",      # installed Google Chrome (channel)
    "Firefox": "firefox",    # Playwright's Firefox (playwright install firefox)
}

# --------------------------------------------------------------------- theming
# Two full colour palettes (dark = default). Every widget colour in the app is
# derived from the active palette so a single _apply_theme() call restyles the
# whole program — main window, panels, table, log, menus and every sub-dialog.
# Keys are semantic roles, not raw colours, so both themes stay in sync.
THEMES = {
    "dark": {
        "bg":          "#1e1f22",  # window / frames
        "surface":     "#2b2d31",  # buttons, headings, labelframe body
        "hover":       "#3a3d43",  # active button / heading
        "field":       "#141517",  # entry / combobox / text input background
        "fg":          "#e4e6eb",  # primary text
        "fg_muted":    "#9aa0a6",  # secondary / subtle text
        "border":      "#3a3d43",
        "select_bg":   "#2d4f8a",  # selected table row / text
        "select_fg":   "#ffffff",
        "accent":      "#4a9eff",  # focus ring, progressbar, links
        "accent_hover": "#63abff",
        "accent_press": "#3a86e0",
        "featured_bg": "#182233",  # accent-tinted panel for the DevCat section
        "featured_border": "#4a9eff",
        "tree_bg":     "#232427",
        "ok":          "#4ade80",  # green (downloaded / online)
        "warn":        "#f0a020",  # orange (nameless / warning)
        "error":       "#ff6b6b",  # red (missing / offline)
        "link":        "#4a9eff",
        "checking":    "#d0a030",  # amber (busy check)
        "title":       "#f5f6f8",  # bold headings in the detail panel
        "nonbase_bg":  "#4a2a2a",  # update/DLC row background tint
        "tooltip_bg":  "#3a3d43",
        "tooltip_fg":  "#e4e6eb",
        "log_bg":      "#141517",
        "log_fg":      "#c8ccd0",
    },
    "light": {
        "bg":          "#f0f0f0",
        "surface":     "#e4e4e4",
        "hover":       "#d5d5d5",
        "field":       "#ffffff",
        "fg":          "#1a1a1a",
        "fg_muted":    "#555555",
        "border":      "#b8b8b8",
        "select_bg":   "#cce0ff",
        "select_fg":   "#000000",
        "accent":      "#1a6fd4",
        "accent_hover": "#2f7fe0",
        "accent_press": "#155cb0",
        "featured_bg": "#eef4fc",  # soft blue-tinted panel for the DevCat section
        "featured_border": "#a9c8ef",
        "tree_bg":     "#ffffff",
        "ok":          "#1a8f3c",
        "warn":        "#cc6600",
        "error":       "#c0392b",
        "link":        "#1a6fd4",
        "checking":    "#b8860b",
        "title":       "#1a1a1a",
        "nonbase_bg":  "#ffe0e0",
        "tooltip_bg":  "#ffffe0",
        "tooltip_fg":  "#333333",
        "log_bg":      "#111111",
        "log_fg":      "#dddddd",
    },
}

# The palette currently in force. Read via theme() so module-level widgets
# (tooltips, dialogs) pick up the same colours the main window uses.
_ACTIVE = {"name": "dark"}


def theme() -> dict:
    """Return the active colour palette."""
    return THEMES.get(_ACTIVE["name"], THEMES["dark"])


class _Tooltip:
    """A lightweight hover tooltip for any Tk/ttk widget."""

    def __init__(self, widget, text, delay=450):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _e=None):
        self._cancel()
        self._after = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after:
            self.widget.after_cancel(self._after)
            self._after = None

    def _show(self):
        if self._tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 14
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        _t = theme()
        tk.Label(self._tip, text=self.text, justify="left", bg=_t["tooltip_bg"],
                 fg=_t["tooltip_fg"], relief="solid", borderwidth=1, font=("Segoe UI", 8),
                 padx=6, pady=3, wraplength=340).pack()

    def _hide(self, _e=None):
        self._cancel()
        if self._tip:
            self._tip.destroy()
            self._tip = None

# Treeview columns: (internal id, heading, width, anchor)
COLUMNS = [
    ("downloaded", "DL", 36, "center"),
    ("game_title", "Game", 260, "w"),
    ("region", "Region", 135, "center"),
    ("version", "Version", 70, "center"),
    ("title_id", "Title ID", 140, "center"),
    ("build_id", "Build ID", 140, "center"),
    ("upload_date", "Uploaded", 100, "center"),
    ("cheat_count", "Cheats", 55, "center"),
    ("source", "Source", 90, "center"),
]


class ProgressTracker:
    """Track progress with rate and ETA calculation."""
    def __init__(self, label=""):
        self.label = label
        self.start_time = time.time()
        self.done = 0
        self.total = 1
        self.bytes_done = 0

    def update(self, done, total, bytes_done=None):
        self.done = done
        self.total = total
        if bytes_done is not None:
            self.bytes_done = bytes_done

    def rate_str(self, unit="items"):
        """Return rate as 'X items/s' or 'X MB/s'."""
        elapsed = time.time() - self.start_time
        if elapsed < 0.1:
            return "calculating..."
        if unit == "items":
            rate = self.done / elapsed
            return f"{rate:.1f} items/s"
        elif unit == "bytes":
            mb = self.bytes_done / (1024 * 1024)
            rate_mb = mb / elapsed
            return f"{rate_mb:.1f} MB/s"
        return ""

    def eta_str(self):
        """Return estimated time remaining as 'Xs' or 'Xm Ys'."""
        elapsed = time.time() - self.start_time
        if self.done == 0 or elapsed < 0.1:
            return "..."
        rate = self.done / elapsed
        remaining = max(0, self.total - self.done)
        eta_secs = remaining / rate if rate > 0 else 0
        if eta_secs < 60:
            return f"{int(eta_secs)}s"
        mins = int(eta_secs // 60)
        secs = int(eta_secs % 60)
        return f"{mins}m {secs}s"

    def pct(self):
        """Return percentage 0-100."""
        if self.total <= 0:
            return 0
        return min(100, int(100 * self.done / self.total))


def _default_zip_name() -> str:
    """Default export archive name using today's date, e.g. switch-cheats-05072026.zip."""
    return f"switch-cheats-{time.strftime('%d%m%Y')}.zip"


def _center_dialog(top, parent):
    """Position a Toplevel centered over its parent window (not top-left of the
    screen). Clamped to stay fully on-screen. Best-effort."""
    try:
        top.update_idletasks()
        w = top.winfo_reqwidth() or top.winfo_width()
        h = top.winfo_reqheight() or top.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        # Slightly above true center reads better; clamp inside the screen.
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 3)
        sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
        x = min(max(x, 0), max(0, sw - w))
        y = min(max(y, 0), max(0, sh - h))
        top.geometry(f"+{x}+{y}")
    except Exception:
        pass


class AddEntryDialog:
    """Modal dialog to add/edit a cheat entry (title id, build id, codes...)."""

    def __init__(self, parent, initial=None):
        initial = initial or {}
        self.result = None
        self.top = tk.Toplevel(parent)
        self.top.title("Add cheat entry")
        self.top.transient(parent)
        self.top.grab_set()
        self.top.resizable(True, True)
        self.top.configure(bg=theme()["bg"])

        frm = ttk.Frame(self.top, padding=10)
        frm.pack(fill="both", expand=True)

        self.vars = {
            "title_id": tk.StringVar(value=initial.get("title_id", "")),
            "build_id": tk.StringVar(value=initial.get("build_id", "")),
            "name": tk.StringVar(value=initial.get("name", "")),
            "version": tk.StringVar(value=initial.get("version", "")),
            "credits": tk.StringVar(value=initial.get("credits", "")),
        }
        rows = [
            ("Title ID * (16 hex)", "title_id"),
            ("Build ID * (16 hex)", "build_id"),
            ("Game name", "name"),
            ("Version", "version"),
            ("Credits", "credits"),
        ]
        for i, (label, key) in enumerate(rows):
            ttk.Label(frm, text=label).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Entry(frm, textvariable=self.vars[key], width=46).grid(row=i, column=1, sticky="we", pady=2)

        ttk.Label(frm, text="Cheat code *\n(Atmosphere format,\n[Name] headers)").grid(
            row=len(rows), column=0, sticky="nw", pady=(6, 2))
        _t = theme()
        self.code_text = tk.Text(frm, width=60, height=16, wrap="none", font=("Consolas", 9),
                                 bg=_t["field"], fg=_t["fg"], insertbackground=_t["fg"],
                                 selectbackground=_t["select_bg"], selectforeground=_t["select_fg"],
                                 relief="flat", highlightthickness=1,
                                 highlightbackground=_t["border"], highlightcolor=_t["accent"])
        self.code_text.grid(row=len(rows), column=1, sticky="nsew", pady=(6, 2))
        if initial.get("content"):
            self.code_text.insert("1.0", initial["content"])
        frm.rowconfigure(len(rows), weight=1)
        frm.columnconfigure(1, weight=1)

        btns = ttk.Frame(frm)
        btns.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(btns, text="Cancel", command=self.top.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="Save", command=self._on_save).pack(side="right")

        self.top.bind("<Escape>", lambda _e: self.top.destroy())
        _center_dialog(self.top, parent)

    def _on_save(self):
        import re as _re
        tid = self.vars["title_id"].get().strip().upper()
        bid = self.vars["build_id"].get().strip().upper()
        content = self.code_text.get("1.0", "end").strip()
        if not _re.fullmatch(r"[A-F0-9]{16}", tid) or not _re.fullmatch(r"[A-F0-9]{16}", bid):
            messagebox.showwarning("Add entry", "Title ID and Build ID must be exactly 16 hex characters.", parent=self.top)
            return
        if not content:
            messagebox.showwarning("Add entry", "Please paste the cheat code.", parent=self.top)
            return
        self.result = {
            "title_id": tid, "build_id": bid,
            "name": self.vars["name"].get().strip(),
            "version": self.vars["version"].get().strip(),
            "credits": self.vars["credits"].get().strip(),
            "content": content,
        }
        self.top.destroy()


class ExportSDDialog:
    """Modal dialog: pick the Switch SD-card root + target tool, then export."""

    _MODES = [
        ("atmosphere", "Atmosphère",
         "atmosphere/contents/<TitleID>/cheats/<BuildID>.txt\n"
         "→ auto-loads when you start the game. Works for Atmosphère, EdiZon-SE\n"
         "   and Breeze — this is the recommended option."),
        ("breeze", "Breeze",
         "switch/breeze/cheats/<TitleID>/<BuildID>.txt\n"
         "→ inactive until you enable them inside the Breeze app."),
        ("edizon", "EdiZon SE",
         "switch/EdiZon/cheats/<BuildID>.txt\n"
         "→ EdiZon loads the file when the game launches, then moves it to the\n"
         "   Atmosphère folder itself."),
    ]

    def __init__(self, parent, sd_var, mode_var, selected_count, detect_fn, validate_fn):
        self.result = None
        self._detect = detect_fn
        self._validate = validate_fn
        self.sd_var = sd_var
        self.mode_var = mode_var
        self.scope_var = tk.StringVar(value="all")
        self.selected_count = selected_count

        self.top = tk.Toplevel(parent)
        self.top.title("Export cheats to Switch SD card")
        self.top.transient(parent)
        self.top.grab_set()
        self.top.resizable(False, False)
        self.top.configure(bg=theme()["bg"])
        frm = ttk.Frame(self.top, padding=12)
        frm.pack(fill="both", expand=True)

        # --- SD root row ---
        ttk.Label(frm, text="Switch SD-card root:").grid(row=0, column=0, sticky="w")
        sdrow = ttk.Frame(frm)
        sdrow.grid(row=1, column=0, columnspan=2, sticky="we", pady=(2, 0))
        self.sd_entry = ttk.Entry(sdrow, textvariable=self.sd_var, width=52)
        self.sd_entry.pack(side="left", fill="x", expand=True)
        # Track the trace so it can be removed on close — self.sd_var is the
        # app's persistent StringVar, so a leaked trace would fire on a
        # destroyed widget every time it changes later.
        self._trace_id = self.sd_var.trace_add("write", lambda *_: self._update_validity())
        self.top.bind("<Destroy>", self._on_destroy, add="+")
        ttk.Button(sdrow, text="Browse…", command=self._browse).pack(side="left", padx=(4, 0))
        ttk.Button(sdrow, text="Auto-detect", command=self._autodetect).pack(side="left", padx=(4, 0))
        self.valid_lbl = ttk.Label(frm, text="", font=("Segoe UI", 8))
        self.valid_lbl.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 8))

        # --- target tool ---
        ttk.Label(frm, text="Export for:").grid(row=3, column=0, sticky="w")
        tf = ttk.Frame(frm)
        tf.grid(row=4, column=0, columnspan=2, sticky="we", pady=(2, 8))
        for i, (mode, label, desc) in enumerate(self._MODES):
            ttk.Radiobutton(tf, text=label, value=mode, variable=self.mode_var).grid(
                row=i * 2, column=0, sticky="w")
            ttk.Label(tf, text=desc, foreground=theme()["fg_muted"],
                      font=("Segoe UI", 8)).grid(row=i * 2 + 1, column=0, sticky="w", padx=(22, 0), pady=(0, 4))

        # --- scope ---
        ttk.Label(frm, text="Scope:").grid(row=5, column=0, sticky="w")
        sf = ttk.Frame(frm)
        sf.grid(row=6, column=0, columnspan=2, sticky="we", pady=(2, 8))
        ttk.Radiobutton(sf, text="All downloaded cheats", value="all",
                        variable=self.scope_var).pack(side="left")
        state = "normal" if selected_count else "disabled"
        ttk.Radiobutton(sf, text=f"Selected rows only ({selected_count})", value="selected",
                        variable=self.scope_var, state=state).pack(side="left", padx=(12, 0))

        ttk.Label(frm, text="Only files with real cheats are copied; empty/stub files are "
                            "skipped.\nExisting cheats on the card are merged, not overwritten.",
                  foreground=theme()["fg_muted"], font=("Segoe UI", 8)).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(0, 8))

        btns = ttk.Frame(frm)
        btns.grid(row=8, column=0, columnspan=2, sticky="e")
        ttk.Button(btns, text="Cancel", command=self.top.destroy).pack(side="right", padx=(6, 0))
        self.export_btn = ttk.Button(btns, text="Export", command=self._on_export)
        self.export_btn.pack(side="right")
        frm.columnconfigure(1, weight=1)
        self.top.bind("<Escape>", lambda _e: self.top.destroy())
        self._update_validity()
        if not self.sd_var.get().strip():
            self._autodetect()
        _center_dialog(self.top, parent)

    def _browse(self):
        from tkinter import filedialog
        cur = self.sd_var.get().strip()
        d = filedialog.askdirectory(title="Select the Switch SD-card root",
                                    initialdir=cur or "/", parent=self.top)
        if d:
            self.sd_var.set(d)

    def _autodetect(self):
        roots = self._detect()
        if roots:
            self.sd_var.set(roots[0])
            extra = f" (+{len(roots) - 1} more)" if len(roots) > 1 else ""
            self.valid_lbl.config(text=f"✓ Auto-detected SD card: {roots[0]}{extra}",
                                  foreground=theme()["ok"])
        else:
            self.valid_lbl.config(
                text="⚠ No SD card auto-detected — pick the drive root with Browse…",
                foreground=theme()["warn"])

    def _on_destroy(self, event):
        if event.widget is self.top and getattr(self, "_trace_id", None):
            try:
                self.sd_var.trace_remove("write", self._trace_id)
            except Exception:
                pass
            self._trace_id = None

    def _update_validity(self):
        try:
            if not self.valid_lbl.winfo_exists():
                return
        except Exception:
            return
        p = self.sd_var.get().strip()
        if not p:
            self.valid_lbl.config(text="Choose the SD-card root (e.g. D:\\).",
                                  foreground=theme()["fg_muted"])
        elif self._validate(p):
            self.valid_lbl.config(text="✓ Looks like a Switch SD card (CFW folders found).",
                                  foreground=theme()["ok"])
        else:
            self.valid_lbl.config(
                text="⚠ No atmosphere/ or switch/ folder here — export anyway if you are sure.",
                foreground=theme()["warn"])

    def _on_export(self):
        p = self.sd_var.get().strip()
        if not p or not Path(p).is_dir():
            messagebox.showwarning("Export to SD", "Please choose a valid SD-card root folder.",
                                   parent=self.top)
            return
        if not self._validate(p):
            if not messagebox.askyesno(
                "Export to SD",
                f"'{p}' does not look like a Switch SD card (no atmosphere/ or switch/ "
                "folder).\n\nExport there anyway?", parent=self.top):
                return
        self.result = {"sd_root": p, "mode": self.mode_var.get(),
                       "scope": self.scope_var.get()}
        self.top.destroy()


class ExportZipDialog:
    """Modal dialog: pick a ZIP file + target layout, then export cheats into it.

    The archive uses the exact SD-card layout (see ExportSDDialog._MODES), so
    the user can just unzip it onto the SD-card root.
    """

    _MODES = ExportSDDialog._MODES

    def __init__(self, parent, zip_var, mode_var, selected_count, default_scope="all"):
        self.result = None
        self.zip_var = zip_var
        self.mode_var = mode_var
        self.scope_var = tk.StringVar(
            value="selected" if (default_scope == "selected" and selected_count) else "all")

        self.top = tk.Toplevel(parent)
        self.top.title("Export cheats to a ZIP file")
        self.top.transient(parent)
        self.top.grab_set()
        self.top.resizable(False, False)
        self.top.configure(bg=theme()["bg"])
        frm = ttk.Frame(self.top, padding=12)
        frm.pack(fill="both", expand=True)

        # --- ZIP file row ---
        ttk.Label(frm, text="Save ZIP as:").grid(row=0, column=0, sticky="w")
        zrow = ttk.Frame(frm)
        zrow.grid(row=1, column=0, columnspan=2, sticky="we", pady=(2, 8))
        ttk.Entry(zrow, textvariable=self.zip_var, width=52).pack(
            side="left", fill="x", expand=True)
        ttk.Button(zrow, text="Save As…", command=self._browse).pack(side="left", padx=(4, 0))

        # --- target layout ---
        ttk.Label(frm, text="Layout inside the ZIP (for which tool):").grid(
            row=2, column=0, sticky="w")
        tf = ttk.Frame(frm)
        tf.grid(row=3, column=0, columnspan=2, sticky="we", pady=(2, 8))
        for i, (mode, label, desc) in enumerate(self._MODES):
            ttk.Radiobutton(tf, text=label, value=mode, variable=self.mode_var).grid(
                row=i * 2, column=0, sticky="w")
            ttk.Label(tf, text=desc, foreground=theme()["fg_muted"],
                      font=("Segoe UI", 8)).grid(row=i * 2 + 1, column=0, sticky="w",
                                                 padx=(22, 0), pady=(0, 4))

        # --- scope ---
        ttk.Label(frm, text="Scope:").grid(row=4, column=0, sticky="w")
        sf = ttk.Frame(frm)
        sf.grid(row=5, column=0, columnspan=2, sticky="we", pady=(2, 8))
        ttk.Radiobutton(sf, text="All downloaded cheats", value="all",
                        variable=self.scope_var).pack(side="left")
        state = "normal" if selected_count else "disabled"
        ttk.Radiobutton(sf, text=f"Selected rows only ({selected_count})", value="selected",
                        variable=self.scope_var, state=state).pack(side="left", padx=(12, 0))

        ttk.Label(frm, text="Only files with real cheats are included; empty/stub files are "
                            "skipped.\nUnzip the archive onto your SD-card root to install "
                            "the cheats.",
                  foreground=theme()["fg_muted"], font=("Segoe UI", 8)).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(0, 8))

        btns = ttk.Frame(frm)
        btns.grid(row=7, column=0, columnspan=2, sticky="e")
        ttk.Button(btns, text="Cancel", command=self.top.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="Export", command=self._on_export).pack(side="right")
        frm.columnconfigure(1, weight=1)
        self.top.bind("<Escape>", lambda _e: self.top.destroy())
        _center_dialog(self.top, parent)

    def _browse(self):
        from tkinter import filedialog
        cur = self.zip_var.get().strip()
        initialdir = str(Path(cur).parent) if cur else str(DATA_DIR)
        initialfile = Path(cur).name if cur else _default_zip_name()
        path = filedialog.asksaveasfilename(
            title="Export cheats to ZIP", parent=self.top,
            defaultextension=".zip", initialdir=initialdir, initialfile=initialfile,
            filetypes=[("ZIP archive", "*.zip"), ("All files", "*.*")])
        if path:
            self.zip_var.set(path)

    def _on_export(self):
        p = self.zip_var.get().strip()
        if not p:
            messagebox.showwarning("Export to ZIP", "Please choose where to save the ZIP file.",
                                   parent=self.top)
            return
        if not p.lower().endswith(".zip"):
            p += ".zip"
            self.zip_var.set(p)
        self.result = {"zip_path": p, "mode": self.mode_var.get(),
                       "scope": self.scope_var.get()}
        self.top.destroy()


class ImportDBDialog:
    """Modal dialog to import a previously exported cheats.db: merge or replace."""

    _MODES = [
        ("merge", "Merge into the current database (recommended)",
         "Add and update builds from the imported database. Nothing is removed;\n"
         "existing entries keep their data and never lose a real cheat count."),
        ("replace", "Replace the current database entirely",
         "Overwrite the current database with the imported one. A backup of the\n"
         "current database is saved first."),
    ]

    def __init__(self, parent, src_name):
        self.result = None
        self.mode_var = tk.StringVar(value="merge")

        self.top = tk.Toplevel(parent)
        self.top.title("Import database")
        self.top.transient(parent)
        self.top.grab_set()
        self.top.resizable(False, False)
        self.top.configure(bg=theme()["bg"])
        frm = ttk.Frame(self.top, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text=f"Import from:  {src_name}",
                  font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Label(frm, text="How should the imported data be applied?").grid(
            row=1, column=0, sticky="w")
        tf = ttk.Frame(frm)
        tf.grid(row=2, column=0, sticky="we", pady=(2, 8))
        for i, (mode, label, desc) in enumerate(self._MODES):
            ttk.Radiobutton(tf, text=label, value=mode, variable=self.mode_var).grid(
                row=i * 2, column=0, sticky="w")
            ttk.Label(tf, text=desc, foreground=theme()["fg_muted"],
                      font=("Segoe UI", 8)).grid(row=i * 2 + 1, column=0, sticky="w",
                                                 padx=(22, 0), pady=(0, 6))

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, sticky="e", pady=(4, 0))
        ttk.Button(btns, text="Cancel", command=self.top.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="Import", command=self._on_import).pack(side="right")
        self.top.bind("<Escape>", lambda _e: self.top.destroy())
        _center_dialog(self.top, parent)

    def _on_import(self):
        self.result = {"mode": self.mode_var.get()}
        self.top.destroy()


def _fmt_size(n) -> str:
    """Human-readable byte size, e.g. 12.3 MB."""
    try:
        n = float(n)
    except Exception:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


class UpdateDialog:
    """Modal dialog summarising the available program / data updates.

    It only reports and dispatches: the actual work runs in the app's worker
    threads (program self-install, or data download+import).
    """

    def __init__(self, parent, app, info: dict):
        self.app = app
        self.info = info
        t = theme()
        self.top = tk.Toplevel(parent)
        self.top.title("Updates")
        self.top.transient(parent)
        self.top.grab_set()
        self.top.resizable(False, False)
        self.top.configure(bg=t["bg"])
        frm = ttk.Frame(self.top, padding=14)
        frm.pack(fill="both", expand=True)

        prog = info.get("program")
        cheats = info.get("cheats")
        db = info.get("db")

        ttk.Label(frm, text="Updates available" if (prog or cheats or db)
                  else "You are up to date",
                  font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(frm, text=f"Installed version: v{APP_VERSION}",
                  foreground=t["fg_muted"], font=("Segoe UI", 8)).pack(
                      anchor="w", pady=(0, 10))

        # --- Program update block ---
        if prog:
            box = ttk.LabelFrame(frm, text="Program", padding=(10, 8))
            box.pack(fill="x", pady=(0, 8))
            if prog["newer_version"]:
                head = f"New version v{prog['version']} is available."
            else:
                head = ("The current release was re-uploaded (a fix without a "
                        "version bump).")
            ttk.Label(box, text=head, font=("Segoe UI", 9, "bold"),
                      wraplength=440, justify="left").pack(anchor="w")
            setup = prog.get("setup") or {}
            if setup.get("size"):
                ttk.Label(box, text=f"Installer: {_fmt_size(setup['size'])}",
                          foreground=t["fg_muted"], font=("Segoe UI", 8)).pack(
                              anchor="w", pady=(2, 0))
            notes = (prog.get("notes") or "").strip()
            if notes:
                ttk.Label(box, text="What's new:", font=("Segoe UI", 8, "bold")).pack(
                    anchor="w", pady=(6, 0))
                txt = tk.Text(box, height=5, width=58, wrap="word",
                              font=("Segoe UI", 8), relief="flat",
                              bg=t["field"], fg=t["fg"],
                              highlightthickness=1, highlightbackground=t["border"])
                txt.insert("1.0", notes)
                txt.config(state="disabled")
                txt.pack(fill="x", pady=(2, 0))
            frozen = getattr(sys, "frozen", False)
            btn_text = "Update & Restart" if frozen else "Open download page"
            ttk.Button(box, text=btn_text,
                       command=self._on_program).pack(anchor="e", pady=(8, 0))

        # --- Data update block ---
        if cheats or db:
            box = ttk.LabelFrame(frm, text="Data (from DevCatSKZ)", padding=(10, 8))
            box.pack(fill="x", pady=(0, 8))
            if db:
                ttk.Label(box, text=f"• Newer database  ({_fmt_size(db.get('size'))})",
                          wraplength=440, justify="left").pack(anchor="w")
            if cheats:
                ttk.Label(box, text=f"• Newer cheats archive  ({_fmt_size(cheats.get('size'))})",
                          wraplength=440, justify="left").pack(anchor="w")
            ttk.Label(box, text="Downloaded and merged into your database "
                                "(nothing is removed).",
                      foreground=t["fg_muted"], font=("Segoe UI", 8)).pack(
                          anchor="w", pady=(2, 0))
            ttk.Button(box, text="Download data update",
                       command=self._on_data).pack(anchor="e", pady=(8, 0))

        if not (prog or cheats or db):
            ttk.Label(frm, text="Program, cheats and database are all current.",
                      foreground=t["fg_muted"]).pack(anchor="w")

        # --- Footer ---
        foot = ttk.Frame(frm)
        foot.pack(fill="x", pady=(6, 0))
        rel = info.get("release") or {}
        if rel.get("html_url"):
            ttk.Button(foot, text="Open GitHub release",
                       command=lambda: webbrowser.open(rel["html_url"])).pack(side="left")
        ttk.Button(foot, text="Close", command=self.top.destroy).pack(side="right")
        self.top.bind("<Escape>", lambda _e: self.top.destroy())
        _center_dialog(self.top, parent)

    def _on_program(self):
        self.top.destroy()
        self.app.start_program_update(self.info)

    def _on_data(self):
        self.top.destroy()
        self.app.start_data_update(self.info)


class _QueueWriter:
    """File-like object that forwards written lines to a queue (for the log).

    Optionally mirrors everything to another stream (e.g. the log file) so the
    worker output is not lost from scraper.log while stdout is redirected.
    """

    def __init__(self, q: "queue.Queue", mirror=None):
        self.q = q
        self.mirror = mirror
        self._buf = ""

    def write(self, s: str):
        if self.mirror is not None:
            try:
                self.mirror.write(s)
                self.mirror.flush()
            except Exception:
                pass
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self.q.put(line)

    def flush(self):
        if self._buf:
            self.q.put(self._buf)
            self._buf = ""


class ScraperGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME}  v{APP_VERSION}  ·  by {APP_AUTHOR}")
        self._set_window_icon()
        # A sensible floor; the real size is computed after the UI is built (or a
        # saved geometry is restored). See the end of __init__.
        self.root.minsize(1200, 800)

        self.db_path = tk.StringVar(value=DEFAULT_DB)
        self.status_var = tk.StringVar(value="Ready.")
        self.total_games_var = tk.StringVar(value="0 games")
        self.search_var = tk.StringVar()
        self.not_downloaded_only = tk.BooleanVar(value=False)
        self.names_missing = tk.BooleanVar(value=False)
        self.nonbase_only = tk.BooleanVar(value=False)
        self.hide_placeholder_builds = tk.BooleanVar(value=True)
        self.auto_scan_downloaded = tk.BooleanVar(value=False)
        # Two independent scrape controls (decoupled):
        #  - full catalog: discover over /games (ALL games) instead of the fast
        #    /entry "latest cheats" feed. Default on = the complete dataset.
        #  - skip 0-cheat: drop builds with 0 cheats during scrape. Default OFF so
        #    0-cheat builds stay in the DB and are visible under "Not downloaded".
        self.scrape_full_catalog = tk.BooleanVar(value=True)
        self.scrape_skip_zero = tk.BooleanVar(value=False)
        self.auto_download = tk.BooleanVar(value=True)
        self.rescan_all = tk.BooleanVar(value=False)
        # When the API hits the daily quota, automatically reset it via a
        # logged-in browser window and keep downloading until complete.
        self.auto_reset_quota = tk.BooleanVar(value=True)
        self.browser_choice = tk.StringVar(value="Built-in")
        self.update_pages = tk.IntVar(value=5)
        # Check whether cheatslips.com is reachable on every program start.
        self.online_check_startup = tk.BooleanVar(value=True)
        # When ON, a DevCatSKZ download also fetches the cover images afterwards.
        # Off by default — covers are not part of the archive and cost extra time.
        self.devcat_covers = tk.BooleanVar(value=False)
        # Check GitHub for a newer program build / data package at every start.
        self.update_check_startup = tk.BooleanVar(value=True)
        # SD-card export (remembered between runs).
        self.sd_export_root = tk.StringVar(value="")
        self.sd_export_mode = tk.StringVar(value="atmosphere")
        self.export_zip_path = tk.StringVar(value="")
        # download/login settings
        self.dl_output = tk.StringVar(value=DEFAULT_OUTPUT)
        self.email_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.api_token_var = tk.StringVar()
        self.remember_pw = tk.BooleanVar(value=True)
        self.show_images = tk.BooleanVar(value=True)
        self.show_description = tk.BooleanVar(value=False)
        self.cache_covers = tk.BooleanVar(value=True)
        self._img_refs = {}      # url -> PhotoImage (kept to avoid GC)
        self._img_token = None   # marks the latest cover request
        self._desc_token = None  # marks the latest description fetch
        self._desc_attempted = set()  # title ids already tried this session
        self._titledb_desc = None      # lazy {title_id: (description, intro)} index
        self._titledb_desc_lock = threading.Lock()
        self._link_counter = 0   # unique tag ids for clickable links

        self._log_queue: "queue.Queue" = queue.Queue()
        self._busy = False
        self._stop_event = threading.Event()
        self._row_lock = threading.Lock()
        self._row_slugs: dict[str, str] = {}
        self._row_cheats: dict[str, list] = {}
        self._sort_state: dict[str, bool] = {}
        self._search_after_id = None
        self._refresh_gen = 0    # generation counter for async table refreshes
        self._last_busy_start: Optional[float] = None

        # Mirror everything printed anywhere into a persistent log file too.
        try:
            self._log_writer = enable_file_logging(LOG_FILE)
        except Exception:
            self._log_writer = None

        # Colour theme (dark is the default). Loaded from settings below, then
        # applied to the ttk styles BEFORE any widget is built so creation-time
        # colours are already correct.
        self.theme_name = "dark"

        self._loaded_geometry = False
        self._load_settings()
        # Seed the updater's first-run baseline as early as possible, so the
        # "install date" anchor reflects the true first program start.
        self._update_state = self._load_update_state()

        _ACTIVE["name"] = self.theme_name
        self._style = ttk.Style(self.root)
        self._all_menus = []          # tk.Menu widgets to recolour on theme change
        self._apply_theme(self.theme_name)

        self._build_toolbar()
        # Vertical splitter: table + database bar on top, log at the bottom.
        # The user can drag the sash to make the log panel as large as they want.
        self.vpaned = ttk.Panedwindow(self.root, orient="vertical")
        self.vpaned.pack(fill="both", expand=True)
        self._top_container = ttk.Frame(self.vpaned)
        self.vpaned.add(self._top_container, weight=5)
        # Pack the fixed database bar at the BOTTOM first so it always keeps its
        # space, then let the table fill whatever height remains. If the table
        # were packed first with expand=True, a short window or an enlarged log
        # panel would clip the bar and its buttons would disappear.
        self._build_database_bar()
        self._build_main()
        self._build_log()
        self._install_edit_shortcuts()
        # Re-apply now that every widget (log, tree, menus, toggle button) exists
        # so the classic tk widgets and menus pick up the theme colours too.
        self._apply_theme(self.theme_name)

        # Size and place the window so it works both in a normal window and in
        # full screen, and fits a 1920x1080 (Full HD) display without being cut
        # off by the taskbar. The toolbar's natural width drives the minimum
        # width so all buttons stay visible; the table/log expand to fill extra
        # space (incl. full screen). See _install_window_controls for F11/Esc.
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        # Usable area, leaving room for the taskbar and window title bar.
        avail_w = screen_w - 16
        avail_h = screen_h - 80
        toolbar_w = self.root.winfo_reqwidth() + 24

        # Minimum size: just wide enough for the toolbar (which now wraps onto
        # several rows), so the window fits smaller screens without clipping.
        min_w = min(max(toolbar_w, 1000), avail_w)
        min_h = min(700, avail_h)
        self.root.minsize(min_w, min_h)

        if not self._loaded_geometry:
            # Open at a comfortable size, centered on the screen.
            win_w = min(max(toolbar_w, 1400), avail_w)
            win_h = min(940, avail_h)
            pos_x = max(0, (screen_w - win_w) // 2)
            pos_y = max(0, (screen_h - win_h) // 2 - 20)
            self.root.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        else:
            # Clamp a restored geometry (e.g. saved on a larger monitor) so the
            # window always stays fully visible on the current screen.
            m = re.match(r"(\d+)x(\d+)([+-]\d+)([+-]\d+)", self.root.geometry())
            if m:
                w = min(max(int(m.group(1)), min_w), avail_w)
                h = min(max(int(m.group(2)), min_h), avail_h)
                x = min(max(int(m.group(3)), 0), max(0, screen_w - w))
                y = min(max(int(m.group(4)), 0), max(0, screen_h - h))
                self.root.geometry(f"{w}x{h}+{x}+{y}")

        self._install_window_controls()

        self.root.after(150, self._drain_log)
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.refresh_table()
        self._append_log(f"{APP_NAME} v{APP_VERSION} — by {APP_AUTHOR}")
        # Check whether cheatslips.com is reachable once at startup (optional,
        # toggle 'check at startup'); runs in a background thread.
        if self.online_check_startup.get():
            self.root.after(800, self.on_check_online)
        # Check GitHub for a newer program/data version at startup (optional).
        # Runs quietly in the background; pops the dialog only if something's new.
        if self.update_check_startup.get():
            self.root.after(1500, lambda: self.on_check_updates(startup=True))

    def _set_window_icon(self):
        """Set the window / taskbar icon from app.ico when it can be found."""
        candidates = []
        mei = getattr(sys, "_MEIPASS", None)
        if mei:
            candidates.append(Path(mei) / "app.ico")
        candidates += [Path(sys.executable).resolve().parent / "app.ico",
                       _HERE / "app.ico"]
        for ico in candidates:
            try:
                if ico.exists():
                    self.root.iconbitmap(default=str(ico))
                    return
            except Exception:
                pass

    # ------------------------------------------------------ window controls
    def _install_window_controls(self):
        """Allow using the app windowed or full screen.

        F11 toggles full screen, Escape leaves it, and Ctrl+M maximizes/restores
        the window. The window state is remembered across these toggles so the
        previous geometry is restored when leaving full screen.
        """
        self._is_fullscreen = False
        self.root.bind("<F11>", self._toggle_fullscreen)
        self.root.bind("<Escape>", self._exit_fullscreen)
        self.root.bind("<Control-m>", self._toggle_maximize)

    def _toggle_fullscreen(self, _event=None):
        self._is_fullscreen = not self._is_fullscreen
        self.root.attributes("-fullscreen", self._is_fullscreen)
        return "break"

    def _exit_fullscreen(self, _event=None):
        if self._is_fullscreen:
            self._is_fullscreen = False
            self.root.attributes("-fullscreen", False)
        return "break"

    def _toggle_maximize(self, _event=None):
        # "zoomed" is the maximized state on Windows.
        try:
            new_state = "normal" if self.root.state() == "zoomed" else "zoomed"
            self.root.state(new_state)
        except Exception:
            pass
        return "break"

    # ------------------------------------------------------- edit shortcuts
    def _install_edit_shortcuts(self):
        """Enable the standard editing keyboard shortcuts in every text field,
        independent of the keyboard layout.

        Tkinter already maps Ctrl+C / Ctrl+X / Ctrl+V to the built-in
        <<Copy>>/<<Cut>>/<<Paste>> virtual events, but Ctrl+A defaults to
        "move cursor to start of line" rather than Select-All, and there is no
        select-all in multi-line Text widgets. We bind those at the widget-class
        level so they apply to all current and future Entry/Text widgets.
        """
        def entry_select_all(event):
            w = event.widget
            try:
                w.selection_range(0, "end")
                w.icursor("end")
            except Exception:
                pass
            return "break"

        def text_select_all(event):
            w = event.widget
            try:
                w.tag_add("sel", "1.0", "end-1c")
                w.mark_set("insert", "end-1c")
                w.see("insert")
            except Exception:
                pass
            return "break"

        # Copy / Cut / Paste bound explicitly so they work regardless of the Tk
        # build or keyboard layout (a concrete <Control-c> class binding takes
        # precedence over the <<Copy>> alias, so it fires exactly once).
        def gen(virtual):
            def handler(event):
                event.widget.event_generate(virtual)
                return "break"
            return handler

        copy_h, cut_h, paste_h = gen("<<Copy>>"), gen("<<Cut>>"), gen("<<Paste>>")

        for cls in ("Entry", "TEntry", "Text"):
            select_all = entry_select_all if cls in ("Entry", "TEntry") else text_select_all
            self.root.bind_class(cls, "<Control-a>", select_all)
            self.root.bind_class(cls, "<Control-A>", select_all)
            self.root.bind_class(cls, "<Control-c>", copy_h)
            self.root.bind_class(cls, "<Control-C>", copy_h)
            self.root.bind_class(cls, "<Control-x>", cut_h)
            self.root.bind_class(cls, "<Control-X>", cut_h)
            self.root.bind_class(cls, "<Control-v>", paste_h)
            self.root.bind_class(cls, "<Control-V>", paste_h)

    # ------------------------------------------------------------- settings
    @staticmethod
    def _abs_path(value: str, fallback: str) -> str:
        """Resolve a stored path: keep absolute paths, anchor relatives to the
        script directory. Empty / bare './cheats.db' style values fall back to
        the absolute default so the app works from any working directory."""
        try:
            value = (value or "").strip()
            if not value:
                return fallback
            p = Path(value)
            if p.is_absolute():
                return str(p)
            # Strip a leading './' or '.\' and anchor to the script directory.
            return str((DATA_DIR / p).resolve())
        except Exception:
            return fallback

    def _load_settings(self):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        self.email_var.set(data.get("email", ""))
        self.api_token_var.set(data.get("api_token", ""))
        self.password_var.set(data.get("password", ""))
        self.remember_pw.set(bool(data.get("remember_pw", True)))
        _theme = data.get("theme", "dark")
        self.theme_name = _theme if _theme in THEMES else "dark"
        self.show_images.set(bool(data.get("show_images", True)))
        self.show_description.set(bool(data.get("show_description", False)))
        self.cache_covers.set(bool(data.get("cache_covers", True)))
        self.hide_placeholder_builds.set(bool(data.get("hide_placeholder_builds", True)))
        self.auto_scan_downloaded.set(bool(data.get("auto_scan_downloaded", False)))
        self.auto_reset_quota.set(bool(data.get("auto_reset_quota", True)))
        # Browser choice (migrate the old use_installed_browser bool).
        _legacy_ib = data.get("use_installed_browser")
        choice = data.get("browser_choice", "Chrome" if _legacy_ib else "Built-in")
        if choice not in _BROWSER_KINDS:
            choice = "Built-in"
        self.browser_choice.set(choice)
        # Migrate the old single "scrape_entry_only" flag: it meant entry-feed
        # discovery + skip 0-cheat, i.e. NOT full catalog and skip zero.
        legacy = data.get("scrape_entry_only")
        self.scrape_full_catalog.set(bool(data.get(
            "scrape_full_catalog", (not legacy) if legacy is not None else True)))
        self.scrape_skip_zero.set(bool(data.get(
            "scrape_skip_zero", legacy if legacy is not None else False)))
        self.online_check_startup.set(bool(data.get("online_check_startup", True)))
        self.devcat_covers.set(bool(data.get("devcat_covers", False)))
        self.update_check_startup.set(bool(data.get("update_check_startup", True)))
        self.sd_export_root.set(data.get("sd_export_root", ""))
        self.sd_export_mode.set(data.get("sd_export_mode", "atmosphere"))
        self.export_zip_path.set(data.get("export_zip_path", ""))
        if data.get("output"):
            self.dl_output.set(self._abs_path(data["output"], DEFAULT_OUTPUT))
        if data.get("db_path"):
            self.db_path.set(self._abs_path(data["db_path"], DEFAULT_DB))
        geo = data.get("geometry")
        if geo:
            try:
                self.root.geometry(geo)
                self._loaded_geometry = True
            except Exception:
                pass

    def _save_settings(self):
        remember = self.remember_pw.get()
        data = {
            "email": self.email_var.get().strip(),
            "api_token": self.api_token_var.get().strip(),
            "password": self.password_var.get() if remember else "",
            "remember_pw": remember,
            "theme": self.theme_name,
            "show_images": self.show_images.get(),
            "show_description": self.show_description.get(),
            "cache_covers": self.cache_covers.get(),
            "hide_placeholder_builds": self.hide_placeholder_builds.get(),
            "auto_scan_downloaded": self.auto_scan_downloaded.get(),
            "auto_reset_quota": self.auto_reset_quota.get(),
            "browser_choice": self.browser_choice.get(),
            "scrape_full_catalog": self.scrape_full_catalog.get(),
            "scrape_skip_zero": self.scrape_skip_zero.get(),
            "online_check_startup": self.online_check_startup.get(),
            "devcat_covers": self.devcat_covers.get(),
            "update_check_startup": self.update_check_startup.get(),
            "sd_export_root": self.sd_export_root.get(),
            "sd_export_mode": self.sd_export_mode.get(),
            "export_zip_path": self.export_zip_path.get(),
            "output": self.dl_output.get(),
            "db_path": self.db_path.get(),
        }
        try:
            data["geometry"] = self.root.geometry()
        except Exception:
            pass
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    # ---------------------------------------------------------- update state
    def _load_update_state(self) -> dict:
        """Read the updater bookkeeping file, seeding first-run baselines.

        On the very first run the file does not exist yet: every baseline is set
        to *now*, so only releases/data uploaded AFTER this moment count as an
        update (matching "newer than when the program was first started").
        """
        try:
            with open(UPDATE_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            if not isinstance(state, dict):
                raise ValueError
        except Exception:
            state = {}
        if not state.get("install_epoch"):
            now = time.time()
            state = {
                "install_epoch": now,
                "program_baseline": now,
                "data_cheats_baseline": now,
                "data_db_baseline": now,
            }
            self._save_update_state(state)
        # Fill any missing key from install_epoch (forward-compatible).
        base = state.get("install_epoch", time.time())
        for key in ("program_baseline", "data_cheats_baseline", "data_db_baseline"):
            state.setdefault(key, base)
        return state

    def _save_update_state(self, state: dict):
        try:
            with open(UPDATE_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    # --------------------------------------------------------------- theming
    def _apply_tree_tags(self):
        """(Re)colour the table's row tags for the active theme."""
        t = theme()
        self.tree.tag_configure("done", foreground=t["ok"])
        self.tree.tag_configure("nameless", foreground=t["warn"])
        # Background tint for update/DLC title ids (cheats need the base id).
        # Background-only so it never clashes with the done/nameless text colours.
        self.tree.tag_configure("nonbase", background=t["nonbase_bg"])

    def _apply_cheat_text_style(self):
        """(Re)colour the detail panel's text widget + tags for the active theme."""
        t = theme()
        self.cheat_text.configure(
            bg=t["bg"], fg=t["fg"], insertbackground=t["fg"],
            selectbackground=t["select_bg"], selectforeground=t["select_fg"],
            inactiveselectbackground=t["select_bg"])
        _base = ("Segoe UI", 9)
        self.cheat_text.tag_config("title", font=("Segoe UI", 10, "bold"), foreground=t["title"])
        self.cheat_text.tag_config("subtle", font=_base, foreground=t["fg_muted"])
        self.cheat_text.tag_config("ok", font=("Segoe UI", 9, "bold"), foreground=t["ok"])
        self.cheat_text.tag_config("missing", font=("Segoe UI", 9, "bold"), foreground=t["error"])
        self.cheat_text.tag_config("warn", font=_base, foreground=t["warn"])
        self.cheat_text.tag_config("label", font=("Segoe UI", 9, "bold"), foreground=t["fg_muted"])
        self.cheat_text.tag_config("value", font=_base, foreground=t["fg"])
        # Monospace for hex IDs so Title/Build ID line up and read cleanly.
        self.cheat_text.tag_config("mono", font=("Consolas", 9), foreground=t["fg"])
        self.cheat_text.tag_config("section", font=("Segoe UI", 9, "bold"),
                                   foreground=t["title"], spacing1=8, spacing3=2)
        self.cheat_text.tag_config("bullet", font=_base, foreground=t["fg"],
                                   lmargin1=16, lmargin2=28, spacing1=1)

    def _apply_theme(self, name):
        """Restyle the whole program (ttk widgets, classic widgets, menus,
        sub-dialogs) for the given theme name. Safe to call before the widgets
        exist (initial styling) and again on every toggle."""
        if name not in THEMES:
            name = "dark"
        self.theme_name = name
        _ACTIVE["name"] = name
        t = theme()
        st = self._style
        try:
            st.theme_use("clam")   # the only stock theme that honours colours
        except Exception:
            pass

        BG, SURF, HOV = t["bg"], t["surface"], t["hover"]
        FIELD, FG, MUT = t["field"], t["fg"], t["fg_muted"]
        BORDER, SEL, SELFG, ACCENT = t["border"], t["select_bg"], t["select_fg"], t["accent"]

        st.configure(".", background=BG, foreground=FG, fieldbackground=FIELD,
                     bordercolor=BORDER, darkcolor=SURF, lightcolor=SURF,
                     troughcolor=SURF, arrowcolor=FG, insertcolor=FG,
                     focuscolor=ACCENT, selectbackground=SEL, selectforeground=SELFG)
        st.configure("TFrame", background=BG)
        st.configure("TLabel", background=BG, foreground=FG)
        st.configure("TLabelframe", background=BG, bordercolor=BORDER)
        st.configure("TLabelframe.Label", background=BG, foreground=MUT)
        st.configure("TButton", background=SURF, foreground=FG, bordercolor=BORDER,
                     focuscolor=BG, padding=(8, 3))
        st.map("TButton",
               background=[("pressed", HOV), ("active", HOV), ("disabled", BG)],
               foreground=[("disabled", MUT)])
        st.configure("TMenubutton", background=SURF, foreground=FG,
                     bordercolor=BORDER, arrowcolor=FG, padding=(8, 3))
        st.map("TMenubutton", background=[("active", HOV)])
        st.configure("TCheckbutton", background=BG, foreground=FG, focuscolor=BG,
                     indicatorbackground=FIELD, indicatorforeground=FG, bordercolor=BORDER)
        st.map("TCheckbutton", background=[("active", BG)], foreground=[("disabled", MUT)],
               indicatorbackground=[("selected", FIELD), ("pressed", FIELD)])
        st.configure("TRadiobutton", background=BG, foreground=FG, focuscolor=BG,
                     indicatorbackground=FIELD, indicatorforeground=FG, bordercolor=BORDER)
        st.map("TRadiobutton", background=[("active", BG)], foreground=[("disabled", MUT)],
               indicatorbackground=[("selected", FIELD), ("pressed", FIELD)])
        st.configure("TEntry", fieldbackground=FIELD, foreground=FG, insertcolor=FG,
                     bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
        st.map("TEntry", fieldbackground=[("readonly", SURF)],
               foreground=[("disabled", MUT)], bordercolor=[("focus", ACCENT)])
        st.configure("TCombobox", fieldbackground=FIELD, foreground=FG, background=SURF,
                     arrowcolor=FG, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
        st.map("TCombobox", fieldbackground=[("readonly", FIELD)],
               foreground=[("disabled", MUT)], bordercolor=[("focus", ACCENT)])
        st.configure("TProgressbar", background=ACCENT, troughcolor=SURF, bordercolor=BORDER)
        for sb in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            st.configure(sb, background=SURF, troughcolor=BG, bordercolor=BORDER, arrowcolor=FG)
            st.map(sb, background=[("active", HOV)])
        st.configure("TPanedwindow", background=BG)
        st.configure("Treeview", background=t["tree_bg"], fieldbackground=t["tree_bg"],
                     foreground=FG, bordercolor=BORDER)
        st.map("Treeview", background=[("selected", SEL)], foreground=[("selected", SELFG)])
        st.configure("Treeview.Heading", background=SURF, foreground=FG,
                     bordercolor=BORDER, relief="flat")
        st.map("Treeview.Heading", background=[("active", HOV)])

        # --- Featured "Get everything from DevCatSKZ" card --------------
        # A compact, accent-tinted card: one primary (accent) button plus two
        # quiet secondary buttons, wrapped in a thin 1px accent border (drawn by
        # FeaturedBorder.TFrame behind a 1px inset). Refined, not a neon slab.
        panel = t.get("featured_bg", SURF)
        st.configure("Featured.TFrame", background=panel)
        st.configure("FeaturedBorder.TFrame", background=t.get("featured_border", ACCENT))
        st.configure("FeaturedTitle.TLabel", background=panel, foreground=ACCENT,
                     font=("Segoe UI", 10, "bold"))
        st.configure("Featured.TLabel", background=panel, foreground=t["fg_muted"])
        st.configure("Featured.TCheckbutton", background=panel, foreground=t["fg_muted"],
                     focuscolor=panel)
        st.map("Featured.TCheckbutton", background=[("active", panel)],
               foreground=[("disabled", MUT)])
        st.configure("Accent.TButton", background=ACCENT, foreground="#ffffff",
                     bordercolor=ACCENT, focuscolor=panel, font=("Segoe UI", 9, "bold"),
                     padding=(12, 6))
        st.map("Accent.TButton",
               background=[("pressed", t["accent_press"]), ("active", t["accent_hover"]),
                           ("disabled", SURF)],
               foreground=[("disabled", MUT)])
        st.configure("FeaturedSec.TButton", background=SURF, foreground=FG,
                     bordercolor=BORDER, focuscolor=panel, padding=(10, 6))
        st.map("FeaturedSec.TButton",
               background=[("pressed", HOV), ("active", HOV), ("disabled", panel)],
               foreground=[("disabled", MUT)])

        # Combobox dropdown list is a classic Tk listbox styled via the option DB.
        self.root.option_add("*TCombobox*Listbox.background", FIELD)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", SEL)
        self.root.option_add("*TCombobox*Listbox.selectForeground", SELFG)

        self.root.configure(bg=BG)

        # Classic tk widgets (guarded — some are built after the first call).
        if hasattr(self, "log"):
            self.log.configure(bg=t["log_bg"], fg=t["log_fg"], insertbackground=t["log_fg"])
        if hasattr(self, "cheat_text"):
            self._apply_cheat_text_style()
        if hasattr(self, "tree"):
            self._apply_tree_tags()
        for menu in getattr(self, "_all_menus", []):
            try:
                menu.configure(bg=SURF, fg=FG, activebackground=SEL,
                               activeforeground=SELFG, activeborderwidth=0, relief="flat")
            except Exception:
                pass
        if hasattr(self, "online_status_lbl") and \
                self.online_status_lbl.cget("text") in ("● not checked", ""):
            self.online_status_lbl.config(foreground=MUT)
        if hasattr(self, "theme_btn"):
            self.theme_btn.configure(
                text="☀ Light Mode" if name == "dark" else "☾ Dark Mode")

    def on_toggle_theme(self):
        """Flip between dark and light mode and remember the choice."""
        self._apply_theme("light" if self.theme_name == "dark" else "dark")
        self._save_settings()
        self._append_log(f"Theme: {self.theme_name} mode.")

    # ------------------------------------------------------------------ UI
    def _build_toolbar(self):
        # Action buttons get collected here so _set_busy can disable them all.
        self._action_buttons = []
        toolbar = ttk.Frame(self.root, padding=(10, 8))
        toolbar.pack(fill="x")

        # ---- Featured: get everything from DevCatSKZ (headline action) ----
        # A compact, refined card, right-aligned in the top row so it stands out
        # as the fastest way to get all data without dominating the toolbar.
        # Styles (Featured.*/Accent.TButton) adapt to light/dark in _apply_theme.
        # ---- Section 1: External cheat sources (+ featured DevCat card) --
        # The group wraps TIGHTLY around its content (no fill="x"), so the box is
        # only as wide as the sources grid + DevCat card — it doesn't stretch
        # edge-to-edge and waste the rest of the row.
        get_group = ttk.LabelFrame(toolbar, text="External Cheat Sources", padding=(8, 4))
        get_group.pack(anchor="w", pady=(0, 6))
        gcontent = ttk.Frame(get_group)
        gcontent.pack()
        combo = ttk.Frame(gcontent)
        combo.pack()

        # Featured "Get everything from DevCatSKZ" card — the fastest, best
        # source, highlighted on the RIGHT of the other external sources so it
        # sits naturally among them without dominating the whole toolbar.
        border = ttk.Frame(combo, style="FeaturedBorder.TFrame")
        border.pack(side="right", anchor="n", padx=(12, 0))
        feat = ttk.Frame(border, style="Featured.TFrame", padding=(14, 10))
        feat.pack(padx=1, pady=1)   # 1px accent border shows around the card
        devcat_title = ttk.Label(feat, text="★  Get Everything from DevCatSKZ Github Repo",
                                 style="FeaturedTitle.TLabel")
        devcat_title.pack(anchor="w", pady=(0, 8))
        # The former sub-text now lives in a tooltip to keep the card compact.
        _Tooltip(devcat_title,
                 "Skip scraping — grab all cheats and the complete database "
                 "straight from the maintainer's GitHub. 'Download Cheats' = the "
                 "ready-made cheat archive, 'Download Database' = the full GUI "
                 "database (merged in), '★ Download Complete' = both. Tick "
                 "'Download Covers' to also fetch the cover images.")
        brow = ttk.Frame(feat, style="Featured.TFrame")
        brow.pack(anchor="w")
        self.devcat_cheats_btn = ttk.Button(
            brow, text="Download Cheats", style="FeaturedSec.TButton",
            command=self.on_devcat_cheats)
        self.devcat_cheats_btn.pack(side="left", padx=(0, 5))
        self.devcat_db_btn = ttk.Button(
            brow, text="Download Database", style="FeaturedSec.TButton",
            command=self.on_devcat_db)
        self.devcat_db_btn.pack(side="left", padx=(0, 5))
        self.devcat_all_btn = ttk.Button(
            brow, text="★  Download Complete", style="Accent.TButton",
            command=self.on_devcat_complete)
        self.devcat_all_btn.pack(side="left")
        self._action_buttons += [self.devcat_cheats_btn, self.devcat_db_btn,
                                  self.devcat_all_btn]
        # Both toggles share one row to keep the card compact and its height
        # close to the sources grid beside it.
        cbrow = ttk.Frame(feat, style="Featured.TFrame")
        cbrow.pack(anchor="w", fill="x", pady=(8, 0))
        devcat_cov_cb = ttk.Checkbutton(
            cbrow, text="Download Covers", variable=self.devcat_covers,
            style="Featured.TCheckbutton", command=self._save_settings)
        devcat_cov_cb.pack(side="left")
        update_cb = ttk.Checkbutton(
            cbrow, text="Check updates at startup",
            variable=self.update_check_startup, style="Featured.TCheckbutton",
            command=self._save_settings)
        update_cb.pack(side="left", padx=(16, 0))
        _Tooltip(devcat_cov_cb,
                 "When ON, each DevCatSKZ download also fetches the cover images "
                 "afterwards. Off by default — covers are not part of the archive "
                 "(the database stores only cover URLs) and downloading them takes "
                 "extra time. Already-saved covers are skipped.")
        # ---- Updates: same repo, checked on demand (and optionally at start) --
        urow = ttk.Frame(feat, style="Featured.TFrame")
        urow.pack(anchor="w", fill="x", pady=(8, 0))
        self.check_updates_btn = ttk.Button(
            urow, text="Check Updates", style="FeaturedSec.TButton",
            command=self.on_check_updates)
        self.check_updates_btn.pack(side="left")
        self.update_status_lbl = ttk.Label(
            urow, text=f"v{APP_VERSION}", style="Featured.TLabel",
            font=("Segoe UI", 8))
        self.update_status_lbl.pack(side="left", padx=(8, 0))
        self._action_buttons += [self.check_updates_btn]
        _Tooltip(self.check_updates_btn,
                 "Check GitHub for a newer program build AND newer cheats/database "
                 "packages. Detects both a new version (e.g. 1.1) and a re-upload "
                 "of the current release/data (a fix without a version bump, via "
                 "the upload date). Found program updates install themselves "
                 "(the app restarts); data updates are downloaded and imported.")
        _Tooltip(update_cb,
                 "ON: quietly check GitHub for updates at every program start and "
                 "notify you if something is newer.\nOFF: only check when you click "
                 "'Check Updates'.")
        _Tooltip(self.devcat_cheats_btn,
                 "Download the maintainer's ready-made cheats archive and import "
                 "it — all cheat files without scraping cheatslips yourself.")
        _Tooltip(self.devcat_db_btn,
                 "Download the maintainer's complete database (names, regions, "
                 "versions, descriptions, cover URLs) and merge it into yours.")
        _Tooltip(self.devcat_all_btn,
                 "Download BOTH the cheats archive and the full database in one go "
                 "— the fastest way to get everything. Tick 'Download Covers' "
                 "below to fetch the cover images as well.")

        # Grid of the other sources on the LEFT. A 3-column x 4-row layout keeps
        # the block a sensible width (not edge-to-edge) and about as tall as the
        # DevCat card beside it, so the two read as one balanced unit.
        src_grid = ttk.Frame(combo)
        src_grid.pack(side="left", anchor="n")
        self.gba_btn = ttk.Button(src_grid, text="Download GBATemp Archive", command=self.on_gbatemp)
        self.hamlet_btn = ttk.Button(src_grid, text="Download Hamlet TitleDB",
                                     command=self.on_hamlet_titledb)
        self.hamlet_60fps_btn = ttk.Button(src_grid, text="Download Hamlet 60FPS/Res/GFX",
                                           command=self.on_hamlet_60fps)
        self.tdb_btn = ttk.Button(src_grid, text="Download TitleDB", command=self.on_titledb_cheats)
        self.ibnux_btn = ttk.Button(src_grid, text="Download Ibnux", command=self.on_ibnux)
        self.sthetix_btn = ttk.Button(src_grid, text="Download Sthetix TitleDB",
                                      command=self.on_sthetix)
        self.breeze_btn = ttk.Button(src_grid, text="Download Breeze NXCheatCode",
                                     command=self.on_breeze)
        self.chansey_btn = ttk.Button(src_grid, text="Download Chansey 60FPS/Res/GFX",
                                      command=self.on_chansey)
        self.mynx_btn = ttk.Button(src_grid, text="Download MyNXCheats",
                                   command=self.on_mynx)
        self.import_disk_btn = ttk.Button(src_grid, text="Import Folder", command=self.on_import_disk)
        self.import_zip_btn = ttk.Button(src_grid, text="Import ZIP", command=self.on_import_zip)
        self.everything_btn = ttk.Button(src_grid, text="★ Scrape & Download Everything",
                                         command=self.on_scrape_download_everything)
        # A tidy 3-column x 4-row grid. 'uniform' makes every column the same
        # width (sized to the widest button) so the block is a clean rectangle
        # and the buttons line up perfectly, without stretching to fill the whole
        # window. Order flows left-to-right, top-to-bottom.
        _srcs = [self.gba_btn, self.hamlet_btn, self.hamlet_60fps_btn,
                 self.tdb_btn, self.ibnux_btn, self.sthetix_btn,
                 self.breeze_btn, self.chansey_btn, self.mynx_btn,
                 self.import_disk_btn, self.import_zip_btn, self.everything_btn]
        _COLS = 3
        for i, btn in enumerate(_srcs):
            r, c = divmod(i, _COLS)
            btn.grid(row=r, column=c, sticky="ew", padx=(0, 4), pady=(0, 4))
        for c in range(_COLS):
            src_grid.columnconfigure(c, weight=1, uniform="srccol")

        self._action_buttons += [self.gba_btn, self.hamlet_btn, self.hamlet_60fps_btn,
                                 self.tdb_btn, self.ibnux_btn,
                                 self.sthetix_btn, self.breeze_btn,
                                 self.chansey_btn, self.mynx_btn,
                                 self.import_disk_btn, self.import_zip_btn,
                                 self.everything_btn]
        _Tooltip(self.gba_btn,
                 "Download the GBATemp/HamletDuFromage cheat archive, import all "
                 "cheats (source=gbatemp), then fill names/region + titledb versions "
                 "and recount from disk.")
        _Tooltip(self.hamlet_btn,
                 "Download HamletDuFromage's titles_complete.zip from the LATEST "
                 "switch-cheats-db release (always the newest), import all cheats "
                 "(source=hamlet-titledb), then fill names/region + titledb versions "
                 "and recount from disk.")
        _Tooltip(self.hamlet_60fps_btn,
                 "Download HamletDuFromage's titles_60fps-res-gfx.zip (60 FPS / "
                 "resolution / GFX cheats) from the LATEST switch-cheats-db release "
                 "(always the newest), import all cheats (source=hamlet-60fps), then "
                 "fill names/region + titledb versions and recount from disk.")
        _Tooltip(self.sthetix_btn,
                 "Download titles_complete.zip from the LATEST sthetix/nx-cheats-db "
                 "release — a DAILY-updated aggregate of GBAtemp + graphics cheats + "
                 "switch-cheats-db + cheatslips (~141k cheats). Import all cheats "
                 "(source=sthetix), then fill names/region + versions + recount.")
        _Tooltip(self.breeze_btn,
                 "Download titles.zip (the Breeze/EdiZon-SE cheat database) from the "
                 "LATEST tomvita/NXCheatCode release — GBAtemp community codes, partly "
                 "different from cheatslips. Import (source=breeze), then fill "
                 "names/region + versions + recount.")
        _Tooltip(self.chansey_btn,
                 "Import the LIVE ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats repo — the "
                 "ORIGINAL source of the 60 FPS / resolution / graphics cheats, always "
                 "current. Import (source=chansey-60fps), then fill names/region + "
                 "versions + recount.")
        _Tooltip(self.mynx_btn,
                 "Import the LIVE Arch9SK7/MyNXCheats repo — a curated collection for "
                 "~50 recent big titles (TotK, Scarlet/Violet, ...). Import "
                 "(source=mynxcheats), then fill names/region + versions + recount.")
        _Tooltip(self.tdb_btn,
                 "Import titledb's own cheats.json as an extra source "
                 "(source=titledb), then fill names/region + versions + recount.")
        _Tooltip(self.ibnux_btn,
                 "Download the ibnux/switch-cheat archive and import its cheats "
                 "(source=ibnux), then fill names/region + versions + recount.")
        _Tooltip(self.import_disk_btn,
                 "Scan the output folder (titles/ and by_bid/) and import cheat "
                 "files that aren't in the database yet (source=disk). No download.")
        _Tooltip(self.import_zip_btn,
                 "Import a cheat ZIP archive (e.g. one exported with 'Export to "
                 "ZIP', or any Atmosphère/Breeze/EdiZon-layout archive) back into "
                 "the database + output folder (source=import-zip).")
        _Tooltip(self.everything_btn,
                 "One click: cheatslips scrape (/entry feed) + ALL external "
                 "archives (GBATemp, HamletDuFromage ×2, Sthetix, Breeze, Chansey, "
                 "MyNXCheats, titledb, ibnux), then names/covers/region/versions, "
                 "download all cheat files and covers. Long-running; Stop anytime.")

        # ---- Section 2: Get cheat information (enrich) + Search ------------
        row2 = ttk.Frame(toolbar)
        row2.pack(fill="x", pady=(0, 6))

        enrich_group = ttk.LabelFrame(row2, text="Get Cheat Information", padding=(8, 4))
        enrich_group.pack(side="left", fill="y", padx=(0, 8))
        self.names_btn = ttk.Button(enrich_group, text="Get Names",
                                    command=self.on_get_names)
        self.names_btn.pack(side="left", padx=(0, 4))
        self.region_btn = ttk.Button(enrich_group, text="Get Region",
                                     command=self.on_get_region)
        self.region_btn.pack(side="left", padx=(0, 4))
        self.vt_btn = ttk.Button(enrich_group, text="Get Versions from TitleDB",
                                 command=self.on_get_versions_titledb)
        self.vt_btn.pack(side="left", padx=(0, 4))
        self.vc_btn = ttk.Button(enrich_group, text="Get Versions Cheatslips",
                                 command=self.on_get_versions_cheatslips)
        self.vc_btn.pack(side="left", padx=(0, 4))
        self.desc_btn = ttk.Button(enrich_group, text="Get Descriptions",
                                   command=self.on_get_descriptions)
        self.desc_btn.pack(side="left", padx=(0, 4))
        self.covers_btn = ttk.Button(enrich_group, text="Download Covers",
                                     command=self.on_download_covers)
        self.covers_btn.pack(side="left", padx=(0, 4))
        self._action_buttons += [self.names_btn, self.region_btn, self.vt_btn,
                                  self.vc_btn, self.desc_btn, self.covers_btn]
        _Tooltip(self.names_btn,
                 "Fill missing game names + covers + metadata from titledb regions, "
                 "then the CheatSlips API, switchbrew, tinfoil, GitHub lists and "
                 "finally by inheriting from the base game.")
        _Tooltip(self.region_btn,
                 "Tag every title with its eShop region(s) (US/EU/AU/JP/KR/HK) "
                 "from the titledb region files.")
        _Tooltip(self.vt_btn,
                 "Fill build versions from titledb only (builds.json / "
                 "versions.json) — fast, no cheatslips.")
        _Tooltip(self.vc_btn,
                 "Fill the remaining build versions from cheatslips' game pages "
                 "(HTML) — slower; only needed for builds titledb doesn't cover.")
        _Tooltip(self.desc_btn,
                 "Fill missing game descriptions + intro texts for all titles from "
                 "titledb (English regions). Downloads/caches the region files.")
        _Tooltip(self.covers_btn,
                 "Download the cover images of all database entries to "
                 "coversdownload/ (already-saved covers are skipped).")

        # ---- Section 3: Download cheat files (own area) --------------------
        dl_group = ttk.LabelFrame(toolbar, text="Scrape & Download Cheat Files · cheatslips.com", padding=(8, 6))
        dl_group.pack(fill="x")

        auth = ttk.Frame(dl_group)
        auth.pack(fill="x", pady=(0, 6))
        ttk.Label(auth, text="Email:").pack(side="left", padx=(0, 4))
        ttk.Entry(auth, textvariable=self.email_var, width=34).pack(side="left", padx=(0, 8))
        ttk.Label(auth, text="Password:").pack(side="left", padx=(0, 4))
        pw_ent, pw_btn = self._secret_entry(auth, self.password_var, 16)
        pw_ent.pack(side="left", padx=(0, 2))
        pw_btn.pack(side="left", padx=(0, 8))
        ttk.Checkbutton(auth, text="remember", variable=self.remember_pw).pack(side="left", padx=(0, 10))
        ttk.Label(auth, text="or Token:").pack(side="left", padx=(0, 4))
        tok_ent, tok_btn = self._secret_entry(auth, self.api_token_var, 30)
        tok_ent.pack(side="left", padx=(0, 2))
        tok_btn.pack(side="left", padx=(0, 8))
        self.browser_login_btn = ttk.Button(auth, text="Browser Login",
                                            command=self.on_browser_login)
        self.browser_login_btn.pack(side="left")
        self._action_buttons += [self.browser_login_btn]
        # Online indicator + manual check + startup-check toggle. The check
        # runs in its own thread and is deliberately NOT busy-managed, so the
        # user can check any time — even while a download is running.
        self.online_status_lbl = ttk.Label(auth, text="● not checked",
                                           foreground=theme()["fg_muted"])
        self.online_status_lbl.pack(side="left", padx=(14, 4))
        self.check_online_btn = ttk.Button(auth, text="Check Online",
                                           command=self.on_check_online)
        self.check_online_btn.pack(side="left", padx=(0, 4))
        online_cb = ttk.Checkbutton(auth, text="check at startup",
                                    variable=self.online_check_startup)
        online_cb.pack(side="left")
        _Tooltip(self.online_status_lbl,
                 "Whether cheatslips.com is currently reachable — green = online, "
                 "red = offline. Checked at program start (if enabled) and via "
                 "'Check Online'.")
        _Tooltip(self.check_online_btn,
                 "Check right now whether cheatslips.com is online. Works any "
                 "time, even while a download or scrape is running.")
        _Tooltip(online_cb,
                 "ON: automatically check whether cheatslips.com is online at "
                 "every program start.\nOFF: no automatic check (use the "
                 "'Check Online' button instead).")
        _Tooltip(self.browser_login_btn,
                 "One-time cheatslips login in the embedded browser: your "
                 "email/password are pre-filled, you only solve the reCAPTCHA. "
                 "The session cookies are saved to the persistent profile, so "
                 "every future browser download / quota reset logs in "
                 "automatically — you never have to log in again.")

        scrape = ttk.Frame(dl_group)
        scrape.pack(fill="x", pady=(0, 6))
        self.scrape_btn = ttk.Button(scrape, text="Scrape", command=self.on_scrape_all)
        self.scrape_btn.pack(side="left", padx=(0, 6))
        self.update_btn = ttk.Button(scrape, text="Update Recent", command=self.on_update_recent)
        self.update_btn.pack(side="left", padx=(0, 2))
        ttk.Label(scrape, text="pages:").pack(side="left")
        ttk.Spinbox(scrape, from_=1, to=50, width=3, textvariable=self.update_pages).pack(side="left", padx=(2, 12))
        def _opt(text, var, tip, pad=(0, 8)):
            cb = ttk.Checkbutton(scrape, text=text, variable=var)
            cb.pack(side="left", padx=pad)
            _Tooltip(cb, tip)
            return cb

        _opt("full catalog (all games, slower)", self.scrape_full_catalog,
             "ON: scan the COMPLETE cheatslips catalog (~29k games) — slower.\n"
             "OFF: use the fast /entry 'latest cheats' feed (~1900 games). Both find "
             "the same cheat-having builds.")
        _opt("skip 0-cheat builds", self.scrape_skip_zero,
             "ON: drop builds that show 0 cheats during the scrape.\n"
             "OFF (default): keep them, so nothing is hidden and 0-cheat builds stay "
             "visible under 'Not downloaded'.")
        _opt("rescan", self.rescan_all,
             "ON: re-scrape games that are already in the database.\n"
             "OFF: skip known games (much faster incremental scan).")
        _opt("download after scrape", self.auto_download,
             "ON: right after the scrape finishes, automatically start downloading "
             "the cheat files.", pad=(0, 14))
        self.stop_btn = ttk.Button(scrape, text="Stop", command=self.on_stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(0, 14))
        self._action_buttons += [self.scrape_btn, self.update_btn]
        _Tooltip(self.scrape_btn,
                 "Scrape cheat metadata from cheatslips.com (Title/Build IDs, names, "
                 "cheat names). With a valid token the cheat files are saved in the "
                 "same pass.")
        _Tooltip(self.update_btn,
                 "Only scan the newest 'latest cheats' pages (set 'pages') to pick up "
                 "recently added/updated cheats — much faster than a full scrape.")

        action = ttk.Frame(dl_group)
        action.pack(fill="x")
        ttk.Label(action, text="Output:").pack(side="left", padx=(0, 4))
        out_entry = ttk.Entry(action, textvariable=self.dl_output, width=52)
        out_entry.pack(side="left", padx=(0, 2))
        out_entry.bind("<KeyRelease>", lambda _e: self.refresh_table())
        ttk.Button(action, text="...", width=3, command=self._choose_output).pack(side="left", padx=(0, 2))
        ttk.Button(action, text="Open", width=5, command=self._open_output).pack(side="left", padx=(0, 8))

        # Options row: browser fallback + browser choice + manual reset.
        opts = ttk.Frame(dl_group)
        opts.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(
            opts, text="Download via browser when API is limited (keeps downloading until complete)",
            variable=self.auto_reset_quota).pack(side="left", padx=(0, 12))
        ttk.Label(opts, text="Browser:").pack(side="left", padx=(0, 3))
        ttk.Combobox(opts, textvariable=self.browser_choice, state="readonly", width=10,
                     values=list(_BROWSER_KINDS.keys())).pack(side="left", padx=(0, 12))
        self.reset_quota_btn = ttk.Button(
            opts, text="Reset API Limit", command=self.on_reset_api_limit)
        self.reset_quota_btn.pack(side="left")
        self._action_buttons += [self.reset_quota_btn]
        _Tooltip(self.reset_quota_btn,
                 "Open the browser and click cheatslips' 'reset my quota' once. "
                 "Resets the WEBSITE download limit (helps browser downloads), NOT "
                 "the API daily quota.")

        # Dedicated download-actions row (left = smallest scope, right = biggest).
        dlrow = ttk.Frame(dl_group)
        dlrow.pack(fill="x", pady=(6, 2))
        ttk.Label(dlrow, text="Download:").pack(side="left", padx=(0, 6))
        self.dl_api_btn = ttk.Button(dlrow, text="Download (API only)", command=self.on_download_api)
        self.dl_api_btn.pack(side="left", padx=(0, 4))
        self.dl_sel_btn = ttk.Button(dlrow, text="Download Selected", command=self.on_download_selected)
        self.dl_sel_btn.pack(side="left", padx=(0, 4))
        self.dl_browser_btn = ttk.Button(dlrow, text="Download via Browser",
                                         command=self.on_download_browser)
        self.dl_browser_btn.pack(side="left", padx=(0, 4))
        self.dl_all_btn = ttk.Button(dlrow, text="Build Full Dataset", command=self.on_download_all)
        self.dl_all_btn.pack(side="left", padx=(0, 4))
        self._action_buttons += [self.dl_api_btn, self.dl_sel_btn, self.dl_browser_btn,
                                  self.dl_all_btn]
        _Tooltip(self.dl_api_btn,
                 "Download cheat files via the official API ONLY (never the browser). "
                 "Uses the selected rows, or ALL games if nothing is selected. "
                 "Stops when the API daily quota is hit.")
        _Tooltip(self.dl_sel_btn,
                 "Download the SELECTED rows. Uses the API and — if 'Download via "
                 "browser when API is limited' is ticked — falls back to the browser "
                 "for whatever the API can't deliver.")
        _Tooltip(self.dl_browser_btn,
                 "Download via the logged-in browser directly (bypass the API limit). "
                 "Uses the selected rows, or ALL still-missing builds if nothing is "
                 "selected. Resets the website quota automatically; uses the chosen "
                 "Browser. Fetches all source pages of a build and merges them.")
        _Tooltip(self.dl_all_btn,
                 "Build the COMPLETE dataset for ALL games: download every cheat "
                 "file (API + optional browser fallback), then fill names/region/"
                 "versions, fix ID names and fix 0-cheat entries.")

        # ---- Search + table filters: last toolbar row, sits directly above the
        # database table columns (below the download buttons). --------------
        search_row = ttk.Frame(toolbar)
        search_row.pack(fill="x", pady=(8, 0))
        search_group = ttk.LabelFrame(search_row, text="Search", padding=(8, 4))
        search_group.pack(side="left", fill="both", expand=True)
        search_entry = ttk.Entry(search_group, textvariable=self.search_var, width=20)
        search_entry.pack(side="left", padx=(0, 8))
        search_entry.bind("<KeyRelease>", lambda _e: self._debounced_refresh_table())
        ttk.Checkbutton(search_group, text="Auto scan", variable=self.auto_scan_downloaded,
                        command=self.refresh_table).pack(side="left", padx=(0, 4))
        ttk.Checkbutton(search_group, text="Not downloaded", variable=self.not_downloaded_only,
                        command=self.refresh_table).pack(side="left", padx=(0, 4))
        ttk.Checkbutton(search_group, text="Show Unnamed Games", variable=self.names_missing,
                        command=self.refresh_table).pack(side="left", padx=(0, 4))
        ttk.Checkbutton(search_group, text="Hide placeholder builds", variable=self.hide_placeholder_builds,
                        command=self.refresh_table).pack(side="left", padx=(0, 4))
        ttk.Checkbutton(search_group, text="Show Covers", variable=self.show_images,
                        command=self._on_select_row).pack(side="left", padx=(0, 4))
        ttk.Checkbutton(search_group, text="Save Covers", variable=self.cache_covers,
                        command=self._on_select_row).pack(side="left", padx=(0, 4))
        ttk.Checkbutton(search_group, text="Show Description", variable=self.show_description,
                        command=self._on_select_row).pack(side="left")
        # Dark/light toggle, far right of the filter row. Label shows the mode
        # you'll switch TO; _apply_theme keeps it in sync.
        self.theme_btn = ttk.Button(
            search_group, width=13, command=self.on_toggle_theme,
            text="☀ Light Mode" if self.theme_name == "dark" else "☾ Dark Mode")
        self.theme_btn.pack(side="right", padx=(6, 2))
        _Tooltip(self.theme_btn, "Switch between dark and light mode (saved between runs).")

    def _build_main(self):
        # Table (left) + cheat-names panel (right), resizable.
        paned = ttk.Panedwindow(self._top_container, orient="horizontal")
        paned.pack(side="top", fill="both", expand=True, padx=10)

        left = ttk.Frame(paned)
        columns = [c[0] for c in COLUMNS]
        self.tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="extended")
        for col_id, heading, width, anchor in COLUMNS:
            self.tree.heading(col_id, text=heading,
                              command=lambda c=col_id: self._sort_by(c))
            self.tree.column(col_id, width=width, anchor=anchor, stretch=(col_id == "game_title"))
        self._apply_tree_tags()
        vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._copy_cell)
        self.tree.bind("<<TreeviewSelect>>", self._on_select_row)
        self.tree.bind("<Button-3>", self._show_context_menu)
        # Ctrl+A = select all rows, Ctrl+C = copy selected rows (tab-separated).
        self.tree.bind("<Control-a>", self._tree_select_all)
        self.tree.bind("<Control-A>", self._tree_select_all)
        self.tree.bind("<Control-c>", self._tree_copy)
        self.tree.bind("<Control-C>", self._tree_copy)

        # Right-click context menu, grouped by task (download → inspect →
        # edit → metadata → destructive → global). Entry indices are recorded
        # in self._ctx_index so _show_context_menu never relies on hard-coded
        # positions when relabelling entries for multi-selections.
        self.context_menu = tk.Menu(self.tree, tearoff=0)
        self._all_menus.append(self.context_menu)
        self._ctx_index = {}

        def _ctx_add(key, label, command):
            self.context_menu.add_command(label=label, command=command)
            self._ctx_index[key] = self.context_menu.index("end")

        # -- get the cheats -------------------------------------------------
        _ctx_add("download", "Download this", self._ctx_download)
        _ctx_add("download_api", "Download via API", self._ctx_api_download)
        _ctx_add("download_browser", "Download via browser (bypass API limit)",
                 self._ctx_browser_download)
        self.context_menu.add_separator()
        # -- inspect the build / its file on disk ---------------------------
        _ctx_add("check_file", "Check Cheat File", self._ctx_check_cheat_file)
        _ctx_add("open_explorer", "Open in Explorer", self._ctx_open_in_explorer)
        _ctx_add("open_link", "Open cheatslips page", self._ctx_open_link)
        _ctx_add("export_zip", "Export to ZIP", self._ctx_export_zip)
        self.context_menu.add_separator()
        # -- edit / create ---------------------------------------------------
        _ctx_add("edit_codes", "Edit entry (codes)", self._ctx_edit_entry)
        _ctx_add("edit_ids", "Edit Title ID / Build ID", self._ctx_edit_ids)
        _ctx_add("add_new", "Add new entry", self._ctx_add_new_entry)
        self.context_menu.add_separator()
        # -- metadata / enrichment -------------------------------------------
        # Same actions as the "Get Cheat Information" toolbar section, available
        # here too. These run over the whole database (like the buttons do).
        # These run for the SELECTED rows only (fall back to all when nothing
        # is selected) — see the _ctx_get_* wrappers.
        info_menu = tk.Menu(self.context_menu, tearoff=0)
        self._all_menus.append(info_menu)
        info_menu.add_command(label="Get Names", command=self._ctx_get_names)
        info_menu.add_command(label="Get Region", command=self._ctx_get_region)
        info_menu.add_command(label="Get Versions from TitleDB",
                              command=self._ctx_get_versions_titledb)
        info_menu.add_command(label="Get Versions Cheatslips",
                              command=self._ctx_get_versions_cheatslips)
        info_menu.add_command(label="Get Descriptions", command=self._ctx_get_descriptions)
        info_menu.add_separator()
        info_menu.add_command(label="Download Covers (all)", command=self.on_download_covers)
        info_menu.add_command(label="Download cover (selected)",
                              command=self._ctx_download_covers)
        self._ctx_info_cover_index = info_menu.index("end")  # relabelled per selection
        self.context_menu.add_cascade(label="Get Cheat Information", menu=info_menu)
        self._ctx_info_menu = info_menu  # keep a reference alive
        self.context_menu.add_separator()
        # -- destructive, isolated at the bottom so it can't be misclicked ---
        _ctx_add("delete", "Delete entry", self._ctx_delete)
        self.context_menu.add_separator()
        # -- global (not row-specific) ---------------------------------------
        _ctx_add("reset_quota", "Reset API Limit", self._ctx_reset_api_limit)
        paned.add(left, weight=3)

        right = ttk.Labelframe(paned, text="Game", padding=(8, 6))
        self.cover_label = ttk.Label(right, anchor="center")
        self.cover_label.pack(side="top", fill="x", pady=(0, 6))
        txtframe = ttk.Frame(right)
        txtframe.pack(side="top", fill="both", expand=True)
        # Match the surrounding panel background (set per theme in _apply_theme).
        self.cheat_text = tk.Text(txtframe, width=30, wrap="word", state="disabled",
                                  font=("Segoe UI", 9),
                                  relief="flat", padx=8, pady=6, tabs=("104",),
                                  cursor="arrow", highlightthickness=0)
        cvsb = ttk.Scrollbar(txtframe, orient="vertical", command=self.cheat_text.yview)
        self.cheat_text.configure(yscrollcommand=cvsb.set)
        self.cheat_text.pack(side="left", fill="both", expand=True)
        cvsb.pack(side="right", fill="y")
        self._apply_cheat_text_style()
        paned.add(right, weight=1)

    def _build_database_bar(self):
        # Bottom row under the table: database actions + DB path. Packed at the
        # bottom BEFORE the table so its height is always reserved (never
        # clipped when the window/log leaves the table little room).
        bar = ttk.LabelFrame(self._top_container, text="Database", padding=(8, 4))
        bar.pack(side="bottom", fill="x", padx=10, pady=(6, 0))

        left = ttk.Frame(bar)
        left.pack(side="left")
        self.refresh_btn = ttk.Button(left, text="Refresh", command=self.on_refresh)
        self.refresh_btn.pack(side="left", padx=(0, 4))
        self.add_btn = ttk.Button(left, text="Add Entry", command=self.on_add_entry)
        self.add_btn.pack(side="left", padx=(0, 4))
        self.csv_btn = ttk.Button(left, text="Export CSV", command=self.on_export_csv)
        self.csv_btn.pack(side="left", padx=(0, 4))
        self.exportdb_btn = ttk.Button(left, text="Export DB", command=self.on_export_db)
        self.exportdb_btn.pack(side="left", padx=(0, 4))
        self.importdb_btn = ttk.Button(left, text="Import DB", command=self.on_import_db)
        self.importdb_btn.pack(side="left", padx=(0, 4))
        self.exportsd_btn = ttk.Button(left, text="Export to SD", command=self.on_export_sd)
        self.exportsd_btn.pack(side="left", padx=(0, 4))
        self.exportzip_btn = ttk.Button(left, text="Export to ZIP", command=self.on_export_zip)
        self.exportzip_btn.pack(side="left", padx=(0, 4))

        # Rarely-used repairs tucked into a small dropdown menu.
        self.repair_btn = ttk.Menubutton(left, text="Repair ▾")
        repair_menu = tk.Menu(self.repair_btn, tearoff=0)
        self._all_menus.append(repair_menu)
        repair_menu.add_command(label="Clean invalid cheat files", command=self.on_clean_invalid)
        repair_menu.add_command(label="Retry quota-skipped builds", command=self.on_retry_quota_skipped)
        repair_menu.add_command(label="Retry 'unavailable' builds", command=self.on_clear_unavailable)
        repair_menu.add_separator()
        repair_menu.add_command(label="Fix 0-cheat entries", command=self.on_fix_zero)
        repair_menu.add_command(label="Recount cheats from disk", command=self.on_recount_disk)
        repair_menu.add_command(label="Scan for empty cheat files", command=self.on_find_empty)
        repair_menu.add_command(label="Fix ID names", command=self.on_fix_id_names)
        repair_menu.add_separator()
        repair_menu.add_command(label="Sync titles folder with DB", command=self.on_sync_titles)
        self.repair_btn["menu"] = repair_menu
        self.repair_btn.pack(side="left", padx=(0, 4))

        self.clear_btn = ttk.Button(left, text="Clear DB", command=self.on_clear_db)
        self.clear_btn.pack(side="left", padx=(0, 4))

        ttk.Label(left, textvariable=self.total_games_var).pack(side="left", padx=(12, 0))

        self.nonbase_btn = ttk.Button(left, text="Update/DLC IDs", command=self._toggle_nonbase,
                                      width=13)
        self.nonbase_btn.pack(side="left", padx=(12, 0))
        self._action_buttons += [self.nonbase_btn]

        # DB path on the right, expands to fill the remaining width.
        right = ttk.Frame(bar)
        right.pack(side="right", fill="x", expand=True, padx=(12, 0))
        ttk.Label(right, text="DB:").pack(side="left")
        ttk.Button(right, text="...", width=3, command=self._choose_db).pack(side="right")
        ttk.Entry(right, textvariable=self.db_path).pack(side="left", fill="x", expand=True, padx=(4, 4))

        self._action_buttons += [self.add_btn, self.csv_btn, self.exportdb_btn,
                                 self.importdb_btn, self.exportsd_btn, self.exportzip_btn,
                                 self.repair_btn, self.clear_btn]
        _Tooltip(self.importdb_btn,
                 "Import a previously exported database (.db). Merge it into the "
                 "current database (nothing removed) or replace the current one "
                 "entirely (a backup is made first).")
        _Tooltip(self.exportsd_btn,
                 "Copy the downloaded cheat files onto a Switch SD card in the "
                 "layout Atmosphère / Breeze / EdiZon expects. Auto-detects the "
                 "card; skips empty/stub files; merges with existing SD cheats.")
        _Tooltip(self.exportzip_btn,
                 "Export all downloaded cheats into a ZIP with the SD-card layout "
                 "(Atmosphère / Breeze / EdiZon). Unzip it onto the SD-card root "
                 "to install. Skips empty/stub files.")
        _Tooltip(self.refresh_btn,
                 "Reconcile every build's cheat count with the actual .txt files "
                 "on disk, then rescan downloaded status and redraw the table.")
        _Tooltip(self.add_btn,
                 "Manually add a cheat entry: Title ID, Build ID, cheat codes "
                 "(Atmosphere format), name and version.")
        _Tooltip(self.csv_btn,
                 "Export the (filtered) database to a UTF-8 CSV with all columns "
                 "(Excel-compatible).")
        _Tooltip(self.exportdb_btn,
                 "Save a consistent copy of the whole cheats.db (SQLite backup) "
                 "to a location you choose.")
        _Tooltip(self.repair_btn,
                 "Maintenance tools: clean invalid files, retry quota-skipped / "
                 "'unavailable' builds, fix 0-cheat entries, recount from disk, "
                 "scan for empty files, fix ID names, sync titles folder.")
        _Tooltip(self.clear_btn,
                 "Empty the database AND delete all downloaded files on disk "
                 "(cheats, covers, ZIP, caches). Keeps titledb caches + settings.")
        _Tooltip(self.nonbase_btn,
                 "Toggle a filter that shows only update/DLC title ids "
                 "(…800 / non-…000) — these need the base id on the console.")

    def _build_log(self):
        # Lives in the bottom pane of the vertical splitter so it can be dragged
        # taller. weight=1 (vs. 5 for the table) sets a compact initial height.
        frame = ttk.Frame(self.vpaned, padding=(10, 6))
        self.vpaned.add(frame, weight=1)
        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, textvariable=self.status_var).pack(side="left")
        self.progress = ttk.Progressbar(top, mode="determinate", length=220)
        self.progress.pack(side="right")
        logbox = ttk.Frame(frame)
        logbox.pack(fill="both", expand=True, pady=(4, 0))
        self.log = tk.Text(logbox, height=7, wrap="none", state="disabled",
                           bg=theme()["log_bg"], fg=theme()["log_fg"], font=("Consolas", 9))
        lvsb = ttk.Scrollbar(logbox, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=lvsb.set)
        lvsb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

    # ----------------------------------------------------------------- data
    def _debounced_refresh_table(self, delay_ms: int = 300):
        """Refresh the table after the user stops typing in the search box."""
        if self._search_after_id is not None:
            self.root.after_cancel(self._search_after_id)
        self._search_after_id = self.root.after(delay_ms, self._do_refresh_table)

    def _do_refresh_table(self):
        self._search_after_id = None
        self.refresh_table()

    def _downloaded_cache_path(self, output: str = None) -> Path:
        return Path(output or self.dl_output.get()) / ".downloaded_cache.json"

    def _load_downloaded_cache(self, output: str = None) -> set:
        cache_path = self._downloaded_cache_path(output)
        if not cache_path.exists():
            return set()
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            return {str(bid).upper() for bid in data.get("build_ids", [])}
        except Exception:
            return set()

    def _save_downloaded_cache(self, build_ids: set, output: str = None) -> None:
        cache_path = self._downloaded_cache_path(output)
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps({"build_ids": sorted(build_ids)}, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            print(f"Could not save downloaded cache: {exc}")

    def _update_downloaded_cache_incremental(self) -> None:
        """Quickly update the cache with files modified since the last busy start.

        Called automatically after a download operation so the 'Not downloaded'
        filter stays accurate even when auto-scan is disabled.
        """
        start = self._last_busy_start
        if start is None:
            return
        try:
            new_bids = scan_downloaded_build_ids(self.dl_output.get(), modified_since=start)
            if not new_bids:
                return
            cached = self._load_downloaded_cache()
            cached.update(new_bids)
            self._save_downloaded_cache(cached)
            print(f"Downloaded cache updated with {len(new_bids)} new build(s).")
        except Exception as exc:
            print(f"Incremental cache update failed: {exc}")

    def _get_downloaded_build_ids(self, force_scan: bool = False,
                                  auto_scan: bool = None, output: str = None):
        """Return the set of build ids whose cheat files are on disk.

        If auto-scan is enabled or force_scan is True, perform a live disk scan
        and persist the result to a JSON cache. Otherwise, read the cache.

        ``auto_scan``/``output`` may be passed explicitly (snapshots taken on
        the main thread) so this can safely run inside a worker thread without
        touching Tk variables.

        Returns (build_ids, scan_kind) where scan_kind is one of:
        'live', 'cached', or 'fallback' (live failed, used cache).
        """
        if auto_scan is None:
            auto_scan = self.auto_scan_downloaded.get()
        if output is None:
            output = self.dl_output.get()
        if auto_scan or force_scan:
            try:
                downloaded = scan_downloaded_build_ids(output)
                self._save_downloaded_cache(downloaded, output)
                return downloaded, "live"
            except Exception as exc:
                print(f"Live scan failed: {exc}; falling back to cache.")
                return self._load_downloaded_cache(output), "fallback"
        return self._load_downloaded_cache(output), "cached"

    def refresh_table(self, force_scan: bool = False):
        """Rebuild the table without blocking the UI.

        The DB query and the disk scan run in a background thread; the rows are
        then inserted on the Tk thread in chunks, so even 5000+ rows never
        freeze the window. A generation counter cancels superseded refreshes
        (e.g. while typing in the search box).
        """
        self._refresh_gen += 1
        gen = self._refresh_gen
        # Snapshot every Tk variable here (main thread) — the worker thread
        # must never touch Tk objects.
        snap = {
            "db_path": self.db_path.get(),
            "term": self.search_var.get().strip() or None,
            "output": self.dl_output.get(),
            "auto_scan": self.auto_scan_downloaded.get(),
            "force_scan": force_scan,
            "not_downloaded": self.not_downloaded_only.get(),
            "names_missing": self.names_missing.get(),
            "nonbase_only": self.nonbase_only.get(),
            "hide_placeholder": self.hide_placeholder_builds.get(),
        }
        threading.Thread(target=self._refresh_table_worker, args=(gen, snap),
                         daemon=True).start()

    def _refresh_table_worker(self, gen, snap):
        """Background part of refresh_table: query + scan + row preparation.

        Results are handed back through the _log_queue (drained on the Tk
        thread every 150 ms) — root.after() is NOT thread-safe from here.
        """
        path = Path(snap["db_path"])
        if not path.exists():
            self._log_queue.put(("table_rows", gen, [], "0 games",
                f"No database yet at {path} - click 'Scrape all' to build it."))
            return
        try:
            db = GameDatabase(path)
            try:
                rows = db.search(term=snap["term"])
                total_games = db.count_games()
            finally:
                db.close()
            downloaded, scan_kind = self._get_downloaded_build_ids(
                force_scan=snap["force_scan"], auto_scan=snap["auto_scan"],
                output=snap["output"])
        except Exception as exc:
            self._log_queue.put(("table_rows", gen, [], None,
                                 f"Refresh failed: {exc}"))
            return
        if gen != self._refresh_gen:
            return  # superseded while querying — skip the row prep
        prepared = []
        have = nameless = nonbase = 0
        for r in rows:
            bid = (r["build_id"] or "").upper()
            is_done = bid in downloaded
            has_name = bool(r["game_title"])
            kind = title_id_kind(r["title_id"])
            is_nonbase = kind in ("update", "dlc")
            # "Not downloaded" shows complete entries whose cheat file is
            # not yet on disk.
            if snap["not_downloaded"] and is_done:
                continue
            if snap["names_missing"] and has_name:
                continue
            if snap["nonbase_only"] and not is_nonbase:
                continue
            if snap["hide_placeholder"] and is_placeholder_build_id(bid, r["title_id"]):
                continue
            tags = []
            if not has_name:
                tags.append("nameless")
            if is_done:
                tags.append("done")
            if is_nonbase:
                tags.append("nonbase")
            values = (
                "✓" if is_done else "✗",
                r["game_title"] or "",
                r["region"] or "-",
                r["version"] or "-",
                r["title_id"] or "-",
                r["build_id"] or "-",
                r["upload_date"] or "-",
                r["cheat_count"] if r["cheat_count"] is not None else "-",
                r["source"] or "-",
            )
            try:
                names = json.loads(r["cheat_names"] or "[]")
            except Exception:
                names = []
            cheats = {
                "names": names,
                "credits": r["credits"],
                "description": r["description"],
                "image": r["image"],
                "publisher": r["publisher"],
                "developer": r["developer"],
                "category": r["category"],
                "region": r["region"],
                "release_date": r["release_date"],
                "players": r["players"],
                "version_date": r["version_date"],
                "game_description": r["game_description"],
                "source": r["source"],
                "languages": r["languages"],
                "nsu_id": r["nsu_id"],
                "intro": r["intro"],
                "rating_content": r["rating_content"],
                "is_demo": r["is_demo"],
                "screenshots": r["screenshots"],
            }
            prepared.append((values, tuple(tags), r["slug"], cheats))
            if is_done:
                have += 1
            if not has_name:
                nameless += 1
            if is_nonbase:
                nonbase += 1
        shown = len(prepared)
        parts = [f"{shown} build(s) shown", f"{have} downloaded",
                 f"{shown - have} not downloaded"]
        if nameless:
            parts.append(f"{nameless} unnamed")
        if nonbase:
            parts.append(f"{nonbase} update/DLC ID(s)")
        if scan_kind == "live":
            parts.append("live scan")
        elif scan_kind == "fallback":
            parts.append("cache fallback")
        else:
            parts.append("cached")
        games_label = f"{total_games} game{'s' if total_games != 1 else ''}"
        self._log_queue.put(("table_rows", gen, prepared, games_label,
                             " · ".join(parts)))

    def _apply_refresh(self, gen, prepared, games_label, status):
        """Main thread: swap the table contents to the prepared rows, inserting
        in chunks so large datasets never block the event loop."""
        if gen != self._refresh_gen:
            return  # a newer refresh superseded this one
        with self._row_lock:
            children = self.tree.get_children()
            if children:
                self.tree.delete(*children)
            self._row_slugs.clear()
            self._row_cheats.clear()
        if games_label is not None:
            self.total_games_var.set(games_label)
        self.status_var.set(status)

        chunk = 800

        def insert_chunk(start=0):
            if gen != self._refresh_gen:
                return  # cancelled by a newer refresh mid-insert
            end = min(start + chunk, len(prepared))
            with self._row_lock:
                for values, tags, slug, cheats in prepared[start:end]:
                    item = self.tree.insert("", "end", values=values, tags=tags)
                    self._row_slugs[item] = slug
                    self._row_cheats[item] = cheats
            if end < len(prepared):
                self.root.after(1, lambda: insert_chunk(end))

        insert_chunk()

    # --------------------------------------------------------- context menu
    def _selected_pairs(self):
        """List of (title_id, build_id) for every selected row."""
        col_ids = [c[0] for c in COLUMNS]
        tid_idx = col_ids.index("title_id")
        bid_idx = col_ids.index("build_id")
        pairs = []
        for item in self.tree.selection():
            v = self.tree.item(item, "values")
            tid = v[tid_idx] if len(v) > tid_idx else None
            bid = v[bid_idx] if len(v) > bid_idx else None
            pairs.append((tid, bid))
        return pairs

    def _toggle_nonbase(self):
        """Toggle the Update/DLC IDs filter and refresh the table."""
        self.nonbase_only.set(not self.nonbase_only.get())
        self.refresh_table()

    def _selected_title_ids(self):
        """Distinct valid (16-hex) title ids across all selected rows."""
        out = []
        for tid, _bid in self._selected_pairs():
            if tid and len(tid) == 16 and tid not in out:
                out.append(tid)
        return out

    def _show_context_menu(self, event):
        if self._busy:
            return
        row = self.tree.identify_row(event.y)
        if not row:
            return
        # Keep an existing multi-selection if right-clicking inside it;
        # otherwise select just the clicked row.
        if row not in self.tree.selection():
            self.tree.selection_set(row)
        n = len(self.tree.selection())
        m, idx = self.context_menu, self._ctx_index
        m.entryconfig(idx["download"],
                      label=f"Download ({n})" if n > 1 else "Download this")
        m.entryconfig(idx["download_api"],
                      label=f"Download via API ({n})" if n > 1 else "Download via API")
        m.entryconfig(idx["download_browser"],
                      label=f"Download via browser ({n})" if n > 1
                      else "Download via browser (bypass API limit)")
        m.entryconfig(idx["check_file"],
                      label=f"Check Cheat Files ({n})" if n > 1 else "Check Cheat File")
        m.entryconfig(idx["export_zip"],
                      label=f"Export to ZIP ({n} selected)" if n > 1 else "Export to ZIP")
        self._ctx_info_menu.entryconfig(
            self._ctx_info_cover_index,
            label=f"Download cover (selected {n})" if n > 1 else "Download cover (selected)")
        m.entryconfig(idx["delete"],
                      label=f"Delete ({n})" if n > 1 else "Delete entry")
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _ctx_add_new_entry(self, _event=None):
        """Add a brand-new cheat entry manually via the context menu."""
        self.on_add_entry()

    def _ctx_download(self):
        tids = self._selected_title_ids()
        if not tids:
            messagebox.showwarning("Download", "No valid title id selected.")
            return
        self._start_download(tids)

    def _ctx_api_download(self):
        tids = self._selected_title_ids()
        if not tids:
            messagebox.showwarning("Download via API", "No valid title id selected.")
            return
        self._start_api_download(tids)

    def _ctx_download_covers(self):
        tids = self._selected_title_ids()
        if not tids:
            messagebox.showwarning("Download covers", "No valid title id selected.")
            return
        self._download_covers(tids)

    def _ctx_download_game_info(self):
        """Refresh metadata for the selected title(s) from the API / titledb."""
        tids = self._selected_title_ids()
        if not tids:
            messagebox.showwarning("Download game info", "No valid title id selected.")
            return
        if not messagebox.askyesno(
            "Download game info",
            f"Refresh game metadata (name, cover, build list, credits) for {len(tids)} selected game(s)?"):
            return
        self._save_settings()
        self._stop_event.clear()
        self._set_busy(True)
        cfg = {
            "token": self.api_token_var.get().strip() or None,
            "db_path": self.db_path.get(),
            "output": self.dl_output.get(),
            "title_ids": tids,
        }
        threading.Thread(target=self._download_game_info_worker, args=(cfg,), daemon=True).start()

    def _download_game_info_worker(self, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            db = GameDatabase(Path(cfg["db_path"]))
            try:
                api = CheatslipsAPI(token=cfg.get("token"))
                tids = cfg["title_ids"]
                tr = ProgressTracker("info")
                def prog(done, total):
                    tr.update(done, total)
                    self._log_queue.put(("progress", done, total,
                        f"Game info {done}/{total} ({tr.pct()}%) | {tr.rate_str('items')}"))
                refreshed = refresh_titles_from_api(
                    api, db, tids,
                    progress_cb=prog, should_stop=self._stop_event.is_set)
                if not self._stop_event.is_set():
                    # Fill missing names/covers from titledb for the selected titles.
                    fill_missing_names(
                        db, api=api, progress_cb=prog,
                        should_stop=self._stop_event.is_set,
                        cache_dir=str(DATA_DIR), with_regions=True)
                    recount_cheats_from_disk(db, Path(cfg["output"]), only_missing=False,
                                             should_stop=self._stop_event.is_set)
                print(f"Game info refreshed: {refreshed} game(s).")
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Download game info failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("download_done",))

    def _ctx_browser_download(self):
        """Download the selected games directly through the logged-in browser.

        Goes to each game's page, downloads every build as ZIP/HTML and sorts
        them into titles/{tid}/cheats/{bid}.txt — bypassing the API quota. If the
        quota blocks a reset is triggered automatically.
        """
        if self._busy:
            return
        if not _PW_OK:
            messagebox.showerror(
                "Download via browser",
                "Playwright is not installed.\n\nInstall it in a terminal:\n"
                "    pip install playwright\n    playwright install")
            return
        tids = self._selected_title_ids()
        if not tids:
            messagebox.showwarning("Download via browser", "No valid title id selected.")
            return
        if not messagebox.askyesno(
            "Download via browser",
            f"Open a browser and download {len(tids)} game(s) directly from "
            "cheatslips.com?\n\n"
            "You log in once (solve the reCAPTCHA if asked); the quota is reset "
            "automatically when needed."):
            return
        self._start_browser_download(tids)

    def on_download_browser(self):
        """Button: download via the logged-in browser (bypass the API limit).
        Uses the selected rows, or ALL missing builds if nothing is selected."""
        if self._busy:
            return
        if not _PW_OK:
            messagebox.showerror(
                "Download via browser",
                "Playwright is not installed.\n\nInstall it in a terminal:\n"
                "    pip install playwright\n    playwright install")
            return
        tids = self._selected_title_ids() or None
        if tids is None:
            if not messagebox.askyesno(
                "Download via browser",
                "No rows selected — download ALL still-missing builds directly via "
                "the browser?\n\nThis opens a browser (log in once / solve the "
                "reCAPTCHA), resets the quota automatically and can take a very long "
                "time for many builds. Stop anytime."):
                return
        else:
            if not messagebox.askyesno(
                "Download via browser",
                f"Open a browser and download {len(tids)} selected game(s) directly "
                "from cheatslips.com?\n\nYou log in once (solve the reCAPTCHA if "
                "asked); the quota is reset automatically when needed."):
                return
        self._start_browser_download(tids)

    def _start_browser_download(self, title_ids):
        self._save_settings()
        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set("Browser download...")
        cfg = {
            "email": self.email_var.get().strip() or None,
            "password": self.password_var.get() or None,
            "token": self.api_token_var.get().strip() or None,
            "output": self.dl_output.get(),
            "db_path": self.db_path.get(),
            "browser": self._browser_kind(),
            "title_ids": title_ids,   # None = all still-missing builds
        }
        threading.Thread(target=self._browser_download_worker, args=(cfg,), daemon=True).start()

    def _browser_download_worker(self, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            db = GameDatabase(Path(cfg["db_path"]))
            try:
                out = Path(cfg["output"])
                pairs = missing_build_pairs(db, out)
                if cfg.get("title_ids"):
                    wanted = {t.upper() for t in cfg["title_ids"]}
                    pairs = [p for p in pairs if p[0].upper() in wanted]
                if not pairs:
                    print("Nothing left to download — already complete.")
                    return
                # Use the API+browser auto-reset loop; the browser fallback handles
                # anything the API will not deliver.
                api = CheatslipsAPI(token=cfg["token"])
                if not api.token and cfg["email"] and cfg["password"]:
                    try:
                        api.get_token(cfg["email"], cfg["password"])
                    except Exception as exc:
                        print(f"(API token unavailable: {exc} — using browser only.)")
                saved = self._run_quota_reset_loop(api, db, out, pairs, cfg)
                print(f"Browser download finished - {saved} new file(s).")
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Browser download failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("download_done",))

    def on_reset_api_limit(self):
        if self._busy:
            return
        if not _PW_OK:
            messagebox.showerror(
                "Reset API Limit",
                "Playwright is not installed.\n\nInstall it in a terminal:\n"
                "    pip install playwright\n    playwright install")
            return
        if not messagebox.askyesno(
            "Reset API Limit",
            "Open a browser, log in (if not already cached), and click the "
            "'Reset my quota' button on cheatslips.com?\n\n"
            "Make sure your email/password are filled in."):
            return
        self._save_settings()
        self._stop_event.clear()
        self._set_busy(True)
        cfg = {
            "email": self.email_var.get().strip() or None,
            "password": self.password_var.get() or None,
            "browser": self._browser_kind(),
        }
        threading.Thread(target=self._reset_api_limit_worker, args=(cfg,), daemon=True).start()

    def _ctx_reset_api_limit(self, _event=None):
        self.on_reset_api_limit()

    def _ctx_check_cheat_file(self, _event=None):
        """Inspect the selected build(s)' cheat file on disk: does it exist,
        how many REAL cheats (with code lines) does it contain, and which?

        Also writes the counted number back to the DB (recount from disk), so
        the 'Cheats' column always matches the actual file afterwards.

        Runs in a worker thread: the disk lookups (incl. one rglob fallback
        for files outside the standard layout) must never block the UI —
        checking many not-downloaded rows used to freeze the whole program.
        """
        if self._busy:
            return
        pairs = self._selected_pairs()
        if not pairs:
            messagebox.showwarning("Check cheat file", "No row selected.")
            return
        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set(f"Checking {len(pairs)} cheat file(s)...")
        cfg = {"output": self.dl_output.get().strip() or DEFAULT_OUTPUT,
               "db_path": self.db_path.get()}
        threading.Thread(target=self._check_cheat_file_worker,
                         args=(pairs, cfg), daemon=True).start()

    def _check_cheat_file_worker(self, pairs, cfg):
        out = Path(cfg["output"])
        reports = []
        synced = 0
        # Fallback index (stem -> path) for files outside the standard layout.
        # Built AT MOST ONCE per call — the old code ran a full rglob PER ROW
        # without a file, which froze the GUI for minutes on multi-selections.
        file_index = None
        try:
            db = GameDatabase(Path(cfg["db_path"]))
            try:
                for i, (tid, bid) in enumerate(pairs, 1):
                    if self._stop_event.is_set():
                        break
                    if len(pairs) > 20:
                        self._log_queue.put(("progress", i, len(pairs),
                                             f"Checking cheat files {i}/{len(pairs)}"))
                    tid_u, bid_u = (tid or "").upper(), (bid or "").upper()
                    path = None
                    for p in (out / "titles" / tid_u / "cheats" / f"{bid_u}.txt",
                              out / "by_bid" / f"{bid_u}.txt"):
                        if p.exists():
                            path = p
                            break
                    if path is None:
                        if file_index is None:
                            file_index = {}
                            try:
                                for p in out.rglob("*.txt"):
                                    file_index.setdefault(p.stem.upper(), p)
                            except Exception:
                                pass
                        path = file_index.get(bid_u)
                    if path is None:
                        reports.append((tid, bid, None, [], "no file on disk"))
                        continue
                    try:
                        text = path.read_text(encoding="utf-8", errors="replace")
                    except Exception as exc:
                        reports.append((tid, bid, path, [], f"unreadable: {exc}"))
                        continue
                    names = parse_valid_cheats(text)
                    verdict = (f"{len(names)} valid cheat(s)" if names
                               else "file exists but has NO real code lines (stub)")
                    reports.append((tid, bid, path, names, verdict))
                    # Sync the DB count with what is really in the file — but only
                    # WRITE (and later refresh the table) when it actually changes,
                    # so checking already-correct rows never triggers a needless
                    # full refresh/disk-rescan.
                    cur = db._conn.execute(
                        "SELECT cheat_count FROM builds WHERE title_id = ? AND build_id = ?",
                        (tid, bid)).fetchone()
                    old_count = cur[0] if cur else None
                    if old_count != len(names):
                        if db.set_build_cheats(tid, bid, len(names), names):
                            synced += 1
            finally:
                db.close()
        except Exception as exc:
            self._log_queue.put(("error", f"Check cheat file failed:\n{exc}"))
        self._log_queue.put(("check_file_done", reports, synced, str(out)))

    def _finish_check_cheat_file(self, reports, synced, out):
        """Main thread: log + show the results of a cheat-file check."""
        self._set_busy(False)
        out = Path(out)
        lines = []
        for tid, bid, path, names, verdict in reports:
            try:
                loc = str(path.relative_to(out)) if path else "-"
            except Exception:
                loc = str(path) if path else "-"
            print(f"Check cheat file {tid}/{bid}: {verdict} ({loc})")
            lines.append(f"{tid}/{bid}\n  {verdict}\n  file: {loc}")
        if not reports:
            self.status_var.set("Check cheat file: nothing checked.")
            return
        n = len(reports)
        self.status_var.set(f"Checked {n} cheat file(s)"
                            + (f" — {synced} count(s) corrected." if synced else "."))
        # Refresh FIRST (only when something changed), THEN show the modal — so
        # the table is already up to date when the dialog blocks the loop.
        if synced:
            self.refresh_table()
        if n == 1:
            tid, bid, path, names, verdict = reports[0]
            detail = f"{tid} / {bid}\n\nResult: {verdict}\nFile: {path if path else '— not downloaded —'}"
            if names:
                shown = "\n".join(f"  • {nm}" for nm in names[:20])
                more = f"\n  … and {len(names) - 20} more" if len(names) > 20 else ""
                detail += f"\n\nCheats found:\n{shown}{more}"
            else:
                detail += ("\n\nNo usable cheats: the file contains no line with "
                           "real cheat codes.\nSuch stub files come from aggregated "
                           "databases (names/ads only)\nand correctly count as "
                           "'not downloaded' / 0 cheats.")
            body = detail
        else:
            body = (f"Checked {n} build(s):\n\n" + "\n\n".join(lines[:12])
                    + ("\n\n…" if len(lines) > 12 else ""))
        # Show the result dialog on top of the main window. Passing parent and
        # forcing the window forward avoids the dialog opening BEHIND the app
        # (a Tk/Windows quirk right after a context-menu grab), which makes the
        # app look frozen because it is modal.
        try:
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass
        self.root.after(10, lambda: messagebox.showinfo(
            "Check cheat file", body, parent=self.root))

    # ---------------------------------------------------- export to SD card
    def on_export_sd(self):
        if self._busy:
            return
        selected = self._selected_title_ids()
        dlg = ExportSDDialog(self.root, self.sd_export_root, self.sd_export_mode,
                             len(selected), detect_sd_roots, looks_like_sd_root)
        self.root.wait_window(dlg.top)
        if not dlg.result:
            return
        r = dlg.result
        self._save_settings()
        mode_label = {"atmosphere": "Atmosphère", "breeze": "Breeze",
                      "edizon": "EdiZon SE"}.get(r["mode"], r["mode"])
        scope_tids = selected if r["scope"] == "selected" else None
        scope_txt = (f"{len(selected)} selected game(s)" if scope_tids
                     else "ALL downloaded cheats")
        if not messagebox.askyesno(
            "Export to SD",
            f"Export {scope_txt} to:\n{r['sd_root']}\n\n"
            f"Target: {mode_label}\n\n"
            "Only files with real cheats are copied; existing SD cheats are merged. "
            "Proceed?"):
            return
        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set(f"Exporting cheats to SD ({mode_label})...")
        cfg = {"db_path": self.db_path.get(), "output": self.dl_output.get(),
               "sd_root": r["sd_root"], "mode": r["mode"], "title_ids": scope_tids}
        threading.Thread(target=self._export_sd_worker, args=(cfg,), daemon=True).start()

    def _export_sd_worker(self, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        stats = None
        try:
            db = GameDatabase(Path(cfg["db_path"]))
            try:
                tracker = ProgressTracker("sd-export")
                def prog(done, total):
                    tracker.update(done, total)
                    self._log_queue.put(("progress", done, total,
                        f"Exporting to SD {done}/{total} ({tracker.pct()}%) | "
                        f"{tracker.rate_str('items')} | ~{tracker.eta_str()} remaining"))
                stats = export_cheats_to_sd(
                    db, Path(cfg["output"]), cfg["sd_root"], mode=cfg["mode"],
                    title_ids=cfg["title_ids"], progress_cb=prog,
                    should_stop=self._stop_event.is_set)
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Export to SD failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("sd_export_done", stats, cfg.get("mode")))

    def _finish_sd_export(self, stats, mode):
        self._set_busy(False)
        if not stats:
            self.status_var.set("SD export failed — see log.")
            return
        mode_label = {"atmosphere": "Atmosphère", "breeze": "Breeze",
                      "edizon": "EdiZon SE"}.get(mode, mode)
        self.status_var.set(
            f"SD export ({mode_label}): {stats['exported']} file(s) for "
            f"{stats['games']} game(s).")
        try:
            self.root.lift(); self.root.focus_force()
        except Exception:
            pass
        self.root.after(10, lambda: messagebox.showinfo(
            "Export to SD",
            f"Export finished ({mode_label}):\n\n"
            f"  • {stats['exported']} cheat file(s) for {stats['games']} game(s)\n"
            f"  • {stats['skipped_stub']} empty/stub file(s) skipped\n"
            f"  • {stats['missing']} build(s) not downloaded (nothing to copy)\n"
            f"  • {stats['errors']} error(s)\n\n"
            "You can now safely eject the card and start your games.",
            parent=self.root))

    # ------------------------------------------------------- export to ZIP
    def _ctx_export_zip(self, _event=None):
        """Context menu: export the SELECTED rows into a ZIP (SD layout)."""
        self.on_export_zip(self._selected_title_ids() or None)

    def on_export_zip(self, title_ids=None):
        """Export downloaded cheats into a ZIP with the SD-card layout.

        Called with ``title_ids`` from the context menu (selected rows) — the
        dialog then defaults to the 'selected' scope; the toolbar button passes
        None (defaults to all, but 'selected' is still available).
        """
        if self._busy:
            return
        selected = self._selected_title_ids()
        # Default file name is always dated with today's date, e.g.
        # "switch-cheats-05072026.zip". Keep the last-used folder (from a
        # remembered path) but refresh the name to the current date each time.
        prev = self.export_zip_path.get().strip()
        base_dir = str(Path(prev).parent) if prev else self.dl_output.get()
        self.export_zip_path.set(str(Path(base_dir) / _default_zip_name()))
        dlg = ExportZipDialog(self.root, self.export_zip_path, self.sd_export_mode,
                              len(selected),
                              default_scope="selected" if title_ids else "all")
        self.root.wait_window(dlg.top)
        if not dlg.result:
            return
        r = dlg.result
        self._save_settings()
        mode_label = {"atmosphere": "Atmosphère", "breeze": "Breeze",
                      "edizon": "EdiZon SE"}.get(r["mode"], r["mode"])
        scope_tids = selected if r["scope"] == "selected" else None
        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set(f"Exporting cheats to ZIP ({mode_label})...")
        cfg = {"db_path": self.db_path.get(), "output": self.dl_output.get(),
               "zip_path": r["zip_path"], "mode": r["mode"], "title_ids": scope_tids}
        threading.Thread(target=self._export_zip_worker, args=(cfg,), daemon=True).start()

    def _export_zip_worker(self, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        stats = None
        try:
            db = GameDatabase(Path(cfg["db_path"]))
            try:
                tracker = ProgressTracker("zip-export")
                def prog(done, total):
                    tracker.update(done, total)
                    self._log_queue.put(("progress", done, total,
                        f"Exporting to ZIP {done}/{total} ({tracker.pct()}%) | "
                        f"{tracker.rate_str('items')} | ~{tracker.eta_str()} remaining"))
                stats = export_cheats_to_zip(
                    db, Path(cfg["output"]), cfg["zip_path"], mode=cfg["mode"],
                    title_ids=cfg["title_ids"], progress_cb=prog,
                    should_stop=self._stop_event.is_set)
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Export to ZIP failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("zip_export_done", stats, cfg.get("mode"), cfg.get("zip_path")))

    def _finish_zip_export(self, stats, mode, zip_path):
        self._set_busy(False)
        if not stats:
            self.status_var.set("ZIP export failed — see log.")
            return
        mode_label = {"atmosphere": "Atmosphère", "breeze": "Breeze",
                      "edizon": "EdiZon SE"}.get(mode, mode)
        if stats["exported"] == 0:
            self.status_var.set("ZIP export: nothing to export (no downloaded cheats).")
            self.root.after(10, lambda: messagebox.showinfo(
                "Export to ZIP",
                "Nothing was exported — none of the selected builds have a "
                "downloaded cheat file with real codes yet.", parent=self.root))
            return
        self.status_var.set(
            f"ZIP export ({mode_label}): {stats['exported']} file(s) for "
            f"{stats['games']} game(s) → {zip_path}")
        try:
            self.root.lift(); self.root.focus_force()
        except Exception:
            pass
        self.root.after(10, lambda: messagebox.showinfo(
            "Export to ZIP",
            f"ZIP created ({mode_label}):\n{zip_path}\n\n"
            f"  • {stats['exported']} cheat file(s) for {stats['games']} game(s)\n"
            f"  • {stats['skipped_stub']} empty/stub file(s) skipped\n"
            f"  • {stats['missing']} build(s) not downloaded (nothing to copy)\n"
            f"  • {stats['errors']} error(s)\n\n"
            "Unzip the archive onto your SD-card root to install the cheats.",
            parent=self.root))

    def _finish_import_db(self, summary):
        self._set_busy(False)
        self.refresh_table(force_scan=True)
        if not summary:
            self.status_var.set("Import database failed — see log.")
            return
        if summary["mode"] == "replace":
            self.status_var.set(
                f"Database replaced — {summary['after']} build(s).")
            msg = (f"Database replaced with the imported one.\n\n"
                   f"  • {summary['after']} build(s) now in the database\n")
            if summary.get("backup"):
                msg += f"\nA backup of the previous database was saved to:\n{summary['backup']}"
        else:
            self.status_var.set(
                f"Database merged — {summary['added']} added, "
                f"{summary['updated']} updated ({summary['after']} total).")
            msg = (f"Imported {summary['total_imported']} build(s):\n\n"
                   f"  • {summary['added']} new build(s) added\n"
                   f"  • {summary['updated']} existing build(s) updated\n"
                   f"  • {summary['after']} build(s) now in the database\n\n"
                   "Nothing was removed; existing entries kept their data.")
        try:
            self.root.lift(); self.root.focus_force()
        except Exception:
            pass
        self.root.after(10, lambda: messagebox.showinfo(
            "Import database", msg, parent=self.root))

    # ------------------------------------------ get everything from DevCatSKZ
    def on_devcat_cheats(self):
        self._start_devcat(
            ("cheats",), "Download cheats from DevCatSKZ",
            "Download the maintainer's ready-made cheats archive and import it?\n\n"
            "You get every cheat file without scraping cheatslips yourself. Your "
            "existing cheats are kept (merged).")

    def on_devcat_db(self):
        self._start_devcat(
            ("db",), "Download DevCatSKZ database",
            "Download the maintainer's complete database and merge it into yours?\n\n"
            "You get all names, regions, versions, descriptions and cover URLs. "
            "Nothing is removed; your own entries are kept and enriched.")

    def on_devcat_complete(self):
        self._start_devcat(
            ("db", "cheats"), "Download complete from DevCatSKZ",
            "Download the maintainer's complete database AND cheats archive?\n\n"
            "This is the fastest way to get everything — the full GUI database plus "
            "every cheat file. Nothing is removed.")

    def _start_devcat(self, parts, title, message):
        if self._busy:
            return
        if not messagebox.askyesno(title, message):
            return
        self._stop_event.clear()
        self._save_settings()
        self._set_busy(True)
        self.status_var.set("Downloading from DevCatSKZ...")
        cfg = {"db_path": self.db_path.get(), "output": self.dl_output.get()}
        threading.Thread(target=self._devcat_worker, args=(parts, cfg), daemon=True).start()

    def _devcat_worker(self, parts, cfg):
        import tempfile

        def prog(label):
            def cb(done, total):
                kb = done // 1024
                pct = f" ({int(done * 100 / total)}%)" if total else ""
                self._log_queue.put(("progress", done, max(total, 1),
                                     f"{label}: {kb:,} KB{pct}"))
            return cb

        db_summary = cheats_summary = None
        try:
            # Database first so the rich metadata is in place, then the files.
            if "db" in parts:
                self._log_queue.put(("status", "Downloading database from DevCatSKZ..."))
                tmp = Path(tempfile.gettempdir()) / "devcat_download.db"
                download_file(devcat_asset_url(DEVCAT_DB_ASSET), tmp,
                              progress_cb=prog("Database"),
                              should_stop=self._stop_event.is_set)
                self._log_queue.put(("status", "Importing database..."))
                db_summary = import_database(cfg["db_path"], str(tmp), mode="merge")
                try:
                    tmp.unlink()
                except Exception:
                    pass
            if "cheats" in parts:
                self._log_queue.put(("status", "Downloading cheats from DevCatSKZ..."))
                tmpz = Path(tempfile.gettempdir()) / "devcat_download.zip"
                download_file(devcat_asset_url(DEVCAT_CHEATS_ASSET), tmpz,
                              progress_cb=prog("Cheats"),
                              should_stop=self._stop_event.is_set)
                self._log_queue.put(("status", "Importing cheats..."))
                db = GameDatabase(Path(cfg["db_path"]))
                try:
                    written, games = import_cheats_from_zip(
                        cfg["output"], db, tmpz,
                        progress_cb=lambda d, t: self._log_queue.put(
                            ("progress", d, max(t, 1), f"Importing cheats {d}/{t}")),
                        should_stop=self._stop_event.is_set)
                    cheats_summary = (written, games)
                finally:
                    db.close()
                try:
                    tmpz.unlink()
                except Exception:
                    pass
            self._log_queue.put(("devcat_done", db_summary, cheats_summary))
        except Exception as exc:
            self._log_queue.put(("error", f"Download from DevCatSKZ failed:\n{exc}"))
            self._log_queue.put(("download_done",))

    def _finish_devcat(self, db_summary, cheats_summary):
        self._set_busy(False)
        self._update_downloaded_cache_incremental()
        self.refresh_table(force_scan=True)
        # Getting the data via the DevCat buttons counts as "up to date": move the
        # baselines forward so the updater only reports genuinely newer re-uploads.
        self._advance_data_baseline(cheats=bool(cheats_summary), db=bool(db_summary))
        parts = []
        if db_summary:
            parts.append(f"Database: {db_summary['added']} added, "
                         f"{db_summary['updated']} updated ({db_summary['after']} total)")
        if cheats_summary:
            parts.append(f"Cheats: {cheats_summary[0]} file(s) for "
                         f"{cheats_summary[1]} game(s)")
        self.status_var.set("DevCatSKZ download done — " + " · ".join(parts))
        # Covers are fetched only when the user opted in via the card checkbox
        # (off by default). No prompt — the checkbox is the choice.
        if self.devcat_covers.get():
            self.root.after(10, lambda: self._download_covers(None))

    def _advance_data_baseline(self, cheats=False, db=False, when=None):
        """Mark the cheats/database packages as current as of *when* (now)."""
        when = when if when is not None else time.time()
        if cheats:
            self._update_state["data_cheats_baseline"] = when
        if db:
            self._update_state["data_db_baseline"] = when
        if cheats or db:
            self._save_update_state(self._update_state)

    # ============================================================= UPDATES
    def on_check_updates(self, startup: bool = False):
        """Check GitHub for a newer program build and/or data packages.

        Runs in a background thread (never busy-managed, so it can run any time).
        When *startup* is True the result only pops a dialog if something is new;
        a manual click always reports the outcome (including "up to date").
        """
        # A manual click while the checker is already running is a no-op.
        if getattr(self, "_update_checking", False):
            return
        self._update_checking = True
        if not startup:
            self.update_status_lbl.config(text="checking…",
                                          foreground=theme()["checking"])
        threading.Thread(target=self._check_updates_worker,
                         args=(startup,), daemon=True).start()

    def _check_updates_worker(self, startup: bool):
        try:
            info = self._compute_updates()
            self._log_queue.put(("update_result", info, startup))
        except Exception as exc:
            self._log_queue.put(("update_error", str(exc), startup))

    def _compute_updates(self) -> dict:
        """Query the repo and decide what (if anything) is newer than baseline."""
        st = self._update_state
        info = {"error": None, "program": None, "cheats": None, "db": None,
                "release": None}

        # --- Program build (the /releases/latest release) ---
        rel = fetch_github_release(tag=None)
        info["release"] = rel
        newer_version = version_is_newer(rel["version"], APP_VERSION)
        rebuilt = rel["newest_epoch"] > float(st.get("program_baseline", 0)) + 1
        if newer_version or rebuilt:
            setup = find_release_asset(rel, PROGRAM_SETUP_ASSET)
            portable = find_release_asset(rel, PROGRAM_PORTABLE_ASSET)
            info["program"] = {
                "version": rel["version"],
                "newer_version": newer_version,
                "rebuilt": rebuilt,
                "newest_epoch": rel["newest_epoch"],
                "setup": setup,
                "portable": portable,
                "html_url": rel["html_url"],
                "notes": rel["body"],
            }

        # --- Data packages (the 'data' release: cheats zip + database.db) ---
        try:
            data_rel = fetch_github_release(tag=DEVCAT_DATA_TAG)
            cheats_a = find_release_asset(data_rel, DEVCAT_CHEATS_ASSET)
            db_a = find_release_asset(data_rel, DEVCAT_DB_ASSET)
            if cheats_a and cheats_a["epoch"] > float(st.get("data_cheats_baseline", 0)) + 1:
                info["cheats"] = cheats_a
            if db_a and db_a["epoch"] > float(st.get("data_db_baseline", 0)) + 1:
                info["db"] = db_a
        except Exception:
            # A missing/absent data release must not fail the program check.
            pass
        return info

    def _handle_update_result(self, info: dict, startup: bool):
        self._update_checking = False
        prog = info.get("program")
        has_data = bool(info.get("cheats") or info.get("db"))
        t = theme()
        if prog and info["cheats"] and info["db"]:
            label, colour = "update + data available", t["warn"]
        elif prog:
            label, colour = f"update available ({prog['version']})", t["warn"]
        elif has_data:
            label, colour = "new data available", t["warn"]
        else:
            label, colour = f"v{APP_VERSION} — up to date", t["ok"]
        self.update_status_lbl.config(text=label, foreground=colour)
        # Startup checks stay quiet unless something is actually new.
        if startup and not (prog or has_data):
            return
        self._show_update_dialog(info)

    def _handle_update_error(self, msg: str, startup: bool):
        self._update_checking = False
        self.update_status_lbl.config(text="check failed",
                                      foreground=theme()["fg_muted"])
        self._append_log(f"Update check failed: {msg}")
        if not startup:
            messagebox.showwarning(
                "Check Updates",
                "Could not check for updates:\n\n" + msg +
                "\n\nCheck your internet connection and try again.")

    def _show_update_dialog(self, info: dict):
        prog = info.get("program")
        cheats = info.get("cheats")
        db = info.get("db")
        if not (prog or cheats or db):
            messagebox.showinfo(
                "Check Updates",
                f"You are up to date.\n\nInstalled version: v{APP_VERSION}\n"
                "Program, cheats and database are all current.")
            return
        UpdateDialog(self.root, self, info)

    # ---- program self-update -------------------------------------------
    def start_program_update(self, info: dict):
        """Kick off downloading + installing a newer program build."""
        if self._busy:
            messagebox.showinfo("Update", "Please wait for the current task to "
                                          "finish, then try again.")
            return
        prog = info.get("program") or {}
        if not getattr(sys, "frozen", False):
            # From source there is nothing to self-install — point at the page.
            if prog.get("html_url"):
                webbrowser.open(prog["html_url"])
            messagebox.showinfo(
                "Update",
                "You are running from source. Pull the latest code from GitHub "
                "(git pull) — the release page has been opened in your browser.")
            return
        setup = prog.get("setup")
        if not setup or not setup.get("url"):
            if prog.get("html_url"):
                webbrowser.open(prog["html_url"])
            messagebox.showinfo(
                "Update",
                "No installer asset was found in the latest release. The release "
                "page has been opened so you can update manually.")
            return
        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set("Downloading update…")
        threading.Thread(target=self._program_update_worker,
                         args=(prog,), daemon=True).start()

    def _program_update_worker(self, prog: dict):
        import tempfile
        setup = prog["setup"]
        dest = Path(tempfile.gettempdir()) / PROGRAM_SETUP_ASSET

        def cb(done, total):
            kb = done // 1024
            pct = f" ({int(done * 100 / total)}%)" if total else ""
            self._log_queue.put(("progress", done, max(total, 1),
                                 f"Downloading update: {kb:,} KB{pct}"))
        try:
            self._log_queue.put(("status", "Downloading the update installer…"))
            download_file(setup["url"], dest, progress_cb=cb,
                          should_stop=self._stop_event.is_set)
            self._log_queue.put(("program_update_ready", str(dest), prog))
        except Exception as exc:
            self._log_queue.put(("error", f"Downloading the update failed:\n{exc}"))
            self._log_queue.put(("download_done",))

    def _launch_installer_and_quit(self, setup_path: str, prog: dict):
        """Run the downloaded installer (elevated, in place) and exit the app.

        The installer updates the files this .exe is running from, so we must
        exit right after launching it to release the file locks. Runtime data
        lives in the data dir and is never touched by the installer.
        """
        app_dir = str(Path(sys.executable).resolve().parent)
        # Silent, in-place update into the current folder. /CLOSEAPPLICATIONS lets
        # Setup free any file still locked by a lingering process; the installer's
        # postinstall [Run] entry relaunches the app once (de-elevated).
        args = (f'/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS '
                f'/DIR="{app_dir}"')
        launched = False
        try:
            import ctypes
            # ShellExecute respects the installer's admin manifest and shows the
            # UAC prompt (subprocess/CreateProcess would fail with error 740).
            rc = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", setup_path, args, None, 1)
            launched = int(rc) > 32
        except Exception as exc:
            self._append_log(f"Could not launch the installer: {exc}")
            launched = False
        if not launched:
            self._set_busy(False)
            messagebox.showwarning(
                "Update",
                "The update could not be started (installer launch was declined "
                "or blocked). Nothing has changed — you can try again or update "
                "manually from the GitHub release page.")
            return
        # The installer is now running. Advance the baseline so a same-version
        # re-upload is not reported again after the update completes, then quit
        # so the files this .exe runs from are unlocked for replacement.
        self._update_state["program_baseline"] = max(
            time.time(), float(prog.get("newest_epoch", 0)))
        self._save_update_state(self._update_state)
        self._save_settings()
        try:
            if self._log_writer and hasattr(self._log_writer, "close"):
                self._log_writer.close()
        except Exception:
            pass
        os._exit(0)

    # ---- data (cheats + database) update -------------------------------
    def start_data_update(self, info: dict):
        """Download + import whichever data packages are newer than baseline."""
        if self._busy:
            return
        parts = []
        if info.get("db"):
            parts.append("db")
        if info.get("cheats"):
            parts.append("cheats")
        if not parts:
            return
        self._stop_event.clear()
        self._save_settings()
        self._set_busy(True)
        self.status_var.set("Downloading data update from DevCatSKZ…")
        cfg = {"db_path": self.db_path.get(), "output": self.dl_output.get()}
        # Reuse the proven DevCat import worker; _finish_devcat advances the
        # data baselines for whichever parts came down.
        threading.Thread(target=self._devcat_worker,
                         args=(tuple(parts), cfg), daemon=True).start()

    # -------------------------------------------------------- online check

    # -------------------------------------------------------- online check
    def on_check_online(self):
        """Check whether cheatslips.com is reachable, in the background.

        Deliberately not busy-managed: the check can run any time, even while
        a scrape/download is in progress. The result colours the indicator.
        """
        self.online_status_lbl.config(text="● checking...", foreground=theme()["checking"])
        threading.Thread(target=self._check_online_worker, daemon=True).start()

    def _check_online_worker(self):
        ok = check_cheatslips_online()
        self._log_queue.put(("online_status", ok))

    # ------------------------------------------------------- browser login
    def on_browser_login(self):
        """One-time cheatslips login in the embedded browser.

        Opens the chosen browser with the persistent profile, pre-fills the
        credentials from the GUI and lets the user finish the login (reCAPTCHA).
        The session cookies are then stored in the profile + storage state, so
        every future browser download / quota reset is logged in automatically.
        """
        if self._busy:
            return
        if not _PW_OK:
            messagebox.showerror(
                "Browser Login",
                "Playwright is not installed. Install it with:\n\n"
                "    pip install playwright\n    playwright install")
            return
        if not (self.email_var.get().strip() and self.password_var.get()):
            if not messagebox.askyesno(
                "Browser Login",
                "No email/password entered — the login form will open empty and "
                "you type the credentials in the browser yourself.\n\n"
                "Tip: enter email + password in the GUI first, then only the "
                "reCAPTCHA is left to solve.\n\nOpen the browser anyway?",
            ):
                return
        self._save_settings()
        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set("Opening browser for cheatslips login...")
        cfg = {
            "email": self.email_var.get().strip() or None,
            "password": self.password_var.get() or None,
            "browser": self._browser_kind(),
        }
        threading.Thread(target=self._browser_login_worker, args=(cfg,), daemon=True).start()

    def _browser_login_worker(self, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            print("Opening the browser for a one-time cheatslips login...")
            print("If the login form appears: credentials are pre-filled from "
                  "the GUI (when entered) — solve the reCAPTCHA and click Login.")
            session = _pw_scrape.BrowserSession(
                email=cfg.get("email"),
                password=cfg.get("password"),
                log=print,
                headless=False,
                browser=cfg.get("browser", "builtin"),
                should_stop=self._stop_event.is_set,
            )
            try:
                session.start()
                if session.ensure_login():
                    print("✓ Logged in — session cookies saved to the persistent "
                          "profile.")
                    print("Future browser downloads / quota resets will log in "
                          "automatically; you will not be asked again.")
                    self._log_queue.put(("status", "cheatslips login saved — "
                                         "browser downloads are now automatic."))
                else:
                    print("Login was NOT completed — no cookies saved. "
                          "Click 'Browser Login' to try again.")
            finally:
                # close() persists cookies + localStorage for the next session.
                session.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Browser login failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("download_done",))

    def _ctx_open_link(self, _event=None):
        """Open the cheatslips.com build page for the selected row(s) in the
        default browser."""
        pairs = self._selected_pairs()
        if not pairs:
            messagebox.showwarning("Open Link", "No row selected.")
            return
        db = GameDatabase(Path(self.db_path.get()))
        try:
            lookup = {(t.upper(), b.upper()): (slug, sid)
                      for t, b, slug, sid in db.builds_for_download()}
            opened = 0
            for tid, bid in pairs:
                slug, sid = lookup.get((tid.upper(), bid.upper()), (None, None))
                if not slug:
                    print(f"Open Link: no slug stored for {tid}/{bid}")
                    continue
                url = f"https://www.cheatslips.com/game/{slug}/{sid}" if sid else f"https://www.cheatslips.com/game/{slug}"
                try:
                    webbrowser.open(url)
                    opened += 1
                except Exception as exc:
                    print(f"Open Link: could not open {url}: {exc}")
            if opened:
                self.status_var.set(f"Opened {opened} link(s) in browser.")
        finally:
            db.close()

    def _find_cheat_file(self, out: Path, tid: str, bid: str):
        """Locate the .txt cheat file for a build, both layouts + rglob fallback."""
        tid = (tid or "").upper()
        bid = (bid or "").upper()
        for p in (out / "titles" / tid / "cheats" / f"{bid}.txt",
                  out / "by_bid" / f"{bid}.txt"):
            if p.exists():
                return p
        try:
            for p in out.rglob("*.txt"):
                if p.stem.upper() == bid:
                    return p
        except Exception:
            pass
        return None

    def _ctx_open_in_explorer(self, _event=None):
        """Reveal the selected build's cheat .txt in the system file explorer.

        Opens the file selected in Explorer (Windows). If the file isn't on disk
        yet, falls back to opening the title's folder so the user still lands in
        the right place.
        """
        pairs = self._selected_pairs()
        if not pairs:
            messagebox.showwarning("Open in Explorer", "No row selected.")
            return
        out = Path(self.dl_output.get().strip() or DEFAULT_OUTPUT)
        tid, bid = pairs[0]
        path = self._find_cheat_file(out, tid, bid)
        try:
            import os
            import subprocess
            if path is not None:
                if sys.platform.startswith("win"):
                    # /select, highlights the file inside its folder.
                    subprocess.Popen(["explorer", "/select,", str(path)])
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", "-R", str(path)])
                else:
                    subprocess.Popen(["xdg-open", str(path.parent)])
                self.status_var.set(f"Revealed {path.name} in Explorer.")
            else:
                # File not downloaded — open the title folder (or output root).
                folder = out / "titles" / (tid or "").upper()
                if not folder.exists():
                    folder = out
                folder.mkdir(parents=True, exist_ok=True)
                if hasattr(os, "startfile"):
                    os.startfile(str(folder))
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(folder)])
                else:
                    subprocess.Popen(["xdg-open", str(folder)])
                self.status_var.set(
                    f"No cheat file on disk for {tid}/{bid} — opened {folder}.")
        except Exception as exc:
            messagebox.showerror("Open in Explorer", f"Could not open:\n\n{exc}")

    def _reset_api_limit_worker(self, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            session = _pw_scrape.BrowserSession(
                email=cfg.get("email"),
                password=cfg.get("password"),
                log=print,
                headless=False,
                browser=cfg.get("browser", "builtin"),
                should_stop=self._stop_event.is_set,
            )
            try:
                session.start()
                if not session.ensure_login():
                    print("Login was not completed — reset aborted.")
                    return
                print("Resetting API quota via browser...")
                if session.reset_quota():
                    print("API quota reset successful.")
                else:
                    print("API quota reset failed — see browser/log for details.")
            finally:
                session.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Reset API Limit failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("download_done",))

    def on_download_covers(self):
        if self._busy:
            return
        if not messagebox.askyesno(
            "Download covers",
            "Download cover images for all entries in the database and save them to\n"
            f"{COVERS_DIR}?\n\n"
            "Already-saved covers are skipped. (Entries without a cover URL are ignored.)",
        ):
            return
        self._download_covers(None)

    def _download_covers(self, title_ids):
        if self._busy:
            return
        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set("Downloading covers...")
        cfg = {"db_path": self.db_path.get(), "title_ids": title_ids}
        threading.Thread(target=self._download_covers_worker, args=(cfg,), daemon=True).start()

    def _cover_rows(self, db, title_ids=None):
        """DB rows (title_id, image) that have a cover URL, optional id filter."""
        if title_ids:
            qmarks = ",".join("?" * len(title_ids))
            return db._conn.execute(
                "SELECT DISTINCT title_id, image FROM builds "
                "WHERE image IS NOT NULL AND image != '' "
                f"AND title_id IN ({qmarks})", title_ids,
            ).fetchall()
        return db._conn.execute(
            "SELECT DISTINCT title_id, image FROM builds "
            "WHERE image IS NOT NULL AND image != ''"
        ).fetchall()

    def _download_cover_rows(self, rows, should_stop, prefix="Covers"):
        """Download + save each (title_id, image) cover. Returns (saved, skipped, failed)."""
        import requests
        total = len(rows)
        tracker = ProgressTracker("covers")
        saved = skipped = failed = 0
        for i, r in enumerate(rows, 1):
            if should_stop():
                print("Stopped by user.")
                break
            tid, url = r[0], r[1]
            path = self._cover_cache_path(url, tid)
            if path.exists():
                skipped += 1
            else:
                try:
                    raw = requests.get(self._normalize_url(url), timeout=15).content
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
                    saved += 1
                except Exception as exc:
                    failed += 1
                    print(f"  ERROR {tid}: {exc}")
            tracker.update(i, total)
            self._log_queue.put(("progress", i, total,
                f"{prefix} {i}/{total} ({tracker.pct()}%) | {tracker.rate_str('items')}"))
        return saved, skipped, failed

    def _download_covers_worker(self, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            db = GameDatabase(Path(cfg["db_path"]))
            try:
                rows = self._cover_rows(db, cfg.get("title_ids"))
            finally:
                db.close()
            if not rows:
                print("No cover URLs found in the database. Run 'Fill Names, Region + Versions' first.")
                return
            print(f"Downloading covers for {len(rows)} game(s) -> {COVERS_DIR}")
            saved, skipped, failed = self._download_cover_rows(rows, self._stop_event.is_set)
            print(f"Covers done — {saved} downloaded, {skipped} already present, {failed} failed.")
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Download covers failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("download_done",))

    # ----------------------------------------------- scrape & download everything
    def on_scrape_download_everything(self):
        if self._busy:
            return
        if not messagebox.askyesno(
            "Scrape & Download Everything",
            "Build the COMPLETE database in one go:\n\n"
            "   1. Scrape all cheats from cheatslips.com\n"
            "   2. Import the GBATemp archive\n"
            "   3. Import the HamletDuFromage TitleDB archive\n"
            "   4. Import the HamletDuFromage TitleDB 60FPS/Res/GFX archive\n"
            "   5. Import the Sthetix TitleDB archive (daily aggregate)\n"
            "   6. Import the Breeze NXCheatCode database\n"
            "   7. Import the Chansey 60FPS/Res/GFX repo\n"
            "   8. Import the MyNXCheats repo\n"
            "   9. Import titledb cheats\n"
            "  10. Import ibnux/switch-cheat archive\n"
            "  11. Fill names, covers, region + versions\n"
            "  12. Download all cheat files (API, then browser when quota is hit)\n"
            "  13. Download all cover images\n\n"
            "For step 12, enable 'Download via browser when API is limited' so the\n"
            "browser fetches whatever the API can't (daily limit).\n\n"
            "This can take a long while and downloads a lot of data.\n"
            "You can press Stop at any time. Proceed?",
        ):
            return
        self._stop_event.clear()
        self._save_settings()
        self._set_busy(True)
        self.everything_btn.config(text="Working...")
        self.status_var.set("Scrape & Download Everything started...")
        cfg = {
            "db_path": self.db_path.get(),
            "output": self.dl_output.get(),
            "token": self.api_token_var.get().strip() or None,
            "email": self.email_var.get().strip() or None,
            "password": self.password_var.get() or None,
            "auto_reset": self.auto_reset_quota.get(),
            "browser": self._browser_kind(),
        }
        threading.Thread(target=self._everything_worker, args=(cfg,), daemon=True).start()

    def _everything_worker(self, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        stop = self._stop_event.is_set
        try:
            out = Path(cfg["output"])
            db = GameDatabase(Path(cfg["db_path"]))
            # One API/token shared by all phases.
            api = CheatslipsAPI(token=cfg.get("token"))
            if not api.token and cfg.get("email") and cfg.get("password"):
                try:
                    api.get_token(cfg["email"], cfg["password"])
                except Exception as _e:
                    print(f"Could not get API token ({_e}) — metadata only.")
                    api = CheatslipsAPI()
            have_token = bool(api.token) and api.token_works()
            # Every external archive source, imported in order after the scrape.
            # Adding a new source here is one line; step numbers adapt.
            archives = [
                ("GBATemp", lambda cb: download_gbatemp_archive(
                    out, db, api=None, progress_cb=cb, should_stop=stop)),
                ("HamletDuFromage TitleDB", lambda cb: download_hamlet_titledb_archive(
                    out, db, api=None, progress_cb=cb, should_stop=stop)),
                ("HamletDuFromage 60FPS/Res/GFX", lambda cb: download_hamlet_60fps_archive(
                    out, db, api=None, progress_cb=cb, should_stop=stop)),
                ("Sthetix TitleDB", lambda cb: download_sthetix_archive(
                    out, db, api=None, progress_cb=cb, should_stop=stop)),
                ("Breeze NXCheatCode", lambda cb: download_breeze_archive(
                    out, db, api=None, progress_cb=cb, should_stop=stop)),
                ("Chansey 60FPS/Res/GFX", lambda cb: download_chansey_archive(
                    out, db, api=None, progress_cb=cb, should_stop=stop)),
                ("MyNXCheats", lambda cb: download_mynx_archive(
                    out, db, api=None, progress_cb=cb, should_stop=stop)),
                ("titledb", lambda cb: download_titledb_cheats(
                    out, db, progress_cb=cb, should_stop=stop)),
                ("ibnux/switch-cheat", lambda cb: download_ibnux_archive(
                    out, db, api=None, progress_cb=cb, should_stop=stop)),
            ]
            total = 1 + len(archives) + 3  # scrape + archives + enrich/download/covers
            try:
                # ---- [1/N] cheatslips scrape (+ inline content if token) ----
                if not stop():
                    print(f"=== [1/{total}] Scraping cheatslips.com ===")
                    scraper = CheatslipsMetadataScraper(delay=0.3, max_concurrent=4)
                    downloaded = scan_downloaded_build_ids(out) if have_token else set()
                    saved_files = {"n": 0}
                    tr = ProgressTracker("scrape")

                    def game_cb(d, t):
                        tr.update(d, t)
                        self._log_queue.put(("progress", d, t,
                            f"[1/{total}] Scraping {d}/{t} ({tr.pct()}%) | {tr.rate_str('items')}"))

                    def on_game(info):
                        # Complete dataset: keep every build (incl. 0-cheat) so the
                        # GUI can classify them; never drop rows here.
                        enrich_info_with_api(info, api)
                        db.upsert_game(info, source="cheatslips")
                        if have_token:
                            self._save_inline_content(info, out, downloaded, saved_files, db=db)

                    # Use the /entry "latest cheats" feed: it already covers every
                    # game that has cheats (~1894), so scanning the full /games
                    # catalog (~29k games) would be ~15x slower for the same result.
                    scraper.scrape_all_streaming(on_game, entry_only=True,
                                                 game_cb=game_cb, should_stop=stop, skip_slugs=None)
                    print(f"Scrape done ({saved_files['n']} cheat file(s) saved inline)."
                          if have_token else "Scrape done (metadata only).")

                # ---- [2..N-3] external cheat archives ----
                for i, (label, fetch) in enumerate(archives, start=2):
                    if stop():
                        break
                    print(f"=== [{i}/{total}] {label} archive ===")
                    tr_a = ProgressTracker(label)

                    def ap(d, t, tr_a=tr_a, label=label, i=i):
                        tr_a.update(d, t)
                        self._log_queue.put(("progress", d, t,
                            f"[{i}/{total}] {label} {d}/{t} ({tr_a.pct()}%)"))
                    try:
                        w, ng = fetch(ap)
                        print(f"{label}: {w} file(s), {ng} game(s).")
                    except Exception as exc:
                        print(f"{label} step skipped: {exc}")

                # ---- [N-2] names + covers + region + versions + recount ----
                step = len(archives) + 2
                if not stop():
                    print(f"=== [{step}/{total}] Names, covers, region, versions ===")
                    trf = ProgressTracker("fill")
                    def fp(d, t):
                        trf.update(d, t)
                        self._log_queue.put(("progress", d, t, f"[{step}/{total}] Enrich {d}/{t} ({trf.pct()}%)"))
                    try:
                        fill_missing_names(db, api=api, progress_cb=fp, should_stop=stop,
                                           cache_dir=str(DATA_DIR), with_regions=True)
                        recount_cheats_from_disk(db, out, only_missing=False, should_stop=stop)
                        if not stop():
                            # Versions already came from the [1/N] cheatslips scrape, so
                            # only do the fast titledb-based pass here. Re-scraping
                            # cheatslips (fill_missing_versions) would be a slow duplicate.
                            fill_versions_from_titledb(db, should_stop=stop)
                    except Exception as exc:
                        print(f"Enrich step issue: {exc}")

                # ---- [N-1] download remaining cheat files ----
                step = len(archives) + 3
                if not stop() and have_token:
                    print(f"=== [{step}/{total}] Downloading remaining cheat files ===")
                    trd = ProgressTracker("download")
                    def dp(d, t):
                        trd.update(d, t)
                        self._log_queue.put(("progress", d, t, f"[{step}/{total}] Download {d}/{t} ({trd.pct()}%)"))
                    try:
                        saved = api_download_from_db(api, db, out, resume=True,
                                                     progress_cb=dp, should_stop=stop)
                        print(f"Downloaded {saved} new cheat file(s) via API.")
                        cleanup_invalid_cheat_entries(db, out, should_stop=stop)
                        # When the API hits its daily quota, fetch everything still
                        # missing through the logged-in browser (auto-reset loop) —
                        # this is the part that works while the API is quota-blocked.
                        if cfg.get("auto_reset") and not stop():
                            pairs = missing_build_pairs(db, out)
                            if pairs:
                                print(f"{len(pairs)} build(s) still missing after API — "
                                      f"downloading via browser...")
                                extra = self._run_quota_reset_loop(api, db, out, pairs, cfg)
                                print(f"Browser download added {extra} more file(s).")
                            else:
                                print("Nothing left to download — dataset complete.")
                        elif not cfg.get("auto_reset"):
                            print("(Browser download off — tick 'Download via browser when "
                                  "API is limited' to fetch quota-blocked builds.)")
                    except Exception as exc:
                        print(f"Download step issue: {exc}")
                elif not have_token:
                    print(f"=== [{step}/{total}] Skipped cheat-file download (no valid token) ===")

                # ---- [N/N] cover images ----
                step = len(archives) + 4
                if not stop():
                    print(f"=== [{step}/{total}] Downloading cover images ===")
                    rows = self._cover_rows(db)
                    if rows:
                        s, sk, f = self._download_cover_rows(rows, stop, prefix=f"[{step}/{total}] Covers")
                        print(f"Covers — {s} downloaded, {sk} already present, {f} failed.")
                    else:
                        print("No cover URLs to download.")

                if stop():
                    print("Stopped by user.")
                print(f"Everything done. Database holds {db.count()} build(s).")
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Scrape & Download Everything failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("everything_done",))

    def _ctx_delete(self):
        pairs = self._selected_pairs()
        if not pairs:
            return
        if not messagebox.askyesno(
            "Delete entries",
            f"Delete {len(pairs)} selected entr{'y' if len(pairs)==1 else 'ies'}?\n"
            "This also deletes the downloaded cheat file(s) on disk.",
        ):
            return
        out = Path(self.dl_output.get())
        files_removed = 0
        dirs_removed = 0
        for tid, bid in pairs:
            bid = bid.upper()
            tid = tid.upper()
            # Exact known paths
            for p in (out / "titles" / tid / "cheats" / f"{bid}.txt", out / "by_bid" / f"{bid}.txt"):
                if p.exists():
                    try:
                        p.unlink()
                        files_removed += 1
                    except Exception:
                        pass
            # Fallback: any .txt file with this build id anywhere under the output dir
            for p in out.rglob("*.txt"):
                if p.stem.upper() == bid:
                    try:
                        p.unlink()
                        files_removed += 1
                    except Exception:
                        pass
            # Remove empty parent directories (keep root output dir)
            for sub in (out / "titles" / tid / "cheats", out / "titles" / tid, out / "by_bid"):
                try:
                    if sub.exists() and not any(sub.iterdir()):
                        sub.rmdir()
                except Exception:
                    pass
            # If the title_id folder has no remaining cheat files, delete it entirely
            tid_dir = out / "titles" / tid
            if tid_dir.exists() and not any(tid_dir.rglob("*.txt")):
                try:
                    shutil.rmtree(tid_dir)
                    dirs_removed += 1
                except Exception:
                    pass
        try:
            db = GameDatabase(Path(self.db_path.get()))
            n = sum(db.delete_build(bid, tid) for tid, bid in pairs)
            db.close()
        except Exception as exc:
            messagebox.showerror("Delete entries", str(exc))
            return
        parts = [f"Deleted {n} entr{'y' if n == 1 else 'ies'}", f"{files_removed} file(s)"]
        if dirs_removed:
            parts.append(f"{dirs_removed} folder(s)")
        self.status_var.set(" · ".join(parts))
        self.refresh_table()

    def _ctx_edit_ids(self):
        pairs = self._selected_pairs()
        if len(pairs) != 1:
            messagebox.showinfo("Edit IDs", "Select exactly one entry to edit its IDs.")
            return
        old_tid, old_bid = pairs[0]
        new_tid = simpledialog.askstring("Edit Title ID", "Title ID (16 hex):",
                                         initialvalue=old_tid, parent=self.root)
        if new_tid is None:
            return
        new_bid = simpledialog.askstring("Edit Build ID", "Build ID (16 hex):",
                                         initialvalue=old_bid, parent=self.root)
        if new_bid is None:
            return
        new_tid = new_tid.strip().upper()
        new_bid = new_bid.strip().upper()
        import re as _re
        if not _re.fullmatch(r"[A-F0-9]{16}", new_tid) or not _re.fullmatch(r"[A-F0-9]{16}", new_bid):
            messagebox.showwarning("Edit IDs", "Both IDs must be exactly 16 hex characters.")
            return
        if (new_tid, new_bid) == (old_tid, old_bid):
            return  # nothing changed
        try:
            db = GameDatabase(Path(self.db_path.get()))
            ok = db.update_build_ids(old_bid, old_tid, new_bid, new_tid)
            db.close()
        except Exception as exc:
            messagebox.showerror("Edit IDs", str(exc))
            return
        if not ok:
            messagebox.showwarning("Edit IDs", "An entry with those IDs already exists.")
            return
        moved = self._move_cheat_file(old_tid, old_bid, new_tid, new_bid)
        self.status_var.set("Entry updated" + (" and file moved." if moved else "."))
        self.refresh_table()

    def _move_cheat_file(self, old_tid, old_bid, new_tid, new_bid) -> bool:
        """Move the cheat .txt on disk to match changed title/build ids.

        Handles both layouts: titles/{tid}/cheats/{bid}.txt and by_bid/{bid}.txt.
        Returns True if a file was moved. Empty old folders are cleaned up.
        """
        out = Path(self.dl_output.get())
        moved = False
        candidates = [
            (out / "titles" / (old_tid or "") / "cheats" / f"{old_bid}.txt",
             out / "titles" / (new_tid or "") / "cheats" / f"{new_bid}.txt"),
            (out / "by_bid" / f"{old_bid}.txt",
             out / "by_bid" / f"{new_bid}.txt"),
        ]
        for src, dst in candidates:
            if not src.exists() or src == dst:
                continue
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                src.replace(dst)
                moved = True
                # Clean up now-empty old cheats/ and title/ folders.
                for folder in (src.parent, src.parent.parent):
                    try:
                        if folder.is_dir() and not any(folder.iterdir()):
                            folder.rmdir()
                    except Exception:
                        pass
            except Exception as exc:
                print(f"  WARN: could not move {src} -> {dst}: {exc}")
        return moved

    def _ctx_edit_entry(self):
        pairs = self._selected_pairs()
        if len(pairs) != 1:
            messagebox.showinfo("Edit entry", "Select exactly one entry to edit.")
            return
        tid, bid = pairs[0]
        # Gather current values from DB + the cheat file on disk.
        row = None
        try:
            db = GameDatabase(Path(self.db_path.get()))
            info = db.get_game_info(tid)
            db.close()
            if info:
                for s in info["sources"]:
                    if (s["build_id"] or "").upper() == (bid or "").upper():
                        row = (info.get("title"), s)
                        break
        except Exception:
            row = None
        content = ""
        p = Path(self.dl_output.get()) / "titles" / tid / "cheats" / f"{bid}.txt"
        if p.exists():
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                content = ""
        initial = {
            "title_id": tid, "build_id": bid,
            "name": (row[0] if row else "") or "",
            "version": (row[1].get("version") if row else "") or "",
            "credits": (row[1].get("credits") if row else "") or "",
            "content": content,
        }
        dlg = AddEntryDialog(self.root, initial=initial)
        self.root.wait_window(dlg.top)
        r = dlg.result
        if not r:
            return
        names = parse_cheat_names_from_content(r["content"])
        try:
            db = GameDatabase(Path(self.db_path.get()))
            # If the IDs changed, remove the old entry + file.
            if (r["title_id"], r["build_id"]) != (tid, bid):
                db.delete_build(bid, tid)
                if p.exists():
                    try:
                        p.unlink()
                    except Exception:
                        pass
            save_dir = Path(self.dl_output.get()) / "titles" / r["title_id"] / "cheats"
            save_path = save_dir / f"{r['build_id']}.txt"
            save_cheat_merged(save_path, r["content"])
            db.upsert_game({
                "title_id": r["title_id"], "title": r["name"] or None, "slug": None,
                "image": None, "banner": None,
                "sources": [{
                    "build_id": r["build_id"], "title_id": r["title_id"], "source_id": None,
                    "version": r["version"] or None, "upload_date": None,
                    "cheat_count": len(names), "cheat_names": names,
                    "credits": r["credits"] or None, "description": None, "cheat_id": None,
                }],
            }, source="manual")
            db.close()
        except Exception as exc:
            messagebox.showerror("Edit entry", str(exc))
            return
        self.status_var.set(f"Saved {r['title_id']}/{r['build_id']} ({len(names)} cheat(s)).")
        self.refresh_table()

    def on_refresh(self):
        """Manual refresh: reconcile every build's cheat count with the actual
        .txt file on disk (background), then rescan downloaded state + redraw."""
        # During a running operation, just redraw — don't start a second worker.
        if self._busy:
            self.refresh_table(force_scan=True)
            return
        path = Path(self.db_path.get())
        if not path.exists():
            self.refresh_table(force_scan=True)
            return
        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set("Recounting cheats from disk...")
        cfg = {"db_path": self.db_path.get(), "output": self.dl_output.get()}
        threading.Thread(target=self._refresh_worker, args=(cfg,), daemon=True).start()

    def _refresh_worker(self, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            db = GameDatabase(Path(cfg["db_path"]))
            try:
                recount_cheats_from_disk(db, Path(cfg["output"]), only_missing=False,
                                         should_stop=self._stop_event.is_set)
            finally:
                db.close()
        except Exception as exc:
            print(f"Refresh recount failed: {exc}")
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("refresh_done",))

    def on_clear_db(self):
        if self._busy:
            return
        if not messagebox.askyesno(
            "Clear database & downloaded files",
            "Empty the database AND delete every downloaded file on disk?\n\n"
            "This removes:\n"
            "  - all cheat files (titles/ and by_bid/)\n"
            "  - all downloaded covers (coversdownload/)\n"
            "  - the packaged ZIP, meta/ folder and cache/skip files\n\n"
            "Region title databases (titledb_*.json) are kept.\n"
            "This CANNOT be undone.",
        ):
            return
        self._save_settings()
        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set("Clearing database and downloaded files...")
        cfg = {"output": self.dl_output.get(), "db_path": self.db_path.get()}
        threading.Thread(target=self._clear_db_worker, args=(cfg,), daemon=True).start()

    def _purge_disk_data(self, out: Path) -> int:
        """Delete all downloaded cheat files, covers, the ZIP and cache/skip files.

        Region title databases (titledb_*.json), settings.json and the database
        file itself are left untouched. Returns the number of top-level entries
        (folders + files) that were removed.
        """
        removed = 0
        targets = [
            out / "titles",
            out / "by_bid",
            out / "meta",
            out / "cheatsdownload.zip",
            out / ".downloaded_cache.json",
            out / "unavailable_builds.txt",
            out / "quota_skipped.txt",
            Path(COVERS_DIR),
        ]
        for t in targets:
            try:
                if t.is_dir():
                    shutil.rmtree(t)
                    removed += 1
                    print(f"Removed folder: {t}")
                elif t.exists():
                    t.unlink()
                    removed += 1
                    print(f"Removed file: {t.name}")
            except Exception as exc:
                print(f"Could not remove {t}: {exc}")
        return removed

    def _clear_db_worker(self, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            n = 0
            try:
                db = GameDatabase(Path(cfg["db_path"]))
                n = db.clear()
                db.close()
                print(f"Cleared {n} database entr{'y' if n == 1 else 'ies'}.")
            except Exception as exc:
                print(f"Could not clear database: {exc}")
                self._log_queue.put(("error", f"Clear database failed:\n{exc}"))

            removed = self._purge_disk_data(Path(cfg["output"]))
            print(f"Deleted {removed} item(s) from disk. Cleanup done.")
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Clear failed:\n{exc}"))
        finally:
            # Drop cached cover images so the preview pane reflects the wipe.
            self._img_refs.clear()
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("download_done",))

    def _browser_kind(self):
        """Canonical browser kind for the chosen entry: builtin/chrome/edge/firefox."""
        return _BROWSER_KINDS.get(self.browser_choice.get(), "builtin")

    def _secret_entry(self, parent, var, width):
        """A masked entry (•••) with a small show/hide toggle button.
        Returns (entry, button) — the caller packs them."""
        ent = ttk.Entry(parent, textvariable=var, show="•", width=width)
        state = {"shown": False}

        def toggle():
            state["shown"] = not state["shown"]
            ent.config(show="" if state["shown"] else "•")
            btn.config(text="hide" if state["shown"] else "show")

        btn = ttk.Button(parent, text="show", width=5, command=toggle)
        return ent, btn

    def _build_api(self, cfg):
        """Build a CheatslipsAPI from the token / email+password in cfg.
        Returns an unauthenticated client (names still resolve via titledb) if no
        credentials are available."""
        api = CheatslipsAPI(token=cfg.get("token"))
        if not api.token and cfg.get("email") and cfg.get("password"):
            try:
                api.get_token(cfg["email"], cfg["password"])
                print("Got API token for name fallback.")
            except Exception as exc:
                print(f"Could not get API token ({exc}) — names from titledb only.")
                api = CheatslipsAPI()
        return api

    def _postprocess_import(self, db, cfg):
        """Unified post-processing for the external-source imports
        (GBATemp / titledb / ibnux). Kept identical for all three:
          1) fill names + covers + region ONCE,
          2) fill versions from titledb ONLY (cheatslips version lookup is
             intentionally NOT used),
          3) recount cheat counts from the .txt files on disk.
        """
        stop = self._stop_event.is_set
        out = Path(cfg["output"])
        api = self._build_api(cfg)

        # 1) Names + covers + region tags (single pass; region reuses cached files).
        if not stop():
            print("=== Names, covers + region (titledb -> API -> switchbrew/tinfoil/GitHub) ===")
            tr = ProgressTracker("fill")
            def fprog(done, total):
                tr.update(done, total)
                self._log_queue.put(("progress", done, total,
                    f"Names/region {done}/{total} ({tr.pct()}%) | {tr.rate_str('items')}"))
            fill_missing_names(db, api=api, progress_cb=fprog, should_stop=stop,
                               cache_dir=str(DATA_DIR), with_regions=True)

        # 2) Versions from titledb ONLY — cheatslips version lookup is disabled by design.
        if not stop():
            print("=== Versions (titledb only — cheatslips lookup disabled) ===")
            def vprog(done, total):
                self._log_queue.put(("progress", done, total, f"titledb versions {done}/{total}"))
            n = fill_versions_from_titledb(db, progress_cb=vprog, should_stop=stop)
            print(f"Versions filled: {n} via titledb.")

        # 3) Recount cheat counts from the actual files on disk.
        if not stop():
            print("=== Recounting cheat counts from disk ===")
            def rprog(done, total):
                self._log_queue.put(("progress", done, total, f"Recounting {done}/{total}"))
            recount_cheats_from_disk(db, out, only_missing=False,
                                     progress_cb=rprog, should_stop=stop)

    # ------------------------------------------ external archive imports
    # All "External Cheat Sources" buttons share the exact same flow:
    # confirm -> download+extract archive -> DB import -> _postprocess_import.
    # _start_archive_import/_archive_import_worker implement it once; each
    # button only supplies its title, confirmation text and download function.
    def _start_archive_import(self, title, message, label, download_fn):
        """Generic handler for an archive-import button.

        ``download_fn(out_path, db, progress_cb, should_stop)`` must download +
        import the source and return (files_written, games).
        """
        if self._busy:
            return
        if not messagebox.askyesno(
            title,
            message + "\n\nAfterwards: names + covers + region, versions "
            "(titledb only) and a\ncheat-count recount from disk.",
        ):
            return
        self._save_settings()
        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set(f"Downloading {label}...")
        cfg = {
            "output": self.dl_output.get(),
            "db_path": self.db_path.get(),
            "token": self.api_token_var.get().strip() or None,
            "email": self.email_var.get().strip() or None,
            "password": self.password_var.get() or None,
        }
        threading.Thread(target=self._archive_import_worker,
                         args=(label, download_fn, cfg), daemon=True).start()

    def _archive_import_worker(self, label, download_fn, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            db = GameDatabase(Path(cfg["db_path"]))
            try:
                tracker = ProgressTracker(label)
                def prog(done, total):
                    tracker.update(done, total)
                    msg = (f"{label} {done}/{total} ({tracker.pct()}%) | "
                           f"{tracker.rate_str('items')} | ~{tracker.eta_str()} remaining")
                    self._log_queue.put(("progress", done, total, msg))

                # 1) Download + extract the archive and import it into the DB.
                written, ngames = download_fn(
                    Path(cfg["output"]), db, prog, self._stop_event.is_set)
                print(f"Imported {written} files, {ngames} games.")

                # Unified post-processing (names/covers/region + titledb versions + recount).
                self._postprocess_import(db, cfg)

                print(f"{label} import done. DB now holds {db.count()} builds.")
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"{label} import failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("download_done",))

    def on_gbatemp(self):
        self._start_archive_import(
            "Download GBAtemp Archive",
            "Download the latest GBAtemp/HamletDuFromage cheat archive,\n"
            "extract all cheat files and add them to the database?",
            "GBAtemp archive",
            lambda out, db, prog, stop: download_gbatemp_archive(
                out, db, api=None, progress_cb=prog, should_stop=stop))

    def on_hamlet_titledb(self):
        self._start_archive_import(
            "Download HamletDuFromage TitleDB",
            "Download HamletDuFromage's titles_complete.zip from the LATEST\n"
            "switch-cheats-db release (always the newest), extract all cheat\n"
            "files and add them to the database?",
            "HamletDuFromage TitleDB",
            lambda out, db, prog, stop: download_hamlet_titledb_archive(
                out, db, api=None, progress_cb=prog, should_stop=stop))

    def on_hamlet_60fps(self):
        self._start_archive_import(
            "Download HamletDuFromage TitleDB 60FPS/Res/GFX",
            "Download HamletDuFromage's titles_60fps-res-gfx.zip (60 FPS /\n"
            "resolution / GFX cheats) from the LATEST switch-cheats-db release\n"
            "(always the newest), extract all cheat files and add them to the\n"
            "database?",
            "HamletDuFromage 60FPS/Res/GFX",
            lambda out, db, prog, stop: download_hamlet_60fps_archive(
                out, db, api=None, progress_cb=prog, should_stop=stop))

    def on_sthetix(self):
        self._start_archive_import(
            "Download Sthetix TitleDB",
            "Download titles_complete.zip from the LATEST sthetix/nx-cheats-db\n"
            "release — a DAILY-updated aggregate of GBAtemp + graphics cheats +\n"
            "switch-cheats-db + cheatslips (~141k cheats) — and add all cheats\n"
            "to the database?",
            "Sthetix TitleDB",
            lambda out, db, prog, stop: download_sthetix_archive(
                out, db, api=None, progress_cb=prog, should_stop=stop))

    def on_breeze(self):
        self._start_archive_import(
            "Download Breeze NXCheatCode",
            "Download titles.zip (the Breeze/EdiZon-SE cheat database) from the\n"
            "LATEST tomvita/NXCheatCode release — GBAtemp community codes,\n"
            "partly different from cheatslips — and add all cheats to the\n"
            "database?",
            "Breeze NXCheatCode",
            lambda out, db, prog, stop: download_breeze_archive(
                out, db, api=None, progress_cb=prog, should_stop=stop))

    def on_chansey(self):
        self._start_archive_import(
            "Download Chansey 60FPS/Res/GFX",
            "Import the LIVE ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats repo —\n"
            "the ORIGINAL source of the 60 FPS / resolution / graphics cheats,\n"
            "always current — and add all cheats to the database?",
            "Chansey 60FPS/Res/GFX",
            lambda out, db, prog, stop: download_chansey_archive(
                out, db, api=None, progress_cb=prog, should_stop=stop))

    def on_mynx(self):
        self._start_archive_import(
            "Download MyNXCheats",
            "Import the LIVE Arch9SK7/MyNXCheats repo — a curated collection\n"
            "for ~50 recent big titles (TotK, Scarlet/Violet, ...) — and add\n"
            "all cheats to the database?",
            "MyNXCheats",
            lambda out, db, prog, stop: download_mynx_archive(
                out, db, api=None, progress_cb=prog, should_stop=stop))

    def on_titledb_cheats(self):
        self._start_archive_import(
            "titledb Cheats",
            "Import titledb's own cheat database (cheats.json) as an extra source?",
            "titledb cheats",
            lambda out, db, prog, stop: download_titledb_cheats(
                out, db, progress_cb=prog, should_stop=stop))

    def on_ibnux(self):
        self._start_archive_import(
            "ibnux/switch-cheat",
            "Download the latest ibnux/switch-cheat archive, extract all cheats\n"
            "and add them to the database?",
            "ibnux",
            lambda out, db, prog, stop: download_ibnux_archive(
                out, db, api=None, progress_cb=prog, should_stop=stop))

    def on_update_recent(self):
        if self._busy:
            return
        try:
            pages = max(1, int(self.update_pages.get()))
        except (tk.TclError, ValueError):
            pages = 5
        if not messagebox.askyesno(
            "Update recent cheats",
            f"Scan the {pages} most recent 'latest cheat codes' page(s) on cheatslips.com\n"
            "and add any new builds - this also re-checks games already in the database\n"
            "that show up there, since that means cheatslips just updated them.\n\n"
            "Much faster than a full rescan since only the recent pages are fetched.",
        ):
            return
        self._stop_event.clear()
        self._save_settings()
        self._set_busy(True)
        self.update_btn.config(text="Updating...")
        self.status_var.set("Checking for new cheats...")
        cfg = {
            "db_path": self.db_path.get(),
            "output": self.dl_output.get(),
            "pages": pages,
            "skip_zero": self.scrape_skip_zero.get(),
            "auto_download": self.auto_download.get(),
            "token": self.api_token_var.get().strip() or None,
            "email": self.email_var.get().strip() or None,
            "password": self.password_var.get() or None,
        }
        threading.Thread(target=self._update_recent_worker, args=(cfg,), daemon=True).start()

    def _update_recent_worker(self, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        new_builds = 0
        try:
            db = GameDatabase(Path(cfg["db_path"]))
            try:
                before = db.all_build_ids()
                scraper = CheatslipsMetadataScraper(delay=0.3, max_concurrent=4)
                api = CheatslipsAPI()
                tracker = ProgressTracker("update")

                def game_cb(done, total):
                    tracker.update(done, total)
                    msg = (f"Checking recent cheats {done}/{total} ({tracker.pct()}%)"
                           f" | {tracker.rate_str('items')}")
                    self._log_queue.put(("progress", done, total, msg))

                skip_zero = bool(cfg.get("skip_zero"))

                def on_game(info):
                    enrich_info_with_api(info, api)
                    # Optional "skip 0-cheat" filter (off by default so newly
                    # discovered 0-cheat builds are recorded and visible).
                    if skip_zero:
                        info["sources"] = [s for s in info.get("sources", [])
                                           if (s.get("cheat_count") or 0) > 0]
                        if not info["sources"]:
                            return
                    db.upsert_game(info, source="cheatslips")

                scraper.scrape_all_streaming(
                    on_game, entry_only=True, max_pages=cfg["pages"],
                    game_cb=game_cb, should_stop=self._stop_event.is_set,
                    skip_slugs=None,
                )
                after = db.all_build_ids()
                new_builds = len(after - before)
                # Correct counts from the actual files (never trust cheatslips'
                # numbers where we have the real file on disk).
                if not self._stop_event.is_set():
                    recount_cheats_from_disk(db, Path(cfg["output"]), only_missing=False,
                                             should_stop=self._stop_event.is_set)
                if self._stop_event.is_set():
                    print("Stopped by user.")
                print(f"Update done — {new_builds} new build(s) found. DB now holds {db.count()} builds.")
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Update failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("update_done", new_builds, cfg))

    def on_add_entry(self):
        if self._busy:
            return
        dlg = AddEntryDialog(self.root)
        self.root.wait_window(dlg.top)
        r = dlg.result
        if not r:
            return
        tid, bid = r["title_id"], r["build_id"]
        content = r["content"]
        names = parse_cheat_names_from_content(content)
        try:
            # 1) Write the cheat file into our schema (ready for the SD card).
            save_dir = Path(self.dl_output.get()) / "titles" / tid / "cheats"
            save_path = save_dir / f"{bid}.txt"
            save_cheat_merged(save_path, content)
            # 2) Add to the database (source = manual).
            db = GameDatabase(Path(self.db_path.get()))
            db.upsert_game({
                "title_id": tid, "title": r["name"] or None, "slug": None,
                "image": None, "banner": None,
                "sources": [{
                    "build_id": bid, "title_id": tid, "source_id": None,
                    "version": r["version"] or None, "upload_date": None,
                    "cheat_count": len(names), "cheat_names": names,
                    "credits": r["credits"] or None, "description": None, "cheat_id": None,
                }],
            }, source="manual")
            db.close()
        except Exception as exc:
            messagebox.showerror("Add entry", str(exc))
            return
        # Keep the downloaded cache in sync so the new entry shows as downloaded.
        cached = self._load_downloaded_cache()
        cached.add(bid.upper())
        self._save_downloaded_cache(cached)
        self.status_var.set(f"Added {tid}/{bid} ({len(names)} cheat(s)).")
        self.refresh_table()

    def _info_cfg(self):
        return {
            "db_path": self.db_path.get(),
            "output": self.dl_output.get(),
            "token": self.api_token_var.get().strip() or None,
            "email": self.email_var.get().strip() or None,
            "password": self.password_var.get() or None,
        }

    def _start_info_task(self, label, task):
        """Run a single enrichment task ``task(db, cfg)`` in a background worker."""
        if self._busy:
            return
        self._save_settings()
        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set(f"{label}...")
        threading.Thread(target=self._info_task_worker,
                         args=(label, task, self._info_cfg()), daemon=True).start()

    def _info_task_worker(self, label, task, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            db = GameDatabase(Path(cfg["db_path"]))
            try:
                task(db, cfg)
                print(f"{label} finished. DB holds {db.count()} builds.")
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"{label} failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("download_done",))

    @staticmethod
    def _scope_suffix(title_ids):
        """Label suffix that shows a scoped run (context menu on selected rows)."""
        return f" ({len(title_ids)} selected)" if title_ids else ""

    def on_get_names(self, title_ids=None):
        """Fill missing game names + covers + metadata (titledb -> API ->
        switchbrew/tinfoil/GitHub -> known names -> derive from base).

        With ``title_ids`` (from the context menu on selected rows) the run is
        limited to those titles; without it, the whole database is processed.
        """
        def task(db, cfg):
            db.set_write_restrict(title_ids)
            api = self._build_api(cfg)
            tr = ProgressTracker("names")
            def prog(d, t):
                tr.update(d, t)
                self._log_queue.put(("progress", d, t,
                    f"Names {d}/{t} ({tr.pct()}%) | {tr.rate_str('items')}"))
            # with_regions=False: region tagging is its own button now.
            n = fill_missing_names(db, api=api, progress_cb=prog,
                                   should_stop=self._stop_event.is_set,
                                   cache_dir=str(DATA_DIR), with_regions=False)
            print(f"Names + covers: {n} game(s) enriched.")
        self._start_info_task("Get Names" + self._scope_suffix(title_ids), task)

    def on_get_region(self, title_ids=None):
        """Tag every title with its eShop region (US/EU/AU/JP/KR/HK) from titledb."""
        def task(db, cfg):
            db.set_write_restrict(title_ids)
            tr = ProgressTracker("region")
            def prog(d, t):
                tr.update(d, t)
                self._log_queue.put(("progress", d, t, f"Region {d}/{t} ({tr.pct()}%)"))
            n = fill_regions_from_titledb(db, cache_dir=str(DATA_DIR), progress_cb=prog,
                                          should_stop=self._stop_event.is_set)
            print(f"Region tags: {n} title(s) tagged.")
        self._start_info_task("Get Region" + self._scope_suffix(title_ids), task)

    def on_get_versions_titledb(self, title_ids=None):
        """Fill build versions from titledb only (builds.json / versions.json)."""
        def task(db, cfg):
            db.set_write_restrict(title_ids)
            def prog(d, t):
                self._log_queue.put(("progress", d, t, f"titledb versions {d}/{t}"))
            n = fill_versions_from_titledb(db, progress_cb=prog,
                                           should_stop=self._stop_event.is_set)
            print(f"titledb versions: {n} filled.")
        self._start_info_task("Get Versions from TitleDB" + self._scope_suffix(title_ids), task)

    def on_get_versions_cheatslips(self, title_ids=None):
        """Fill remaining build versions from cheatslips' game pages (HTML)."""
        def task(db, cfg):
            db.set_write_restrict(title_ids)
            api = self._build_api(cfg)
            scraper = CheatslipsMetadataScraper(delay=0.3, max_concurrent=4)
            def prog(d, t):
                self._log_queue.put(("progress", d, t, f"cheatslips versions {d}/{t}"))
            n = fill_missing_versions(api, scraper, db, progress_cb=prog,
                                      should_stop=self._stop_event.is_set)
            print(f"cheatslips versions: {n} filled.")
        self._start_info_task("Get Versions Cheatslips" + self._scope_suffix(title_ids), task)

    def on_get_descriptions(self, title_ids=None):
        """Fill missing game descriptions + intro texts from titledb for all titles."""
        def task(db, cfg):
            db.set_write_restrict(title_ids)
            def prog(d, t):
                self._log_queue.put(("progress", d, t, f"Descriptions region {d}/{t}"))
            n = fill_descriptions_from_titledb(db, cache_dir=str(DATA_DIR), progress_cb=prog,
                                               should_stop=self._stop_event.is_set)
            print(f"Descriptions: {n} title(s) filled.")
        self._start_info_task("Get Descriptions" + self._scope_suffix(title_ids), task)

    # Context-menu wrappers: run the Get-* actions on the SELECTED rows only.
    def _ctx_get_names(self):
        self.on_get_names(self._selected_title_ids() or None)

    def _ctx_get_region(self):
        self.on_get_region(self._selected_title_ids() or None)

    def _ctx_get_versions_titledb(self):
        self.on_get_versions_titledb(self._selected_title_ids() or None)

    def _ctx_get_versions_cheatslips(self):
        self.on_get_versions_cheatslips(self._selected_title_ids() or None)

    def _ctx_get_descriptions(self):
        self.on_get_descriptions(self._selected_title_ids() or None)

    def on_import_zip(self):
        """Import a cheat ZIP archive (as exported via 'Export to ZIP', or any
        Atmosphère/Breeze/EdiZon-layout archive) back into the DB + output."""
        if self._busy:
            return
        from tkinter import filedialog
        prev = self.export_zip_path.get().strip()
        initialdir = str(Path(prev).parent) if prev else self.dl_output.get()
        zpath = filedialog.askopenfilename(
            title="Import cheat ZIP", parent=self.root, initialdir=initialdir,
            filetypes=[("ZIP archive", "*.zip"), ("All files", "*.*")])
        if not zpath:
            return
        self._start_archive_import(
            "Import ZIP",
            f"Import cheats from:\n{zpath}\n\nAdd them to the database and the "
            "output folder?",
            "ZIP import",
            lambda out, db, prog, stop: import_cheats_from_zip(
                out, db, zpath, progress_cb=prog, should_stop=stop))

    def on_import_disk(self):
        if self._busy:
            return
        out = Path(self.dl_output.get())
        if not (out / "titles").exists() and not (out / "by_bid").exists():
            messagebox.showinfo(
                "Import disk",
                f"No titles/ or by_bid/ folder found in:\n{out}\n\n"
                "Download or place cheat files there first.",
            )
            return
        if not messagebox.askyesno(
            "Import disk",
            f"Scan {out} for titles/ and by_bid/ cheat files and import missing entries into the DB?\n\n"
            "Known build ids (e.g. Potion Permit) will be linked automatically.",
        ):
            return
        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set("Importing cheat files from disk...")
        cfg = {"db_path": self.db_path.get(), "output": str(out)}
        threading.Thread(target=self._import_disk_worker, args=(cfg,), daemon=True).start()

    def _import_disk_worker(self, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            db = GameDatabase(Path(cfg["db_path"]))
            try:
                out = Path(cfg["output"])
                total = import_disk_titles_to_db(
                    out / "titles", out / "meta", db,
                )
                print(f"Import disk done — {total} row(s) imported. DB holds {db.count()} builds.")
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Import disk failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("download_done",))

    def on_fix_id_names(self):
        if self._busy:
            return
        if not messagebox.askyesno(
            "Fix ID names",
            "Search for rows where the game name is the raw title id and replace it\n"
            "with a real name (known names or derived from the base game).\n\n"
            "Proceed?",
        ):
            return
        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set("Fixing title-id placeholders...")
        cfg = {"db_path": self.db_path.get()}
        threading.Thread(target=self._fix_id_names_worker, args=(cfg,), daemon=True).start()

    def _fix_id_names_worker(self, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            db = GameDatabase(Path(cfg["db_path"]))
            try:
                tracker = ProgressTracker("fix_id_names")

                def prog(done, total):
                    tracker.update(done, total)
                    msg = (f"Fix ID names {done}/{total} ({tracker.pct()}%)"
                           f" | {tracker.rate_str('items')} | ~{tracker.eta_str()} remaining")
                    self._log_queue.put(("progress", done, total, msg))

                total = fix_title_id_names(
                    db, progress_cb=prog, should_stop=self._stop_event.is_set,
                )
                # Also delete any rows that carry a placeholder build id.
                removed = remove_placeholder_builds(db)
                total += removed
                print(f"Fix ID names done — {total} row(s) fixed. DB holds {db.count()} builds.")
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Fix ID names failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("download_done",))

    def on_sync_titles(self):
        if self._busy:
            return
        if not messagebox.askyesno(
            "Sync titles folder with DB",
            "Remove every title_id folder (and any cheat files) that is not in the database, "
            "so the titles folder matches the database exactly?",
        ):
            return
        self._save_settings()
        self._stop_event.clear()
        self._set_busy(True)
        cfg = {
            "output": self.dl_output.get(),
            "db_path": self.db_path.get(),
        }
        threading.Thread(target=self._sync_titles_worker, args=(cfg,), daemon=True).start()

    def _sync_titles_worker(self, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            db = GameDatabase(Path(cfg["db_path"]))
            try:
                removed_tids, removed_files = cleanup_titles_folder(
                    db, Path(cfg["output"]), should_stop=self._stop_event.is_set,
                )
                print(
                    f"Sync done — removed {removed_tids} title folder(s) "
                    f"and {removed_files} extra cheat file(s)."
                )
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Sync failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("download_done",))

    def on_fix_zero(self):
        if self._busy:
            return
        try:
            db = GameDatabase(Path(self.db_path.get()))
            tids = db.zero_cheat_title_ids()
            db.close()
        except Exception as exc:
            messagebox.showerror("Fix 0-cheat", str(exc))
            return
        if not tids:
            messagebox.showinfo("Fix 0-cheat", "No entries with 0 cheats found.")
            return
        if not messagebox.askyesno(
            "Fix 0-cheat",
            f"{len(tids)} game(s) have entries with 0 cheats.\n"
            "Refresh them from the API and download their cheat codes?",
        ):
            return
        self._save_settings()
        self._stop_event.clear()
        self._set_busy(True)
        cfg = {
            "email": self.email_var.get().strip() or None,
            "password": self.password_var.get() or None,
            "token": self.api_token_var.get().strip() or None,
            "output": self.dl_output.get(),
            "db_path": self.db_path.get(),
        }
        threading.Thread(target=self._fix_zero_worker, args=(tids, cfg), daemon=True).start()

    def _fix_zero_worker(self, title_ids, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            api = CheatslipsAPI(token=cfg["token"])
            if not api.token and cfg["email"] and cfg["password"]:
                print("Requesting API token...")
                api.get_token(cfg["email"], cfg["password"])

            db = GameDatabase(Path(cfg["db_path"]))
            try:
                def prog(done, total):
                    self._log_queue.put(("progress", done, total, f"Refreshing {done}/{total}"))

                refresh_titles_from_api(api, db, title_ids,
                                        progress_cb=prog, should_stop=self._stop_event.is_set)

                if api.token and api.token_works():
                    def dprog(done, total):
                        self._log_queue.put(("progress", done, total, f"Downloading {done}/{total}"))
                    saved = api_download_from_db(api, db, Path(cfg["output"]),
                                                 title_ids=title_ids, resume=True,
                                                 progress_cb=dprog,
                                                 should_stop=self._stop_event.is_set)
                    print(f"Fix finished - {saved} new file(s).")
                else:
                    print("Metadata refreshed. (No valid token - cheat codes not downloaded.)")
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Fix failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("download_done",))

    def on_recount_disk(self):
        """Rescan every downloaded cheat .txt and write the real cheat count back
        to the DB, so the GUI shows the true number of cheats per build even when
        the API/HTML reported 0."""
        if self._busy:
            return
        if not messagebox.askyesno(
            "Recount cheats from disk",
            "Scan every downloaded cheat file on disk and update the cheat count "
            "in the database to match the actual file contents?\n\n"
            "This corrects builds that show 0 cheats even though the .txt file "
            "contains codes. It does not delete anything.",
        ):
            return
        self._save_settings()
        self._stop_event.clear()
        self._set_busy(True)
        cfg = {
            "output": self.dl_output.get(),
            "db_path": self.db_path.get(),
        }
        threading.Thread(target=self._recount_disk_worker, args=(cfg,), daemon=True).start()

    def _recount_disk_worker(self, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            db = GameDatabase(Path(cfg["db_path"]))
            try:
                def prog(done, total):
                    self._log_queue.put(("progress", done, total,
                                         f"Recounting {done}/{total}"))
                updated = recount_cheats_from_disk(
                    db, Path(cfg["output"]), only_missing=False,
                    progress_cb=prog, should_stop=self._stop_event.is_set)
                print(f"Recount done — {updated} build(s) updated from disk.")
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Recount failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("download_done",))

    def on_find_empty(self):
        """Scan downloaded files for ones with NO usable cheats (empty, quota/
        placeholder, or codeless names) and report them, then reset their DB
        count to 0 so they show up under 'Not downloaded'."""
        if self._busy:
            return
        if not messagebox.askyesno(
            "Scan for empty cheat files",
            "Scan every downloaded cheat file and find the ones that contain NO "
            "usable cheats — empty, a quota/placeholder message, or only names "
            "without any codes.\n\n"
            "They are listed in the log and their cheat count is reset to 0 so "
            "they appear under 'Not downloaded'. No files are deleted.",
        ):
            return
        self._save_settings()
        self._stop_event.clear()
        self._set_busy(True)
        cfg = {"output": self.dl_output.get(), "db_path": self.db_path.get()}
        threading.Thread(target=self._find_empty_worker, args=(cfg,), daemon=True).start()

    def _find_empty_worker(self, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            db = GameDatabase(Path(cfg["db_path"]))
            try:
                def prog(done, total):
                    self._log_queue.put(("progress", done, total,
                                         f"Scanning {done}/{total}"))
                empty = find_empty_cheat_files(
                    db, Path(cfg["output"]), progress_cb=prog,
                    should_stop=self._stop_event.is_set)
                if not empty:
                    print("No empty cheat files found — every downloaded file has real cheats.")
                else:
                    print(f"\n{len(empty)} empty cheat file(s) (no usable cheats):")
                    for tid, bid in empty:
                        print(f"    {tid}/{bid}")
                        db.set_build_cheats(tid, bid, 0, [])
                    print(f"Reset {len(empty)} entr{'y' if len(empty) == 1 else 'ies'} "
                          f"to 0 cheats — they now show under 'Not downloaded'.")
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Scan for empty files failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("download_done",))

    def on_clean_invalid(self):
        if self._busy:
            return
        if not messagebox.askyesno(
            "Clean invalid cheat files",
            "Scan all downloaded cheat files and delete the ones that only contain "
            "a quota message or placeholder?\n\n"
            "The database entries will be reset to 0 cheats so they can be re-downloaded "
            "once the quota resets.",
        ):
            return
        self._save_settings()
        self._stop_event.clear()
        self._set_busy(True)
        cfg = {
            "output": self.dl_output.get(),
            "db_path": self.db_path.get(),
        }
        threading.Thread(target=self._clean_invalid_worker, args=(cfg,), daemon=True).start()

    def _clean_invalid_worker(self, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            db = GameDatabase(Path(cfg["db_path"]))
            try:
                cleaned = cleanup_invalid_cheat_entries(
                    db, Path(cfg["output"]), should_stop=self._stop_event.is_set)
                print(f"Clean invalid files done — {cleaned} entr{'y' if cleaned == 1 else 'ies'} reset.")
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Clean failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("download_done",))

    def on_clear_unavailable(self):
        """Clear the 'no codes on cheatslips' marks so those builds are retried."""
        if self._busy:
            return
        try:
            db = GameDatabase(Path(self.db_path.get()))
            try:
                n = db.count_unavailable()
                if n == 0:
                    messagebox.showinfo(
                        "Retry 'unavailable' builds",
                        "No builds are currently marked as unavailable.")
                    return
                if not messagebox.askyesno(
                    "Retry 'unavailable' builds",
                    f"{n} build(s) are marked as having no codes on cheatslips and "
                    f"are skipped during downloads.\n\nClear these marks so they are "
                    f"retried on the next download?"):
                    return
                cleared = db.clear_unavailable()
            finally:
                db.close()
        except Exception as exc:
            messagebox.showerror("Retry 'unavailable' builds", str(exc))
            return
        self.status_var.set(
            f"Cleared {cleared} 'unavailable' mark(s) — they will be retried next download.")
        self.refresh_table()

    def on_retry_quota_skipped(self):
        if self._busy:
            return
        quota_file = Path(self.dl_output.get()) / "quota_skipped.txt"
        if not quota_file.exists():
            messagebox.showinfo(
                "Retry quota-skipped builds",
                f"No quota-skipped list found.\n\nExpected file:\n{quota_file}\n\n"
                "Run a download first; skipped builds are recorded automatically.")
            return
        try:
            pairs = []
            for line in quota_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    pairs.append((parts[0], parts[1]))
        except Exception as exc:
            messagebox.showerror("Retry quota-skipped builds", str(exc))
            return
        if not pairs:
            messagebox.showinfo("Retry quota-skipped builds", "No builds listed in the file.")
            return
        if not messagebox.askyesno(
            "Retry quota-skipped builds",
            f"Retry {len(pairs)} build(s) from {quota_file.name}?\n\n"
            "Make sure your quota has reset first.",
        ):
            return
        self._save_settings()
        self._stop_event.clear()
        self._set_busy(True)
        cfg = {
            "email": self.email_var.get().strip() or None,
            "password": self.password_var.get() or None,
            "token": self.api_token_var.get().strip() or None,
            "output": self.dl_output.get(),
            "db_path": self.db_path.get(),
            "pairs": pairs,
            "auto_reset": self.auto_reset_quota.get(),
            "browser": self._browser_kind(),
        }
        threading.Thread(target=self._retry_quota_worker, args=(cfg,), daemon=True).start()

    def _retry_quota_worker(self, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            api = CheatslipsAPI(token=cfg["token"])
            if not api.token and cfg["email"] and cfg["password"]:
                print("Requesting API token...")
                api.get_token(cfg["email"], cfg["password"])
                print("Got API token.")
            if not api.token_works():
                raise RuntimeError("API token is invalid.")
            db = GameDatabase(Path(cfg["db_path"]))
            try:
                out = Path(cfg["output"])
                if cfg.get("auto_reset"):
                    # Enrich each (tid, bid) with slug/source_id from the DB so the
                    # browser fallback can reach the right game page.
                    lookup = {(t.upper(), b.upper()): (slug, sid)
                              for t, b, slug, sid in db.builds_for_download()}
                    enriched = []
                    for tid, bid in cfg["pairs"]:
                        slug, sid = lookup.get((tid.upper(), bid.upper()), ("", ""))
                        enriched.append((tid, bid, slug, sid))
                    saved = self._run_quota_reset_loop(api, db, out, enriched, cfg)
                else:
                    def prog(done, total):
                        self._log_queue.put(("progress", done, total, f"Retrying {done}/{total}"))
                    saved = download_build_list(
                        api, db, out, cfg["pairs"],
                        progress_cb=prog, should_stop=self._stop_event.is_set)
                print(f"Retry finished - {saved} new file(s).")
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Retry failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("download_done",))

    def _insert_link(self, label, url):
        """Insert a clickable link into the detail panel that opens in a browser."""
        tag = f"link{self._link_counter}"
        self._link_counter += 1
        self.cheat_text.insert("end", label, (tag,))
        self.cheat_text.tag_config(tag, foreground=theme()["link"], underline=True)
        self.cheat_text.tag_bind(tag, "<Button-1>", lambda _e, u=url: webbrowser.open(u))
        self.cheat_text.tag_bind(tag, "<Enter>", lambda _e: self.cheat_text.config(cursor="hand2"))
        self.cheat_text.tag_bind(tag, "<Leave>", lambda _e: self.cheat_text.config(cursor=""))

    def _on_select_row(self, _event=None):
        sel = self.tree.selection()
        t = self.cheat_text
        t.config(state="normal")
        t.delete("1.0", "end")
        if not sel:
            t.config(state="disabled")
            return
        with self._row_lock:
            values = self.tree.item(sel[0], "values")
            col_ids = [c[0] for c in COLUMNS]

            def col(name):
                i = col_ids.index(name)
                return values[i] if len(values) > i else None

            bid = col("build_id") or "?"
            sel_tid = col("title_id")
            game_title = (col("game_title") or "").strip()
            version = col("version")
            data = self._row_cheats.get(sel[0], {})
        names = data.get("names", [])

        def field(label, val, value_tag="value"):
            if val:
                t.insert("end", f"{label}\t", ("label",))
                t.insert("end", f"{val}\n", (value_tag,))

        # --- Header: game name, then version / cheat count ---
        if game_title:
            t.insert("end", game_title + "\n", ("title",))
        cc = col("cheat_count")
        if names:
            count_str = f"{len(names)} cheat" + ("" if len(names) == 1 else "s")
        elif cc and str(cc) not in ("-", "0"):
            count_str = f"{cc} cheats"
        else:
            count_str = "count unknown"
        sub_parts = []
        if version and str(version) not in ("-", ""):
            sub_parts.append(str(version))
        sub_parts.append(count_str)
        t.insert("end", "  ·  ".join(sub_parts) + "\n\n", ("subtle",))

        # --- Download status (green = on disk, red = missing) ---
        on_disk = False
        if sel_tid and bid not in ("?", "-"):
            out = Path(self.dl_output.get())
            on_disk = ((out / "titles" / sel_tid / "cheats" / f"{bid}.txt").exists()
                       or (out / "by_bid" / f"{bid}.txt").exists())
        if on_disk:
            t.insert("end", "✓ Downloaded\n\n", ("ok",))
        else:
            t.insert("end", "✗ Not downloaded\n", ("missing",))
            t.insert("end", "metadata only — codes still need fetching\n\n", ("subtle",))

        # --- Identifiers (clearly labelled, monospace so they line up) ---
        field("Title ID", sel_tid if sel_tid not in (None, "", "-") else None, "mono")
        field("Build ID", bid if bid not in (None, "", "-", "?") else None, "mono")

        # --- Update/DLC title-id warning ---
        kind = title_id_kind(sel_tid)
        if kind in ("update", "dlc"):
            try:
                _db = GameDatabase(Path(self.db_path.get()))
                base, confident = resolve_base_title_id(_db, sel_tid)
                _db.close()
            except Exception:
                base, confident = base_title_id(sel_tid), False
            note = "found in DB" if confident else "best guess — verify"
            t.insert("end", f"⚠ {kind.upper()} id — cheats need base id {base} ({note})\n\n",
                     ("warn",))

        # --- Metadata (aligned label / value columns) ---
        field("Region", data.get("region"))
        field("Source", data.get("source"))
        field("Publisher", data.get("publisher"))
        field("Developer", data.get("developer"))
        field("Genre", data.get("category"))
        field("Languages", data.get("languages"))
        field("Players", data.get("players"))
        field("Released", data.get("release_date"))
        field("Version date", data.get("version_date"))
        field("Content", data.get("rating_content"))
        if data.get("is_demo"):
            field("Demo", "yes")
        field("Credits", data.get("credits"))

        # Nintendo eShop link (from nsuId).
        nsu = data.get("nsu_id")
        if nsu:
            t.insert("end", "eShop\t", ("label",))
            self._insert_link("open page", f"https://ec.nintendo.com/US/en/titles/{nsu}")
            t.insert("end", "\n")

        # Intro + description (toggle: "Show Description"). Fetch online if the DB
        # has none yet — like "Show Covers" pulls the cover on demand.
        if self.show_description.get():
            intro = data.get("intro")
            desc = data.get("game_description") or data.get("description")
            if intro:
                t.insert("end", f"\n{intro}\n", ("value",))
            if desc:
                t.insert("end", f"\n{desc}\n", ("value",))
            if not intro and not desc:
                fetching = self._maybe_fetch_description(sel_tid, data)
                t.insert("end", "\n(loading description…)\n" if fetching
                         else "\n(no description available)\n", ("subtle",))

        # Screenshots (clickable).
        shots = data.get("screenshots")
        if shots:
            try:
                urls = json.loads(shots)
            except Exception:
                urls = []
            if urls:
                t.insert("end", "\nScreenshots\t", ("label",))
                for idx, url in enumerate(urls, 1):
                    self._insert_link(f"#{idx}", url)
                    t.insert("end", "  ")
                t.insert("end", "\n")

        # --- Cheats ---
        t.insert("end", f"Cheats ({len(names)})\n", ("section",))
        if names:
            for name in names:
                t.insert("end", f"• {name}\n", ("bullet",))
        else:
            t.insert("end", "(none listed)\n", ("subtle",))
        t.config(state="disabled")
        self._update_cover(data.get("image") if sel else None, sel_tid)

    # ------------------------------------------------------------- cover img
    @staticmethod
    def _normalize_url(url):
        """Fix cover URLs that come without a scheme.

        titledb stores some covers as protocol-relative '//cdn01.nintendo...' or
        bare 'cdn01.nintendo...'; requests needs an explicit https:// scheme.
        """
        u = (url or "").strip()
        if not u:
            return u
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http://") or u.startswith("https://"):
            return u
        return "https://" + u

    def _cover_cache_path(self, url, title_id):
        """Local cache file for a cover: coversdownload/{title_id}.<ext> (or a url hash)."""
        import re as _re
        ext = ".jpg"
        m = _re.search(r"\.(jpg|jpeg|png|webp|gif|bmp)(?:\?|$)", url or "", _re.IGNORECASE)
        if m:
            ext = "." + m.group(1).lower()
        if title_id and _re.fullmatch(r"[A-Fa-f0-9]{16}", title_id):
            name = title_id.upper()
        else:
            import hashlib
            name = hashlib.sha1((url or "").encode("utf-8")).hexdigest()[:16]
        return Path(COVERS_DIR) / f"{name}{ext}"

    def _update_cover(self, url, title_id=None):
        if not _PIL_OK or not self.show_images.get() or not url:
            self.cover_label.config(image="", text="")
            self.cover_label.image = None
            return
        if url in self._img_refs:
            self.cover_label.config(image=self._img_refs[url], text="")
            self.cover_label.image = self._img_refs[url]
            return
        token = object()
        self._img_token = token
        # Only use the on-disk cache when "Save Covers" is enabled.
        cache_path = self._cover_cache_path(url, title_id) if self.cache_covers.get() else None
        self.cover_label.config(image="", text="loading cover...")
        threading.Thread(target=self._fetch_cover, args=(url, token, cache_path),
                         daemon=True).start()

    def _fetch_cover(self, url, token, cache_path=None):
        try:
            import io
            # Use the local cache if present (offline, no re-download); otherwise
            # download once and store the original bytes on disk for next time.
            if cache_path is not None and cache_path.exists():
                raw = cache_path.read_bytes()
            else:
                import requests
                raw = requests.get(self._normalize_url(url), timeout=15).content
                if cache_path is not None:
                    try:
                        cache_path.parent.mkdir(parents=True, exist_ok=True)
                        cache_path.write_bytes(raw)
                    except Exception:
                        pass
            img = Image.open(io.BytesIO(raw))
            img.thumbnail((180, 180))
            self.root.after(0, lambda: self._apply_cover(url, token, img))
        except Exception:
            self.root.after(0, lambda: self.cover_label.config(text="(cover unavailable)", image=""))

    def _apply_cover(self, url, token, pil_img):
        if token is not self._img_token:
            return  # selection changed in the meantime
        try:
            photo = ImageTk.PhotoImage(pil_img)
        except Exception:
            self.cover_label.config(text="(cover error)", image="")
            return
        self._img_refs[url] = photo
        self.cover_label.config(image=photo, text="")
        self.cover_label.image = photo

    # --------------------------------------------------- description on demand
    def _maybe_fetch_description(self, tid, data):
        """When 'Show Description' is on but the DB has no description for this
        title, fetch it online (cheatslips API) in the background and store it —
        analogous to how covers are pulled on demand. Returns True if a fetch
        was started."""
        if not self.show_description.get() or not tid or len(tid) != 16:
            return False
        if data.get("game_description") or data.get("description") or data.get("intro"):
            return False
        if tid in self._desc_attempted:
            return False
        self._desc_attempted.add(tid)
        token = object()
        self._desc_token = token
        threading.Thread(target=self._fetch_description, args=(tid, token), daemon=True).start()
        return True

    def _load_titledb_desc(self):
        """Lazily build a {title_id: (description, intro)} index from the locally
        cached titledb region files (no download — works offline and is far
        faster/more reliable than cheatslips). Cached for the session; returns {}
        if no region files are present yet (run 'Fill Names' once to fetch them)."""
        if self._titledb_desc is not None:
            return self._titledb_desc
        with self._titledb_desc_lock:
            if self._titledb_desc is not None:
                return self._titledb_desc
            index = {}
            for region in _TITLEDB_DESC_REGIONS:
                cache = DATA_DIR / f"titledb_{region}.json"
                if not cache.exists():
                    continue
                try:
                    data = json.loads(cache.read_text(encoding="utf-8"))
                except Exception:
                    continue
                for e in data.values():
                    if not isinstance(e, dict):
                        continue
                    tid = (e.get("id") or "").upper()
                    if not tid or tid in index:
                        continue
                    desc = (e.get("description") or "").strip()
                    intro = (e.get("intro") or "").strip()
                    if desc or intro:
                        index[tid] = (desc, intro)
            self._titledb_desc = index
            return index

    def _fetch_description(self, tid, token):
        # Source: locally cached titledb (offline, fast) — NOT cheatslips.
        idx = self._load_titledb_desc()
        entry = idx.get((tid or "").upper())
        if not entry:
            # No cached titledb data (or title not covered) — allow a later retry
            # once the region files have been downloaded via "Fill Names".
            if not idx:
                self._desc_attempted.discard(tid)
            return
        desc, intro = entry
        if not desc and not intro:
            return
        try:
            db = GameDatabase(Path(self.db_path.get()))
            try:
                fields = {}
                if desc:
                    fields["game_description"] = desc
                if intro:
                    fields["intro"] = intro
                db.update_game_fields(tid, fields)
            finally:
                db.close()
        except Exception:
            pass
        self.root.after(0, lambda: self._apply_fetched_description(tid, token, desc, intro))

    def _apply_fetched_description(self, tid, token, desc, intro):
        if token is not self._desc_token:
            return
        sel = self.tree.selection()
        if not sel:
            return
        item = sel[0]
        col_ids = [c[0] for c in COLUMNS]
        vals = self.tree.item(item, "values")
        ti = col_ids.index("title_id")
        if len(vals) <= ti or (vals[ti] or "").upper() != (tid or "").upper():
            return   # the selection moved to another game
        cache = self._row_cheats.get(item)
        if cache is not None:
            if desc:
                cache["game_description"] = desc
            if intro:
                cache["intro"] = intro
        self._on_select_row()

    def _sort_by(self, col_id: str):
        import datetime as _dt
        import re as _re

        ascending = not self._sort_state.get(col_id, False)
        self._sort_state[col_id] = ascending
        rows = [(self.tree.set(k, col_id), k) for k in self.tree.get_children("")]

        def sort_key(val):
            """Return (is_missing, comparable_value) for the given column type.

            is_missing rows are always pushed to the end, regardless of sort
            direction, so '-' placeholders don't end up first on a descending sort.
            """
            if col_id == "cheat_count":
                try:
                    return (0, int(val))
                except ValueError:
                    return (1, 0)
            if col_id == "upload_date":
                try:
                    return (0, _dt.datetime.strptime(val, "%d %b %Y"))
                except (ValueError, TypeError):
                    return (1, _dt.datetime.min)
            if col_id == "version":
                parts = tuple(int(p) for p in _re.findall(r"\d+", val or ""))
                return (1, ()) if not parts else (0, parts)
            return (0, val.lower())

        keyed = [(sort_key(val), val, k) for val, k in rows]
        valued = sorted((kv for kv in keyed if kv[0][0] == 0),
                        key=lambda kv: kv[0][1], reverse=not ascending)
        missing = [kv for kv in keyed if kv[0][0] != 0]
        for index, (_key, _val, k) in enumerate(valued + missing):
            self.tree.move(k, "", index)

    def _tree_select_all(self, _event=None):
        self.tree.selection_set(self.tree.get_children())
        return "break"

    def _tree_copy(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return "break"
        lines = ["\t".join(str(v) for v in self.tree.item(i, "values")) for i in sel]
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(lines))
        self.status_var.set(f"Copied {len(sel)} row(s) to clipboard.")
        return "break"

    def _copy_cell(self, event):
        row = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not row or not col:
            return
        idx = int(col.replace("#", "")) - 1
        values = self.tree.item(row, "values")
        if 0 <= idx < len(values):
            self.root.clipboard_clear()
            self.root.clipboard_append(str(values[idx]))
            self.status_var.set(f"Copied: {values[idx]}")

    def _choose_db(self):
        path = filedialog.askopenfilename(
            title="Select cheats database",
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")],
        )
        if path:
            self.db_path.set(path)
            self.refresh_table()

    def _choose_output(self):
        """Pick the output folder for downloaded cheat files via a folder dialog."""
        current = self.dl_output.get().strip()
        initial = current if current and Path(current).is_dir() else str(DATA_DIR)
        path = filedialog.askdirectory(title="Select output folder", initialdir=initial)
        if path:
            self.dl_output.set(path)
            self.refresh_table()

    def _open_output(self):
        """Open the output folder in the system file explorer."""
        path = Path(self.dl_output.get().strip() or DEFAULT_OUTPUT)
        try:
            path.mkdir(parents=True, exist_ok=True)
            import os
            if hasattr(os, "startfile"):           # Windows
                os.startfile(str(path))
            else:                                   # macOS / Linux fallback
                import subprocess, sys as _sys
                opener = "open" if _sys.platform == "darwin" else "xdg-open"
                subprocess.Popen([opener, str(path)])
        except Exception as exc:
            messagebox.showerror("Open folder", f"Could not open:\n{path}\n\n{exc}")

    def _on_closing(self):
        if self._busy:
            if not messagebox.askyesno("Quit", "Scraping/downloading in progress. Really quit?"):
                return
            self._stop_event.set()
        self._save_settings()
        if self._log_writer and hasattr(self._log_writer, 'close'):
            try:
                self._log_writer.close()
            except Exception:
                pass
        self.root.destroy()

    def on_export_csv(self):
        path = Path(self.db_path.get())
        if not path.exists():
            messagebox.showwarning("Export CSV", "No database yet. Scrape first.")
            return
        dest = filedialog.asksaveasfilename(
            title="Export database to CSV",
            defaultextension=".csv",
            initialfile="cheats.csv",
            filetypes=[("CSV file", "*.csv"), ("All files", "*.*")],
        )
        if not dest:
            return
        try:
            db = GameDatabase(path)
            rows = db.search(term=self.search_var.get().strip() or None)
            db.close()
            n = export_rows_csv(rows, Path(dest))
        except Exception as exc:
            messagebox.showerror("Export CSV", f"Failed: {exc}")
            return
        self.status_var.set(f"Exported {n} row(s) to {dest}")
        messagebox.showinfo("Export CSV", f"""Exported {n} row(s) to:
{dest}

Columns included:
• Game Title, Title/Build ID, Version, Upload Date
• Cheat Count & Names, Credits, Description
• Cover/Banner URLs, Source (GBatemp/titledb/cheatslips)
• Publisher, Developer, Genre, Release Date
• Player Count, Size, Rating, and more""")

    def on_export_db(self):
        """Export a full copy of the entire SQLite database (cheats.db)."""
        import datetime as _dt
        import sqlite3 as _sqlite3

        src = Path(self.db_path.get())
        if not src.exists():
            messagebox.showwarning("Export database", "No database file yet. Scrape first.")
            return
        default_name = f"cheats_backup_{_dt.date.today().isoformat()}.db"
        dest = filedialog.asksaveasfilename(
            title="Export full database",
            defaultextension=".db",
            initialfile=default_name,
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")],
        )
        if not dest:
            return
        if Path(dest).resolve() == src.resolve():
            messagebox.showwarning("Export database",
                                   "Choose a different file than the live database.")
            return
        srccon = dstcon = None
        try:
            # SQLite online backup -> a clean, consistent copy even if WAL is in use.
            # (close explicitly: `with sqlite3.connect` only ends the transaction,
            #  it does not release the file handle.)
            srccon = _sqlite3.connect(str(src))
            dstcon = _sqlite3.connect(dest)
            srccon.backup(dstcon)
        except Exception as exc:
            messagebox.showerror("Export database", f"Failed: {exc}")
            return
        finally:
            for con in (dstcon, srccon):
                if con is not None:
                    try:
                        con.close()
                    except Exception:
                        pass
        try:
            size_mb = Path(dest).stat().st_size / (1024 * 1024)
        except Exception:
            size_mb = 0
        self.status_var.set(f"Database exported to {dest} ({size_mb:.1f} MB)")
        messagebox.showinfo("Export database",
                            f"Full database exported to:\n{dest}\n\n{size_mb:.1f} MB")

    def on_import_db(self):
        """Import a previously exported cheats.db (merge into or replace the current)."""
        import sqlite3 as _sqlite3

        if self._busy:
            return
        src = filedialog.askopenfilename(
            title="Import database (.db)",
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")],
            initialdir=str(DATA_DIR),
        )
        if not src:
            return
        src = Path(src)
        live = Path(self.db_path.get())
        if src.resolve() == live.resolve():
            messagebox.showwarning("Import database",
                                   "That file is already the current database.")
            return
        # Sanity-check: it must be a valid cheats database (has a 'builds' table).
        try:
            con = _sqlite3.connect(str(src))
            has = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                              "AND name='builds'").fetchone()
            con.close()
        except Exception as exc:
            messagebox.showerror("Import database",
                                 f"Not a valid database file:\n{exc}")
            return
        if not has:
            messagebox.showerror("Import database",
                                 "This file has no 'builds' table — it is not a "
                                 "Switch Cheats database.")
            return

        dlg = ImportDBDialog(self.root, src.name)
        self.root.wait_window(dlg.top)
        if not dlg.result:
            return
        mode = dlg.result["mode"]
        if mode == "replace":
            if not messagebox.askyesno(
                "Replace database",
                "Replace the ENTIRE current database with the imported one?\n\n"
                "A timestamped backup of the current database is saved first.",
                icon="warning"):
                return

        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set(f"Importing database ({mode})...")
        threading.Thread(target=self._import_db_worker,
                         args=(str(live), str(src), mode), daemon=True).start()

    def _import_db_worker(self, live_path, src_path, mode):
        try:
            summary = import_database(live_path, src_path, mode=mode)
            self._log_queue.put(("import_db_done", summary))
        except Exception as exc:
            self._log_queue.put(("error", f"Import database failed:\n{exc}"))
            self._log_queue.put(("download_done",))

    # --------------------------------------------------------------- busy
    def _set_busy(self, busy: bool):
        self._busy = busy
        if busy:
            self._last_busy_start = time.time()
        state = "disabled" if busy else "normal"
        for btn in self._action_buttons:
            btn.config(state=state)
        self.stop_btn.config(state="normal" if busy else "disabled")
        if not busy:
            self.progress.config(value=0)

    def on_stop(self):
        if self._busy:
            self._stop_event.set()
            self.status_var.set("Stopping after the current item...")

    # --------------------------------------------------------------- scrape
    def on_scrape_all(self):
        if self._busy:
            return
        if not messagebox.askyesno(
            "Scrape all",
            "Scrape metadata for ALL games from cheatslips.com?\n"
            "This can take several minutes (no login required).",
        ):
            return
        self._stop_event.clear()
        self._save_settings()
        self._set_busy(True)
        self.scrape_btn.config(text="Scraping...")
        self.status_var.set("Scraping started...")
        # Read Tk variables here (main thread); never touch them from the worker.
        db_path = self.db_path.get()
        # Discovery source and 0-cheat filter are independent now.
        entry_only = not self.scrape_full_catalog.get()
        skip_zero = self.scrape_skip_zero.get()
        rescan = self.rescan_all.get()
        cfg = {
            "output": self.dl_output.get(),
            "skip_zero": skip_zero,
            "token": self.api_token_var.get().strip() or None,
            "email": self.email_var.get().strip() or None,
            "password": self.password_var.get() or None,
        }
        threading.Thread(target=self._scrape_worker, args=(db_path, entry_only, rescan, cfg),
                         daemon=True).start()

    def _save_inline_content(self, info, out, downloaded, saved_files, db=None):
        """Write cheat .txt files from content the API returned during the scrape.

        Skips builds without real content (no token / placeholder / quota message)
        and ones whose file already exists, so it is safe to call for every scraped game.
        When ``db`` is given, the build's cheat count is set from the file that was
        just written (the union of all sources), so the DB always reflects reality.
        """
        for src in info.get("sources", []):
            content = src.get("content")
            if not content or not is_valid_cheat_content(content):
                continue
            bid = (src.get("build_id") or "").upper()
            tid = (src.get("title_id") or info.get("title_id") or "").upper()
            if not bid or len(tid) != 16 or bid in downloaded:
                continue
            try:
                save_dir = out / "titles" / tid / "cheats"
                save_path = save_dir / f"{bid}.txt"
                if save_cheat_merged(save_path, content):
                    saved_files["n"] += 1
                downloaded.add(bid)
                # Count REAL cheats from the file we just wrote (authoritative;
                # codeless entries don't count).
                if db is not None and save_path.exists():
                    names = parse_valid_cheats(
                        save_path.read_text(encoding="utf-8", errors="replace"))
                    db.set_build_cheats(tid, bid, len(names), names)
            except Exception as exc:
                print(f"  WARN: could not save {tid}/{bid}: {exc}")

    def _scrape_worker(self, db_path, entry_only, rescan, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            scraper = CheatslipsMetadataScraper(delay=0.3, max_concurrent=4)
            skip_zero = bool(cfg.get("skip_zero"))
            print(("Discovery: /entry latest-cheats feed" if entry_only
                   else "Discovery: full catalog (all games)")
                  + (" · skipping 0-cheat builds" if skip_zero
                     else " · keeping 0-cheat builds"))
            db = GameDatabase(Path(db_path))
            removed = db.purge_invalid()
            if removed:
                print(f"Cleaned up {removed} old rows with missing title id.")
            # Incremental: skip games already in the DB unless 'rescan all' is set.
            skip_slugs = None if rescan else set(db.all_slugs())
            counter = {"n": 0}
            # Use a token if available: the metadata API call already returns the
            # cheat content, so we can save the .txt files in the SAME pass instead
            # of a second download run.
            api = CheatslipsAPI(token=cfg.get("token"))
            if not api.token and cfg.get("email") and cfg.get("password"):
                try:
                    api.get_token(cfg["email"], cfg["password"])
                except Exception as _e:
                    print(f"Could not get API token ({_e}) — scraping metadata only.")
                    api = CheatslipsAPI()
            save_content = bool(api.token) and api.token_works()
            out = Path(cfg.get("output") or DEFAULT_OUTPUT)
            downloaded = scan_downloaded_build_ids(out) if save_content else set()
            saved_files = {"n": 0}
            if save_content:
                print("Token OK — cheat content is saved during this scrape (single pass).")
            tracker = ProgressTracker("scrape")

            def page_cb(done, total):
                # Page discovery only updates the status line (no progress bar),
                # so the bar can track the actual game loading smoothly.
                self._log_queue.put(("status", f"Finding games... (list page {done}/{total})"))

            def game_cb(done, total):
                tracker.update(done, total)
                msg = f"Loading {done}/{total} games ({tracker.pct()}%) | {tracker.rate_str('items')} | ~{tracker.eta_str()} remaining"
                self._log_queue.put((
                    "progress", done, total, msg,
                ))

            def on_game(info):
                # Pull all extra fields the API provides (credits, description,
                # image, banner, authoritative cheat names, ids, and - with a token -
                # the cheat content).
                enrich_info_with_api(info, api)
                # Optional "skip 0-cheat" filter (independent of the discovery
                # source): drop builds with no cheats so the DB isn't filled with
                # empty placeholder builds. Off by default so 0-cheat builds stay
                # visible under "Not downloaded".
                if skip_zero:
                    info["sources"] = [s for s in info.get("sources", [])
                                       if (s.get("cheat_count") or 0) > 0]
                    if not info["sources"]:
                        return
                db.upsert_game(info, source="cheatslips")
                counter["n"] += 1
                # Save cheat .txt files in the same pass when we have a valid token.
                if save_content:
                    self._save_inline_content(info, out, downloaded, saved_files, db=db)
                if counter["n"] % 25 == 0:
                    print(f"  {counter['n']} games with cheats saved")

            try:
                scraper.scrape_all_streaming(
                    on_game,
                    entry_only=entry_only,
                    page_cb=page_cb,
                    game_cb=game_cb,
                    should_stop=self._stop_event.is_set,
                    skip_slugs=skip_slugs,
                )
                if self._stop_event.is_set():
                    print("Stopped by user.")
                if save_content:
                    print(f"Saved {saved_files['n']} cheat file(s) during the scrape.")
                # Make every build's cheat count match its actual .txt file on
                # disk (also fixes builds whose count came from HTML/API earlier).
                if not self._stop_event.is_set():
                    recount_cheats_from_disk(db, out, only_missing=False,
                                             should_stop=self._stop_event.is_set)
                print(f"Done. Database holds {db.count()} build(s).")
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Scrape failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("scrape_done",))

    # ------------------------------------------------------------- download
    def on_download_selected(self):
        if self._busy:
            return
        if not self.tree.selection():
            messagebox.showinfo("Download", "Select one or more rows in the table first.")
            return
        tids = self._selected_title_ids()
        if not tids:
            messagebox.showwarning("Download", "No valid title id in the selection.")
            return
        self._start_download(tids)

    def on_download_api(self):
        """Download via the official API ONLY (never the browser). Uses the
        selected rows if any, otherwise the whole database."""
        if self._busy:
            return
        tids = self._selected_title_ids() or None
        if tids is None:
            try:
                db = GameDatabase(Path(self.db_path.get()))
                n = len(db.all_title_ids())
                db.close()
            except Exception:
                n = 0
            if n == 0:
                messagebox.showinfo("Download (API only)", "Database is empty — run Scrape first.")
                return
            if not messagebox.askyesno(
                "Download (API only)",
                f"Download cheat files for all {n} game(s) via the official API only "
                f"(no browser)?\n\nAlready-downloaded builds are skipped.\n"
                f"If the API daily quota is hit, it stops — use 'Download Selected' with "
                f"the browser option for those."):
                return
        self._start_api_download(tids)

    def on_download_all(self):
        if self._busy:
            return
        try:
            db = GameDatabase(Path(self.db_path.get()))
            n = len(db.all_title_ids())
            db.close()
        except Exception:
            n = 0
        if n == 0:
            messagebox.showinfo("Build Full Dataset", "Database is empty - run Scrape first.")
            return
        if not messagebox.askyesno(
            "Build Full Dataset",
            f"Build a complete dataset for {n} game(s)?\nRuns in order:\n"
            "  1. Download all cheat files (API)\n"
            "  2. Fill names, region + versions (titledb / API)\n"
            "  3. Fix ID names\n"
            "  4. Fix 0-cheat entries\n\n"
            "Each step continues even if a previous one fails.\n"
            "Already-downloaded builds are skipped automatically.",
        ):
            return
        self._stop_event.clear()
        self._save_settings()
        self._set_busy(True)
        self.status_var.set("Building complete dataset...")
        cfg = {
            "email": self.email_var.get().strip() or None,
            "password": self.password_var.get() or None,
            "token": self.api_token_var.get().strip() or None,
            "output": self.dl_output.get(),
            "db_path": self.db_path.get(),
            "auto_reset": self.auto_reset_quota.get(),
            "browser": self._browser_kind(),
        }
        threading.Thread(target=self._download_everything_worker, args=(cfg,), daemon=True).start()

    def _download_everything_worker(self, cfg):
        """Full pipeline: download all -> fill names/region/versions -> fix id
        names -> fix 0-cheat. Each step is isolated so a failure (e.g. no token)
        doesn't stop the rest — maximises dataset completeness."""
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        stopped = self._stop_event.is_set
        try:
            db = GameDatabase(Path(cfg["db_path"]))
            api = CheatslipsAPI(token=cfg["token"])
            if not api.token and cfg["email"] and cfg["password"]:
                try:
                    print("Requesting API token...")
                    api.get_token(cfg["email"], cfg["password"])
                    print("Got API token.")
                except Exception as exc:
                    print(f"Could not get API token ({exc}).")
            token_ok = bool(api.token) and api.token_works()
            if not token_ok:
                print("WARNING: no valid API token — cheat *content* won't be downloaded, "
                      "but names/region/versions and the fixes still run.")
            try:
                # --- [1/4] Download all cheat files ---
                if not stopped():
                    print("\n=== [1/4] Download all cheat files ===")
                    try:
                        if token_ok:
                            tr = ProgressTracker("download")
                            def dprog(done, total):
                                tr.update(done, total)
                                self._log_queue.put(("progress", done, total,
                                    f"Downloading {done}/{total} ({tr.pct()}%) | {tr.rate_str('items')}"))
                            saved = api_download_from_db(api, db, Path(cfg["output"]),
                                                         title_ids=None, resume=True,
                                                         progress_cb=dprog, should_stop=stopped)
                            print(f"Downloaded {saved} new file(s).")
                            cleanup_invalid_cheat_entries(db, Path(cfg["output"]), should_stop=stopped)
                            # Fetch the rest via the browser when the API is limited.
                            if cfg.get("auto_reset") and not stopped():
                                pairs = missing_build_pairs(db, Path(cfg["output"]))
                                if pairs:
                                    extra = self._run_quota_reset_loop(
                                        api, db, Path(cfg["output"]), pairs, cfg)
                                    print(f"Browser download added {extra} more file(s).")
                        else:
                            print("Skipped (no valid token).")
                    except Exception as exc:
                        print(f"Download step failed: {exc}")

                # --- [2/4] Fill names, region + versions (+ recount) ---
                if not stopped():
                    print("\n=== [2/4] Fill names, region + versions ===")
                    try:
                        tr = ProgressTracker("fill")
                        def fprog(done, total):
                            tr.update(done, total)
                            self._log_queue.put(("progress", done, total,
                                f"Names/region {done}/{total} ({tr.pct()}%) | {tr.rate_str('items')}"))
                        fill_missing_names(db, api=api, progress_cb=fprog,
                                           should_stop=stopped, cache_dir=str(DATA_DIR),
                                           with_regions=True)
                        recount_cheats_from_disk(db, cfg["output"], only_missing=False,
                                                 should_stop=stopped)
                        scraper = CheatslipsMetadataScraper(delay=0.3, max_concurrent=4)
                        n1 = fill_versions_from_titledb(db, should_stop=stopped)
                        n2 = fill_missing_versions(api, scraper, db, should_stop=stopped) \
                            if not stopped() else 0
                        print(f"Versions filled: {n1} via titledb, {n2} via cheatslips.")
                    except Exception as exc:
                        print(f"Fill step failed: {exc}")

                # --- [3/4] Fix ID names ---
                if not stopped():
                    print("\n=== [3/4] Fix ID names ===")
                    try:
                        n = fix_title_id_names(db, should_stop=stopped)
                        n += remove_placeholder_builds(db)
                        print(f"Fixed {n} row(s).")
                    except Exception as exc:
                        print(f"Fix ID names step failed: {exc}")

                # --- [4/4] Fix 0-cheat entries ---
                if not stopped():
                    print("\n=== [4/4] Fix 0-cheat entries ===")
                    try:
                        tids = db.zero_cheat_title_ids()
                        if not tids:
                            print("No 0-cheat entries.")
                        else:
                            print(f"Refreshing {len(tids)} 0-cheat game(s) from the API...")
                            refresh_titles_from_api(api, db, tids, should_stop=stopped)
                            if token_ok and not stopped():
                                saved = api_download_from_db(api, db, Path(cfg["output"]),
                                                             title_ids=tids, resume=True,
                                                             should_stop=stopped)
                                print(f"0-cheat fix: {saved} new file(s).")
                                cleanup_invalid_cheat_entries(db, Path(cfg["output"]), should_stop=stopped)
                    except Exception as exc:
                        print(f"Fix 0-cheat step failed: {exc}")

                if stopped():
                    print("\nStopped by user.")
                print(f"\n=== Complete dataset build done. DB holds {db.count()} builds. ===")
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Download All failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("download_done",))

    def _run_quota_reset_loop(self, api, db, out, pairs, cfg) -> int:
        """Open a persistent logged-in browser and download `pairs`, resetting the
        API quota in the browser whenever it is hit. Returns files saved.

        Runs inside the worker thread (stdout already mirrored to the log).
        The Playwright session is opened and closed in the same worker thread
        because its objects are bound to the thread that created them.
        """
        if not pairs:
            return 0
        if not _PW_OK:
            print("Browser download needs Playwright. Install it with:\n"
                  "    pip install playwright\n    playwright install")
            return 0

        print(f"\n=== Browser download: {len(pairs)} build(s) still missing ===")
        print("A browser window will open. Log in once (solve the reCAPTCHA if "
              "asked); the download then continues automatically. With saved "
              "cookies the login should be automatic on later runs.")
        session = _pw_scrape.BrowserSession(
            email=cfg.get("email"),
            password=cfg.get("password"),
            log=print,
            headless=False,
            browser=cfg.get("browser", "builtin"),
            should_stop=self._stop_event.is_set,
        )
        try:
            session.start()
            if not session.ensure_login():
                print("Login was not completed — browser download aborted.")
                return 0

            def reset_cb():
                if self._stop_event.is_set():
                    return False
                return session.reset_quota()

            def browser_dl(slug, tid, bid, sid):
                if self._stop_event.is_set():
                    return None
                return session.download_build(slug, tid, bid, out, sid)

            def prog(done, total):
                self._log_queue.put(("progress", done, total,
                                     f"Browser download {done}/{total}"))

            return download_with_quota_reset(
                api, db, out, pairs,
                reset_cb=reset_cb,
                browser_download_cb=browser_dl,
                progress_cb=prog,
                should_stop=self._stop_event.is_set,
                log=print,
            )
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"Browser download loop failed: {exc}")
            return 0
        finally:
            session.close()

    def _start_download(self, title_ids):
        self._stop_event.clear()
        self._save_settings()
        self._set_busy(True)
        self.status_var.set("Connecting to the API...")
        # Read Tk variables here (main thread); never touch them from the worker.
        cfg = {
            "email": self.email_var.get().strip() or None,
            "password": self.password_var.get() or None,
            "token": self.api_token_var.get().strip() or None,
            "output": self.dl_output.get(),
            "db_path": self.db_path.get(),
            "auto_reset": self.auto_reset_quota.get(),
            "browser_fallback": True,   # on API quota, finish via the browser
            "browser": self._browser_kind(),
        }
        threading.Thread(
            target=self._download_worker, args=(title_ids, cfg), daemon=True
        ).start()

    def _start_api_download(self, title_ids):
        """Download via the official API only — forces the browser fallback off,
        regardless of the 'Download via browser when API is limited' checkbox."""
        self._stop_event.clear()
        self._save_settings()
        self._set_busy(True)
        self.status_var.set("Downloading via API...")
        cfg = {
            "email": self.email_var.get().strip() or None,
            "password": self.password_var.get() or None,
            "token": self.api_token_var.get().strip() or None,
            "output": self.dl_output.get(),
            "db_path": self.db_path.get(),
            "auto_reset": False,        # pure API — never open the browser
            "browser_fallback": False,  # …not even when the quota is hit
            "browser": "builtin",
        }
        threading.Thread(
            target=self._download_worker, args=(title_ids, cfg), daemon=True
        ).start()

    def _download_worker(self, title_ids, cfg: dict):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            api = CheatslipsAPI(token=cfg["token"])
            if not api.token:
                if cfg["email"] and cfg["password"]:
                    print("Requesting API token...")
                    api.get_token(cfg["email"], cfg["password"])
                    print("Got API token.")
                else:
                    raise RuntimeError("Enter your email + password, or an API token.")
            if not api.token_works():
                raise RuntimeError("API token is invalid - no cheat content returned.")

            db = GameDatabase(Path(cfg["db_path"]))
            try:
                out = Path(cfg["output"])
                if cfg.get("auto_reset"):
                    # Continuous reset+download cycle: try every missing build, reset
                    # the API quota in the browser whenever it is hit, and keep going.
                    pairs = missing_build_pairs(db, out)
                    if title_ids:
                        wanted = {t.upper() for t in title_ids}
                        pairs = [p for p in pairs if p[0].upper() in wanted]
                    if pairs:
                        saved = self._run_quota_reset_loop(api, db, out, pairs, cfg)
                        print(f"Download finished - {saved} new file(s).")
                    else:
                        print("Nothing left to download — database is complete.")
                else:
                    tracker = ProgressTracker("download")
                    def progress(done, total):
                        tracker.update(done, total)
                        msg = f"Downloaded {done}/{total} ({tracker.pct()}%) | {tracker.rate_str('items')} | ~{tracker.eta_str()} remaining"
                        self._log_queue.put(("progress", done, total, msg))

                    stats: dict = {}
                    saved = api_download_from_db(
                        api, db, out,
                        title_ids=title_ids,
                        resume=True,
                        progress_cb=progress,
                        should_stop=self._stop_event.is_set,
                        stats=stats,
                    )
                    print(f"Download finished - {saved} new file(s).")
                    # Delete any files that only contain a quota/placeholder message and
                    # reset their database entries so they are re-tried after the quota resets.
                    cleaned = cleanup_invalid_cheat_entries(
                        db, out, should_stop=self._stop_event.is_set)
                    print(f"Cleaned up {cleaned} invalid cheat entries.")
                    # When the API hit its daily limit, keep going with the browser
                    # (HTML) download for whatever is still missing — unless this is
                    # the dedicated "Download (API only)" button (browser_fallback off).
                    if (cfg.get("browser_fallback") and stats.get("quota")
                            and not self._stop_event.is_set()):
                        pairs = missing_build_pairs(db, out)
                        if title_ids:
                            wanted = {t.upper() for t in title_ids}
                            pairs = [p for p in pairs if p[0].upper() in wanted]
                        if pairs:
                            print(f"\nAPI limit reached — continuing with the browser "
                                  f"download for {len(pairs)} remaining build(s)...")
                            saved += self._run_quota_reset_loop(api, db, out, pairs, cfg)
                            print(f"Download finished - {saved} new file(s) total "
                                  f"(API + browser).")
                # Make every build's cheat count match its actual .txt on disk.
                if not self._stop_event.is_set():
                    recount_cheats_from_disk(db, out, only_missing=False,
                                             should_stop=self._stop_event.is_set)
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Download failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("download_done",))

    # ----------------------------------------------------------------- log
    def _drain_log(self):
        try:
            while True:
                msg = self._log_queue.get_nowait()
                if isinstance(msg, tuple):
                    self._handle_event(msg)
                    continue
                self._append_log(msg)
                self.status_var.set(msg)
        except queue.Empty:
            pass
        self.root.after(150, self._drain_log)

    def _handle_event(self, msg: tuple):
        kind = msg[0]
        if kind == "progress":
            done, total = msg[1], msg[2]
            label = msg[3] if len(msg) > 3 else None
            self.progress.config(maximum=max(total, 1), value=done)
            if label:
                self.status_var.set(label)
        elif kind == "status":
            self.status_var.set(msg[1])
        elif kind == "table_rows":
            # Async refresh_table result: (gen, prepared_rows, games_label, status)
            self._apply_refresh(msg[1], msg[2], msg[3], msg[4])
        elif kind == "check_file_done":
            # Async cheat-file check result: (reports, synced, output_dir)
            self._finish_check_cheat_file(msg[1], msg[2], msg[3])
        elif kind == "sd_export_done":
            self._finish_sd_export(msg[1], msg[2])
        elif kind == "zip_export_done":
            self._finish_zip_export(msg[1], msg[2], msg[3])
        elif kind == "import_db_done":
            self._finish_import_db(msg[1])
        elif kind == "devcat_done":
            self._finish_devcat(msg[1], msg[2])
        elif kind == "update_result":
            self._handle_update_result(msg[1], msg[2])
        elif kind == "update_error":
            self._handle_update_error(msg[1], msg[2])
        elif kind == "program_update_ready":
            self._launch_installer_and_quit(msg[1], msg[2])
        elif kind == "online_status":
            ok = bool(msg[1])
            if ok:
                self.online_status_lbl.config(text="● Online", foreground=theme()["ok"])
            else:
                self.online_status_lbl.config(text="● OFFLINE", foreground=theme()["error"])
            self._append_log(f"cheatslips.com is {'online' if ok else 'OFFLINE'}.")
        elif kind == "error":
            messagebox.showerror("Error", msg[1])
        elif kind == "scrape_done":
            self.scrape_btn.config(text="Scrape")
            self._set_busy(False)
            self._update_downloaded_cache_incremental()
            self.refresh_table()
            # Chain straight into the download if requested.
            if self.auto_download.get():
                self.status_var.set("Scraping done - starting download...")
                self.root.after(500, lambda: self._start_download(None))
        elif kind == "download_done":
            self._set_busy(False)
            self._update_downloaded_cache_incremental()
            self.refresh_table()
        elif kind == "refresh_done":
            self._set_busy(False)
            self.refresh_table(force_scan=True)
        elif kind == "everything_done":
            self.everything_btn.config(text="★ Scrape & Download Everything")
            self._set_busy(False)
            self._update_downloaded_cache_incremental()
            self.refresh_table()
            self.status_var.set("Scrape & Download Everything finished.")
        elif kind == "update_done":
            new_builds = msg[1] if len(msg) > 1 else 0
            self.update_btn.config(text="Update Recent")
            self._set_busy(False)
            self._update_downloaded_cache_incremental()
            self.refresh_table()
            if new_builds and self.auto_download.get() and not self._stop_event.is_set():
                self.status_var.set(f"{new_builds} new build(s) found - starting download...")
                self.root.after(500, lambda: self._start_download(None))
            else:
                self.status_var.set(f"Update done - {new_builds} new build(s) found.")

    def _append_log(self, msg: str):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")


def run_gui():
    root = tk.Tk()
    ScraperGUI(root)
    root.mainloop()


if __name__ == "__main__":
    run_gui()
