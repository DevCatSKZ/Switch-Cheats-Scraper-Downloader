#pragma once
// ---------------------------------------------------------------------------
// Installiert-Status: scannt sdmc:/atmosphere/contents/<TID>/cheats/<BID>.txt
// (das Layout der switch-cheats.zip) in einem Hintergrund-Thread in ein
// RAM-Set - das Switch-Pendant zu scan_downloaded_build_ids() am Desktop.
// Abfragen (isInstalled/anyInstalled) sind lockfrei billig genug fuer das
// Rendering (mutex-guarded Set-Lookups).
// ---------------------------------------------------------------------------
#include <string>
#include <utility>
#include <vector>

namespace installer {

// Startet einen (erneuten) Scan im Hintergrund; no-op solange einer laeuft.
void startScan();
bool scanning();          // true solange der Worker arbeitet
bool scannedOnce();       // true nachdem mindestens ein Scan fertig ist
int installedFileCount(); // Anzahl gefundener Cheat-Dateien

// Ist GENAU dieses (TitleID, BuildID)-Paar als Datei auf der SD vorhanden?
bool isInstalled(const std::string& tid, const std::string& bid);
// Ist IRGENDEIN Paar der Liste installiert? (Bibliothekszeile)
bool anyInstalled(const std::vector<std::pair<std::string, std::string>>& pairs);
// Wie viele Paare der Liste sind installiert? (Zeilen-weise Zaehlung wie am
// Desktop: dieselbe Build-ID kann zu mehreren Title-IDs gehoeren.)
int countInstalled(const std::vector<std::pair<std::string, std::string>>& pairs);

// Liest den Inhalt einer installierten Cheat-Datei ("" wenn nicht vorhanden).
std::string readCheatFile(const std::string& tid, const std::string& bid);

// Beim App-Ende: laufenden Scan-Thread joinen.
void shutdown();

} // namespace installer
