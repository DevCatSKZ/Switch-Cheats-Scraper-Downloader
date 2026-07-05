<!-- Language: English (below) · Deutsch (further down) -->
**🇬🇧 English** · [🇩🇪 Deutsch](#changelog-deutsch)

# Changelog

All notable changes to this project are documented here.

## v1.1 — 2026-07-05

### Added
- **Self-update ("Check Updates")** in the DevCatSKZ card: checks GitHub for a
  newer program version *and* newer cheats/database packages. It detects a new
  version (e.g. 1.1) **and** a re-upload of the current release/data asset (a fix
  without a version bump, via the upload date). Program updates install
  themselves (restart); data updates are downloaded and imported. Optional
  automatic check at startup.

### Fixed
- DevCatSKZ downloads crashed in the packaged (windowed) build with
  `'NoneType' object has no attribute 'write'` — fixed (logging now tolerates a
  `None` stdout).

### Changed
- Covers are now fetched via the **"Download Covers"** checkbox (off by default)
  instead of a yes/no prompt after each download.
- The **"External Cheat Sources"** area is more compact (no wasted width); the
  DevCatSKZ card description moved into a tooltip.
- **Installer** now defaults to `C:\Program Files (x86)\Switch Cheats Scraper &
  Downloader` (needs admin); the destination folder is freely selectable /
  creatable in the wizard.

## v1.0 — 2026-07-05

Scrape & download Nintendo Switch cheats from CheatSlips.com, GBATemp/HamletDuFromage,
Sthetix, Breeze (NXCheatCode), ChanseyIsTheBest (60FPS/Res/GFX), MyNXCheats, ibnux and
titledb. Manage all your cheats in a searchable SQLite database and export them straight
to your Switch SD card (Atmosphère / Breeze / EdiZon) or a ZIP.

### Get everything from DevCatSKZ
- A prominent one-click section to **download the maintainer's prebuilt data**
  from GitHub instead of scraping: **Download Cheats** (ready-made archive),
  **Download Database** (the full GUI database, merged in), or **Download
  Complete** (both). After each, the app offers to fetch covers too.
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

---

<a id="changelog-deutsch"></a>
[🇬🇧 English](#changelog) · **🇩🇪 Deutsch**

# Änderungsverlauf

Alle nennenswerten Änderungen an diesem Projekt sind hier dokumentiert.

## v1.1 — 05.07.2026

### Neu
- **Selbst-Update („Check Updates")** in der DevCatSKZ-Karte: prüft GitHub auf
  eine neuere Programmversion *und* neuere Cheats-/Datenbank-Pakete. Erkennt eine
  neue Version (z. B. 1.1) **und** ein erneutes Hochladen des aktuellen
  Release-/Daten-Assets (Fix ohne Versionssprung, über das Upload-Datum).
  Programm-Updates installieren sich selbst (Neustart), Daten-Updates werden
  geladen und importiert. Optional automatisch beim Start.

### Behoben
- DevCatSKZ-Downloads brachen im installierten (Fenster-)Build mit
  `'NoneType' object has no attribute 'write'` ab — behoben (Logging verträgt
  jetzt `None`-stdout).

### Geändert
- Cover werden jetzt über die Checkbox **„Download Covers"** (standardmäßig aus)
  geladen — statt Nachfrage-Dialog nach jedem Download.
- Der **„External Cheat Sources"**-Bereich ist kompakter (kein verschwendeter
  Platz); die DevCatSKZ-Karten-Beschreibung liegt jetzt im Tooltip.
- Der **Installer** schlägt jetzt `C:\Program Files (x86)\Switch Cheats Scraper &
  Downloader` vor (Adminrechte); der Zielordner ist im Assistenten frei wählbar /
  neu anlegbar.

## v1.0 — 05.07.2026

Nintendo-Switch-Cheats von CheatSlips.com, GBATemp/HamletDuFromage, Sthetix,
Breeze (NXCheatCode), ChanseyIsTheBest (60FPS/Res/GFX), MyNXCheats, ibnux und
titledb **scrapen und herunterladen**. Alle Cheats in einer durchsuchbaren
SQLite-Datenbank verwalten und direkt auf die Switch-SD-Karte
(Atmosphère / Breeze / EdiZon) oder als ZIP exportieren.

### Alles von DevCatSKZ
- Ein hervorgehobener Ein-Klick-Bereich, um die **fertigen Daten des Maintainers**
  von GitHub zu laden statt zu scrapen: **Download Cheats** (fertiges Archiv),
  **Download Database** (die komplette GUI-Datenbank, gemergt) oder **Download
  Complete** (beides). Danach bietet die App jeweils an, auch die Cover zu laden.
- Die Datenbank enthält nur Cover-**URLs**, niemals Cover-Bilder — es werden keine
  urheberrechtlich geschützten Bilddaten weitergegeben; jeder Nutzer lädt die
  Cover selbst von der Quelle.

### Quellen
- Scrape + offizielle API von **CheatSlips.com** (Metadaten ohne Login,
  Cheat-Inhalte über API-Token / E-Mail+Passwort).
- Externe Cheat-Archive: **GBATemp/HamletDuFromage** (`titles_complete.zip`),
  **HamletDuFromage 60FPS/Res/GFX**, **Sthetix** (tägliches Aggregat), **Breeze /
  NXCheatCode**, **Chansey NX-60FPS-RES-GFX** (Live-Repo), **MyNXCheats** (Live-Repo),
  **ibnux** und **titledb** `cheats.json`.
- Ein-Klick-Pipeline **★ Scrape & Download Everything**.

### Download
- Offizieller **API**-Download (kein Browser) mit automatischem
  **Browser-Fallback** (Playwright) bei erreichter Tages-Quota — löst jeden Build
  zu seiner Cheat-Seite auf, erledigt Login/reCAPTCHA einmalig, setzt die
  Website-Quota zurück und versucht es erneut.
- **Browser-Login**-Button: einmaliger Login, Cookies bleiben für künftige Läufe erhalten.

### Anreicherung
- **Namen/Cover**, **Regionen** (mit switchbrew-/Homebrew-/Schrift-Fallbacks),
  **Versionen** (titledb + cheatslips) und **Beschreibungen** füllen.
- Versionen aus dem Kontextmenü laufen nur für die markierten Zeilen.

### Export / Import
- **Export auf die SD-Karte** (Atmosphère-/Breeze-/EdiZon-Layout, Laufwerks-Auto-Erkennung).
- **Export als ZIP** (dieselbe SD-Struktur, datierter Standard-Dateiname) und
  **Import ZIP** zurück in die Datenbank.
- **Export DB** / **Import DB**: die komplette `cheats.db` sichern und später
  wieder importieren — in die aktuelle Datenbank **mergen** (nichts wird entfernt,
  eine echte Cheat-Anzahl geht nie verloren) oder die aktuelle **ersetzen**
  (vorher wird ein Backup erstellt).

### App
- Durchsuchbare Datenbank-GUI (nach Name, Title-ID oder Build-ID), Cover-Panel,
  Live-Disk-Abgleich, asynchrones Tabellen-Refresh, WAL-Datenbank.
- **Dark Mode als Standard** mit Ein-Klick-Umschalter zwischen Hell und Dunkel,
  der das komplette Programm neu einfärbt — Hauptfenster, Tabelle, Detail-Panel,
  Log, Menüs und alle Unterfenster; die Auswahl bleibt zwischen den Läufen erhalten.
- Online-Status-Anzeige, größenbegrenztes Log, Datei-Scan-Cache.
- Portable Datenspeicherung neben der `.exe` (weicht auf `%LOCALAPPDATA%` aus,
  wenn schreibgeschützt). Windows-Installer enthalten.
