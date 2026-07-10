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
        # Theme + language pickers on the right of the header.
        self._build_theme_lang_pickers(self._header, side="right")
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
                            font=("Segoe UI", 11), padx=10, pady=9, width=16,
                            command=lambda k=key: self._select_page(k))
            btn.pack(side="left", fill="x", expand=True)
            self._nav_btns[key] = btn
            self._nav_marks[key] = mark
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

        self._select_page("home")
        self._paint_modern()   # colour everything for the current theme

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
        """Recompute the Home stats off-thread, then paint them on the UI thread."""
        if not hasattr(self, "_dash_vars"):
            return
        import threading

        def work():
            stats = self._dashboard_stats()
            try:
                self.root.after(0, lambda: self._paint_dashboard(stats))
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
        for (name, version, tid, bid, cc) in s["recent"]:
            rowf = ttk.Frame(host, style="Glass.TFrame")
            rowf.pack(fill="x", pady=1)
            label = (name or tid or "?")[:34]
            name_lbl = ttk.Label(rowf, text=label, style="Glass.TLabel",
                                 cursor="hand2")
            name_lbl.pack(side="left")
            # Click a name → jump straight to its game page.
            name_lbl.bind("<Button-1>",
                          lambda _e, t_=tid: self.open_game_page(t_))
            meta = f"{cc}"
            if version:
                meta = f"v{version} · {cc}"
            ttk.Label(rowf, text=meta, style="StatSub.TLabel").pack(side="right")

    def _build_library_page(self, page):
        self._page_title(page, "Browse", "Library",
                         "Search, browse and manage every cheat in your database.")
        # Order matters: filters on top, database bar reserved at the BOTTOM,
        # the table fills whatever height remains (same trick as classic).
        self._build_filter_section(page, with_pickers=False)
        self._build_database_bar(page, compact=True)
        self._build_main(page)

    def _build_sources_page(self, page):
        self._page_title(page, "Collect", "Sources",
                         "Import cheats from 9+ community sources, then enrich the metadata.")
        grid_host = ttk.Frame(page, style="Body.TFrame")
        grid_host.pack(anchor="w", pady=(0, 12))
        self._build_sources_grid(grid_host)
        self._build_info_section(page)

    def _build_scrape_page(self, page):
        self._page_title(page, "Scraping", "CheatSlips",
                         "Scrape cheatslips.com and download the cheat files.")
        self._build_cheatslips_section(page)

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
        ttk.Button(bar, text="←  " + t("Back to Library"),
                   command=lambda: self._select_page("library")).pack(side="left")
        self._detail_fav_btn = ttk.Button(bar, text="⭐",
                                          command=self._detail_toggle_fav)
        self._detail_fav_btn.pack(side="right")
        self._detail_export_btn = ttk.Button(
            bar, text=t("Export as ZIP"), command=self._detail_export)
        self._detail_export_btn.pack(side="right", padx=(0, 6))
        self._detail_dl_btn = ttk.Button(
            bar, text="⬇ " + t("Download cheats"), command=self._detail_download)
        self._detail_dl_btn.pack(side="right", padx=(0, 6))
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

        # ---- left column: cover + description + facts ----------------------
        left = ttk.Frame(cols, style="Body.TFrame")
        left.pack(side="left", fill="y", padx=(0, 16), anchor="n")
        cover = ttk.Label(left, style="Glass.TLabel", anchor="center")
        cover.pack(anchor="n")
        url = field("image") or field("banner")
        if url:
            self._load_cover_into(cover, url, tid)
        facts = ttk.Frame(left, style="Body.TFrame")
        facts.pack(anchor="w", pady=(10, 0))
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
            dbox = tk.Text(left, width=36, height=13, wrap="word",
                           font=("Segoe UI", 9), relief="flat",
                           bg=c["surface"], fg=c["fg_muted"],
                           padx=10, pady=8, highlightthickness=1,
                           highlightbackground=c["border"], cursor="arrow")
            dbox.insert("1.0", str(desc)[:2200])
            dbox.config(state="disabled")
            dbox.pack(anchor="w", pady=(10, 0))

        # ---- right column: builds as glass cards (scrollable) -------------
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

        import json as _json
        for r in rows:
            self._build_build_card(inner, tid, r, _json)

        self._paint_detail_fav(self._detail_tid in self._favorites)
        self._pages["detail"].tkraise()
        self._nav_current = "library"   # keep Library lit in the sidebar
        self._paint_nav()

    def _build_build_card(self, parent, tid, r, _json):
        c = theme()
        border, card = self._glass_card(parent, padding=(14, 10))
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
        ttk.Button(btns, text="✏ " + t("Edit codes"),
                   command=lambda: self._detail_edit(tid, bid)).pack(side="left")
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

    # ------------------------------------------------------------- busy sync
    def _set_busy(self, busy: bool):
        super()._set_busy(busy)
        try:
            self.footer_stop_btn.config(state="normal" if busy else "disabled")
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
                     foreground=_VIOLET, font=("Segoe UI Semibold", 15))
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
        self._paint_nav()

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
            try:
                if key == current:
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
            except Exception:
                pass


def run_gui():
    root = tk.Tk()
    ModernApp(root)
    root.mainloop()


if __name__ == "__main__":
    run_gui()
