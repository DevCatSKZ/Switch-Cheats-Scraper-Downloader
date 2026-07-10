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
from tkinter import ttk

import i18n
from i18n import t
from gui import (ScraperGUI, theme, _Tooltip,
                 APP_NAME, APP_AUTHOR, APP_VERSION)


# Sidebar navigation: (key, glyph, label). Labels are static English keys —
# the i18n auto-hook translates them like every other widget text.
_NAV = [
    ("home",    "⌂",  "Home"),
    ("library", "▤",  "Library"),
    ("sources", "☁",  "Sources"),
    ("scrape",  "⇣",  "CheatSlips"),
    ("log",     "≡",  "Log"),
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

        # ---------- pages ---------------------------------------------------
        self._build_home_page(self._pages["home"])
        self._build_library_page(self._pages["library"])
        self._build_sources_page(self._pages["sources"])
        self._build_scrape_page(self._pages["scrape"])
        self._build_log_page(self._pages["log"])

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

    def _build_home_page(self, page):
        self._page_title(page, "Overview", "Home",
                         "Everything for your Switch cheats — collected, managed, delivered.")
        # Quick stats strip — glass cards with teal hairline borders.
        stats = ttk.Frame(page, style="Body.TFrame")
        stats.pack(fill="x", pady=(0, 14))
        b1, card1 = self._glass_card(stats, padding=(18, 12))
        b1.pack(side="left", padx=(0, 12))
        ttk.Label(card1, textvariable=self.total_games_var,
                  style="StatBig.TLabel").pack(anchor="w")
        ttk.Label(card1, text="in your database", style="StatSub.TLabel").pack(anchor="w")
        b2, card2 = self._glass_card(stats, padding=(18, 12))
        b2.pack(side="left", padx=(0, 12))
        ttk.Label(card2, text=f"v{APP_VERSION}", style="StatBigV.TLabel").pack(anchor="w")
        ttk.Label(card2, text="program version", style="StatSub.TLabel").pack(anchor="w")
        # The featured DevCat card (downloads, updates, Switch app) — the same
        # proven card as in the classic toolbar, as the hero of the Home page.
        self._build_devcat_card(page, beside_grid=False)

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

    # ------------------------------------------------------------ navigation
    def _select_page(self, key):
        self._pages[key].tkraise()
        self._nav_current = key
        self._paint_nav()

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
