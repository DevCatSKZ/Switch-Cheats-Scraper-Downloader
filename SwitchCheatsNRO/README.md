# Switch Cheats Scraper & Downloader (NRO Homebrew) — v2.0

**Der vollständige Port der Windows-Software auf die Nintendo Switch.** Seit
v2.0 ist die `.nro` kein reiner Downloader mehr, sondern bildet dieselbe
Informationsarchitektur und dieselbe **„Prisma / Holo-Glass"-Designsprache** wie
das Desktop-Tool auf der Konsole ab: eine Sidebar-Shell mit den Seiten
**Start · Bibliothek · Quellen · CheatSlips · Einstellungen · Protokoll** plus
Spiel-Detailseite und Cheat-Editor.

Datenbasis ist dasselbe `data`-Release von
[DevCatSKZ/Switch-Cheats-Scraper-Downloader](https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/tag/data):
die **`database.db`** (durchsuchbare Bibliothek mit ~3000 Spielen) und die
**`switch-cheats.zip`** (alle Cheat-Dateien im Atmosphère-Layout
`atmosphere/contents/<TitleID>/cheats/<BuildID>.txt`).

## Was auf der Switch (fast) genauso funktioniert wie am PC

| Windows-Tool | Switch v2.0 |
|---|---|
| Holo-Glass-Sidebar + Rechteck-Aktivmarkierung + Badges | ✅ |
| Start-Dashboard (Spiele/Cheats/installiert/DB-Größe + „Zuletzt aktualisiert") | ✅ (Live-SQLite-Stats) |
| Bibliothek: Suche, Filter-Chips, Spalten, **Cover-Galerie**, Installiert-Status | ✅ Tabelle **und** Kachel-Galerie (Cover async geladen) |
| Spiel-Detailseite: Fakten, Build-Karten, Cheat-Namen, Favoriten | ✅ |
| **CheatSlips-API** (Token, Cheats pro Spiel) | ✅ Token per swkbd, Y auf der Spielseite lädt & installiert |
| Community-Quellen (Hamlet / Sthetix / Breeze …) | ✅ eigene **Quellen-Seite**, lädt direkt ins Atmosphère-Layout |
| **Cheat-Editor** mit Syntax-Validierung | ✅ Zeilen ansehen/bearbeiten (swkbd), Fehler rot, Header gold |
| Export als ZIP · Reset/Clean | ✅ ZIP auf SD-Wurzel · 2-stufiges Löschen |
| Auto-Update (App + Daten) · 6 Sprachen | ✅ |

Der einzige Desktop-Teil, der auf der Konsole **physisch unmöglich** ist, ist das
Playwright-**Browser**-Scraping (kein Chromium auf der Switch). Sein Ersatz ist
genau das, was ohnehin schon da ist: die **CheatSlips-API** + das vom Desktop-Tool
gepflegte, aggregierte `data`-Release — funktional deckungsgleich.

## Funktionsumfang (Basis-Downloader, weiterhin vorhanden)

- **Update-Erkennung, integriert in den Download-Bereich**: fragt die
  GitHub-API nach dem `updated_at`-Zeitstempel des Release-Assets
  `switch-cheats.zip` ab und vergleicht ihn mit dem zuletzt lokal
  installierten Stand (gespeichert in
  `sdmc:/switch/SwitchCheatsDownloader/last_update.txt`). Die Prüfung läuft
  **beim App-Start automatisch** (nur Abfrage, kein Download) und zeigt das
  Ergebnis samt **Download-Größe** (z. B. "(4.3 MB)") direkt im Bereich
  "Herunterladen & Installieren" an; per **Y**-Taste oder Tap auf den
  **Prüfen**-Button lässt sie sich jederzeit manuell wiederholen. Ist die
  Konsole offline, erscheint stattdessen eine rote Meldung "Keine
  Internetverbindung verfügbar." (plus Offline-Anzeige in der Fußleiste).
  Das ist dieselbe "Reupload ohne Versionsbump"-Erkennung wie im Desktop-Tool.
  Der Start-Check prüft **still** auch auf eine neuere App-Version und
  markiert den Menüpunkt "App-Update" dann mit einem blauen Punkt.
- **Download & Installation** in einem Schritt: lädt `switch-cheats.zip` per HTTPS
  herunter (mit Fortschrittsanzeige in MB) und entpackt sie anschließend direkt
  nach `sdmc:/` (Fortschrittsanzeige und Abschlussmeldung in Dateien =
  Anzahl der Build-IDs). Der Download startet **nie automatisch**, sondern
  nur per **A**-Taste bzw. Tap auf den **Starten**-Button.
- **Download-Resume**: Ein abgebrochener Download (B-Taste, Verbindungsabriss,
  Stall) hinterlässt eine `.part`-Teildatei samt Metadatei und wird beim
  nächsten Versuch per HTTP-Range **an derselben Stelle fortgesetzt** —
  aber nur, wenn die Datei noch zum selben Release-Stand (`updated_at`)
  gehört; sonst wird frisch geladen.
- **Mehrsprachigkeit** (EN/DE/ES/FR/IT/JA) — dieselben Sprachen wie das
  Desktop-Tool (`@/c/Coding/Switch Cheats Scraper/i18n.py`), inklusive
  **echter Umlaute/Akzente in allen Sprachen** ("verfügbar", "Télécharger",
  "Última versión", "Già"). Die Systemsprache der Switch wird beim Start
  automatisch erkannt (`setGetSystemLanguage()`), lässt sich aber jederzeit
  per **L/R** durchschalten — oder direkt über die **Sprachauswahl-Leiste**
  (alle 6 Sprachen antippbar) im **Info**-Bereich; die Wahl wird in
  `sdmc:/switch/SwitchCheatsDownloader/lang.txt` gespeichert. Japanische Glyphen
  werden über den Nintendo-Systemfont korrekt dargestellt.
- **App-Self-Update**: analog zur "Nach Updates suchen"-Funktion kann die App
  auch ihre **eigene neue `.nro`-Version** von einem GitHub-Release laden und
  sich selbst ersetzen (Details siehe unten).
- **"Prisma (Holo-Glas)"-Design** — dasselbe Signatur-Theme wie die
  Windows-Version (tiefes Petrol-Schwarz, Teal-Mint-Akzent,
  Teal→Violett-Verlaufs-Button, Gold-Highlights): linke Kategorie-Leiste +
  rechtes Detail-Panel, Fußleiste mit Online-Status (wird alle 5 Sekunden
  aktualisiert), aktuellem Sprachkürzel und Tasten-Hinweisen. VSync begrenzt
  die Renderschleife (Akku/Wärme).
- **Vollständige Joycon-/Controller-Steuerung**: Steuerkreuz **oder linker
  Stick** hoch/runter zur Navigation, **A** bestätigt, **B** bricht eine
  laufende Aktion ab, **+** beendet die App (bricht dabei laufende Downloads
  sauber ab).
- **Touchscreen-Steuerung**: Antippen eines Menüpunkts **wählt ihn nur aus**
  (startet nichts automatisch). Aktionen werden über den **Starten**-Button
  im Panel (bzw. **A**) ausgelöst; während einer laufenden Aktion wird
  derselbe Button zum antippbaren **Abbrechen**-Button.
- **Robustheit**: Schreibfehler (z. B. volle SD-Karte) werden beim Entpacken
  und beim Self-Update erkannt statt still ignoriert; eingeschlafene
  Downloads (< 1 Byte/s für 30 s) werden abgebrochen; ZIP-Eintragspfade
  werden gegen Path-Traversal (Zip-Slip) geprüft; das GitHub-Rate-Limit
  (HTTP 403/429) wird verständlich gemeldet; alte `.part`-Reste werden beim
  Start aufgeräumt. Alle Fehlermeldungen sind in allen 6 Sprachen übersetzt.
- Bestehende Cheat-Dateien auf der SD-Karte werden **überschrieben** — die ZIP
  aus dem eigenen Repository ist die maßgebliche, ständig aktualisierte Quelle.

## Technischer Aufbau

| Datei | Zweck |
|---|---|
| `source/main.cpp` | SDL2-Hauptprogramm: Fenster/Renderer, UI-Zeichnung (Sidebar/Panel/Fußleiste), Eingabeverarbeitung (Joystick + Touch), State-Machine, Hintergrund-Thread-Steuerung |
| `source/updater.hpp/.cpp` | GitHub-API-Abfrage (libcurl), Datei-Download mit Fortschritt/Abbruch, Lesen/Schreiben des lokalen Update-Zeitstempels, Internet-Check (nifm) |
| `source/zip_extract.hpp/.cpp` | Entpacken der ZIP direkt auf die SD-Karte (minizip `unzip.h`), legt Zielverzeichnisse automatisch an |
| `source/json_util.hpp` | Minimaler, gezielter JSON-Feld-Extraktor für die GitHub-API-Antwort (kein voller JSON-Parser nötig, da das Schema fix ist) |
| `source/version_util.hpp` | Reine Versions-String-Logik fürs Self-Update (`normalizeVersion`, `isNewerVersion`) — ohne Switch-Abhängigkeiten, auf dem Host testbar |
| `source/i18n.hpp/.cpp` | Übersetzungstabelle (6 Sprachen, inkl. aller Fehlermeldungen), Systemsprach-Erkennung (`set`-Service), Persistenz der manuellen Sprachwahl, `i18n::tr()`-Lookup |
| `source/config.hpp` | Zentrale Konstanten (Repo, Tag, Asset-Name, Pfade, NRO-Release-Tag); die App-Version kommt aus dem Makefile (`APP_VERSION`) |
| `tests/test_logic.cpp` | Host-Tests für die pure Logik (JSON-Extraktor, Versionsvergleich, Zip-Slip-Schutz) — mit normalem `g++` kompilierbar, kein devkitPro nötig |
| `icon.jpg` | App-Icon (256×256 JPEG) für hbmenu — erzeugt aus dem offiziellen App-Logo der Windows-Software (`app_icon.png`), wird vom Makefile automatisch eingebettet |
| `romfs/cacert.pem` | Mozilla-CA-Bundle, wird für die TLS-Zertifikatsprüfung von libcurl/mbedTLS benötigt (die Switch hat keinen eigenen System-CA-Store für Homebrew) |

**Font:** Es wird **kein** Font mitgeliefert — die App lädt den offiziellen
Nintendo-Systemfont zur Laufzeit über `plGetSharedFontByType()` und reicht ihn
direkt an SDL2_ttf weiter (`TTF_OpenFontRW`). Das spart Platz und stellt volle
Zeichensatz-Unterstützung (Umlaute etc.) sicher.

**Downloads/Entpacken laufen in einem Hintergrund-Thread** (`std::thread`),
damit die Oberfläche währenddessen flüssig auf Eingaben (inkl. Abbrechen)
reagiert. Fortschritt wird über `std::atomic`-Variablen an den Render-Loop
kommuniziert.

## Build-Anleitung

### Voraussetzungen

- [devkitPro](https://devkitpro.org/wiki/Getting_Started) mit den Paketen:
  `switch-dev`, `switch-sdl2`, `switch-sdl2_ttf`, `switch-curl`,
  `switch-mbedtls`, `switch-zlib` (minizip liegt in den `switch-sdl2_image`-
  bzw. Basis-Portlibs bei `libminizip`).

  ```powershell
  (devkitPro pacman) pacman -S switch-dev switch-sdl2 switch-sdl2_ttf switch-curl switch-mbedtls switch-zlib
  ```

- Die Umgebungsvariable `DEVKITPRO` muss gesetzt sein (unter der devkitPro-
  MSYS2-Shell standardmäßig `/opt/devkitpro`).

### ⚠️ Wichtig: Pfad ohne Leerzeichen

GNU Makes Textfunktionen (`notdir` etc.) verarbeiten Pfade **wortweise** und
brechen bei Leerzeichen im Pfad (z. B. `C:\Coding\Switch Cheats Scraper\...`).
Das devkitPro-Standard-Makefile ist davon betroffen. **Vor dem Bauen** daher
einen Laufwerksbuchstaben ohne Leerzeichen auf den Projekt-Elternordner mappen:

```powershell
subst X: "C:\Coding\Switch Cheats Scraper"
```

(Das ist nicht-destruktiv, nur eine virtuelle Laufwerkszuordnung; mit
`subst X: /d` wieder aufhebbar. Muss nach jedem Neustart erneut ausgeführt
werden, da `subst` nicht persistent ist.)

### Bauen

In der devkitPro-MSYS2-Shell (z. B. `c:\devkitPro\msys2\usr\bin\bash.exe`):

```bash
cd /x/SwitchCheatsNRO
make
```

Ergebnis: `SwitchCheatsDownloader.nro` im Projektordner.

```bash
make clean   # räumt build/, .elf, .nacp auf
```

## Installation auf der Switch

**Am einfachsten über das fertige Release:**
[`SwitchCheatsDownloader-Switch.zip`](https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/latest)
herunterladen und **direkt ins Wurzelverzeichnis der SD-Karte entpacken** —
die ZIP bringt die passende Ordnerstruktur mit (`switch/SwitchCheatsDownloader.nro`).

Manuell:

1. `SwitchCheatsDownloader.nro` auf die SD-Karte in den Ordner
   `/switch/` kopieren (z. B. `sd:/switch/SwitchCheatsDownloader.nro`).
2. Über den Homebrew-Menü-Launcher (`hbmenu`) auf der (gemoddeten) Switch starten.
3. Im Programm **"Herunterladen & Installieren"** auswählen (Steuerkreuz + A,
   oder antippen) — lädt die neueste `switch-cheats.zip` und entpackt sie
   automatisch nach `sd:/atmosphere/contents/...`.
4. Mit **"Nach Updates suchen"** kann jederzeit unverbindlich geprüft werden,
   ob eine neuere Version vorliegt, ohne sie direkt herunterzuladen.

Die App benötigt eine aktive **Internetverbindung** (WLAN) auf der Switch;
der Online-Status wird unten links in der Fußleiste angezeigt.

## Bedienung

| Eingabe | Aktion |
|---|---|
| Steuerkreuz oder linker Stick hoch/runter | Menüpunkt wechseln |
| **A** | ausgewählten Menüpunkt aktivieren |
| **Y** | manueller Update-Check (im Bereich "Herunterladen & Installieren") |
| **B** | laufenden Download/Installation abbrechen |
| **L / R** | UI-Sprache umschalten (EN/DE/ES/FR/IT/JA) |
| **+** | App beenden (bricht laufende Aktion sauber ab) |
| Touch (antippen) | Menüpunkt auswählen (führt nichts aus) |
| Touch auf **Starten**-Button | ausgewählte Aktion ausführen (im Leerlauf) |
| Touch auf **Prüfen**-Button | manueller Update-Check (nur im Install-Bereich sichtbar) |
| Touch auf **Sprachauswahl** (DE/EN/ES/FR/IT/JA) | Sprache direkt wählen (nur im Info-Bereich sichtbar) |
| Touch auf **Abbrechen**-Button | laufende Aktion abbrechen (derselbe Button während einer Aktion) |

Menüpunkte:

- **Herunterladen & Installieren** – zeigt den lokalen Stand und die neueste
  verfügbare Version (die Prüfung läuft beim App-Start automatisch, ohne
  Download; **Y**/Prüfen wiederholt sie manuell); **A**/Starten lädt
  `switch-cheats.zip` herunter und entpackt sie auf die SD-Karte (mit
  Fortschrittsanzeige).
- **Info** – zeigt Quelle, Zielpfad, lokal installierten Stand und aktuelle Sprache.
- **App-Update** – prüft auf eine neuere `.nro`-Version (erster A-Druck) und
  installiert sie bei Verfügbarkeit (zweiter A-Druck), siehe unten.
- **Beenden** – schließt die App.

## App-Self-Update (eigene `.nro` aktualisieren)

Der Menüpunkt **App-Update** arbeitet zweistufig, damit die laufende App nicht
versehentlich mitten im Betrieb überschrieben wird:

1. **Erster A-Druck** → *Prüfen*: fragt das GitHub-Release mit dem Tag
   `nro` ab (`cfg::kNroReleaseTag`) und liest die Version aus dem
   **Release-Titel** (`name`-Feld, z. B. `v1.1.0`); diese wird numerisch mit
   `cfg::kAppVersion` verglichen. **Wichtig:** Der `tag_name` des Releases ist
   immer `nro` (das ist der feste Abfrage-Tag) und kann daher keine
   Versionsinfo tragen — deshalb steht die Version im Titel.
2. **Zweiter A-Druck** (nur wenn eine neuere Version gefunden wurde) →
   *Installieren*: lädt das Asset `SwitchCheatsDownloader.nro` herunter,
   prüft die **NRO-Magic** (`"NRO0"` bei Offset 0x10 — verhindert, dass je
   eine HTML-Fehlerseite als App installiert wird) und **ersetzt die eigene
   `.nro`-Datei** an ihrem Startpfad. Danach die App bitte über das
   Homebrew-Menü **neu starten**.

Technische Hinweise:

- Der eigene Pfad wird bevorzugt aus `argv[0]` (vom hbloader übergeben)
  ermittelt, sonst gilt der Fallback `sdmc:/switch/SwitchCheatsDownloader.nro`
  (`cfg::kSelfNroFallbackPath`). Das Überschreiben funktioniert, weil der
  hbloader die `.nro` beim Start vollständig in den RAM lädt und die Datei
  danach nicht mehr geöffnet hält.
- Ersetzt wird per `remove()` + `rename()` (quasi-atomar auf demselben
  Dateisystem); nur wenn das fehlschlägt, greift ein Copy-Fallback mit
  vollständiger Schreibfehler-Prüfung — ein halb geschriebenes Ziel wird
  entfernt statt als Erfolg gemeldet.
- Solange **noch kein** `nro`-Release veröffentlicht ist, liefert die
  GitHub-API einen HTTP 404 — das wird sauber als *"Kein App-Update verfügbar"*
  behandelt (kein Fehler).

### Als Maintainer ein NRO-Release veröffentlichen

Damit das Self-Update greift:

1. `APP_VERSION` im **Makefile** erhöhen (einzige Quelle — `config.hpp` und
   der User-Agent übernehmen den Wert automatisch) und die App neu bauen.
2. Ein GitHub-Release mit dem Tag **`nro`** anlegen (bzw. das bestehende
   aktualisieren) und den **Release-Titel** exakt auf die neue Version setzen
   (z. B. `v1.1.0`). Der Titel muss mit der Versionsnummer beginnen —
   zusätzlicher Text dahinter (z. B. `v1.1.0 Hotfix`) ist erlaubt.
3. Die frisch gebaute `SwitchCheatsDownloader.nro` als Asset mit exakt diesem
   Namen (`cfg::kNroAssetName`) an das Release anhängen.

Repository/Tag/Asset lassen sich zentral in `source/config.hpp` anpassen
(`kNroApiUrl`, `kNroReleaseTag`, `kNroAssetName`).

## Testen im Emulator (Eden)

Die App wurde erfolgreich im **Eden**-Emulator (v0.2.1, yuzu-Fork) getestet —
inklusive echtem GitHub-Update-Check, komplettem Download und Entpacken von
5298 Cheat-Dateien auf die virtuelle SD-Karte:

```powershell
eden.exe -g "C:\...\SwitchCheatsDownloader.nro"
```

- Virtuelle SD-Karte: `%APPDATA%\eden\sdmc\` (dort landen
  `atmosphere/contents/...` und `switch/SwitchCheatsDownloader/...`).
- Emulator-Log: `%APPDATA%\eden\log\eden_log.txt`.
- Standard-Tastatur-Mapping: Pfeiltasten = Steuerkreuz, `C` = A, `X` = B,
  `Q`/`E` = L/R, `M` = +, WASD = linker Stick.
- **Wichtig:** `eden-cli.exe` nutzt eine separate Konfiguration ohne
  Netzwerk-Interface — zum Testen die GUI (`eden.exe -g …`) verwenden.
- Hintergrund: Eden crashte ursprünglich beim Boot der App, weil sein
  DeleteFile-Handler bei `remove()` auf nicht existierende Pfade abstürzt.
  Die App verwendet deshalb überall `removeIfExists()` (stat vor remove) —
  auf echter Hardware verhält sich das identisch.
- Maus-Klicks kommen im Guest als **Touch-Events mit versetzten Koordinaten**
  an (Eden-Eigenheit) — Klick-Ziele treffen daher unzuverlässig; zum
  präzisen Testen die Tastatur verwenden. Auf echter Hardware liefert der
  Touchscreen exakte Koordinaten.

## Fehlerbehebung

**„Netzwerkfehler: SSL peer certificate or SSH remote key was not OK"**
(erscheint direkt beim Prüfen/Herunterladen)

- **Ursache:** Die **Konsolen-Uhr ist falsch gestellt.** Steht Datum/Uhrzeit
  daneben, kann die TLS-Verifikation das GitHub-Zertifikat nicht prüfen — es
  wirkt „noch nicht gültig" bzw. „abgelaufen", und curl bricht mit Fehler 60
  (`CURLE_PEER_FAILED_VERIFICATION`) ab. Besonders häufig mit **90DNS**, das
  Nintendos Zeit-Synchronisation blockiert, sodass die Uhr mit der Zeit abweicht.
- **Lösung:** An der Konsole **Systemeinstellungen → Konsole → Datum und
  Uhrzeit** öffnen und Datum & Uhrzeit korrekt setzen — entweder „Uhrzeit über
  das Internet synchronisieren" kurz aktivieren, oder (bei 90DNS) dieses
  vorübergehend entfernen, damit die Konsole einmal synchronisieren kann. Danach
  die App neu starten; der Download funktioniert wieder. Das mitgelieferte
  CA-Bundle (`romfs/cacert.pem`) enthält die nötigen Roots — ein Update daran ist
  hierfür nicht erforderlich.
- **Proaktiver Hinweis:** Steht die Uhr offensichtlich falsch (vor 2025), zeigt
  die App auf der Download-Seite bereits eine rote Warnung an, bevor der
  Fehlschlag auftritt. Zusätzlich nennt die Fehlermeldung jetzt den genauen
  curl-Grund (z. B. „certificate is not yet valid"), der direkt auf die Uhr zeigt.

## Bekannte Einschränkungen / mögliche Erweiterungen

- Ein Abbruch **während des Entpackens** (B-Taste oder Abbrechen-Button)
  lässt das Archiv teilweise entpackt zurück — ein erneuter vollständiger
  Lauf über "Herunterladen & Installieren" korrigiert das (Dateien werden
  überschrieben).
- Abgebrochene Downloads werden per HTTP-Range fortgesetzt (siehe oben);
  liegengebliebene `.part`-Dateien ohne zugehörige Metadatei werden beim
  App-Start automatisch entfernt.
- Die CA-Zertifikate (`romfs/cacert.pem`) sollten gelegentlich aktualisiert
  werden (Mozilla-CA-Bundle), falls GitHub in Zukunft auf neue Root-CAs wechselt.
- Nach einem App-Self-Update ist ein **manueller Neustart** über das
  Homebrew-Menü nötig — ein automatisches Live-Relaunch der aktualisierten
  `.nro` ist bewusst nicht implementiert (auf der Switch fragil über CFW-Versionen).
- Die L/R-Tastenzuordnung für die Sprachumschaltung folgt der üblichen
  SDL2-Switch-Button-Reihenfolge (`JOY_L=6`, `JOY_R=7`).
