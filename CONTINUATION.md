# CheatSlips Scraper – Continuation Guide

Stand: Juni 2026 (Basis) + **Update Juli 2026** (siehe Block direkt hierunter). Dieses Dokument beschreibt Architektur, Klassen und offene Punkte für den nächsten Entwickler/Agenten.

## ⚡ Update Juli 2026 — was seit Juni neu ist

**Zwei GUIs, ein Motor.** `SwitchCheatsScraper.py` startet standardmäßig die
**moderne Holo-Glass-Shell** (`gui_modern.py`, Klasse `ModernApp(ScraperGUI)`);
`--classic` bzw. `python gui.py` startet die klassische Oberfläche. Beide teilen
sich **alle** Widgets/Handler: `gui.py`s Layout wurde in einen
`_compose_ui()`-Hook + parametrisierte Sektions-Builder zerlegt
(`_build_sources_grid/_build_devcat_card(beside_grid)/_build_info_section/`
`_build_cheatslips_section/_build_filter_section(with_pickers)/`
`_build_theme_lang_pickers(side)/_build_main(parent)/`
`_build_database_bar(parent, compact)` [compact = 2-zeilig für die Modern-Shell]
`/_build_log(parent, with_status)`). ModernApp überschreibt nur `_compose_ui`,
`_apply_theme` (+ eigene Styles/`_paint_modern`), `_set_busy` (Footer-Stop) und
`__init__` (optimale Fenstergröße ~1560×1000 statt maximiert). Neue Widgets in
Sektionen einbauen ⇒ erscheinen automatisch in **beiden** GUIs. Achtung i18n:
Der Auto-Hook übersetzt nur statische `text=`-Literale — f-Strings brauchen
explizit `t()`; generische Keys („Scrape", „Browse") vor dem Anlegen auf
Kollisionen prüfen.

**Self-Update, still & verifiziert.** Installer ist **per-user**
(`PrivilegesRequired=lowest`, `{autopf}` → LocalAppData\Programs, kein UAC).
Beim Start gefundene Programm-Updates installieren sich still (`/SILENT`,
Verb `open` statt `runas` bei schreibbarem App-Ordner) und die App startet neu;
Downloads werden vorher gegen GitHubs **SHA-256-Asset-Digest** geprüft
(`fetch_github_release` liefert `digest`, Prüfung in `_program_update_worker`).
Schalter „Update automatically" (Default AN); manueller Check zeigt immer den
neu gestalteten Dialog (Markdown-Notes via `_render_release_notes`).

**Neue UX-Bausteine (gui.py):** Welcome-Dialog beim Erststart mit leerer DB
(`_maybe_show_welcome`/`WelcomeDialog`, Flag `welcome_shown` in settings);
rotierende Sicherheits-Backups `backup_database()` (→ `<db>.bak`/`.bak2`,
WAL-sicher) vor Clear/Import/Fix-ID/Sync/Recount/Clean; Windows-**Toasts**
(`show_windows_toast`, reines Win32) bei Scrape-Ende / Daten-Update /
Update-Installation, nur wenn das Fenster im Hintergrund ist; Button
**„Download Android App"** in der ★-Karte (Speichern-unter → neueste APK,
SHA-256-geprüft).

**Emulator-Ökosystem.** `export_cheats_for_emulator()` +
„Export for Emulators"-Dialog erzeugen `<TitleID>/<GameName>/cheats/<BuildID>.txt`
(Yuzu-Familie `load`, Ryujinx `mods`), Ordner oder ZIP; das fertige
`switch-cheats-emulator.zip` liegt im `data`-Release (names.json entfällt).
Die **Android-App** lädt genau dieses Paket, entpackt in einen öffentlichen
Ordner (schnelle `java.io.File`-Writes; SAF war ~5× langsamer) — Import dann
pro Spiel im Emulator (Add-ons → „Mods and cheats"), weil Android 11+ fremde
`Android/data` für Dritt-Apps komplett sperrt (gilt für Eden **und** Suyu
**und** Sudachi).

**Feature-Updates (2026-07-10, Commits e3b4c87 / 66089ea / b94c544):**
- **Cheat-Editor** (`CheatEditorDialog`; Doppelklick klassisch / „Edit codes"
  modern): Syntax-Highlighting + **Validierung** (`classify_cheat_line`:
  gültige Zeile = 1–4 Wörter à 8 Hex; Fehler rot+unterstrichen, Live-Zähler,
  Speichern-Rückfrage), „＋ New cheat"-Vorlage, Rechtsklick-Blockoperationen
  (Duplizieren/Löschen). Gemeinsamer Öffner: `_open_cheat_editor_for(tid,bid)`.
- **Modern-Shell-Seiten:** ⚙ Settings (alle Optionen zentral), Live-Dashboard
  (Stats + klickbares „Recently updated"), **Spiel-Detailseite**
  (`open_game_page`; Doppelklick in der modernen Bibliothek routet hierher —
  Cover, Beschreibung, Build-Karten, aufklappbare Cheats, ⭐/Download/Export).
  Bibliothek: Chips (⭐ Favoriten, ⚡ Has cheats, 🖼 No cover, 🔎 Search in
  cheats), Spalten-Menü, Filter-Presets (persistiert).
- **⭐ Favoriten/Watchlist:** in settings.json (`favorites`, überlebt
  DB-Replace); nach Daten-Updates Diff → Toast, wenn Favoriten neue Cheats
  bekamen (`_favorite_counts_snapshot`/`_favorite_news`).
- **Cheat-Inhaltssuche:** `GameDatabase.search(in_cheats=True)` matcht
  `cheat_names` (JSON-Text, LIKE NOCASE).
- **Repair → „Find invalid code lines":** scannt alle Dateien mit den
  Editor-Regeln, `InvalidLinesDialog` (nicht-modal) → Doppelklick öffnet den
  Editor, gefixte Dateien fallen aus der Liste (Referenzbestand: 183 Treffer).
- **Daten-Auto-Update** (`keep_data_updated`, Settings-Opt-in) + einmaliger
  **Migrations-Hinweis** für Program-Files-Installationen (Download+Start des
  Per-User-Installers, SHA-256-geprüft).

**Merkzettel:** Details/Fallstricke stehen in den Memory-Notizen
(`modern-gui-architecture`, `windows-auto-update`, `android-cheat-delivery`,
`i18n-architecture`).

> **Hinweis:** Dieses Dokument betrifft nur das **Python-Desktop-Tool**. Die
> Switch-Homebrew-App (`.nro`) ist ein eigenständiges C++/SDL2-Teilprojekt und
> hat eine eigene Handoff-Doku: `SwitchCheatsNRO/CONTINUATION.md`.

> **Primärpfad: offizielle CheatSlips-REST-API (`X-API-TOKEN`).** Zusätzlich gibt es einen **Browser-Download** (Playwright, `playwright_scrape.py`) für Cheats, die die API nicht liefert, und um das Website-**Quota automatisch zurückzusetzen**. Playwright ist Pflicht-Abhängigkeit (`requirements.txt`); die **Browser (Chromium + Firefox) installiert das Programm bei Bedarf selbst** (`playwright_scrape.install_browsers` / `_launch_auto`) — kein manuelles `playwright install` nötig. Gesteuert über die GUI-Checkbox *„Download via browser when API is limited"*, das **„Browser:"-Dropdown** (Built-in/Chrome/Edge/Firefox) bzw. das Kontextmenü.

## 1. Projekt-Zweck

Python-Tool zum Sammeln und Herunterladen von Nintendo-Switch-Cheatcodes von [CheatSlips.com](https://www.cheatslips.com) sowie aus zwei externen Archiven.

| Modus | Beschreibung |
|-------|-------------|
| `metadata` | HTML-Scraping (kein Login): Sammelt Title-IDs, Build-IDs, Version, Upload-Datum, Cheat-Namen; pflegt `cheats.db`. |
| `download` | API-Download (Token nötig): Lädt Cheat-Inhalte über `GET /cheats/{titleId}/{buildId}`. |
| `package` | Packt `titles/`-Struktur als ZIP für die SD-Karte. |
| `db` | CLI-Suche/Anzeige der SQLite-Datenbank. |
| `gui` | Tkinter-GUI (`gui.py`) mit allen Funktionen. |

## 2. Ausgabe-Struktur

```
cheatsdownload/
├── titles/
│   └── {TITLE_ID}/
│       └── cheats/
│           └── {BUILD_ID}.txt   <- Atmosphere-Format
├── by_bid/                       <- bei --flat-output
└── cheatsdownload.zip            <- bei `package`

cheats.db       <- SQLite-Datenbank (zentrale Wahrheitsquelle)
scraper.log     <- automatisches Log der GUI
```

## 3. Architektur

### Klassen (`scraper.py`)

| Klasse | Zweck |
|--------|-------|
| `GameDatabase` | SQLite `cheats.db` — upsert-basiert, alle Metadaten + Build-Inhalte |
| `CheatslipsMetadataScraper` | HTML-Scraping (kein Login): Spielliste, Slugs, Build-IDs, Version |
| `CheatslipsAPI` | REST-API-Wrapper: Token-Holen, `get_game()`, `get_cheat()`, `token_works()` |
| `StateManager` | Interne Resume-Verwaltung fuer den `download`-CLI-Modus |
| `ScraperGUI` (`gui.py`) | Tkinter-GUI — alle Buttons, Filter, Tabelle, Log-Panel |

### Datenmodell `GameDatabase.builds`

Primaerschluessel `(build_id, title_id)`. Alle `upsert_*`-Methoden nutzen `COALESCE` — bestehende Werte werden nie ueberschrieben, fehlende werden ergaenzt.

Spalten: `build_id, title_id, slug, game_title, image, banner, version, source_id, upload_date, cheat_count, cheat_names (JSON), credits, description, publisher, developer, category, game_description, release_date, players, size_bytes, rating, source, last_updated`

Die Spalte `source` markiert die Herkunft (`cheatslips` / `cheatslips-web` / `gbatemp` / `ibnux` / `titledb` / `gamesmd` / `disk` / `npshop`) **oder** den Sonderwert `unavailable:<reason>` für Builds, die auf cheatslips nachweislich keine Codes haben. `builds_for_download()` filtert `source LIKE 'unavailable%'` heraus, sodass solche Builds in künftigen Läufen übersprungen werden; die Markierung überlebt Metadaten-Rescans (COALESCE) und wird nur über `clear_unavailable()` / GUI „Retry 'unavailable' builds" zurückgesetzt.

**0-Cheat-Sichtbarkeit (Stand 2026-07-01):** `cheat_count`/`cheat_names` werden im `upsert_build`-ON-CONFLICT geschützt — ein erneuter Scrape mit 0/NULL Cheats überschreibt einen bereits bekannten positiven Wert **nicht** (CASE-Logik), nur positive Werte aktualisieren. Die Discovery-Quelle und der 0-Cheat-Filter sind **entkoppelt** (zwei GUI-Checkboxen, beide in `settings.json`):
- `self.scrape_full_catalog` (Default AN) → `scrape_all_streaming(entry_only=not full_catalog)`: an = `/games` (kompletter Katalog), aus = `/entry`-Feed (schnell).
- `self.scrape_skip_zero` (Default AUS) → der `on_game`-Filter verwirft nur bei `True` Builds mit `cheat_count == 0`.

(Migration in `_load_settings`: altes `scrape_entry_only=True` → `full_catalog=False` + `skip_zero=True`.) „★ Everything" nutzt fest full catalog + keine Filterung (kompletter Datensatz); „Update Recent" nutzt fest den `/entry`-Feed, respektiert aber `skip_zero`.

Die HTML-„Game releases"-Tabelle wird jetzt inkl. **„Available cheats"-Spalte** geparst (`scrape_game_details`, `add_source(..., cheat_count=...)`), sodass Tabellen-Builds ihre echte Cheat-Zahl bekommen statt 0 — auch ohne API-Treffer. Die Tabellen-Anzeige (`refresh_table`) filtert **nicht** nach `cheat_count`.

**Die Datei auf der Disk ist die maßgebliche Quelle für die Cheat-Anzahl.** `recount_cheats_from_disk` (mit `parse_cheat_names_from_content` = `[Name]`/`{Name}`-Header-Zählung) wird jetzt **automatisch** ausgeführt: (a) pro Build direkt nach dem Inline-Speichern beim Scrape (`_save_inline_content(..., db=db)` → `set_build_cheats`), und (b) als voller `only_missing=False`-Durchlauf am Ende von Scrape- und Download-Läufen (`_scrape_worker`, `_download_worker`, „★ Everything", „Fill Names", „Download game info", ibnux). `recount_cheats_from_disk` schreibt nur bei tatsächlicher Änderung (Vergleich mit `cheat_count`/`cheat_names`), bleibt also auch über die ganze DB günstig. Auch der **„Refresh"-Button** (`on_refresh` → `_refresh_worker`, Hintergrund-Thread, danach `refresh_table(force_scan=True)`) macht diesen Voll-Abgleich; interne `refresh_table`-Aufrufe (Suche/Filter) tun das **nicht** und bleiben schnell. Manuell weiterhin über *Repair ▾ → „Recount cheats from disk"*.

### Externe Datenquellen

| Quelle | Funktion | Token noetig? |
|--------|----------|--------------|
| cheatslips.com HTML | Spielliste, Slugs, Build-IDs | Nein |
| CheatSlips REST-API | Cheat-Inhalte, Spielnamen, Cover | Ja (Inhalte), Nein (Namen) |
| GBAtemp/HamletDuFromage | `switch-cheats-db` ZIP-Archiv | Nein |
| titledb `cheats.json` | Zusaetzliche Cheat-Eintraege | Nein |
| titledb `{region}.json` | Spielnamen + Cover fuer alle Regionen (~80 MB, 7-Tage-Cache) | Nein |

### Wichtige Funktionen

| Funktion | Beschreibung |
|----------|-------------|
| `fill_missing_names(db, api, regions)` | Fuellt fehlende Namen/Cover aus 7 titledb-Regionen, dann API-Fallback |
| `fill_metadata_from_titledb(db, region)` | Fuellt aus einer einzelnen Region-Datei |
| `fill_missing_versions(api, scraper, db)` | Build-Versionen: erst titledb, dann CheatSlips-HTML |
| `fill_versions_from_titledb(db)` | Schnelle Version-Zuordnung via `versions.json` |
| `refresh_titles_from_api(api, db, tids)` | Spieldaten (Name, Cover, Cheats) per API nachladen |
| `download_gbatemp_archive(output, db)` | GBAtemp-ZIP herunterladen + in DB importieren |
| `download_titledb_cheats(output, db)` | titledb `cheats.json` importieren |
| `api_download_from_db(api, db, output)` | Alle Builds aus DB via API herunterladen |
| `enrich_info_with_api(info, api)` | Scraper-Ergebnis mit API-Daten anreichern |
| `scan_downloaded_build_ids(output_dir)` | Set aller vorhandenen Build-IDs auf Disk |
| `recount_cheats_from_disk(db, output, only_missing)` | Cheat-Anzahl/-Namen aus den `.txt`-Dateien neu berechnen (`only_missing=False` = alle) |
| `export_rows_csv(rows, dest)` | DB-Zeilen als UTF-8-CSV exportieren |
| `parse_cheat_names_from_content(text)` | Cheat-Namen aus Dateiinhalt extrahieren |
| `version_int_to_str(n)` | Nintendo-Version-Int nach `"1.x.0"` |
| `download_with_quota_reset(...)` | API-Download mit autom. Quota-Reset + Browser-Fallback; markiert codelose Builds als `unavailable` und schreibt `unavailable_builds.txt` |
| `GameDatabase.mark_build_unavailable(tid, bid, reason)` | Build als „keine Codes auf cheatslips" markieren (`source = unavailable:<reason>`) |
| `GameDatabase.clear_unavailable()` | Alle `unavailable`-Markierungen zurücksetzen |
| `GameDatabase.count_unavailable()` | Anzahl markierter Builds |

### Browser-Fallback (`playwright_scrape.py`)

`BrowserSession` hält ein eingeloggtes, persistentes Chromium (`browser_profile/`).
Ablauf pro Build (`download_build` → `_download_build`):

1. **Build-ID → Cheat-Seite auflösen.** `_find_source_build_pairs()` liest die
   Spielseite aus — sowohl die featured **Cheat-Karten** als auch die
   **„Game releases"-Tabelle** (sonst werden Builds, die nur in der Tabelle
   stehen, nie gefunden). Ist ein Build keine Karte, fällt `_resolve_source_id()`
   auf die **Build-ID-URL** zurück.
2. **Landing-Page folgen.** Hat `/game/{slug}/{build_id}` kein Download-Formular,
   folgt `_download_build()` dem Link zur numerischen Cheat-Seite
   (`/game/{slug}/{nnnn}`) — ein Hop (`depth`-Guard).
3. **Download per Browser-`fetch`** (CSRF aus dem Formular).
4. **Quota-„Preview" erkennen.** Bei erreichtem Download-Limit liefert cheatslips
   ein **codeloses ZIP** (nur `[Namen]`, keine `XXXXXXXX XXXXXXXX`-Zeilen).
   `_download_build()` setzt dann via `reset_cb` (`reset_quota`) das Quota zurück
   und versucht **einmal** erneut.
5. **Endgültig keine Codes** (codeloser Upload oder „no cheat available") →
   Rückgabe des Sentinels `scraper.BUILD_UNAVAILABLE`; transiente Fehler (HTML/
   Login/Ladefehler) → `None` (werden später erneut versucht).

Wichtig: cheatslips-Cheats sind **build-spezifisch**. Build-IDs aus titledb, für
die niemand einen Cheat hochgeladen hat (häufig bei Pokémon), haben echt keine
Cheats und werden korrekt als `unavailable` markiert.

## 4. GUI-Buttons (gui.py)

| Button | Funktion |
|--------|----------|
| Scrape Cheat Slips | HTML-Scraping, optional direkt danach Download |
| Fill names | `fill_missing_names` fuer alle 7 Regionen + API-Fallback |
| Fill versions | `fill_missing_versions` (titledb + CheatSlips) |
| Fix 0-cheat | `refresh_titles_from_api` + erneuter Download |
| Recount cheats from disk | `recount_cheats_from_disk(only_missing=False)` — zählt Cheats aller Builds aus den `.txt`-Dateien neu |
| Download GBAtemp Archive | GBAtemp-ZIP + `fill_missing_names` |
| titledb Cheats | titledb `cheats.json` + `fill_missing_names` |
| Export CSV | 23-Spalten-CSV-Export |
| Add entry | Manueller Build-Eintrag |
| Clear DB | Datenbank leeren **+ alle Disk-Daten löschen** (Cheats, Cover, ZIP, Caches; titledb-Caches bleiben) |

Filter: **Missing only** (ohne Datei), **Unnamed only** (ohne Spielname).
Farben: gruen = heruntergeladen, orange = kein Spielname.
Statusleiste: `N builds . X downloaded . Y missing . Z unnamed`.

**Repair ▾**-Menue: *Clean invalid cheat files*, *Retry quota-skipped builds*,
*Retry 'unavailable' builds* (`on_clear_unavailable` → `clear_unavailable()`),
*Fix 0-cheat entries*, *Recount cheats from disk* (`on_recount_disk` →
`recount_cheats_from_disk(only_missing=False)`), *Fix ID names*,
*Sync titles folder with DB*.

**Download-Bereich:** Buttons *Download via API* (nur API), *Download Selected*,
*Download All*; Checkbox *Download via browser when API is limited*; **Browser:**-
Dropdown (`browser_choice` → `_browser_kind()` = builtin/chrome/edge/firefox,
an `BrowserSession(browser=…)` durchgereicht); Button *Reset API Limit*. Der
Browser-Download-Loop läuft in `_run_quota_reset_loop()` (eigener Worker-Thread,
da Playwright-Objekte thread-gebunden sind). Chrome/Edge laufen über Playwright-
**Channels** (nutzen die installierten Browser), Built-in/Firefox über die
mitgelieferten Playwright-Browser (Auto-Install via `_launch_auto`).

**Fenster/Tastatur** (`_install_window_controls`, `_install_edit_shortcuts`):
Neuer User startet zentriert mit `min(max(toolbar_w, 1400), Bildschirm−16) ×
min(940, Bildschirm−80)` (≈ 1400×940 auf Full HD); `minsize` = `max(toolbar_w,
1000) × 700` (auf den Bildschirm gedeckelt). Toolbar-Breite ist ~1329 px (Search
in eigener Zeile), passt damit auf 1366×768-Notebooks ohne abgeschnittene Buttons.
F11 Vollbild, Esc verlassen, Ctrl+M maximieren; Ctrl+A markiert-alles in Entry/
Text, Ctrl+C/X/V wie gewohnt; in der Tabelle Ctrl+A = alle Zeilen, Ctrl+C = kopieren.
Die GUI ist in einen vertikalen `ttk.Panedwindow` (`self.vpaned`) gegliedert:
oben Tabelle + Database-Bar (`self._top_container`), unten das Log-Panel — der
Sash dazwischen macht das Log-Fenster frei in der Höhe verstellbar (eigene
Scrollleiste). Die Sash-Position wird derzeit **nicht** persistiert.

## 5. Aktueller Stand (Juni 2026)

### Funktioniert vollstaendig

- API-basierter Download (kein Browser, kein reCAPTCHA)
- HTML-Scraping mit parallelem `ThreadPoolExecutor`
- GBAtemp-Archiv-Import + automatische Namensbefuellung (alle Regionen)
- titledb-Import (Cheats + Metadaten)
- Multi-Region-Namensbefuellung: US -> EU -> GB -> AU -> JP -> KR -> ZH
- API-Credentials werden an alle Worker-Threads weitergereicht
- Tabellenvisualisierung: gruen (heruntergeladen), orange (kein Name)
- `Unnamed only`-Filter in der GUI
- 0-Cheat-Builds bleiben sichtbar (Scrape-Filter standardmäßig aus, 0-Cheat-Schutz im Upsert)
- Cheat-Anzahl aus den Disk-Dateien neu berechenbar (`Recount cheats from disk`)
- `Clear DB` leert DB **und** Disk-Daten (Cheats/Cover/ZIP/Caches)
- vergrößerbares Log-Fenster (vertikaler Splitter)
- `check_missing.py` als DB-basierter Diagnosebericht
- Unit-Tests: `extract_version`, `normalize_slug`, `GameDatabase`, `parse_cheat_names_from_content`, `version_int_to_str`, `fill_game_meta`, `update_game_fields`, `title_ids_missing_meta/version`

### Bekannte Einschraenkungen

- GBAtemp-only-Spiele die weder in titledb noch auf CheatSlips sind, bekommen keinen Namen (sehr selten)
- `fill_missing_names` laedt 7 x ~80 MB; nach dem ersten Lauf gecacht (7 Tage)
- `refresh_titles_from_api` fuellt nur Namen, wenn das Spiel auf CheatSlips Cheats hat

## 6. CLI-Optionen

```powershell
# Metadaten scrapen
python scraper.py metadata --output ./cheatsdownload

# Cheats herunterladen (API-Token erforderlich)
python scraper.py download --db ./cheats.db --email "x@y.de" --password "pw" --output ./cheatsdownload

# Nur ein Spiel
python scraper.py download --db ./cheats.db --token "TOKEN" --title-id 010038B015560000

# ZIP packen
python scraper.py package --output ./cheatsdownload

# DB-Diagnose
python check_missing.py --db ./cheats.db --output ./cheatsdownload --show-unnamed 50
```

## 7. Offene TODOs

1. **Download-Fortschritt in DB schreiben** — `downloaded`-Flag in `builds`-Tabelle statt nur Disk-Abgleich
2. **Parallele Region-Downloads** — mehrere titledb-Dateien gleichzeitig herunterladen
3. **`StateManager`-Tests** — noch nicht in `test_scraper.py` abgedeckt
4. **Kombinierter Fortschrittsbalken** ueber alle Regionen in `fill_missing_names`
5. **Globale BID-Deduplizierung** — identische Build-IDs ueber mehrere Title-IDs erkennen

## 8. Wichtige Dateien

| Datei | Inhalt |
|-------|--------|
| `scraper.py` | Gesamte Backend-Logik (API, DB, Quota-Reset-Loop, `BUILD_UNAVAILABLE`) |
| `playwright_scrape.py` | Browser-Download: `BrowserSession` (Browser-Auswahl builtin/chrome/edge/firefox), Build-ID-Auflösung, Quota-Reset, Download, Browser-Auto-Install (`install_browsers`/`_launch_auto`) |
| `browser_scrape.py` | `extract_cheat_text_from_html` (HTML-Cheat-Extraktion); `CookieCheatScraper` derzeit ungenutzt |
| `npshop_scraper.py` | Eigenständiger Browser-Scraper für npshop.org (OAuth-Login); **noch nicht in der GUI verdrahtet** |
| `gui.py` | Tkinter-Frontend |
| `test_scraper.py` | Unit-Tests (stdlib only): `python -m unittest test_scraper` |
| `check_missing.py` | DB-Diagnosebericht (fehlende Namen, Versionen, Quellen) |
| `_api.yaml` | OpenAPI-Spec der CheatSlips-API |
| `requirements.txt` | Python-Abhaengigkeiten |
| `README.md` | Nutzer-Dokumentation |


## 9. Screenshots fuer GitHub (README & Releases)

Die Bilder liegen unter `screenshots/` und werden von README **und** der
v1.2-Release-Beschreibung referenziert (Raw-URLs auf `main`). Beim Ersetzen
IMMER denselben Dateinamen behalten (`windows-tool.png`, `switch-app.png`),
dann bleiben alle Links gueltig.

**Konventionen (Fehler, die schon passiert sind - nicht wiederholen!):**

1. **Immer englische UI** - der gesamte GitHub-Auftritt ist englisch.
   Windows-Tool: Sprache "English"; Switch-App: vor dem Start `EN` in die
   lang.txt der virtuellen SD schreiben
   (`%APPDATA%\eden\sdmc\switch\SwitchCheatsDownloader\lang.txt`).
2. **Keine privaten/lokalen Pfade im Bild.** Das Windows-Tool zeigt Output-
   und DB-Pfad an! Vorgehen: portable Version nach `C:\SwitchCheatsScraper`
   kopieren, dort `settings.json` + `session.json` **loeschen** (sonst werden
   die alten Pfade aus den kopierten Settings angezeigt!), eine gefuellte
   `cheats.db` daneben legen, von dort starten -> Pfade zeigen neutral
   `C:\SwitchCheatsScraper\...`. Nach dem Screenshot Kopie wieder entfernen.
3. **Gefuellte Datenbank zeigen** (leere Liste wirkt kaputt) und leere
   Login-Felder kontrollieren (kein Token/keine E-Mail sichtbar).
4. **Switch-Screenshot:** vorher ALLE laufenden Eden-Instanzen beenden
   (sonst erwischt man eine alte Instanz mit falschem Stand/Sprache);
   Eden startet gern minimiert -> Fenster erst wiederherstellen; dann das
   Fenster auf den reinen Render-Bereich zuschneiden
   (Fenster-relativ x=8, y=55, 1280x720). Details zur Eden-Automatisierung:
   `SwitchCheatsNRO/CONTINUATION.md` Abschnitt 9.
5. Windows-Screenshot auf ~1728 px Breite herunterskalieren (Dateigroesse).

6. **Fenstermodus statt maximiert** fuer Windows-Screenshots: Der Nutzer hat
   einen Widescreen-Monitor - maximierte Aufnahmen wirken extrem in die
   Breite gezogen. Fenstergroesse ~1540x1250 (settings.json:
   "window_state": "normal" + passende "geometry" setzen).
