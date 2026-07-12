#pragma once
// ---------------------------------------------------------------------------
// Persistente Einstellungen (sdmc:/switch/SwitchCheatsDownloader/settings.txt)
// im simplen key=value-Format - das Switch-Pendant zu settings.json der
// Windows-Version. Favoriten leben hier (NICHT in der DB), damit sie ein
// Daten-Update/DB-Replace ueberleben - gleiche Entscheidung wie am Desktop.
// ---------------------------------------------------------------------------
#include <set>
#include <string>

namespace settings {

// Laedt settings.txt (fehlende Datei = Defaults). Einmal beim Start rufen.
void load();
// Schreibt alle Werte zurueck (legt den App-Ordner bei Bedarf an).
void save();

std::string get(const std::string& key, const std::string& def = "");
void set(const std::string& key, const std::string& value);
bool getBool(const std::string& key, bool def = false);
void setBool(const std::string& key, bool v);

// -- Favoriten (Basis-Title-IDs, UPPERCASE) --------------------------------
bool isFavorite(const std::string& baseTid);
void toggleFavorite(const std::string& baseTid);
const std::set<std::string>& favorites();

} // namespace settings
