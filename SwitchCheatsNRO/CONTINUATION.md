# SwitchCheatsNRO – Continuation Guide (Handoff für die nächste KI)

Stand: Juli 2026. Dieses Dokument beschreibt die **Nintendo-Switch-Homebrew-App**
(`.nro`) im Unterordner `SwitchCheatsNRO/` so, dass eine andere KI (oder ein
Entwickler) ohne Vorwissen weiterarbeiten kann. Es ergänzt die nutzerorientierte
`README.md` um die interne Architektur, Fallstricke und offene Punkte.

> **Abgrenzung:** Das übergeordnete `CONTINUATION.md` (eine Ebene höher) betrifft
> ausschließlich das **Python-Desktop-Tool** (CheatSlips-Scraper). Diese Datei
> hier betrifft ausschließlich die **C++/SDL2-NRO-App**. Beide Projekte teilen
> sich nur die Datenquelle (die `switch-cheats.zip` aus dem GitHub-`data`-Release),
> **keinen Code**.

---

## 1. Zweck der App

Eigenständige `.nro`-Homebrew, die auf einer gemoddeten Switch:

1. die aktuelle `switch-cheats.zip` aus dem GitHub-`data`-Release herunterlädt und
2. **direkt auf der SD-Karte** ins Atmosphère-Layout entpackt
   (`atmosphere/contents/<TitleID>/cheats/<BuildID>.txt`).

Zusätzlich: Update-Erkennung (via `updated_at`), Mehrsprachigkeit (6 Sprachen) und
App-Self-Update (die `.nro` ersetzt sich selbst).

---

## 2. Dateiübersicht (`source/`)

| Datei | Verantwortung | Wichtige Symbole |
|---|---|---|
| `main.cpp` | SDL2-Hauptprogramm: Fenster/Renderer (VSync), gesamtes UI-Zeichnen (Sidebar/Panel/Footer/Abbrechen-Button), Eingaben (Joystick-Buttons + linker Stick + Touch + Maus), State-Machine, Steuerung des Hintergrund-Threads, Online-Status-Poll | `main()`, `Action`-Enum, `run*Worker()`, `start*()`, `activateItem`-Lambda, `menuLabel`-Lambda, `drawText/drawProgressBar`, `g_online` |
| `updater.hpp/.cpp` | GitHub-API (libcurl), Datei-Download mit Fortschritt/Abbruch/Stall-Erkennung, lokaler Update-Zeitstempel, Internet-Check (nifm), **Self-Update** (Version aus Release-Titel, NRO-Magic-Check) | `fetchLatestReleaseInfo()`, `downloadFile()`, `read/writeLocalUpdatedAt()`, `isInternetAvailable()`, `checkAppUpdate()`, `getSelfNroPath()`, `installSelfUpdate()`, static `httpGetString()`, `applyCommonCurlOpts()`, `hasNroMagic()` |
| `version_util.hpp` | Reine Versions-String-Logik (kein Switch-Code, host-testbar) | `versionutil::normalizeVersion()`, `versionutil::isNewerVersion()` |
| `zip_extract.hpp/.cpp` | Entpacken der ZIP direkt auf SD (minizip `unzip.h`), legt Zielverzeichnisse an, prüft Schreibfehler und wehrt Zip-Slip ab | `zipextract::extractZipToPath()`, `zipextract::isSafeEntryName()` (inline im Header, host-testbar) |
| `json_util.hpp` | Minimaler, gezielter JSON-Feldextraktor (kein voller Parser – Schema ist fix) | `jsonutil::extractJsonString()`, `jsonutil::findAssetObject()` |
| `i18n.hpp/.cpp` | Übersetzungstabelle (6 Sprachen, inkl. `err.*`-Fehlertexte für updater/zip_extract), Systemsprach-Erkennung, Persistenz, Lookup | `i18n::init/tr/getLang/setLang/nextLang/prevLang/langCode`, `Lang`-Enum, `kTable[]`, atomic `g_lang` |
| `config.hpp` | Alle zentralen Konstanten; `kAppVersion`/`kUserAgent` kommen aus dem Makefile-Makro `APP_VERSION` | Namespace `cfg::` |
| `../tests/test_logic.cpp` | Host-Tests für json_util/version_util/isSafeEntryName (49 Asserts); wird NICHT in die NRO gebaut (Makefile-Wildcard erfasst nur `source/`) | `g++ -std=gnu++17 -I source -o test tests/test_logic.cpp && ./test` |
| `../icon.jpg` | App-Icon (256×256 JPEG, kein Alpha) für hbmenu; aus `app_icon.png` der Windows-Software erzeugt (System.Drawing: PNG auf Navy (14,16,24) flatten, Qualität 92). Das Makefile setzt `APP_ICON`/`--icon` automatisch, wenn die Datei existiert | elf2nro `--icon` |
| `../romfs/cacert.pem` | Mozilla-CA-Bundle für TLS (Switch hat keinen System-CA-Store für Homebrew) | in RomFS eingebettet, via `CURLOPT_CAINFO = "romfs:/cacert.pem"` |

**Wichtig:** `updater.cpp` und `zip_extract.cpp` benutzen `i18n::tr()` für alle
nutzerseitigen Fehlermeldungen (Keys `err.*`) — keine hartkodierten deutschen
Strings mehr. Alle curl-Transfers laufen über `applyCommonCurlOpts()`
(TLS-Verifikation, Redirects nur HTTPS via `CURLOPT_REDIR_PROTOCOLS_STR`).

**Font:** wird nicht mitgeliefert. Zur Laufzeit über `plGetSharedFontByType(PlSharedFontType_Standard)`
geladen und per `TTF_OpenFontRW` an SDL2_ttf gereicht → volle Umlaut- und
Japanisch-Unterstützung ohne eigene Font-Datei.

---

## 3. Nebenläufigkeit & State-Machine (`main.cpp`)

Der UI-Thread rendert bei ~60 fps; jede länger laufende Aktion (Netzwerk, Entpacken)
läuft in **genau einem** Hintergrund-`std::thread` (`g_worker`).

```
enum class Action { None, Checking, Installing, AppChecking, AppInstalling };
static std::atomic<Action> g_action{Action::None};   // "busy"-Zustand = != None
```

- **Nur eine Aktion gleichzeitig.** Alle `start*()`-Funktionen brechen sofort ab,
  wenn `g_action != None`. Menü-Navigation/Aktivierung ist bei `busy` gesperrt
  (außer B = Abbrechen und L/R = Sprache, die immer erlaubt sind).
- **Thread-Lebenszyklus:** `start*()` ruft `joinWorkerIfDone()` (joint den alten
  Thread, wenn fertig), setzt `g_action` und startet den neuen Worker. Jeder
  Worker setzt am Ende `g_action = Action::None`. Beim Beenden der Hauptschleife
  wird `g_cancelRequested` gesetzt und `g_worker.join()` aufgerufen.
- **Abbruch:** `std::atomic<bool> g_cancelRequested`. Die Fortschritts-Callbacks
  von `downloadFile()`/`extractZipToPath()` geben `!g_cancelRequested` zurück;
  `false` bricht die Operation ab. Auslöser: B-Taste ODER Tap auf den
  Abbrechen-Button (wird nur bei `busy` gerendert und hit-getestet).
- **Fortschritt:** `g_bytesDone/g_bytesTotal` (Download) und `g_zipIndex/g_zipTotal`
  (Entpacken) sind `std::atomic` und werden im Render-Loop gelesen. Anzeige-
  Reihenfolge: erst Entpack-Balken (`zt > 0`), dann Download-Balken
  (`total > 0`), dann nur-Bytes (Server ohne Content-Length), sonst Statuszeile.
- **Online-Status:** `std::atomic<bool> g_online` — der UI-Thread pollt
  `isInternetAvailable()` alle 5 s, aber NUR wenn `g_action == None` (damit
  nifm nie von zwei Threads gleichzeitig benutzt wird); die Worker setzen
  `g_online` bei ihrem eigenen Internet-Check zu Beginn.

### Geteilter Zustand hinter `g_dataMutex`

Zwei getrennte Ergebnis-Sätze, damit Cheats-Update und App-Update sich nicht
gegenseitig überschreiben:

- **Cheats-Update:** `g_statusLine`, `g_resultLine`, `g_resultSuccess`,
  `g_haveResult`, `g_remoteUpdatedAt`, `g_localUpdatedAt`, `g_updateAvailable`,
  `g_haveRemoteInfo`.
- **App-Self-Update:** `g_appResultLine`, `g_appResultSuccess`, `g_appHaveResult`,
  `g_appChecked`, `g_appUpdateAvailable`, `g_appJustInstalled`,
  `g_appRemoteVersion`, `g_appDownloadUrl`. `g_selfNroPath` wird **einmal** beim
  Start gesetzt (vor Thread-Start) und danach nur gelesen → kein Mutex nötig.

Der Render-Loop kopiert diese Felder **einmal pro Frame** unter dem Mutex in
lokale Variablen und zeichnet dann außerhalb des Locks.

---

## 4. Menü (4 Einträge)

`kMenuCount = 4`. Labels kommen pro Frame aus `menuLabel(i)` → `i18n::tr(...)`,
damit ein Sprachwechsel sofort greift. Der frühere separate Menüpunkt
"Nach Updates suchen" ist in den Install-Bereich **integriert**: beim
App-Start läuft einmalig `startCheck()` (`autoCheckStarted`-Flag in `main()`,
reiner Check ohne Download), und das Install-Panel zeigt den Statusblock
(lokal / neueste Version / verfügbar-oder-aktuell). Indizes:

| idx | Key | Aktion in `activateItem` |
|---|---|---|
| 0 | `menu.install` | `startInstall()` (Panel zeigt zusätzlich den Update-Status) |
| 1 | `menu.info` | – (nur Anzeige, `hasAction(1) == false`) |
| 2 | `menu.appupdate` | 1. A-Druck → `startAppCheck()`; 2. A-Druck (wenn `g_appChecked && g_appUpdateAvailable`) → `startAppInstall()` |
| 3 | `menu.exit` | `exitRequested = true` |

**Touch/Maus-Verhalten (auf Nutzerwunsch geändert):** Ein Tap auf einen
Sidebar-Eintrag **wählt nur aus**, startet nichts. Aktionen laufen über die
**Panel-Buttons** (Rect `panelBtnX/Y/W/H`, fest über der Fußleiste,
gezeichnet über das `drawPanelButton`-Lambda): während einer Aktion
"B Abbrechen"; im Leerlauf je nach Panel:

- **Install-Panel (idx 0):** "A Starten" (Akzent) + "Y Prüfen"
  (`panelBtn2X`) für den manuellen Update-Check — auch per **`JOY_Y`**.
- **Info-Panel (idx 1):** **Sprachauswahl-Leiste** — alle 6 Sprachen als
  direkt antippbare Buttons (`langBtnIndex`-Lambda, 120 px breit, Stride
  136, aktuelle Sprache mit Akzent-Rahmen hervorgehoben) →
  `i18n::setLang()`. L/R funktioniert weiterhin parallel.
- **App-Update/Exit (idx 2/3):** "A Starten" bzw. "A Beenden".

`runCheckWorker` setzt bei Erfolg KEINEN Result-Text mehr (der Status steht
im Statusblock inkl. **Download-Größe** aus dem API-`size`-Feld), sondern
räumt nur eine alte Fehlermeldung weg; offline erscheint `result.noInternet`
in Rot. Am Ende läuft ein **stiller App-Update-Check** (`checkAppUpdate()`),
der nur `g_appUpdateAvailable`/Version/URL setzt (NICHT `g_appChecked`) —
das Render zeichnet dann ein **Akzent-Badge** am "App-Update"-Menüpunkt;
der explizite zweistufige Ablauf bleibt unverändert.

**Eingaben** (SDL-Joystick-Button-Codes, oben in `main.cpp` als `#define`):
`JOY_A=0, JOY_B=1, JOY_X=2, JOY_Y=3, JOY_L=6, JOY_R=7, JOY_PLUS=10, JOY_MINUS=11,
JOY_LEFT=12, JOY_UP=13, JOY_RIGHT=14, JOY_DOWN=15`. Zusätzlich:

- **Linker Stick** (`SDL_JOYAXISMOTION`, Achse 1 = Y): diskrete Navigation mit
  Totzone 16000; löst nur beim Richtungswechsel aus (`stickDir`-Variable,
  kein Auto-Repeat).
- **Touch** (`SDL_FINGERDOWN`) und **Maus** (`SDL_MOUSEBUTTONDOWN`) auf die
  Sidebar-Trefferzonen; bei `busy` stattdessen Hit-Test auf den
  Abbrechen-Button (`inCancelBtn`-Lambda, Rect fest über der Fußleiste).

---

## 5. Self-Update-Ablauf (`updater.cpp` + `main.cpp`)

1. `checkAppUpdate()` fragt `cfg::kNroApiUrl` (Tag `nro`) ab und liest die
   Version aus dem **Release-TITEL** (`name`-Feld, z. B. `v1.2.0`), NICHT aus
   `tag_name`. **Grund:** Das Release wird über den festen Tag `nro`
   abgefragt, sein `tag_name` ist daher immer der String `"nro"` und kann
   keine Version tragen (das war in v1.0.0 ein Bug — der Vergleich
   `isNewerVersion("nro", …)` konnte nie anschlagen). Das `name`-Feld wird
   nur im Response-Teil VOR dem `"assets"`-Array gesucht, damit kein
   Asset-`name` matcht. Parsing/Vergleich: `versionutil::normalizeVersion()`
   ("v1.2.0 Hotfix" → "1.2.0") + `versionutil::isNewerVersion()` (numerischer
   Komponentenvergleich). Kein parsebarer Titel → Fehler
   `err.noVersionInTitle`. **HTTP 404 = `ok=true, available=false`** (noch
   kein Release → kein Fehler); 403/429 → `err.rateLimit`.
2. Bei verfügbarem Update lädt `runAppInstallWorker()` das Asset nach
   `cfg::kTmpNroPath` und ruft `installSelfUpdate(tmp, g_selfNroPath, err)`:
   Plausibilitätscheck (≥ 1 KB **und** NRO-Magic `"NRO0"` bei Offset 0x10 via
   `hasNroMagic()`), dann `rename()`; schlägt das fehl (auf der Switch
   scheitert `rename()` auf ein existierendes Ziel), `remove(self)` +
   erneutes `rename()`. Erst danach Copy-Fallback mit vollständiger
   `fwrite`/`fclose`-Prüfung — bei Fehler wird das halb geschriebene Ziel
   entfernt und die verifizierte `.nro` bleibt unter `kTmpNroPath` liegen
   (manuelle Rettung; wird beim nächsten erfolgreichen App-Start aufgeräumt).
3. `g_selfNroPath` kommt aus `getSelfNroPath(argc, argv)`: bevorzugt `argv[0]`
   (vom hbloader), normalisiert auf `sdmc:`-Präfix, sonst `cfg::kSelfNroFallbackPath`.
4. Danach `g_appJustInstalled = true` → UI zeigt `appupdate.restartHint`
   (manueller Neustart nötig; kein Live-Relaunch implementiert).

Das Überschreiben der laufenden `.nro` ist möglich, weil der hbloader sie beim
Start komplett in den RAM lädt und die Datei nicht offen hält.

**Maintainer-Ablauf für ein Release:** `APP_VERSION` im Makefile erhöhen →
bauen → Release mit Tag `nro`, **Titel** = `vX.Y.Z`, Asset
`SwitchCheatsDownloader.nro` (Details im README).

---

## 6. i18n-System (`i18n.cpp`) — WICHTIGE FALLSTRICKE

- `Lang`-Reihenfolge: **`DE=0, EN, ES, FR, IT, JA`**. Die 6 Strings in jeder
  `kTable`-Zeile müssen **exakt in dieser Reihenfolge** stehen.
- `g_lang` ist ein **`std::atomic<int>`**: `tr()` wird auch aus den
  Hintergrund-Workern gerufen (updater/zip_extract übersetzen ihre Fehler
  selbst), während der UI-Thread per L/R umschalten kann.
- `init()`: erkennt Systemsprache (`detectSystemLang()` via `set`-Service), lädt
  danach eine evtl. gespeicherte Wahl aus `cfg::kLangFile`. **Format seit
  v1.1.0: Sprachkürzel als Text** ("DE", "EN", …); das alte v1.0.0-Format
  (roher 4-Byte-`int`) wird beim Lesen weiterhin erkannt (Fallback in
  `init()`), geschrieben wird nur noch Text. Muss in `main()` **nach**
  `plInitialize` aufgerufen werden (ist es).
- `tr(key)` gibt bei fehlendem Key den **Key selbst** zurück (Debug-Hilfe).
- Neuen String hinzufügen: eine Zeile `{"my.key", {"DE","EN","ES","FR","IT","JA"}}`
  in `kTable` ergänzen. `kTableSize` wird automatisch berechnet.
- **Diakritika:** Die ES-Spalte verwendet echtes Spanisch mit Akzenten
  (á/é/í/ó/ú/ñ/¡ als **rohe UTF-8-Zeichen** direkt im Quelltext — GCC reicht
  sie byteweise durch, der Systemfont rendert sie; im Eden-Emulator
  verifiziert). Der Hex-Escape-Fallstrick unten betrifft NUR `\x`-Escapes,
  nicht rohe UTF-8-Zeichen. DE/FR/IT nutzen noch ASCII-Ersatzschreibweisen
  ("verfuegbar", "Telecharger") — bei Bedarf analog umstellbar.
- **Fehlermeldungs-Konvention:** Keys `err.*`; Prefix-Keys enden mit `": "`
  und der Aufrufer hängt dynamische Teile an (Pfad, curl-Fehlertext,
  HTTP-Code). Keine hartkodierten nutzerseitigen Strings in
  updater.cpp/zip_extract.cpp!

### ⚠️ Der Hex-Escape-Fallstrick (schon zweimal aufgetreten!)

Japanische Strings sind als UTF-8-Byte-Escapes (`\xe3\x83\xbc...`) kodiert.
In C/C++ ist `\x` **gierig** und frisst **beliebig viele** folgende Hex-Ziffern
(nicht nur 2!). Steht direkt hinter einem `\xNN` ein ASCII-Zeichen, das eine
gültige Hex-Ziffer ist (`0-9`, `a-f`, **`A-F`**), verschmilzt es mit dem Escape →
`warning: hex escape sequence out of range` und falsches Byte.

**Lösung:** String-Literal-Konkatenation zum Trennen nutzen:

```cpp
// FALSCH: "...\xe5\xba\xa6A\xe3\x83\x9c..."   (A wird Teil von \xa6)
// RICHTIG:
"...\xe5\xba\xa6" "A" "\xe3\x83\x9c..."
```

Das betraf `install.desc2` (…`\xae` + `Atmosphere`) und `appupdate.pressAgain`
(…`\xa6` + `A`). Beim Einfügen neuer JA-Strings mit eingebetteten lateinischen
Buchstaben oder Ziffern **immer** so trennen. Nach jeder i18n-Änderung neu bauen
und die Compiler-Warnungen prüfen (Ziel: **0 Warnungen**).

---

## 7. Konfiguration (`config.hpp`, Namespace `cfg::`)

| Konstante | Bedeutung |
|---|---|
| `kRepoOwner/kRepoName/kReleaseTag/kAssetName` | GitHub-Quelle der `switch-cheats.zip` (Tag `data`) |
| `kApiUrl` | REST-Endpunkt der `data`-Release |
| `kAppDir/kStateFile/kTmpZipPath/kSdRoot/kLangFile` | SD-Pfade (`sdmc:/...`) |
| `kTmpZipMetaPath` | Merkt sich das `updated_at` der `.part`-Teildatei — Grundlage für den **Download-Resume** (nur fortsetzen, wenn der Release-Stand unverändert ist; sonst frisch laden). Teildatei+Meta werden immer als Paar gehalten (Konsistenz-Check beim App-Start) |
| `kAppVersion` | **Eigene App-Version** – Vergleichsbasis fürs Self-Update. Kommt aus dem Makefile-Makro `APP_VERSION` (**dort** erhöhen, nicht in config.hpp — der `#ifndef`-Fallback in config.hpp greift nur bei Builds ohne Makefile) |
| `kUserAgent` | HTTP-User-Agent, per String-Literal-Konkatenation aus `APP_VERSION` abgeleitet |
| `kNroReleaseTag/kNroAssetName/kNroApiUrl` | Self-Update-Quelle (Tag `nro`; Version steht im Release-**Titel**) |
| `kSelfNroFallbackPath/kTmpNroPath` | Self-Update-Pfade |
| `kScreenW/kScreenH` | logische Renderauflösung 1280×720 (Switch skaliert automatisch) |

---

## 8. Build

Voraussetzungen: devkitPro mit `switch-dev switch-sdl2 switch-sdl2_ttf switch-curl
switch-mbedtls switch-zlib` (minizip via `libminizip`). Umgebungsvariable
`DEVKITPRO` gesetzt.

### ⚠️ Pfad ohne Leerzeichen zwingend erforderlich

Das devkitPro-Makefile bricht bei Leerzeichen im Pfad (`C:\Coding\Switch Cheats Scraper\...`).
Vor dem Bauen ein Laufwerk ohne Leerzeichen mappen (nicht-destruktiv):

```powershell
subst X: "C:\Coding\Switch Cheats Scraper"
```

Dann in der devkitPro-MSYS2-Bash (`c:\devkitPro\msys2\usr\bin\bash.exe`):

```bash
cd /x/SwitchCheatsNRO
make            # -> SwitchCheatsDownloader.nro
make clean      # räumt build/, .elf, .nacp
```

Danach ggf. `subst X: /D` zum Aufheben. Das Makefile erfasst neue `source/*.cpp`
automatisch (Wildcard) – kein manuelles Eintragen nötig. Die Versionsnummer
(`APP_VERSION`) wird im Makefile gepflegt und als `-DAPP_VERSION="..."`
(`DEFINES`) in den Code durchgereicht.

**Kompletter One-Liner** (Mapping + Clean-Build + Log), wie zuletzt verwendet:

```powershell
subst X: "C:\Coding\Switch Cheats Scraper" ; c:\devkitPro\msys2\usr\bin\bash.exe -lc "cd /x/SwitchCheatsNRO && make 2>&1 | tail -40"
```

### Host-Tests (ohne Switch/devkitPro-Toolchain)

Die pure Logik (JSON-Extraktor, Versionsvergleich, Zip-Slip-Schutz) ist in
`tests/test_logic.cpp` mit 49 Asserts abgedeckt und läuft mit jedem normalen
g++ (z. B. dem aus der devkitPro-MSYS2):

```powershell
c:\devkitPro\msys2\usr\bin\g++.exe -std=gnu++17 -Wall -Wextra -I source -o test_logic.exe tests\test_logic.cpp
.\test_logic.exe   # erwartet: "49 passed, 0 failed"
```

Nach Änderungen an `json_util.hpp`, `version_util.hpp` oder
`isSafeEntryName()` immer mitlaufen lassen (und bei neuen Edge-Cases
erweitern).

---

## 9. Emulator-Tests (Eden) — Erkenntnisse & Vorgehen

Die App wurde im **Eden v0.2.1** (yuzu-Fork, `C:\Emulatoren\...`) end-to-end
getestet: Boot, UI-Rendering (60 fps/VSync), Menü-Navigation, Sprachwechsel
per L/R, **echter GitHub-Update-Check**, kompletter Download + Entpacken von
5298 Dateien auf die virtuelle SD (`%APPDATA%\eden\sdmc\`), `last_update.txt`
und `lang.txt` korrekt geschrieben.

**Kritische Erkenntnisse (nicht wieder einbauen!):**

1. **`remove()` auf nicht existierende Pfade crasht Eden** (Access Violation
   im DeleteFile-Handler des Emulators; auf Hardware harmlos). Deshalb gibt
   es `updater::removeIfExists()` (stat vor remove) — überall dort verwenden,
   wo das Ziel fehlen kann (Startup-Cleanup, `remove(selfPath)` vor rename).
   `fopen()` auf fehlende Dateien ist dagegen unkritisch.
2. **Das devkitPro-curl nutzt den nativen `ssl:`-Service der Switch**
   (`Curl_ssl_libnx` in der Map, KEINE mbedtls-SSL-Symbole) — mbedTLS wird
   nur gelinkt, aber nicht für TLS benutzt. `curl_global_init` ruft daher
   `sslInitialize` auf. Die Initialisierung passiert lazy
   (`updater::ensureCurlGlobalInit()`, aus den `start*()`-Funktionen im
   UI-Thread) statt beim App-Boot.
3. **`eden-cli.exe` hat eine separate Config ohne Netzwerk-Interface**
   ("BSD: Network isn't initialized") — für Tests immer die GUI verwenden:
   `eden.exe -g <pfad>.nro`. Log: `%APPDATA%\eden\log\eden_log.txt`
   (asynchron — die letzte Zeile ist NICHT zwingend der Crash-Ort!).
4. **Tastatur-Mapping** (aus `%APPDATA%\eden\config\qt-config.ini`):
   Pfeiltasten = Steuerkreuz, `C` = A, `X` = B, `V` = X, `Z` = Y,
   `Q`/`E` = L/R, `M` = +, `N` = −, WASD = linker Stick.
5. Durch die Emulator-Tests gefundener echter Bug (gefixt): `persist()` in
   i18n.cpp legte den App-Ordner nicht an → Sprachwahl ging vor dem ersten
   Download verloren.
6. **Maus-Klicks kommen im Guest NUR als `SDL_FINGERDOWN` an** (keine
   SDL-Maus-Events!) und die Touch-Koordinaten sind gegenüber der
   Host-Klickposition **deutlich versetzt** (per Guest-seitigem Input-Log
   verifiziert: Klick auf "Info" lieferte finger-y ≈ 0.518 → traf
   "App-Update"). Klick-basierte UI-Tests haben daher unscharfe Trefferzonen
   — präzise Eingaben immer per Tastatur. Der erste Klick nach Fokuswechsel
   wird zudem oft von Qt verschluckt (Fenster-Aktivierung).
7. Die Stick-Navigation hat einen Neutral-Guard (`stickSeenNeutral` in
   `main()`): navigiert erst, nachdem die Achse einmal in der Totzone
   gelesen wurde — filtert Init-/Resync-Bursts (Emulator-Fokuswechsel,
   Suspend/Resume) heraus.

---

## 10. Aktueller Stand (Juli 2026, v1.2.0)

### Neu in v1.2.0 (alle Punkte im Eden-Emulator verifiziert)
- **Echte Diakritika in ALLEN Sprachen** ("verfügbar", "Télécharger",
  "È disponibile", zuvor schon ES) — rohe UTF-8-Zeichen im Quelltext.
- **Download-Größe** im Statusblock ("Neueste Version: … (4.3 MB)") aus dem
  `size`-Feld der GitHub-API (`jsonutil::extractJsonNumber`).
- Abschlussmeldung zeigt die Anzahl der installierten Dateien (= Build-IDs).
  (Eine zusätzliche Spiele-Anzahl war kurz drin und wurde auf Nutzerwunsch
  wieder entfernt.)
- **Stiller App-Update-Check** beim Start-Check + Akzent-Badge am
  "App-Update"-Menüpunkt.
- **Download-Resume**: Teildatei + `.meta` (updated_at) bleiben bei
  Abbruch/Netzfehler liegen; Fortsetzung per `CURLOPT_RESUME_FROM_LARGE`
  ("ab"-Append, Fortschritts-Offset im Trampoline, 206 erwartet — liefert
  der Server trotz Range 200, wird die Datei verworfen und frisch geladen).
  Verifiziert mit einer echten 2-MB-Teildatei: byte-genaue Fortsetzung,
  ZIP fehlerfrei entpackt. HTTP-Fehler entfernen die Teildatei immer
  (Fehlerseiten-Bytes); `keepPartial` gilt nur bei 200/206-Transporten.
- **Sprachauswahl-Leiste** im Info-Panel (alle 6 Sprachen direkt antippbar).

---

## Alt: Stand v1.1.0

### Fertig & baut sauber (0 Warnungen), Host-Tests grün (49/49)
- **Kombiniertes Menü (4 Einträge)**: Update-Check ist in den Install-Bereich
  integriert, läuft beim Start automatisch (nur Abfrage); Download startet
  ausschließlich per A/Starten-Button (Nutzerwunsch: kein Auto-Start).
- Download/Installation der `switch-cheats.zip` mit Fortschritt —
  **im Eden-Emulator end-to-end verifiziert** (siehe Abschnitt 9).
- Dunkles UI (Sidebar + Panel + Footer), Joystick-Buttons/linker Stick/Touch/Maus,
  VSync; Touch wählt nur aus, Panel-Button = Starten/Abbrechen.
- **Mehrsprachigkeit** EN/DE/ES/FR/IT/JA inkl. aller Fehlermeldungen (`err.*`),
  Systemsprach-Erkennung, L/R-Umschaltung, Persistenz in `lang.txt`
  (Textkürzel; liest auch das alte Binärformat).
- **App-Self-Update** (zweistufig: prüfen → installieren): Version aus dem
  Release-Titel (Fix des "tag_name ist immer nro"-Bugs aus v1.0.0),
  NRO-Magic-Check, remove+rename statt nicht-atomarem Copy, saubere
  404-Behandlung, Rate-Limit-Meldung.
- **Härtung:** fwrite/fclose-Prüfung beim Entpacken und Self-Update (volle
  SD-Karte wird erkannt, halb geschriebene Dateien werden entfernt),
  Zip-Slip-Schutz, Download-Stall-Erkennung (LOW_SPEED 1 B/s / 30 s),
  Redirects nur HTTPS, Temp-`.part`-Cleanup beim Start und im Fehlerpfad,
  Online-Status-Refresh alle 5 s, Null-Font-Guards (kein Crash, falls der
  Systemfont nicht lädt).

### Im Eden-Emulator verifiziert (Guest-seitig identisch zur Hardware)
- Boot, UI-Rendering, Systemfont, 60 fps mit VSync.
- Steuerkreuz-Navigation, **`JOY_R=7`** (Sprachwechsel per `E`/R bestätigt),
  Maus-Klick-Auswahl in der Sidebar, Start-Button, **manueller
  Y-Check-Button** (verifiziert: nach Löschen von `last_update.txt` sprang
  die Anzeige per Klick auf "Update verfügbar" um), **Offline-Meldung**
  (verifiziert mit Eden `network_interface=None`: rote
  "No internet connection available."-Zeile + Offline-Fußzeile).
- Kompletter Netzwerkpfad: nifm-Onlinecheck, GitHub-API über den
  `ssl:`-Service, JSON-Parsing, Download, Entpacken (5298 Dateien, korrektes
  Atmosphère-Layout), `last_update.txt`, Re-Check → "bereits aktuell".
- Sprachpersistenz (`lang.txt` = Textkürzel) nach dem mkdir-Fix.
- **Japanische Glyphen** rendern korrekt mit dem Systemfont (komplettes
  JA-UI im Emulator geprüft), ebenso die **spanischen Akzente** (á/é/í/ó/ú/¡).
- Offline-Verhalten, manueller Y-Check, App-Icon im NRO eingebettet
  (JFIF-Marker verifiziert).

### Nicht auf echter Hardware getestet (VERIFIZIEREN!)
- **`JOY_L=6`** (nur R wurde im Emulator ausgelöst) und der **linke Stick**
  (`SDL_JOYAXISMOTION`, Achse 1) mit echten Joycons.
- **Selbst-Überschreiben der laufenden `.nro`** via `installSelfUpdate()`
  (inkl. Verhalten von `rename()` auf existierendes Ziel).
- **`argv[0]`-Pfadauflösung** durch den hbloader (sonst greift der Fallback-Pfad).
- **Touch-Treffer** von Sidebar und Start/Prüfen/Abbrechen-Button auf dem
  echten Touchscreen (Edens Maus→Touch-Mapping ist koordinatenversetzt und
  taugt nicht als Beleg, siehe Abschnitt 9).
- Darstellung des **App-Icons in hbmenu** (im NRO eingebettet, aber nur auf
  echter Hardware sichtbar).

---

## 11. Offene TODOs / mögliche Erweiterungen

1. ~~NRO-Release veröffentlichen~~ **ERLEDIGT (2026-07-07):** Release mit Tag
   `nro`, Titel `v1.2.0`, Asset `SwitchCheatsDownloader.nro` ist live
   (Self-Update aktiv). Zusätzlich haengt an v1.2 die Nutzer-ZIP
   `SwitchCheatsDownloader-Switch.zip` (SD-Struktur `switch/…nro`), und die
   NRO-Quellen liegen im Repo unter `SwitchCheatsNRO/`. Bei künftigen
   Releases: `APP_VERSION` im Makefile erhöhen → clean bauen → beim
   `nro`-Release Asset ersetzen + **Titel** auf `vX.Y.Z` setzen → neue ZIP
   ans aktuelle Versions-Release hängen.
2. **Abbruch während des Entpackens** lässt teilweise entpackte Dateien zurück –
   ein erneuter Voll-Lauf korrigiert das (überschreibt). Ggf. Rollback ergänzen.
3. **CA-Bundle** (`romfs/cacert.pem`) gelegentlich aktualisieren — oder nach
   Hardware-Test entfernen (curl nutzt den nx-`ssl:`-Service, CAINFO wird
   vermutlich ignoriert; würde ~230 KB sparen).
4. **Automatischer Live-Relaunch** nach Self-Update (bewusst weggelassen, weil
   über CFW-Versionen fragil) – falls gewünscht, `envHasNextLoad()`/`envSetNextLoad`
   evaluieren.
5. Optional: freien SD-Speicher **vor** dem Entpacken prüfen (`statvfs`) statt
   erst am Schreibfehler zu scheitern.
6. Optional: Texture-Caching für gerenderte Textzeilen (aktuell wird jede
   Zeile pro Frame neu gerendert; mit VSync unkritisch, aber Sparpotenzial).
7. Optional: Build-/Release-Automation per GitHub Actions
   (devkitpro/devkita64-Docker: NRO bauen + Host-Tests + `nro`-Release
   aktualisieren).

---

## 12. Schnell-Referenz für Änderungen

- **Version erhöhen (Release):** NUR `APP_VERSION` im Makefile ändern —
  config.hpp und User-Agent übernehmen automatisch.
- **Neuer Menüpunkt:** `kMenuCount` erhöhen, Case in `menuLabel` + `activateItem`
  ergänzen, Render-Block `else if (selected == N)` hinzufügen, i18n-Keys anlegen.
- **Neuer Übersetzungsstring:** Zeile in `kTable` (`i18n.cpp`), auf den
  Hex-Escape-Fallstrick achten (Abschnitt 6). Nutzerseitige Fehlermeldungen
  immer als `err.*`-Key, nie hartkodiert.
- **Neue Netzwerk-/Update-Logik:** in `updater.cpp` implementieren (curl-Setup
  über `applyCommonCurlOpts()`/`httpGetString()`), Signatur in `updater.hpp`
  deklarieren, aus einem Worker in `main.cpp` aufrufen (nie direkt im
  UI-Thread – blockiert das Rendering).
- **Nach jeder Änderung:** Clean-Build ausführen und auf **0 Warnungen**
  achten; bei Logik-Änderungen zusätzlich die Host-Tests laufen lassen
  (Abschnitt 8, „Host-Tests").
