<p align="center">
  <img src="banner.png" width="820" alt="Switch Cheats Scraper & Downloader">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-1.3-blue" alt="Version">
  <img src="https://img.shields.io/badge/platform-Windows-0078D6?logo=windows" alt="Platform">
  <img src="https://img.shields.io/badge/homebrew-Nintendo%20Switch-e60012?logo=nintendoswitch&logoColor=white" alt="Switch">
  <img src="https://img.shields.io/badge/Android-Eden%20%C2%B7%20Suyu%20%C2%B7%20Sudachi-3DDC84?logo=android&logoColor=white" alt="Android">
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

<p align="center"><b>by DevCatSKZ</b></p>

A tool to **scrape and download** Nintendo Switch cheat codes from **[CheatSlips.com](https://www.cheatslips.com), [GBATempArchive](https://gbatemp.net), [HamletDuFromage](https://github.com/HamletDuFromage/switch-cheats-db), [Sthetix](https://github.com/sthetix/nx-cheats-db), [Breeze (NXCheatCode)](https://github.com/tomvita/NXCheatCode), [ChanseyIsTheBest (60FPS/Res/GFX)](https://github.com/ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats), [MyNXCheats](https://github.com/Arch9SK7/MyNXCheats), [ibnux](https://github.com/ibnux/switch-cheat) and [titledb](https://github.com/blawar/titledb)**, manage them in a **searchable SQLite database** (names, covers, regions, versions, descriptions) and export them straight into the right layout on your **Switch SD card** (Atmosphère / Breeze / EdiZon) — or as a ZIP.

> Only use the tool with your **own** CheatSlips account. All cheat codes belong to their original authors/uploaders.

<p align="center"><img src="screenshots/windows-tool.png" width="900" alt="Switch Cheats Scraper & Downloader (Windows)"></p>

**How it works (Windows):**
1. **Collect** — scrape CheatSlips and/or import 9+ community sources into a local **SQLite database** (game names, covers, regions, versions, descriptions).
2. **Browse** — search and filter everything in the GUI.
3. **Export** — one click to your SD card (Atmosphère / Breeze / EdiZon layout) or as ZIP. The merged dataset is also published as the always-current [`data` release](https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/tag/data), so nobody *has* to scrape.

## ⬇️ Download (Windows)

Ready-made builds are on the **[Releases](../../releases/latest)** page:

> **📦 Ready-made cheats & database** (no scraping needed): download [`switch-cheats.zip`](https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/download/data/switch-cheats.zip) (all cheat files) + [`database.db`](https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/download/data/database.db) (full database) from the continuously-updated **[`data` release »](https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/tag/data)** — refreshed whenever new cheats are added.

| Variant | Description |
|---|---|
| **Installer** (`SwitchCheatsScraper-Setup.exe`) | Classic install (default path `C:\Program Files (x86)\Switch Cheats Scraper & Downloader`, freely choosable/creatable in the wizard; needs admin rights; adds Start-menu/Desktop shortcuts). Lets you pick the program language. |
| **Portable** (`SwitchCheatsScraper-portable.zip`) | Unzip and run `SwitchCheatsScraper.exe` — no install needed. Data lives **next to the EXE**. |

No Python required — the EXE is self-contained. (The built-in Chromium ships with the app; Firefox/Chrome for the optional browser download are fetched on demand when selected.)

## 🎮 Switch app (homebrew)

The desktop tool has a **counterpart that runs directly on the Switch**: a standalone homebrew app (`SwitchCheatsDownloader.nro`) that fetches the always-current [`data` release](https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/tag/data) **on the console** and extracts it straight into the Atmosphère layout on the SD card — no PC needed.

<p align="center"><img src="screenshots/switch-app.png" width="720" alt="Switch Cheats Downloader homebrew app"></p>

**What it does:** on launch it checks whether new cheats are available (same "re-upload without version bump" detection as the desktop tool, incl. download size), and one press on **A** downloads and extracts everything to `atmosphere/contents/<TitleID>/cheats/`. Interrupted downloads **resume** where they stopped, the app can **update itself** from this repo, and the UI speaks **6 languages** (EN/DE/ES/FR/IT/JA, auto-detected from the console) with full Joy-Con **and** touch control.

**Install:** download [`SwitchCheatsDownloader-Switch.zip`](../../releases/latest) from the latest release and extract it to the **root of your SD card** (it contains `switch/SwitchCheatsDownloader.nro`), then launch *Switch Cheats Downloader* from the Homebrew Menu. Requires a modded Switch (Atmosphère + hbmenu) and Wi-Fi.

Source & developer docs: [`SwitchCheatsNRO/`](SwitchCheatsNRO/) — build with devkitPro, see its [README](SwitchCheatsNRO/README.md).

## 🤖 Android app (emulators)

The same downloader also runs on **Android**, for the Switch emulators **Eden, Suyu and Sudachi** (`SwitchCheatsDownloader-Android.apk`). It fetches the always-current [`data` release](https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/tag/data) **on the phone** and writes the cheats straight into the emulator's load layout — no PC needed.

**What it does:** pick your emulator and tap **Start** — it downloads every cheat and writes it into the emulator's load folder as `.../load/<TitleID>/<GameName>/cheats/<BuildID>.txt`, naming each mod folder after the real game (resolved from the data release's `names.json`, falling back to the Title ID). Interrupted downloads **resume**, the app checks this repo for **updates** (a newer APK *and* refreshed cheats, same re-upload detection as the desktop tool), shows a live online status, and speaks the same **6 languages** (EN/DE/ES/FR/IT/JA, auto-detected from the device). Same **Holo-Glass** look as the Windows and Switch apps.

**Storage:** on first launch the app asks once for **All files access** (`MANAGE_EXTERNAL_STORAGE`) so it can write into the emulator folders. Where the OS still blocks a direct write (another app's `Android/data/…` on Android 11+), it falls back to a **one-time folder pick** — pre-navigated to the emulator's folder — and then keeps working automatically. An **export to a folder of your choice** is always available.

**Install:** download [`SwitchCheatsDownloader-Android.apk`](../../releases/latest) from the latest release, allow installation from unknown sources, and grant **All files access** on first launch. Requires Android 8.0 (API 26)+.

Source & developer docs: [`SwitchCheatsAndroid/`](SwitchCheatsAndroid/) — build with Gradle (`gradlew assembleRelease`), see its [README](SwitchCheatsAndroid/README.md).

## 📦 Always-current cheats & database

You don't have to scrape anything yourself: a **continuously updated** cheats archive and full GUI database are kept in the repo's **[`data` release](https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/tag/data)**. Whenever new cheats appear, these files are refreshed — so grabbing them always gives you the **latest** dataset.

| Asset | What it is | Direct link |
|---|---|---|
| `switch-cheats.zip` | All cheat files (Atmosphère layout) | [download](https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/download/data/switch-cheats.zip) |
| `database.db` | Complete GUI database (names, regions, versions, descriptions, cover **URLs**) | [download](https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/download/data/database.db) |

In the app, the **★ Get Everything from DevCatSKZ** card downloads these with one click (**Download Cheats** / **Download Database** / **★ Download Complete**), and **Check Updates** notices when they were refreshed and re-imports them — nothing is removed, existing entries are merged and enriched.

## ✨ Highlights

- **"Prisma (Holo-Glass)" signature look** — the default theme on Windows *and* the Switch app: deep petrol-black, teal-mint accents, gradient highlights. Switchable to classic Dark/Light via the theme dropdown.
- **Get the Switch app with one click** — the **Download Switch App** button fetches the always-latest homebrew `.nro` and can copy it straight onto your (auto-detected) Switch SD card.
- **Everything from DevCatSKZ in one click** — no scraping needed: pull the ready-made cheat archive and the complete database straight from the [`data` release](https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/tag/data) (the database stores only cover *URLs*, never cover images). Kept up to date as new cheats come in.
- **Self-update via "Check Updates"** — checks [GitHub](https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/latest) for a newer program build **and** newer cheats/database packages. Detects both a new version (e.g. 1.2) **and** a re-upload of the current release/data (a fix without a version bump, via the upload date). Program updates install themselves (the app restarts); data updates are downloaded and imported. Optional automatic check at startup.
- **Multi-language (6 languages)** — the whole interface in **English, Deutsch, Español, Français, Italiano and 日本語**. Switch it via the language selector next to the dark/light toggle; also selectable **in the installer**. Default is English. *(→ [Language](#-language))*
- **Many cheat sources** in one tool: cheatslips.com (scrape + official API), GBATempArchive, HamletDuFromage, Sthetix, Breeze, Chansey (60 FPS/Res/GFX), MyNXCheats, ibnux, titledb.
- **One-click complete dataset** (★ Scrape & Download Everything) plus targeted single actions.
- **SD-card export** (auto-detects the drive) and **ZIP export/import** in exactly the layout Atmosphère/Breeze/EdiZon expect.
- **Robust browser fallback** (Playwright) for cheats the API won't deliver, with automatic login handling and quota reset.
- **Searchable database GUI** with cover display, regions, versions, descriptions and live disk reconciliation.
- **Dark mode by default**, with a one-click toggle between light and dark — applies to the **whole program**: main window, table, detail panel, log, menus and **all sub-windows**. The choice is remembered between runs.

## 🌍 Language

The interface is available in **6 languages**: **English** (default), **Deutsch**, **Español**, **Français**, **Italiano** and **日本語 (Japanese)**.

- **In the program:** choose the language from the **language selector** at the bottom-right of the *Search* bar (next to the dark/light toggle). The app **restarts** to apply it; the choice is stored in `settings.json`.
- **In the installer:** pick the start language on the **"Program language"** page (pre-selected from the setup language). Choosing e.g. German setup makes the program **start in German** — stored via `default_lang.txt` next to the app.
- Translations are **natural** rather than literal; common tech terms stay in English (Download, Scrape, API, Token, ZIP, Title/Build ID, …). Missing translations fall back cleanly to English.

## Features

- **`metadata`**: Collects all games, Title IDs, Build IDs, **version**, **upload date**, **cheat count** and cheat names — **without login** — and maintains a **SQLite database** (`cheats.db`).
- **`db`**: Searches and shows the maintained database (game name, version, Title ID, Build ID, upload date, cheat count).
- **`gui`**: Graphical interface with a workflow-grouped toolbar and a searchable **database view**.
- **`download`**: Downloads the **full cheat-code files** via the **official API** (`X-API-TOKEN`) — **no browser, no reCAPTCHA**. The token is fetched from email/password or supplied directly.
- Saves the output in Switch Atmosphère format:
  ```
  titles/{TITLE_ID}/cheats/{BUILD_ID}.txt
  ```
- **Many cheat sources**: cheatslips.com (scrape + API) plus external archives — **GBATempArchive, HamletDuFromage** (`titles_complete.zip`), **HamletDuFromage 60FPS/Res/GFX**, **Sthetix** (daily aggregate, ~141k cheats), **Breeze/NXCheatCode**, **Chansey 60FPS/Res/GFX** (live repo), **MyNXCheats** (live repo), **ibnux** and **titledb** `cheats.json`. The **Source** column shows where each build's cheats came from; cheats are **merged** per build (duplicates are never lost), and codeless **stub files** (names/ads only) are skipped on import.
- **Update Recent**: fetches only the newest "latest cheat codes" pages from cheatslips to pick up new/updated cheats — without a full rescan.
- **Two decoupled scrape toggles** (stored in `settings.json`):
  - **"full catalog (all games)"** (default ON): discovery over the complete game catalog `/games`. Off = fast `/entry` feed (only recently uploaded cheats).
  - **"skip 0-cheat builds"** (default OFF): when on, builds with 0 cheats are dropped during the scrape. **Off by default**, so **all** listed builds enter the DB — even ones the API/HTML (temporarily) reports 0 cheats for. Those appear under the **"Not downloaded"** filter instead of silently missing. Both toggles combine independently.
- **HTML cheat count from the "Game releases" table**: the "Available cheats" column is read directly, so a build shows its true cheat count even when the API doesn't include that build (instead of a wrong 0).
- **0-cheat protection**: a re-scrape that returns 0/no cheats for a build no longer overwrites an already-known (real) cheat count.
- **Fully maintained SQLite database** (`cheats.db`) with all fields: name, Title ID, Build ID, version, upload date, cheat names, credits, description, cover image, banner, **region** (US/EU/AU/JP/KR/HK/CN/Homebrew) and **source**.
- **Metadata enrichment** via **individually callable buttons** (Get Names / Get Region / Get Versions from TitleDB / Get Versions Cheatslips / Get Descriptions / Download Covers): game names + covers from all titledb regions, switchbrew, tinfoil.io, GitHub name lists and the CheatSlips API; **region** tagging with several fallbacks (titledb → base game → switchbrew → homebrew tag → script heuristic); versions from titledb or cheatslips; descriptions from titledb.
- **Streaming scrape**: detail scraping starts immediately, in parallel with listing.
- **Disk reconciliation**: shows which builds are already downloaded and which are missing. A **file cache** (`.scan_cache.json`, mtime+size per file) makes repeated live scans many times faster (~5000 files: from ~45 s to ~1 s) — changed files are still re-checked.
- **Smooth GUI even with large databases**: the table is filled **asynchronously** (DB query + disk scan in the background, batched row inserts) — no more freezing on refresh or while typing in the search. The SQLite DB runs in **WAL mode** (parallel read/write without "database is locked") and has an **index on the Title ID** for fast enrichment runs.
- **Robust browser fallback** for cheats the API won't deliver: resolves every Build ID to the right cheat page (cheat cards **and** the "Game releases" table, incl. Build-ID landing pages), automatically **resets the quota** when the download limit is hit and retries. When the API download (including the automatic one after *Scrape*/*Update Recent*) hits the **daily quota**, the tool **automatically switches to the browser download** for the remaining builds — with a saved login this runs without further input. Only the **"Download (API only)"** button stays purely API-based.
- **"Unavailable" marking**: builds that provably have **no codes** on cheatslips (no cheat present, or a codeless upload = names only) are marked and **skipped** in future runs (list in `unavailable_builds.txt`, resettable via **Repair ▾ → "Retry 'unavailable' builds"**).
- **Export to the Switch SD card**: copies the downloaded cheats straight into the right format (**Atmosphère** `atmosphere/contents/<TID>/cheats/<BID>.txt`, **Breeze** or **EdiZon SE**). The SD card is found by **auto-detect**; empty/stub files are skipped, existing card cheats merged.
- **Export as ZIP** (and **re-import**): pack the same SD layout into a ZIP archive (all or only selected entries) — to unzip onto the SD-card root later; also via right-click context menu for individual cheats. Such an archive can be read back in any time via **"Import ZIP"**.
- **Cheatslips online status**: colored indicator (green/red) whether the site is reachable — automatically at program start (can be disabled) and any time via a button.
- **Browser Login**: one-time cheatslips login in the embedded browser; the cookies are stored persistently, so future browser downloads/quota resets are logged in automatically.
- **Targeted enrichment**: the *Get* functions (Names/Region/Versions/Descriptions) run over the whole DB via the toolbar button, but via the **right-click context menu** only for the **selected** entries.
- **Progress bar + Stop**, **CSV export**, **DB export** (back up the whole `cheats.db`), **package command** (ZIP for the SD card).
- **Standard shortcuts** in all text fields (Ctrl+A selects all, Ctrl+C/X/V) and full-screen support (**F11**, **Esc**, **Ctrl+M**), optimized for Full HD.

## Installation

Python 3.10+ is required. The **default download** uses the official API (no browser). For the **browser download** (cheats the API won't deliver, + automatic quota reset) the tool uses **Playwright** — already in `requirements.txt`.

```powershell
pip install -r requirements.txt
```

The Playwright **browsers are installed automatically** by the program the first time a browser download is used — **you don't have to do anything** (no manual `playwright install`). Optionally you can fetch them up front:

```powershell
playwright install chromium firefox
```

In the **download area** you can pick which browser is used from the **"Browser:"** dropdown: **Built-in** (bundled Chromium), **Chrome** (your installed browser) or **Firefox** (Playwright's Firefox, downloaded on demand into the app's data folder).

## Important notes

- The default download uses the **official CheatSlips API** (`https://www.cheatslips.com/api/v1`) — **no browser, no reCAPTCHA**. Only the optional **browser fallback** (for API gaps/quota) opens a browser window.
- CheatSlips cheats are **build-specific**: codes exist only for the exact Build IDs someone uploaded a cheat for. Build IDs without an upload (common for Pokémon titles/titledb versions) or **codeless uploads** (cheat names only) have no codes and are marked/skipped as *unavailable* — this is not a bug.
- The cheat **content** requires a token: you need an **API token** (from your CheatSlips account), or supply email+password and the tool fetches a token automatically via `POST /token`.
- **Metadata** (game name, Title ID, Build IDs, cheat names, credits, description, cover) is available **without a token**.
- There is **no** "list all games" API endpoint — discovery (Title IDs) still runs over the site's HTML (`metadata`/scrape), the content then via the API.

## Usage

### 1. Collect all game metadata (no login)

```powershell
python scraper.py metadata --output ./metadata
```

Result:
- `metadata/metadata.json` – all games with Title IDs, Build IDs, version, upload date, cheat count and cheat names.
- `metadata/by_build_id.json` – flat index **sorted by Build ID** (incl. version, upload date, cheat count).
- `cheats.db` – persistent **SQLite database**, updated on every run. Change the path with `--db`.

### Search / show the database

```powershell
# Show everything
python scraper.py db

# Search by game name
python scraper.py db --search "final fantasy"

# Filter by Build ID or Title ID
python scraper.py db --build-id 3CFD457814DD647F
python scraper.py db --title-id 010038B015560000
```

Output (columns): **Game | Version | Title ID | Build ID | Uploaded | Cheats**.

### Start the program

```powershell
python SwitchCheatsScraper.py
```

That's the single, obvious start command. (The old `python gui.py` / `python scraper.py gui` calls still work but are no longer needed.)

**As a ready Windows EXE with installer:** the program can be built into a self-contained `SwitchCheatsScraper.exe` (+ setup installer) — see **[BUILD.md](BUILD.md)** (`build.ps1` does everything automatically). When run as an EXE, it stores all data (database, downloads, settings, login profile) **in the same folder as the EXE** (portable) — so the app stays copyable/movable together with its data. Only if that folder is read-only (e.g. installed under Program Files with admin rights) it automatically falls back to `%LOCALAPPDATA%\SwitchCheatsScraper`. The bundled installer defaults to `C:\Program Files (x86)\Switch Cheats Scraper & Downloader` — in the wizard you can pick any other folder via **"Browse…"** or **create a new folder**. For a Program Files install the runtime data automatically lands in `%LOCALAPPDATA%\SwitchCheatsScraper` (that folder is writable); the **Portable** variant stays entirely next to the EXE.

On the **first launch** the window opens **maximized** (full screen); the window state is remembered afterwards, so it reopens the way you left it. It is freely resizable and, on a fresh start, sized for Full HD. Between the table and the **log window** there is a **drag handle** — you can enlarge/shrink the log as you like (with its own scrollbar). **Shortcuts:** **F11** full-screen on/off, **Esc** leave full-screen, **Ctrl+M** maximize/restore; in all text fields **Ctrl+A** (select all), **Ctrl+C/X/V** (copy/cut/paste).

The toolbar is grouped into workflow areas:

**★ Get Everything from DevCatSKZ Github Repo** (the highlighted card in the *External Cheat Sources* area — the fastest way to all data)
- The fastest start for new users — **without any scraping**. Downloads the maintainer's ready-made data straight from the [`data` release](https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/tag/data) and imports it:
  - **"Download Cheats"**: the ready-made cheat archive → all cheat files on disk + in the database.
  - **"Download Database"**: the complete GUI database (names, regions, versions, descriptions, cover **URLs**) merged into yours — nothing is removed, a real cheat count is never lost.
  - **"★ Download Complete"**: both in one step — the full experience.
- **Download covers optionally** — via the **"Download Covers"** checkbox in the card (**off by default**): when **on**, each DevCatSKZ download afterwards fetches the cover images; when **off**, no covers are downloaded. Covers are deliberately **not** part of the download: the database stores only cover **URLs** (pointing at the original source), never the images themselves — so no copyrighted image data is redistributed; each user loads covers directly from the source. Already-saved covers are skipped; the setting persists between runs.
- The maintainer keeps this data current over time — clicking again always fetches the **latest** cheats/database version.
- **Source:** the data lives in the repo's `data` release as `switch-cheats.zip` (all cheat files, Atmosphère layout) and `database.db` (complete GUI database). Direct links:
  - `https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/download/data/switch-cheats.zip`
  - `https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/download/data/database.db`
- **"Check Updates"** (button in the DevCat card, installed version shown next to it): checks [`/releases/latest`](https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/latest) for a newer **program** and the `data` release for newer **cheats/database**. Two detection rules apply to everything:
  1. **New version** — the release tag (e.g. `v1.2`) is higher than the installed version, **or**
  2. **Re-uploaded** — the upload date of the release asset or of `switch-cheats.zip`/`database.db` is newer than the stored baseline (first-run time). This also catches **updates without a version bump** (e.g. you re-upload a fixed 1.0).
  - When a **program update** is found, the tool downloads the installer, runs it (installs itself **in place**) and **restarts the app** afterwards — your data (DB, downloads, settings) stays untouched. From **source** it opens the release page instead (then `git pull`).
  - When a **data update** is found, `switch-cheats.zip`/`database.db` are downloaded, **unpacked and merged into your database** (nothing is removed). The tool then remembers the new baseline, so only real later re-uploads are reported again.
  - With the **"Check for updates at startup"** checkbox (default **on**) the program checks quietly in the background at every start and only speaks up when something is genuinely newer. The baseline lives in `update_state.json` in the data folder (survives updates).

**Scrape Cheats from cheatslips.com** (obtaining cheats)
- **"Scrape"**: starts metadata scraping from cheatslips.com in the background (live log, **progress bar**, **Stop** button). With a valid **token/login** the cheat files are saved **in the same pass** (the metadata API call already returns the content) — no separate download run needed.
- **"Update Recent"** + *pages*: fetches only the N newest "latest cheat codes" pages and adds new/updated builds — much faster than a full rescan.
- **"Download GBATemp Archive"**: imports the [HamletDuFromage cheat archive](https://github.com/HamletDuFromage/switch-cheats-db) (asset `contents_complete.zip`) and then fills names, covers and **region**.
- **"Download Hamlet TitleDB"** (HamletDuFromage): fetches the asset `titles_complete.zip` from the **latest** [switch-cheats-db release](https://github.com/HamletDuFromage/switch-cheats-db/releases/latest) and imports the cheats (source `hamlet-titledb`) — then names/covers/region, versions (titledb only) and a recount from disk.
- **"Download Hamlet 60FPS/Res/GFX"** (HamletDuFromage): as above, but fetches `titles_60fps-res-gfx.zip` (60-FPS, resolution and graphics cheats) from the **latest** release (source `hamlet-60fps`).
- **"Download Sthetix TitleDB"**: fetches `titles_complete.zip` from the **latest** [sthetix/nx-cheats-db release](https://github.com/sthetix/nx-cheats-db/releases/latest) — a **daily** auto-updated aggregate of GBAtemp + graphics cheats + switch-cheats-db + cheatslips (~141k cheats, the freshest single source). Source `sthetix`.
- **"Download Breeze NXCheatCode"**: fetches `titles.zip` (the database behind the **Breeze**/EdiZon-SE homebrew) from the **latest** [tomvita/NXCheatCode release](https://github.com/tomvita/NXCheatCode/releases/latest) — GBAtemp community codes, partly a different corpus than cheatslips. Source `breeze`.
- **"Download Chansey 60FPS/Res/GFX"**: imports the **live repo** [ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats](https://github.com/ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats) (main-branch ZIP) — the **original source** of the 60-FPS/resolution/graphics cheats, always fresher than release snapshots. Source `chansey-60fps`.
- **"Download MyNXCheats"**: imports the **live repo** [Arch9SK7/MyNXCheats](https://github.com/Arch9SK7/MyNXCheats) — a curated collection for ~50 recent top titles (TotK, Scarlet/Violet …). Source `mynxcheats`.
- All import buttons share the same flow (confirm → download/extract → DB import → names/covers/region + versions + recount) and **merge** cheats per build — duplicates across sources are never lost and never overwrite anything.
- **Stub protection**: aggregated databases (Breeze, sthetix …) sometimes contain **codeless stub files** (only cheat names or ad headers like "From MAX-CHEATS.com", not a single real code line). Such files are **skipped** on import (log: "Skipped N codeless stub file(s)") — the build stays visible as a 0-cheat entry in the DB, but no junk lands in `titles/` and none of it is merged into real cheat files. Existing stub files are removed by **Repair ▾ → "Clean invalid cheat files"**.
- **"Download TitleDB"**: imports titledb's own `cheats.json` as an extra source and then fills names, covers and **region**.
- **"Import Folder"**: reads existing `.txt` cheat files from the output folder into the DB.
- **"Import ZIP"**: imports a cheat **ZIP archive** back into the program (e.g. one previously made with **"Export to ZIP"**, or any archive in Atmosphère/Breeze/EdiZon layout). Recognizes all three layouts, skips empty/stub files, writes the cheats to `titles/{tid}/cheats/{bid}.txt` (source `import-zip`) and then fills names/region/versions. For the flat EdiZon layout (Build ID only) the Title ID is resolved from the existing DB.
- **"★ Scrape & Download Everything"**: builds the **complete database with one click** — runs in sequence: cheatslips scrape → **all external archives** (GBATemp → HamletDuFromage TitleDB → HamletDuFromage 60FPS/Res/GFX → **Sthetix** → **Breeze** → **Chansey** → **MyNXCheats** → titledb → ibnux) → names/covers/region/versions → download cheat files (with token, browser fallback at quota) → download cover images. Cancel any time with **Stop**.
- **Browser fallback** (no separate button anymore, but automatic via the *"Download via browser when API is limited"* checkbox in the download area, or **right-click → "Download via browser (bypass API limit)"**): fallback for cheats the API won't deliver (e.g. due to the daily quota). Opens a **real browser window** inside the program (Playwright — browser selectable via the "Browser:" dropdown) with the cheatslips login page, fills **email/password from the GUI automatically**, you only solve the reCAPTCHA and click Login (with saved cookies this is skipped on later runs). After login the tool takes over the browser session, **resolves every Build ID to the right cheat page** (cheat cards and "Game releases" table, incl. Build-ID landing pages), reads the download form (CSRF token) and submits it directly via a browser `fetch`. Each downloaded cheat file/ZIP is unpacked and sorted into `titles/{tid}/cheats/{bid}.txt`. The Playwright browsers are **installed automatically** on demand.
- Options: *full catalog (all games, slower)* — on = complete catalog `/games`, off = fast `/entry` feed —, *skip 0-cheat builds* (**off by default**; only enable if empty builds should really be skipped), *rescan* (don't skip known games), *download after scrape* (download straight after the scrape). The first two toggles are independent. All options have **hover tooltips** with a short explanation. **Stop** aborts running actions.

**Get Cheat Information** (enrichment) — **six single buttons**, each callable on its own (formerly a single combo button; now split so you can e.g. refresh only the region or only the versions):
- **"Get Names"**: fills missing game names + covers + metadata — from all titledb regions (US/EU/AU/JP/KR/HK, ~80 MB each, 7-day cache), then CheatSlips API, switchbrew, tinfoil.io, GitHub name lists and finally by inheriting from the base game (…000).
- **"Get Region"**: tags every title with its eShop region. Primarily from the titledb region files; then fallbacks for SKUs titledb doesn't list — derivation from the **base game** (…000) for update/DLC IDs, the **switchbrew** region column (EUR→EU, USA→US, JPN→JP, KOR→KR, CHN→CN), a **homebrew** tag (05… Title IDs or "Homebrew" in the name) and, as a last stage, a **script heuristic** (Japanese kana→JP, Chinese characters→CN). Remaining titles without a reliable source (JP/Asian retail SKUs, delisted titles) are deliberately left blank rather than mis-tagged.
- **"Get Versions from TitleDB"**: fills build versions **from titledb only** (fast, without cheatslips).
- **"Get Versions Cheatslips"**: fills the **remaining** versions from the cheatslips game pages (HTML, slower; only for builds titledb doesn't cover).
- **"Get Descriptions"**: fills missing **game descriptions + intro texts** for all titles from titledb (English regions, downloading/caching the region files).
- **"Download Covers"**: downloads the cover images of **all** database entries to `coversdownload/{title_id}.jpg` (already-present ones are skipped). Also available targeted via **right-click → "Download cover"** for selected rows.

> These toolbar buttons apply to the **whole database**. The same functions exist in the **right-click context menu** under *Get Cheat Information ▸* — there they run **only for the selected rows** (handy to refresh a single entry).

**Search + table filters** (own row **directly above the table**, below the download buttons): live search by **game name, Title ID or Build ID** (partial IDs too, case-insensitive); the table is refilled **asynchronously** so the UI never freezes while typing. Checkboxes **Auto scan** (re-read disk status automatically), **Not downloaded** (only not-downloaded builds), **Show Unnamed Games** (only entries without a real name), **Hide placeholder builds** (hide placeholder builds), **Show Covers** (cover in the detail panel on/off — **off by default**), **Save Covers** (cache loaded covers locally at `coversdownload/{title_id}.jpg` — on by default, then available offline), **Show Description** (description text in the detail panel — off by default). At the far right of this row the **☀ Light Mode / ☾ Dark Mode** button switches the color scheme — **dark mode is the default**; the switch recolors the **whole program** instantly (main window, table, panels, log, menus and dialogs) and the choice is remembered between runs. Next to it, the **language selector** switches the interface language (the app restarts to apply it).

**Scrape & Download Cheat Files · cheatslips.com** (own area)
- Enter email/password **or** an API token (*remember* saves the password).
- **"Browser Login"**: **one-time cheatslips login for new users** — opens the chosen browser (Playwright), pre-fills email/password from the GUI, you only solve the reCAPTCHA and click Login. The **session cookies are stored persistently in the program profile** (`browser_profile/`), so **all future browser downloads and quota resets are logged in automatically** — never log in again. Best done once right after the first program start.
- **Online indicator + "Check Online"**: colored status whether cheatslips.com is **reachable** — **green ● Online** / **red ● OFFLINE** (yellow while checking). Checked **automatically at every program start** (disable via the *"check at startup"* checkbox, stored in settings) and triggerable manually any time via the **"Check Online" button** — even while a scrape/download runs. Responses below HTTP 500 count as online; timeouts/connection errors/5xx as offline.
- **Output**: target folder for the `.txt` files — type a path, pick via **"…"** in the file dialog, or open it in Explorer with **"Open"**.
- **"Download (API only)"** – downloads cheat files **only via the API** (never the browser). Uses the selected rows, or **all** games if nothing is selected. Stops when the API daily quota is hit.
- **"Download Selected"** – downloads only the **selected** games (or **all** if nothing is selected). Uses the API first and **automatically switches to the browser download once the API daily quota is hit** — the same applies to the automatic download after *Scrape*/*Update Recent* (*download after scrape*). Only **"Download (API only)"** stays purely API-based.
- **"Build Full Dataset"** – builds a **complete dataset** for **all** games in one run (each step continues even if a previous one fails):
  1. **Download all cheat files** (API; already-present builds are skipped, downloaded ones marked source `cheatslips`),
  2. **Fill names, covers, region, versions + descriptions** (titledb/API; also refreshes the cheat count from the files),
  3. **Fix ID names** (replace Title-ID placeholders, remove placeholder builds),
  4. **Fix 0-cheat entries** (refresh + re-fetch 0-cheat entries via API).
  Without a valid token the content is skipped, but names/region/versions/fixes still run.
- **Download via browser when API is limited** (checkbox, default on): when **on**, the tool opens the **logged-in browser from the start** for the missing builds (reset-and-retry loop). When **off**, the download runs purely via the API first and switches to the browser **only when the quota is hit** (only "Download (API only)" avoids the browser entirely). In both cases a **logged-in browser window** (Playwright) is opened, the **website quota is reset automatically** and the cheats are downloaded **directly via the browser** until everything is fetched. For builds the API won't deliver, the right cheat page is found (cards **and** "Game releases" table, Build-ID landing pages) and the download form is submitted via the browser session. If the browser download hits the website limit (codeless "preview" ZIP), the quota is reset and retried once.
- **"Browser:" dropdown**: selects the browser for browser downloads/quota resets — **Built-in** (bundled Chromium), **Chrome** (your install, via the Playwright channel) or **Firefox** (Playwright's Firefox). Missing Playwright browsers are **downloaded automatically** on first use.
- **"Reset API Limit"**: resets the quota once manually via the browser.
- Builds **without codes** on cheatslips (no cheat present or codeless upload) are marked *unavailable*, logged in `unavailable_builds.txt` and skipped in future. Reset via **Repair ▾ → "Retry 'unavailable' builds"**.

**Database** (bar below the table)
- **"Refresh"**: first reconciles each build's cheat count with the actual `.txt` file on disk (in the background) and then refreshes the table — so the shown count always matches the file content. This also runs **automatically after a single download** (*Download this / via API / via browser*), so a just-downloaded build flips to "downloaded" and shows its real count without pressing it.
- **"Add Entry"** (manual build: Title ID, Build ID, cheat content, name, version).
- **"Export CSV"**: database as CSV with all columns (Excel-compatible, UTF-8).
- **"Export DB"**: backs up the whole `cheats.db` as a consistent copy (SQLite backup) to a location you choose (default file name `database.db`, matching the data-release asset).
- **"Import DB"**: imports a previously exported database (`.db`). A dialog lets you choose: **Merge** into the current database (adds/updates builds, nothing removed, existing entries keep their data and never lose a real cheat count) or **Replace** — replace the current database entirely (a timestamped backup of the current database is saved first). Runs in the background and refreshes the table afterwards.
- **"Export to SD"**: copies the downloaded cheat files **straight to the Switch SD card** in the right format. A dialog lets you:
  - pick the **SD-card root** (navigate via **Browse…** or **Auto-detect** — finds the drive automatically by the CFW folders `atmosphere/`, `switch/`, `Nintendo/`, `bootloader/`, `emummc/`),
  - pick the **target tool**:
    - **Atmosphère** → `atmosphere/contents/<TitleID>/cheats/<BuildID>.txt` — **auto-loads at game start**. Recommended, works for Atmosphère, EdiZon-SE **and** Breeze (all read this path).
    - **Breeze** → `switch/breeze/cheats/<TitleID>/<BuildID>.txt` — inactive until you enable them in the Breeze app.
    - **EdiZon SE** → `switch/EdiZon/cheats/<BuildID>.txt` — EdiZon loads the file at game start and moves it into the Atmosphère folder itself.
  - the **scope**: **all** downloaded cheats or only the **selected** rows.

  Only files with **real** cheats are copied (empty/stub files are skipped); existing cheats on the card are **merged, not overwritten**. Runs in the background with progress/log and a summary.
- **"Export to ZIP"**: exports the downloaded cheats into a **ZIP archive** with **exactly the same SD layout** (Atmosphère / Breeze / EdiZon selectable) — just **unzip** onto the SD-card root, done. In the dialog you pick the target file (**Save As…**), layout and scope (all or selected rows). The default file name is `switch-cheats.zip` (matching the data-release asset). Empty/stub files are skipped; an empty result creates no file. The same action is available via **right-click → "Export to ZIP"** for the selected entries.
- **"Repair ▾"**: rarely used repairs — *Clean invalid cheat files* (remove empty/placeholder **and codeless stub** files; the DB entry stays visible as a 0-cheat row), *Retry quota-skipped builds* (reload the list from `quota_skipped.txt`), *Retry 'unavailable' builds* (reset the "no cheat on cheatslips" marks so those builds are retried), *Fix 0-cheat entries* (refresh + re-fetch 0-cheat entries via API), *Recount cheats from disk* (recount the cheat count for **all** builds from the actual `.txt` files and write it to the DB — corrects entries wrongly showing 0; deletes nothing), *Fix ID names* (replace Title-ID placeholders with real names) and *Sync titles folder with DB*.
- **"Clear DB"**: empties the database **and deletes all downloaded files on disk** (with confirmation) — cheat files (`titles/`, `by_bid/`), covers (`coversdownload/`), the packaged ZIP, the `meta/` folder and cache/skip files. The titledb region caches (`titledb_*.json`) and `settings.json` are kept. **DB path** selectable on the right.

**Table** — columns: DL · Game · **Region** · Version · Title ID · Build ID · Uploaded · Cheats · **Source**.
- **DL status (OK/empty)**: reconciled against actually present `.txt` files — downloaded rows green, **nameless rows orange**.
- **Source**: origin of the cheats per build (`cheatslips` / `cheatslips-web` / `gbatemp` / `hamlet-titledb` / `hamlet-60fps` / `sthetix` / `breeze` / `chansey-60fps` / `mynxcheats` / `ibnux` / `titledb` / `gamesmd` / `disk` / `npshop`), or `unavailable:<reason>` for builds without codes on cheatslips.
- **Detail panel** on the right: cover, download status, **Title ID** and **Build ID** (clearly labeled, monospace), all cheats, publisher, genre, release date, region, source, credits and the description of the selected build. Covers are loaded from the URL on first display and (when **Save Covers** is on, the default) cached locally at `coversdownload/{title_id}.jpg` — then available offline without a re-download.
- **Column sorting** on click (date chronological, version + cheat count numeric), **double-click** copies a cell, **Ctrl+A/C** selects/copies in the table. **Right-click** opens the context menu:
  The menu is **grouped** by task (Obtain → Check → Edit → Metadata → Delete → Global); all count actions show the number on multi-select (e.g. "Delete (3)"):
  1. **Download this / via API / via browser** (bypass API limit) — also works for a multi-selection,
  2. **Check cheat file** (checks the build's cheat file on disk: present? how many **real** cheats with code lines? which names? — also detects codeless stub files and **writes the counted number straight back into the DB**), **Open in Explorer** (shows the cheat `.txt` selected in File Explorer; otherwise the title folder), **Open cheatslips page** (open the build page in the browser), **Export to ZIP** (export the selected cheats as a ZIP with SD layout),
  3. **Edit entry (codes)**, **Edit Title ID / Build ID** (also moves the file on disk), **Add new entry**,
  4. **Get Cheat Information ▸** (submenu with the same actions as the toolbar area of the same name — *Get Names*, *Get Region*, *Get Versions from TitleDB*, *Get Versions Cheatslips*, *Get Descriptions*). In the context menu they run **only for the selected rows** (without a selection, for the whole DB); the toolbar buttons still run over the whole database. Plus both cover options together: *Download Covers (all)* and *Download cover (selected)*,
  5. **Delete entry** (also removes the file) — deliberately **isolated at the end** so it isn't hit by accident,
  6. **Reset API Limit** (global, reset the quota once via the browser).
- **Status bar**: shown builds · downloaded · missing · without names.

CSV export also works via CLI:

```powershell
python scraper.py db --export-csv cheats.csv
python scraper.py db --search "zelda" --export-csv zelda.csv
```

**CSV columns:** Game Title, **Region**, Version, Version Date, Title ID, Build ID, Upload Date, Cheat Count, Credits, Description, Publisher, Developer, Genre, Release Date, Player Count, Size, Rating, Game Description, Slug, Source ID, Cheat ID, Cover URL, Banner URL, Cheat Names (JSON), **Source** (gbatemp/titledb/cheatslips/disk).

Disk reconciliation (what's already downloaded?) also via CLI:

```powershell
# Reconcile the DL column against ./cheatsdownload
python scraper.py db --output ./cheatsdownload

# Show only still-missing builds
python scraper.py db --output ./cheatsdownload --missing-only
```

### Tests & logging

```powershell
# Unit tests (standard library only)
python -m unittest test_scraper

# Also mirror console output into a log file
python scraper.py metadata --log-file scraper.log
python scraper.py download --token "YOUR_API_TOKEN" --log-file scraper.log
```

The GUI writes to `scraper.log` automatically. The log file is **size-limited**: if it grows over 5 MB, it is trimmed to the last ~1 MB on the next start (the oldest part is dropped, marked `===== log truncated =====`).

### 2. Download cheats (API)

Prerequisite: a filled `cheats.db` (see `metadata`/scrape). The download uses the Title IDs from the database and fetches the cheat content via the API.

All games from the database, with email/password (token fetched automatically):

```powershell
python scraper.py download --db ./cheats.db --email "you@email.com" --password "yourpassword" --output ./cheatsdownload
```

Or with a ready API token from your account:

```powershell
python scraper.py download --db ./cheats.db --token "YOUR_API_TOKEN" --output ./cheatsdownload
```

A single game via the Title ID:

```powershell
python scraper.py download --db ./cheats.db --token "YOUR_API_TOKEN" --title-id 010038B015560000
```

The files land in Switch Atmosphère format:

```
cheatsdownload/
└── titles/
    └── {TITLE_ID}/
        └── cheats/
            └── {BUILD_ID}.txt
```

So you can copy the folder straight to the Switch SD card.

### 3. Options

- `--flat-output` — all cheat files as `{BUILD_ID}.txt` in `cheatsdownload/by_bid/`.
- `--no-resume` — re-download files that already exist (otherwise they're skipped).
- `--log-file scraper.log` — also mirror console output to a file.

### 4. Parallel scraping in metadata mode

With `--workers` the game details can be scraped in parallel:

```powershell
python scraper.py metadata --output ./metadata --workers 8
```

### 5. Pack cheat files as a ZIP

After the download you can pack the `titles/` structure into a ZIP to copy it easily onto the Switch SD card:

```powershell
python scraper.py package --output ./cheatsdownload
```

That creates `cheatsdownload/cheatsdownload.zip`.

## Output

Without `--flat-output` the cheat files are stored in Atmosphère format:

```
cheatsdownload/
└── titles/
    └── 010038B015560000/
        └── cheats/
            └── 3CFD457814DD647F.txt
```

With `--flat-output` all files are sorted directly by Build ID:

```
cheatsdownload/
└── by_bid/
    ├── 3CFD457814DD647F.txt
    └── AAAA1ED3B0A458D6.txt
```

Each `.txt` contains all cheat codes for that Build ID in the standard format:

```
[Max Money]
04000000 ...
...

[Inf HP]
04000000 ...
...
```

## Project structure

```
.
├── SwitchCheatsScraper.py  # ► start launcher (python SwitchCheatsScraper.py)
├── scraper.py          # main script (metadata, download, package, db, gui) + quota-reset loop
├── gui.py              # graphical interface (scrape, DB view, download, CSV)
├── i18n.py             # multi-language (6 languages) + auto-translation of the Tk UI
├── playwright_scrape.py # browser fallback (Playwright): Build-ID resolution, quota reset, download
├── browser_scrape.py   # HTML cheat extraction (extract_cheat_text_from_html)
├── test_scraper.py     # unit tests (python -m unittest test_scraper)
├── requirements.txt    # Python dependencies
├── SwitchCheatsScraper.spec # PyInstaller config (build to EXE)
├── installer.iss       # Inno Setup script (Windows installer)
├── build.ps1           # one-click build: EXE + installer
├── BUILD.md            # build guide (EXE + installer)
├── .gitignore          # ignores data/caches/build artifacts
└── README.md           # this file

# Created automatically at runtime (excluded via .gitignore):
#   cheats.db           – persistent SQLite database (WAL mode: plus .db-wal/.db-shm)
#   cheatsdownload/      – downloaded cheat files (titles/, by_bid/, meta/, ZIP)
#   cheatsdownload/.downloaded_cache.json – cache of already-present Build IDs
#   cheatsdownload/.scan_cache.json – file-validity cache (mtime+size) for fast scans
#   cheatsdownload/unavailable_builds.txt – builds without codes on cheatslips (skipped)
#   coversdownload/      – locally cached cover images ({title_id}.jpg)
#   browser_profile/     – persistent Chromium profile (login/cookies) for the browser fallback
#   titledb_*.json       – cached titledb region files (~80 MB each)
#   settings.json        – GUI settings (email/token – private!)
#   update_state.json    – self-updater baseline (first-install / upload timestamps)
#   scraper.log          – log file (size-limited: >5 MB → trimmed to the last ~1 MB)
```

## Troubleshooting

- **ModuleNotFoundError**: run `pip install -r requirements.txt`.
- **"API token is invalid"**: check email/password or use a valid token from your CheatSlips account.
- **Empty database on download**: run **Scrape**/`metadata` first so Title IDs are in `cheats.db`.
- **503 error while scraping**: the site is throttling — wait a bit; the tool retries automatically with backoff.

## Disclaimer

- Only use the tool with your own CheatSlips.com account.
- Respect the CheatSlips.com terms of service.
- All credit for the cheat codes belongs to the original authors and uploaders.

---

**Switch Cheats Scraper & Downloader** · Version 1.3 · © DevCatSKZ
