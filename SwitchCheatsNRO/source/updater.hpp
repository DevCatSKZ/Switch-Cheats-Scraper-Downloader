#pragma once
#include <string>
#include <functional>
#include <atomic>

namespace updater {

struct ReleaseInfo {
    bool ok = false;
    std::string downloadUrl;   // browser_download_url des Assets
    std::string updatedAt;     // ISO-8601 Datum des Assets (updated_at)
    long long sizeBytes = 0;   // Asset-Groesse laut API ("size"), 0 wenn unbekannt
    std::string error;
};

// Initialisiert curl global (und damit den ssl:-Service) beim ERSTEN Aufruf;
// weitere Aufrufe sind no-ops. Wird bewusst erst vor dem ersten
// Netzwerkzugriff gerufen (aus den start*()-Funktionen im UI-Thread, nie
// nebenlaeufig): das beschleunigt den App-Start und vermeidet, dass der
// ssl:-Service schon beim Boot angefasst wird (dessen Emulation crasht z.B.
// in Eden/yuzu, waehrend echte Hardware ihn problemlos bereitstellt).
void ensureCurlGlobalInit();

// Gegenstueck fuer den App-Exit: raeumt curl nur auf, wenn es initialisiert wurde.
void curlGlobalCleanup();

// Loescht path nur, wenn er existiert. remove() auf nicht existierende Pfade
// ist auf echter Hardware harmlos (liefert -1), bringt aber den DeleteFile-
// Handler mancher Emulatoren (Eden/yuzu) zum Absturz.
void removeIfExists(const char* path);

// Fragt die GitHub-API nach der aktuellen "data"-Release ab und liefert
// die Download-URL + das Upload/Update-Datum des switch-cheats.zip Assets.
ReleaseInfo fetchLatestReleaseInfo();

// Dasselbe fuer ein BELIEBIGES Asset des data-Release (z.B. database.db).
ReleaseInfo fetchAssetInfo(const char* assetName);

// Fortschritts-Callback: (bytesDownloaded, bytesTotal) -> return false zum Abbrechen
using ProgressCb = std::function<bool(long long done, long long total)>;

struct DownloadResult {
    bool ok = false;
    bool cancelled = false;
    std::string error;
};

// Laedt url in destPath (auf sdmc:/) herunter, ruft progress periodisch auf.
// resumeFrom > 0 setzt einen abgebrochenen Download per HTTP-Range fort
// (destPath wird angehaengt statt ueberschrieben; der Fortschritts-Callback
// bekommt bereits um resumeFrom erhoehte Werte geliefert). keepPartial laesst
// bei Abbruch/Transportfehlern die Teildatei fuer einen spaeteren
// Resume-Versuch liegen (bei HTTP-Fehlern wird sie immer entfernt, weil sie
// dann Fehlerseiten-Bytes enthalten koennte).
DownloadResult downloadFile(const std::string& url, const std::string& destPath, const ProgressCb& progress,
                            long long resumeFrom = 0, bool keepPartial = false);

// Liest/schreibt das lokal gespeicherte "zuletzt installierte" Update-Datum.
std::string readLocalUpdatedAt();
bool writeLocalUpdatedAt(const std::string& isoDate);

// Kleine Datei-Helfer (fuer Resume-Metadaten u.ae.).
bool fileExists(const char* path);
long long fileSize(const char* path);                       // -1 wenn nicht vorhanden
std::string readTextFile(const char* path);                 // getrimmt; "" wenn nicht lesbar
bool writeTextFile(const char* path, const std::string& content); // legt AppDir an

// Einfacher Internet-Erreichbarkeitscheck (nifm).
bool isInternetAvailable();

// ---------------------------------------------------------------------------
// Self-Update der App (.nro) selbst.
// ---------------------------------------------------------------------------
struct AppUpdateInfo {
    bool ok = false;          // Anfrage erfolgreich durchgefuehrt
    bool available = false;   // eine neuere Version wurde gefunden
    std::string remoteVersion;
    std::string downloadUrl;
    std::string error;
};

// Prueft das kNroReleaseTag Release auf eine neuere App-Version: die Version
// steht im Release-TITEL ("name"-Feld, z.B. "v1.1.0") und wird gegen
// cfg::kAppVersion verglichen (der tag_name ist immer "nro" und traegt keine
// Versionsinfo). Ein HTTP 404 (noch kein Release veroeffentlicht) wird als
// "ok=true, available=false" behandelt, nicht als Fehler.
AppUpdateInfo checkAppUpdate();

// Ermittelt den Pfad der eigenen .nro-Datei (bevorzugt argv[0], sonst Fallback).
std::string getSelfNroPath(int argc, char** argv);

// Ersetzt selfPath durch die unter tmpPath heruntergeladene neue .nro.
bool installSelfUpdate(const std::string& tmpPath, const std::string& selfPath, std::string& error);

} // namespace updater
