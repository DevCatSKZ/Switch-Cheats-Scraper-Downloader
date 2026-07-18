#pragma once
// ---------------------------------------------------------------------------
// Bibliotheks-Datenbank: liest die vom Desktop-Tool veroeffentlichte
// database.db (data-Release, Tabelle "builds") READ-ONLY via SQLite.
//
// Threading-Modell: SQLite ist mit SQLITE_THREADSAFE=0 gebaut - ALLE
// db::-Aufrufe muessen vom UI-Thread kommen. Die Bibliothek wird EINMAL
// komplett in den RAM geladen (~3000 Gruppen, ein paar hundert KB) und
// danach rein in C++ gefiltert/sortiert - das haelt Suche, Filter und
// Paging unabhaengig von SQLite und die DB-Datei ersetzbar (Daten-Update
// laedt eine neue Datei und ruft reload()).
// ---------------------------------------------------------------------------
#include <string>
#include <vector>

namespace db {

// Eine Zeile der Bibliothek = ein SPIEL (Basis-Title-ID, regionale Varianten
// und Updates/DLC per substr(title_id,1,13)||'000' zusammengefasst - exakt
// die Gruppierung der Windows-Galerie und des Spielezaehlers).
struct GameRow {
    std::string baseTid;     // "0100ABCD1234E000" (normalisiert, UPPERCASE)
    std::string title;       // bester bekannter Name ("" wenn unbenannt)
    std::string region;      // z.B. "AU/EU/US"
    int builds = 0;          // Anzahl Builds in der Gruppe
    long long cheats = 0;    // Summe cheat_count
    std::string lastUpdated; // MAX(last_updated) der Gruppe (ISO, "" moeglich)
    std::string image;       // erste bekannte Cover-URL ("" moeglich)
    // Alle (title_id, build_id)-Paare der Gruppe - fuer den Installiert-Check
    // gegen die auf SD liegenden Cheat-Dateien.
    std::vector<std::pair<std::string, std::string>> pairs;
};

// Ein Build fuer die Detailseite (Spaltenauszug aus "builds").
struct BuildRow {
    std::string titleId, buildId, version, source, region;
    int cheatCount = 0;
    std::string cheatNamesJson; // rohes JSON-Array (Namen), "" moeglich
    std::string publisher, developer, category, releaseDate;
    std::string players, languages, rating;
};

struct Stats {
    int games = 0;
    int builds = 0;
    long long cheats = 0;
    long long dbSizeBytes = 0; // 0 = keine DB-Datei vorhanden
};

// Oeffnet die DB (falls vorhanden) und laedt die Bibliothek in den RAM.
// Rueckgabe false, wenn keine/keine lesbare DB da ist (Bibliothek leer).
// Bei Fehlern steht die Ursache in lastError().
bool reload();
const std::string& lastError();

bool loaded();                       // true nach erfolgreichem reload()
const std::vector<GameRow>& games(); // alle Gruppen, nach Titel sortiert
Stats stats();                       // Kennzahlen (aus dem RAM-Abbild)

// Alle Builds eines Spiels (Basis-Gruppe) fuer die Detailseite.
std::vector<BuildRow> gameBuilds(const std::string& baseTid);

// Die juengsten Gruppen (nach lastUpdated absteigend), max n Stueck.
std::vector<const GameRow*> recent(int n);

// Parst ein JSON-String-Array ("cheat_names") in Einzelnamen.
std::vector<std::string> parseNameArray(const std::string& json);

} // namespace db
