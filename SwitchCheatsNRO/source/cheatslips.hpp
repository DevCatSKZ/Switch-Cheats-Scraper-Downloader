#pragma once
// ---------------------------------------------------------------------------
// CheatSlips.com REST-API (https://www.cheatslips.com/api/v1) - das
// Konsolen-Pendant der Desktop-Klasse CheatslipsAPI. Cheat-INHALTE brauchen
// ein API-Token (aus dem eigenen CheatSlips-Account); ohne Token liefert die
// API den Platzhalter "Please register and send APIToken".
//
// Auf der Switch gibt es keinen Browser - das Token wird per Software-
// Tastatur eingegeben und in settings.txt gespeichert.
// ---------------------------------------------------------------------------
#include <string>
#include <vector>

namespace cheatslips {

// Token-Verwaltung (persistiert via settings::).
std::string token();
void setToken(const std::string& t);
bool hasToken();

struct GameCheats {
    bool ok = false;
    std::string error;          // menschenlesbar (uebersetzt/apitext)
    int cheatsSeen = 0;         // Cheats in der Antwort
    int filesWritten = 0;       // geschriebene Build-Dateien
    int skippedNoToken = 0;     // Platzhalter-Inhalte (Token fehlt/ungueltig)
};

// Holt alle Cheats eines Spiels (GET /cheats/{titleId}) und schreibt sie
// pro Build nach sdmc:/atmosphere/contents/<TID>/cheats/<BID>.txt.
// Mehrere Cheats desselben Builds werden aneinandergehaengt.
GameCheats fetchAndInstall(const std::string& titleId);

// Schneller Token-Test: fragt ein bekanntes Spiel ab und prueft, ob echte
// Inhalte (kein Platzhalter) zurueckkommen.
bool tokenWorks(std::string& detail);

} // namespace cheatslips
