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

import i18n
from i18n import t
# Patch the Tk/ttk widget factories, menus, dialogs and messageboxes so every
# static text/label/title/message is auto-translated at build time. Must run
# BEFORE any widget is created (the active language is chosen in __init__).
i18n.install_tk_i18n()

from scraper import (
    APP_NAME,
    APP_VERSION,
    APP_AUTHOR,
    DEVCAT_CHEATS_ASSET,
    DEVCAT_DB_ASSET,
    DEVCAT_DATA_TAG,
    PROGRAM_SETUP_ASSET,
    PROGRAM_PORTABLE_ASSET,
    NRO_ASSET,
    NRO_SD_DIR,
    devcat_asset_url,
    download_file,
    download_switch_app,
    copy_nro_to_sd,
    fetch_github_release,
    find_release_asset,
    version_is_newer,
    CheatslipsAPI,
    CheatslipsMetadataScraper,
    GameDatabase,
    check_cheatslips_online,
    export_cheats_to_sd,
    export_cheats_to_zip,
    export_cheats_for_emulator,
    export_shared_db,
    EMULATOR_TARGETS,
    build_title_name_map,
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


def _installer_default_language() -> str:
    """Read the language the installer selected (default_lang.txt next to the
    executable/script), so a fresh install starts in the chosen language.
    Returns an i18n code, defaulting to English."""
    try:
        base = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
        for cand in (base / "default_lang.txt", DATA_DIR / "default_lang.txt"):
            if cand.exists():
                return i18n.normalize_lang(cand.read_text(encoding="utf-8").strip())
    except Exception:
        pass
    return "en"


class _TrVar(tk.StringVar):
    """A StringVar whose value is translated into the active language on set().

    Used for the status bar so plain ``set("Ready.")`` calls localise
    automatically. Pre-translated strings (already-formatted templates) pass
    through unchanged, since a translated string is not itself a catalogue key."""

    def set(self, value):
        super().set(i18n.t(value) if isinstance(value, str) else value)

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
    # Modern "slate" dark — deep neutral background, soft off-white text, one
    # calm blue accent. Tuned for long reading sessions and a pro, low-glare feel.
    "dark": {
        "bg":          "#14161b",  # app canvas
        "surface":     "#1d2026",  # cards, buttons, headings, labelframe body
        "hover":       "#2a2e37",  # hover / active
        "field":       "#0e1014",  # entry / combobox / text input background
        "fg":          "#e6e9ef",  # primary text
        "fg_muted":    "#8b93a1",  # secondary / subtle text
        "border":      "#2b3039",  # subtle separators / outlines
        "select_bg":   "#1f3d68",  # selected table row / text (muted blue)
        "select_fg":   "#ffffff",
        "accent":      "#4c9dff",  # focus ring, progressbar, links, primary CTA
        "accent_hover": "#66acff",
        "accent_press": "#3d86e6",
        "featured_bg": "#141d2e",  # accent-tinted panel for the DevCat section
        "featured_border": "#2f5da8",
        "tree_bg":     "#181b21",
        "tree_alt":    "#20242d",  # alternating table row
        "ok":          "#3fb950",  # green (downloaded / online)
        "warn":        "#e3a72f",  # amber (nameless / warning)
        "error":       "#f85149",  # red (missing / offline)
        "link":        "#4c9dff",
        "checking":    "#d0a030",
        "title":       "#f3f5f9",  # bold headings in the detail panel
        "heading_fg":  "#a7afbd",  # section (labelframe) headers
        "nonbase_bg":  "#382530",  # update/DLC row background tint
        "tooltip_bg":  "#2a2e37",
        "tooltip_fg":  "#e6e9ef",
        "log_bg":      "#0e1014",
        "log_fg":      "#c6ccd6",
        "accent_fg":   "#ffffff",  # text ON accent buttons
        "accent2":     "#a78bfa",  # soft violet secondary (harmonises with blue)
    },
    # Clean light — soft neutral canvas with white cards/controls, crisp borders
    # and a confident blue accent. Calm, high-contrast, professional.
    "light": {
        "bg":          "#eef0f3",  # soft gray canvas
        "surface":     "#ffffff",  # white cards, buttons, controls
        "hover":       "#e7ebf1",
        "field":       "#ffffff",
        "fg":          "#1b1f24",
        "fg_muted":    "#616b78",
        "border":      "#d4d9e0",
        "select_bg":   "#d8e5ff",
        "select_fg":   "#0f2544",
        "accent":      "#2563eb",
        "accent_hover": "#3b74ee",
        "accent_press": "#1d4fd0",
        "featured_bg": "#eef4ff",  # soft blue-tinted panel for the DevCat section
        "featured_border": "#bcd2f6",
        "tree_bg":     "#ffffff",
        "tree_alt":    "#f5f7fa",
        "ok":          "#1a8f3c",
        "warn":        "#b7791f",
        "error":       "#d1342b",
        "link":        "#2563eb",
        "checking":    "#b8860b",
        "title":       "#1b1f24",
        "heading_fg":  "#4b5563",
        "nonbase_bg":  "#fde8e8",
        "tooltip_bg":  "#20242c",  # dark tooltip on light UI (modern)
        "tooltip_fg":  "#f0f2f5",
        # A LIGHT console in the light theme — a black block looked out of place.
        "log_bg":      "#f3f5f8",
        "log_fg":      "#2b3440",
        "accent_fg":   "#ffffff",
        "accent2":     "#7c3aed",  # violet secondary, readable on white
    },
    # "Prisma (Holo-Glas)" — deep petrol-black signature theme with a teal-mint
    # primary accent, electric-violet secondary and gold highlights. Tk has no
    # real alpha/blur/gradients, so every translucent tone of the spec is
    # PRE-BLENDED onto its background:
    #   surface      = panel #0B141C + 7%  glass tint #3EE6D0  -> "glass"
    #   featured_bg  = panel #0B141C + 12% glass tint          -> hero glass
    #   border       = #FFFFFF @14% on #040A10                 -> hairline
    #   select_bg    = accent #2DE1C2 @18% on surface          -> active fill
    #   fg_muted     = #EAF7F3 @88% on panel                   -> secondary text
    #   nonbase_bg   = violet #7C5CFF @15% on tree_bg          -> DLC row tint
    "prisma": {
        "bg":          "#040a10",  # deep petrol-black canvas
        "surface":     "#0f2329",  # glass panels/cards (teal-tinted)
        "hover":       "#133a3b",  # hover = a touch more accent in the glass
        "field":       "#050d13",  # inputs sit slightly below the canvas
        "fg":          "#f0fbf8",  # cool white
        "fg_muted":    "#cfdcd9",
        "border":      "#272c31",  # 14% white hairline
        "select_bg":   "#144545",  # accent @18% fill for active rows
        "select_fg":   "#f0fbf8",
        "accent":      "#2de1c2",  # teal-mint (primary)
        "accent_hover": "#4fe9ce",
        "accent_press": "#1fc4a8",
        "featured_bg": "#112d32",  # hero card = stronger glass tint
        "featured_border": "#135750",  # glass border (#30E6C8 @~30%)
        "tree_bg":     "#0b141c",
        "tree_alt":    "#0e1b24",
        "ok":          "#3ee68f",
        "warn":        "#ffc24b",  # gold doubles as the highlight colour
        "error":       "#ff6b7a",
        "link":        "#2de1c2",
        "checking":    "#ffc24b",
        "title":       "#f0fbf8",
        "heading_fg":  "#b7cfc9",
        "nonbase_bg":  "#1c1f3e",  # electric-violet tint (secondary accent)
        "tooltip_bg":  "#0f2329",
        "tooltip_fg":  "#f0fbf8",
        "log_bg":      "#050d13",
        "log_fg":      "#bfd9d2",
        "accent_fg":   "#04211c",  # dark petrol on the bright accent — never white
        "accent2":     "#7c5cff",  # electric-violet secondary (landing page)
        # Buttons exakt wie auf der Switch-Version: sehr dunkles Panel-Glas
        # (#0B141C) mit dezenter Haarlinie; Hover in Akzent-Glas.
        "btn_bg":      "#0b141c",  # = kColItem der Switch-App
        "btn_border":  "#272c31",  # = kColHairline der Switch-App
        "btn_hover":   "#144545",  # = kColItemHover (Akzent 18%)
    },
}

# The palette currently in force. Read via theme() so module-level widgets
# (tooltips, dialogs) pick up the same colours the main window uses.
# "Prisma (Holo-Glas)" is the signature default — matching the Switch app.
_ACTIVE = {"name": "prisma"}


def theme() -> dict:
    """Return the active colour palette."""
    return THEMES.get(_ACTIVE["name"], THEMES["prisma"])


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
    """Default export archive name (matches the data-release asset)."""
    return "switch-cheats.zip"


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


def classify_cheat_line(s: str) -> str:
    """Classify one (stripped) cheat-file line for highlighting/validation.

    Returns "empty" | "head" | "master" | "code" | "error" | "comment".
    A valid Atmosphère code line is 1–4 words of exactly 8 hex digits each
    (the cheat VM's 128-bit max instruction). Lines that clearly TRY to be
    code but are malformed (7/9-digit words, stray characters, >4 words)
    come back as "error"; free text stays a harmless "comment"."""
    import re as _re
    if not s:
        return "empty"
    if s.startswith("[") and s.endswith("]"):
        return "head"
    if s.startswith("{") and s.endswith("}"):
        return "master"
    tokens = s.split()
    hex8 = sum(1 for t in tokens if _re.fullmatch(r"[0-9A-Fa-f]{8}", t))
    if hex8 == len(tokens):
        return "code" if 1 <= len(tokens) <= 4 else "error"
    # At least one proper opcode word, or the whole line is hex-ish gibberish
    # → the author meant this to be code; flag it instead of hiding it.
    if hex8 >= 1 or all(_re.fullmatch(r"[0-9A-Fa-f]+", t) for t in tokens):
        return "error"
    return "comment"


def highlight_cheat_text(txt: "tk.Text") -> int:
    """Apply Atmosphère-cheat syntax highlighting + validation to a Text widget.

    [Named cheat] / {Master cheat} headers get the accent, hex code lines are
    dimmed apart from their opcode, free text reads as a comment — and
    MALFORMED code lines are marked red. Returns the number of invalid lines.
    Tags are (re)configured here so a theme change refreshes correctly.
    """
    import re as _re
    t = theme()
    txt.tag_configure("cheat_head", foreground=t["accent"],
                      font=("Consolas", 10, "bold"))
    txt.tag_configure("cheat_master", foreground=t.get("warn", t["accent"]),
                      font=("Consolas", 10, "bold"))
    txt.tag_configure("cheat_op", foreground=t["accent"])
    txt.tag_configure("cheat_comment", foreground=t["fg_muted"])
    txt.tag_configure("cheat_error", foreground=t.get("error", "#ff6b7a"),
                      underline=True)
    for tag in ("cheat_head", "cheat_master", "cheat_op", "cheat_comment",
                "cheat_error"):
        txt.tag_remove(tag, "1.0", "end")
    errors = 0
    lines = txt.get("1.0", "end-1c").split("\n")
    for i, line in enumerate(lines, 1):
        kind = classify_cheat_line(line.strip())
        if kind == "empty":
            continue
        if kind == "head":
            txt.tag_add("cheat_head", f"{i}.0", f"{i}.end")
        elif kind == "master":
            txt.tag_add("cheat_master", f"{i}.0", f"{i}.end")
        elif kind == "code":
            # Code line: tint just the leading opcode word.
            m = _re.match(r"^(\s*)([0-9A-Fa-f]{8})", line)
            if m:
                a = f"{i}.{len(m.group(1))}"
                b = f"{i}.{len(m.group(1)) + 8}"
                txt.tag_add("cheat_op", a, b)
        elif kind == "error":
            txt.tag_add("cheat_error", f"{i}.0", f"{i}.end")
            errors += 1
        else:
            txt.tag_add("cheat_comment", f"{i}.0", f"{i}.end")
    return errors


class CheatEditorDialog:
    """View + edit a build's cheat codes with live [Title] highlighting.

    Opened by double-clicking a row. Saves back to BOTH the .txt file on disk
    and the database (cheat_count / cheat_names) via the on_save callback, which
    returns (ok: bool, message: str) so the dialog can report inline without
    closing — a real editor, not just a form.
    """

    def __init__(self, parent, *, title_id, build_id, name, version, credits,
                 content, downloaded, on_save):
        self._on_save = on_save
        self._tid0, self._bid0 = title_id, build_id
        th = theme()
        self.top = tk.Toplevel(parent)
        self.top.title(t("Cheat editor"))
        self.top.transient(parent)
        self.top.grab_set()
        self.top.configure(bg=th["bg"])
        self.top.minsize(560, 460)

        frm = ttk.Frame(self.top, padding=14)
        frm.pack(fill="both", expand=True)

        # ---- header: game name + identity line -------------------------------
        head = ttk.Frame(frm)
        head.pack(fill="x")
        ttk.Label(head, text=(name or t("Unnamed game")),
                  font=("Segoe UI Semibold", 13),
                  foreground=th["accent"]).pack(anchor="w")
        dl_txt = t("downloaded") if downloaded else t("not downloaded")
        self._ident = ttk.Label(
            head, foreground=th["fg_muted"], font=("Segoe UI", 9),
            text=f"{title_id}  ·  {build_id}"
                 + (f"  ·  v{version}" if version else "")
                 + f"  ·  {dl_txt}")
        self._ident.pack(anchor="w", pady=(2, 0))

        # ---- editable metadata (name / version) ------------------------------
        meta = ttk.Frame(frm)
        meta.pack(fill="x", pady=(10, 6))
        self.name_var = tk.StringVar(value=name or "")
        self.version_var = tk.StringVar(value=version or "")
        self.credits_var = tk.StringVar(value=credits or "")
        ttk.Label(meta, text=t("Name")).grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(meta, textvariable=self.name_var, width=34).grid(
            row=0, column=1, sticky="we", padx=(0, 12))
        ttk.Label(meta, text=t("Version")).grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Entry(meta, textvariable=self.version_var, width=12).grid(
            row=0, column=3, sticky="w")
        meta.columnconfigure(1, weight=1)

        # ---- code editor -----------------------------------------------------
        ttk.Label(frm, text=t("Cheat codes (Atmosphère format · [Name] / {Master} headers)"),
                  foreground=th["fg_muted"], font=("Segoe UI", 8)).pack(anchor="w")
        box = ttk.Frame(frm)
        box.pack(fill="both", expand=True, pady=(3, 0))
        self.code = tk.Text(box, width=64, height=18, wrap="none",
                            font=("Consolas", 10), undo=True,
                            bg=th["field"], fg=th["fg"], insertbackground=th["fg"],
                            selectbackground=th["select_bg"], selectforeground=th["select_fg"],
                            relief="flat", highlightthickness=1,
                            highlightbackground=th["border"], highlightcolor=th["accent"])
        vsb = ttk.Scrollbar(box, orient="vertical", command=self.code.yview)
        hsb = ttk.Scrollbar(box, orient="horizontal", command=self.code.xview)
        self.code.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.code.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="we")
        box.rowconfigure(0, weight=1)
        box.columnconfigure(0, weight=1)
        if content:
            self.code.insert("1.0", content)
        self.code.edit_reset()          # first content isn't an undo step
        self._err_count = highlight_cheat_text(self.code)

        # Re-highlight (debounced) as the user types.
        self._hl_after = None
        self.code.bind("<<Modified>>", self._on_modified)

        # Right-click menu: insert a new-cheat template, duplicate/delete the
        # cheat block under the cursor, and the standard clipboard trio.
        self._menu_line = 1
        self._code_menu = tk.Menu(self.code, tearoff=0,
                                  bg=th["surface"], fg=th["fg"],
                                  activebackground=th["hover"],
                                  activeforeground=th["fg"])
        self._code_menu.add_command(label=t("＋ Insert new cheat"),
                                    command=self._insert_template)
        self._code_menu.add_command(label=t("Duplicate this cheat"),
                                    command=lambda: self._block_op("dup"))
        self._code_menu.add_command(label=t("Delete this cheat"),
                                    command=lambda: self._block_op("del"))
        self._code_menu.add_separator()
        for lbl, ev in ((t("Cut"), "<<Cut>>"), (t("Copy"), "<<Copy>>"),
                        (t("Paste"), "<<Paste>>")):
            self._code_menu.add_command(
                label=lbl, command=lambda e=ev: self.code.event_generate(e))
        self.code.bind("<Button-3>", self._show_code_menu)

        # ---- footer: live count + status + buttons ---------------------------
        foot = ttk.Frame(frm)
        foot.pack(fill="x", pady=(10, 0))
        self.count_var = tk.StringVar()
        ttk.Label(foot, textvariable=self.count_var,
                  foreground=th["fg_muted"], font=("Segoe UI", 9)).pack(side="left")
        # Live validation verdict: warns about malformed code lines (red).
        self.err_var = tk.StringVar()
        ttk.Label(foot, textvariable=self.err_var,
                  foreground=th.get("error", "#ff6b7a"),
                  font=("Segoe UI", 9)).pack(side="left", padx=(10, 0))
        self.status = ttk.Label(foot, text="", foreground=th.get("ok", th["accent"]),
                                font=("Segoe UI", 9))
        self.status.pack(side="left", padx=(12, 0))
        ttk.Button(foot, text=t("Close"), command=self._close).pack(side="right")
        ttk.Button(foot, text=t("Save"), style="Accent.TButton",
                   command=self._save).pack(side="right", padx=(0, 6))
        ttk.Button(foot, text=t("Reload from disk"),
                   command=self._reload).pack(side="right", padx=(0, 6))
        newbtn = ttk.Button(foot, text="＋ " + t("New cheat"),
                            command=self._insert_template)
        newbtn.pack(side="right", padx=(0, 6))
        _Tooltip(newbtn, "Insert a ready-made [Name] + code-line scaffold at "
                         "the end — right-click any cheat to duplicate or "
                         "delete it.")

        self._reload_content = content or ""
        self._refresh_count()
        self.top.bind("<Control-s>", lambda _e: self._save())
        self.top.bind("<Escape>", lambda _e: self._close())
        self.top.protocol("WM_DELETE_WINDOW", self._close)
        _center_dialog(self.top, parent)

    # ---- template + per-cheat block operations ----------------------------
    def _show_code_menu(self, event):
        """Remember the clicked line, then pop the editor context menu."""
        try:
            self._menu_line = int(self.code.index(f"@{event.x},{event.y}").split(".")[0])
        except Exception:
            self._menu_line = 1
        try:
            self._code_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._code_menu.grab_release()

    def _insert_template(self):
        """Append a fresh [Name] + code-line scaffold and select the name so
        the user can type straight over it."""
        body = self.code.get("1.0", "end-1c")
        if body and not body.endswith("\n"):
            self.code.insert("end", "\n")
        if body.strip():
            self.code.insert("end", "\n")
        start = self.code.index("end-1c")
        line = int(start.split(".")[0])
        self.code.insert("end", "[New Cheat]\n04000000 00000000 00000000\n")
        # Select "New Cheat" inside the brackets for immediate renaming.
        self.code.tag_remove("sel", "1.0", "end")
        self.code.tag_add("sel", f"{line}.1", f"{line}.10")
        self.code.mark_set("insert", f"{line}.10")
        self.code.see("end")
        self.code.focus_set()
        self._rehighlight()

    def _cheat_block_at(self, line: int):
        """(first_line, last_line) of the cheat block containing *line* — from
        its [header]/{header} down to the line before the next header."""
        lines = self.code.get("1.0", "end-1c").split("\n")
        n = len(lines)
        line = max(1, min(line, n))

        def is_head(s):
            s = s.strip()
            return (s.startswith("[") and s.endswith("]")) or \
                   (s.startswith("{") and s.endswith("}"))

        start = None
        for i in range(line, 0, -1):
            if is_head(lines[i - 1]):
                start = i
                break
        if start is None:
            return None
        end = n
        for i in range(start + 1, n + 1):
            if is_head(lines[i - 1]):
                end = i - 1
                break
        # Trim trailing blank lines off the block.
        while end > start and not lines[end - 1].strip():
            end -= 1
        return start, end

    def _block_op(self, op: str):
        blk = self._cheat_block_at(self._menu_line)
        if blk is None:
            self.status.config(text=t("Click inside a cheat block first."),
                               foreground=theme().get("warn", "#ffc24b"))
            return
        start, end = blk
        text = self.code.get(f"{start}.0", f"{end}.end")
        if op == "del":
            # Also swallow ONE blank separator line after the block.
            after = self.code.get(f"{end + 1}.0", f"{end + 1}.end")
            self.code.delete(f"{start}.0",
                             f"{end + (2 if not after.strip() else 1)}.0")
        else:  # duplicate — rename the header so both stay distinguishable
            first, rest = (text.split("\n", 1) + [""])[:2]
            s = first.strip()
            first = s[0] + s[1:-1] + " (copy)" + s[-1]
            copy = first + ("\n" + rest if rest else "")
            self.code.insert(f"{end}.end", "\n\n" + copy)
        self._rehighlight()

    def _on_modified(self, _e=None):
        if not self.code.edit_modified():
            return
        self.code.edit_modified(False)
        if self._hl_after:
            try:
                self.top.after_cancel(self._hl_after)
            except Exception:
                pass
        self._hl_after = self.top.after(180, self._rehighlight)
        self.status.config(text="")

    def _rehighlight(self):
        self._hl_after = None
        self._err_count = highlight_cheat_text(self.code)
        self._refresh_count()

    def _refresh_count(self):
        import re as _re
        body = self.code.get("1.0", "end-1c")
        n = len(_re.findall(r"(?m)^\s*[\[{].+[\]}]\s*$", body))
        self.count_var.set(t("{n} cheat(s)", n=n))
        e = getattr(self, "_err_count", 0)
        self.err_var.set(t("⚠ {n} invalid code line(s)", n=e) if e else "")

    def _reload(self):
        self.code.delete("1.0", "end")
        self.code.insert("1.0", self._reload_content)
        self.code.edit_reset()
        self._err_count = highlight_cheat_text(self.code)
        self._refresh_count()
        self.status.config(text=t("Reloaded from disk."))

    def _save(self, close=False):
        # Run the validation on the CURRENT text (the debounce may not have
        # fired yet) and make broken code an explicit decision, not a surprise
        # on the console.
        self._err_count = highlight_cheat_text(self.code)
        self._refresh_count()
        if self._err_count and not messagebox.askyesno(
                t("Cheat editor"),
                t("{n} code line(s) are malformed (marked red) — Atmosphère "
                  "may reject this cheat file on the console.\n\nSave anyway?",
                  n=self._err_count),
                parent=self.top):
            return
        payload = {
            "title_id": self._tid0, "build_id": self._bid0,
            "name": self.name_var.get().strip(),
            "version": self.version_var.get().strip(),
            "credits": self.credits_var.get().strip(),
            "content": self.code.get("1.0", "end-1c").rstrip() + "\n",
        }
        ok, msg = self._on_save(payload)
        self.status.config(
            text=msg, foreground=theme().get("ok" if ok else "error", theme()["accent"]))
        if ok:
            self._reload_content = payload["content"]
            if close:
                self.top.destroy()

    def _close(self):
        self.top.destroy()


class InvalidLinesDialog:
    """Result list of the 'Find invalid code lines' repair scan.

    Non-modal, so the user can work through the list: double-click (or the
    button) opens the build in the cheat editor — the broken lines are already
    marked red there. After the editor closes the file is re-checked and a
    fixed file disappears from the list.
    """

    def __init__(self, parent, app, results):
        self.app = app
        th = theme()
        self.top = tk.Toplevel(parent)
        self.top.title(t("Find invalid code lines"))
        self.top.transient(parent)
        self.top.configure(bg=th["bg"])
        self.top.minsize(640, 380)

        frm = ttk.Frame(self.top, padding=12)
        frm.pack(fill="both", expand=True)
        self.head_var = tk.StringVar()
        ttk.Label(frm, textvariable=self.head_var,
                  font=("Segoe UI Semibold", 11),
                  foreground=th["accent"]).pack(anchor="w")
        ttk.Label(frm, text=t("Double-click a row to open it in the cheat "
                              "editor — the broken lines are marked red."),
                  foreground=th["fg_muted"], font=("Segoe UI", 9)).pack(
                      anchor="w", pady=(2, 8))

        cols = ("game", "tid", "bid", "count", "sample")
        box = ttk.Frame(frm)
        box.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(box, columns=cols, show="headings",
                                 selectmode="browse")
        for cid, head, width, anchor in (
                ("game", t("Game"), 200, "w"),
                ("tid", "Title ID", 130, "center"),
                ("bid", "Build ID", 130, "center"),
                ("count", t("⚠ Lines"), 60, "center"),
                ("sample", t("Example"), 190, "w")):
            self.tree.heading(cid, text=head)
            self.tree.column(cid, width=width, anchor=anchor,
                             stretch=(cid in ("game", "sample")))
        vsb = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._rows = {}
        for r in results:
            item = self.tree.insert("", "end", values=(
                r["name"] or t("Unnamed game"), r["tid"] or "?", r["bid"],
                r["count"], r["sample"]))
            self._rows[item] = r
        self._update_head()

        self.tree.bind("<Double-1>", self._open_selected)
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text=t("Close"),
                   command=self.top.destroy).pack(side="right")
        ttk.Button(btns, text=t("Open in editor"), style="Accent.TButton",
                   command=self._open_selected).pack(side="right", padx=(0, 6))
        self.top.bind("<Escape>", lambda _e: self.top.destroy())
        _center_dialog(self.top, parent)

    def _update_head(self):
        self.head_var.set(t("{n} file(s) with invalid code lines.",
                            n=len(self.tree.get_children())))

    def _open_selected(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        item = sel[0]
        r = self._rows.get(item)
        if not r:
            return
        dlg = self.app._open_cheat_editor_for(r["tid"], r["bid"],
                                              name=r["name"])
        try:
            self.top.wait_window(dlg.top)
        except Exception:
            pass
        # Re-check the file: fixed → drop the row; still broken → update count.
        try:
            p = self.app._cheat_file_path(r["tid"], r["bid"])
            bad = []
            if p and p.exists():
                bad = [ln for ln in p.read_text(
                           encoding="utf-8", errors="replace").splitlines()
                       if classify_cheat_line(ln.strip()) == "error"]
            if not bad:
                self.tree.delete(item)
                self._rows.pop(item, None)
                self._update_head()
            else:
                r["count"] = len(bad)
                r["sample"] = bad[0].strip()[:60]
                self.tree.item(item, values=(
                    r["name"] or t("Unnamed game"), r["tid"] or "?", r["bid"],
                    r["count"], r["sample"]))
        except Exception:
            pass


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
            extra = t(" (+{n} more)", n=len(roots) - 1) if len(roots) > 1 else ""
            self.valid_lbl.config(text=t("✓ Auto-detected SD card: {info}",
                                         info=f"{roots[0]}{extra}"),
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
                t("'{p}' does not look like a Switch SD card (no atmosphere/ or "
                  "switch/ folder).\n\nExport there anyway?", p=p), parent=self.top):
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


class ExportEmulatorDialog:
    """Modal dialog: export the database's cheats into the emulator 'load'
    layout  <TitleID>/<GameName>/cheats/<BuildID>.txt  — as a folder tree or a
    ZIP, optionally prefixed with a specific emulator's load path."""

    def __init__(self, parent, dest_var, selected_count, default_scope="all"):
        self.result = None
        self.dest_var = dest_var
        self.target_var = tk.StringVar(value="generic")
        self.astype_var = tk.StringVar(value="folder")   # folder | zip
        self.scope_var = tk.StringVar(
            value="selected" if (default_scope == "selected" and selected_count) else "all")
        self.selected_count = selected_count

        self.top = tk.Toplevel(parent)
        self.top.title("Export cheats for emulators")
        self.top.transient(parent)
        self.top.grab_set()
        self.top.resizable(False, False)
        self.top.configure(bg=theme()["bg"])
        frm = ttk.Frame(self.top, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Export every downloaded cheat into the emulator "
                            "\"load\" layout, named after the game.",
                  foreground=theme()["fg_muted"], font=("Segoe UI", 8)).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        # --- emulator target (adds its load / mods path prefix) ---
        ttk.Label(frm, text="Emulator:").grid(row=1, column=0, sticky="w")
        self._emu_ids = list(EMULATOR_TARGETS.keys())
        self.emu_combo = ttk.Combobox(
            frm, state="readonly", width=52,
            values=[t(EMULATOR_TARGETS[e][0]) for e in self._emu_ids])
        default_id = "generic" if "generic" in self._emu_ids else self._emu_ids[0]
        self.emu_combo.current(self._emu_ids.index(default_id))
        self.target_var.set(default_id)
        self.emu_combo.grid(row=2, column=0, columnspan=2, sticky="we", pady=(2, 8))
        self.emu_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_emu())

        # --- export as folder or ZIP ---
        ttk.Label(frm, text="Export as:").grid(row=3, column=0, sticky="w")
        af = ttk.Frame(frm)
        af.grid(row=4, column=0, columnspan=2, sticky="we", pady=(2, 8))
        ttk.Radiobutton(af, text="Folder", value="folder", variable=self.astype_var,
                        command=self._on_astype).pack(side="left")
        ttk.Radiobutton(af, text="ZIP file", value="zip", variable=self.astype_var,
                        command=self._on_astype).pack(side="left", padx=(12, 0))

        # --- destination ---
        self.dest_lbl = ttk.Label(frm, text="Destination folder:")
        self.dest_lbl.grid(row=5, column=0, sticky="w")
        drow = ttk.Frame(frm)
        drow.grid(row=6, column=0, columnspan=2, sticky="we", pady=(2, 8))
        ttk.Entry(drow, textvariable=self.dest_var, width=52).pack(
            side="left", fill="x", expand=True)
        ttk.Button(drow, text="Browse…", command=self._browse).pack(side="left", padx=(4, 0))

        # --- scope ---
        ttk.Label(frm, text="Scope:").grid(row=7, column=0, sticky="w")
        sf = ttk.Frame(frm)
        sf.grid(row=8, column=0, columnspan=2, sticky="we", pady=(2, 8))
        ttk.Radiobutton(sf, text="All games in the database", value="all",
                        variable=self.scope_var).pack(side="left")
        state = "normal" if selected_count else "disabled"
        ttk.Radiobutton(sf, text=t("Selected rows only ({n})", n=selected_count),
                        value="selected", variable=self.scope_var,
                        state=state).pack(side="left", padx=(12, 0))

        # --- structure preview ---
        self.preview = ttk.Label(frm, text="", foreground=theme()["accent"],
                                 font=("Consolas", 8))
        self.preview.grid(row=9, column=0, columnspan=2, sticky="w", pady=(2, 2))
        ttk.Label(frm, text="Folder names come from the database (special characters "
                            "removed); the Title ID is used when a game has no name.\n"
                            "Only files with real cheats are written; empty/stub files "
                            "are skipped.",
                  foreground=theme()["fg_muted"], font=("Segoe UI", 8)).grid(
            row=10, column=0, columnspan=2, sticky="w", pady=(0, 8))

        btns = ttk.Frame(frm)
        btns.grid(row=11, column=0, columnspan=2, sticky="e")
        ttk.Button(btns, text="Cancel", command=self.top.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="Export", command=self._on_export).pack(side="right")
        frm.columnconfigure(1, weight=1)
        self.top.bind("<Escape>", lambda _e: self.top.destroy())
        self._update_preview()
        _center_dialog(self.top, parent)

    def _on_astype(self):
        is_zip = self.astype_var.get() == "zip"
        self.dest_lbl.config(text="Save ZIP as:" if is_zip else "Destination folder:")
        # Keep the shown path in sync with the type so it's always obvious where
        # the result lands — a folder path, or a visible .zip file.
        p = self.dest_var.get().strip().rstrip("/\\")
        if is_zip and p and not p.lower().endswith(".zip"):
            self.dest_var.set(p + ".zip")
        elif not is_zip and p.lower().endswith(".zip"):
            self.dest_var.set(p[:-4])

    def _on_emu(self):
        idx = self.emu_combo.current()
        if idx >= 0:
            self.target_var.set(self._emu_ids[idx])
        self._update_preview()

    def _update_preview(self):
        prefix = EMULATOR_TARGETS.get(self.target_var.get(), ("", ""))[1]
        p = (prefix + "/") if prefix else ""
        try:
            self.preview.config(text=p + "<TitleID>/<GameName>/cheats/<BuildID>.txt")
        except Exception:
            pass

    def _browse(self):
        from tkinter import filedialog
        cur = self.dest_var.get().strip()
        if self.astype_var.get() == "zip":
            base = Path(cur).parent if cur else Path(str(DATA_DIR))
            initialdir = str(base if base.exists() else DATA_DIR)
            initialfile = (Path(cur).name if cur.lower().endswith(".zip")
                           else "switch-cheats-emulator.zip")
            path = filedialog.asksaveasfilename(
                title="Export cheats for emulators (ZIP)", parent=self.top,
                defaultextension=".zip", initialdir=initialdir, initialfile=initialfile,
                filetypes=[("ZIP archive", "*.zip"), ("All files", "*.*")])
        else:
            base = Path(cur) if cur else Path(str(DATA_DIR))
            initialdir = str(base if base.exists()
                             else (base.parent if base.parent.exists() else DATA_DIR))
            path = filedialog.askdirectory(
                title="Choose the destination folder", parent=self.top, initialdir=initialdir)
        if path:
            self.dest_var.set(path)

    def _on_export(self):
        p = self.dest_var.get().strip()
        is_zip = self.astype_var.get() == "zip"
        if not p:
            messagebox.showwarning("Export for Emulators",
                                   "Please choose a destination.", parent=self.top)
            return
        if is_zip and not p.lower().endswith(".zip"):
            p += ".zip"
            self.dest_var.set(p)
        self.result = {"target": self.target_var.get(), "as_zip": is_zip,
                       "dest": p, "scope": self.scope_var.get()}
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


def backup_database(db_path) -> "Path | None":
    """Safety net before destructive actions: snapshot *db_path* to <db>.bak,
    rotating the previous snapshot to <db>.bak2 (two generations). Uses sqlite's
    online backup API, so it is safe while the DB is open in WAL mode.
    Returns the backup path, or None when there was nothing to back up or the
    backup failed (the caller logs, but never blocks the action on it)."""
    import sqlite3 as _sq
    src = Path(db_path)
    if not src.exists() or src.stat().st_size == 0:
        return None
    bak1 = Path(str(src) + ".bak")
    bak2 = Path(str(src) + ".bak2")
    try:
        if bak1.exists():
            if bak2.exists():
                bak2.unlink()
            bak1.replace(bak2)
        s = _sq.connect(f"file:{src}?mode=ro", uri=True)
        d = _sq.connect(str(bak1))
        with d:
            s.backup(d)
        s.close(); d.close()
        return bak1
    except Exception:
        return None


def sha256_of_file(path, chunk=1 << 20) -> str:
    """Hex SHA-256 of a file, streamed (update downloads are hundreds of MB)."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


# ---- Windows notifications (no third-party deps) ---------------------------
# Shell_NotifyIcon with NIF_INFO shows a balloon that Windows 10/11 renders as
# a regular toast in the notification center — exactly what we want for "the
# long task finished while the window was in the background".

def _notifyicondata(hwnd, title="", msg=""):
    import ctypes
    from ctypes import wintypes

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon", wintypes.HICON),
            ("szTip", ctypes.c_wchar * 128),
            ("dwState", wintypes.DWORD),
            ("dwStateMask", wintypes.DWORD),
            ("szInfo", ctypes.c_wchar * 256),
            ("uTimeoutOrVersion", wintypes.UINT),
            ("szInfoTitle", ctypes.c_wchar * 64),
            ("dwInfoFlags", wintypes.DWORD),
        ]

    n = NOTIFYICONDATAW()
    n.cbSize = ctypes.sizeof(n)
    n.hWnd = hwnd
    n.uID = 0x5343  # 'SC'
    n.szTip = APP_NAME[:127]
    n.szInfo = (msg or "")[:255]
    n.szInfoTitle = (title or "")[:63]
    return n


def show_windows_toast(hwnd, title, msg) -> bool:
    """Show (or refresh) the toast; returns True when Windows accepted it."""
    try:
        import ctypes
        NIF_ICON, NIF_TIP, NIF_INFO = 0x2, 0x4, 0x10
        NIM_ADD, NIM_MODIFY = 0x0, 0x1
        n = _notifyicondata(hwnd, title, msg)
        n.uFlags = NIF_INFO | NIF_TIP | NIF_ICON
        n.hIcon = ctypes.windll.user32.LoadIconW(None, 32512)  # IDI_APPLICATION
        n.dwInfoFlags = 0x1  # NIIF_INFO
        n.uTimeoutOrVersion = 10000
        shell = ctypes.windll.shell32
        if not shell.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(n)):
            return bool(shell.Shell_NotifyIconW(NIM_ADD, ctypes.byref(n)))
        return True
    except Exception:
        return False


def remove_windows_toast(hwnd):
    """Drop the temporary tray icon again once the balloon has faded."""
    try:
        import ctypes
        NIM_DELETE = 0x2
        n = _notifyicondata(hwnd)
        ctypes.windll.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(n))
    except Exception:
        pass


def _render_release_notes(txt: "tk.Text", md: str, t: dict):
    """Render simple GitHub-flavoured markdown (headings, **bold**, bullets and
    `code`) into a Text widget with tags — far nicer than showing the raw
    ## / ** / - markup as plain text."""
    import re
    txt.tag_configure("h", foreground=t["accent"], font=("Segoe UI Semibold", 10),
                      spacing1=8, spacing3=3)
    txt.tag_configure("b", font=("Segoe UI", 9, "bold"))
    txt.tag_configure("code", font=("Consolas", 9), foreground=t["accent"])
    txt.tag_configure("li", lmargin1=14, lmargin2=30, spacing3=3)
    txt.tag_configure("p", foreground=t["fg"], spacing3=3)

    def inline(line: str, tags: tuple):
        i = 0
        for m in re.finditer(r"\*\*(.+?)\*\*|`([^`]+)`", line):
            if m.start() > i:
                txt.insert("end", line[i:m.start()], tags)
            if m.group(1) is not None:
                txt.insert("end", m.group(1), tags + ("b",))
            else:
                txt.insert("end", m.group(2), tags + ("code",))
            i = m.end()
        if i < len(line):
            txt.insert("end", line[i:], tags)

    for raw in (md or "").splitlines():
        s = raw.strip()
        if not s:
            txt.insert("end", "\n")
        elif s.startswith("#"):
            inline(s.lstrip("#").strip(), ("h",)); txt.insert("end", "\n")
        elif s[:2] in ("- ", "* ") or s.startswith("• "):
            body = s[2:].strip()
            txt.insert("end", "•  ", ("li", "p"))
            inline(body, ("li", "p")); txt.insert("end", "\n")
        else:
            inline(s, ("p",)); txt.insert("end", "\n")


class UpdateDialog:
    """Modal dialog summarising the available program / data updates, with the
    release notes rendered nicely instead of raw markdown.

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
        frm = ttk.Frame(self.top, padding=18)
        frm.pack(fill="both", expand=True)

        prog = info.get("program")
        cheats = info.get("cheats")
        db = info.get("db")
        something = bool(prog or cheats or db)
        frozen = getattr(sys, "frozen", False)

        # --- Header: prominent title + version transition ---
        ttk.Label(frm, text="Updates available" if something else "You are up to date",
                  foreground=(t["accent"] if something else t["ok"]),
                  font=("Segoe UI Semibold", 15)).pack(anchor="w")
        if prog and prog.get("newer_version"):
            sub = f"v{APP_VERSION}  →  v{prog['version']}"
        else:
            sub = f"Installed version: v{APP_VERSION}"
        ttk.Label(frm, text=sub, foreground=t["fg_muted"],
                  font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))
        ttk.Separator(frm).pack(fill="x", pady=13)

        # --- Program update ---
        if prog:
            head = (f"New version v{prog['version']}" if prog["newer_version"]
                    else "Current release re-uploaded (a fix, no version bump)")
            ttk.Label(frm, text=head, foreground=t["fg"],
                      font=("Segoe UI Semibold", 11), wraplength=470,
                      justify="left").pack(anchor="w")
            setup = prog.get("setup") or {}
            meta = []
            if setup.get("size"):
                meta.append(f"Installer {_fmt_size(setup['size'])}")
            if frozen:
                meta.append("installs & restarts automatically")
            if meta:
                ttk.Label(frm, text="   ·   ".join(meta), foreground=t["fg_muted"],
                          font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))

            notes = (prog.get("notes") or "").strip()
            if notes:
                ttk.Label(frm, text="What's new", foreground=t["fg_muted"],
                          font=("Segoe UI Semibold", 9)).pack(anchor="w", pady=(11, 4))
                nbox = ttk.Frame(frm)
                nbox.pack(fill="both", expand=True)
                txt = tk.Text(nbox, height=9, width=62, wrap="word", relief="flat",
                              bg=t["field"], fg=t["fg"], padx=12, pady=10,
                              highlightthickness=1, highlightbackground=t["border"],
                              highlightcolor=t["border"], cursor="arrow",
                              font=("Segoe UI", 9))
                sb = ttk.Scrollbar(nbox, command=txt.yview)
                txt.configure(yscrollcommand=sb.set)
                txt.pack(side="left", fill="both", expand=True)
                sb.pack(side="right", fill="y")
                _render_release_notes(txt, notes, t)
                txt.config(state="disabled")

            btn_text = "Update & Restart" if frozen else "Open download page"
            ttk.Button(frm, text=btn_text, style="Accent.TButton",
                       command=self._on_program).pack(anchor="e", pady=(13, 0))

        # --- Data update ---
        if cheats or db:
            if prog:
                ttk.Separator(frm).pack(fill="x", pady=13)
            ttk.Label(frm, text="Cheat data (from DevCatSKZ)", foreground=t["fg"],
                      font=("Segoe UI Semibold", 11)).pack(anchor="w")
            bits = []
            if db:
                bits.append(f"database {_fmt_size(db.get('size'))}")
            if cheats:
                bits.append(f"cheats {_fmt_size(cheats.get('size'))}")
            ttk.Label(frm, text="Newer " + " + ".join(bits) + " available — "
                      "merged into your database (nothing is removed).",
                      foreground=t["fg_muted"], font=("Segoe UI", 9),
                      wraplength=470, justify="left").pack(anchor="w", pady=(3, 0))
            ttk.Button(frm, text="Download data update",
                       command=self._on_data).pack(anchor="e", pady=(11, 0))

        if not something:
            ttk.Label(frm, text="Program, cheats and database are all current.",
                      foreground=t["fg_muted"]).pack(anchor="w")

        # --- Footer ---
        ttk.Separator(frm).pack(fill="x", pady=(15, 11))
        foot = ttk.Frame(frm)
        foot.pack(fill="x")
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


class UpdateProgressDialog:
    """Modal, non-closable progress window shown for the whole update so the user
    always sees what is happening (downloading, then installing)."""

    def __init__(self, parent, on_cancel=None):
        t = theme()
        self.top = tk.Toplevel(parent)
        self.top.title("Updating")
        self.top.transient(parent)
        self.top.resizable(False, False)
        self.top.configure(bg=t["bg"])
        self.top.protocol("WM_DELETE_WINDOW", lambda: None)  # can't be closed
        frm = ttk.Frame(self.top, padding=18)
        frm.pack(fill="both", expand=True)
        self.phase = ttk.Label(frm, text="Preparing update…", font=("Segoe UI", 11, "bold"))
        self.phase.pack(anchor="w")
        self.bar = ttk.Progressbar(frm, length=400, mode="determinate", maximum=100)
        self.bar.pack(fill="x", pady=(12, 6))
        self.detail = ttk.Label(frm, text="", foreground=t["fg_muted"], font=("Segoe UI", 9))
        self.detail.pack(anchor="w")
        self.cancel_btn = None
        if on_cancel:
            self.cancel_btn = ttk.Button(frm, text="Cancel", command=on_cancel)
            self.cancel_btn.pack(anchor="e", pady=(12, 0))
        try:
            self.top.grab_set()
        except Exception:
            pass
        _center_dialog(self.top, parent)

    def disable_cancel(self):
        try:
            if self.cancel_btn:
                self.cancel_btn.config(state="disabled")
        except Exception:
            pass

    def set_phase(self, text):
        try:
            self.phase.config(text=text)
        except Exception:
            pass

    def set_progress(self, done, total, detail=""):
        try:
            self.bar.stop()
            self.bar.config(mode="determinate", value=(int(done * 100 / total) if total else 0))
            if detail:
                self.detail.config(text=detail)
        except Exception:
            pass

    def busy(self, phase=None, detail=""):
        try:
            if phase:
                self.phase.config(text=phase)
            if detail:
                self.detail.config(text=detail)
            self.bar.config(mode="indeterminate"); self.bar.start(14)
            self.disable_cancel()  # past the point where cancelling is safe
        except Exception:
            pass

    def close(self):
        try:
            self.bar.stop()
        except Exception:
            pass
        try:
            self.top.grab_release(); self.top.destroy()
        except Exception:
            pass


class WelcomeDialog:
    """First-run greeting shown when the database is missing or empty.

    One friendly choice instead of an empty table: pull the complete, always
    current DevCatSKZ dataset with a single click (the same action as the
    ★ Download Complete card), or start empty and scrape yourself.
    """

    def __init__(self, parent, app):
        self.app = app
        t_theme = theme()
        self.top = tk.Toplevel(parent)
        self.top.title("Welcome")
        self.top.transient(parent)
        self.top.grab_set()
        self.top.resizable(False, False)
        self.top.configure(bg=t_theme["bg"])
        frm = ttk.Frame(self.top, padding=22)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="👋  " + t("Welcome!"),
                  foreground=t_theme["accent"],
                  font=("Segoe UI Semibold", 16)).pack(anchor="w")
        ttk.Label(frm, text="Get started in one click",
                  foreground=t_theme["fg"], font=("Segoe UI Semibold", 11)).pack(
                      anchor="w", pady=(10, 2))
        ttk.Label(
            frm,
            text="Your database is still empty. Load the complete, "
                 "continuously-updated cheat database from DevCatSKZ — "
                 "every game, every cheat, ready to browse. You can also "
                 "start empty and scrape everything yourself later.",
            foreground=t_theme["fg_muted"], font=("Segoe UI", 10),
            wraplength=430, justify="left").pack(anchor="w")
        ttk.Label(
            frm,
            text="Tip: the ★ card at the top does the same any time.",
            foreground=t_theme["fg_muted"], font=("Segoe UI", 8)).pack(
                anchor="w", pady=(8, 0))

        ttk.Separator(frm).pack(fill="x", pady=14)
        row = ttk.Frame(frm)
        row.pack(fill="x")
        ttk.Button(row, text="Start empty",
                   command=self._close).pack(side="left")
        ttk.Button(row, text="★  " + t("Download complete database (~25 MB)"),
                   style="Accent.TButton",
                   command=self._download).pack(side="right")
        self.top.bind("<Escape>", lambda _e: self._close())
        self.top.protocol("WM_DELETE_WINDOW", self._close)
        _center_dialog(self.top, parent)

    def _close(self):
        self.top.destroy()

    def _download(self):
        self.top.destroy()
        self.app.on_devcat_complete()


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
        self.status_var = _TrVar(value="Ready.")
        self.total_games_var = tk.StringVar(value=t("{n} games", n=0))
        self.search_var = tk.StringVar()
        self.not_downloaded_only = tk.BooleanVar(value=False)
        self.names_missing = tk.BooleanVar(value=False)
        self.nonbase_only = tk.BooleanVar(value=False)
        self.hide_placeholder_builds = tk.BooleanVar(value=True)
        # Quick-filter chips (Library): only builds that actually have cheats,
        # only builds still missing a cover image, and only ⭐ favorites.
        self.has_cheats_only = tk.BooleanVar(value=False)
        self.missing_cover_only = tk.BooleanVar(value=False)
        self.favorites_only = tk.BooleanVar(value=False)
        # Extend the search into the cheat NAMES ("inf health" → every game
        # that has such a cheat).
        self.search_in_cheats = tk.BooleanVar(value=False)
        # Library power: hidden table columns + saved filter presets (persisted).
        self._hidden_columns: set = set()
        self._filter_presets: dict = {}
        # ⭐ favourite games (title_ids, persisted in settings.json so they
        # survive data updates and full DB replaces).
        self._favorites: set = set()
        self.auto_scan_downloaded = tk.BooleanVar(value=False)
        # Two independent scrape controls (decoupled):
        #  - full catalog: discover over /games (ALL games) instead of the fast
        #    /entry "latest cheats" feed. Default OFF = fast /entry feed; both
        #    find the same cheat-having builds, full catalog is just much slower.
        #  - skip 0-cheat: drop builds with 0 cheats during scrape. Default OFF so
        #    0-cheat builds stay in the DB and are visible under "Not downloaded".
        self.scrape_full_catalog = tk.BooleanVar(value=False)
        self.scrape_skip_zero = tk.BooleanVar(value=False)
        self.auto_download = tk.BooleanVar(value=True)
        self.rescan_all = tk.BooleanVar(value=False)
        # Optional Phase-B browser fallback: the API pass ALWAYS resets the quota
        # in the browser when the limit is hit; with this on it ALSO downloads via
        # the logged-in browser the codes that exist only on the website (not via
        # the API). Off by default — most builds come from the API + resets.
        self.browser_fallback = tk.BooleanVar(value=False)
        self.browser_choice = tk.StringVar(value="Built-in")
        self.update_pages = tk.IntVar(value=5)
        # Check whether cheatslips.com is reachable on every program start.
        self.online_check_startup = tk.BooleanVar(value=True)
        # When ON, a DevCatSKZ download also fetches the cover images afterwards.
        # Off by default — covers are not part of the archive and cost extra time.
        self.devcat_covers = tk.BooleanVar(value=False)
        # "Download Switch App": when ON the freshly downloaded .nro is copied
        # straight onto a detected Switch SD card (like the cheats SD export).
        # Off by default — plugging in the SD card is the deliberate choice.
        self.nroapp_copy_sd = tk.BooleanVar(value=False)
        # Check GitHub for a newer program build / data package at every start.
        self.update_check_startup = tk.BooleanVar(value=True)
        # Auto-install a found program update at startup (no dialog, no clicks) —
        # only ever done silently when the app folder is writable (per-user install
        # or portable), so it never triggers a UAC prompt.
        self.auto_update = tk.BooleanVar(value=True)
        # Keep the cheat DATA current: silently check the DevCatSKZ data release
        # at startup and merge a newer database automatically (like the program
        # auto-update, but for the cheats). Off by default — opt in on Settings.
        self.keep_data_updated = tk.BooleanVar(value=False)
        # One-time first-run greeting (persisted in settings.json).
        self._welcome_shown = False
        # One-time nudge for legacy admin (Program Files) installs to switch to
        # the no-UAC per-user installer.
        self._migration_hint_shown = False
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
        self.show_images = tk.BooleanVar(value=False)
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
        self.theme_name = "prisma"

        # Language: default to the installer's choice (default_lang.txt); a saved
        # "language" in settings.json (read in _load_settings) overrides it. The
        # active language must be set BEFORE any widget is built so the Tk
        # auto-translation hook picks it up at creation time.
        self.language = i18n.set_language(_installer_default_language())

        self._loaded_geometry = False
        self._saved_window_state = None
        self._load_settings()
        # Seed the updater's first-run baseline as early as possible, so the
        # "install date" anchor reflects the true first program start.
        self._update_state = self._load_update_state()

        _ACTIVE["name"] = self.theme_name
        self._style = ttk.Style(self.root)
        self._all_menus = []          # tk.Menu widgets to recolour on theme change
        self._apply_theme(self.theme_name)

        self._compose_ui()
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
            # Open at a comfortable size, centered on the screen — this becomes the
            # "restore" size once the (first-run) maximized window is un-maximized.
            win_w = min(max(toolbar_w, 1400), avail_w)
            win_h = min(940, avail_h)
            pos_x = max(0, (screen_w - win_w) // 2)
            pos_y = max(0, (screen_h - win_h) // 2 - 20)
            self.root.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
            # First launch: start maximized (full screen) for the best first look.
            try:
                self.root.state("zoomed")
            except Exception:
                pass
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
            # Restore a previously maximized window.
            if self._saved_window_state == "zoomed":
                try:
                    self.root.state("zoomed")
                except Exception:
                    pass

        self._install_window_controls()

        self.root.after(150, self._drain_log)
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.refresh_table()
        self._append_log(f"{APP_NAME} v{APP_VERSION} — by {APP_AUTHOR}")
        # Check whether cheatslips.com is reachable once at startup (optional,
        # toggle 'check at startup'); runs in a background thread.
        if self.online_check_startup.get():
            self.root.after(800, self.on_check_online)
        # First run with an empty database → friendly one-click onboarding.
        self.root.after(900, self._maybe_show_welcome)
        # Legacy admin install → one-time offer to switch to the no-UAC version.
        self.root.after(1100, self._maybe_show_migration_hint)
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
        self.theme_name = _theme if _theme in THEMES else "prisma"
        if data.get("language"):
            self.language = i18n.set_language(data["language"])
        self.show_images.set(bool(data.get("show_images", False)))
        self.show_description.set(bool(data.get("show_description", False)))
        self.cache_covers.set(bool(data.get("cache_covers", True)))
        self.hide_placeholder_builds.set(bool(data.get("hide_placeholder_builds", True)))
        self._hidden_columns = set(data.get("hidden_columns", []) or [])
        self._filter_presets = dict(data.get("filter_presets", {}) or {})
        self._favorites = {str(f).upper() for f in data.get("favorites", []) or []}
        self.auto_scan_downloaded.set(bool(data.get("auto_scan_downloaded", False)))
        self.browser_fallback.set(bool(data.get("browser_fallback", False)))
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
            "scrape_full_catalog", (not legacy) if legacy is not None else False)))
        self.scrape_skip_zero.set(bool(data.get(
            "scrape_skip_zero", legacy if legacy is not None else False)))
        self.online_check_startup.set(bool(data.get("online_check_startup", True)))
        self.devcat_covers.set(bool(data.get("devcat_covers", False)))
        self.nroapp_copy_sd.set(bool(data.get("nroapp_copy_sd", False)))
        self.update_check_startup.set(bool(data.get("update_check_startup", True)))
        self.auto_update.set(bool(data.get("auto_update", True)))
        self.keep_data_updated.set(bool(data.get("keep_data_updated", False)))
        self._welcome_shown = bool(data.get("welcome_shown", False))
        self._migration_hint_shown = bool(data.get("migration_hint_shown", False))
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
        self._saved_window_state = data.get("window_state")

    def _save_settings(self):
        remember = self.remember_pw.get()
        data = {
            "email": self.email_var.get().strip(),
            "api_token": self.api_token_var.get().strip(),
            "password": self.password_var.get() if remember else "",
            "remember_pw": remember,
            "theme": self.theme_name,
            "language": self.language,
            "show_images": self.show_images.get(),
            "show_description": self.show_description.get(),
            "cache_covers": self.cache_covers.get(),
            "hide_placeholder_builds": self.hide_placeholder_builds.get(),
            "hidden_columns": sorted(self._hidden_columns),
            "filter_presets": self._filter_presets,
            "favorites": sorted(self._favorites),
            "auto_scan_downloaded": self.auto_scan_downloaded.get(),
            "browser_fallback": self.browser_fallback.get(),
            "browser_choice": self.browser_choice.get(),
            "scrape_full_catalog": self.scrape_full_catalog.get(),
            "scrape_skip_zero": self.scrape_skip_zero.get(),
            "online_check_startup": self.online_check_startup.get(),
            "devcat_covers": self.devcat_covers.get(),
            "nroapp_copy_sd": self.nroapp_copy_sd.get(),
            "update_check_startup": self.update_check_startup.get(),
            "auto_update": self.auto_update.get(),
            "keep_data_updated": self.keep_data_updated.get(),
            "welcome_shown": getattr(self, "_welcome_shown", False),
            "migration_hint_shown": getattr(self, "_migration_hint_shown", False),
            "sd_export_root": self.sd_export_root.get(),
            "sd_export_mode": self.sd_export_mode.get(),
            "export_zip_path": self.export_zip_path.get(),
            "output": self.dl_output.get(),
            "db_path": self.db_path.get(),
        }
        try:
            data["geometry"] = self.root.geometry()
            data["window_state"] = self.root.state()   # "zoomed" (maximized) or "normal"
        except Exception:
            pass
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    # --------------------------------------------------- first-run welcome
    def _db_build_count(self) -> int:
        """Number of builds in the current DB (0 when missing/unreadable)."""
        try:
            p = Path(self.db_path.get())
            if not p.exists() or p.stat().st_size == 0:
                return 0
            import sqlite3 as _sq
            con = _sq.connect(f"file:{p}?mode=ro", uri=True)
            n = con.execute("SELECT COUNT(*) FROM builds").fetchone()[0]
            con.close()
            return int(n)
        except Exception:
            return 0

    def _dashboard_stats(self, output: str = None, fast: bool = False) -> dict:
        """Snapshot of library numbers for the Home dashboard. Read-only, quick;
        safe to call from a worker thread (opens its own RO connection).
        *output* is a main-thread snapshot of the output folder.

        ``fast=True`` uses the cached downloaded-build set (instant, no disk
        scan) so the dashboard can paint immediately; a follow-up call with
        ``fast=False`` reconciles against disk in the background."""
        import sqlite3 as _sq
        out = {"games": 0, "builds": 0, "cheats": 0, "with_cheats": 0,
               "downloaded": 0, "db_size": 0, "last_data": None, "recent": []}
        p = Path(self.db_path.get())
        bids = []
        try:
            out["db_size"] = p.stat().st_size
        except Exception:
            pass
        if p.exists() and p.stat().st_size:
            try:
                con = _sq.connect(f"file:{p}?mode=ro", uri=True)
                out["builds"] = con.execute("SELECT COUNT(*) FROM builds").fetchone()[0]
                out["cheats"] = con.execute(
                    "SELECT COALESCE(SUM(cheat_count),0) FROM builds").fetchone()[0]
                out["with_cheats"] = con.execute(
                    "SELECT COUNT(*) FROM builds WHERE cheat_count>0").fetchone()[0]
                out["games"] = con.execute(
                    "SELECT COUNT(DISTINCT substr(title_id,1,13)||'000') FROM builds"
                ).fetchone()[0]
                # Row-wise list, NOT a set: the same build_id can belong to
                # several title_ids (5307 rows ↔ ~5033 distinct bids) and the
                # percentage must match the table, which counts rows.
                bids = [r[0] for r in con.execute(
                    "SELECT UPPER(build_id) FROM builds WHERE build_id IS NOT NULL")]
                out["recent"] = con.execute(
                    "SELECT game_title, version, title_id, build_id, cheat_count "
                    "FROM builds WHERE game_title IS NOT NULL AND game_title<>'' "
                    "AND last_updated IS NOT NULL "
                    "ORDER BY last_updated DESC LIMIT 8").fetchall()
                con.close()
            except Exception:
                pass
        # "downloaded" must agree with the table. fast=True reads the cached set
        # (instant, for the first paint); otherwise a LIVE disk scan (~5000
        # files, well under a second in a worker thread) reconciles against disk
        # and refreshes the cache.
        if fast:
            on_disk = self._load_downloaded_cache(output)
        else:
            try:
                on_disk = scan_downloaded_build_ids(output or self.dl_output.get())
                self._save_downloaded_cache(on_disk, output)   # keep the cache fresh
            except Exception:
                on_disk = self._load_downloaded_cache(output)
        disk = {b.upper() for b in on_disk}
        out["downloaded"] = sum(1 for b in bids if b in disk) if bids \
            else len(disk)
        st = getattr(self, "_update_state", {}) or {}
        out["last_data"] = st.get("data_db_baseline") or st.get("data_cheats_baseline")
        return out

    def _maybe_show_welcome(self):
        """First start with an empty database → offer the one-click complete
        download instead of greeting the user with an empty table. Shown once."""
        if self._welcome_shown or self._busy:
            return
        self._welcome_shown = True
        self._save_settings()
        if self._db_build_count() > 0:
            return   # existing data — nothing to onboard
        WelcomeDialog(self.root, self)

    def _maybe_show_migration_hint(self):
        """Legacy admin installs (under Program Files, app folder not writable)
        need a UAC prompt for every update. Offer — once — to switch to the
        current per-user installer, which updates silently forever after."""
        if getattr(self, "_migration_hint_shown", False):
            return
        if not getattr(sys, "frozen", False) or self._app_dir_writable():
            return   # from source, portable, or already a per-user install
        self._migration_hint_shown = True
        self._save_settings()
        if messagebox.askyesno(
            t("Switch to the no-admin version"),
            t("This copy is installed under Program Files, so every update needs "
              "a Windows admin prompt (UAC).\n\nThe current installer sets the "
              "app up just for you — then updates install silently, with no admin "
              "prompt ever again.\n\nDownload and run the new installer now?"),
                parent=self.root):
            self._download_and_run_installer()

    def _download_and_run_installer(self):
        if self._busy:
            return
        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set(t("Downloading the installer…"))
        threading.Thread(target=self._installer_dl_worker, daemon=True).start()

    def _installer_dl_worker(self):
        import tempfile
        try:
            rel = fetch_github_release(tag=None)
            asset = find_release_asset(rel, PROGRAM_SETUP_ASSET)
            if not asset or not asset.get("url"):
                raise RuntimeError("installer asset not found in the latest release")
            dest = Path(tempfile.gettempdir()) / PROGRAM_SETUP_ASSET
            download_file(
                asset["url"], dest,
                progress_cb=lambda d, tot: self._log_queue.put(
                    ("progress", d, max(tot, 1), f"Installer: {d // 1024:,} KB")),
                should_stop=self._stop_event.is_set)
            digest = (asset.get("digest") or "").strip().lower()
            if digest.startswith("sha256:") and \
                    sha256_of_file(dest) != digest.split(":", 1)[1]:
                raise RuntimeError("SHA-256 mismatch — the download is corrupted")
            self._log_queue.put(("run_installer", str(dest)))
        except Exception as exc:
            self._log_queue.put(("error", f"Installer download failed:\n{exc}"))
            self._log_queue.put(("download_done",))

    # ------------------------------------------------------ safety backups
    def _backup_db(self, reason: str):
        """Rotating snapshot (<db>.bak, previous → .bak2) before an action that
        can destroy data. Never blocks the action — a failed backup is logged."""
        bak = backup_database(self.db_path.get())
        if bak:
            self._append_log(t("Safety backup before {reason}: {name}",
                               reason=reason, name=bak.name))
        return bak

    # ------------------------------------------------ Windows notifications
    def _toast(self, title: str, message: str):
        """Windows notification for a finished long task — only when the window
        is NOT in the foreground (in focus, the in-app status is enough)."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            user = ctypes.windll.user32
            hwnd = user.GetAncestor(self.root.winfo_id(), 2)   # GA_ROOT
            if user.GetForegroundWindow() == hwnd:
                return
            if show_windows_toast(hwnd, title, message):
                # Drop the temporary tray icon once the balloon has faded.
                self.root.after(12000, lambda: remove_windows_toast(hwnd))
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
        # Subtle zebra striping on alternating rows (background only, so it never
        # clashes with the done/nameless text colours).
        self.tree.tag_configure("stripe", background=t.get("tree_alt", t["tree_bg"]))
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
            name = "prisma"
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

        HEAD = t.get("heading_fg", MUT)
        BASE = ("Segoe UI", 9)
        SEMI = ("Segoe UI Semibold", 9)
        st.configure(".", background=BG, foreground=FG, fieldbackground=FIELD,
                     bordercolor=BORDER, darkcolor=SURF, lightcolor=SURF,
                     troughcolor=SURF, arrowcolor=MUT, insertcolor=FG,
                     focuscolor=ACCENT, selectbackground=SEL, selectforeground=SELFG,
                     font=BASE)
        st.configure("TFrame", background=BG)
        st.configure("TLabel", background=BG, foreground=FG, font=BASE)
        # Sections read as clean cards with a hairline border + quiet header label.
        st.configure("TLabelframe", background=BG, bordercolor=BORDER,
                     relief="solid", borderwidth=1)
        st.configure("TLabelframe.Label", background=BG, foreground=HEAD, font=SEMI)
        # Buttons — flat, roomy, with an accent outline on hover/focus. Themes
        # can tint them separately from the panels (Prisma: teal glass chips).
        BTN_BG = t.get("btn_bg", SURF)
        BTN_BORDER = t.get("btn_border", BORDER)
        BTN_HOV = t.get("btn_hover", HOV)
        st.configure("TButton", background=BTN_BG, foreground=FG, bordercolor=BTN_BORDER,
                     focuscolor=BTN_BG, relief="flat", padding=(11, 5), anchor="center")
        # Disabled buttons keep their glass fill (only the text is dimmed);
        # with "disabled -> BG" they vanished into the canvas while a
        # process was running (Prisma theme).
        st.map("TButton",
               background=[("pressed", BTN_HOV), ("active", BTN_HOV), ("disabled", BTN_BG)],
               foreground=[("disabled", MUT)],
               bordercolor=[("active", ACCENT), ("focus", ACCENT)])
        st.configure("TMenubutton", background=BTN_BG, foreground=FG, bordercolor=BTN_BORDER,
                     arrowcolor=MUT, relief="flat", padding=(11, 5))
        st.map("TMenubutton", background=[("active", BTN_HOV)], bordercolor=[("active", ACCENT)])
        st.configure("TCheckbutton", background=BG, foreground=FG, focuscolor=BG,
                     indicatorbackground=FIELD, indicatorforeground="#ffffff", bordercolor=BORDER)
        st.map("TCheckbutton", background=[("active", BG)], foreground=[("disabled", MUT)],
               indicatorbackground=[("selected", ACCENT), ("active", HOV)],
               bordercolor=[("selected", ACCENT)])
        st.configure("TRadiobutton", background=BG, foreground=FG, focuscolor=BG,
                     indicatorbackground=FIELD, indicatorforeground=ACCENT, bordercolor=BORDER)
        st.map("TRadiobutton", background=[("active", BG)], foreground=[("disabled", MUT)],
               indicatorbackground=[("selected", FIELD)])
        st.configure("TEntry", fieldbackground=FIELD, foreground=FG, insertcolor=FG,
                     bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=(6, 4))
        st.map("TEntry", fieldbackground=[("readonly", SURF)], foreground=[("disabled", MUT)],
               bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
               darkcolor=[("focus", ACCENT)])
        st.configure("TCombobox", fieldbackground=FIELD, foreground=FG, background=SURF,
                     arrowcolor=MUT, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                     padding=(6, 4))
        st.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("disabled", MUT)],
               bordercolor=[("focus", ACCENT)], arrowcolor=[("active", FG)])
        st.configure("TSpinbox", fieldbackground=FIELD, foreground=FG, arrowcolor=MUT,
                     bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=(6, 3))
        st.map("TSpinbox", bordercolor=[("focus", ACCENT)])
        st.configure("TProgressbar", background=ACCENT, troughcolor=FIELD,
                     bordercolor=BORDER, lightcolor=ACCENT, darkcolor=ACCENT, thickness=8)
        for sb in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            st.configure(sb, background=BORDER, troughcolor=BG, bordercolor=BG,
                         arrowcolor=MUT, relief="flat")
            st.map(sb, background=[("active", HOV), ("pressed", ACCENT)])
        st.configure("TPanedwindow", background=BG)
        st.configure("Sash", background=BORDER, sashthickness=6)
        # Table — roomier rows + a quiet, flat header.
        st.configure("Treeview", background=t["tree_bg"], fieldbackground=t["tree_bg"],
                     foreground=FG, bordercolor=BORDER, relief="flat", rowheight=27, font=BASE)
        st.map("Treeview", background=[("selected", SEL)], foreground=[("selected", SELFG)])
        st.configure("Treeview.Heading", background=SURF, foreground=HEAD, bordercolor=BORDER,
                     relief="flat", padding=(8, 6), font=SEMI)
        st.map("Treeview.Heading", background=[("active", HOV)], foreground=[("active", FG)])

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
        st.configure("Accent.TButton", background=ACCENT,
                     foreground=t.get("accent_fg", "#ffffff"),
                     bordercolor=ACCENT, focuscolor=panel, font=("Segoe UI", 9, "bold"),
                     padding=(12, 6))
        st.map("Accent.TButton",
               background=[("pressed", t["accent_press"]), ("active", t["accent_hover"]),
                           ("disabled", BTN_BG)],
               foreground=[("disabled", MUT)])
        st.configure("FeaturedSec.TButton", background=BTN_BG, foreground=FG,
                     bordercolor=BTN_BORDER, focuscolor=panel, padding=(10, 6))
        st.map("FeaturedSec.TButton",
               background=[("pressed", BTN_HOV), ("active", BTN_HOV), ("disabled", BTN_BG)],
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
                self.online_status_lbl.cget("text") in (i18n.t("● not checked"), "● not checked", ""):
            self.online_status_lbl.config(foreground=MUT)
        if hasattr(self, "theme_combo"):
            try:
                self.theme_combo.current(self._THEME_ORDER.index(self.theme_name))
            except Exception:
                pass

    # Theme selection: a dropdown (like the language picker). The ORDER maps
    # combobox indices to theme keys; display names are translated at build
    # time (a language change restarts the app anyway).
    _THEME_ORDER = ("prisma", "dark", "light")

    def _theme_display_names(self):
        return [t("◆ Prisma"), t("☾ Dark"), t("☀ Light")]

    def on_theme_selected(self, _event=None):
        """Theme picked in the dropdown: apply and remember it."""
        idx = self.theme_combo.current()
        if 0 <= idx < len(self._THEME_ORDER):
            self._apply_theme(self._THEME_ORDER[idx])
            self._save_settings()
            self._append_log(f"Theme: {self.theme_name}.")
        try:
            self.theme_combo.selection_clear()
        except Exception:
            pass

    def _on_language_selected(self, _e=None):
        """Language picked in the combobox: confirm, save and restart so every
        widget is rebuilt in the new language (the cleanest, most reliable way)."""
        name = self.lang_display.get()
        code = next((c for c, n in i18n.LANGUAGES.items() if n == name), self.language)
        if code == self.language:
            return
        lang_name = i18n.LANGUAGES.get(code, name)
        if not messagebox.askyesno(
                t("Restart to change language"),
                t("Switch the program language now?\n\nThe app will close and reopen "
                  "in {lang}.", lang=lang_name)):
            self.lang_display.set(i18n.language_name(self.language))  # revert
            return
        self.language = code
        i18n.set_language(code)
        self._save_settings()
        self._restart_app()

    def _restart_app(self):
        """Relaunch this program (used after a language change), then quit so the
        new process owns the window. Works for both the frozen exe and source.

        The new process is fully DETACHED with its own DEVNULL std handles. This
        is essential for a packaged *windowed* build: there sys.stdin/out/err are
        None, and a plain Popen would try to inherit those invalid handles and
        fail with WinError 6 — so the app would close without ever reopening."""
        import subprocess
        if getattr(sys, "frozen", False):
            args = [sys.executable] + sys.argv[1:]
            workdir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            script = os.path.abspath(sys.argv[0])
            args = [sys.executable, script] + sys.argv[1:]
            workdir = os.path.dirname(script)
        creationflags = 0
        if os.name == "nt":
            # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP — the child survives our
            # os._exit and does not depend on this (closing) process' console.
            creationflags = 0x00000008 | 0x00000200
        launched = False
        try:
            subprocess.Popen(
                args, cwd=workdir, close_fds=True, creationflags=creationflags,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
            launched = True
        except Exception as exc:
            self._append_log(f"Restart failed: {exc}")
        try:
            if self._log_writer and hasattr(self._log_writer, "close"):
                self._log_writer.close()
        except Exception:
            pass
        if not launched:
            # Couldn't relaunch — don't kill the app silently; the language is
            # already saved, so tell the user to reopen it manually.
            try:
                messagebox.showinfo(
                    t("Restart to change language"),
                    t("Please close and reopen the app to apply the new language."))
            except Exception:
                pass
            return
        try:
            self.root.destroy()
        except Exception:
            pass
        os._exit(0)

    # ------------------------------------------------------------------ UI
    # ------------------------------------------------------------ UI compose
    def _compose_ui(self):
        """Assemble the CLASSIC single-window layout from the section builders.

        The modern shell (gui_modern.ModernApp) overrides this method and places
        the very same sections into a sidebar-paged layout instead — every
        widget, handler and behaviour is shared between both UIs.
        """
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

    def _build_toolbar(self):
        # Action buttons get collected here so _set_busy can disable them all.
        self._action_buttons = []
        toolbar = ttk.Frame(self.root, padding=(10, 8))
        toolbar.pack(fill="x")
        self._build_sources_section(toolbar)
        self._build_info_section(toolbar)
        self._build_cheatslips_section(toolbar)
        self._build_filter_section(toolbar)

    def _build_sources_section(self, parent):
        # ---- Section 1: External cheat sources (+ featured DevCat card) --
        # The group wraps TIGHTLY around its content (no fill="x"), so the box is
        # only as wide as the sources grid + DevCat card — it doesn't stretch
        # edge-to-edge and waste the rest of the row.
        get_group = ttk.LabelFrame(parent, text="External Cheat Sources", padding=(8, 4))
        get_group.pack(anchor="w", pady=(0, 6))
        gcontent = ttk.Frame(get_group)
        gcontent.pack()
        combo = ttk.Frame(gcontent)
        combo.pack()
        self._build_devcat_card(combo, beside_grid=True)
        self._build_sources_grid(combo)

    def _build_devcat_card(self, parent, beside_grid=False):
        # ---- Featured: get everything from DevCatSKZ (headline action) ----
        # A compact, refined card — in the classic layout right-aligned BESIDE
        # the sources grid; in the modern shell a standalone card on the Start
        # page. Styles (Featured.*/Accent.TButton) adapt per theme.
        border = ttk.Frame(parent, style="FeaturedBorder.TFrame")
        if beside_grid:
            border.pack(side="right", anchor="n", padx=(12, 0))
        else:
            border.pack(anchor="nw")
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
        autoupd_cb = ttk.Checkbutton(
            urow, text="Update automatically", variable=self.auto_update,
            style="Featured.TCheckbutton", command=self._save_settings)
        autoupd_cb.pack(side="right")
        _Tooltip(autoupd_cb,
                 "ON (recommended): a found program update installs itself silently "
                 "at startup and the app restarts — no clicks, no prompts. Works "
                 "because the app is installed per-user (or run portable). OFF: "
                 "updates are only offered in a dialog for you to confirm.")
        self._action_buttons += [self.check_updates_btn]
        # ---- Switch homebrew app: download the on-console counterpart --------
        srow = ttk.Frame(feat, style="Featured.TFrame")
        srow.pack(anchor="w", fill="x", pady=(8, 0))
        self.nroapp_btn = ttk.Button(
            srow, text="Download Switch App", style="FeaturedSec.TButton",
            command=self.on_download_switch_app)
        self.nroapp_btn.pack(side="left")
        nroapp_cb = ttk.Checkbutton(
            srow, text="Copy to SD card", variable=self.nroapp_copy_sd,
            style="Featured.TCheckbutton", command=self._save_settings)
        nroapp_cb.pack(side="left", padx=(8, 0))
        self.androidapp_btn = ttk.Button(
            srow, text="Download Android App", style="FeaturedSec.TButton",
            command=self.on_download_android_app)
        self.androidapp_btn.pack(side="left", padx=(12, 0))
        self._action_buttons += [self.nroapp_btn, self.androidapp_btn]
        _Tooltip(self.androidapp_btn,
                 "Download the Android companion app (SwitchCheatsDownloader-"
                 "Android.apk) — you pick where to save it. Always downloads "
                 "the LATEST app version (SHA-256 verified). Copy the .apk onto "
                 "your phone and install it.")
        _Tooltip(self.nroapp_btn,
                 "Download the Switch homebrew app (SwitchCheatsDownloader.nro) — "
                 "the on-console counterpart of this tool. It fetches the "
                 "always-current cheats archive directly on the Switch. Always "
                 "downloads the LATEST app version.")
        _Tooltip(nroapp_cb,
                 "ON: the downloaded app is copied straight onto your Switch SD "
                 "card as /switch/SwitchCheatsDownloader.nro (auto-detected, like "
                 "the cheats SD export).\nOFF: you pick where to save the .nro "
                 "yourself.")
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

    def _build_sources_grid(self, parent):
        # Grid of the other sources on the LEFT. A 3-column x 4-row layout keeps
        # the block a sensible width (not edge-to-edge) and about as tall as the
        # DevCat card beside it, so the two read as one balanced unit.
        src_grid = ttk.Frame(parent)
        # Center the button grid vertically so its gap to the frame border is the
        # same top and bottom (the DevCatSKZ card on the right is taller).
        src_grid.pack(side="left", anchor="center")
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

    def _build_info_section(self, parent):
        # ---- Section 2: Get cheat information (enrich) ---------------------
        row2 = ttk.Frame(parent)
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

    def _build_cheatslips_section(self, parent):
        # ---- Section 3: Download cheat files (own area) --------------------
        dl_group = ttk.LabelFrame(parent, text="Scrape & Download Cheat Files · cheatslips.com", padding=(8, 6))
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
        # Entprellt wie das Suchfeld: ein voller Tabellenaufbau pro Tastendruck
        # macht das Tippen im Pfadfeld sonst spuerbar zaeh.
        out_entry.bind("<KeyRelease>", lambda _e: self._debounced_refresh_table())
        ttk.Button(action, text="...", width=3, command=self._choose_output).pack(side="left", padx=(0, 2))
        ttk.Button(action, text="Open", width=7, command=self._open_output).pack(side="left", padx=(0, 8))

        # Options row: browser fallback + browser choice + manual reset.
        opts = ttk.Frame(dl_group)
        opts.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(
            opts, text="Download via browser when API is limited (keeps downloading until complete)",
            variable=self.browser_fallback).pack(side="left", padx=(0, 12))
        ttk.Label(opts, text="Browser:").pack(side="left", padx=(0, 3))
        self.browser_combo = ttk.Combobox(opts, textvariable=self.browser_choice,
                                          state="readonly", width=10,
                                          values=list(_BROWSER_KINDS.keys()))
        self.browser_combo.pack(side="left", padx=(0, 12))
        self.browser_combo.bind("<<ComboboxSelected>>", self._on_browser_selected)
        _Tooltip(self.browser_combo,
                 "Browser used for login / quota reset. Built-in Chromium ships "
                 "with the app. Firefox is downloaded on demand into your data "
                 "folder (no admin). Chrome uses your installed Google Chrome.")
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
                 "Download cheat files via the official API. Uses the selected rows, "
                 "or ALL games if nothing is selected. When the API limit is hit the "
                 "quota is reset automatically and the download continues — the "
                 "browser opens only for those resets, never to download cheats.")
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

    def _build_filter_section(self, parent, with_pickers=True):
        # ---- Search + table filters: sits directly above the table columns --
        search_row = ttk.Frame(parent)
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

        # ---- power row: quick-filter chips + column picker + presets --------
        power = ttk.Frame(parent)
        power.pack(fill="x", pady=(4, 0))
        # Quick-filter chips (toggle buttons via the ttk Toolbutton style).
        fav_chip = ttk.Checkbutton(power, text="⭐ " + t("Favorites"),
                                   style="Toolbutton",
                                   variable=self.favorites_only,
                                   command=self.refresh_table)
        fav_chip.pack(side="left", padx=(0, 4))
        _Tooltip(fav_chip,
                 "Show only your ⭐ favourite games. Right-click any row → "
                 "'⭐ Add / remove favorite' to build your watchlist — after a "
                 "data update you get a notification when a favourite gained "
                 "new cheats.")
        ttk.Checkbutton(power, text="⚡ " + t("Has cheats"), style="Toolbutton",
                        variable=self.has_cheats_only,
                        command=self.refresh_table).pack(side="left", padx=(0, 4))
        ttk.Checkbutton(power, text="🖼 " + t("No cover"), style="Toolbutton",
                        variable=self.missing_cover_only,
                        command=self.refresh_table).pack(side="left", padx=(0, 4))
        cheat_chip = ttk.Checkbutton(power, text="🔎 " + t("Search in cheats"),
                                     style="Toolbutton",
                                     variable=self.search_in_cheats,
                                     command=self.refresh_table)
        cheat_chip.pack(side="left", padx=(0, 10))
        _Tooltip(cheat_chip,
                 "ON: the search box also matches the cheat NAMES — type "
                 "'inf health' to find every game that has such a cheat. "
                 "OFF: search game names and IDs only.")
        # Column show/hide menu.
        self.columns_btn = ttk.Menubutton(power, text=t("Columns") + " ▾")
        colmenu = tk.Menu(self.columns_btn, tearoff=0)
        self._all_menus.append(colmenu)
        self._col_vars = {}
        for col_id, heading, _w, _a in COLUMNS:
            var = tk.BooleanVar(value=(col_id not in self._hidden_columns))
            self._col_vars[col_id] = var
            colmenu.add_checkbutton(
                label=t(heading), variable=var,
                command=self._apply_column_visibility_from_menu)
        self.columns_btn["menu"] = colmenu
        self.columns_btn.pack(side="left", padx=(0, 10))
        # Filter presets.
        ttk.Label(power, text=t("Preset:")).pack(side="left", padx=(0, 3))
        self.preset_combo = ttk.Combobox(power, state="readonly", width=16,
                                         values=self._preset_names())
        self.preset_combo.pack(side="left", padx=(0, 3))
        self.preset_combo.bind("<<ComboboxSelected>>", self._apply_selected_preset)
        ttk.Button(power, text=t("Save…"), width=7,
                   command=self._save_current_preset).pack(side="left", padx=(0, 2))
        ttk.Button(power, text=t("Delete"), width=7,
                   command=self._delete_selected_preset).pack(side="left")

        if with_pickers:
            self._build_theme_lang_pickers(search_group)

    def _build_theme_lang_pickers(self, parent, side="right"):
        """Theme + language comboboxes (classic: far right of the filter row;
        modern shell: in the header bar). Creates self.theme_combo/lang_combo."""
        # Theme picker. Label shows the current theme; _apply_theme keeps it in sync.
        self.theme_combo = ttk.Combobox(
            parent, width=11, state="readonly",
            values=self._theme_display_names())
        try:
            self.theme_combo.current(self._THEME_ORDER.index(self.theme_name))
        except Exception:
            self.theme_combo.current(0)
        self.theme_combo.bind("<<ComboboxSelected>>", self.on_theme_selected)
        self.theme_combo.pack(side=side, padx=(6, 2))
        _Tooltip(self.theme_combo, "Choose the theme (saved between runs).")

        # Language picker (native names, so each is readable in its own script).
        # Changing it saves the choice and restarts the app in the new language.
        self.lang_display = tk.StringVar(value=i18n.language_name(self.language))
        self.lang_combo = ttk.Combobox(
            parent, width=11, state="readonly", textvariable=self.lang_display,
            values=list(i18n.LANGUAGES.values()))
        self.lang_combo.pack(side=side, padx=(6, 2))
        self.lang_combo.bind("<<ComboboxSelected>>", self._on_language_selected)
        _Tooltip(self.lang_combo,
                 "Choose the program language. The app restarts to apply it.")

    # ----------------------------------------------- library power features
    def _apply_column_visibility(self):
        """Show only the columns not in self._hidden_columns (order preserved)."""
        if not hasattr(self, "tree"):
            return
        visible = [c[0] for c in COLUMNS if c[0] not in self._hidden_columns]
        if not visible:                      # never hide everything
            visible = ["game_title"]
        try:
            self.tree.configure(displaycolumns=visible)
        except Exception:
            pass

    def _apply_column_visibility_from_menu(self):
        """Sync self._hidden_columns from the menu vars, apply + persist."""
        self._hidden_columns = {c for c, v in self._col_vars.items() if not v.get()}
        self._apply_column_visibility()
        self._save_settings()

    # -- filter presets ---------------------------------------------------
    _PRESET_VARS = ("not_downloaded_only", "names_missing", "nonbase_only",
                    "hide_placeholder_builds", "has_cheats_only",
                    "missing_cover_only", "favorites_only", "search_in_cheats")

    def _preset_names(self):
        return sorted(self._filter_presets.keys())

    def _capture_filter_state(self) -> dict:
        return {k: bool(getattr(self, k).get()) for k in self._PRESET_VARS}

    def _save_current_preset(self):
        from tkinter import simpledialog
        name = simpledialog.askstring(
            t("Save filter preset"), t("Preset name:"), parent=self.root)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        self._filter_presets[name] = self._capture_filter_state()
        self._save_settings()
        self.preset_combo.configure(values=self._preset_names())
        self.preset_combo.set(name)
        self.status_var.set(t("Saved filter preset '{name}'.", name=name))

    def _apply_selected_preset(self, _e=None):
        name = self.preset_combo.get()
        state = self._filter_presets.get(name)
        if not state:
            return
        for k in self._PRESET_VARS:
            if k in state:
                getattr(self, k).set(bool(state[k]))
        self.refresh_table()
        self.status_var.set(t("Applied filter preset '{name}'.", name=name))

    def _delete_selected_preset(self):
        name = self.preset_combo.get()
        if name in self._filter_presets:
            del self._filter_presets[name]
            self._save_settings()
            self.preset_combo.configure(values=self._preset_names())
            self.preset_combo.set("")
            self.status_var.set(t("Deleted filter preset '{name}'.", name=name))

    # -- ⭐ favourites / watchlist -----------------------------------------
    def toggle_favorite_tid(self, tid) -> bool:
        """Toggle one game's ⭐; returns the NEW state. Persists + refreshes."""
        tid_u = (tid or "").strip().upper()
        if not tid_u:
            return False
        if tid_u in self._favorites:
            self._favorites.discard(tid_u)
            fav = False
        else:
            self._favorites.add(tid_u)
            fav = True
        self._save_settings()
        self.refresh_table()
        return fav

    def _ctx_toggle_favorite(self):
        """Toggle ⭐ for every selected row's game (per title_id)."""
        pairs = self._selected_pairs()
        seen, added, removed = set(), 0, 0
        for tid, _bid in pairs:
            tid_u = (tid or "").strip().upper()
            if not tid_u or tid_u == "-" or tid_u in seen:
                continue
            seen.add(tid_u)
            if tid_u in self._favorites:
                self._favorites.discard(tid_u)
                removed += 1
            else:
                self._favorites.add(tid_u)
                added += 1
        if not seen:
            return
        self._save_settings()
        self.refresh_table()
        self.status_var.set(t("Favorites: {added} added, {removed} removed "
                              "({total} total).", added=added, removed=removed,
                              total=len(self._favorites)))

    def _favorite_counts_snapshot(self, db_path) -> dict:
        """Per-favourite (cheat sum, build count, name) — the watchlist takes
        this snapshot before a data update and diffs it afterwards. Read-only
        connection, safe to call from worker threads."""
        favs = {f.upper() for f in getattr(self, "_favorites", set())}
        if not favs:
            return {}
        import sqlite3 as _sq
        out = {}
        try:
            p = Path(db_path)
            if not p.exists():
                return {}
            con = _sq.connect(f"file:{p}?mode=ro", uri=True)
            q = ("SELECT UPPER(title_id), COALESCE(SUM(cheat_count),0), COUNT(*), "
                 "MAX(game_title) FROM builds WHERE UPPER(title_id) IN (%s) "
                 "GROUP BY UPPER(title_id)" % ",".join("?" * len(favs)))
            for tid, total, builds, name in con.execute(q, tuple(sorted(favs))):
                out[tid] = (total, builds, name or tid)
            con.close()
        except Exception:
            pass
        return out

    def _favorite_news(self, db_path, before: dict) -> list:
        """Names of favourites that gained cheats or builds since *before*."""
        if not getattr(self, "_favorites", None):
            return []
        after = self._favorite_counts_snapshot(db_path)
        news = []
        for tid, (total, builds, name) in after.items():
            prev = before.get(tid)
            if prev is None:
                if total > 0:
                    news.append(name)
            elif total > prev[0] or builds > prev[1]:
                news.append(name)
        return sorted(news)

    def _build_main(self, parent=None):
        # Table (left) + cheat-names panel (right), resizable.
        paned = ttk.Panedwindow(parent or self._top_container, orient="horizontal")
        paned.pack(side="top", fill="both", expand=True, padx=10)

        left = ttk.Frame(paned)
        columns = [c[0] for c in COLUMNS]
        self.tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="extended")
        for col_id, heading, width, anchor in COLUMNS:
            self.tree.heading(col_id, text=heading,
                              command=lambda c=col_id: self._sort_by(c))
            self.tree.column(col_id, width=width, anchor=anchor, stretch=(col_id == "game_title"))
        self._apply_tree_tags()
        self._apply_column_visibility()   # honour any saved hidden columns
        vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        # Double-click a row opens the cheat viewer/editor (single-cell copy is
        # still available via Ctrl+C / the context menu).
        self.tree.bind("<Double-1>", self._open_cheat_editor)
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
        _ctx_add("favorite", "⭐ Add / remove favorite", self._ctx_toggle_favorite)
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

    def _build_database_bar(self, parent=None, compact=False):
        # Bottom row under the table: database actions + DB path. Packed at the
        # bottom BEFORE the table so its height is always reserved (never
        # clipped when the window/log leaves the table little room).
        # compact=True (modern windowed shell): wrap onto TWO rows so nothing is
        # cut off at ~1560px window width.
        bar = ttk.LabelFrame(parent or self._top_container, text="Database", padding=(8, 4))
        bar.pack(side="bottom", fill="x", padx=10, pady=(6, 0))

        if compact:
            left = ttk.Frame(bar)
            left.pack(fill="x", anchor="w")
            left2 = ttk.Frame(bar)
            left2.pack(fill="x", anchor="w", pady=(4, 0))
        else:
            left = ttk.Frame(bar)
            left.pack(side="left")
            left2 = left
        self.refresh_btn = ttk.Button(left, text="Refresh", command=self.on_refresh)
        self.refresh_btn.pack(side="left", padx=(0, 4))
        self.add_btn = ttk.Button(left, text="Add Entry", command=self.on_add_entry)
        self.add_btn.pack(side="left", padx=(0, 4))
        self.csv_btn = ttk.Button(left, text="Export CSV", command=self.on_export_csv)
        self.csv_btn.pack(side="left", padx=(0, 4))
        self.exportdb_btn = ttk.Button(left, text="Export DB", command=self.on_export_db)
        self.exportdb_btn.pack(side="left", padx=(0, 4))
        self.exportnames_btn = ttk.Button(left, text="Export names.json",
                                          command=self.on_export_names)
        self.exportnames_btn.pack(side="left", padx=(0, 4))
        self.importdb_btn = ttk.Button(left, text="Import DB", command=self.on_import_db)
        self.importdb_btn.pack(side="left", padx=(0, 4))
        self.exportsd_btn = ttk.Button(left, text="Export to SD", command=self.on_export_sd)
        self.exportsd_btn.pack(side="left", padx=(0, 4))
        self.exportzip_btn = ttk.Button(left, text="Export to ZIP", command=self.on_export_zip)
        self.exportzip_btn.pack(side="left", padx=(0, 4))
        self.exportemu_btn = ttk.Button(left2, text="Export for Emulators",
                                        command=self.on_export_emulator)
        self.exportemu_btn.pack(side="left", padx=(0, 4))

        # Rarely-used repairs tucked into a small dropdown menu.
        self.repair_btn = ttk.Menubutton(left2, text="Repair ▾")
        repair_menu = tk.Menu(self.repair_btn, tearoff=0)
        self._all_menus.append(repair_menu)
        repair_menu.add_command(label="Clean invalid cheat files", command=self.on_clean_invalid)
        repair_menu.add_command(label="Retry quota-skipped builds", command=self.on_retry_quota_skipped)
        repair_menu.add_command(label="Retry 'unavailable' builds", command=self.on_clear_unavailable)
        repair_menu.add_separator()
        repair_menu.add_command(label="Fix 0-cheat entries", command=self.on_fix_zero)
        repair_menu.add_command(label="Recount cheats from disk", command=self.on_recount_disk)
        repair_menu.add_command(label="Scan for empty cheat files", command=self.on_find_empty)
        repair_menu.add_command(label="Find invalid code lines", command=self.on_find_invalid_lines)
        repair_menu.add_command(label="Fix ID names", command=self.on_fix_id_names)
        repair_menu.add_separator()
        repair_menu.add_command(label="Sync titles folder with DB", command=self.on_sync_titles)
        self.repair_btn["menu"] = repair_menu
        self.repair_btn.pack(side="left", padx=(0, 4))

        self.clear_btn = ttk.Button(left2, text="Clear DB", command=self.on_clear_db)
        self.clear_btn.pack(side="left", padx=(0, 4))

        ttk.Label(left2, textvariable=self.total_games_var).pack(side="left", padx=(12, 0))

        self.nonbase_btn = ttk.Button(left2, text="Update/DLC IDs", command=self._toggle_nonbase,
                                      width=13)
        self.nonbase_btn.pack(side="left", padx=(12, 0))
        self._action_buttons += [self.nonbase_btn]

        # DB path on the right, expands to fill the remaining width (compact:
        # shares the second row with the remaining buttons).
        right = ttk.Frame(left2 if compact else bar)
        right.pack(side="right", fill="x", expand=True, padx=(12, 0))
        ttk.Label(right, text="DB:").pack(side="left")
        ttk.Button(right, text="...", width=3, command=self._choose_db).pack(side="right")
        ttk.Entry(right, textvariable=self.db_path).pack(side="left", fill="x", expand=True, padx=(4, 4))

        self._action_buttons += [self.add_btn, self.csv_btn, self.exportdb_btn,
                                 self.exportnames_btn,
                                 self.importdb_btn, self.exportsd_btn, self.exportzip_btn,
                                 self.exportemu_btn,
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
        _Tooltip(self.exportemu_btn,
                 "Build an emulator package: export the cheats into the "
                 "<TitleID>/<GameName>/cheats/<BuildID>.txt layout that Eden, Suyu, "
                 "Sudachi (and desktop yuzu/Ryujinx) read from their 'load' folder. "
                 "Game names come from the database (special characters removed). "
                 "Folder or ZIP; pick a specific emulator to prepend its load path.")
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
        _Tooltip(self.exportnames_btn,
                 "Export a small Title ID → game name map (names.json) from the "
                 "current database. The Android app uses it to name each game's "
                 "cheat folder; upload it to the 'data' release to keep names current.")
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

    def _build_log(self, parent=None, with_status=True):
        # Classic: lives in the bottom pane of the vertical splitter so it can be
        # dragged taller (weight=1 vs. 5 for the table = compact initial height).
        # Modern shell: built into its own page (status+progress live in the footer).
        if parent is None:
            frame = ttk.Frame(self.vpaned, padding=(10, 6))
            self.vpaned.add(frame, weight=1)
        else:
            frame = ttk.Frame(parent, padding=(10, 6))
            frame.pack(fill="both", expand=True)
        if with_status:
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
            "has_cheats": self.has_cheats_only.get(),
            "missing_cover": self.missing_cover_only.get(),
            "favorites_only": self.favorites_only.get(),
            "favorites": frozenset(self._favorites),
            "in_cheats": self.search_in_cheats.get(),
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
            self._log_queue.put(("table_rows", gen, [], t("{n} games", n=0),
                t("No database yet at {path} - click 'Scrape all' to build it.", path=path)))
            return
        try:
            db = GameDatabase(path)
            try:
                rows = db.search(term=snap["term"], in_cheats=snap["in_cheats"])
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
            if snap["has_cheats"] and not (r["cheat_count"] or 0) > 0:
                continue
            if snap["missing_cover"] and (r["image"] or "").strip():
                continue
            is_fav = (r["title_id"] or "").upper() in snap["favorites"]
            if snap["favorites_only"] and not is_fav:
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
                ("⭐ " if is_fav else "") + (r["game_title"] or ""),
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
        # Human-readable summary with grouped thousands, e.g.
        # "5,307 builds · 100% downloaded · 57 update/DLC".
        pct = (100 * have // shown) if shown else 0
        parts = [t("{n} builds", n=f"{shown:,}"),
                 t("{pct}% downloaded", pct=pct)]
        if shown - have:
            parts.append(t("{n} missing", n=f"{shown - have:,}"))
        if nameless:
            parts.append(t("{n} unnamed", n=f"{nameless:,}"))
        if nonbase:
            parts.append(t("{n} update/DLC", n=f"{nonbase:,}"))
        games_label = t("{n} games", n=total_games)
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
                for offset, (values, tags, slug, cheats) in enumerate(prepared[start:end]):
                    # Zebra-stripe odd rows (skip rows that already have a
                    # background tint so the two never fight over the background).
                    if (start + offset) % 2 and "nonbase" not in tags:
                        tags = tuple(tags) + ("stripe",)
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
                      label=t("Download ({n})", n=n) if n > 1 else t("Download this"))
        m.entryconfig(idx["download_api"],
                      label=t("Download via API ({n})", n=n) if n > 1 else t("Download via API"))
        m.entryconfig(idx["download_browser"],
                      label=t("Download via browser ({n})", n=n) if n > 1
                      else t("Download via browser (bypass API limit)"))
        m.entryconfig(idx["check_file"],
                      label=t("Check Cheat Files ({n})", n=n) if n > 1 else t("Check Cheat File"))
        m.entryconfig(idx["export_zip"],
                      label=t("Export to ZIP ({n} selected)", n=n) if n > 1 else t("Export to ZIP"))
        self._ctx_info_menu.entryconfig(
            self._ctx_info_cover_index,
            label=t("Download cover (selected {n})", n=n) if n > 1 else t("Download cover (selected)"))
        m.entryconfig(idx["delete"],
                      label=t("Delete ({n})", n=n) if n > 1 else t("Delete entry"))
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
            t("Refresh game metadata (name, cover, build list, credits) for {n} selected game(s)?",
              n=len(tids))):
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
            t("Open a browser and download {n} game(s) directly from "
              "cheatslips.com?\n\n"
              "You log in once (solve the reCAPTCHA if asked); the quota is reset "
              "automatically when needed.", n=len(tids))):
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
                t("Open a browser and download {n} selected game(s) directly "
                  "from cheatslips.com?\n\nYou log in once (solve the reCAPTCHA if "
                  "asked); the quota is reset automatically when needed.", n=len(tids))):
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
            "browser_fallback": True,   # this IS the browser-download path
            "title_ids": title_ids,   # None = all still-missing builds
        }
        threading.Thread(target=self._missing_download_worker, args=(cfg,), daemon=True).start()

    def _missing_download_worker(self, cfg):
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
            # True = auto-refresh like the Refresh button after a cheat download.
            self._log_queue.put(("download_done", True))

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
        self.status_var.set(t("Checking {n} cheat file(s)...", n=len(pairs)))
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
        self.status_var.set(
            t("Checked {n} cheat file(s) — {s} count(s) corrected.", n=n, s=synced)
            if synced else t("Checked {n} cheat file(s).", n=n))
        # Refresh FIRST (only when something changed), THEN show the modal — so
        # the table is already up to date when the dialog blocks the loop.
        if synced:
            self.refresh_table()
        if n == 1:
            tid, bid, path, names, verdict = reports[0]
            detail = f"{tid} / {bid}\n\n" + t("Result: {verdict}\nFile: {path}",
                verdict=verdict, path=path if path else t("— not downloaded —"))
            if names:
                shown = "\n".join(f"  • {nm}" for nm in names[:20])
                more = ("\n" + t("  … and {n} more", n=len(names) - 20)
                        if len(names) > 20 else "")
                detail += "\n\n" + t("Cheats found:") + f"\n{shown}{more}"
            else:
                detail += "\n\n" + t(
                    "No usable cheats: the file contains no line with "
                    "real cheat codes.\nSuch stub files come from aggregated "
                    "databases (names/ads only)\nand correctly count as "
                    "'not downloaded' / 0 cheats.")
            body = detail
        else:
            body = (t("Checked {n} build(s):", n=n) + "\n\n" + "\n\n".join(lines[:12])
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
        scope_txt = (t("{n} selected game(s)", n=len(selected)) if scope_tids
                     else t("ALL downloaded cheats"))
        if not messagebox.askyesno(
            "Export to SD",
            t("Export {scope} to:\n{root}\n\nTarget: {mode}\n\n"
              "Only files with real cheats are copied; existing SD cheats are "
              "merged. Proceed?", scope=scope_txt, root=r["sd_root"],
              mode=mode_label)):
            return
        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set(t("Exporting cheats to SD ({mode})...", mode=mode_label))
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
        self.status_var.set(t("SD export ({mode}): {exported} file(s) for "
                              "{games} game(s).", mode=mode_label,
                              exported=stats['exported'], games=stats['games']))
        try:
            self.root.lift(); self.root.focus_force()
        except Exception:
            pass
        self.root.after(10, lambda: messagebox.showinfo(
            "Export to SD",
            t("Export finished ({mode}):\n\n"
              "  • {exported} cheat file(s) for {games} game(s)\n"
              "  • {stubs} empty/stub file(s) skipped\n"
              "  • {missing} build(s) not downloaded (nothing to copy)\n"
              "  • {errors} error(s)\n\n"
              "You can now safely eject the card and start your games.",
              mode=mode_label, exported=stats['exported'], games=stats['games'],
              stubs=stats['skipped_stub'], missing=stats['missing'],
              errors=stats['errors']),
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
        # Callers may hand an explicit title set (context menu, game page);
        # otherwise fall back to the table selection.
        selected = title_ids or self._selected_title_ids()
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
        self.status_var.set(t("Exporting cheats to ZIP ({mode})...", mode=mode_label))
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
        self.status_var.set(t("ZIP export ({mode}): {exported} file(s) for "
                              "{games} game(s) → {path}", mode=mode_label,
                              exported=stats['exported'], games=stats['games'],
                              path=zip_path))
        try:
            self.root.lift(); self.root.focus_force()
        except Exception:
            pass
        self.root.after(10, lambda: messagebox.showinfo(
            "Export to ZIP",
            t("ZIP created ({mode}):\n{path}\n\n"
              "  • {exported} cheat file(s) for {games} game(s)\n"
              "  • {stubs} empty/stub file(s) skipped\n"
              "  • {missing} build(s) not downloaded (nothing to copy)\n"
              "  • {errors} error(s)\n\n"
              "Unzip the archive onto your SD-card root to install the cheats.",
              mode=mode_label, path=zip_path, exported=stats['exported'],
              games=stats['games'], stubs=stats['skipped_stub'],
              missing=stats['missing'], errors=stats['errors']),
            parent=self.root))

    # ------------------------------------------------- export for emulators
    def on_export_emulator(self):
        """Export the DB's cheats into the emulator load layout (folder or ZIP)."""
        if self._busy:
            return
        if not Path(self.db_path.get()).exists():
            messagebox.showwarning("Export for Emulators",
                                   t("No database file yet. Scrape first."))
            return
        selected = self._selected_title_ids()
        if not hasattr(self, "emu_export_path"):
            self.emu_export_path = tk.StringVar(
                value=str(Path(self.dl_output.get()) / "switch-cheats-emulator"))
        dlg = ExportEmulatorDialog(self.root, self.emu_export_path, len(selected),
                                   default_scope="selected" if selected else "all")
        self.root.wait_window(dlg.top)
        if not dlg.result:
            return
        r = dlg.result
        scope_tids = selected if r["scope"] == "selected" else None
        label = EMULATOR_TARGETS.get(r["target"], (r["target"], ""))[0]
        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set(t("Exporting cheats for emulators ({label})...", label=label))
        cfg = {"db_path": self.db_path.get(), "output": self.dl_output.get(),
               "dest": r["dest"], "target": r["target"], "as_zip": r["as_zip"],
               "title_ids": scope_tids}
        threading.Thread(target=self._export_emulator_worker, args=(cfg,), daemon=True).start()

    def _export_emulator_worker(self, cfg):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        stats = None
        try:
            db = GameDatabase(Path(cfg["db_path"]))
            try:
                name_map = build_title_name_map(db._conn)
                prefix = EMULATOR_TARGETS.get(cfg["target"], ("", ""))[1]
                tracker = ProgressTracker("emu-export")
                def prog(done, total):
                    tracker.update(done, total)
                    self._log_queue.put(("progress", done, total,
                        f"Exporting for emulators {done}/{total} ({tracker.pct()}%) | "
                        f"{tracker.rate_str('items')} | ~{tracker.eta_str()} remaining"))
                stats = export_cheats_for_emulator(
                    db, Path(cfg["output"]), cfg["dest"], name_map, prefix=prefix,
                    as_zip=cfg["as_zip"], title_ids=cfg["title_ids"],
                    progress_cb=prog, should_stop=self._stop_event.is_set)
            finally:
                db.close()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"FATAL: {exc}")
            self._log_queue.put(("error", f"Emulator export failed:\n{exc}"))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout
            self._log_queue.put(("emu_export_done", stats, cfg.get("as_zip"), cfg.get("dest")))

    def _finish_emulator_export(self, stats, as_zip, dest):
        self._set_busy(False)
        if not stats:
            self.status_var.set("Emulator export failed — see log.")
            return
        if stats["exported"] == 0:
            self.status_var.set("Emulator export: nothing to export (no downloaded cheats).")
            self.root.after(10, lambda: messagebox.showinfo(
                "Export for Emulators",
                "Nothing was exported — none of the selected builds have a "
                "downloaded cheat file with real codes yet.", parent=self.root))
            return
        kind = "ZIP" if as_zip else t("folder")
        self.status_var.set(t("Emulator export ({kind}): {exported} file(s) for "
                              "{games} game(s) → {dest}", kind=kind,
                              exported=stats['exported'], games=stats['games'], dest=dest))
        try:
            self.root.lift(); self.root.focus_force()
        except Exception:
            pass
        self.root.after(10, lambda: messagebox.showinfo(
            "Export for Emulators",
            t("Emulator export finished ({kind}):\n{dest}\n\n"
              "  • {exported} cheat file(s) for {games} game(s)\n"
              "  • {stubs} empty/stub file(s) skipped\n"
              "  • {missing} build(s) not downloaded (nothing to copy)\n"
              "  • {errors} error(s)\n\n"
              "Copy the <TitleID>/<GameName>/cheats/… structure into your "
              "emulator's load folder.", kind=kind, dest=dest,
              exported=stats['exported'], games=stats['games'],
              stubs=stats['skipped_stub'], missing=stats['missing'],
              errors=stats['errors']), parent=self.root))

    def _finish_import_db(self, summary):
        self._set_busy(False)
        self.refresh_table(force_scan=True)
        if not summary:
            self.status_var.set("Import database failed — see log.")
            return
        if summary["mode"] == "replace":
            self.status_var.set(t("Database replaced — {n} build(s).",
                                  n=summary['after']))
            msg = t("Database replaced with the imported one.\n\n"
                    "  • {n} build(s) now in the database\n", n=summary['after'])
            if summary.get("backup"):
                msg += "\n" + t("A backup of the previous database was saved "
                                "to:\n{path}", path=summary['backup'])
        else:
            self.status_var.set(t("Database merged — {added} added, "
                                  "{updated} updated ({total} total).",
                                  added=summary['added'],
                                  updated=summary['updated'],
                                  total=summary['after']))
            msg = t("Imported {total} build(s):\n\n"
                    "  • {added} new build(s) added\n"
                    "  • {updated} existing build(s) updated\n"
                    "  • {after} build(s) now in the database\n\n"
                    "Nothing was removed; existing entries kept their data.",
                    total=summary['total_imported'], added=summary['added'],
                    updated=summary['updated'], after=summary['after'])
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
        # Watchlist: snapshot the favourites BEFORE the import so _finish_devcat
        # can tell which of them gained new cheats.
        fav_before = self._favorite_counts_snapshot(cfg["db_path"])
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
            fav_news = self._favorite_news(cfg["db_path"], fav_before)
            self._log_queue.put(("devcat_done", db_summary, cheats_summary, fav_news))
        except Exception as exc:
            self._log_queue.put(("error", f"Download from DevCatSKZ failed:\n{exc}"))
            self._log_queue.put(("download_done",))

    def _finish_devcat(self, db_summary, cheats_summary, fav_news=None):
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
        self.status_var.set(t("DevCatSKZ download done — {parts}", parts=" · ".join(parts)))
        # ⭐ watchlist: when favourites gained new cheats, THAT is the headline
        # of the notification; otherwise the generic "data is current" toast.
        if fav_news:
            names = ", ".join(fav_news[:5]) + ("…" if len(fav_news) > 5 else "")
            line = t("{n} favorite(s) got new cheats: {names}",
                     n=len(fav_news), names=names)
            self._append_log("⭐ " + line)
            self._toast(t("Favorites updated"), line)
        else:
            self._toast(t("Data update installed"),
                        t("Cheats and database are up to date."))
        # Covers are fetched only when the user opted in via the card checkbox
        # (off by default). No prompt — the checkbox is the choice.
        if self.devcat_covers.get():
            self.root.after(10, lambda: self._download_covers(None))

    # ---------------------------------------------- Switch homebrew app (.nro)
    def on_download_switch_app(self):
        """Download the latest Switch app; optionally copy it onto the SD card.

        Mirrors the cheats SD export: the card is auto-detected via the CFW
        marker folders; with the checkbox off the user just picks a save
        location. Always fetches the CURRENT app version from GitHub.
        """
        if self._busy:
            return
        sd_root = None
        if self.nroapp_copy_sd.get():
            roots = [r for r in detect_sd_roots() if looks_like_sd_root(r)]
            if len(roots) == 1:
                sd_root = roots[0]
            else:
                initial = (self.sd_export_root.get()
                           or (roots[0] if roots else ""))
                chosen = filedialog.askdirectory(
                    title=t("Select your Switch SD card root"),
                    initialdir=initial or None, parent=self.root)
                if not chosen:
                    return
                if not looks_like_sd_root(chosen) and not messagebox.askyesno(
                        "Download Switch App",
                        t("'{path}' does not look like a Switch SD card "
                          "(no atmosphere/switch/Nintendo folder). Use it "
                          "anyway?", path=chosen), parent=self.root):
                    return
                sd_root = chosen
            target_txt = os.path.join(sd_root, NRO_SD_DIR, NRO_ASSET)
            if not messagebox.askyesno(
                    "Download Switch App",
                    t("Download the latest Switch app and copy it to:\n"
                      "{target}\n\nAn existing copy on the card is replaced. "
                      "Proceed?", target=target_txt), parent=self.root):
                return
            import tempfile
            dest = Path(tempfile.gettempdir()) / NRO_ASSET
        else:
            path = filedialog.asksaveasfilename(
                title=t("Save Switch app as..."),
                initialfile=NRO_ASSET, defaultextension=".nro",
                filetypes=[(t("Switch homebrew app"), "*.nro")],
                parent=self.root)
            if not path:
                return
            dest = Path(path)
        self._stop_event.clear()
        self._save_settings()
        self._set_busy(True)
        self.status_var.set(t("Downloading Switch app..."))
        threading.Thread(target=self._switch_app_worker,
                         args=(dest, sd_root), daemon=True).start()

    def _switch_app_worker(self, dest, sd_root):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            def prog(done, total):
                kb = done // 1024
                pct = f" ({int(done * 100 / total)}%)" if total else ""
                self._log_queue.put(("progress", done, max(total, 1),
                                     f"Switch app: {kb:,} KB{pct}"))
            info = download_switch_app(dest, progress_cb=prog,
                                       should_stop=self._stop_event.is_set)
            print(f"Switch app v{info['version']} downloaded "
                  f"({info['size'] // 1024:,} KB).")
            target = None
            if sd_root:
                target = copy_nro_to_sd(info["path"], sd_root)
                print(f"Copied to {target}")
                try:
                    Path(info["path"]).unlink()
                except Exception:
                    pass
            self._log_queue.put(("switchapp_done", info, target))
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self._log_queue.put(("error", f"Switch app download failed:\n{exc}"))
            self._log_queue.put(("switchapp_done", None, None))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout

    def _finish_switch_app(self, info, target):
        self._set_busy(False)
        if not info:
            self.status_var.set(t("Switch app download failed — see log."))
            return
        ver = info.get("version", "?")
        try:
            self.root.lift(); self.root.focus_force()
        except Exception:
            pass
        if target:
            self.status_var.set(t("Switch app v{ver} copied to SD card.", ver=ver))
            self.root.after(10, lambda: messagebox.showinfo(
                "Download Switch App",
                t("Switch app v{ver} copied to:\n{target}\n\n"
                  "You can now safely eject the card and launch "
                  "'Switch Cheats Downloader' from the Homebrew Menu.",
                  ver=ver, target=target), parent=self.root))
        else:
            self.status_var.set(t("Switch app v{ver} downloaded.", ver=ver))
            self.root.after(10, lambda: messagebox.showinfo(
                "Download Switch App",
                t("Switch app v{ver} saved to:\n{path}\n\n"
                  "Copy it into the /switch/ folder on your Switch SD card and "
                  "launch it from the Homebrew Menu.",
                  ver=ver, path=info.get("path", "?")), parent=self.root))

    # ------------------------------------------- Android companion app (.apk)
    ANDROID_APK_ASSET = "SwitchCheatsDownloader-Android.apk"

    def on_download_android_app(self):
        """Download the latest Android app: the user picks where to save the
        .apk (explorer dialog), then the CURRENT release asset is fetched and
        SHA-256 verified."""
        if self._busy:
            return
        path = filedialog.asksaveasfilename(
            title=t("Save Android app as..."),
            initialfile=self.ANDROID_APK_ASSET, defaultextension=".apk",
            filetypes=[(t("Android app"), "*.apk")],
            parent=self.root)
        if not path:
            return
        self._stop_event.clear()
        self._save_settings()
        self._set_busy(True)
        self.status_var.set(t("Downloading Android app..."))
        threading.Thread(target=self._android_app_worker,
                         args=(Path(path),), daemon=True).start()

    def _android_app_worker(self, dest):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._log_queue, mirror=self._log_writer)
        try:
            rel = fetch_github_release(tag=None)   # /releases/latest
            asset = find_release_asset(rel, self.ANDROID_APK_ASSET)
            if not asset or not asset.get("url"):
                raise RuntimeError(
                    f"asset '{self.ANDROID_APK_ASSET}' not found in the latest release")

            def prog(done, total):
                kb = done // 1024
                pct = f" ({int(done * 100 / total)}%)" if total else ""
                self._log_queue.put(("progress", done, max(total, 1),
                                     f"Android app: {kb:,} KB{pct}"))

            download_file(asset["url"], dest, progress_cb=prog,
                          should_stop=self._stop_event.is_set)
            want = int(asset.get("size") or 0)
            got = dest.stat().st_size
            if want and got != want:
                raise RuntimeError(f"download incomplete: got {got:,} of {want:,} bytes")
            # Same integrity check as the self-updater: never hand the user a
            # corrupted or tampered apk.
            digest = (asset.get("digest") or "").strip().lower()
            if digest.startswith("sha256:"):
                if sha256_of_file(dest) != digest.split(":", 1)[1]:
                    raise RuntimeError("SHA-256 mismatch — the download is corrupted")
                print("Android app verified (SHA-256 OK).")
            ver = rel.get("version", "?")
            print(f"Android app v{ver} downloaded ({got // 1024:,} KB).")
            self._log_queue.put(("androidapp_done", ver, str(dest)))
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self._log_queue.put(("error", f"Android app download failed:\n{exc}"))
            self._log_queue.put(("androidapp_done", None, None))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout

    def _finish_android_app(self, ver, path):
        self._set_busy(False)
        if not ver:
            self.status_var.set(t("Android app download failed — see log."))
            return
        try:
            self.root.lift(); self.root.focus_force()
        except Exception:
            pass
        self.status_var.set(t("Android app v{ver} downloaded.", ver=ver))
        self.root.after(10, lambda: messagebox.showinfo(
            "Download Android App",
            t("Android app v{ver} saved to:\n{path}\n\n"
              "Copy the .apk onto your phone and install it (allow installation "
              "from unknown sources).", ver=ver, path=path), parent=self.root))

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
        # --- Auto-update runs ONLY on the automatic startup check: a found program
        #     update installs itself silently (no dialog, no clicks) when enabled
        #     AND doable without a UAC prompt (a writable app folder — per-user
        #     install or portable). A MANUAL "Check Updates" click always opens the
        #     dialog instead, so the user reviews the notes, presses Update &
        #     Restart and WATCHES the download + install progress. ---
        can_silent = (getattr(sys, "frozen", False) and not self._busy
                      and self._app_dir_writable())
        # 1) A found PROGRAM update installs itself silently on startup, when
        #    enabled AND doable without a UAC prompt (writable frozen build). A
        #    manual "Check Updates" click never lands here.
        if startup and prog and self.auto_update.get() and can_silent:
            self.update_status_lbl.config(text="installing update…",
                                          foreground=theme()["checking"])
            self.start_program_update(info)
            return
        # 2) The cheat DATA auto-merges on startup when the user keeps it current
        #    ("Keep the cheat data up to date" on Settings) — non-destructive, so
        #    it works from source too — or as part of the classic silent path.
        #    _finish_devcat shows a toast with the result.
        data_auto = (self.keep_data_updated.get()
                     or (self.auto_update.get() and can_silent))
        if startup and has_data and data_auto and not self._busy:
            self.start_data_update(info)
            if not prog:
                return
            # A program update is ALSO available → still show its dialog below.
            info = dict(info, cheats=None, db=None)
        # 3) Startup checks stay quiet unless something is actually new.
        if startup and not (prog or bool(info.get("cheats") or info.get("db"))):
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
                t("Could not check for updates:\n\n{msg}\n\n"
                  "Check your internet connection and try again.", msg=msg))

    def _show_update_dialog(self, info: dict):
        prog = info.get("program")
        cheats = info.get("cheats")
        db = info.get("db")
        if not (prog or cheats or db):
            messagebox.showinfo(
                "Check Updates",
                t("You are up to date.\n\nInstalled version: v{ver}\n"
                  "Program, cheats and database are all current.",
                  ver=APP_VERSION))
            return
        UpdateDialog(self.root, self, info)

    # ---- program self-update -------------------------------------------
    def _is_installed_build(self) -> bool:
        """True when this frozen build was set up by the Inno Setup installer
        (its uninstaller sits next to the .exe); False for a portable unzip."""
        try:
            return (Path(sys.executable).resolve().parent / "unins000.exe").exists()
        except Exception:
            return False

    def _app_dir_writable(self) -> bool:
        """Can we write into the folder the .exe runs from? (portable updates
        replace files there; a Program Files install is read-only for the user)."""
        try:
            d = Path(sys.executable).resolve().parent
            probe = d / ".scs_update_probe"
            probe.write_text("ok", encoding="utf-8"); probe.unlink()
            return True
        except Exception:
            return False

    def start_program_update(self, info: dict):
        """Download + apply a newer build — via the INSTALLER for an installed
        build, or by replacing files IN PLACE for a portable build. Each path is
        chosen to match how this copy was set up (with a sensible fallback)."""
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
        setup = prog.get("setup") or {}
        portable = prog.get("portable") or {}
        installed = self._is_installed_build()
        # Choose the method that matches this build; fall back if its asset or a
        # writable app folder is missing.
        method = None
        if installed:
            if setup.get("url"):
                method = "installer"
            elif portable.get("url") and self._app_dir_writable():
                method = "portable"
        else:  # portable build
            if portable.get("url") and self._app_dir_writable():
                method = "portable"
            elif setup.get("url"):
                method = "installer"
        if method is None:
            if prog.get("html_url"):
                webbrowser.open(prog["html_url"])
            messagebox.showinfo(
                "Update",
                "Couldn't update automatically (no matching download, or the app "
                "folder is read-only). The release page has been opened so you can "
                "update manually.")
            return
        self._stop_event.clear()
        self._set_busy(True)
        self._update_dlg = UpdateProgressDialog(self.root, on_cancel=self._cancel_update)
        self._update_dlg.set_phase(t("Downloading update ({method})…", method=method))
        self.status_var.set("Downloading update…")
        threading.Thread(target=self._program_update_worker,
                         args=(method, prog), daemon=True).start()

    def _cancel_update(self):
        """User cancelled the update download."""
        self._stop_event.set()
        dlg = getattr(self, "_update_dlg", None)
        if dlg:
            dlg.set_phase("Cancelling…"); dlg.disable_cancel()

    def _program_update_worker(self, method: str, prog: dict):
        import tempfile
        import zipfile
        asset = prog.get("setup") if method == "installer" else prog.get("portable")
        name = PROGRAM_SETUP_ASSET if method == "installer" else PROGRAM_PORTABLE_ASSET
        dest = Path(tempfile.gettempdir()) / name

        def cb(done, total):
            mb, tmb = done / 1048576, (total / 1048576 if total else 0)
            pct = f" ({int(done * 100 / total)}%)" if total else ""
            self._log_queue.put(("progress", done, max(total, 1),
                                 f"Downloading update: {mb:.1f} / {tmb:.1f} MB{pct}"))
        try:
            self._log_queue.put(("status", t("Downloading update ({method})…", method=method)))
            download_file(asset["url"], dest, progress_cb=cb,
                          should_stop=self._stop_event.is_set)
            # Guard against a silently-truncated download (dropped connection):
            # never apply a partial update.
            want = int(asset.get("size") or 0)
            got = dest.stat().st_size
            if want and got != want:
                raise RuntimeError(f"download incomplete: got {got:,} of {want:,} bytes")
            # Verify the content against GitHub's published SHA-256 digest —
            # a corrupted or tampered download is never installed.
            digest = (asset.get("digest") or "").strip().lower()
            if digest.startswith("sha256:"):
                self._log_queue.put(("update_phase", t("Verifying download…"),
                                     "SHA-256"))
                have = sha256_of_file(dest)
                if have != digest.split(":", 1)[1]:
                    raise RuntimeError(
                        f"SHA-256 mismatch — the download is corrupted or was "
                        f"tampered with (expected {digest.split(':', 1)[1][:12]}…, "
                        f"got {have[:12]}…). Nothing was installed.")
                self._log_queue.put(("status", t("Update verified (SHA-256 OK).")))
            if method == "portable":
                # Extract here (worker thread) so the UI/progress dialog stays live.
                self._log_queue.put(("update_phase", "Preparing update…", "Extracting files…"))
                exe = Path(sys.executable).resolve()
                work = Path(tempfile.gettempdir()) / "scs_update"
                shutil.rmtree(work, ignore_errors=True)
                work.mkdir(parents=True, exist_ok=True)
                extract = work / "extract"
                with zipfile.ZipFile(dest) as z:
                    z.extractall(extract)
                src = extract / "SwitchCheatsScraper"
                if not (src / exe.name).exists():
                    found = next(extract.rglob(exe.name), None)
                    if not found:
                        raise RuntimeError("the update archive did not contain the app")
                    src = found.parent
                payload = {"src": str(src), "extract": str(extract),
                           "zip": str(dest), "work": str(work)}
            else:
                payload = {"setup": str(dest)}
            self._log_queue.put(("program_update_ready", method, payload, prog))
        except Exception as exc:
            self._log_queue.put(("error", f"Downloading the update failed:\n{exc}"))
            self._log_queue.put(("download_done",))

    def _apply_program_update(self, method: str, payload: dict, prog: dict):
        if method == "installer":
            self._apply_installer_update(payload["setup"], prog)
        else:
            self._apply_portable_update(payload, prog)

    def _advance_program_baseline(self, prog: dict):
        """Record this build as current so the same version isn't offered again."""
        self._update_state["program_baseline"] = max(
            time.time(), float(prog.get("newest_epoch", 0)))
        self._save_update_state(self._update_state)
        self._save_settings()

    def _quit_for_update(self):
        try:
            if self._log_writer and hasattr(self._log_writer, "close"):
                self._log_writer.close()
        except Exception:
            pass
        os._exit(0)

    def _update_failed(self, message: str):
        dlg = getattr(self, "_update_dlg", None)
        if dlg:
            dlg.close(); self._update_dlg = None
        self._set_busy(False)
        messagebox.showwarning("Update", message)

    def _apply_installer_update(self, setup_path: str, prog: dict):
        """Run the downloaded installer in place, then quit so the running files are
        unlocked. For a per-user install (writable app folder) this launches WITHOUT
        elevation — no UAC prompt, fully silent. Only a legacy read-only Program
        Files install still elevates via UAC. /SILENT shows the installer's own tiny
        progress window; the postinstall [Run] entry relaunches the app afterwards."""
        app_dir = str(Path(sys.executable).resolve().parent)
        args = (f'/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS '
                f'/DIR="{app_dir}"')
        dlg = getattr(self, "_update_dlg", None)
        if dlg:
            dlg.busy("Installing update…",
                     "A Setup window shows the progress; the app reopens automatically.")
        launched = False
        try:
            import ctypes
            # No UAC when the folder is writable (per-user install): plain "open".
            # A read-only Program Files install needs elevation → "runas" (the only
            # case that still shows a UAC prompt). ShellExecute is used either way
            # (subprocess/CreateProcess would fail with error 740 for "runas").
            verb = "open" if self._app_dir_writable() else "runas"
            rc = ctypes.windll.shell32.ShellExecuteW(None, verb, setup_path, args, None, 1)
            launched = int(rc) > 32
        except Exception as exc:
            self._append_log(f"Could not launch the installer: {exc}")
        if not launched:
            self._update_failed(
                "The update could not be started (the elevation prompt was declined "
                "or blocked). Nothing has changed — try again, or update manually "
                "from the GitHub release page.")
            return
        self._advance_program_baseline(prog)
        self.status_var.set("Update installing — the app will close and reopen…")
        self._toast(t("Update is installing"),
                    t("The app closes and reopens automatically."))
        self._quit_for_update()

    def _apply_portable_update(self, payload: dict, prog: dict):
        """Replace the portable app files in place. A helper in a VISIBLE console
        window (so the user sees the progress) waits briefly for this process to
        exit, copies the new files over the app folder (user data next to the .exe
        is preserved — /E, never mirror/delete), and relaunches. No admin needed."""
        import subprocess
        exe = Path(sys.executable).resolve()
        app_dir = exe.parent
        src, extract = payload["src"], payload["extract"]
        zip_path, work = payload["zip"], Path(payload["work"])
        bat = work / "apply_update.cmd"
        # Grace delay + robocopy /R cover the brief file-lock window after exit.
        script = (
            "@echo off\r\n"
            "title Updating Switch Cheats Scraper\r\n"
            "echo(\r\n"
            "echo    Updating Switch Cheats Scraper ^& Downloader...\r\n"
            "echo    Please wait - the app will reopen automatically.\r\n"
            "echo(\r\n"
            "ping -n 4 127.0.0.1 >nul\r\n"
            f'robocopy "{src}" "{app_dir}" /E /R:25 /W:1 /NFL /NDL /NJH /NJS /NP >nul\r\n'
            "echo    Done. Starting the app...\r\n"
            f'start "" "{exe}"\r\n'
            "ping -n 2 127.0.0.1 >nul\r\n"
            f'rmdir /S /Q "{extract}" >nul 2>&1\r\n'
            f'del /Q "{zip_path}" >nul 2>&1\r\n'
            '(goto) 2>nul & del "%~f0"\r\n'
        )
        bat.write_text(script, encoding="utf-8")
        dlg = getattr(self, "_update_dlg", None)
        if dlg:
            dlg.busy("Installing update…",
                     "The app will close and reopen automatically in a moment.")
        try:
            subprocess.Popen(["cmd", "/c", str(bat)], creationflags=0x00000010,  # NEW_CONSOLE
                             cwd=str(work), close_fds=True)
        except Exception as exc:
            self._update_failed(t("Could not start the updater:\n{err}", err=exc))
            return
        self._advance_program_baseline(prog)
        self.status_var.set("Updating — the app will close and reopen…")
        self._toast(t("Update is installing"),
                    t("The app closes and reopens automatically."))
        self._quit_for_update()

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
                self.status_var.set(t("Opened {n} link(s) in browser.", n=opened))
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
                self.status_var.set(t("Revealed {name} in Explorer.", name=path.name))
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
                self.status_var.set(t("No cheat file on disk for {tid}/{bid} — "
                                      "opened {folder}.", tid=tid, bid=bid,
                                      folder=folder))
        except Exception as exc:
            messagebox.showerror("Open in Explorer",
                                 t("Could not open:\n\n{err}", err=exc))

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
            t("Download cover images for all entries in the database and save them to\n"
              "{dir}?\n\n"
              "Already-saved covers are skipped. (Entries without a cover URL are ignored.)",
              dir=COVERS_DIR),
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
            "browser_fallback": self.browser_fallback.get(),
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
                        saved = self._api_download(api, db, out, cfg, progress_cb=dp)
                        print(f"Downloaded {saved} new cheat file(s).")
                        cleanup_invalid_cheat_entries(db, out, should_stop=stop)
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
            t("Delete {n} selected entries?\n"
              "This also deletes the downloaded cheat file(s) on disk.", n=len(pairs)),
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
        self.status_var.set(t("Entry updated and file moved.") if moved else t("Entry updated."))
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

    def _open_cheat_editor(self, event):
        """Double-click a row → open the cheat viewer/editor for that build."""
        row = self.tree.identify_row(event.y)
        if not row:
            return
        col_ids = [c[0] for c in COLUMNS]
        v = self.tree.item(row, "values")

        def col(name):
            i = col_ids.index(name)
            return (v[i] if len(v) > i else "") or ""

        tid = str(col("title_id")).strip()
        bid = str(col("build_id")).strip()
        if not tid or not bid:
            return
        name, version = str(col("game_title")).strip(), str(col("version")).strip()
        # The table shows "-" as a placeholder for empty version/name and a
        # "⭐ " prefix for favourites — normalise both so they never leak into
        # the editor (and from there into the database).
        name = name.removeprefix("⭐").strip()
        if version in ("-", ""):
            version = ""
        if name == "-":
            name = ""
        self._open_cheat_editor_for(tid, bid, name=name, version=version)

    def _open_cheat_editor_for(self, tid, bid, name="", version=""):
        """Open the cheat editor for a specific build (used by the table's
        double-click, the invalid-lines repair list and the game page).
        Missing metadata is filled from the DB. Returns the dialog."""
        # Credits come from the DB; content + downloaded state come from disk.
        credits = ""
        try:
            db = GameDatabase(Path(self.db_path.get()))
            info = db.get_game_info(tid)
            db.close()
            if info:
                if not name:
                    name = info.get("title") or ""
                for s in info.get("sources", []):
                    if (s.get("build_id") or "").upper() == (bid or "").upper():
                        credits = s.get("credits") or ""
                        if not version:
                            version = s.get("version") or ""
                        break
        except Exception:
            pass
        p = self._cheat_file_path(tid, bid)
        content, downloaded = "", False
        if p and p.exists():
            downloaded = True
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                content = ""
        return CheatEditorDialog(
            self.root, title_id=tid, build_id=bid, name=name, version=version,
            credits=credits, content=content, downloaded=downloaded,
            on_save=self._editor_save)

    def _cheat_file_path(self, tid, bid):
        """Standard on-disk location of a build's cheat file (may not exist)."""
        out = Path(self.dl_output.get().strip() or DEFAULT_OUTPUT)
        tid_u, bid_u = (tid or "").upper(), (bid or "").upper()
        cand = [out / "titles" / tid_u / "cheats" / f"{bid_u}.txt",
                out / "by_bid" / f"{bid_u}.txt"]
        for c in cand:
            if c.exists():
                return c
        return cand[0]   # default write location

    def _editor_save(self, payload):
        """Persist an edit from CheatEditorDialog: overwrite the .txt file AND
        update the DB (name / version / credits / cheat_count / cheat_names).
        Returns (ok, message) so the dialog can report inline."""
        tid, bid = payload["title_id"], payload["build_id"]
        content = payload["content"]
        names = parse_cheat_names_from_content(content)
        try:
            path = self._cheat_file_path(tid, bid)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            db = GameDatabase(Path(self.db_path.get()))
            db.upsert_game({
                "title_id": tid, "title": payload["name"] or None, "slug": None,
                "image": None, "banner": None,
                "sources": [{
                    "build_id": bid, "title_id": tid, "source_id": None,
                    "version": payload["version"] or None, "upload_date": None,
                    "cheat_count": len(names), "cheat_names": names,
                    "credits": payload["credits"] or None, "description": None,
                    "cheat_id": None,
                }],
            }, source="manual")
            db.close()
        except Exception as exc:
            return False, str(exc)
        self.status_var.set(t("Saved {tid}/{bid} ({n} cheat(s)).",
                              tid=tid, bid=bid, n=len(names)))
        self.refresh_table()
        return True, t("Saved — {n} cheat(s).", n=len(names))

    # ------------------------------------- repair: find invalid code lines
    def on_find_invalid_lines(self):
        """Scan every downloaded cheat file for malformed Atmosphère code lines
        (same rules as the editor's red marking) and list the hits — a click
        opens the file in the editor, where the lines are already highlighted."""
        if self._busy:
            return
        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set(t("Scanning cheat files for invalid code lines…"))
        cfg = {"output": self.dl_output.get().strip() or DEFAULT_OUTPUT,
               "db_path": self.db_path.get()}
        threading.Thread(target=self._invalid_lines_worker, args=(cfg,),
                         daemon=True).start()

    def _invalid_lines_worker(self, cfg):
        out = Path(cfg["output"])
        results = []
        try:
            # Name + tid lookups from the DB (one shot, read-only).
            names, bid2tid = {}, {}
            try:
                import sqlite3 as _sq
                con = _sq.connect(f"file:{Path(cfg['db_path'])}?mode=ro", uri=True)
                for tid, bid, name in con.execute(
                        "SELECT UPPER(title_id), UPPER(build_id), game_title "
                        "FROM builds"):
                    bid2tid.setdefault(bid, tid)
                    if name:
                        names.setdefault(tid, name)
                con.close()
            except Exception:
                pass

            files = []
            troot = out / "titles"
            if troot.exists():
                files += [(p.parts[-3].upper(), p.stem.upper(), p)
                          for p in troot.glob("*/cheats/*.txt")]
            broot = out / "by_bid"
            if broot.exists():
                seen = {bid for _t, bid, _p in files}
                files += [(bid2tid.get(p.stem.upper(), ""), p.stem.upper(), p)
                          for p in broot.glob("*.txt")
                          if p.stem.upper() not in seen]

            for i, (tid, bid, path) in enumerate(files, 1):
                if self._stop_event.is_set():
                    break
                if i % 250 == 0:
                    self._log_queue.put(("progress", i, len(files),
                                         f"Scanning {i}/{len(files)}"))
                try:
                    txt = path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                bad = [ln.strip() for ln in txt.splitlines()
                       if classify_cheat_line(ln.strip()) == "error"]
                if bad:
                    results.append({
                        "tid": tid, "bid": bid,
                        "name": names.get(tid, ""),
                        "count": len(bad), "sample": bad[0][:60],
                    })
            results.sort(key=lambda r: (-r["count"], r["name"] or "~"))
            self._log_queue.put(("invalid_scan_done", results))
        except Exception as exc:
            self._log_queue.put(("error", f"Invalid-line scan failed:\n{exc}"))
            self._log_queue.put(("invalid_scan_done", None))

    def _finish_invalid_scan(self, results):
        self._set_busy(False)
        if results is None:
            return
        if not results:
            self.status_var.set(t("No invalid code lines found — all files are clean."))
            messagebox.showinfo(
                t("Find invalid code lines"),
                t("No invalid code lines found — all files are clean."),
                parent=self.root)
            return
        self.status_var.set(t("{n} file(s) with invalid code lines.",
                              n=len(results)))
        InvalidLinesDialog(self.root, self, results)

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
        self.status_var.set(t("Saved {tid}/{bid} ({n} cheat(s)).",
                              tid=r['title_id'], bid=r['build_id'], n=len(names)))
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
        self._backup_db("Clear DB")
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

    def _on_browser_selected(self, event=None):
        """When the user picks a browser in the dropdown, make sure it's available.
        Firefox is offered as an on-demand download into the data folder (no admin);
        Chrome uses the installed Google Chrome (offered for download if missing).
        On No / cancel / failure, revert to the built-in Chromium."""
        kind = self._browser_kind()
        if kind == "builtin" or not _PW_OK:
            return
        if self._busy:
            messagebox.showinfo("Browser", "Please wait for the current task to "
                                           "finish before switching the browser.")
            self.browser_choice.set("Built-in")
            return
        if kind == "firefox":
            if _pw_scrape.firefox_ready():
                self.status_var.set("Firefox is ready.")
                return
            if messagebox.askyesno(
                "Download Firefox",
                "Download the Firefox browser component for the app? (~85 MB)\n\n"
                "It is stored in the app's own data folder.\n\n"
                "Choose No to keep the built-in Chromium."):
                self._start_component_download("firefox")
            else:
                self.browser_choice.set("Built-in")
        elif kind in ("chrome", "edge"):
            # Chrome/Edge drive the user's OWN installed browser — we never install
            # a system browser. If none is present, just point them at an option.
            if _pw_scrape.find_installed_browser():
                self.status_var.set(t("Using your installed {name}.", name=kind))
                return
            messagebox.showinfo(
                "Chrome not found",
                "Google Chrome wasn't found on your system.\n\nInstall Chrome, or use "
                "Firefox or the built-in Chromium instead.")
            self.browser_choice.set("Built-in")

    def _start_component_download(self, target):
        """Download a Playwright BROWSER COMPONENT (e.g. Firefox) into the app's
        data folder — NOT cheat files. Separate from _start_browser_download,
        which downloads cheats via the logged-in browser."""
        self._stop_event.clear()
        self._set_busy(True)
        self._update_dlg = UpdateProgressDialog(self.root, on_cancel=self._cancel_update)
        self._update_dlg.set_phase(t("Downloading {name}…", name=target.capitalize()))
        self.status_var.set(t("Downloading {name}…", name=target))
        threading.Thread(target=self._browser_download_worker,
                         args=(target,), daemon=True).start()

    def _browser_download_worker(self, target):
        # Only self-contained browser components (Firefox) are downloaded — into
        # the app's data folder. We never install a system-wide browser.
        def cb(pct, line):
            self._log_queue.put(("progress", pct, 100, f"Downloading {target}: {pct}%"))
        try:
            ok = _pw_scrape.install_browser_userdir(
                target, progress_cb=cb,
                log=lambda m: self._log_queue.put(str(m)),
                should_stop=self._stop_event.is_set)
            self._log_queue.put(("browser_dl_done", target, bool(ok)))
        except Exception as exc:
            self._log_queue.put(("error", f"Browser download failed:\n{exc}"))
            self._log_queue.put(("browser_dl_done", target, False))

    def _secret_entry(self, parent, var, width):
        """A masked entry (•••) with a small show/hide toggle button.
        Returns (entry, button) — the caller packs them."""
        ent = ttk.Entry(parent, textvariable=var, show="•", width=width)
        state = {"shown": False}

        def toggle():
            state["shown"] = not state["shown"]
            ent.config(show="" if state["shown"] else "•")
            btn.config(text="hide" if state["shown"] else "show")

        btn = ttk.Button(parent, text="show", width=9, command=toggle)
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
            t(message) + "\n\n" + t("Afterwards: names + covers + region, versions "
                                    "(titledb only) and a\ncheat-count recount from disk."),
        ):
            return
        self._save_settings()
        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set(t("Downloading {name}...", name=label))
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
            t("Scan the {pages} most recent 'latest cheat codes' page(s) on "
              "cheatslips.com\nand add any new builds - this also re-checks "
              "games already in the database\nthat show up there, since that "
              "means cheatslips just updated them.\n\nMuch faster than a full "
              "rescan since only the recent pages are fetched.", pages=pages),
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
        self.status_var.set(t("Added {tid}/{bid} ({n} cheat(s)).", tid=tid, bid=bid, n=len(names)))
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
        self.status_var.set(t(label) + "...")
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
            t("Import cheats from:\n{path}\n\nAdd them to the database and the "
              "output folder?", path=zpath),
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
                t("No titles/ or by_bid/ folder found in:\n{path}\n\n"
                  "Download or place cheat files there first.", path=out),
            )
            return
        if not messagebox.askyesno(
            "Import disk",
            t("Scan {path} for titles/ and by_bid/ cheat files and import missing entries into the DB?\n\n"
              "Known build ids (e.g. Potion Permit) will be linked automatically.", path=out),
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
        self._backup_db("Fix ID names")
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
        self._backup_db("Sync titles")
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
            t("{n} game(s) have entries with 0 cheats.\n"
              "Refresh them from the API and download their cheat codes?",
              n=len(tids)),
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
            "browser_fallback": self.browser_fallback.get(),
            "browser": self._browser_kind(),
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
                    saved = self._api_download(api, db, Path(cfg["output"]), cfg,
                                               title_ids=title_ids, progress_cb=dprog)
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
        self._backup_db("Recount cheats")
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
        self._backup_db("Clean invalid")
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
                    t("{n} build(s) are marked as having no codes on cheatslips and "
                      "are skipped during downloads.\n\nClear these marks so they are "
                      "retried on the next download?", n=n)):
                    return
                cleared = db.clear_unavailable()
            finally:
                db.close()
        except Exception as exc:
            messagebox.showerror("Retry 'unavailable' builds", str(exc))
            return
        self.status_var.set(
            t("Cleared {n} 'unavailable' mark(s) — they will be retried next download.", n=cleared))
        self.refresh_table()

    def on_retry_quota_skipped(self):
        if self._busy:
            return
        quota_file = Path(self.dl_output.get()) / "quota_skipped.txt"
        if not quota_file.exists():
            messagebox.showinfo(
                "Retry quota-skipped builds",
                t("No quota-skipped list found.\n\nExpected file:\n{path}\n\n"
                  "Run a download first; skipped builds are recorded automatically.",
                  path=quota_file))
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
            t("Retry {n} build(s) from {name}?\n\n"
              "Make sure your quota has reset first.", n=len(pairs), name=quota_file.name),
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
            "browser_fallback": self.browser_fallback.get(),
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
                # Enrich each (tid, bid) with slug/source_id from the DB so the
                # browser fallback can reach the right game page. The reset loop
                # downloads via the API and resets the quota whenever the limit is
                # hit, so the whole retry set gets fetched.
                lookup = {(t.upper(), b.upper()): (slug, sid)
                          for t, b, slug, sid in db.builds_for_download()}
                enriched = []
                for tid, bid in cfg["pairs"]:
                    slug, sid = lookup.get((tid.upper(), bid.upper()), ("", ""))
                    enriched.append((tid, bid, slug, sid))
                saved = self._run_quota_reset_loop(api, db, out, enriched, cfg)
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
        self.status_var.set(t("Copied {n} row(s) to clipboard.", n=len(sel)))
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
            self.status_var.set(t("Copied: {value}", value=values[idx]))

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
            messagebox.showerror("Open folder",
                                 t("Could not open:\n{path}\n\n{err}",
                                   path=path, err=exc))

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
            messagebox.showerror("Export CSV", t("Failed: {err}", err=exc))
            return
        self.status_var.set(t("Exported {n} row(s) to {dest}", n=n, dest=dest))
        messagebox.showinfo("Export CSV", t(
            "Exported {n} row(s) to:\n{dest}\n\n"
            "Columns included:\n"
            "• Game Title, Title/Build ID, Version, Upload Date\n"
            "• Cheat Count & Names, Credits, Description\n"
            "• Cover/Banner URLs, Source (GBatemp/titledb/cheatslips)\n"
            "• Publisher, Developer, Genre, Release Date\n"
            "• Player Count, Size, Rating, and more", n=n, dest=dest))

    def on_export_db(self):
        """Export a copy of the whole SQLite database (cheats.db).

        Offers a SHARE mode that strips the publisher eShop text
        (game_description / intro) so a database you redistribute carries only
        facts, cheats and community notes — smaller and copyright-clean. Your
        live database is never modified."""
        src = Path(self.db_path.get())
        if not src.exists():
            messagebox.showwarning("Export database", "No database file yet. Scrape first.")
            return
        # yes = optimise for sharing (strip), no = full copy, cancel = abort.
        share = messagebox.askyesnocancel(
            t("Export database"),
            t("Optimise this export for sharing?\n\n"
              "YES  — remove the game descriptions (Nintendo eShop text) so the "
              "shared database is smaller and copyright-clean. Cheats, names, "
              "versions and credits are kept.\n"
              "NO   — export a full 1:1 copy (keeps descriptions).\n\n"
              "Your live database is not changed either way."),
            parent=self.root)
        if share is None:
            return
        dest = filedialog.asksaveasfilename(
            title=t("Export database"),
            defaultextension=".db", initialfile="database.db",
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")])
        if not dest:
            return
        if Path(dest).resolve() == src.resolve():
            messagebox.showwarning("Export database",
                                   "Choose a different file than the live database.")
            return
        try:
            res = export_shared_db(src, dest, strip_publisher_text=bool(share))
        except Exception as exc:
            messagebox.showerror("Export database", t("Failed: {err}", err=exc))
            return
        size_mb = res.get("_after", 0) / (1024 * 1024)
        if share:
            cleared = res.get("game_description", 0)
            self.status_var.set(
                t("Database exported (share) to {dest} — {n} description(s) "
                  "removed, {size} MB", dest=dest, n=cleared, size=f"{size_mb:.1f}"))
            messagebox.showinfo(
                t("Export database"),
                t("Share database exported to:\n{dest}\n\n"
                  "{n} game description(s) removed · {size} MB\n\n"
                  "Ready to upload as the shared 'database.db'.",
                  dest=dest, n=cleared, size=f"{size_mb:.1f}"), parent=self.root)
        else:
            self.status_var.set(t("Database exported to {dest} ({size} MB)",
                                  dest=dest, size=f"{size_mb:.1f}"))
            messagebox.showinfo("Export database",
                                t("Full database exported to:\n{dest}\n\n{size} MB",
                                  dest=dest, size=f"{size_mb:.1f}"), parent=self.root)

    def on_export_names(self):
        """Export a lightweight Title ID → game name map (names.json).

        The Android downloader fetches this from the `data` release to name each
        game's cheat folder (load/<TitleID>/<GameName>/cheats/<BuildID>.txt).
        """
        import collections as _collections
        import json as _json
        import re as _re
        import sqlite3 as _sqlite3

        src = Path(self.db_path.get())
        if not src.exists():
            messagebox.showwarning("Export names.json",
                                   t("No database file yet. Scrape first."))
            return
        dest = filedialog.asksaveasfilename(
            title="Export names.json",
            defaultextension=".json",
            initialfile="names.json",
            initialdir=str(DATA_DIR),
            filetypes=[("JSON file", "*.json"), ("All files", "*.*")],
        )
        if not dest:
            return

        _invalid = _re.compile(r'[\\/:*?"<>|\x00-\x1f]')
        # Trademark / service marks / replacement char, as \u escapes so the
        # source stays encoding-safe: (TM) (R) (C) (P) (SM) and U+FFFD.
        _symbols = _re.compile("[™®©℗℠�]")

        def _clean(name):
            n = _symbols.sub("", name or "")
            n = n.replace("–", "-").replace("—", "-")  # en/em dash -> hyphen
            n = _invalid.sub("", n)
            n = _re.sub(r"\s+", " ", n).strip().strip(".").strip()
            return n[:60].strip()

        best = {}
        con = None
        try:
            con = _sqlite3.connect(str(src))
            con.row_factory = _sqlite3.Row
            # For each Title ID, count the cleaned names and keep the most common
            # one (ties broken by the shortest — the cleaner canonical title).
            buckets = _collections.defaultdict(_collections.Counter)
            for r in con.execute(
                    "SELECT title_id, game_title FROM builds "
                    "WHERE game_title IS NOT NULL AND game_title <> ''"):
                tid = (r["title_id"] or "").strip().upper()
                if len(tid) != 16:
                    continue
                name = _clean(r["game_title"])
                if name:
                    buckets[tid][name] += 1
            best = {tid: sorted(ctr.items(), key=lambda kv: (-kv[1], len(kv[0])))[0][0]
                    for tid, ctr in buckets.items()}
            with open(dest, "w", encoding="utf-8") as f:
                _json.dump(best, f, ensure_ascii=False,
                           separators=(",", ":"), sort_keys=True)
        except Exception as exc:
            messagebox.showerror("Export names.json", t("Failed: {err}", err=exc))
            return
        finally:
            if con is not None:
                try:
                    con.close()
                except Exception:
                    pass

        self.status_var.set(t("names.json exported: {n} games", n=len(best)))
        messagebox.showinfo(
            "Export names.json",
            t("names.json exported to:\n{dest}\n\n{n} games\n\nUpload it to the "
              "'data' release so the Android app always gets current game names.",
              dest=dest, n=len(best)))

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
                                 t("Not a valid database file:\n{err}", err=exc))
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

        self._backup_db("Import DB")
        self._stop_event.clear()
        self._set_busy(True)
        self.status_var.set(t("Importing database ({mode})...", mode=mode))
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
                t("Download cheat files for all {n} game(s) via the official API "
                  "(no browser downloads)?\n\nAlready-downloaded builds are skipped. "
                  "When the API limit is hit, the quota is reset automatically and "
                  "the download continues — the browser opens only for those "
                  "resets.", n=n)):
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
            t("Build a complete dataset for {n} game(s)?\nRuns in order:\n"
              "  1. Download all cheat files (API)\n"
              "  2. Fill names, region + versions (titledb / API)\n"
              "  3. Fix ID names\n"
              "  4. Fix 0-cheat entries\n\n"
              "Each step continues even if a previous one fails.\n"
              "Already-downloaded builds are skipped automatically.", n=n),
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
            "browser_fallback": self.browser_fallback.get(),
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
                            saved = self._api_download(api, db, Path(cfg["output"]), cfg,
                                                       progress_cb=dprog)
                            print(f"Downloaded {saved} new file(s).")
                            cleanup_invalid_cheat_entries(db, Path(cfg["output"]), should_stop=stopped)
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
                                saved = self._api_download(api, db, Path(cfg["output"]),
                                                           cfg, title_ids=tids)
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

    def _api_download(self, api, db, out, cfg, title_ids=None, progress_cb=None) -> int:
        """Single entry point for downloading cheat CONTENT via the API.

        cheatslips' content API has a tiny per-window limit (~3 requests) that
        ONLY the browser quota reset refills. So this ALWAYS runs the reset loop:
        get_game per title, and every time the limit is hit it presses the reset
        button and continues — so a whole selection loads, not just the first
        few. The browser opens for the resets (and, when the browser-download
        option is on, for codes that exist only on the website).

        Used by every download flow (Download, Download via API, Scrape &
        Download Everything, Build Full Dataset, 0-cheat fix) so a marked-but-not-
        downloaded set always loads completely. Returns the number of files saved.
        """
        out = Path(out)
        pairs = missing_build_pairs(db, out)
        if title_ids:
            wanted = {(t or "").upper() for t in title_ids}
            pairs = [p for p in pairs if (p[0] or "").upper() in wanted]
        if not pairs:
            print("Nothing left to download via the API.")
            return 0
        return self._run_quota_reset_loop(api, db, out, pairs, cfg)

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

        print(f"\n=== Download: {len(pairs)} build(s) still missing ===")
        print("Fastest path first: cheats are pulled through the API (one request "
              "per game covers all its builds); when the API limit is hit the quota "
              "is reset in the browser and the API continues — no per-build browser "
              "downloads. Only codes that exist ONLY on the website are fetched via "
              "the browser afterwards.")
        print("A browser window will open (needed for the quota reset + the final "
              "website-only pass). Log in once (solve the reCAPTCHA if asked); with "
              "saved cookies the login is automatic on later runs.")
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
                if not session.reset_quota():
                    return False
                # After a quota reset the API token must be re-requested, otherwise
                # the API keeps returning the 'quota exceeded' message and the retry
                # saves nothing. Refresh it so the refilled quota is actually seen.
                try:
                    if cfg.get("email") and cfg.get("password"):
                        api.get_token(cfg["email"], cfg["password"])
                    elif getattr(api, "email", None) and getattr(api, "password", None):
                        api.get_token(api.email, api.password)
                except Exception as exc:
                    print(f"  (Could not refresh the API token after reset: {exc})")
                return True

            def browser_dl(slug, tid, bid, sid):
                if self._stop_event.is_set():
                    return None
                return session.download_build(slug, tid, bid, out, sid)

            # The quota reset ALWAYS uses the browser. The per-build browser
            # download (Phase B — for codes that exist only on the website) is
            # optional and controlled by the "download via browser when the API
            # is limited" flag; with it off we still reset + pull via the API.
            browser_cb = browser_dl if cfg.get("browser_fallback", False) else None

            def prog(done, total):
                self._log_queue.put(("progress", done, total,
                                     f"Downloading {done}/{total}"))

            return download_with_quota_reset(
                api, db, out, pairs,
                reset_cb=reset_cb,
                browser_download_cb=browser_cb,
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
        # "Download this / Selected" is a TARGETED action: get these builds by any
        # means — API first (with quota resets), then the browser for whatever the
        # API doesn't list (many builds scraped from the website are not on the
        # API). So the browser fallback is always ON here (the checkbox only gates
        # the bulk flows, where thousands of slow browser downloads are unwanted).
        cfg = {
            "email": self.email_var.get().strip() or None,
            "password": self.password_var.get() or None,
            "token": self.api_token_var.get().strip() or None,
            "output": self.dl_output.get(),
            "db_path": self.db_path.get(),
            "browser_fallback": True,
            "browser": self._browser_kind(),
        }
        threading.Thread(
            target=self._download_worker, args=(title_ids, cfg), daemon=True
        ).start()

    def _start_api_download(self, title_ids):
        """Download via the official API — no per-build BROWSER download, but the
        API quota reset IS used, so a whole selection loads even past the API's
        tiny per-window limit: it fetches via the API, and every time the limit
        is hit it presses the reset and continues. The browser opens only for
        those resets, never to download cheats."""
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
            "browser_fallback": False,  # API only — never DOWNLOAD via the browser
            "browser": self._browser_kind(),
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
                tracker = ProgressTracker("download")
                def progress(done, total):
                    tracker.update(done, total)
                    msg = f"Downloaded {done}/{total} ({tracker.pct()}%) | {tracker.rate_str('items')} | ~{tracker.eta_str()} remaining"
                    self._log_queue.put(("progress", done, total, msg))

                saved = self._api_download(api, db, out, cfg, title_ids=title_ids,
                                           progress_cb=progress)
                print(f"Download finished - {saved} new file(s).")
                # Delete any files that only contain a quota/placeholder message and
                # reset their database entries so they are re-tried after a reset.
                cleaned = cleanup_invalid_cheat_entries(
                    db, out, should_stop=self._stop_event.is_set)
                if cleaned:
                    print(f"Cleaned up {cleaned} invalid cheat entries.")
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
            # True = a cheat-file download finished -> auto-refresh like the
            # Refresh button (recount from disk + rescan) so the row updates.
            self._log_queue.put(("download_done", True))

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
            dlg = getattr(self, "_update_dlg", None)
            if dlg:
                dlg.set_progress(done, total, label or "")
        elif kind == "update_phase":
            dlg = getattr(self, "_update_dlg", None)
            if dlg:
                dlg.busy(msg[1], msg[2] if len(msg) > 2 else "")
            self.status_var.set(msg[1])
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
        elif kind == "emu_export_done":
            self._finish_emulator_export(msg[1], msg[2], msg[3])
        elif kind == "import_db_done":
            self._finish_import_db(msg[1])
        elif kind == "devcat_done":
            self._finish_devcat(msg[1], msg[2],
                                msg[3] if len(msg) > 3 else None)
        elif kind == "switchapp_done":
            self._finish_switch_app(msg[1], msg[2])
        elif kind == "androidapp_done":
            self._finish_android_app(msg[1], msg[2])
        elif kind == "invalid_scan_done":
            self._finish_invalid_scan(msg[1])
        elif kind == "run_installer":
            self._set_busy(False)
            path = msg[1]
            try:
                import ctypes
                ctypes.windll.shell32.ShellExecuteW(None, "open", path, "", None, 1)
                self.status_var.set(t("Installer started — follow its steps, then "
                                      "you can remove the old version."))
            except Exception as exc:
                messagebox.showerror("Installer", str(exc))
        elif kind == "update_result":
            self._handle_update_result(msg[1], msg[2])
        elif kind == "update_error":
            self._handle_update_error(msg[1], msg[2])
        elif kind == "program_update_ready":
            self._apply_program_update(msg[1], msg[2], msg[3])
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
            else:
                self._toast(t("Scrape finished"),
                            t("The scrape is done — the results are in the table."))
        elif kind == "download_done":
            dlg = getattr(self, "_update_dlg", None)
            if dlg:
                dlg.close(); self._update_dlg = None
            self._set_busy(False)
            self._update_downloaded_cache_incremental()
            # After a cheat-file download (Download this / via API / via browser),
            # auto-refresh exactly like the Refresh button: recount cheats from disk
            # + live rescan, so the just-downloaded build flips to "downloaded" and
            # shows its real cheat count. Other operations reusing this event keep
            # the lightweight cached redraw.
            if len(msg) > 1 and msg[1] and Path(self.db_path.get()).exists():
                self.on_refresh()
            else:
                self.refresh_table()
        elif kind == "browser_dl_done":
            target, ok = msg[1], msg[2]
            dlg = getattr(self, "_update_dlg", None)
            if dlg:
                dlg.close(); self._update_dlg = None
            self._set_busy(False)
            if ok:
                self._append_log(f"{target.capitalize()} downloaded — ready to use.")
                self.status_var.set(t("{name} ready.", name=target.capitalize()))
            else:
                self.browser_choice.set("Built-in")   # revert to the built-in browser
                self.status_var.set(t("Browser download cancelled/failed — using Built-in."))
        elif kind == "refresh_done":
            self._set_busy(False)
            self.refresh_table(force_scan=True)
        elif kind == "everything_done":
            self.everything_btn.config(text="★ Scrape & Download Everything")
            self._set_busy(False)
            self._update_downloaded_cache_incremental()
            self.refresh_table()
            self.status_var.set(t("Scrape & Download Everything finished."))
        elif kind == "update_done":
            new_builds = msg[1] if len(msg) > 1 else 0
            self.update_btn.config(text="Update Recent")
            self._set_busy(False)
            self._update_downloaded_cache_incremental()
            self.refresh_table()
            if new_builds and self.auto_download.get() and not self._stop_event.is_set():
                self.status_var.set(t("{n} new build(s) found - starting download...", n=new_builds))
                self.root.after(500, lambda: self._start_download(None))
            else:
                self.status_var.set(t("Update done - {n} new build(s) found.", n=new_builds))

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
