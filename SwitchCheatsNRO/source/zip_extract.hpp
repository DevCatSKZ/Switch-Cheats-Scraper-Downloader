#pragma once
#include <string>
#include <functional>

namespace zipextract {

// Fortschritt: (aktueller Eintrag-Index, Gesamtanzahl Eintraege, aktueller Dateiname)
// Rueckgabe false bricht die Extraktion ab.
using ProgressCb = std::function<bool(int index, int total, const std::string& currentName)>;

struct ExtractResult {
    bool ok = false;
    bool cancelled = false;
    int filesWritten = 0;
    std::string error;
};

// Wehrt Zip-Slip ab: absolute Pfade, Laufwerks-/Mount-Praefixe ("sdmc:"),
// Backslashes und ".."-Komponenten in ZIP-Eintragsnamen werden abgelehnt.
// (Inline und ohne Switch-Abhaengigkeiten, damit auf dem Host testbar.)
inline bool isSafeEntryName(const std::string& name) {
    if (name.empty()) return false;
    if (name[0] == '/') return false;
    if (name.find('\\') != std::string::npos) return false;
    if (name.find(':') != std::string::npos) return false;
    if (name == "..") return false;
    if (name.rfind("../", 0) == 0) return false;
    if (name.find("/../") != std::string::npos) return false;
    if (name.size() >= 3 && name.compare(name.size() - 3, 3, "/..") == 0) return false;
    return true;
}

// Entpackt zipPath direkt nach destRoot (z.B. "sdmc:/"), behaelt die im Archiv
// enthaltene Verzeichnisstruktur bei (z.B. atmosphere/contents/<TID>/cheats/<BID>.txt).
// Bereits vorhandene Dateien werden ueberschrieben (die ZIP ist die
// autoritative, staendig aktualisierte Datenquelle).
ExtractResult extractZipToPath(const std::string& zipPath, const std::string& destRoot, const ProgressCb& progress);

} // namespace zipextract
