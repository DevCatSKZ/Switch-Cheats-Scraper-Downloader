#pragma once
// ---------------------------------------------------------------------------
// System-Erkennung: installierte Spiele + laufendes Spiel + Build-ID.
//
// Portiert nach dem Vorbild von EdiZon-SE:
//   * Installierte Titel  -> ns (nsListApplicationRecord + nsGetApplicationControlData)
//   * Laufendes Spiel      -> pm:dmnt (pmdmntGetApplicationProcessId) + pminfo
//   * Build-ID (16 Hex)    -> ldr:dmnt (ldrDmntGetProcessModuleInfo, Haupt-NSO)
//                             mit dmnt:cht (Atmosphere) als Fallback.
//
// Threading: ns/pm/ldr sind libnx-Dienste mit globalen Handles. Alle Aufrufe
// hier laufen ausschliesslich im Hintergrund-Worker (runSysScanWorker) bzw.
// werden per g_dataMutex gepuffert - der UI-Thread liest nur die Ergebnisse.
// ---------------------------------------------------------------------------
#include <switch.h>
#include <string>
#include <vector>
#include <cstdint>

namespace sysinfo {

// Ein installiertes Spiel (Basis-Anwendung, ohne separate Update/DLC-Zeilen).
struct InstalledTitle {
    uint64_t titleId = 0;      // Programm-/Title-ID (Basis, low nibble maskiert)
    std::string name;          // Anzeigename (NACP, Konsolensprache)
    std::string author;        // Herausgeber (NACP)
    std::string version;       // display_version, z.B. "1.1.7" ("" moeglich)
};

// Das aktuell laufende Vordergrund-Spiel (per Forwarder erreichbar).
struct RunningGame {
    bool running = false;
    uint64_t titleId = 0;      // Title-ID des laufenden Prozesses
    std::string buildId;       // 16 Hex-Zeichen (erste 8 Byte der main-NSO-Build-ID)
    std::string name;          // aufgeloest via ns ("" wenn unbekannt)
    std::string version;       // display_version ("" moeglich)
    std::string note;          // Diagnose ("" = ok; sonst Grund, warum keine BID)
};

// Initialisiert ns/account/pm einmalig (idempotent). Wird beim App-Start und
// von saves.cpp aufgerufen; mehrfacher Aufruf ist unschaedlich.
void init();
void exit();

// Enumeriert ALLE installierten Anwendungen (nach Name sortiert). Titel ohne
// lesbare Metadaten erscheinen mit Hex-Title-ID als Name.
std::vector<InstalledTitle> listInstalled();

// Name/Autor/Version zu einer Title-ID (gepuffert). false, wenn ns nichts liefert.
bool titleMeta(uint64_t titleId, std::string& name, std::string& author,
               std::string& version);

// Erkennt das laufende Vordergrund-Spiel inkl. Build-ID (nicht-intrusiv:
// pm/ldr lesen nur, es wird KEIN Cheat-Prozess angehaengt). running=false,
// wenn gerade kein Spiel laeuft (nur die App/HB-Menue).
RunningGame currentGame();

// Formatiert die ersten firstN Byte einer Build-ID als GROSSE Hexkette
// (Atmosphere-Konvention: 8 Byte -> 16 Zeichen, entspricht dem Cheat-Dateinamen).
std::string buildIdHex(const uint8_t* b, size_t firstN = 8);

// Normalisiert eine Title-ID zur Basis-Gruppe der Bibliothek
// (substr(0,13)+"000", GROSS) - passend zu db::GameRow::baseTid.
std::string baseGroup(uint64_t titleId);
std::string hex16(uint64_t v); // 16-stellige Grosshex einer u64

} // namespace sysinfo
