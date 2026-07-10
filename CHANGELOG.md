# Changelog

All notable changes to this project are documented here.

## v1.3 — 2026-07-10 (UX polish 2)

### Improved — Sources & CheatSlips pages redesigned as cards
- The two pages that used to be a thin strip of controls over a big empty area
  are now **card-based** like Home/Settings: the community-source import
  buttons, the metadata-enrichment buttons and the CheatSlips scrape/download
  form each sit in a teal-outlined card, and the remaining space is filled by a
  **live Activity log** that mirrors the run as it happens — no more switching
  to the Log page to watch a scrape or import.

## v1.3 — 2026-07-10 (UX polish)

### Improved — the modern shell got a round of UX work
- **Command palette (Ctrl+K)** — a centred overlay: type to jump to any game or
  run an action (navigate to a page, download the complete dataset, check for
  updates). ↑/↓ to move, Enter/double-click to run, Esc to close.
- **Instant dashboard** — the Home stats now paint immediately from the cache
  and reconcile against disk in the background, instead of a ~1 s live scan
  showing empty "—" cards on every visit.
- **Game detail page** — the description is now taller + scrollable (no more
  cut-off text) and the build cards flow in a **2-column grid** that fills the
  space.
- **Sidebar** — the Library entry shows the games count as a badge; a header
  busy-dot lights amber while a task runs.
- **Keyboard** — Alt+1…6 switch pages, Esc backs out of the game page.
- **Empty states** — friendly messages for an empty database or a search with
  no matches, instead of a blank table.
- **Notification history** — a 🔔 bell in the header collects every toast (with
  an unseen badge); click to review recent notifications.
- **Cleaner status bar** — "5,307 builds · 100% downloaded · 57 update/DLC"
  (grouped thousands, plain wording) instead of the old techy string.
- **Consistent section headers** — the Sources / CheatSlips / Library section
  titles now match the Settings card titles (accent, bold), and the
  "Recently updated" names underline on hover.

## v1.3 — 2026-07-10 (feature update 4)

### Added — share-safe database export
- **"Export DB" now offers a SHARE mode** that strips the publisher eShop text
  (game descriptions / intros) from the exported copy, so a database you
  redistribute carries only facts, cheats, names, versions and community
  credits — smaller (~half the size) and copyright-clean. A full 1:1 export
  (keeps descriptions) is still one click away; your live database is never
  modified. Backed by `scraper.export_shared_db(strip_publisher_text=…)`.
- The publicly shared `database.db` (the `data` release) has been re-exported
  without game descriptions.

## v1.3 — 2026-07-10 (feature update 3)

### Added — game pages, a broken-file finder and editor power tools
- **Game detail page** (modern UI): double-click a game (or click a name on
  Home) → a full page with the cover art, description and facts (players,
  languages, rating), every build as a glass card (version, source, download
  state, cheat count) with expandable cheat lists, per-build "Edit codes",
  and header actions: ⭐ favorite toggle, "Download cheats", "Export as ZIP",
  "Back to Library". The cheat editor now sits one click deeper, on each
  build card.
- **Repair → "Find invalid code lines":** scans every downloaded cheat file
  with the editor's validation rules and lists the broken ones (sorted by
  error count, with an example line). Double-click opens the file in the
  editor — red lines already marked; fixed files disappear from the list.
  Found 183 genuinely broken files on the reference dataset.
- **Editor power tools:** a "＋ New cheat" button inserts a ready-made
  [Name] + code scaffold (name pre-selected for typing); right-click any
  cheat block to duplicate ("[Name (copy)]") or delete it, plus the standard
  clipboard actions.

## v1.3 — 2026-07-10 (feature update 2)

### Added — editor validation, favourites watchlist, cheat search
- **Syntax validation in the cheat editor:** malformed Atmosphère code lines
  (7/9-digit words, stray characters, >4 words per instruction) are marked
  red + underlined with a live "⚠ n invalid code line(s)" counter, and saving
  a broken file asks for confirmation first — no more silently broken cheats
  on the console.
- **⭐ Favourites / watchlist:** right-click any game → "⭐ Add / remove
  favorite" (stars show in the Game column, stored in settings so they survive
  data updates). New ⭐ Favorites quick-filter chip. After every data update
  the app diffs your favourites and notifies you — log line + Windows toast —
  when one of them gained new cheats or builds.
- **Cheat content search:** new 🔎 "Search in cheats" chip — the search box
  then also matches the cheat NAMES, so "inf health" finds every game with
  such a cheat (0 → 359 hits on the full database in testing).
- Both new chips are part of saved filter presets.

## v1.3 — 2026-07-10 (feature update)

### Added — the tool is now a full cheat editor + a real control centre
- **Cheat viewer/editor:** double-click any build to open its codes in a
  syntax-highlighted editor ([Name] / {Master} headers in the accent colour,
  opcodes tinted), edit them with a live cheat count, and save back to BOTH the
  .txt file and the database in one click.
- **Settings page** (modern sidebar): every scattered option in one place —
  program auto-update, startup checks, keep-data-updated, browser choice,
  browser fallback, cover options and the database / output paths.
- **Live dashboard** on Home: games, total cheats, downloaded %, database size,
  the date the cheat data was last updated, and a "Recently updated" list.
- **Library power tools:** quick-filter chips (⚡ Has cheats, 🖼 No cover),
  a Columns menu to show/hide table columns, and named filter presets
  (save / apply / delete) — all persisted.
- **Keep the cheat data up to date automatically:** opt-in on Settings; at
  startup the app quietly checks the DevCatSKZ data release and merges a newer
  database (non-destructive), with a toast when something new arrives.
- **No-admin migration nudge:** a legacy Program-Files install (which needs a
  UAC prompt per update) is offered — once — a one-click download+run of the
  current per-user installer, after which updates install silently forever.

## v1.3 — 2026-07-10 (refreshed build)

### Added — modern Holo-Glass GUI (now the default)
- **Complete visual re-architecture** (`gui_modern.py`): header bar with the
  real app icon + version pill + theme/language pickers, sidebar navigation
  (Home / Library / Sources / CheatSlips / Log) with a teal active-indicator,
  landing-page style page heads, glass stat cards and a persistent status
  footer (status · Stop · progress). Opens in an optimal windowed size
  (~1560×1000, centered) instead of maximized.
- Shares **100% of the widgets and handlers** with the classic UI: `gui.py`'s
  layout was extracted into a `_compose_ui()` hook + parented section builders;
  the classic UI is composed from the same builders and stays pixel-identical.
  `SwitchCheatsScraper.exe --classic` (or `python gui.py`) starts it.
- **"Download Android App" button** on the ★ card: pick a save location, the
  latest `SwitchCheatsDownloader-Android.apk` is downloaded and SHA-256
  verified.

### Added — quality-of-life (2026-07-09/10)
- **Silent self-update:** the installer is now **per-user** (LocalAppData, no
  admin/UAC); a found update downloads, verifies against GitHub's **SHA-256
  digest**, installs silently and restarts the app. "Update automatically"
  checkbox (default ON) — a manual *Check Updates* always shows the redesigned
  dialog (rendered release notes) with a visible download/install progress.
- **First-run welcome dialog:** empty database → one-click "★ Download
  complete database (~25 MB)".
- **Safety backups:** rotating `cheats.db.bak`/`.bak2` (WAL-safe) before
  Clear DB, Import DB, Fix ID names, Sync titles, Recount cheats, Clean invalid.
- **Windows toasts** for finished long tasks (scrape done, data update
  installed, update installing) — only when the window is in the background.
- **"Export for Emulators":** cheats as `<TitleID>/<GameName>/cheats/<BuildID>.txt`
  for Eden / Suyu / Sudachi / Torzu / Yuzu (`load`) and Ryujinx (`mods`), as a
  folder or ZIP; the ready-made `switch-cheats-emulator.zip` is hosted in the
  `data` release.
- **Android app reworked:** downloads `switch-cheats-emulator.zip`, unpacks it
  to a public folder (fast direct file writes) and you import per game via the
  emulator's own *Add-ons → Mods and cheats* (on Android 11+ no third-party
  app can write into an emulator's private `Android/data`). One combined
  Eden/Suyu/Sudachi section with a generic import guide; `names.json` is no
  longer needed.

## v1.3 — 2026-07-08

### Changed — download engine reworked around the API + quota reset
- **All API downloads now get past cheatslips' tiny per-window content limit
  automatically.** The content API only serves ~3 cheats per window and only a
  browser quota reset refills it, so every download now: pulls cheats via the
  API **per game** (one request covers all of a game's builds), and the moment
  the limit is hit it **presses "reset my quota" in the browser, refreshes the
  API token and continues** — repeating until the whole selection is done. No
  more "only the first few loaded".
- **`get_game` (per-title) instead of `get_build` (per-build).** cheatslips'
  per-build endpoint returns empty; the per-title endpoint returns real codes
  for every build of a game in a single request — far fewer requests, so the
  limit is tripped much less often.
- **Requests are sequential with a small pause** (was up to 4 in parallel),
  which alone trips the throttle far less.
- **"Download this" / "Download Selected"** now fetch a build by any means:
  API + resets first, then the **browser** for builds the API doesn't list
  (many builds scraped from the website are not on the API).
- **"Download via browser when API is limited"** is now its own option, **off
  by default**, and controls only the browser fallback (it no longer gates the
  quota reset, which always runs). Bulk builds no longer do thousands of slow
  browser downloads unless you ask for it.
- The **"full catalog (all games, slower)"** scrape option now defaults to
  **OFF** (fast `/entry` feed; both find the same cheat-having builds).

### Fixed
- **"Download via Browser" no longer triggers a stuck browser "update".** A
  method-name collision made that button secretly run the Firefox-component
  installer with your selection as its target — an un-cancellable dialog. It
  now uses the same bundled Chromium as everything else.
- **The browser download no longer churns / looks endless.** When the browser
  session is closed mid-run it stops immediately instead of failing on every
  remaining build; and the API pass no longer walks the whole list once the
  quota is exhausted.
- Remaining maintenance/download dialogs translated in all 6 languages.

### Added
- **"Prisma (Holo-Glass)" signature theme** — deep petrol-black with a
  teal-mint accent, electric-violet gradient highlights and gold accents.
  It is the new **default theme on both platforms** (Windows *and* the
  Switch app), so desktop and console share one unified look. The theme
  switcher is now a **dropdown** (Prisma / Dark / Light) next to the
  language picker; your previously saved theme choice is kept.
- **Download Switch App** (in the "★ Get Everything from DevCatSKZ" card):
  downloads the Switch homebrew app — always the **latest** version from
  the `nro` release — and, with the optional **"Copy to SD card"** checkbox
  (off by default), places it straight onto an auto-detected Switch SD card
  as `/switch/SwitchCheatsDownloader.nro` (same detection as the cheats SD
  export). Downloads are validated against the NRO file signature.
- **Switch app v1.3.0**: ships the Prisma look as its default design
  (teal-glass panels, gradient primary button, gold highlights).

### Fixed
- Typing in the **Output** field no longer rebuilds the game table on every
  keystroke — it is debounced now, like the search box.
- **All remaining dialogs and status messages are now translated** in all
  6 languages (EN/DE/ES/FR/IT/JA): the "Scrape all" confirmation, SD/ZIP
  export summaries, database import/export/merge dialogs, update-check
  messages, cheat-file check results, maintenance-tool confirmations
  (fix 0-cheat, recount, scan empty, clean invalid, sync titles, fix ID
  names) and more — previously these always appeared in English.
- **Prisma theme:** disabled buttons no longer vanish into the background
  while a scrape/download is running — they keep their glass fill with
  dimmed text.

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
