# Changelog

All notable changes to this project are documented here.

## v1.2 — 2026-07-06

### Added — 2026-07-07 (Switch homebrew app)
- **New: standalone Switch homebrew app** (`SwitchCheatsDownloader.nro` v1.2.0,
  source in [`SwitchCheatsNRO/`](SwitchCheatsNRO/)) — the on-console counterpart
  of the desktop tool. Downloads the always-current `switch-cheats.zip` from the
  `data` release directly on the Switch and extracts it into the Atmosphère
  layout on the SD card. Auto-checks on launch (incl. download size), manual
  re-check, resume for interrupted downloads, self-update via the `nro` release,
  6 languages (EN/DE/ES/FR/IT/JA) with real diacritics, Joy-Con + touch control,
  dark Switch-style UI with the official app icon. Ships as
  `SwitchCheatsDownloader-Switch.zip` (extract to SD root) on the release page.

### Added
- **Multi-language interface (6 languages).** The whole program is available in
  **English** (default), **Deutsch, Español, Français, Italiano and 日本語
  (Japanese)**. Switch it via the language selector next to the dark/light toggle
  (bottom-right of the Search bar); the app restarts to apply it and the choice is
  saved in `settings.json`. Translations are natural rather than literal and keep
  common tech terms in English (Download, Scrape, API, Token, ZIP, …).
- **Installer language linked to the program language.** Setup has a "Program
  language" page (pre-selected from the wizard language), so choosing e.g. German
  setup makes the program start in German.
- **Opens maximized (full screen) on first launch.** The window state is
  remembered afterwards, so it reopens the way you left it.

### Changed
- **Smaller downloads.** Only the built-in Chromium is bundled now; Firefox is
  fetched on demand into the app's data folder when selected, and Chrome uses your
  installed Google Chrome. Setup ~338 → ~254 MB, portable ~479 → ~360 MB.
- **Auto-refresh after a single download.** After *Download this / via API / via
  browser*, the table now updates automatically (recount from disk + rescan), just
  like pressing **Refresh** — so the build flips to "downloaded" and shows its real
  cheat count immediately.
- **New first-run defaults.** *Show Covers* is off by default; the **Export to
  ZIP** and **Export DB** default file names are `switch-cheats.zip` and
  `database.db` (matching the data-release assets).

### Fixed
- **Language change now reliably restarts the app** in a packaged (windowed) build
  (the relaunch is fully detached with its own std handles, instead of failing
  silently and leaving the program in English).

## v1.1 — 2026-07-05

### Added
- **Self-update via a "Check Updates" button** (in the DevCatSKZ card). It queries
  the GitHub `releases/latest` for a newer program build and the `data` release
  for newer cheats/database packages. Two detection rules apply to everything:
  a **higher version** (e.g. 1.1), **or** an **asset re-uploaded** more recently
  than the stored baseline (first-run time) — so a fix without a version bump is
  detected too. A found **program update installs itself** (downloads the
  installer, runs it silently in place, and the app restarts); **data updates**
  are downloaded and merged into the database. Optional automatic check at
  startup (on by default). The baseline is stored in `update_state.json` in the
  data dir, so it survives updates.

### Fixed
- **DevCatSKZ downloads no longer fail with `'NoneType' object has no attribute
  'write'`.** In the packaged windowed build `sys.stdout`/`sys.__stdout__` are
  `None`, so the log tee crashed on the first `print()`. The tee now drops `None`
  streams and swallows per-stream errors, so logging can never crash the app.

### Changed
- **DevCatSKZ covers are now controlled by a "Download Covers" checkbox**
  (off by default) in the card, instead of a yes/no prompt after every download.
  The choice is remembered between runs.
- **Reworked the "External Cheat Sources" layout** so it no longer stretches
  edge-to-edge: the source buttons form a tidy 3×4 uniform grid and, together
  with the DevCatSKZ card, sit as one centered, symmetric block.
- **Installer defaults to `C:\Program Files (x86)\Switch Cheats Scraper &
  Downloader`** (needs admin). The "Select Destination Location" page is always
  shown, so any folder can be browsed to or created. Runtime data lives in the
  `%LOCALAPPDATA%` fallback when installed under Program Files. The uninstaller's
  "remove all data" option now also clears that fallback folder.

## v1.0 — 2026-07-05

Scrape & download Nintendo Switch cheats from CheatSlips.com, GBATemp/HamletDuFromage,
Sthetix, Breeze (NXCheatCode), ChanseyIsTheBest (60FPS/Res/GFX), MyNXCheats, ibnux and
titledb. Manage all your cheats in a searchable SQLite database and export them straight
to your Switch SD card (Atmosphère / Breeze / EdiZon) or a ZIP.

### Get everything from DevCatSKZ
- A prominent one-click section to **download the maintainer's prebuilt data**
  from GitHub instead of scraping: **Download Cheats** (ready-made archive),
  **Download Database** (the full GUI database, merged in), or **Download
  Complete** (both). A **"Download Covers"** checkbox (off by default) in the
  card controls whether covers are fetched afterwards.
- The database ships cover **URLs** only, never cover images — no copyrighted
  artwork is redistributed; covers are fetched by each user from the source.

### Sources
- Scrape + official API from **CheatSlips.com** (metadata without login, cheat
  content via API token / email+password).
- External cheat archives: **GBATemp/HamletDuFromage** (`titles_complete.zip`),
  **HamletDuFromage 60FPS/Res/GFX**, **Sthetix** (daily aggregate), **Breeze /
  NXCheatCode**, **Chansey NX-60FPS-RES-GFX** (live repo), **MyNXCheats** (live
  repo), **ibnux**, and **titledb** `cheats.json`.
- One-click **★ Scrape & Download Everything** pipeline.

### Download
- Official **API** download (no browser) with automatic **browser fallback**
  (Playwright) when the daily quota is hit — resolves each build to its cheat
  page, handles login/reCAPTCHA once, resets the website quota and retries.
- **Browser Login** button: one-time login, cookies persist for future runs.

### Enrichment
- Fill **names/covers**, **regions** (with switchbrew/homebrew/script
  fallbacks), **versions** (titledb + cheatslips) and **descriptions**.
- Context-menu versions run only on the selected rows.

### Export / Import
- **Export to SD card** (Atmosphère / Breeze / EdiZon layout, drive auto-detect).
- **Export to ZIP** (same SD layout, dated default name) and **Import ZIP**
  back into the database.
- **Export DB** / **Import DB**: back up the full `cheats.db` and import it again
  later — **merge** it into the current database (nothing removed, a real cheat
  count is never lost) or **replace** the current one (a backup is made first).

### App
- Searchable database GUI (by name, Title ID or Build ID), cover panel,
  live disk reconciliation, async table refresh, WAL database.
- **Dark mode by default** with a one-click light/dark toggle that restyles the
  whole program — main window, table, detail panel, log, menus and every
  sub-dialog; the choice is saved between runs.
- Online status indicator, size-capped log, per-file scan cache.
- Portable data storage next to the `.exe` (falls back to `%LOCALAPPDATA%`
  if read-only). Windows installer included.
