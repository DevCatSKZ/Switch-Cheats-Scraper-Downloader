"""Modern Holo-Glass shell for Switch Cheats Scraper & Downloader.

A complete visual re-architecture of the desktop tool: header bar, sidebar
navigation, task-focused pages and a persistent status footer — while sharing
100% of the widgets, handlers and behaviour with the proven classic UI
(gui.ScraperGUI). Nothing was forked: the section builders in gui.py are
simply composed into a different, modern layout.

Run:      py gui_modern.py
Classic:  py gui.py          (unchanged, always available as fallback)
"""

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import i18n
from i18n import t
from gui import (ScraperGUI, theme, _Tooltip, _BROWSER_KINDS, _fmt_size,
                 COLUMNS, APP_NAME, APP_AUTHOR, APP_VERSION)


# Sidebar navigation: (key, glyph, label). Labels are static English keys —
# the i18n auto-hook translates them like every other widget text.
_NAV = [
    ("home",     "⌂",  "Home"),
    ("library",  "▤",  "Library"),
    ("sources",  "☁",  "Sources"),
    ("scrape",   "⇣",  "CheatSlips"),
    ("settings", "⚙",  "Settings"),
    ("log",      "≡",  "Log"),
]

# Short "what's on this page" hints for the sidebar (Alt+n shortcut appended).
_NAV_TIPS = {
    "home":     "Dashboard: your library at a glance, one-click downloads and updates.",
    "library":  "Search, browse and manage every cheat; double-click a game for its page.",
    "sources":  "Import cheats from 9+ community archives and enrich the metadata.",
    "scrape":   "Scrape cheatslips.com and download the cheat files.",
    "settings": "Updates, downloads, covers and paths — all in one place.",
    "log":      "Everything the app did this session.",
}

# The Holo-Glass secondary accent (electric violet), straight from the
# project's landing page — used sparingly for highlights next to the teal.
_VIOLET = "#7c5cff"


def _spaced(word: str) -> str:
    """Fake the landing page's letter-spaced eyebrow labels in tk."""
    return " ".join(word.upper())


class ModernApp(ScraperGUI):
    """The modern shell: same engine, new professional layout."""

    def __init__(self, root):
        super().__init__(root)
        # The modern shell always opens in an OPTIMAL windowed size — never
        # maximized/fullscreen and never the classic UI's saved giant geometry.
        # Users can still resize or maximize during the session; the next start
        # is tidy again.
        try:
            root.state("normal")
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            w = min(1560, sw - 120)
            h = min(1000, sh - 140)
            x = max(0, (sw - w) // 2)
            y = max(0, (sh - h) // 2 - 20)
            root.geometry(f"{w}x{h}+{x}+{y}")
            root.minsize(min(1280, w), min(840, h))
        except Exception:
            pass

    # ---------------------------------------------------------- glass helper
    def _glass_card(self, parent, padding=(16, 12)):
        """A Holo-Glass panel: 1px teal-glass hairline border around a tinted
        surface — the landing page's card look, in tk. Returns the inner frame."""
        border = tk.Frame(parent, bd=0, highlightthickness=0)
        inner = ttk.Frame(border, style="Glass.TFrame", padding=padding)
        inner.pack(padx=1, pady=1, fill="both", expand=True)
        self._glass_borders = getattr(self, "_glass_borders", []) + [border]
        return border, inner

    def _hairline(self, parent, pady=(0, 12)):
        """A 1px separator line in the glass-border colour."""
        line = tk.Frame(parent, height=1, bd=0, highlightthickness=0)
        line.pack(fill="x", pady=pady)
        self._hairlines = getattr(self, "_hairlines", []) + [line]
        return line

    def _outline_card(self, parent, padding=(16, 12)):
        """A teal-glass-bordered panel whose INTERIOR is the page background —
        so the shared classic sections (LabelFrames, buttons) drop straight in
        without any surface/background mismatch. Returns the inner frame."""
        border = tk.Frame(parent, bd=0, highlightthickness=0)
        inner = ttk.Frame(border, style="Body.TFrame", padding=padding)
        inner.pack(padx=1, pady=1, fill="both", expand=True)
        self._glass_borders = getattr(self, "_glass_borders", []) + [border]
        return border, inner

    def _build_activity_panel(self, parent):
        """A live log tail (glass card) — fills the empty space on the Sources /
        CheatSlips pages and mirrors every log line as it happens."""
        c = theme()
        b, card = self._glass_card(parent, padding=(14, 10))
        b.pack(fill="both", expand=True, pady=(4, 0))
        ttk.Label(card, text=t("Activity"), style="CardTitle.TLabel").pack(anchor="w")
        self._hairline(card, pady=(7, 6))
        box = ttk.Frame(card, style="Glass.TFrame")
        box.pack(fill="both", expand=True)
        txt = tk.Text(box, height=8, wrap="none", state="disabled",
                      bg=c["log_bg"], fg=c["log_fg"], font=("Consolas", 9),
                      relief="flat", highlightthickness=0, padx=8, pady=6)
        sb = ttk.Scrollbar(box, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._activity_texts = getattr(self, "_activity_texts", []) + [txt]
        return txt

    def _append_log(self, msg):
        """Mirror every log line into the on-page Activity panels too."""
        super()._append_log(msg)
        for txt in getattr(self, "_activity_texts", []):
            try:
                txt.config(state="normal")
                txt.insert("end", msg + "\n")
                end = int(txt.index("end-1c").split(".")[0])
                if end > 320:                       # keep it bounded
                    txt.delete("1.0", f"{end - 300}.0")
                txt.see("end")
                txt.config(state="disabled")
            except Exception:
                pass

    # ------------------------------------------------------------ composition
    def _compose_ui(self):
        root = self.root
        # Action buttons get collected here so _set_busy can disable them all
        # (classic initialises this in _build_toolbar, which we don't use).
        self._action_buttons = []

        # ---------- header ------------------------------------------------
        self._header = ttk.Frame(root, style="Hdr.TFrame", padding=(18, 10, 14, 10))
        self._header.pack(fill="x")
        brand = ttk.Frame(self._header, style="Hdr.TFrame")
        brand.pack(side="left")
        # Real app icon in the header (falls back to a glyph without PIL/app.ico).
        self._hdr_icon_img = None
        try:
            from PIL import Image, ImageTk
            from pathlib import Path as _P
            ico = _P(__file__).with_name("app.ico")
            if ico.exists():
                img = Image.open(ico)
                img = img.resize((34, 34), Image.LANCZOS)
                self._hdr_icon_img = ImageTk.PhotoImage(img)
        except Exception:
            self._hdr_icon_img = None
        if self._hdr_icon_img is not None:
            self._hdr_glyph = ttk.Label(brand, image=self._hdr_icon_img,
                                        style="Hdr.TLabel")
        else:
            self._hdr_glyph = ttk.Label(brand, text="◉", style="HdrGlyph.TLabel")
        self._hdr_glyph.pack(side="left", padx=(0, 10))
        names = ttk.Frame(brand, style="Hdr.TFrame")
        names.pack(side="left")
        self._hdr_title = ttk.Label(names, text="Switch Cheats", style="HdrTitle.TLabel")
        self._hdr_title.pack(anchor="w")
        self._hdr_sub = ttk.Label(names, text="Scraper & Downloader",
                                  style="HdrSub.TLabel")
        self._hdr_sub.pack(anchor="w")
        self._hdr_ver = ttk.Label(self._header, text=f"  v{APP_VERSION}  ",
                                  style="HdrPill.TLabel")
        self._hdr_ver.pack(side="left", padx=(14, 0))
        # A quiet hint that Ctrl+K opens the command palette.
        self._hdr_hint = ttk.Label(self._header, text="  ⌕  Ctrl+K  ",
                                   style="HdrHint.TLabel", cursor="hand2")
        self._hdr_hint.pack(side="left", padx=(10, 0))
        self._hdr_hint.bind("<Button-1>", lambda _e: self._open_command_palette())
        # Theme + language pickers on the right of the header.
        self._build_theme_lang_pickers(self._header, side="right")
        # Notification bell (with unseen-count badge) + a busy dot, left of the
        # pickers.
        self._notifications = []      # (epoch_or_None, title, message)
        self._notif_unseen = 0
        self._hdr_busy = ttk.Label(self._header, text="●", style="HdrBusy.TLabel")
        self._hdr_busy.pack(side="right", padx=(10, 10))
        _Tooltip(self._hdr_busy, "Lights up while a task (scrape, download, "
                                 "import…) is running.")
        self._bell_btn = ttk.Label(self._header, text="🔔", style="HdrBell.TLabel",
                                   cursor="hand2")
        self._bell_btn.pack(side="right", padx=(6, 0))
        self._bell_btn.bind("<Button-1>", lambda _e: self._open_notifications())
        _Tooltip(self._bell_btn, "Notifications — every toast this session "
                                 "(scrape done, updates, favourites…).")
        _Tooltip(self._hdr_hint, "Open the command palette: jump to any game or "
                                 "run an action. Shortcut: Ctrl+K.")
        # 1px accent hairline under the header.
        self._hdr_line = tk.Frame(root, height=1, bd=0, highlightthickness=0)
        self._hdr_line.pack(fill="x")

        # ---------- body: sidebar + stacked pages --------------------------
        body = ttk.Frame(root, style="Body.TFrame")
        body.pack(fill="both", expand=True)

        self._sidebar = ttk.Frame(body, style="Side.TFrame", padding=(10, 14, 10, 12))
        self._sidebar.pack(side="left", fill="y")
        # 1px glass hairline between sidebar and content.
        self._side_edge = tk.Frame(body, width=1, bd=0, highlightthickness=0)
        self._side_edge.pack(side="left", fill="y")
        content = ttk.Frame(body, style="Body.TFrame")
        content.pack(side="left", fill="both", expand=True)
        # Sidebar eyebrow, landing-page style.
        self._side_eyebrow = ttk.Label(self._sidebar, text=_spaced("Menu"),
                                       style="SideEyebrow.TLabel")
        self._side_eyebrow.pack(anchor="w", padx=8, pady=(0, 8))
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)

        self._pages: dict[str, ttk.Frame] = {}
        self._nav_btns: dict[str, tk.Button] = {}
        self._nav_marks: dict[str, tk.Frame] = {}
        self._nav_badges: dict[str, tk.Label] = {}
        self._nav_order = [k for k, _g, _l in _NAV]
        for key, glyph, label in _NAV:
            page = ttk.Frame(content, style="Body.TFrame", padding=(18, 12, 18, 10))
            page.grid(row=0, column=0, sticky="nsew")
            self._pages[key] = page
            row = tk.Frame(self._sidebar, bd=0, highlightthickness=0)
            row.pack(fill="x", pady=2)
            # Holo touch: a 3px teal indicator bar marks the active page.
            mark = tk.Frame(row, width=3, bd=0, highlightthickness=0)
            mark.pack(side="left", fill="y")
            btn = tk.Button(row, text=f"  {glyph}   {t(label)}",
                            anchor="w", relief="flat", bd=0, cursor="hand2",
                            font=("Segoe UI", 11), padx=10, pady=9,
                            command=lambda k=key: self._select_page(k))
            btn.pack(side="left", fill="x", expand=True)
            tip = _NAV_TIPS.get(key, "")
            if tip:
                _Tooltip(btn, tip + f"  (Alt+{len(self._nav_btns) + 1})")
            # A count badge (currently only the Library shows the games total).
            badge = tk.Label(row, text="", bd=0, font=("Segoe UI", 8),
                             padx=6, highlightthickness=0)
            badge.pack(side="right", padx=(0, 8))
            self._nav_btns[key] = btn
            self._nav_marks[key] = mark
            self._nav_badges[key] = badge
            self._nav_rows = getattr(self, "_nav_rows", []) + [row]
        # Author credit pinned at the sidebar bottom.
        self._side_credit = ttk.Label(self._sidebar, text=f"by {APP_AUTHOR}",
                                      style="SideCredit.TLabel")
        self._side_credit.pack(side="bottom", pady=(10, 2))

        # Hidden page (no sidebar entry): the per-game detail view, opened by
        # double-clicking a row in the Library or a name on the Home page.
        detail = ttk.Frame(content, style="Body.TFrame", padding=(18, 12, 18, 10))
        detail.grid(row=0, column=0, sticky="nsew")
        self._pages["detail"] = detail

        # ---------- pages ---------------------------------------------------
        self._build_home_page(self._pages["home"])
        self._build_library_page(self._pages["library"])
        self._build_sources_page(self._pages["sources"])
        self._build_scrape_page(self._pages["scrape"])
        self._build_settings_page(self._pages["settings"])
        self._build_log_page(self._pages["log"])
        self._build_detail_page(self._pages["detail"])

        # ---------- footer --------------------------------------------------
        self._footer_line = tk.Frame(root, height=1, bd=0, highlightthickness=0)
        self._footer_line.pack(fill="x")
        self._footer = ttk.Frame(root, style="Foot.TFrame", padding=(16, 7))
        self._footer.pack(fill="x")
        ttk.Label(self._footer, textvariable=self.status_var,
                  style="FootStatus.TLabel").pack(side="left")
        self.progress = ttk.Progressbar(self._footer, mode="determinate", length=260)
        self.progress.pack(side="right")
        self.footer_stop_btn = ttk.Button(self._footer, text="Stop",
                                          command=self.on_stop, state="disabled")
        self.footer_stop_btn.pack(side="right", padx=(0, 12))

        # ---------- keyboard: Alt+1..N pages, Esc back, Ctrl+K palette ------
        for i, key in enumerate(self._nav_order, 1):
            root.bind(f"<Alt-Key-{i}>", lambda _e, k=key: self._select_page(k))
        root.bind("<Escape>", self._on_escape)
        root.bind("<Control-k>", lambda _e: self._open_command_palette())
        root.bind("<Control-K>", lambda _e: self._open_command_palette())

        self._select_page("home")
        self._paint_modern()   # colour everything for the current theme
        self._update_nav_badge()

    # ---------------------------------------------------------------- pages
    def _page_title(self, page, eyebrow, title, subtitle):
        """Landing-page style page head: letter-spaced teal eyebrow, big title,
        muted subtitle — the Holo-Glass signature."""
        head = ttk.Frame(page, style="Body.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="—  " + _spaced(t(eyebrow)),
                  style="Eyebrow.TLabel").pack(anchor="w")
        ttk.Label(head, text=title, style="PageTitle.TLabel").pack(anchor="w", pady=(3, 0))
        ttk.Label(head, text=subtitle, style="PageSub.TLabel").pack(anchor="w")
        self._hairline(page, pady=(10, 14))
        return head

    def _dash_stat(self, parent, key, sub, violet=False):
        """One glass stat card with a live-updated big value + sub label."""
        border, card = self._glass_card(parent, padding=(18, 13))
        border.pack(side="left", fill="both", expand=True, padx=(0, 12))
        var = tk.StringVar(value="—")
        self._dash_vars[key] = var
        ttk.Label(card, textvariable=var,
                  style="StatBigV.TLabel" if violet else "StatBig.TLabel").pack(anchor="w")
        ttk.Label(card, text=sub, style="StatSub.TLabel").pack(anchor="w")
        return card

    def _build_home_page(self, page):
        self._page_title(page, "Overview", "Home",
                         "Everything for your Switch cheats — collected, managed, delivered.")
        self._dash_vars: dict[str, tk.StringVar] = {}

        # ---- live stat cards -------------------------------------------
        stats = ttk.Frame(page, style="Body.TFrame")
        stats.pack(fill="x", pady=(0, 6))
        self._dash_stat(stats, "games", t("games in your database"))
        self._dash_stat(stats, "cheats", t("cheats total"))
        self._dash_stat(stats, "downloaded", t("downloaded"))
        self._dash_stat(stats, "db_size", t("database size"), violet=True)
        # spacer so the 4th card doesn't get a trailing gap
        ttk.Frame(stats, style="Body.TFrame", width=0).pack(side="left")

        self._dash_data_var = tk.StringVar(value="")
        ttk.Label(page, textvariable=self._dash_data_var,
                  style="PageSub.TLabel").pack(anchor="w", pady=(2, 12))

        # ---- two columns: DevCat hero (left) + recently updated (right) --
        cols = ttk.Frame(page, style="Body.TFrame")
        cols.pack(fill="both", expand=True)
        leftcol = ttk.Frame(cols, style="Body.TFrame")
        leftcol.pack(side="left", fill="both", expand=True, padx=(0, 10))
        rightcol = ttk.Frame(cols, style="Body.TFrame")
        rightcol.pack(side="left", fill="both", expand=True, padx=(10, 0))

        # The featured DevCat card (downloads, updates, Switch app).
        self._build_devcat_card(leftcol, beside_grid=False)

        rb, recent = self._glass_card(rightcol, padding=(16, 12))
        rb.pack(fill="both", expand=True)
        ttk.Label(recent, text=t("Recently updated"),
                  style="CardTitle.TLabel").pack(anchor="w")
        self._hairline(recent, pady=(7, 6))
        self._recent_host = ttk.Frame(recent, style="Glass.TFrame")
        self._recent_host.pack(fill="both", expand=True)

        self._refresh_dashboard()

    def _refresh_dashboard(self):
        """Paint the Home stats INSTANTLY from the cache, then reconcile against
        disk in the background — no more empty '—' cards on every visit."""
        if not hasattr(self, "_dash_vars"):
            return
        import threading
        output = self.dl_output.get()   # Tk var snapshot on the main thread

        def work():
            # 1) cached numbers → immediate paint
            try:
                fast = self._dashboard_stats(output, fast=True)
                self.root.after(0, lambda: self._paint_dashboard(fast))
            except Exception:
                pass
            # 2) live disk scan → repaint if the downloaded count changed
            try:
                live = self._dashboard_stats(output, fast=False)
                self.root.after(0, lambda: self._paint_dashboard(live))
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _paint_dashboard(self, s):
        v = self._dash_vars
        if "games" in v:
            v["games"].set(f"{s['games']:,}")
        if "cheats" in v:
            v["cheats"].set(f"{s['cheats']:,}")
        if "downloaded" in v:
            pct = (100 * s["downloaded"] // s["builds"]) if s["builds"] else 0
            v["downloaded"].set(f"{pct}%")
        if "db_size" in v:
            v["db_size"].set(_fmt_size(s["db_size"]))
        # Last data update line.
        import time as _tm
        if s.get("last_data"):
            when = _tm.strftime("%Y-%m-%d %H:%M", _tm.localtime(s["last_data"]))
            self._dash_data_var.set(t("Cheat data last updated: {when}", when=when))
        else:
            self._dash_data_var.set(t("Cheat data last updated: never"))
        # Recently-updated list.
        host = getattr(self, "_recent_host", None)
        if host is None:
            return
        for w in host.winfo_children():
            w.destroy()
        c = theme()
        if not s["recent"]:
            ttk.Label(host, text=t("No entries yet."),
                      style="Glass.TLabel").pack(anchor="w")
            return
        base_font = ("Segoe UI", 9)
        hover_font = ("Segoe UI", 9, "underline")
        for (name, version, tid, bid, cc) in s["recent"]:
            rowf = ttk.Frame(host, style="Glass.TFrame")
            rowf.pack(fill="x", pady=1)
            label = (name or tid or "?")[:34]
            name_lbl = ttk.Label(rowf, text=label, style="Glass.TLabel",
                                 cursor="hand2", font=base_font)
            name_lbl.pack(side="left")
            # Click a name → jump to its game page; underline + accent on hover.
            name_lbl.bind("<Button-1>",
                          lambda _e, t_=tid: self.open_game_page(t_))
            name_lbl.bind("<Enter>", lambda _e, l=name_lbl: l.configure(
                font=hover_font, foreground=theme()["accent"]))
            name_lbl.bind("<Leave>", lambda _e, l=name_lbl: l.configure(
                font=base_font, foreground=theme()["fg"]))
            meta = f"{cc}"
            if version:
                meta = f"v{version} · {cc}"
            ttk.Label(rowf, text=meta, style="StatSub.TLabel").pack(side="right")

    def _build_library_page(self, page):
        self._page_title(page, "Browse", "Library",
                         "Search, browse and manage every cheat in your database.")
        # Order matters: filters on top, database bar reserved at the BOTTOM,
        # the table/gallery fills whatever height remains.
        self._build_filter_section(page, with_pickers=False)
        # View toggle: table ⇄ cover gallery.
        self.library_view = tk.StringVar(value="table")
        vrow = ttk.Frame(page, style="Body.TFrame")
        vrow.pack(fill="x", pady=(4, 0))
        tb = ttk.Checkbutton(vrow, text="▤ " + t("Table"), style="Toolbutton",
                             command=lambda: self._set_library_view("table"))
        tb.pack(side="left")
        gb = ttk.Checkbutton(vrow, text="⊞ " + t("Gallery"), style="Toolbutton",
                             command=lambda: self._set_library_view("gallery"))
        gb.pack(side="left", padx=(4, 0))
        self._view_toggle = {"table": tb, "gallery": gb}
        _Tooltip(gb, "Browse your games as cover tiles — click one for its page. "
                     "Covers you've downloaded show here; the rest use a "
                     "placeholder.")
        self._build_database_bar(page, compact=True)
        # Host holding both views stacked; raise the active one.
        host = ttk.Frame(page, style="Body.TFrame")
        host.pack(fill="both", expand=True, pady=(6, 0))
        host.rowconfigure(0, weight=1)
        host.columnconfigure(0, weight=1)
        self._lib_table_host = ttk.Frame(host, style="Body.TFrame")
        self._lib_table_host.grid(row=0, column=0, sticky="nsew")
        self._lib_gallery_host = ttk.Frame(host, style="Body.TFrame")
        self._lib_gallery_host.grid(row=0, column=0, sticky="nsew")
        self._build_main(self._lib_table_host)
        self._build_gallery(self._lib_gallery_host)
        self._set_library_view("table")

    # ------------------------------------------------------- cover gallery
    def _set_library_view(self, mode):
        self.library_view.set(mode)
        for m, btn in getattr(self, "_view_toggle", {}).items():
            try:
                (btn.state(["selected"]) if m == mode
                 else btn.state(["!selected"]))
            except Exception:
                pass
        if mode == "gallery":
            self._lib_gallery_host.tkraise()
            self._populate_gallery()
        else:
            self._lib_table_host.tkraise()

    def _build_gallery(self, parent):
        c = theme()
        canvas = tk.Canvas(parent, highlightthickness=0, bd=0, bg=c["bg"])
        vsb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, style="Body.TFrame")
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(-e.delta // 120, "units"))
        inner.bind("<MouseWheel>",
                   lambda e: canvas.yview_scroll(-e.delta // 120, "units"))
        self._gallery_canvas = canvas
        self._gallery_inner = inner
        self._gallery_imgs = {}     # title_id -> PhotoImage (kept alive)
        self._gallery_gen = 0

    _GALLERY_CAP = 120
    _GALLERY_COLS = 6

    def _populate_gallery(self):
        import sqlite3 as _sq
        inner = getattr(self, "_gallery_inner", None)
        if inner is None:
            return
        for w in inner.winfo_children():
            w.destroy()
        self._gallery_imgs.clear()
        self._gallery_gen += 1
        gen = self._gallery_gen
        c = theme()
        term = self.search_var.get().strip()
        rows, total = [], 0
        try:
            con = _sq.connect(f"file:{Path(self.db_path.get())}?mode=ro", uri=True)
            where = "WHERE game_title IS NOT NULL AND game_title<>''"
            params = []
            if term:
                where += " AND game_title LIKE ?"
                params.append(f"%{term}%")
            total = con.execute(
                f"SELECT COUNT(DISTINCT substr(title_id,1,13)||'000') "
                f"FROM builds {where}", params).fetchone()[0]
            rows = con.execute(
                f"SELECT MAX(title_id), MAX(game_title), MAX(image), "
                f"COALESCE(SUM(cheat_count),0) FROM builds {where} "
                f"GROUP BY substr(title_id,1,13)||'000' "
                f"ORDER BY game_title COLLATE NOCASE LIMIT ?",
                params + [self._GALLERY_CAP]).fetchall()
            con.close()
        except Exception as exc:
            self._append_log(f"Gallery query failed: {exc}")
            return
        if not rows:
            ttk.Label(inner, text="🔍  " + t("No matches for “{term}”.", term=term)
                      if term else t("Your database is empty — open Home and "
                                     "click ★ Download complete database."),
                      style="PageSub.TLabel").grid(row=0, column=0, padx=20, pady=20)
            return
        cols = self._GALLERY_COLS
        for ci in range(cols):
            inner.columnconfigure(ci, weight=1, uniform="gtile")
        tiles = []
        for i, (tid, name, image, cc) in enumerate(rows):
            tile = self._gallery_tile(inner, tid, name, cc, i // cols, i % cols)
            tiles.append((tid, image, tile))
        if total > len(rows):
            more = total - len(rows)
            ttk.Label(inner, text=t("+{n} more — refine your search to see them.",
                                    n=more), style="StatSub.TLabel").grid(
                row=(len(rows) // cols) + 1, column=0, columnspan=cols,
                sticky="w", pady=(8, 4))
        # Load covers in the background (cache-first; network only if allowed).
        self._gallery_load_covers(tiles, gen)

    def _gallery_tile(self, parent, tid, name, cc, r, col):
        c = theme()
        border, card = self._glass_card(parent, padding=(0, 0))
        border.grid(row=r, column=col, sticky="nsew", padx=5, pady=5)
        card.configure(cursor="hand2")
        cover = tk.Label(card, bd=0, highlightthickness=0, bg=c["surface"],
                         width=13, height=8, anchor="center",
                         fg=c["fg_muted"], font=("Segoe UI Semibold", 20),
                         text=(name or "?")[:1].upper())
        cover.pack(fill="x")
        nm = ttk.Label(card, text=(name or tid or "?"), style="Glass.TLabel",
                       wraplength=150, justify="center", anchor="center",
                       font=("Segoe UI", 9))
        nm.pack(fill="x", padx=6, pady=(4, 1))
        ttk.Label(card, text=t("{n} cheat(s)", n=cc), style="StatSub.TLabel",
                  anchor="center").pack(fill="x", pady=(0, 6))
        for w in (card, cover, nm):
            w.bind("<Button-1>", lambda _e, t_=tid: self.open_game_page(t_))
        return cover

    def _gallery_load_covers(self, tiles, gen):
        """Fill tile covers from the on-disk cache first; optionally fetch the
        rest (throttled, sequential) when the user keeps covers. A generation
        guard cancels the run when the gallery is repopulated."""
        try:
            from PIL import Image, ImageTk
        except Exception:
            return
        import io
        import threading as _th
        allow_net = bool(self.cache_covers.get())

        def work():
            for tid, image, label in tiles:
                if gen != self._gallery_gen:
                    return
                if not image:
                    continue
                cache = self._cover_cache_path(image, (tid or "").upper())
                raw = None
                try:
                    if cache.exists():
                        raw = cache.read_bytes()
                    elif allow_net:
                        import requests
                        raw = requests.get(self._normalize_url(image), timeout=12).content
                        try:
                            cache.parent.mkdir(parents=True, exist_ok=True)
                            cache.write_bytes(raw)
                        except Exception:
                            pass
                except Exception:
                    raw = None
                if not raw:
                    continue
                try:
                    img = Image.open(io.BytesIO(raw))
                    img.thumbnail((150, 150))
                except Exception:
                    continue

                def apply(t_=tid, im=img, lb=label, g=gen):
                    if g != self._gallery_gen:
                        return
                    try:
                        photo = ImageTk.PhotoImage(im)
                        self._gallery_imgs[t_] = photo
                        lb.configure(image=photo, text="", height=160)
                    except Exception:
                        pass
                try:
                    self.root.after(0, apply)
                except Exception:
                    return

        _th.Thread(target=work, daemon=True).start()

    def _build_sources_page(self, page):
        self._page_title(page, "Collect", "Sources",
                         "Import cheats from 9+ community sources, then enrich the metadata.")
        # Card 1: the community-source import buttons.
        b1, c1 = self._outline_card(page, padding=(16, 12))
        b1.pack(fill="x", pady=(0, 12))
        ttk.Label(c1, text=t("Community sources"),
                  style="CardTitle2b.TLabel").pack(anchor="w", pady=(0, 8))
        gh = ttk.Frame(c1, style="Body.TFrame")
        gh.pack(anchor="w")
        self._build_sources_grid(gh)
        # Card 2: the metadata-enrichment buttons (its own LabelFrame title).
        b2, c2 = self._outline_card(page, padding=(16, 8))
        b2.pack(fill="x", pady=(0, 12))
        self._build_info_section(c2)
        # Fill the rest with a live activity log.
        self._build_activity_panel(page)

    def _build_scrape_page(self, page):
        self._page_title(page, "Scraping", "CheatSlips",
                         "Scrape cheatslips.com and download the cheat files.")
        b, inner = self._outline_card(page, padding=(14, 10))
        b.pack(fill="x", pady=(0, 12))
        self._build_cheatslips_section(inner)
        # Fill the rest with a live activity log — watch the scrape/download run.
        self._build_activity_panel(page)

    def _build_log_page(self, page):
        self._page_title(page, "Session", "Log",
                         "Everything the app did this session.")
        self._build_log(page, with_status=False)

    # ------------------------------------------------------------- settings
    def _settings_card(self, parent, title):
        """A titled glass card; returns the inner body frame for controls."""
        border, inner = self._glass_card(parent, padding=(16, 12))
        border.pack(fill="x", pady=(0, 12))
        ttk.Label(inner, text=title, style="CardTitle.TLabel").pack(anchor="w")
        self._hairline(inner, pady=(7, 8))
        body = ttk.Frame(inner, style="Glass.TFrame")
        body.pack(fill="x")
        return body

    def _settings_check(self, parent, text, var, tip=None):
        cb = ttk.Checkbutton(parent, text=text, variable=var,
                             style="Glass.TCheckbutton",
                             command=self._save_settings)
        cb.pack(anchor="w", pady=2)
        if tip:
            _Tooltip(cb, tip)
        return cb

    def _build_settings_page(self, page):
        self._page_title(page, "Configure", "Settings",
                         "Everything in one place — updates, downloads, covers and paths.")
        # Two balanced columns of cards.
        cols = ttk.Frame(page, style="Body.TFrame")
        cols.pack(fill="both", expand=True)
        left = ttk.Frame(cols, style="Body.TFrame")
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = ttk.Frame(cols, style="Body.TFrame")
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))

        # -- Updates ------------------------------------------------------
        upd = self._settings_card(left, t("Updates"))
        self._settings_check(
            upd, t("Update the program automatically"), self.auto_update,
            "ON (recommended): a found program update installs itself silently "
            "at startup and the app restarts — no clicks. OFF: updates are only "
            "offered in a dialog to confirm.")
        self._settings_check(
            upd, t("Check for updates at startup"), self.update_check_startup)
        self._settings_check(
            upd, t("Keep the cheat data up to date automatically"),
            self.keep_data_updated,
            "ON: at startup the app quietly checks the DevCatSKZ data release "
            "and merges a newer cheat database automatically (a toast tells you). "
            "OFF: use '★ Download Complete' on Home when you want fresh data.")

        # -- Startup / online --------------------------------------------
        stp = self._settings_card(left, t("Startup"))
        self._settings_check(
            stp, t("Check whether cheatslips.com is online at startup"),
            self.online_check_startup)

        # -- Downloads & browser -----------------------------------------
        dl = self._settings_card(right, t("Downloads & Browser"))
        brow = ttk.Frame(dl, style="Glass.TFrame")
        brow.pack(fill="x", pady=(0, 4))
        ttk.Label(brow, text=t("Browser:"), style="Glass.TLabel").pack(side="left")
        self.settings_browser_combo = ttk.Combobox(
            brow, textvariable=self.browser_choice, state="readonly", width=12,
            values=list(_BROWSER_KINDS.keys()))
        self.settings_browser_combo.pack(side="left", padx=(6, 0))
        self.settings_browser_combo.bind("<<ComboboxSelected>>", self._on_browser_selected)
        self._settings_check(
            dl, t("Download via browser when the API is limited"),
            self.browser_fallback)
        self._settings_check(
            dl, t("Also download cover images with DevCatSKZ downloads"),
            self.devcat_covers)
        self._settings_check(
            dl, t("Save cover images to disk"), self.cache_covers)

        # -- Paths --------------------------------------------------------
        paths = self._settings_card(right, t("Paths"))
        self._settings_path_row(paths, t("Database:"), self.db_path, self._choose_db)
        self._settings_path_row(paths, t("Output folder:"), self.dl_output,
                                self._choose_output)

    def _settings_path_row(self, parent, label, var, chooser):
        ttk.Label(parent, text=label, style="Glass.TLabel").pack(anchor="w", pady=(4, 1))
        row = ttk.Frame(parent, style="Glass.TFrame")
        row.pack(fill="x")
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="…", width=3, command=chooser).pack(side="left", padx=(4, 0))

    # ------------------------------------------------------- game detail page
    def _build_detail_page(self, page):
        """Static skeleton — the body is rebuilt per game in open_game_page."""
        bar = ttk.Frame(page, style="Body.TFrame")
        bar.pack(fill="x", pady=(0, 8))
        back = ttk.Button(bar, text="←  " + t("Back to Library"),
                          command=lambda: self._select_page("library"))
        back.pack(side="left")
        _Tooltip(back, "Return to the library table (or press Esc).")
        self._detail_fav_btn = ttk.Button(bar, text="⭐",
                                          command=self._detail_toggle_fav)
        self._detail_fav_btn.pack(side="right")
        _Tooltip(self._detail_fav_btn,
                 "Add / remove this game from your ⭐ favourites — a data update "
                 "then notifies you when it gains new cheats.")
        self._detail_export_btn = ttk.Button(
            bar, text=t("Export as ZIP"), command=self._detail_export)
        self._detail_export_btn.pack(side="right", padx=(0, 6))
        _Tooltip(self._detail_export_btn,
                 "Export this game's cheats as a ZIP in the SD-card layout.")
        self._detail_dl_btn = ttk.Button(
            bar, text="⬇ " + t("Download cheats"), command=self._detail_download)
        self._detail_dl_btn.pack(side="right", padx=(0, 6))
        _Tooltip(self._detail_dl_btn,
                 "Download every cheat file for this game (API + browser fallback).")
        self._detail_body = ttk.Frame(page, style="Body.TFrame")
        self._detail_body.pack(fill="both", expand=True)
        self._detail_tid = None
        self._detail_imgs = {}   # keep PhotoImage refs alive

    def _detail_toggle_fav(self):
        if not self._detail_tid:
            return
        fav = self.toggle_favorite_tid(self._detail_tid)
        self._paint_detail_fav(fav)

    def _paint_detail_fav(self, fav):
        self._detail_fav_btn.config(
            text=("★ " + t("Remove favorite")) if fav
            else ("⭐ " + t("Add to favorites")))

    def _detail_download(self):
        if self._detail_tid:
            self._start_download([self._detail_tid])

    def _detail_export(self):
        if self._detail_tid:
            self.on_export_zip([self._detail_tid])

    def open_game_page(self, tid):
        """Populate + show the game page for *tid* (all builds, cover, facts)."""
        tid = (tid or "").strip()
        if not tid or tid == "-":
            return
        import sqlite3 as _sq
        try:
            con = _sq.connect(f"file:{Path(self.db_path.get())}?mode=ro", uri=True)
            con.row_factory = _sq.Row
            rows = con.execute(
                "SELECT * FROM builds WHERE UPPER(title_id)=UPPER(?) "
                "ORDER BY version IS NULL, version, build_id", (tid,)).fetchall()
            con.close()
        except Exception as exc:
            self._append_log(f"Game page: query failed: {exc}")
            rows = []
        if not rows:
            return
        self._detail_tid = tid.upper()
        first = rows[0]

        def field(name):
            vals = [r[name] for r in rows if name in r.keys() and r[name]]
            return vals[0] if vals else ""

        body = self._detail_body
        for w in body.winfo_children():
            w.destroy()
        self._detail_imgs.clear()
        c = theme()

        # ---- head: eyebrow, title, meta line ------------------------------
        title = field("game_title") or tid.upper()
        ttk.Label(body, text="—  " + _spaced(t("Game")),
                  style="Eyebrow.TLabel").pack(anchor="w")
        ttk.Label(body, text=title, style="PageTitle.TLabel").pack(
            anchor="w", pady=(3, 0))
        meta_bits = [b for b in (
            field("publisher"), field("developer"), field("category"),
            field("release_date"), field("region")) if b]
        sub = "  ·  ".join(str(b) for b in meta_bits) or tid.upper()
        ttk.Label(body, text=sub, style="PageSub.TLabel").pack(anchor="w")
        self._hairline(body, pady=(10, 12))

        cols = ttk.Frame(body, style="Body.TFrame")
        cols.pack(fill="both", expand=True)

        # ---- left column: cover + facts + (scrollable) description ---------
        left = ttk.Frame(cols, style="Body.TFrame", width=300)
        left.pack(side="left", fill="y", padx=(0, 16), anchor="n")
        left.pack_propagate(False)
        cover = ttk.Label(left, style="Glass.TLabel", anchor="center")
        cover.pack(anchor="n")
        url = field("image") or field("banner")
        if url:
            self._load_cover_into(cover, url, tid)
        facts = ttk.Frame(left, style="Body.TFrame")
        facts.pack(anchor="w", pady=(10, 0), fill="x")
        for label, value in (
                ("Title ID", tid.upper()),
                (t("Players"), field("players")),
                (t("Languages"), field("languages")),
                (t("Rating"), field("rating"))):
            if not value:
                continue
            rowf = ttk.Frame(facts, style="Body.TFrame")
            rowf.pack(anchor="w", fill="x")
            ttk.Label(rowf, text=f"{label}:", style="PageSub.TLabel",
                      width=10).pack(side="left")
            ttk.Label(rowf, text=str(value)[:36],
                      style="PageSub.TLabel").pack(side="left")

        desc = field("game_description") or field("description") or field("intro")
        if desc:
            dwrap = ttk.Frame(left, style="Body.TFrame")
            dwrap.pack(anchor="w", fill="both", expand=True, pady=(10, 0))
            dbox = tk.Text(dwrap, wrap="word", font=("Segoe UI", 9), relief="flat",
                           bg=c["surface"], fg=c["fg_muted"],
                           padx=10, pady=8, highlightthickness=1,
                           highlightbackground=c["border"], cursor="arrow")
            dsb = ttk.Scrollbar(dwrap, orient="vertical", command=dbox.yview)
            dbox.configure(yscrollcommand=dsb.set)
            dbox.insert("1.0", str(desc))
            dbox.config(state="disabled")
            dbox.pack(side="left", fill="both", expand=True)
            dsb.pack(side="right", fill="y")

        # ---- right column: builds as glass cards in a 2-column grid --------
        right = ttk.Frame(cols, style="Body.TFrame")
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(right, text=t("{n} build(s)", n=len(rows)),
                  style="CardTitle2.TLabel").pack(anchor="w", pady=(0, 6))
        canvas = tk.Canvas(right, highlightthickness=0, bd=0, bg=c["bg"])
        vsb = ttk.Scrollbar(right, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, style="Body.TFrame")
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(win, width=e.width))
        def _wheel(e):
            canvas.yview_scroll(-e.delta // 120, "units")
        for w in (canvas, inner):
            w.bind("<MouseWheel>", _wheel)

        # One column for 1-2 builds, two columns from three on — fills the space.
        ncols = 1 if len(rows) <= 2 else 2
        for ci in range(ncols):
            inner.columnconfigure(ci, weight=1, uniform="bcard")
        import json as _json
        for idx, r in enumerate(rows):
            self._build_build_card(inner, tid, r, _json,
                                   gridpos=(idx // ncols, idx % ncols))

        self._paint_detail_fav(self._detail_tid in self._favorites)
        self._pages["detail"].tkraise()
        self._nav_current = "library"   # keep Library lit in the sidebar
        self._paint_nav()

    def _build_build_card(self, parent, tid, r, _json, gridpos=None):
        c = theme()
        border, card = self._glass_card(parent, padding=(14, 10))
        if gridpos is not None:
            border.grid(row=gridpos[0], column=gridpos[1], sticky="new",
                        padx=(0, 8), pady=(0, 8))
        else:
            border.pack(fill="x", pady=(0, 8), padx=(0, 4))
        bid = (r["build_id"] or "").upper()
        head = ttk.Frame(card, style="Glass.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text=bid, style="CardMono.TLabel").pack(side="left")
        if r["version"]:
            ttk.Label(head, text=f"v{r['version']}",
                      style="CardAccent.TLabel").pack(side="left", padx=(10, 0))
        downloaded = False
        try:
            p = self._cheat_file_path(tid, bid)
            downloaded = bool(p and p.exists())
        except Exception:
            pass
        ttk.Label(head, text=("✓ " + t("downloaded")) if downloaded
                  else ("✗ " + t("not downloaded")),
                  foreground=c["ok"] if downloaded else c["fg_muted"],
                  background=c["surface"], font=("Segoe UI", 9)).pack(side="right")

        sub_bits = []
        if r["upload_date"]:
            sub_bits.append(str(r["upload_date"]))
        if r["source"]:
            sub_bits.append(str(r["source"]))
        n_cheats = r["cheat_count"] or 0
        sub_bits.append(t("{n} cheat(s)", n=n_cheats))
        ttk.Label(card, text="  ·  ".join(sub_bits),
                  style="StatSub.TLabel").pack(anchor="w", pady=(2, 6))

        btns = ttk.Frame(card, style="Glass.TFrame")
        btns.pack(fill="x")
        edit_btn = ttk.Button(btns, text="✏ " + t("Edit codes"),
                              command=lambda: self._detail_edit(tid, bid))
        edit_btn.pack(side="left")
        _Tooltip(edit_btn, "Open this build's codes in the cheat editor "
                           "(syntax-highlighted, validated).")
        try:
            names = _json.loads(r["cheat_names"] or "[]")
        except Exception:
            names = []
        if names:
            holder = ttk.Frame(card, style="Glass.TFrame")
            shown = {"on": False}
            lbl = ttk.Label(holder, text="\n".join(f"· {n}" for n in names[:40]),
                            style="StatSub.TLabel", justify="left")

            def toggle(_e=None, holder=holder, lbl=lbl, shown=shown):
                shown["on"] = not shown["on"]
                if shown["on"]:
                    holder.pack(fill="x", pady=(6, 0))
                    lbl.pack(anchor="w")
                else:
                    lbl.pack_forget()
                    holder.pack_forget()

            ttk.Button(btns, text="▾ " + t("Show cheats"),
                       command=toggle).pack(side="left", padx=(6, 0))
            holder.pack_forget()

    def _detail_edit(self, tid, bid):
        dlg = self._open_cheat_editor_for(tid, bid)
        try:
            self.root.wait_window(dlg.top)
        except Exception:
            pass
        # Counts/downloaded state may have changed — rebuild the page.
        self.open_game_page(tid)

    def _load_cover_into(self, label, url, tid, maxsize=(280, 400)):
        """Async cover for the game page (independent of the table's toggle)."""
        try:
            from PIL import Image, ImageTk
        except Exception:
            return
        import io
        import threading as _th
        cache = self._cover_cache_path(url, (tid or "").upper())

        def work():
            try:
                if cache.exists():
                    raw = cache.read_bytes()
                else:
                    import requests
                    raw = requests.get(self._normalize_url(url), timeout=15).content
                    if self.cache_covers.get():
                        try:
                            cache.parent.mkdir(parents=True, exist_ok=True)
                            cache.write_bytes(raw)
                        except Exception:
                            pass
                img = Image.open(io.BytesIO(raw))
                img.thumbnail(maxsize)

                def apply():
                    try:
                        photo = ImageTk.PhotoImage(img)
                        self._detail_imgs[url] = photo
                        label.config(image=photo)
                    except Exception:
                        pass
                self.root.after(0, apply)
            except Exception:
                pass

        _th.Thread(target=work, daemon=True).start()

    # Double-click in the MODERN library opens the game page (the richer view);
    # the cheat editor sits one click deeper, on each build card.
    def _open_cheat_editor(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            return
        col_ids = [col[0] for col in COLUMNS]
        v = self.tree.item(row, "values")
        idx = col_ids.index("title_id")
        tid = str(v[idx]).strip() if len(v) > idx else ""
        if tid and tid != "-":
            self.open_game_page(tid)

    # ------------------------------------------------------------ navigation
    def _select_page(self, key):
        self._pages[key].tkraise()
        self._nav_current = key
        self._paint_nav()
        if key == "home":
            self._refresh_dashboard()
        elif key == "library":
            self._update_nav_badge()
            self.root.after(150, self._update_empty_state)

    # ------------------------------------------------------------ empty state
    def refresh_table(self, *a, **k):
        super().refresh_table(*a, **k)
        # The async chunked insert finishes a moment later — re-check a few times.
        for delay in (250, 700, 1500):
            self.root.after(delay, self._update_empty_state)
        # Keep the cover gallery in sync with the search when it's the active view.
        if getattr(self, "library_view", None) and \
                self.library_view.get() == "gallery":
            self.root.after(120, self._populate_gallery)

    def _ensure_empty_overlay(self):
        if getattr(self, "_empty_overlay", None) is not None:
            return
        if not hasattr(self, "tree"):
            return
        c = theme()
        self._empty_overlay = tk.Label(
            self.tree.master, text="", justify="center", wraplength=380,
            bg=c["tree_bg"], fg=c["fg_muted"], font=("Segoe UI", 11))

    def _update_empty_state(self):
        if not hasattr(self, "tree"):
            return
        self._ensure_empty_overlay()
        c = theme()
        try:
            self._empty_overlay.configure(bg=c["tree_bg"], fg=c["fg_muted"])
        except Exception:
            pass
        if self.tree.get_children():
            self._empty_overlay.place_forget()
            return
        term = self.search_var.get().strip()
        if self._db_build_count() == 0:
            msg = "📭  " + t("Your database is empty — open Home and click "
                            "★ Download complete database.")
        elif term:
            msg = "🔍  " + t("No matches for “{term}”.", term=term)
        else:
            msg = "🔍  " + t("No entries match the current filters.")
        self._empty_overlay.configure(text=msg)
        self._empty_overlay.place(relx=0.5, rely=0.42, anchor="center")

    # ------------------------------------------------------------- busy sync
    def _set_busy(self, busy: bool):
        super()._set_busy(busy)
        self._busy_state = busy
        try:
            self.footer_stop_btn.config(state="normal" if busy else "disabled")
        except Exception:
            pass
        self._paint_busy()
        if not busy:
            # A finished task may have changed the DB — refresh the Library badge.
            self._update_nav_badge()

    def _paint_busy(self):
        c = theme()
        busy = getattr(self, "_busy_state", False)
        try:
            self._hdr_busy.configure(
                foreground=c.get("warn", "#e3a72f") if busy else c["featured_bg"])
        except Exception:
            pass

    # ---------------------------------------------------------------- theming
    def _apply_theme(self, name):
        super()._apply_theme(name)
        self._modern_styles()
        self._paint_modern()

    def _modern_styles(self):
        """ttk styles for the modern shell, derived from the active theme."""
        c = theme()
        st = getattr(self, "_style", None)
        if st is None:
            return
        st.configure("Hdr.TFrame", background=c["featured_bg"])
        st.configure("Hdr.TLabel", background=c["featured_bg"])
        st.configure("HdrGlyph.TLabel", background=c["featured_bg"],
                     foreground=c["accent"], font=("Segoe UI", 20))
        st.configure("HdrTitle.TLabel", background=c["featured_bg"],
                     foreground=c["title"], font=("Segoe UI Semibold", 13))
        st.configure("HdrSub.TLabel", background=c["featured_bg"],
                     foreground=c["fg_muted"], font=("Segoe UI", 9))
        st.configure("HdrPill.TLabel", background=c["bg"],
                     foreground=c["accent"], font=("Consolas", 10, "bold"))
        st.configure("HdrHint.TLabel", background=c["featured_bg"],
                     foreground=c["fg_muted"], font=("Segoe UI", 8))
        st.configure("HdrBell.TLabel", background=c["featured_bg"],
                     foreground=c["fg_muted"], font=("Segoe UI", 11))
        # Busy dot: amber while a task runs, else blends into the header.
        st.configure("HdrBusy.TLabel", background=c["featured_bg"],
                     foreground=c["featured_bg"], font=("Segoe UI", 11))
        st.configure("Body.TFrame", background=c["bg"])
        st.configure("Glass.TFrame", background=c["surface"])
        st.configure("Side.TFrame", background=c["surface"])
        st.configure("SideEyebrow.TLabel", background=c["surface"],
                     foreground=c["heading_fg"], font=("Consolas", 8, "bold"))
        st.configure("SideCredit.TLabel", background=c["surface"],
                     foreground=c["fg_muted"], font=("Segoe UI", 8))
        st.configure("Foot.TFrame", background=c["surface"])
        st.configure("FootStatus.TLabel", background=c["surface"],
                     foreground=c["fg_muted"], font=("Segoe UI", 9))
        st.configure("PageTitle.TLabel", background=c["bg"],
                     foreground=c["title"], font=("Segoe UI Semibold", 16))
        st.configure("PageSub.TLabel", background=c["bg"],
                     foreground=c["fg_muted"], font=("Segoe UI", 10))
        st.configure("Stat.TFrame", background=c["surface"])
        st.configure("StatBig.TLabel", background=c["surface"],
                     foreground=c["accent"], font=("Segoe UI Semibold", 15))
        st.configure("StatBigV.TLabel", background=c["surface"],
                     foreground=c.get("accent2", _VIOLET),
                     font=("Segoe UI Semibold", 15))
        st.configure("StatSub.TLabel", background=c["surface"],
                     foreground=c["fg_muted"], font=("Segoe UI", 9))
        st.configure("Eyebrow.TLabel", background=c["bg"],
                     foreground=c["accent"], font=("Consolas", 9, "bold"))
        # Controls sitting on a glass card must share its surface background.
        st.configure("CardTitle.TLabel", background=c["surface"],
                     foreground=c["title"], font=("Segoe UI Semibold", 11))
        st.configure("CardTitle2.TLabel", background=c["bg"],
                     foreground=c["title"], font=("Segoe UI Semibold", 11))
        st.configure("CardMono.TLabel", background=c["surface"],
                     foreground=c["fg"], font=("Consolas", 10, "bold"))
        st.configure("CardAccent.TLabel", background=c["surface"],
                     foreground=c["accent"], font=("Segoe UI Semibold", 10))
        st.configure("Glass.TLabel", background=c["surface"], foreground=c["fg"])
        st.configure("Glass.TCheckbutton", background=c["surface"],
                     foreground=c["fg"])
        st.map("Glass.TCheckbutton",
               background=[("active", c["surface"])],
               foreground=[("active", c["fg"])])
        # Unify the section headers on the Sources / CheatSlips / Library pages
        # (ttk LabelFrame titles) with the Settings card titles: accent, bold.
        # Borderless + flat so the surrounding outline card provides the frame.
        st.configure("TLabelframe", background=c["bg"], borderwidth=0,
                     relief="flat")
        st.configure("TLabelframe.Label", background=c["bg"],
                     foreground=c["accent"], font=("Segoe UI Semibold", 10))
        # Section title on the page background (outline cards).
        st.configure("CardTitle2b.TLabel", background=c["bg"],
                     foreground=c["accent"], font=("Segoe UI Semibold", 10))

    def _paint_modern(self):
        """Recolour the plain-tk parts (nav buttons, hairlines, glass borders)."""
        c = theme()
        for w, colour in ((getattr(self, "_hdr_line", None), c["featured_border"]),
                          (getattr(self, "_footer_line", None), c["border"]),
                          (getattr(self, "_side_edge", None), c["featured_border"])):
            if w is not None:
                try:
                    w.configure(bg=colour)
                except Exception:
                    pass
        for line in getattr(self, "_hairlines", []):
            try:
                line.configure(bg=c["border"])
            except Exception:
                pass
        for border in getattr(self, "_glass_borders", []):
            try:
                border.configure(bg=c["featured_border"])
            except Exception:
                pass
        for txt in getattr(self, "_activity_texts", []):
            try:
                txt.configure(bg=c["log_bg"], fg=c["log_fg"])
            except Exception:
                pass
        try:
            self._gallery_canvas.configure(bg=c["bg"])
        except Exception:
            pass
        self._paint_nav()
        self._paint_busy()
        self._paint_bell()

    def _paint_nav(self):
        c = theme()
        current = getattr(self, "_nav_current", None)
        for row in getattr(self, "_nav_rows", []):
            try:
                row.configure(bg=c["surface"])
            except Exception:
                pass
        for key, btn in getattr(self, "_nav_btns", {}).items():
            mark = self._nav_marks.get(key)
            badge = self._nav_badges.get(key)
            active = key == current
            try:
                if active:
                    btn.configure(bg=c["featured_bg"], fg=c["accent"],
                                  activebackground=c["featured_bg"],
                                  activeforeground=c["accent"],
                                  font=("Segoe UI Semibold", 11))
                    if mark is not None:
                        mark.configure(bg=c["accent"])
                else:
                    btn.configure(bg=c["surface"], fg=c["fg_muted"],
                                  activebackground=c["hover"],
                                  activeforeground=c["fg"],
                                  font=("Segoe UI", 11))
                    if mark is not None:
                        mark.configure(bg=c["surface"])
                if badge is not None:
                    badge.configure(bg=c["featured_bg"] if active else c["surface"],
                                    fg=c["fg_muted"])
            except Exception:
                pass

    def _update_nav_badge(self):
        """Show the games total on the Library nav entry."""
        badge = getattr(self, "_nav_badges", {}).get("library")
        if badge is None:
            return
        try:
            n = self._db_build_count_games()
            badge.configure(text=f"{n:,}" if n else "")
        except Exception:
            badge.configure(text="")

    def _db_build_count_games(self) -> int:
        import sqlite3 as _sq
        p = Path(self.db_path.get())
        if not p.exists() or not p.stat().st_size:
            return 0
        try:
            con = _sq.connect(f"file:{p}?mode=ro", uri=True)
            n = con.execute(
                "SELECT COUNT(DISTINCT substr(title_id,1,13)||'000') FROM builds"
            ).fetchone()[0]
            con.close()
            return int(n)
        except Exception:
            return 0

    def _on_escape(self, _e=None):
        """Esc backs out of the game detail page to the Library."""
        if self._pages.get("detail") and self._pages["detail"].winfo_ismapped() \
                and getattr(self, "_detail_tid", None):
            self._select_page("library")

    # ------------------------------------------------------ notifications
    def _toast(self, title, message):
        """Record every toast in the header's notification history, then show it."""
        try:
            self._notifications.insert(0, (None, title, message))
            del self._notifications[40:]
            self._notif_unseen += 1
            self._paint_bell()
        except Exception:
            pass
        super()._toast(title, message)

    def _paint_bell(self):
        n = getattr(self, "_notif_unseen", 0)
        try:
            self._bell_btn.configure(text=("🔔" + (f" {n}" if n else "")))
        except Exception:
            pass

    def _open_notifications(self):
        self._notif_unseen = 0
        self._paint_bell()
        c = theme()
        top = tk.Toplevel(self.root)
        top.title(t("Notifications"))
        top.transient(self.root)
        top.configure(bg=c["bg"])
        top.geometry("420x360")
        frm = ttk.Frame(top, style="Body.TFrame", padding=14)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=t("Notifications"),
                  style="PageTitle.TLabel").pack(anchor="w")
        self._hairline(frm, pady=(8, 8))
        if not self._notifications:
            ttk.Label(frm, text=t("No notifications yet."),
                      style="PageSub.TLabel").pack(anchor="w")
        else:
            host = ttk.Frame(frm, style="Body.TFrame")
            host.pack(fill="both", expand=True)
            for _ts, ntitle, nmsg in self._notifications[:30]:
                b, card = self._glass_card(host, padding=(12, 8))
                b.pack(fill="x", pady=(0, 6))
                ttk.Label(card, text=ntitle, style="CardTitle.TLabel").pack(anchor="w")
                ttk.Label(card, text=nmsg, style="Glass.TLabel",
                          wraplength=350, justify="left").pack(anchor="w")
        ttk.Button(frm, text=t("Close"), command=top.destroy).pack(
            side="bottom", anchor="e", pady=(8, 0))
        top.bind("<Escape>", lambda _e: top.destroy())
        self._paint_modern()

    # ------------------------------------------------------ command palette
    def _open_command_palette(self):
        if getattr(self, "_palette", None) is not None:
            try:
                self._palette.destroy()
            except Exception:
                pass
        CommandPalette(self.root, self)


class CommandPalette:
    """Ctrl+K overlay: type to jump to a game or run an action.

    Matches a small set of built-in actions (navigate to a page, download the
    complete dataset, check for updates) plus the top games whose name matches
    the query. Enter/double-click activates; ↑/↓ move; Esc closes.
    """

    def __init__(self, parent, app):
        self.app = app
        app._palette = self
        c = theme()
        self.top = tk.Toplevel(parent)
        self.top.transient(parent)
        self.top.overrideredirect(True)
        self.top.configure(bg=c["featured_border"])
        # Centered near the top of the parent window.
        parent.update_idletasks()
        w, h = 560, 420
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + 90
        self.top.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")

        outer = ttk.Frame(self.top, style="Glass.TFrame", padding=2)
        outer.pack(fill="both", expand=True, padx=1, pady=1)
        inner = ttk.Frame(outer, style="Glass.TFrame", padding=10)
        inner.pack(fill="both", expand=True)
        self.var = tk.StringVar()
        ent = tk.Entry(inner, textvariable=self.var, font=("Segoe UI", 13),
                       bg=c["field"], fg=c["fg"], insertbackground=c["fg"],
                       relief="flat", highlightthickness=1,
                       highlightbackground=c["border"], highlightcolor=c["accent"])
        ent.pack(fill="x", ipady=6)
        ttk.Label(inner, text=t("Type a game name, or an action…"),
                  style="StatSub.TLabel").pack(anchor="w", pady=(4, 6))
        self.box = tk.Listbox(
            inner, activestyle="none", font=("Segoe UI", 11),
            bg=c["surface"], fg=c["fg"], relief="flat", highlightthickness=0,
            selectbackground=c["select_bg"], selectforeground=c["select_fg"])
        self.box.pack(fill="both", expand=True)

        self._items = []   # parallel list of (label, callback)
        self.var.trace_add("write", lambda *_: self._refresh())
        ent.bind("<Down>", lambda _e: self._move(1))
        ent.bind("<Up>", lambda _e: self._move(-1))
        ent.bind("<Return>", lambda _e: self._activate())
        self.box.bind("<Double-Button-1>", lambda _e: self._activate())
        self.box.bind("<Return>", lambda _e: self._activate())
        for w_ in (self.top, ent, self.box):
            w_.bind("<Escape>", lambda _e: self._close())
        self.top.bind("<FocusOut>", self._maybe_close)
        self._refresh()
        ent.focus_set()

    def _actions(self, term):
        a = []
        for key, _glyph, label in _NAV:
            a.append((f"→  {t(label)}", lambda k=key: self.app._select_page(k)))
        a.append(("★  " + t("Download complete database (~25 MB)"),
                  self.app.on_devcat_complete))
        a.append(("⭯  " + t("Check Updates"),
                  lambda: self.app.on_check_updates()))
        term = term.lower()
        return [x for x in a if not term or term in x[0].lower()]

    def _games(self, term):
        if not term:
            return []
        import sqlite3 as _sq
        out = []
        try:
            p = Path(self.app.db_path.get())
            con = _sq.connect(f"file:{p}?mode=ro", uri=True)
            for tid, name in con.execute(
                    "SELECT title_id, MAX(game_title) FROM builds "
                    "WHERE game_title LIKE ? GROUP BY substr(title_id,1,13) "
                    "ORDER BY game_title LIMIT 8", (f"%{term}%",)):
                if name:
                    out.append((f"🎮  {name}",
                                lambda t_=tid: self.app.open_game_page(t_)))
            con.close()
        except Exception:
            pass
        return out

    def _refresh(self):
        term = self.var.get().strip()
        self._items = self._actions(term) + self._games(term)
        self.box.delete(0, "end")
        for label, _cb in self._items:
            self.box.insert("end", "  " + label)
        if self._items:
            self.box.selection_clear(0, "end")
            self.box.selection_set(0)

    def _move(self, d):
        if not self._items:
            return
        cur = self.box.curselection()
        i = (cur[0] if cur else 0) + d
        i = max(0, min(len(self._items) - 1, i))
        self.box.selection_clear(0, "end")
        self.box.selection_set(i)
        self.box.see(i)

    def _activate(self):
        cur = self.box.curselection()
        if not self._items:
            return
        i = cur[0] if cur else 0
        _label, cb = self._items[i]
        self._close()
        try:
            cb()
        except Exception:
            pass

    def _maybe_close(self, _e=None):
        # Close when focus truly leaves the palette (not just child widgets).
        self.top.after(120, self._close_if_unfocused)

    def _close_if_unfocused(self):
        try:
            if self.top.focus_get() is None:
                self._close()
        except Exception:
            self._close()

    def _close(self):
        try:
            self.app._palette = None
        except Exception:
            pass
        try:
            self.top.destroy()
        except Exception:
            pass


def run_gui():
    root = tk.Tk()
    ModernApp(root)
    root.mainloop()


if __name__ == "__main__":
    run_gui()
