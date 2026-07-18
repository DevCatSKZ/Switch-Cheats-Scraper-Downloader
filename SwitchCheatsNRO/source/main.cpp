// Switch Cheats Scraper & Downloader - Nintendo Switch Port (.nro)
//
// Der vollstaendige Port der Windows-Software auf die Switch: dieselbe
// Holo-Glass-Designsprache (Prisma-Theme), dieselbe Informationsarchitektur
// (Sidebar: Start / Bibliothek / Einstellungen / Protokoll; Spiel-Detailseite)
// und dieselbe Datenbasis - die vom Desktop-Tool veroeffentlichte database.db
// plus switch-cheats.zip aus dem GitHub "data"-Release.
//
// Bedienung: D-Pad/Stick = Auswahl, A = OK, B = Zurueck/Abbrechen,
// X = Kontext (Filter/Favorit), Y = Suche/Pruefen, L/R = Seite wechseln,
// + = Beenden. Volle Touch-Unterstuetzung.

#include <switch.h>
#include <SDL.h>
#include <SDL_ttf.h>
#include <SDL_image.h>
#include <curl/curl.h>

#include <string>
#include <vector>
#include <unordered_map>
#include <thread>
#include <atomic>
#include <mutex>
#include <functional>
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <ctime>
#include <dirent.h>
#include <unistd.h>

#include "config.hpp"
#include "updater.hpp"
#include "zip_extract.hpp"
#include "i18n.hpp"
#include "db.hpp"
#include "installer.hpp"
#include "settings.hpp"
#include "applog.hpp"
#include "cheatslips.hpp"
#include "covers.hpp"
#include "sysinfo.hpp"
#include "saves.hpp"
#include <unordered_set>
#include <strings.h>

using i18n::tr;

// SDL Joystick Button-Codes (siehe devkitPro switch-examples sdl2-demo)
#define JOY_A     0
#define JOY_B     1
#define JOY_X     2
#define JOY_Y     3
#define JOY_L     6
#define JOY_R     7
#define JOY_ZL    8
#define JOY_ZR    9
#define JOY_PLUS  10
#define JOY_MINUS 11
#define JOY_LEFT  12
#define JOY_UP    13
#define JOY_RIGHT 14
#define JOY_DOWN  15

// ---------------------------------------------------------------------------
// Farbschema: "Prisma (Holo-Glas)" - 1:1 die Werte der Windows-Version
// (gui.py THEMES["prisma"]), damit beide Programme identisch aussehen.
// ---------------------------------------------------------------------------
static const SDL_Color kColBg          = {4, 10, 16, 255};     // #040A10 Canvas
static const SDL_Color kColSidebar     = {11, 20, 28, 255};    // #0B141C Panel
static const SDL_Color kColPanel       = {15, 35, 41, 255};    // #0F2329 Glas
static const SDL_Color kColItem        = {11, 20, 28, 255};    // Button-Glas
static const SDL_Color kColItemHover   = {20, 69, 69, 255};    // #144545 aktiv
static const SDL_Color kColAccent      = {45, 225, 194, 255};  // #2DE1C2 Teal
static const SDL_Color kColAccent2     = {124, 92, 255, 255};  // #7C5CFF Violett
static const SDL_Color kColGold        = {255, 194, 75, 255};  // #FFC24B
static const SDL_Color kColOnAccent    = {4, 33, 28, 255};     // Text AUF Akzent
static const SDL_Color kColHairline    = {39, 44, 49, 255};    // Haarlinie
static const SDL_Color kColText        = {240, 251, 248, 255}; // #F0FBF8
static const SDL_Color kColTextMuted   = {207, 220, 217, 255}; // #CFDCD9
static const SDL_Color kColTextDim     = {130, 152, 148, 255}; // gedimmt (Spalten)
static const SDL_Color kColSuccess     = {62, 230, 143, 255};  // #3EE68F
static const SDL_Color kColError       = {255, 107, 122, 255}; // #FF6B7A
static const SDL_Color kColFooter      = {3, 7, 11, 255};

// Uhr-Plausibilitaet (vor 2025-01-01 UTC = sicher falsch -> TLS scheitert).
static constexpr time_t kMinSaneEpoch = 1735689600LL;

// ---------------------------------------------------------------------------
// Geteilter Zustand zwischen UI-Thread und Hintergrund-Worker
// ---------------------------------------------------------------------------
enum class Action { None, Checking, Installing, AppChecking, AppInstalling,
                    Source, CheatSlips, Export, Clean,
                    SysScan, SaveBackup, SaveRestore };

static std::atomic<Action> g_action{Action::None};
static std::atomic<bool>   g_cancelRequested{false};
static std::atomic<long long> g_bytesDone{0};
static std::atomic<long long> g_bytesTotal{0};
static std::atomic<int> g_zipIndex{0};
static std::atomic<int> g_zipTotal{0};
static std::atomic<bool> g_online{false};
// Worker hat eine neue DB geladen -> UI-Thread muss db::reload() ausfuehren
// (SQLite ist THREADSAFE=0: alle DB-Zugriffe laufen im UI-Thread).
static std::atomic<bool> g_dbNeedsReload{false};

static std::mutex g_dataMutex;
static std::string g_statusLine;
static std::string g_resultLine;
static bool g_resultSuccess = false;
static bool g_haveResult = false;
static std::string g_remoteUpdatedAt;   // switch-cheats.zip
static std::string g_localUpdatedAt;
static long long g_remoteSizeBytes = 0;
static std::string g_dbRemoteUpdatedAt; // database.db
static std::string g_dbLocalUpdatedAt;
static bool g_updateAvailable = false;  // zip ODER db neuer
static bool g_haveRemoteInfo = false;

// App-Self-Update Zustand
static std::string g_appResultLine;
static bool g_appResultSuccess = false;
static bool g_appHaveResult = false;
static bool g_appChecked = false;
static bool g_appUpdateAvailable = false;
static bool g_appJustInstalled = false;
static std::string g_appRemoteVersion;
static std::string g_appDownloadUrl;
static std::string g_selfNroPath;

static std::thread g_worker;

// System-Seite: installierte Spiele, laufendes Spiel und Speicherstaende.
// Vom SysScan-Worker gefuellt, per g_dataMutex geschuetzt, vom UI-Thread gelesen.
static std::vector<sysinfo::InstalledTitle> g_sysTitles;
static sysinfo::RunningGame                 g_sysRunning;
static std::vector<saves::SaveEntry>        g_saves;
static std::atomic<bool> g_sysScanned{false}; // mindestens einmal gescannt
static std::atomic<bool> g_sysDirty{false};   // Worker hat neue Daten -> UI kopiert
// Parameter der Save-Worker (nur vom UI-Thread gesetzt, bevor der Worker startet).
static saves::SaveEntry g_saveTarget;
static std::string      g_saveBackupPath;

static void setStatus(const std::string& s) {
    {
        std::lock_guard<std::mutex> lk(g_dataMutex);
        g_statusLine = s;
    }
    applog::add(s);
}
static std::string getStatus() {
    std::lock_guard<std::mutex> lk(g_dataMutex);
    return g_statusLine;
}
// Wie setStatus, aber OHNE Protokoll-Eintrag - fuer haeufige Fortschritts-
// Updates (z.B. jede kopierte Save-Datei), die das Log sonst fluten wuerden.
static void setStatusQuiet(const std::string& s) {
    std::lock_guard<std::mutex> lk(g_dataMutex);
    g_statusLine = s;
}
static void setResult(bool success, const std::string& msg) {
    {
        std::lock_guard<std::mutex> lk(g_dataMutex);
        g_resultSuccess = success;
        g_resultLine = msg;
        g_haveResult = true;
    }
    applog::add(msg);
}
static void setAppResult(bool success, const std::string& msg) {
    {
        std::lock_guard<std::mutex> lk(g_dataMutex);
        g_appResultSuccess = success;
        g_appResultLine = msg;
        g_appHaveResult = true;
    }
    applog::add(msg);
}

static std::string formatBytes(long long b) {
    char buf[64];
    if (b >= 1024 * 1024) {
        snprintf(buf, sizeof(buf), "%.1f MB", b / (1024.0 * 1024.0));
    } else if (b >= 1024) {
        snprintf(buf, sizeof(buf), "%.1f KB", b / 1024.0);
    } else {
        snprintf(buf, sizeof(buf), "%lld B", b);
    }
    return std::string(buf);
}

// ---------------------------------------------------------------------------
// Hintergrund-Aktionen
// ---------------------------------------------------------------------------
static void joinWorkerIfDone() {
    if (g_action.load() == Action::None && g_worker.joinable()) {
        g_worker.join();
    }
}

static void runCheckWorker() {
    g_cancelRequested = false;
    setStatus(tr("status.checkinternet"));

    bool net = updater::isInternetAvailable();
    g_online = net;
    if (!net) {
        setResult(false, tr("result.noInternet"));
        g_action = Action::None;
        return;
    }

    setStatus(tr("status.connecting"));
    updater::ReleaseInfo info = updater::fetchLatestReleaseInfo();
    if (!info.ok) {
        setResult(false, std::string(tr("result.errorPrefix")) + info.error);
        g_action = Action::None;
        return;
    }
    // Zweites Asset desselben Release-JSONs: database.db.
    updater::ReleaseInfo dbInfo = updater::fetchAssetInfo(cfg::kDbAssetName);

    std::string local = updater::readLocalUpdatedAt();
    std::string dbLocal = updater::readTextFile(cfg::kDbStateFile);
    bool zipNewer = local.empty() || info.updatedAt > local;
    bool dbNewer = dbInfo.ok && (dbLocal.empty() || dbInfo.updatedAt > dbLocal);

    {
        std::lock_guard<std::mutex> lk(g_dataMutex);
        g_remoteUpdatedAt = info.updatedAt;
        g_localUpdatedAt = local;
        g_remoteSizeBytes = info.sizeBytes;
        if (dbInfo.ok) g_dbRemoteUpdatedAt = dbInfo.updatedAt;
        g_dbLocalUpdatedAt = dbLocal;
        g_updateAvailable = zipNewer || dbNewer;
        g_haveRemoteInfo = true;
        g_haveResult = false;
        g_resultLine.clear();
    }

    // Stiller App-Update-Check fuer das Badge in den Einstellungen.
    auto appInfo = updater::checkAppUpdate();
    if (appInfo.ok) {
        std::lock_guard<std::mutex> lk(g_dataMutex);
        g_appUpdateAvailable = appInfo.available;
        if (appInfo.available) {
            g_appRemoteVersion = appInfo.remoteVersion;
            g_appDownloadUrl = appInfo.downloadUrl;
        }
    }

    g_action = Action::None;
}

// true = "Komplett holen" (database.db + switch-cheats.zip); false = "Nur
// Cheats" (nur switch-cheats.zip - das schlanke v1-Verhalten).
static std::atomic<bool> g_installWithDb{true};

// database.db (Bibliothek, optional) + switch-cheats.zip (Cheat-Dateien).
static void runInstallWorker() {
    bool withDb = g_installWithDb.load();
    g_cancelRequested = false;
    g_bytesDone = 0;
    g_bytesTotal = 0;
    g_zipIndex = 0;
    g_zipTotal = 0;

    setStatus(tr("status.checkinternet"));
    bool net = updater::isInternetAvailable();
    g_online = net;
    if (!net) {
        setResult(false, tr("result.noInternet"));
        g_action = Action::None;
        return;
    }

    // -- Schritt 1: database.db (klein, ohne Resume) - nur bei "Komplett" ---
    if (withDb) {
    setStatus(tr("status.dbdownload"));
    updater::ReleaseInfo dbInfo = updater::fetchAssetInfo(cfg::kDbAssetName);
    if (dbInfo.ok) {
        std::string dbLocal = updater::readTextFile(cfg::kDbStateFile);
        bool dbNewer = dbLocal.empty() || dbInfo.updatedAt > dbLocal ||
                       !updater::fileExists(cfg::kDbPath);
        if (dbNewer) {
            updater::removeIfExists(cfg::kTmpDbPath);
            auto dl = updater::downloadFile(dbInfo.downloadUrl, cfg::kTmpDbPath,
                [](long long done, long long total) -> bool {
                    g_bytesDone = done;
                    g_bytesTotal = total;
                    return !g_cancelRequested.load();
                });
            if (dl.cancelled) {
                updater::removeIfExists(cfg::kTmpDbPath);
                setResult(false, tr("result.cancelled"));
                g_action = Action::None;
                return;
            }
            if (dl.ok) {
                updater::removeIfExists(cfg::kDbPath);
                if (rename(cfg::kTmpDbPath, cfg::kDbPath) == 0) {
                    updater::writeTextFile(cfg::kDbStateFile, dbInfo.updatedAt);
                    {
                        std::lock_guard<std::mutex> lk(g_dataMutex);
                        g_dbLocalUpdatedAt = dbInfo.updatedAt;
                        g_dbRemoteUpdatedAt = dbInfo.updatedAt;
                    }
                    g_dbNeedsReload = true;
                    applog::add(tr("log.dbupdated"));
                } else {
                    updater::removeIfExists(cfg::kTmpDbPath);
                    applog::add(tr("log.dbrenamefail"));
                }
            } else {
                // DB-Fehler ist nicht fatal - die Cheats koennen trotzdem laden.
                applog::add(std::string(tr("result.errorPrefix")) + dl.error);
            }
        }
    }
    } // Ende withDb

    // -- Schritt 2: switch-cheats.zip (gross, mit Resume) --------------------
    g_bytesDone = 0;
    g_bytesTotal = 0;
    setStatus(tr("status.connecting"));
    updater::ReleaseInfo info = updater::fetchLatestReleaseInfo();
    if (!info.ok) {
        setResult(false, std::string(tr("result.errorPrefix")) + info.error);
        g_action = Action::None;
        return;
    }

    {
        std::lock_guard<std::mutex> lk(g_dataMutex);
        g_remoteUpdatedAt = info.updatedAt;
        g_remoteSizeBytes = info.sizeBytes;
        g_haveRemoteInfo = true;
    }

    long long resumeFrom = 0;
    {
        long long partSize = updater::fileSize(cfg::kTmpZipPath);
        if (partSize > 0 && updater::readTextFile(cfg::kTmpZipMetaPath) == info.updatedAt) {
            resumeFrom = partSize;
        } else if (partSize >= 0) {
            updater::removeIfExists(cfg::kTmpZipPath);
            updater::removeIfExists(cfg::kTmpZipMetaPath);
        }
    }
    updater::writeTextFile(cfg::kTmpZipMetaPath, info.updatedAt);

    setStatus(tr("status.downloading"));
    auto dlResult = updater::downloadFile(info.downloadUrl, cfg::kTmpZipPath,
        [](long long done, long long total) -> bool {
            g_bytesDone = done;
            g_bytesTotal = total;
            return !g_cancelRequested.load();
        },
        resumeFrom, /*keepPartial=*/true);

    if (dlResult.cancelled) {
        setResult(false, updater::fileExists(cfg::kTmpZipPath)
                             ? tr("result.cancelledResume")
                             : tr("result.cancelled"));
        g_action = Action::None;
        return;
    }
    if (!dlResult.ok) {
        if (!updater::fileExists(cfg::kTmpZipPath)) {
            updater::removeIfExists(cfg::kTmpZipMetaPath);
        }
        setResult(false, std::string(tr("result.errorPrefix")) + dlResult.error);
        g_action = Action::None;
        return;
    }

    setStatus(tr("status.extracting"));
    auto exResult = zipextract::extractZipToPath(cfg::kTmpZipPath, cfg::kSdRoot,
        [](int idx, int total, const std::string& /*name*/) -> bool {
            g_zipIndex = idx;
            g_zipTotal = total;
            return !g_cancelRequested.load();
        });

    if (exResult.cancelled) {
        setResult(false, tr("result.cancelledInstall"));
        remove(cfg::kTmpZipPath);
        updater::removeIfExists(cfg::kTmpZipMetaPath);
        g_action = Action::None;
        return;
    }
    if (!exResult.ok) {
        setResult(false, std::string(tr("result.extractErrorPrefix")) + exResult.error);
        remove(cfg::kTmpZipPath);
        updater::removeIfExists(cfg::kTmpZipMetaPath);
        g_action = Action::None;
        return;
    }

    updater::writeLocalUpdatedAt(info.updatedAt);
    remove(cfg::kTmpZipPath);
    updater::removeIfExists(cfg::kTmpZipMetaPath);

    {
        std::lock_guard<std::mutex> lk(g_dataMutex);
        g_localUpdatedAt = info.updatedAt;
        g_updateAvailable = false;
    }

    // Nach der Installation den Installiert-Status neu einlesen.
    installer::startScan();

    setResult(true, std::string(tr("result.doneInstalledPrefix")) + std::to_string(exResult.filesWritten) +
                    tr("result.doneInstalledSuffix"));
    g_action = Action::None;
}

static void startCheck() {
    if (g_action.load() != Action::None) return;
    joinWorkerIfDone();
    updater::ensureCurlGlobalInit();
    g_action = Action::Checking;
    g_worker = std::thread(runCheckWorker);
}

static void startInstall(bool withDb = true) {
    if (g_action.load() != Action::None) return;
    joinWorkerIfDone();
    updater::ensureCurlGlobalInit();
    g_installWithDb = withDb;
    g_action = Action::Installing;
    g_worker = std::thread(runInstallWorker);
}

static void runAppCheckWorker() {
    g_cancelRequested = false;
    setStatus(tr("appupdate.checking"));

    bool net = updater::isInternetAvailable();
    g_online = net;
    if (!net) {
        setAppResult(false, tr("result.noInternet"));
        g_action = Action::None;
        return;
    }

    auto info = updater::checkAppUpdate();
    if (!info.ok) {
        setAppResult(false, std::string(tr("result.errorPrefix")) + info.error);
        g_action = Action::None;
        return;
    }

    std::lock_guard<std::mutex> lk(g_dataMutex);
    g_appChecked = true;
    if (!info.available) {
        g_appUpdateAvailable = false;
        g_appResultSuccess = true;
        g_appResultLine = tr("result.appUpToDate");
    } else {
        g_appUpdateAvailable = true;
        g_appRemoteVersion = info.remoteVersion;
        g_appDownloadUrl = info.downloadUrl;
        g_appResultSuccess = true;
        g_appResultLine = std::string(tr("result.appUpdateAvailablePrefix")) + info.remoteVersion;
    }
    g_appHaveResult = true;
    g_action = Action::None;
}

static void runAppInstallWorker() {
    g_cancelRequested = false;
    g_bytesDone = 0;
    g_bytesTotal = 0;

    std::string url;
    {
        std::lock_guard<std::mutex> lk(g_dataMutex);
        url = g_appDownloadUrl;
    }
    if (url.empty()) {
        setAppResult(false, tr("result.appUpToDate"));
        g_action = Action::None;
        return;
    }

    setStatus(tr("appupdate.installing"));
    auto dlResult = updater::downloadFile(url, cfg::kTmpNroPath,
        [](long long done, long long total) -> bool {
            g_bytesDone = done;
            g_bytesTotal = total;
            return !g_cancelRequested.load();
        });

    if (dlResult.cancelled) {
        setAppResult(false, tr("result.cancelled"));
        g_action = Action::None;
        return;
    }
    if (!dlResult.ok) {
        setAppResult(false, std::string(tr("result.errorPrefix")) + dlResult.error);
        g_action = Action::None;
        return;
    }

    std::string err;
    if (!updater::installSelfUpdate(cfg::kTmpNroPath, g_selfNroPath, err)) {
        setAppResult(false, std::string(tr("result.errorPrefix")) + err);
        g_action = Action::None;
        return;
    }

    {
        std::lock_guard<std::mutex> lk(g_dataMutex);
        g_appUpdateAvailable = false;
        g_appChecked = false;
        g_appJustInstalled = true;
        g_appResultSuccess = true;
        g_appResultLine = tr("result.appUpdateDone");
        g_appHaveResult = true;
    }
    g_action = Action::None;
}

static void startAppCheck() {
    if (g_action.load() != Action::None) return;
    joinWorkerIfDone();
    updater::ensureCurlGlobalInit();
    {
        std::lock_guard<std::mutex> lk(g_dataMutex);
        g_appJustInstalled = false;
    }
    g_action = Action::AppChecking;
    g_worker = std::thread(runAppCheckWorker);
}

static void startAppInstall() {
    if (g_action.load() != Action::None) return;
    joinWorkerIfDone();
    updater::ensureCurlGlobalInit();
    g_action = Action::AppInstalling;
    g_worker = std::thread(runAppInstallWorker);
}

// ---------------------------------------------------------------------------
// Community-Quellen (Quellen-Seite): GitHub-latest-Release-Archive im
// titles/<TID>/cheats/<BID>.txt-Layout -> direkt ins Atmosphere-Layout.
// Dieselben Quellen wie die Desktop-Buttons (die uebrigen Desktop-Quellen
// stecken bereits aggregiert im data-Release).
// ---------------------------------------------------------------------------
struct SourceDef {
    const char* key;        // i18n-Prefix (src.<key>.name / .desc)
    const char* repo;
    const char* assets;     // Release-Asset-Kandidaten (komma-getrennt); live: ""
    bool live;              // true = Default-Branch-ZIP (main/master) statt Release
};
// Vollstaendige Quellen-Liste des Windows-Tools (gui.py Sources-Grid).
// Release-Assets: fetchRepoLatestAsset. Live-Repos: Default-Branch-ZIP.
static const SourceDef kSources[] = {
    {"gbatemp",    "HamletDuFromage/switch-cheats-db",          "contents_complete.zip,titles_complete.zip", false},
    {"hamlet",     "HamletDuFromage/switch-cheats-db",          "titles_complete.zip",       false},
    {"hamlet60",   "HamletDuFromage/switch-cheats-db",          "titles_60fps-res-gfx.zip",  false},
    {"ibnux",      "ibnux/switch-cheat",                        "",                          true},
    {"sthetix",    "sthetix/nx-cheats-db",                      "titles_complete.zip",       false},
    {"breeze",     "tomvita/NXCheatCode",                       "titles.zip",                false},
    {"chansey",    "ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats",  "",                          true},
    {"mynxcheats", "Arch9SK7/MyNXCheats",                       "",                          true},
};
static constexpr int kSourceCount = 8;
static std::atomic<int> g_sourceRunning{-1}; // Index in kSources waehrend Action::Source

static std::vector<std::string> splitCsv(const std::string& s) {
    std::vector<std::string> out;
    std::string cur;
    for (char c : s) {
        if (c == ',') { if (!cur.empty()) out.push_back(cur); cur.clear(); }
        else cur += c;
    }
    if (!cur.empty()) out.push_back(cur);
    return out;
}

static void runSourceWorker(int idx) {
    g_cancelRequested = false;
    g_bytesDone = 0;
    g_bytesTotal = 0;
    g_zipIndex = 0;
    g_zipTotal = 0;
    const SourceDef& src = kSources[idx];

    setStatus(tr("status.checkinternet"));
    bool net = updater::isInternetAvailable();
    g_online = net;
    if (!net) {
        setResult(false, tr("result.noInternet"));
        g_sourceRunning = -1;
        g_action = Action::None;
        return;
    }

    setStatus(tr("status.connecting"));
    std::string tmpZip = std::string(cfg::kAppDir) + "/source.zip.part";
    updater::removeIfExists(tmpZip.c_str());
    auto progress = [](long long done, long long total) -> bool {
        g_bytesDone = done;
        g_bytesTotal = total;
        return !g_cancelRequested.load();
    };

    updater::DownloadResult dl;
    if (src.live) {
        // Live-Repo: Default-Branch-ZIP (erst main, dann master). Kein Release.
        setStatus(tr("status.downloading.src"));
        std::string base = "https://github.com/" + std::string(src.repo) + "/archive/refs/heads/";
        dl = updater::downloadFile(base + "main.zip", tmpZip, progress);
        if (!dl.ok && !dl.cancelled) {
            updater::removeIfExists(tmpZip.c_str());
            g_bytesDone = 0; g_bytesTotal = 0;
            dl = updater::downloadFile(base + "master.zip", tmpZip, progress);
        }
    } else {
        auto info = updater::fetchRepoLatestAsset(src.repo, splitCsv(src.assets));
        if (!info.ok) {
            setResult(false, std::string(tr("result.errorPrefix")) + info.error);
            g_sourceRunning = -1;
            g_action = Action::None;
            return;
        }
        setStatus(tr("status.downloading.src"));
        dl = updater::downloadFile(info.downloadUrl, tmpZip, progress);
    }
    if (dl.cancelled || !dl.ok) {
        updater::removeIfExists(tmpZip.c_str());
        setResult(false, dl.cancelled ? tr("result.cancelled")
                                      : std::string(tr("result.errorPrefix")) + dl.error);
        g_sourceRunning = -1;
        g_action = Action::None;
        return;
    }

    setStatus(tr("status.extracting"));
    auto ex = zipextract::extractCheatArchive(tmpZip,
        [](int i, int total, const std::string&) -> bool {
            g_zipIndex = i;
            g_zipTotal = total;
            return !g_cancelRequested.load();
        });
    updater::removeIfExists(tmpZip.c_str());
    if (ex.cancelled) {
        setResult(false, tr("result.cancelledInstall"));
    } else if (!ex.ok) {
        setResult(false, std::string(tr("result.extractErrorPrefix")) + ex.error);
    } else {
        installer::startScan();
        char buf[160];
        snprintf(buf, sizeof(buf), "%s: %d %s / %d %s", tr(("src." + std::string(src.key) + ".name").c_str()),
                 ex.filesWritten, tr("unit.files"), ex.gamesSeen, tr("unit.games"));
        setResult(true, buf);
    }
    g_sourceRunning = -1;
    g_action = Action::None;
}

static void startSource(int idx) {
    if (g_action.load() != Action::None) return;
    joinWorkerIfDone();
    updater::ensureCurlGlobalInit();
    g_sourceRunning = idx;
    g_action = Action::Source;
    g_worker = std::thread(runSourceWorker, idx);
}

// -- CheatSlips: Cheats fuer EIN Spiel laden (von der Detailseite, Y) --------
static std::string g_csTid;      // Ziel-TitleID des laufenden Fetches
static std::atomic<bool> g_csDone{false}; // Detailseite soll neu laden

static void runCheatslipsWorker() {
    g_cancelRequested = false;
    setStatus(tr("cs.fetching"));
    bool net = updater::isInternetAvailable();
    g_online = net;
    if (!net) {
        setResult(false, tr("result.noInternet"));
        g_action = Action::None;
        return;
    }
    auto r = cheatslips::fetchAndInstall(g_csTid);
    if (!r.ok) {
        setResult(false, std::string(tr("result.errorPrefix")) + r.error);
    } else if (r.filesWritten == 0) {
        std::string why = r.skippedNoToken > 0 ? tr("cs.badtoken") : tr("cs.notfound");
        setResult(false, why);
    } else {
        installer::startScan();
        char buf[128];
        snprintf(buf, sizeof(buf), "CheatSlips: %d %s (%d Cheats)",
                 r.filesWritten, tr("unit.files"), r.cheatsSeen);
        setResult(true, buf);
        g_csDone = true;
    }
    g_action = Action::None;
}

static void startCheatslipsFetch(const std::string& tid) {
    if (g_action.load() != Action::None) return;
    joinWorkerIfDone();
    updater::ensureCurlGlobalInit();
    g_csTid = tid;
    g_action = Action::CheatSlips;
    g_worker = std::thread(runCheatslipsWorker);
}

// -- Export: alle installierten Cheats als ZIP auf die SD-Wurzel -------------
static void runExportWorker() {
    g_cancelRequested = false;
    g_zipIndex = 0;
    g_zipTotal = 0;
    setStatus(tr("exp.running"));
    const char* dest = "sdmc:/switch-cheats-export.zip";
    updater::removeIfExists(dest);
    auto r = zipextract::zipInstalledCheats(dest,
        [](int i, int, const std::string&) -> bool {
            g_zipIndex = i;
            return !g_cancelRequested.load();
        });
    if (r.cancelled) {
        setResult(false, tr("result.cancelled"));
    } else if (!r.ok) {
        setResult(false, std::string(tr("result.errorPrefix")) + r.error);
    } else {
        char buf[160];
        snprintf(buf, sizeof(buf), "%s%d%s", tr("exp.done.prefix"), r.filesWritten,
                 tr("exp.done.suffix"));
        setResult(true, buf);
    }
    g_action = Action::None;
}

static void startExport() {
    if (g_action.load() != Action::None) return;
    joinWorkerIfDone();
    g_action = Action::Export;
    g_worker = std::thread(runExportWorker);
}

// -- Clean: alle installierten Cheat-Dateien + Cover von der SD entfernen ----
static void runCleanWorker() {
    g_cancelRequested = false;
    setStatus(tr("clean.running"));
    int removed = 0;
    std::string root = std::string(cfg::kSdRoot) + "atmosphere/contents";
    DIR* d = opendir(root.c_str());
    if (d) {
        struct dirent* e;
        while ((e = readdir(d)) != nullptr) {
            std::string tid = e->d_name;
            if (tid == "." || tid == "..") continue;
            std::string cheatsDir = root + "/" + tid + "/cheats";
            DIR* cd = opendir(cheatsDir.c_str());
            if (!cd) continue;
            std::vector<std::string> files;
            struct dirent* ce;
            while ((ce = readdir(cd)) != nullptr) {
                std::string fn = ce->d_name;
                if (fn.size() > 4 && fn.compare(fn.size() - 4, 4, ".txt") == 0) {
                    files.push_back(cheatsDir + "/" + fn);
                }
            }
            closedir(cd);
            for (const auto& f : files) {
                if (remove(f.c_str()) == 0) removed++;
            }
            // leere cheats/- und Titel-Ordner aufraeumen (scheitert harmlos,
            // wenn noch andere Inhalte (exefs u.ae.) drinliegen)
            rmdir(cheatsDir.c_str());
            rmdir((root + "/" + tid).c_str());
            if (g_cancelRequested.load()) break;
        }
        closedir(d);
    }
    covers::clearDisk();
    updater::removeIfExists(cfg::kStateFile);
    installer::startScan();
    char buf[128];
    snprintf(buf, sizeof(buf), "%s%d%s", tr("clean.done.prefix"), removed, tr("clean.done.suffix"));
    setResult(true, buf);
    g_action = Action::None;
}

static void startClean() {
    if (g_action.load() != Action::None) return;
    joinWorkerIfDone();
    g_action = Action::Clean;
    g_worker = std::thread(runCleanWorker);
}

// ---------------------------------------------------------------------------
// System-Erkennung: installierte Spiele + laufendes Spiel + Saves scannen.
// Alle libnx-Systemdienste (ns/pm/ldr/fs/account) werden hier im Hintergrund
// abgefragt - der UI-Thread liest nur die gepufferten Ergebnisse.
// ---------------------------------------------------------------------------
static void runSysScanWorker() {
    setStatus(tr("sys.scanning"));
    sysinfo::init();
    sysinfo::RunningGame run = sysinfo::currentGame();
    auto titles = sysinfo::listInstalled();
    auto sv = saves::listSaves();
    {
        std::lock_guard<std::mutex> lk(g_dataMutex);
        g_sysRunning = run;
        g_sysTitles = std::move(titles);
        g_saves = std::move(sv);
    }
    g_sysScanned = true;
    g_sysDirty = true;
    char buf[96];
    snprintf(buf, sizeof(buf), "%s%d%s", tr("sys.scandone.prefix"),
             (int)g_sysTitles.size(), tr("sys.scandone.suffix"));
    setResult(true, buf);
    g_action = Action::None;
}
static void startSysScan() {
    if (g_action.load() != Action::None) return;
    joinWorkerIfDone();
    g_action = Action::SysScan;
    g_worker = std::thread(runSysScanWorker);
}

static void runSaveBackupWorker() {
    saves::SaveEntry e;
    { std::lock_guard<std::mutex> lk(g_dataMutex); e = g_saveTarget; }
    setStatus(tr("save.backing"));
    std::string outPath, err;
    bool ok = saves::backup(e, outPath, err, [](const std::string& f) {
        setStatusQuiet(std::string(tr("save.file")) + " " + f);
    });
    if (ok) setResult(true, tr("save.backup.ok"));
    else    setResult(false, std::string(tr("save.backup.fail")) + " (" + err + ")");
    g_action = Action::None;
}
static void startSaveBackup(const saves::SaveEntry& e) {
    if (g_action.load() != Action::None) return;
    joinWorkerIfDone();
    { std::lock_guard<std::mutex> lk(g_dataMutex); g_saveTarget = e; }
    g_action = Action::SaveBackup;
    g_worker = std::thread(runSaveBackupWorker);
}

static void runSaveRestoreWorker() {
    saves::SaveEntry e; std::string path;
    { std::lock_guard<std::mutex> lk(g_dataMutex); e = g_saveTarget; path = g_saveBackupPath; }
    setStatus(tr("save.restoring"));
    std::string err;
    bool ok = saves::restore(e, path, err, [](const std::string& f) {
        setStatusQuiet(std::string(tr("save.file")) + " " + f);
    });
    if (ok) setResult(true, tr("save.restore.ok"));
    else    setResult(false, std::string(tr("save.restore.fail")) + " (" + err + ")");
    g_action = Action::None;
}
static void startSaveRestore(const saves::SaveEntry& e, const std::string& path) {
    if (g_action.load() != Action::None) return;
    joinWorkerIfDone();
    { std::lock_guard<std::mutex> lk(g_dataMutex); g_saveTarget = e; g_saveBackupPath = path; }
    g_action = Action::SaveRestore;
    g_worker = std::thread(runSaveRestoreWorker);
}

// ---------------------------------------------------------------------------
// Rendering-Hilfsfunktionen
// ---------------------------------------------------------------------------
static void setColor(SDL_Renderer* r, SDL_Color c) {
    SDL_SetRenderDrawColor(r, c.r, c.g, c.b, c.a);
}
static void fillRect(SDL_Renderer* r, int x, int y, int w, int h, SDL_Color c) {
    SDL_Rect rect{x, y, w, h};
    setColor(r, c);
    SDL_RenderFillRect(r, &rect);
}
static void drawRectOutline(SDL_Renderer* r, int x, int y, int w, int h, SDL_Color c) {
    SDL_Rect rect{x, y, w, h};
    setColor(r, c);
    SDL_RenderDrawRect(r, &rect);
}
// Text-Textur-Cache: TTF_Render + CreateTexture JEDE Frame war der
// Haupt-FPS-Fresser (~30 FPS in der Bibliothek). Gerenderte Zeilen werden
// pro (Font, Farbe, Text) gecacht und periodisch per LRU ausgeduennt.
struct CachedText {
    SDL_Texture* tex = nullptr;
    int w = 0, h = 0;
    Uint32 lastUse = 0;
};
static std::unordered_map<std::string, CachedText> g_textCache;

static void textCacheMaintain() {
    if (g_textCache.size() < 700) return;
    Uint32 now = SDL_GetTicks();
    for (auto it = g_textCache.begin(); it != g_textCache.end();) {
        if (now - it->second.lastUse > 4000) {
            if (it->second.tex) SDL_DestroyTexture(it->second.tex);
            it = g_textCache.erase(it);
        } else {
            ++it;
        }
    }
}
static void textCacheDestroy() {
    for (auto& [k, v] : g_textCache) {
        if (v.tex) SDL_DestroyTexture(v.tex);
    }
    g_textCache.clear();
}

static void drawText(SDL_Renderer* r, TTF_Font* font, const std::string& text, int x, int y, SDL_Color color) {
    if (text.empty() || !font) return;
    char keyBuf[48];
    snprintf(keyBuf, sizeof(keyBuf), "%p|%02x%02x%02x|", (void*)font, color.r, color.g, color.b);
    std::string key = std::string(keyBuf) + text;
    auto it = g_textCache.find(key);
    if (it == g_textCache.end()) {
        SDL_Surface* surf = TTF_RenderUTF8_Blended(font, text.c_str(), color);
        if (!surf) return;
        CachedText ct;
        ct.tex = SDL_CreateTextureFromSurface(r, surf);
        ct.w = surf->w;
        ct.h = surf->h;
        SDL_FreeSurface(surf);
        if (!ct.tex) return;
        it = g_textCache.emplace(std::move(key), ct).first;
    }
    it->second.lastUse = SDL_GetTicks();
    SDL_Rect dst{x, y, it->second.w, it->second.h};
    SDL_RenderCopy(r, it->second.tex, nullptr, &dst);
}
static int textWidth(TTF_Font* font, const std::string& text) {
    if (!font || text.empty()) return 0;
    int w = 0, h = 0;
    TTF_SizeUTF8(font, text.c_str(), &w, &h);
    return w;
}
static void drawTextCentered(SDL_Renderer* r, TTF_Font* font, const std::string& text, int x, int y, int lineH, SDL_Color color) {
    if (!font) return;
    int tw = 0, th = 0;
    TTF_SizeUTF8(font, text.c_str(), &tw, &th);
    drawText(r, font, text, x, y + (lineH - th) / 2, color);
}
static void drawTextRight(SDL_Renderer* r, TTF_Font* font, const std::string& text, int xRight, int y, SDL_Color color) {
    drawText(r, font, text, xRight - textWidth(font, text), y, color);
}

// Horizontaler Farbverlauf (Signatur-Buttons Teal -> Violett).
static void drawGradientRectH(SDL_Renderer* r, int x, int y, int w, int h,
                              SDL_Color c1, SDL_Color c2) {
    for (int i = 0; i < w; i++) {
        float f = (w <= 1) ? 0.0f : static_cast<float>(i) / static_cast<float>(w - 1);
        SDL_SetRenderDrawColor(r,
            static_cast<Uint8>(c1.r + (c2.r - c1.r) * f),
            static_cast<Uint8>(c1.g + (c2.g - c1.g) * f),
            static_cast<Uint8>(c1.b + (c2.b - c1.b) * f), 255);
        SDL_RenderDrawLine(r, x + i, y, x + i, y + h - 1);
    }
}

// Gezeichnetes Haekchen - das "✓"-Glyph fehlt im Nintendo-Systemfont
// (rendert als Kaestchen), also zeichnen wir es selbst (2px dick).
static void drawCheckmark(SDL_Renderer* r, int cx, int cy, int size, SDL_Color c) {
    setColor(r, c);
    int x1 = cx - size / 2, y1 = cy;
    int x2 = cx - size / 6, y2 = cy + size / 3;
    int x3 = cx + size / 2, y3 = cy - size / 3;
    for (int off = 0; off < 2; off++) {
        SDL_RenderDrawLine(r, x1, y1 + off, x2, y2 + off);
        SDL_RenderDrawLine(r, x2, y2 + off, x3, y3 + off);
    }
}

static void drawProgressBar(SDL_Renderer* r, int x, int y, int w, int h, double frac, SDL_Color fg) {
    if (frac < 0) frac = 0;
    if (frac > 1) frac = 1;
    fillRect(r, x, y, w, h, kColItem);
    fillRect(r, x, y, static_cast<int>(w * frac), h, fg);
    drawRectOutline(r, x, y, w, h, kColHairline);
}

// Glass-Karte: Panel-Flaeche + Haarlinien-Rand (Holo-Glass-Grundelement).
static void drawCard(SDL_Renderer* r, int x, int y, int w, int h,
                     SDL_Color fill = kColPanel, SDL_Color border = kColHairline) {
    fillRect(r, x, y, w, h, fill);
    drawRectOutline(r, x, y, w, h, border);
}

// Eyebrow-Schreibweise der Windows-Seitenkoepfe: "S T Ö B E R N"
// (Leerzeichen zwischen den UTF-8-Codepoints).
static std::string spaced(const std::string& s) {
    std::string out;
    size_t i = 0;
    while (i < s.size()) {
        unsigned char c = static_cast<unsigned char>(s[i]);
        size_t len = (c < 0x80) ? 1 : (c < 0xE0) ? 2 : (c < 0xF0) ? 3 : 4;
        if (i + len > s.size()) len = 1;
        if (!out.empty()) out += ' ';
        out.append(s, i, len);
        i += len;
    }
    return out;
}

// Bricht Text am Wortende auf maxW um (mehrzeilig, vollstaendig lesbar).
// Ueberlange Einzel-"Woerter" (z.B. CJK ohne Leerzeichen) werden hart an der
// UTF-8-Codepoint-Grenze gebrochen. Ergebnis pro (Font,maxW,Text) gecacht.
static std::unordered_map<std::string, std::vector<std::string>> g_wrapCache;
static const std::vector<std::string>& wrapText(TTF_Font* font, const std::string& text, int maxW) {
    std::string key = std::to_string((uintptr_t)font) + "|" + std::to_string(maxW) + "|" + text;
    auto it = g_wrapCache.find(key);
    if (it != g_wrapCache.end()) return it->second;
    std::vector<std::string> lines;
    std::string line;
    int lastSpaceLen = -1;   // Byte-Position eines Leerzeichens in `line`
    size_t i = 0;
    while (i < text.size()) {
        unsigned char c = static_cast<unsigned char>(text[i]);
        size_t len = (c < 0x80) ? 1 : (c < 0xE0) ? 2 : (c < 0xF0) ? 3 : 4;
        if (i + len > text.size()) len = 1;
        std::string ch = text.substr(i, len);
        std::string trial = line + ch;
        if (!line.empty() && textWidth(font, trial) > maxW) {
            if (lastSpaceLen > 0) {
                lines.push_back(line.substr(0, lastSpaceLen));
                line = line.substr(lastSpaceLen + 1);
            } else {
                lines.push_back(line);
                line.clear();
            }
            lastSpaceLen = -1;
            line += ch;
        } else {
            line = trial;
        }
        if (ch == " ") lastSpaceLen = static_cast<int>(line.size()) - 1;
        i += len;
    }
    if (!line.empty()) lines.push_back(line);
    if (lines.empty()) lines.push_back("");
    if (g_wrapCache.size() > 512) g_wrapCache.clear();
    return g_wrapCache.emplace(std::move(key), std::move(lines)).first->second;
}

// Text auf maxW kuerzen (mit "..."), Ergebnis gecacht (stabile Zeilen).
static std::unordered_map<std::string, std::string> g_truncCache;
static std::string truncated(TTF_Font* font, const std::string& text, int maxW) {
    if (!font || text.empty()) return text;
    std::string key = std::to_string(maxW) + "|" + text;
    auto it = g_truncCache.find(key);
    if (it != g_truncCache.end()) return it->second;
    std::string result = text;
    if (textWidth(font, text) > maxW) {
        std::string cur = text;
        while (!cur.empty() && textWidth(font, cur + "...") > maxW) {
            // letztes UTF-8-Zeichen entfernen
            size_t cut = cur.size() - 1;
            while (cut > 0 && (static_cast<unsigned char>(cur[cut]) & 0xC0) == 0x80) cut--;
            cur.resize(cut);
        }
        result = cur + "...";
    }
    if (g_truncCache.size() > 4096) g_truncCache.clear();
    g_truncCache[key] = result;
    return result;
}

// ---------------------------------------------------------------------------
// Software-Tastatur (swkbd) - fuer Suche und Texteingaben.
// ---------------------------------------------------------------------------
static bool showKeyboard(const std::string& header, const std::string& initial,
                         std::string& out) {
    SwkbdConfig kbd;
    if (R_FAILED(swkbdCreate(&kbd, 0))) return false;
    swkbdConfigMakePresetDefault(&kbd);
    swkbdConfigSetHeaderText(&kbd, header.c_str());
    swkbdConfigSetInitialText(&kbd, initial.c_str());
    swkbdConfigSetStringLenMax(&kbd, 60);
    char buf[256] = {0};
    Result rc = swkbdShow(&kbd, buf, sizeof(buf));
    swkbdClose(&kbd);
    if (R_FAILED(rc)) return false;
    out = buf;
    return true;
}

// ---------------------------------------------------------------------------
// Seiten / Navigation
// ---------------------------------------------------------------------------
enum class Page { Home = 0, Library, Sources, CheatSlips, System, SaveGames,
                  Settings, Log, Detail, Editor, SysDetail, Saves };

struct NavEntry {
    Page page;
    const char* labelKey;
    const char* eyebrowKey;
    const char* subKey;
};
static const NavEntry kNav[] = {
    {Page::Home,       "nav.home",       "eyebrow.home",       "sub.home"},
    {Page::Library,    "nav.library",    "eyebrow.library",    "sub.library"},
    {Page::Sources,    "nav.sources",    "eyebrow.sources",    "sub.sources"},
    {Page::CheatSlips, "nav.cheatslips", "eyebrow.cheatslips", "sub.cheatslips"},
    {Page::System,     "nav.system",     "eyebrow.system",     "sub.system"},
    {Page::SaveGames,  "nav.saves",      "eyebrow.saves",      "sub.saves"},
    {Page::Settings,   "nav.settings",   "eyebrow.settings",   "sub.settings"},
    {Page::Log,        "nav.log",        "eyebrow.log",        "sub.log"},
};
static constexpr int kNavCount = 8;

// ---------------------------------------------------------------------------
// Cheat-Zeilen-Klassifizierung - der Port von classify_cheat_line() aus
// gui.py: Header [..]/{..}, gueltige Codezeile = 1-4 Woerter aus je 8 Hex.
// ---------------------------------------------------------------------------
enum class LineKind { Empty, Header, Master, Code, Error };
static LineKind classifyCheatLine(const std::string& raw) {
    // trim
    size_t a = raw.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return LineKind::Empty;
    size_t b = raw.find_last_not_of(" \t\r\n");
    std::string s = raw.substr(a, b - a + 1);
    if (s.front() == '[' && s.back() == ']') return LineKind::Header;
    if (s.front() == '{' && s.back() == '}') return LineKind::Master;
    // Woerter zaehlen und pruefen
    int words = 0;
    size_t i = 0;
    while (i < s.size()) {
        while (i < s.size() && (s[i] == ' ' || s[i] == '\t')) i++;
        if (i >= s.size()) break;
        size_t start = i;
        while (i < s.size() && s[i] != ' ' && s[i] != '\t') i++;
        std::string w = s.substr(start, i - start);
        if (w.size() != 8) return LineKind::Error;
        for (char c : w) {
            if (!std::isxdigit(static_cast<unsigned char>(c))) return LineKind::Error;
        }
        words++;
        if (words > 4) return LineKind::Error;
    }
    return words >= 1 ? LineKind::Code : LineKind::Error;
}

// Bibliotheks-Filter (X-Taste zykliert) - Pendant der Windows-Chips.
enum class LibFilter { All = 0, HasCheats, Installed, Favorites, Count };

// Wiederhol-Navigation: erster Schritt sofort, dann Delay + Repeat.
struct Repeater {
    Uint32 nextAt = 0;
    int dir = 0;
    int step(int curDir, Uint32 now) {
        if (curDir == 0) {
            dir = 0;
            return 0;
        }
        if (curDir != dir) {
            dir = curDir;
            nextAt = now + 320;
            return curDir;
        }
        if (static_cast<Sint32>(now - nextAt) >= 0) {
            nextAt = now + 70;
            return curDir;
        }
        return 0;
    }
};

// Touch-Ziel: Rechteck + Aktion (pro Frame neu aufgebaut).
struct HitBox {
    SDL_Rect rect;
    std::function<void()> fn;
};

int main(int argc, char** argv) {
    romfsInit();
    socketInitializeDefault();

    Result plRc = plInitialize(PlServiceType_User);
    i18n::init();
    settings::load();
    g_selfNroPath = updater::getSelfNroPath(argc, argv);

    // Reste abgebrochener Laeufe aufraeumen (siehe Kommentar in v1.3).
    updater::removeIfExists(cfg::kTmpNroPath);
    updater::removeIfExists(cfg::kTmpDbPath);
    if (updater::fileExists(cfg::kTmpZipPath) != updater::fileExists(cfg::kTmpZipMetaPath)) {
        updater::removeIfExists(cfg::kTmpZipPath);
        updater::removeIfExists(cfg::kTmpZipMetaPath);
    }

    SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER);
    SDL_InitSubSystem(SDL_INIT_JOYSTICK);
    SDL_JoystickEventState(SDL_ENABLE);
    SDL_Joystick* joy = SDL_JoystickOpen(0);
    TTF_Init();
    IMG_Init(IMG_INIT_JPG | IMG_INIT_PNG);
    covers::init();

    SDL_Window* window = SDL_CreateWindow("Switch Cheats Scraper & Downloader",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        cfg::kScreenW, cfg::kScreenH, SDL_WINDOW_SHOWN);
    SDL_Renderer* renderer = SDL_CreateRenderer(window, -1,
        SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);

    TTF_Font* fontTitle = nullptr;  // 30 - Seitentitel
    TTF_Font* fontStat  = nullptr;  // 36 - Stat-Karten-Werte
    TTF_Font* fontBody  = nullptr;  // 22 - Flaechentext
    TTF_Font* fontSmall = nullptr;  // 18 - Sekundaertext
    TTF_Font* fontTiny  = nullptr;  // 15 - Eyebrows/Badges/Spalten

    if (R_SUCCEEDED(plRc)) {
        PlFontData font;
        if (R_SUCCEEDED(plGetSharedFontByType(&font, PlSharedFontType_Standard))) {
            fontTitle = TTF_OpenFontRW(SDL_RWFromConstMem(font.address, font.size), 1, 30);
            fontStat  = TTF_OpenFontRW(SDL_RWFromConstMem(font.address, font.size), 1, 36);
            fontBody  = TTF_OpenFontRW(SDL_RWFromConstMem(font.address, font.size), 1, 22);
            fontSmall = TTF_OpenFontRW(SDL_RWFromConstMem(font.address, font.size), 1, 18);
            fontTiny  = TTF_OpenFontRW(SDL_RWFromConstMem(font.address, font.size), 1, 15);
        }
    }

    // Sofort einen Ladebildschirm zeichnen, BEVOR die (grosse) DB synchron
    // geladen wird - sonst wirkt das Fenster beim Start eingefroren (v2.1.1).
    {
        SDL_SetRenderDrawColor(renderer, kColBg.r, kColBg.g, kColBg.b, 255);
        SDL_RenderClear(renderer);
        if (fontStat) {
            std::string ld = tr("app.loading");
            int tw = textWidth(fontStat, ld);
            drawText(renderer, fontStat, ld, (cfg::kScreenW - tw) / 2,
                     cfg::kScreenH / 2 - 26, kColAccent);
        }
        SDL_RenderPresent(renderer);
    }

    // Lokale Staende + Bibliothek laden, Installiert-Scan starten.
    {
        std::lock_guard<std::mutex> lk(g_dataMutex);
        g_localUpdatedAt = updater::readLocalUpdatedAt();
        g_dbLocalUpdatedAt = updater::readTextFile(cfg::kDbStateFile);
    }
    // DB-Laden STARTEN (nicht blockierend): der Haupt-Loop laeuft sofort los und
    // laedt die ~5000 Builds haeppchenweise via reloadStep() (unten im Loop) -
    // die Steuerung reagiert ab dem ersten Frame. Kein Thread, kein Rendern im
    // Ladecode (beides crasht die Konsole).
    if (!db::reloadBegin() && updater::fileExists(cfg::kDbPath)) {
        applog::add(std::string("DB: ") + db::lastError());
    }
    // Namen-Resolver fuer den System-Scan: Spielnamen kommen aus unserer DB
    // (RAM) statt per 128-KB-Read/Spiel von der Konsole. Waehrend die DB noch
    // laedt (loaded()==false) NICHT lesen - dann faellt der Scan auf ns zurueck.
    sysinfo::setNameResolver([](uint64_t tid, std::string& out) -> bool {
        if (!db::loaded()) return false;
        std::string base = sysinfo::baseGroup(tid);
        for (const auto& g : db::games()) {
            if (!g.title.empty() && strcasecmp(g.baseTid.c_str(), base.c_str()) == 0) {
                out = g.title;
                return true;
            }
        }
        return false;
    });
    installer::startScan();
    // Online-Status NICHT synchron am Start pruefen - nifmInitialize + Abfrage
    // blockieren den Main-Thread. Der periodische Check im Loop uebernimmt das
    // kurz nach dem ersten Frame (schnelles, sichtbares Erscheinen der UI).
    Uint32 nextOnlineCheck = SDL_GetTicks() + 600;

    // ---------------- UI-Zustand ----------------
    Page page = Page::Home;
    Page pageBeforeDetail = Page::Library;
    bool exitRequested = false;
    bool autoCheckStarted = false;
    bool dbWasLoaded = false;   // Erkennt das Ende des inkrementellen DB-Ladens

    // Bibliothek
    std::string libQuery;
    LibFilter libFilter = LibFilter::All;
    std::vector<int> libRows;      // Indizes in db::games()
    int libSel = 0;                // Auswahl innerhalb libRows
    int libScroll = 0;
    bool libDirty = true;          // Filter/Suche/DB geaendert -> neu aufbauen
    bool prevScanned = false;
    int prevInstalledCount = -1;

    // Detailseite
    std::string detailTid;
    std::string detailTitle;
    std::vector<db::BuildRow> detailBuilds;
    int detailSel = 0;
    int detailScroll = 0;
    bool detailExpanded = false;   // Cheat-Namen des gewaehlten Builds offen
    int detailNameScroll = 0;
    std::unordered_map<std::string, std::vector<std::string>> nameCache;

    // Bibliothek: Tabellen- oder Galerie-Ansicht (Minus wechselt - das
    // Pendant zum Table/Gallery-Toggle der Windows-Bibliothek).
    bool libGallery = false;

    // Quellen-Seite
    int srcSel = 0;
    int srcScroll = 0;

    // CheatSlips-Seite (eine Token-Karte)
    // (kein eigener Zustand noetig - Token liegt in settings)

    // Editor (verstecke Seite; ZR auf einem installierten Build im Detail)
    std::string edTid, edBid;
    std::vector<std::string> edLines;
    bool edDirty = false;
    int edSel = 0;
    int edScroll = 0;

    // System-Seiten: installierte Spiele / laufendes Spiel / Speicherstaende.
    // ui*-Kopien werden aus den g_sys*-Puffern uebernommen (SQLite/libnx-Dienste
    // laufen im Worker; der UI-Thread arbeitet nur auf diesen Kopien).
    std::vector<sysinfo::InstalledTitle> uiTitles;
    sysinfo::RunningGame                 uiRunning;
    std::vector<saves::SaveEntry>        uiSaves;
    int sysSel = 0, sysScroll = 0;                 // Auswahl Installiert-Liste
    sysinfo::InstalledTitle sysDetailTitle;        // in SysDetail geoeffnetes Spiel
    int saveSel = 0, saveScroll = 0;               // Auswahl auf der Saves-Seite
    int sgSel = 0, sgScroll = 0;                    // Auswahl auf der Speicherstaende-Seite
    Page savesReturn = Page::System;               // wohin B von der Saves-Seite zurueckkehrt
    int saveUserSel = 0;                           // gewaehlter Nutzer-Save (Restore-Ziel)
    bool restoreArmed = false;                     // Restore-Sicherheitsstufe (wie cleanArmed)
    std::vector<saves::Backup> saveBackups;        // Backups des offenen Spiels (UI-Cache)
    std::vector<db::BuildRow> sysDetailBuilds;      // Build-IDs des offenen Spiels (aus DB)
    std::unordered_set<std::string> dbBaseSet;     // Basis-TIDs mit Cheats (O(1)-Lookup)
    bool dbBaseSetReady = false;
    Action prevAct = Action::None;                 // Erkennung "Save-Worker fertig"
    std::vector<Page> pageStack;                   // Navigations-Verlauf (B = zurueck)
    bool menuFocus = false;                         // Fokus links (Menue) statt rechts (Inhalt)
    int  menuSel = 0;                               // Cursor-Position im linken Menue

    // Einstellungen: 0=Sprache 1=App-Update 2=Neu laden 3=Export 4=Clean
    int setSel = 0;
    static constexpr int kSetCount = 5;
    bool cleanArmed = false;       // Sicherheitsstufe: 1. A scharf, 2. A loescht

    // Protokoll
    int logScroll = 0;             // 0 = ganz unten (neueste)

    // Eingabe-Wiederholung
    Repeater repUpDown;
    int stickDir = 0;
    bool stickSeenNeutral = false;

    std::vector<HitBox> hits;      // Touch-Ziele des aktuellen Frames

    // Layout-Konstanten (gespiegelt an gui_modern.py)
    const int headerH = 64;
    const int sidebarW = 280;
    const int footerH = 52;
    const int contentX = sidebarW + 40;
    const int contentW = cfg::kScreenW - contentX - 40;
    const int navItemH = 58;
    const int navStartY = headerH + 46;

    auto rebuildLibRows = [&]() {
        libRows.clear();
        const auto& games = db::games();
        std::string q = libQuery;
        for (auto& c : q) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        for (int i = 0; i < static_cast<int>(games.size()); i++) {
            const auto& g = games[i];
            if (!q.empty()) {
                std::string hay = g.title + " " + g.baseTid;
                for (auto& c : hay) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
                if (hay.find(q) == std::string::npos) continue;
            }
            switch (libFilter) {
                case LibFilter::HasCheats:
                    if (g.cheats <= 0) continue;
                    break;
                case LibFilter::Installed:
                    if (!installer::anyInstalled(g.pairs)) continue;
                    break;
                case LibFilter::Favorites:
                    if (!settings::isFavorite(g.baseTid)) continue;
                    break;
                default:
                    break;
            }
            libRows.push_back(i);
        }
        if (libSel >= static_cast<int>(libRows.size())) libSel = static_cast<int>(libRows.size()) - 1;
        if (libSel < 0) libSel = 0;
        libDirty = false;
    };

    // Nav-Seiten (Hauptmenue) vs. Unterseiten (Detail/Editor/SysDetail/Saves,
    // die ihr eigenes B-Zurueck haben).
    auto isNavPage = [](Page p) {
        return p != Page::Detail && p != Page::Editor &&
               p != Page::SysDetail && p != Page::Saves;
    };
    // Wechsel zwischen Menueseiten mit Verlauf: die aktuelle Nav-Seite wird
    // gemerkt, damit B eine Navigation zurueckspringt (normale Switch-Zurueck-Geste).
    auto navTo = [&](Page target) {
        if (target == page) return;
        if (isNavPage(page)) {
            pageStack.push_back(page);
            if (pageStack.size() > 16) pageStack.erase(pageStack.begin());
        }
        page = target;
    };

    auto openDetail = [&](const db::GameRow& g) {
        detailTid = g.baseTid;
        detailTitle = g.title.empty() ? g.baseTid : g.title;
        detailBuilds = db::gameBuilds(g.baseTid);
        detailSel = 0;
        detailScroll = 0;
        detailExpanded = false;
        detailNameScroll = 0;
        pageBeforeDetail = page;
        page = Page::Detail;
    };

    // Basis-TID-Menge (Spiele mit Cheats in unserer DB) fuer O(1)-Markierung
    // installierter Spiele. Wird bei DB-Reload neu aufgebaut.
    auto rebuildDbBaseSet = [&]() {
        dbBaseSet.clear();
        for (auto& g : db::games()) dbBaseSet.insert(g.baseTid);
        dbBaseSetReady = true;
    };
    auto titleHasCheats = [&](uint64_t tid) -> bool {
        if (!dbBaseSetReady) rebuildDbBaseSet();
        return dbBaseSet.count(sysinfo::baseGroup(tid)) > 0;
    };
    // Springt zur Cheat-Detailseite des Spiels (Basis-Gruppe) - von der
    // System-/SysDetail-Seite aus (B kehrt dank pageBeforeDetail korrekt zurueck).
    auto openCheatsForTid = [&](uint64_t tid) -> bool {
        std::string base = sysinfo::baseGroup(tid);
        for (auto& g : db::games()) {
            if (strcasecmp(g.baseTid.c_str(), base.c_str()) == 0) { openDetail(g); return true; }
        }
        applog::add(tr("sys.nocheats"));
        return false;
    };
    auto openSysDetail = [&](const sysinfo::InstalledTitle& t) {
        sysDetailTitle = t;
        saveBackups = saves::listBackups(t.titleId);           // Zaehler ohne Frame-I/O
        sysDetailBuilds = db::gameBuilds(sysinfo::baseGroup(t.titleId)); // Build-IDs aus DB
        page = Page::SysDetail;
    };
    auto openSavesPage = [&](uint64_t tid) {
        savesReturn = page;   // Ruecksprungziel merken (SysDetail oder Speicherstaende)
        saveBackups = saves::listBackups(tid);
        saveSel = 0; saveScroll = 0; saveUserSel = 0; restoreArmed = false;
        page = Page::Saves;
    };
    // Saves (aus uiSaves) fuer eine bestimmte Title-ID (Basis, low nibble egal).
    auto curSaves = [&](uint64_t tid) {
        std::vector<saves::SaveEntry> v;
        uint64_t mask = 0xFFFFFFFFFFFFFFF0ULL;
        for (auto& e : uiSaves)
            if ((e.titleId & mask) == (tid & mask)) v.push_back(e);
        return v;
    };

    auto openEditor = [&](const std::string& tid, const std::string& bid) {
        std::string content = installer::readCheatFile(tid, bid);
        edLines.clear();
        std::string cur;
        for (char c : content) {
            if (c == '\n') {
                if (!cur.empty() && cur.back() == '\r') cur.pop_back();
                edLines.push_back(cur);
                cur.clear();
            } else {
                cur += c;
            }
        }
        if (!cur.empty()) edLines.push_back(cur);
        if (edLines.empty()) edLines.push_back("");
        edTid = tid;
        edBid = bid;
        edDirty = false;
        edSel = 0;
        edScroll = 0;
        page = Page::Editor;
    };

    auto saveEditor = [&]() {
        std::string path = std::string(cfg::kSdRoot) + "atmosphere/contents/" +
                           edTid + "/cheats/" + edBid + ".txt";
        FILE* f = fopen(path.c_str(), "wb");
        if (!f) {
            applog::add(std::string(tr("err.createFile")) + path);
            return false;
        }
        for (size_t i = 0; i < edLines.size(); i++) {
            fputs(edLines[i].c_str(), f);
            if (i + 1 < edLines.size()) fputc('\n', f);
        }
        fclose(f);
        edDirty = false;
        applog::add(tr("ed.saved"));
        return true;
    };

    auto filterLabel = [&](LibFilter f) -> std::string {
        switch (f) {
            case LibFilter::HasCheats: return tr("lib.filter.cheats");
            case LibFilter::Installed: return tr("lib.filter.installed");
            case LibFilter::Favorites: return tr("lib.filter.favs");
            default: return tr("lib.filter.all");
        }
    };

    auto doSearch = [&]() {
        std::string out;
        if (showKeyboard(tr("lib.search.header"), libQuery, out)) {
            libQuery = out;
            libSel = 0;
            libScroll = 0;
            libDirty = true;
        } else {
            applog::add(tr("log.kbdfail"));
        }
    };

    while (!exitRequested && appletMainLoop()) {
        Uint32 now = SDL_GetTicks();
        bool busy = g_action.load() != Action::None;

        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) {
                exitRequested = true;
            } else if (event.type == SDL_JOYBUTTONDOWN) {
                int btn = event.jbutton.button;
                bool onNavPage = page != Page::Detail && page != Page::Editor &&
                                 page != Page::SysDetail && page != Page::Saves;
                if (btn == JOY_PLUS) {
                    if (busy) g_cancelRequested = true;
                    exitRequested = true;
                } else if (btn == JOY_B) {
                    if (busy) {
                        g_cancelRequested = true;
                    } else if (menuFocus) {
                        menuFocus = false;   // B im Menue-Fokus -> zurueck in den Inhalt
                    } else if (page == Page::Editor) {
                        if (edDirty) applog::add(tr("ed.discarded"));
                        page = Page::Detail;
                    } else if (page == Page::Detail) {
                        page = pageBeforeDetail;
                    } else if (page == Page::Saves) {
                        page = savesReturn;
                    } else if (page == Page::SysDetail) {
                        page = Page::System;
                    } else if (!pageStack.empty()) {
                        // Nav-Seite: eine Navigation zurueck (Verlaufs-Stack).
                        page = pageStack.back();
                        pageStack.pop_back();
                        cleanArmed = false;
                    }
                } else if (btn == JOY_L && onNavPage) {
                    int idx = 0;
                    for (int i = 0; i < kNavCount; i++) {
                        if (kNav[i].page == page) idx = i;
                    }
                    navTo(kNav[(idx + kNavCount - 1) % kNavCount].page);
                    cleanArmed = false;
                    menuFocus = false;
                } else if (btn == JOY_R && onNavPage) {
                    int idx = 0;
                    for (int i = 0; i < kNavCount; i++) {
                        if (kNav[i].page == page) idx = i;
                    }
                    navTo(kNav[(idx + 1) % kNavCount].page);
                    cleanArmed = false;
                    menuFocus = false;
                } else if (btn == JOY_A) {
                    if (menuFocus) {
                        navTo(kNav[menuSel].page);   // A im Menue -> gewaehlte Seite oeffnen
                        menuFocus = false;
                    } else if (page == Page::Home) {
                        if (!busy) startInstall(true);
                    } else if (page == Page::Library) {
                        if (!libRows.empty() && libSel < static_cast<int>(libRows.size())) {
                            openDetail(db::games()[libRows[libSel]]);
                        }
                    } else if (page == Page::System) {
                        if (!busy && !uiTitles.empty() &&
                            sysSel < static_cast<int>(uiTitles.size()))
                            openSysDetail(uiTitles[sysSel]);
                    } else if (page == Page::SysDetail) {
                        if (!busy) openSavesPage(sysDetailTitle.titleId);
                    } else if (page == Page::SaveGames) {
                        if (!busy && !uiTitles.empty() &&
                            sgSel < static_cast<int>(uiTitles.size())) {
                            sysDetailTitle = uiTitles[sgSel];
                            openSavesPage(sysDetailTitle.titleId);
                        }
                    } else if (page == Page::Saves) {
                        // Zeilen: [0..nUsers) Save-Quellen (Backup), danach Backups (Restore).
                        auto cs = curSaves(sysDetailTitle.titleId);
                        int nUsers = static_cast<int>(cs.size());
                        if (!busy) {
                            if (saveSel < nUsers) {
                                saveUserSel = saveSel;
                                restoreArmed = false;
                                startSaveBackup(cs[saveSel]);
                            } else {
                                int bi = saveSel - nUsers;
                                if (nUsers > 0 && bi >= 0 &&
                                    bi < static_cast<int>(saveBackups.size())) {
                                    if (!restoreArmed) {
                                        restoreArmed = true;   // 1x A = scharf schalten
                                    } else {
                                        restoreArmed = false;
                                        int u = (saveUserSel < nUsers) ? saveUserSel : 0;
                                        startSaveRestore(cs[u], saveBackups[bi].path);
                                    }
                                }
                            }
                        }
                    } else if (page == Page::Sources) {
                        if (!busy) startSource(srcSel);
                    } else if (page == Page::CheatSlips) {
                        // Token per Software-Tastatur eingeben/aendern
                        std::string out;
                        if (showKeyboard(tr("cs.token.header"), cheatslips::token(), out)) {
                            cheatslips::setToken(out);
                            applog::add(out.empty() ? tr("cs.token.cleared") : tr("cs.token.saved"));
                        }
                    } else if (page == Page::Detail) {
                        detailExpanded = !detailExpanded;
                        detailNameScroll = 0;
                    } else if (page == Page::Editor) {
                        if (edSel < static_cast<int>(edLines.size())) {
                            std::string out;
                            if (showKeyboard(tr("ed.line.header"), edLines[edSel], out)) {
                                if (out != edLines[edSel]) {
                                    edLines[edSel] = out;
                                    edDirty = true;
                                }
                            }
                        }
                    } else if (page == Page::Settings) {
                        if (setSel == 1 && !busy) {
                            bool checked, available;
                            {
                                std::lock_guard<std::mutex> lk(g_dataMutex);
                                checked = g_appChecked;
                                available = g_appUpdateAvailable;
                            }
                            if (checked && available) startAppInstall();
                            else startAppCheck();
                        } else if (setSel == 2) {
                            db::reload();
                            installer::startScan();
                            libDirty = true;
                            applog::add(tr("set.reload.done"));
                        } else if (setSel == 3 && !busy) {
                            startExport();
                        } else if (setSel == 4 && !busy) {
                            if (!cleanArmed) {
                                cleanArmed = true;
                            } else {
                                cleanArmed = false;
                                startClean();
                            }
                        }
                    }
                } else if (btn == JOY_Y) {
                    if (page == Page::Library) {
                        doSearch();
                    } else if (page == Page::Home && !busy) {
                        startCheck();
                    } else if ((page == Page::System || page == Page::SysDetail ||
                                page == Page::SaveGames) && !busy) {
                        startSysScan();
                    } else if (page == Page::Detail && !busy && !detailTid.empty()) {
                        if (cheatslips::hasToken()) {
                            startCheatslipsFetch(detailTid);
                        } else {
                            applog::add(tr("cs.token.missing"));
                        }
                    } else if (page == Page::CheatSlips && !busy) {
                        // Token testen
                        updater::ensureCurlGlobalInit();
                        std::string detail;
                        bool ok = cheatslips::tokenWorks(detail);
                        applog::add((ok ? "OK: " : "!! ") + detail);
                    } else if (page == Page::Editor) {
                        // neue Zeile nach der aktuellen einfuegen
                        std::string out;
                        if (showKeyboard(tr("ed.newline.header"), "", out)) {
                            edLines.insert(edLines.begin() + edSel + 1, out);
                            edSel++;
                            edDirty = true;
                        }
                    }
                } else if (btn == JOY_X) {
                    if (page == Page::Home) {
                        if (!busy) startInstall(false);   // Nur Cheats (v1-Verhalten)
                    } else if (page == Page::Saves && !busy) {
                        auto cs = curSaves(sysDetailTitle.titleId);
                        int nUsers = static_cast<int>(cs.size());
                        int bi = saveSel - nUsers;
                        if (bi >= 0 && bi < static_cast<int>(saveBackups.size())) {
                            if (saves::deleteBackup(saveBackups[bi].path)) {
                                saveBackups = saves::listBackups(sysDetailTitle.titleId);
                                int total = nUsers + static_cast<int>(saveBackups.size());
                                if (saveSel >= total) saveSel = total - 1;
                                if (saveSel < 0) saveSel = 0;
                                restoreArmed = false;
                                applog::add(tr("save.deleted"));
                            }
                        }
                    } else if (page == Page::Library) {
                        libFilter = static_cast<LibFilter>(
                            (static_cast<int>(libFilter) + 1) % static_cast<int>(LibFilter::Count));
                        libSel = 0;
                        libScroll = 0;
                        libDirty = true;
                    } else if (page == Page::Detail && !detailTid.empty()) {
                        settings::toggleFavorite(detailTid);
                        libDirty = true;
                    } else if (page == Page::Editor) {
                        if (edLines.size() > 1) {
                            edLines.erase(edLines.begin() + edSel);
                            if (edSel >= static_cast<int>(edLines.size()))
                                edSel = static_cast<int>(edLines.size()) - 1;
                            edDirty = true;
                        } else if (!edLines[0].empty()) {
                            edLines[0].clear();
                            edDirty = true;
                        }
                    }
                } else if (btn == JOY_MINUS) {
                    if (page == Page::Library) {
                        libGallery = !libGallery;
                        libScroll = 0; // Scroll-Index wechselt die Bedeutung (Zeile/Reihe)
                    } else if (page == Page::Editor && edDirty) {
                        saveEditor();
                    }
                } else if (btn == JOY_ZR) {
                    if (page == Page::System && uiRunning.running) {
                        openCheatsForTid(uiRunning.titleId);
                    } else if (page == Page::SysDetail) {
                        openCheatsForTid(sysDetailTitle.titleId);
                    } else if (page == Page::Detail && detailSel < static_cast<int>(detailBuilds.size())) {
                        const auto& b = detailBuilds[detailSel];
                        if (installer::isInstalled(b.titleId, b.buildId)) {
                            openEditor(b.titleId, b.buildId);
                        } else {
                            applog::add(tr("ed.notinstalled"));
                        }
                    }
                } else if (btn == JOY_LEFT) {
                    if (menuFocus) {
                        // bereits im linken Menue
                    } else if (page == Page::Library && libGallery && (libSel % 6) != 0) {
                        libSel -= 1;   // innerhalb der Galerie-Reihe nach links
                    } else if (page == Page::Settings && setSel == 0) {
                        i18n::prevLang();
                    } else if (isNavPage(page)) {
                        menuFocus = true;   // Links -> ans linke Menue
                        menuSel = 0;        // Cursor auf die aktuelle Seite setzen
                        for (int i = 0; i < kNavCount; i++)
                            if (kNav[i].page == page) menuSel = i;
                    }
                } else if (btn == JOY_RIGHT) {
                    if (menuFocus) {
                        navTo(kNav[menuSel].page);   // Rechts -> gewaehlte Seite oeffnen
                        menuFocus = false;
                    } else if (page == Page::Library && libGallery) {
                        libSel += 1;        // Galerie nach rechts
                        if (libSel >= static_cast<int>(libRows.size()))
                            libSel = static_cast<int>(libRows.size()) - 1;
                        if (libSel < 0) libSel = 0;
                    } else if (page == Page::Settings && setSel == 0) {
                        i18n::nextLang();
                    }
                }
            } else if (event.type == SDL_FINGERDOWN || event.type == SDL_MOUSEBUTTONDOWN) {
                int px, py;
                if (event.type == SDL_FINGERDOWN) {
                    px = static_cast<int>(event.tfinger.x * cfg::kScreenW);
                    py = static_cast<int>(event.tfinger.y * cfg::kScreenH);
                } else {
                    px = event.button.x;
                    py = event.button.y;
                }
                for (const auto& h : hits) {
                    if (px >= h.rect.x && px < h.rect.x + h.rect.w &&
                        py >= h.rect.y && py < h.rect.y + h.rect.h) {
                        h.fn();
                        break;
                    }
                }
            }
        }

        joinWorkerIfDone();

        // Bibliotheks-DB haeppchenweise laden (nicht-blockierend): der Loop laeuft
        // normal weiter, also reagiert die Steuerung ab dem ersten Frame. Wenn
        // fertig geladen -> Bibliothek + Cheat-Set einmal neu aufbauen.
        if (db::loading()) db::reloadStep(400);
        if (db::loaded() && !dbWasLoaded) {
            dbWasLoaded = true;
            libDirty = true;
            dbBaseSetReady = false;
        }

        if (!autoCheckStarted) {
            autoCheckStarted = true;
            startCheck();
        }

        // Worker hat eine neue database.db abgelegt -> im UI-Thread neu laden.
        if (g_dbNeedsReload.exchange(false)) {
            db::reload();
            installer::startScan();
            libDirty = true;
            dbBaseSetReady = false;   // Cheat-Markierungen der System-Liste neu aufbauen
        }

        // System-/Speicherstaende-Seite: beim ersten Betreten automatisch scannen.
        if ((page == Page::System || page == Page::SaveGames) &&
            !g_sysScanned.load() && g_action.load() == Action::None) {
            startSysScan();
        }
        // Worker hat neue System-Daten geliefert -> in UI-lokale Kopien uebernehmen.
        if (g_sysDirty.exchange(false)) {
            std::lock_guard<std::mutex> lk(g_dataMutex);
            uiTitles = g_sysTitles;
            uiRunning = g_sysRunning;
            uiSaves = g_saves;
            if (sysSel >= static_cast<int>(uiTitles.size()))
                sysSel = static_cast<int>(uiTitles.size()) - 1;
            if (sysSel < 0) sysSel = 0;
            if (sgSel >= static_cast<int>(uiTitles.size()))
                sgSel = static_cast<int>(uiTitles.size()) - 1;
            if (sgSel < 0) sgSel = 0;
        }
        // Save-Backup/Restore abgeschlossen -> Backup-Liste der Saves-Seite auffrischen.
        {
            Action curAct = g_action.load();
            if (prevAct != curAct) {
                if ((prevAct == Action::SaveBackup || prevAct == Action::SaveRestore) &&
                    curAct == Action::None && page == Page::Saves) {
                    saveBackups = saves::listBackups(sysDetailTitle.titleId);
                }
                prevAct = curAct;
            }
        }
        // CheatSlips-Fetch fertig -> Detailseite zeigt neuen Installiert-Stand.
        if (g_csDone.exchange(false) && page == Page::Detail && !detailTid.empty()) {
            detailBuilds = db::gameBuilds(detailTid);
        }

        // Installiert-Scan fertig geworden / Zaehler geaendert -> Filter neu.
        {
            bool sc = installer::scannedOnce();
            int ic = installer::installedFileCount();
            if (sc != prevScanned || ic != prevInstalledCount) {
                prevScanned = sc;
                prevInstalledCount = ic;
                if (libFilter == LibFilter::Installed) libDirty = true;
            }
        }

        if (libDirty) rebuildLibRows();

        // Auf/Ab-Navigation mit Wiederholung (D-Pad + linker Stick).
        {
            int dir = 0;
            if (joy) {
                if (SDL_JoystickGetButton(joy, JOY_UP)) dir = -1;
                else if (SDL_JoystickGetButton(joy, JOY_DOWN)) dir = 1;
                if (dir == 0) {
                    Sint16 ax = SDL_JoystickGetAxis(joy, 1);
                    const int kDeadzone = 16000;
                    int sdir = (ax < -kDeadzone) ? -1 : (ax > kDeadzone) ? 1 : 0;
                    if (sdir == 0) stickSeenNeutral = true;
                    if (stickSeenNeutral) dir = sdir;
                    stickDir = sdir;
                }
            }
            int step = repUpDown.step(dir, now);
            if (step != 0) {
                if (menuFocus) {
                    // Menue-Fokus: Hoch/Runter bewegt den Cursor (ohne Seitenwechsel);
                    // A/Rechts oeffnet die gewaehlte Seite.
                    menuSel += step;
                    if (menuSel < 0) menuSel = 0;
                    if (menuSel >= kNavCount) menuSel = kNavCount - 1;
                } else if (page == Page::Library) {
                    int n = static_cast<int>(libRows.size());
                    if (n > 0) {
                        // Galerie: Auf/Ab springt eine ganze Kachel-Reihe.
                        libSel += step * (libGallery ? 6 : 1);
                        if (libSel < 0) libSel = 0;
                        if (libSel >= n) libSel = n - 1;
                    }
                } else if (page == Page::Sources) {
                    srcSel += step;
                    if (srcSel < 0) srcSel = 0;
                    if (srcSel >= kSourceCount) srcSel = kSourceCount - 1;
                } else if (page == Page::Editor) {
                    int n = static_cast<int>(edLines.size());
                    if (n > 0) {
                        edSel += step;
                        if (edSel < 0) edSel = 0;
                        if (edSel >= n) edSel = n - 1;
                    }
                } else if (page == Page::Detail) {
                    if (detailExpanded) {
                        detailNameScroll += step;
                        if (detailNameScroll < 0) detailNameScroll = 0;
                    } else {
                        int n = static_cast<int>(detailBuilds.size());
                        if (n > 0) {
                            detailSel += step;
                            if (detailSel < 0) detailSel = 0;
                            if (detailSel >= n) detailSel = n - 1;
                        }
                    }
                } else if (page == Page::Settings) {
                    setSel += step;
                    if (setSel < 0) setSel = 0;
                    if (setSel >= kSetCount) setSel = kSetCount - 1;
                } else if (page == Page::Log) {
                    logScroll -= step; // hoch = aeltere Zeilen
                    if (logScroll < 0) logScroll = 0;
                } else if (page == Page::System) {
                    int n = static_cast<int>(uiTitles.size());
                    if (n > 0) {
                        sysSel += step;
                        if (sysSel < 0) sysSel = 0;
                        if (sysSel >= n) sysSel = n - 1;
                    }
                } else if (page == Page::SaveGames) {
                    int n = static_cast<int>(uiTitles.size());
                    if (n > 0) {
                        sgSel += step;
                        if (sgSel < 0) sgSel = 0;
                        if (sgSel >= n) sgSel = n - 1;
                    }
                } else if (page == Page::Saves) {
                    int n = static_cast<int>(curSaves(sysDetailTitle.titleId).size()) +
                            static_cast<int>(saveBackups.size());
                    if (n > 0) {
                        saveSel += step;
                        if (saveSel < 0) saveSel = 0;
                        if (saveSel >= n) saveSel = n - 1;
                    }
                    restoreArmed = false;
                }
            }
        }

        Uint32 nowTicks = SDL_GetTicks();
        if (static_cast<Sint32>(nowTicks - nextOnlineCheck) >= 0) {
            if (g_action.load() == Action::None) {
                g_online = updater::isInternetAvailable();
            }
            nextOnlineCheck = nowTicks + 5000;
        }

        // ------------------------------------------------------------------
        // Zeichnen
        // ------------------------------------------------------------------
        hits.clear();
        setColor(renderer, kColBg);
        SDL_RenderClear(renderer);

        Action curAction = g_action.load();
        busy = curAction != Action::None;
        db::Stats st = db::stats();

        // ---------------- Header ----------------
        fillRect(renderer, 0, 0, cfg::kScreenW, headerH, kColSidebar);
        fillRect(renderer, 0, headerH, cfg::kScreenW, 1, kColHairline);
        drawText(renderer, fontBody, "Switch Cheats", 28, 9, kColText);
        drawText(renderer, fontTiny, "Scraper & Downloader", 28, 38, kColAccent);
        // Versions-Chip
        {
            std::string v = std::string("v") + cfg::kAppVersion;
            int vw = textWidth(fontTiny, v) + 16;
            int vx = 28 + textWidth(fontBody, "Switch Cheats") + 18;
            fillRect(renderer, vx, 18, vw, 26, kColItemHover);
            drawTextCentered(renderer, fontTiny, v, vx + 8, 18, 26, kColAccent);
        }
        // rechts: Sprachkuerzel
        {
            std::string lang = i18n::langCode(i18n::getLang());
            drawTextRight(renderer, fontSmall, lang, cfg::kScreenW - 28, 22, kColTextMuted);
        }

        // ---------------- Sidebar ----------------
        fillRect(renderer, 0, headerH + 1, sidebarW, cfg::kScreenH - headerH - 1, kColSidebar);
        fillRect(renderer, sidebarW, headerH + 1, 1, cfg::kScreenH - headerH - 1, kColHairline);
        drawText(renderer, fontTiny, spaced(tr("nav.menu")), 28, headerH + 18, kColTextDim);

        for (int i = 0; i < kNavCount; i++) {
            int y = navStartY + i * (navItemH + 4);
            bool active = menuFocus
                ? (i == menuSel)   // Menue-Fokus: der Cursor bestimmt das Highlight
                : ((kNav[i].page == page) ||
                   ((page == Page::Detail || page == Page::Editor) &&
                    kNav[i].page == Page::Library) ||
                   ((page == Page::SysDetail || page == Page::Saves) &&
                    kNav[i].page == Page::System));
            // Aktive Zeile = EIN durchgehendes Rechteck + Akzentbalken links
            // (exakt der gefixte Windows-Look).
            if (active) {
                fillRect(renderer, 0, y, sidebarW, navItemH, kColItemHover);
                fillRect(renderer, 0, y, menuFocus ? 7 : 5, navItemH, kColAccent);
                if (menuFocus)   // Fokus-Hinweis: der Cursor sitzt im linken Menue
                    drawTextCentered(renderer, fontBody, ">", sidebarW - 30, y, navItemH,
                                     kColAccent);
            }
            drawTextCentered(renderer, fontBody, tr(kNav[i].labelKey), 32, y, navItemH,
                             active ? kColAccent : kColTextMuted);
            // Badge: Spielezahl an "Bibliothek" (Pille) - wie am Desktop.
            if (kNav[i].page == Page::Library && st.games > 0) {
                char nbuf[32];
                snprintf(nbuf, sizeof(nbuf), "%d", st.games);
                int bw = textWidth(fontTiny, nbuf) + 16;
                int bx = sidebarW - bw - 18;
                int by = y + (navItemH - 24) / 2;
                fillRect(renderer, bx, by, bw, 24, active ? kColItem : kColItemHover);
                drawTextCentered(renderer, fontTiny, nbuf, bx + 8, by, 24, kColAccent);
            }
            HitBox hb;
            hb.rect = {0, y, sidebarW, navItemH};
            Page target = kNav[i].page;
            hb.fn = [&navTo, &menuFocus, target]() { navTo(target); menuFocus = false; };
            hits.push_back(hb);
        }
        drawText(renderer, fontTiny, "by DevCatSKZ", 28, cfg::kScreenH - footerH - 30, kColTextDim);

        // ---------------- Seitenkopf ----------------
        const NavEntry* nav = &kNav[0];
        Page headPage = (page == Page::Detail || page == Page::Editor) ? Page::Library
                      : (page == Page::SysDetail || page == Page::Saves) ? Page::System
                      : page;
        for (int i = 0; i < kNavCount; i++) {
            if (kNav[i].page == headPage) nav = &kNav[i];
        }
        int cy = headerH + 20;
        if (page != Page::Detail && page != Page::Editor &&
            page != Page::SysDetail && page != Page::Saves) {
            drawText(renderer, fontTiny, std::string("\xe2\x80\x94  ") + spaced(tr(nav->eyebrowKey)),
                     contentX, cy, kColAccent);
            cy += 26;
            drawText(renderer, fontTitle, tr(nav->labelKey), contentX, cy, kColText);
            cy += 42;
            drawText(renderer, fontSmall, tr(nav->subKey), contentX, cy, kColTextMuted);
            cy += 30;
            fillRect(renderer, contentX, cy, contentW, 1, kColHairline);
            cy += 18;
        }

        // ------------------------------------------------------------------
        // Seite: START (Dashboard + Komplett-Download)
        // ------------------------------------------------------------------
        if (page == Page::Home) {
            // Stat-Karten (Spiele / Cheats / Installiert / DB-Groesse)
            int cardGap = 14;
            int cardW = (contentW - 3 * cardGap) / 4;
            int cardH = 80;
            struct StatDef { std::string value; const char* labelKey; SDL_Color col; };
            char instBuf[32];
            if (installer::scannedOnce()) {
                snprintf(instBuf, sizeof(instBuf), "%d", installer::installedFileCount());
            } else {
                snprintf(instBuf, sizeof(instBuf), "...");
            }
            char gbuf[32], cbuf[32];
            snprintf(gbuf, sizeof(gbuf), "%d", st.games);
            snprintf(cbuf, sizeof(cbuf), "%lld", st.cheats);
            StatDef defs[4] = {
                {st.games ? gbuf : "\xe2\x80\x94", "stat.games", kColAccent},
                {st.cheats ? cbuf : "\xe2\x80\x94", "stat.cheats", kColAccent},
                {instBuf, "stat.installed", kColAccent},
                {st.dbSizeBytes ? formatBytes(st.dbSizeBytes) : "\xe2\x80\x94", "stat.dbsize", kColAccent2},
            };
            for (int i = 0; i < 4; i++) {
                int x = contentX + i * (cardW + cardGap);
                drawCard(renderer, x, cy, cardW, cardH);
                fillRect(renderer, x + 16, cy + 14, 26, 3, defs[i].col);
                drawText(renderer, fontStat, defs[i].value, x + 16, cy + 20, defs[i].col);
                drawText(renderer, fontTiny, tr(defs[i].labelKey), x + 16, cy + 58, kColTextMuted);
            }
            cy += cardH + 14;

            // Uhr-Warnung (falsche Systemzeit -> SSL-Fehler)
            if (time(nullptr) < kMinSaneEpoch) {
                drawText(renderer, fontSmall, tr("clock.warn"), contentX, cy, kColError);
                cy += 30;
            }

            // Linke Karte: "Alles holen" | rechte Karte: Zuletzt aktualisiert
            int leftW = (contentW - 16) * 60 / 100;
            int rightW = contentW - 16 - leftW;
            int cardsY = cy;
            int cardsH = cfg::kScreenH - footerH - cardsY - 14;
            drawCard(renderer, contentX, cardsY, leftW, cardsH);
            drawCard(renderer, contentX + leftW + 16, cardsY, rightW, cardsH);

            int lx = contentX + 20;
            int ly = cardsY + 16;
            int lTextW = leftW - 40;
            // Oberkante des Button-Blocks (2 Reihen) - Statuszeilen duerfen NIE
            // darunter laufen.
            int btnHh = 46, btnGapp = 10;
            int stateLimit = cardsY + cardsH - 14 - btnHh - btnGapp - btnHh - 6;
            // Titel + Beschreibung VOLLSTAENDIG per Wortumbruch (kein "..." mehr).
            for (const auto& tl : wrapText(fontBody, tr("home.card.title"), lTextW)) {
                drawText(renderer, fontBody, tl, lx, ly, kColGold);
                ly += 28;
            }
            ly += 4;
            for (const auto& dl2 : wrapText(fontSmall, tr("home.card.desc"), lTextW)) {
                drawText(renderer, fontSmall, dl2, lx, ly, kColTextMuted);
                ly += 24;
            }
            ly += 8;
            // Ab hier nur zeichnen, was ueber dem Button-Block Platz hat.
            auto stateLine = [&](const std::string& t, SDL_Color c, int adv) {
                if (ly + 22 <= stateLimit) { drawText(renderer, fontSmall, t, lx, ly, c); ly += adv; }
            };

            std::string remoteAt, localAt, dbLocalAt, resultMsg;
            long long remoteSize = 0;
            bool updateAvail = false, haveRemote = false, resultOk = false, haveResult = false;
            {
                std::lock_guard<std::mutex> lk(g_dataMutex);
                remoteAt = g_remoteUpdatedAt;
                localAt = g_localUpdatedAt;
                dbLocalAt = g_dbLocalUpdatedAt;
                remoteSize = g_remoteSizeBytes;
                updateAvail = g_updateAvailable;
                haveRemote = g_haveRemoteInfo;
                resultMsg = g_resultLine;
                resultOk = g_resultSuccess;
                haveResult = g_haveResult;
            }

            stateLine(std::string(tr("check.local")) +
                (localAt.empty() ? tr("check.never") : localAt), kColTextMuted, 24);
            stateLine(std::string(tr("home.dbstate")) +
                (dbLocalAt.empty() ? tr("check.never") : dbLocalAt), kColTextMuted, 24);
            if (haveRemote) {
                std::string remoteLine = std::string(tr("check.remote")) + remoteAt;
                if (remoteSize > 0) remoteLine += "  (" + formatBytes(remoteSize) + ")";
                stateLine(remoteLine, kColTextMuted, 24);
                stateLine(updateAvail ? tr("check.available") : tr("check.uptodate"),
                          updateAvail ? kColGold : kColSuccess, 28);
            }

            if (curAction == Action::Installing) {
                long long done = g_bytesDone.load(), total = g_bytesTotal.load();
                int zi = g_zipIndex.load(), zt = g_zipTotal.load();
                if (zt > 0) {
                    double frac = (double)zi / (double)zt;
                    drawText(renderer, fontSmall, tr("install.extract"), lx, ly, kColText);
                    ly += 28;
                    drawProgressBar(renderer, lx, ly, leftW - 40, 24, frac, kColAccent);
                    ly += 34;
                    drawText(renderer, fontTiny,
                        std::to_string(zi) + " / " + std::to_string(zt) + tr("install.filesSuffix"),
                        lx, ly, kColTextMuted);
                } else if (total > 0) {
                    double frac = (double)done / (double)total;
                    drawText(renderer, fontSmall, tr("install.download"), lx, ly, kColText);
                    ly += 28;
                    drawProgressBar(renderer, lx, ly, leftW - 40, 24, frac, kColAccent);
                    ly += 34;
                    drawText(renderer, fontTiny, formatBytes(done) + " / " + formatBytes(total),
                             lx, ly, kColTextMuted);
                } else {
                    drawText(renderer, fontSmall, getStatus(), lx, ly, kColAccent);
                }
            } else if (curAction == Action::Checking) {
                drawText(renderer, fontSmall, getStatus(), lx, ly, kColAccent);
            } else if (haveResult) {
                drawText(renderer, fontSmall, truncated(fontSmall, resultMsg, leftW - 40),
                         lx, ly, resultOk ? kColSuccess : kColError);
            }

            // Buttons: A = Komplett holen (DB + Cheats), X = Nur Cheats (das
            // schlanke v1-Verhalten: nur switch-cheats.zip), Y = Pruefen.
            int btnH = 46;
            int gap2 = 10;
            int interiorW = leftW - 40;
            int btnY = cardsY + cardsH - btnH - 14;   // untere Reihe (sekundaer)
            int btnYtop = btnY - btnH - gap2;         // obere Reihe (primaer)
            if (busy) {
                std::string cl = std::string("B  ") + tr("btn.cancel");
                fillRect(renderer, lx, btnY, interiorW, btnH, kColItem);
                drawRectOutline(renderer, lx, btnY, interiorW, btnH, kColHairline);
                drawTextCentered(renderer, fontSmall, cl,
                                 lx + (interiorW - textWidth(fontSmall, cl)) / 2, btnY, btnH, kColText);
                HitBox hb;
                hb.rect = {lx, btnY, interiorW, btnH};
                hb.fn = []() { g_cancelRequested = true; };
                hits.push_back(hb);
            } else {
                // Primaer (oben, volle Breite): Komplett holen
                drawGradientRectH(renderer, lx, btnYtop, interiorW, btnH, kColAccent, kColAccent2);
                std::string lbl = std::string("A  ") + tr("home.btn.getall");
                drawTextCentered(renderer, fontSmall, lbl,
                                 lx + (interiorW - textWidth(fontSmall, lbl)) / 2, btnYtop, btnH, kColOnAccent);
                HitBox hbA;
                hbA.rect = {lx, btnYtop, interiorW, btnH};
                hbA.fn = []() { startInstall(true); };
                hits.push_back(hbA);

                // Sekundaer (unten): Nur Cheats | Pruefen
                int halfW = (interiorW - gap2) / 2;
                std::string lblX = std::string("X  ") + tr("home.btn.cheatsonly");
                fillRect(renderer, lx, btnY, halfW, btnH, kColItem);
                drawRectOutline(renderer, lx, btnY, halfW, btnH, kColHairline);
                drawTextCentered(renderer, fontSmall, lblX,
                                 lx + (halfW - textWidth(fontSmall, lblX)) / 2, btnY, btnH, kColText);
                HitBox hbX;
                hbX.rect = {lx, btnY, halfW, btnH};
                hbX.fn = []() { startInstall(false); };
                hits.push_back(hbX);

                int b2x = lx + halfW + gap2;
                std::string lbl2 = std::string("Y  ") + tr("btn.check");
                fillRect(renderer, b2x, btnY, halfW, btnH, kColItem);
                drawRectOutline(renderer, b2x, btnY, halfW, btnH, kColHairline);
                drawTextCentered(renderer, fontSmall, lbl2,
                                 b2x + (halfW - textWidth(fontSmall, lbl2)) / 2, btnY, btnH, kColText);
                HitBox hb2;
                hb2.rect = {b2x, btnY, halfW, btnH};
                hb2.fn = []() { startCheck(); };
                hits.push_back(hb2);
            }

            // Rechte Karte: Zuletzt aktualisiert
            int rx = contentX + leftW + 16 + 20;
            int ry = cardsY + 16;
            drawText(renderer, fontBody, tr("home.recent"), rx, ry, kColText);
            ry += 30;
            fillRect(renderer, rx, ry, rightW - 40, 1, kColHairline);
            ry += 12;
            auto rec = db::recent(9);
            if (rec.empty()) {
                drawText(renderer, fontSmall, tr("home.norecent"), rx, ry, kColTextMuted);
            } else {
                for (const auto* g : rec) {
                    if (ry > cardsY + cardsH - 34) break;
                    drawText(renderer, fontSmall,
                             truncated(fontSmall, g->title, rightW - 140), rx, ry, kColTextMuted);
                    char nb[32];
                    snprintf(nb, sizeof(nb), "%lld", g->cheats);
                    drawTextRight(renderer, fontSmall, nb, contentX + leftW + 16 + rightW - 20, ry, kColTextDim);
                    ry += 30;
                }
            }
        }

        // ------------------------------------------------------------------
        // Seite: BIBLIOTHEK
        // ------------------------------------------------------------------
        else if (page == Page::Library) {
            // Suche + Filter-Chips
            int chipY = cy;
            std::string searchLbl = libQuery.empty()
                ? std::string("Y  ") + tr("lib.search")
                : std::string(tr("lib.search.prefix")) + libQuery + "  (Y)";
            int searchW = textWidth(fontSmall, searchLbl) + 28;
            fillRect(renderer, contentX, chipY, searchW, 36, kColItem);
            drawRectOutline(renderer, contentX, chipY, searchW, 36,
                            libQuery.empty() ? kColHairline : kColAccent);
            drawTextCentered(renderer, fontSmall, searchLbl, contentX + 14, chipY, 36,
                             libQuery.empty() ? kColTextMuted : kColAccent);
            {
                HitBox hb;
                hb.rect = {contentX, chipY, searchW, 36};
                hb.fn = [&]() { doSearch(); };
                hits.push_back(hb);
            }

            int fx = contentX + searchW + 14;
            for (int f = 0; f < static_cast<int>(LibFilter::Count); f++) {
                std::string lbl = filterLabel(static_cast<LibFilter>(f));
                bool cur = f == static_cast<int>(libFilter);
                int w = textWidth(fontSmall, lbl) + 26;
                fillRect(renderer, fx, chipY, w, 36, cur ? kColItemHover : kColItem);
                drawRectOutline(renderer, fx, chipY, w, 36, cur ? kColAccent : kColHairline);
                drawTextCentered(renderer, fontSmall, lbl, fx + 13, chipY, 36,
                                 cur ? kColText : kColTextMuted);
                HitBox hb;
                hb.rect = {fx, chipY, w, 36};
                hb.fn = [&, f]() {
                    libFilter = static_cast<LibFilter>(f);
                    libSel = 0;
                    libScroll = 0;
                    libDirty = true;
                };
                hits.push_back(hb);
                fx += w + 10;
            }
            // Trefferzahl rechts
            {
                char nb[64];
                snprintf(nb, sizeof(nb), "%d%s", static_cast<int>(libRows.size()),
                         tr("lib.games.suffix"));
                drawTextRight(renderer, fontSmall, nb, contentX + contentW, chipY + 8, kColTextDim);
            }
            cy = chipY + 48;

            if (libGallery) {
                // ---- Galerie-Ansicht (Minus wechselt Tabelle/Galerie) ------
                int n = static_cast<int>(libRows.size());
                const int gcols = 6;
                int gap = 12;
                int tileW = (contentW - (gcols - 1) * gap) / gcols;
                int imgH = tileW;
                int tileH = imgH + 44;
                int visRowsG = (cfg::kScreenH - footerH - cy - 8 + gap) / (tileH + gap);
                if (visRowsG < 1) visRowsG = 1;
                if (!db::loaded() || n == 0) {
                    drawText(renderer, fontSmall, db::loading() ? tr("app.loading") : tr("lib.nodb"),
                             contentX + 8, cy + 24, kColTextMuted);
                } else {
                    int selRow = libSel / gcols;
                    int firstRow = libScroll;
                    if (selRow < firstRow) firstRow = selRow;
                    if (selRow >= firstRow + visRowsG) firstRow = selRow - visRowsG + 1;
                    if (firstRow < 0) firstRow = 0;
                    libScroll = firstRow;
                    for (int vi = 0; vi < visRowsG; vi++) {
                        int row = firstRow + vi;
                        for (int c2 = 0; c2 < gcols; c2++) {
                            int idx = row * gcols + c2;
                            if (idx >= n) break;
                            const auto& g = db::games()[libRows[idx]];
                            int x = contentX + c2 * (tileW + gap);
                            int y = cy + vi * (tileH + gap);
                            bool sel = idx == libSel;
                            drawCard(renderer, x, y, tileW, tileH, sel ? kColItemHover : kColPanel,
                                     sel ? kColAccent : kColHairline);
                            // Cover nur fuer SICHTBARE Kacheln anfordern (Lazy-Load
                            // wie die Windows-Galerie).
                            covers::request(g.baseTid, g.image);
                            int cw = 0, ch = 0;
                            SDL_Texture* tex = covers::get(renderer, g.baseTid, cw, ch);
                            SDL_Rect imgRect{x + 4, y + 4, tileW - 8, imgH - 8};
                            if (tex) {
                                SDL_RenderCopy(renderer, tex, nullptr, &imgRect);
                            } else {
                                fillRect(renderer, imgRect.x, imgRect.y, imgRect.w, imgRect.h, kColItem);
                                std::string ini = g.title.empty() ? "?" : g.title.substr(0, 1);
                                int iw = textWidth(fontStat, ini);
                                drawText(renderer, fontStat, ini, x + (tileW - iw) / 2,
                                         y + imgH / 2 - 22, kColTextDim);
                            }
                            std::string nm = g.title.empty() ? tr("lib.unnamed") : g.title;
                            drawText(renderer, fontTiny, truncated(fontTiny, nm, tileW - 12),
                                     x + 6, y + imgH + 2, sel ? kColText : kColTextMuted);
                            char cbuf2[32];
                            snprintf(cbuf2, sizeof(cbuf2), "%lld", g.cheats);
                            drawText(renderer, fontTiny,
                                     std::string(cbuf2) + tr("gal.cheats.suffix"),
                                     x + 6, y + imgH + 22, kColTextDim);
                            HitBox hb;
                            hb.rect = {x, y, tileW, tileH};
                            hb.fn = [&, idx]() {
                                if (libSel == idx) openDetail(db::games()[libRows[idx]]);
                                else libSel = idx;
                            };
                            hits.push_back(hb);
                        }
                    }
                }
            } else {
            // Spaltenkoepfe
            int colTitleX = contentX + 12;
            int colRegionX = contentX + contentW - 330;
            int colBuildsX = contentX + contentW - 190;
            int colCheatsX = contentX + contentW - 120;
            int colInstX = contentX + contentW - 40;
            drawText(renderer, fontTiny, tr("lib.col.game"), colTitleX, cy, kColTextDim);
            drawText(renderer, fontTiny, tr("lib.col.region"), colRegionX, cy, kColTextDim);
            drawTextRight(renderer, fontTiny, tr("lib.col.builds"), colBuildsX + 40, cy, kColTextDim);
            drawTextRight(renderer, fontTiny, tr("lib.col.cheats"), colCheatsX + 46, cy, kColTextDim);
            cy += 24;
            fillRect(renderer, contentX, cy, contentW, 1, kColHairline);
            cy += 4;

            int rowH = 40;
            int visRows = (cfg::kScreenH - footerH - cy - 8) / rowH;
            if (visRows < 1) visRows = 1;
            int n = static_cast<int>(libRows.size());

            if (!db::loaded() || n == 0) {
                std::string msg = db::loading() ? tr("app.loading")
                                 : !db::loaded() ? tr("lib.nodb")
                                 : (libQuery.empty() && libFilter == LibFilter::All)
                                       ? tr("lib.nodb")
                                       : tr("lib.noresults");
                drawText(renderer, fontSmall, msg, contentX + 8, cy + 24, kColTextMuted);
            } else {
                if (libSel < libScroll) libScroll = libSel;
                if (libSel >= libScroll + visRows) libScroll = libSel - visRows + 1;
                if (libScroll < 0) libScroll = 0;

                for (int vi = 0; vi < visRows; vi++) {
                    int idx = libScroll + vi;
                    if (idx >= n) break;
                    const auto& g = db::games()[libRows[idx]];
                    int y = cy + vi * rowH;
                    bool sel = idx == libSel;
                    if (sel) {
                        fillRect(renderer, contentX, y, contentW, rowH - 2, kColItemHover);
                        fillRect(renderer, contentX, y, 4, rowH - 2, kColAccent);
                    }
                    std::string title = g.title.empty() ? tr("lib.unnamed") : g.title;
                    bool fav = settings::isFavorite(g.baseTid);
                    int tx = colTitleX + (sel ? 6 : 0);
                    if (fav) {
                        drawTextCentered(renderer, fontSmall, "\xe2\x98\x85", tx, y, rowH - 2, kColGold);
                        tx += 26;
                    }
                    drawTextCentered(renderer, fontSmall,
                                     truncated(fontSmall, title, colRegionX - tx - 16),
                                     tx, y, rowH - 2, sel ? kColText : kColTextMuted);
                    drawTextCentered(renderer, fontTiny,
                                     truncated(fontTiny, g.region, 128),
                                     colRegionX, y, rowH - 2, kColTextDim);
                    char bb[16], cb[16];
                    snprintf(bb, sizeof(bb), "%d", g.builds);
                    snprintf(cb, sizeof(cb), "%lld", g.cheats);
                    int tw = textWidth(fontTiny, bb);
                    drawTextCentered(renderer, fontTiny, bb, colBuildsX + 40 - tw, y, rowH - 2, kColTextMuted);
                    tw = textWidth(fontTiny, cb);
                    drawTextCentered(renderer, fontTiny, cb, colCheatsX + 46 - tw, y, rowH - 2, kColAccent);
                    if (installer::scannedOnce() && installer::anyInstalled(g.pairs)) {
                        drawCheckmark(renderer, colInstX + 8, y + (rowH - 2) / 2, 14, kColSuccess);
                    }
                    HitBox hb;
                    hb.rect = {contentX, y, contentW, rowH - 2};
                    hb.fn = [&, idx]() {
                        if (libSel == idx) {
                            openDetail(db::games()[libRows[idx]]);
                        } else {
                            libSel = idx;
                        }
                    };
                    hits.push_back(hb);
                }

                // Duenne Scroll-Anzeige rechts
                if (n > visRows) {
                    int trackY = cy;
                    int trackH = visRows * rowH - 2;
                    fillRect(renderer, contentX + contentW + 8, trackY, 4, trackH, kColItem);
                    int thumbH = trackH * visRows / n;
                    if (thumbH < 24) thumbH = 24;
                    int thumbY = trackY + (trackH - thumbH) * libScroll / (n - visRows > 0 ? n - visRows : 1);
                    fillRect(renderer, contentX + contentW + 8, thumbY, 4, thumbH, kColAccent);
                }
            }
            } // Ende Tabellen-Ansicht
        }

        // ------------------------------------------------------------------
        // Seite: QUELLEN (Community-Archive -> direkt auf die SD)
        // ------------------------------------------------------------------
        else if (page == Page::Sources) {
            int runningIdx = g_sourceRunning.load();
            // Ergebnis-/Notizzeile UNTEN reservieren, Karten scrollen dazwischen.
            int noteH = 26;
            int listBottom = cfg::kScreenH - footerH - noteH - 12;
            int cardH = 76;
            int cardGap = 10;
            int visCards = (listBottom - cy) / (cardH + cardGap);
            if (visCards < 1) visCards = 1;
            if (srcSel < srcScroll) srcScroll = srcSel;
            if (srcSel >= srcScroll + visCards) srcScroll = srcSel - visCards + 1;
            if (srcScroll < 0) srcScroll = 0;

            int listTop = cy;
            for (int vi = 0; vi < visCards; vi++) {
                int i = srcScroll + vi;
                if (i >= kSourceCount) break;
                int y = listTop + vi * (cardH + cardGap);
                bool sel = i == srcSel;
                bool running = runningIdx == i;
                drawCard(renderer, contentX, y, contentW, cardH,
                         sel ? kColItemHover : kColPanel,
                         sel ? kColAccent : kColHairline);
                std::string nameKey = "src." + std::string(kSources[i].key) + ".name";
                std::string descKey = "src." + std::string(kSources[i].key) + ".desc";
                drawText(renderer, fontBody, tr(nameKey.c_str()), contentX + 18, y + 10, kColText);
                drawText(renderer, fontTiny, truncated(fontTiny, tr(descKey.c_str()), contentW - 280),
                         contentX + 18, y + 44, kColTextDim);
                drawTextRight(renderer, fontTiny, kSources[i].repo,
                              contentX + contentW - 18, y + 12, kColTextDim);
                if (running) {
                    long long done = g_bytesDone.load(), total = g_bytesTotal.load();
                    int zi = g_zipIndex.load(), zt = g_zipTotal.load();
                    double frac = zt > 0 ? (double)zi / (double)zt
                                 : (total > 0 ? (double)done / (double)total : 0);
                    drawProgressBar(renderer, contentX + contentW - 240, y + 42, 222, 16,
                                    frac, kColAccent);
                }
                HitBox hb;
                hb.rect = {contentX, y, contentW, cardH};
                hb.fn = [&, i]() {
                    if (srcSel == i && !busy) startSource(i);
                    else srcSel = i;
                };
                hits.push_back(hb);
            }
            // Scroll-Indikator
            if (kSourceCount > visCards) {
                int trackH = visCards * (cardH + cardGap) - cardGap;
                fillRect(renderer, contentX + contentW + 8, listTop, 4, trackH, kColItem);
                int thumbH = trackH * visCards / kSourceCount;
                if (thumbH < 24) thumbH = 24;
                int thumbY = listTop + (trackH - thumbH) * srcScroll /
                             (kSourceCount - visCards > 0 ? kSourceCount - visCards : 1);
                fillRect(renderer, contentX + contentW + 8, thumbY, 4, thumbH, kColAccent);
            }
            // Ergebnis-/Notizzeile ganz unten
            int noteY = cfg::kScreenH - footerH - noteH - 4;
            std::string resultMsg;
            bool resultOk = false, haveResult2 = false;
            {
                std::lock_guard<std::mutex> lk(g_dataMutex);
                resultMsg = g_resultLine;
                resultOk = g_resultSuccess;
                haveResult2 = g_haveResult;
            }
            if (!busy && haveResult2 && !resultMsg.empty()) {
                drawText(renderer, fontSmall, truncated(fontSmall, resultMsg, contentW),
                         contentX, noteY, resultOk ? kColSuccess : kColError);
            } else {
                drawText(renderer, fontTiny, truncated(fontTiny, tr("src.note"), contentW),
                         contentX, noteY + 3, kColTextDim);
            }
        }

        // ------------------------------------------------------------------
        // Seite: CHEATSLIPS (API-Token + Anleitung)
        // ------------------------------------------------------------------
        else if (page == Page::CheatSlips) {
            // Token-Karte
            int cardH = 120;
            drawCard(renderer, contentX, cy, contentW, cardH, kColPanel, kColAccent);
            drawText(renderer, fontBody, tr("cs.token.title"), contentX + 20, cy + 12, kColText);
            bool hasTok = cheatslips::hasToken();
            std::string tokLine;
            if (hasTok) {
                std::string t2 = cheatslips::token();
                std::string masked = t2.size() > 8 ? t2.substr(0, 4) + "..." + t2.substr(t2.size() - 4)
                                                   : std::string("****");
                tokLine = std::string(tr("cs.token.set")) + masked;
            } else {
                tokLine = tr("cs.token.none");
            }
            drawText(renderer, fontSmall, tokLine, contentX + 20, cy + 48,
                     hasTok ? kColSuccess : kColGold);
            drawText(renderer, fontTiny, tr("cs.token.hint"), contentX + 20, cy + 84, kColTextDim);
            {
                HitBox hb;
                hb.rect = {contentX, cy, contentW, cardH};
                hb.fn = [&]() {
                    std::string out;
                    if (showKeyboard(tr("cs.token.header"), cheatslips::token(), out)) {
                        cheatslips::setToken(out);
                        applog::add(out.empty() ? tr("cs.token.cleared") : tr("cs.token.saved"));
                    }
                };
                hits.push_back(hb);
            }
            cy += cardH + 14;

            // Anleitung
            drawCard(renderer, contentX, cy, contentW, 150);
            drawText(renderer, fontBody, tr("cs.how.title"), contentX + 20, cy + 12, kColText);
            drawText(renderer, fontSmall, tr("cs.how.1"), contentX + 20, cy + 48, kColTextMuted);
            drawText(renderer, fontSmall, tr("cs.how.2"), contentX + 20, cy + 76, kColTextMuted);
            drawText(renderer, fontSmall, tr("cs.how.3"), contentX + 20, cy + 104, kColTextMuted);
            cy += 150 + 14;

            drawText(renderer, fontTiny, tr("cs.note"), contentX, cy, kColTextDim);
        }

        // ------------------------------------------------------------------
        // Seite: SPIEL-DETAIL
        // ------------------------------------------------------------------
        else if (page == Page::Detail) {
            int dy = headerH + 20;
            drawText(renderer, fontTiny, std::string("B  ") + tr("game.back"), contentX, dy, kColTextDim);
            {
                HitBox hb;
                hb.rect = {contentX, dy - 6, 220, 30};
                hb.fn = [&]() { page = pageBeforeDetail; };
                hits.push_back(hb);
            }
            dy += 26;
            drawText(renderer, fontTiny, std::string("\xe2\x80\x94  ") + spaced(tr("eyebrow.game")),
                     contentX, dy, kColAccent);
            dy += 24;
            drawText(renderer, fontTitle, truncated(fontTitle, detailTitle, contentW - 220),
                     contentX, dy, kColText);
            // Favoriten-Stern rechts neben Titel
            bool fav = settings::isFavorite(detailTid);
            drawTextRight(renderer, fontBody,
                          fav ? std::string("\xe2\x98\x85 X") : std::string("\xe2\x98\x86 X"),
                          contentX + contentW, dy + 6, fav ? kColGold : kColTextDim);
            dy += 40;

            // Meta-Zeile aus dem ersten Build mit Daten
            std::string metaLine;
            for (const auto& b : detailBuilds) {
                auto add = [&](const std::string& v) {
                    if (v.empty()) return;
                    if (!metaLine.empty()) metaLine += "  \xc2\xb7  ";
                    metaLine += v;
                };
                if (metaLine.empty()) {
                    add(b.publisher);
                    add(b.category);
                    add(b.releaseDate);
                    add(b.region);
                }
            }
            if (metaLine.empty()) metaLine = detailTid;
            drawText(renderer, fontSmall, truncated(fontSmall, metaLine, contentW), contentX, dy, kColTextMuted);
            dy += 28;
            fillRect(renderer, contentX, dy, contentW, 1, kColHairline);
            dy += 14;

            // Linke Fakten-Spalte
            int factsW = 280;
            int fy = dy;
            auto fact = [&](const char* key, const std::string& val) {
                if (val.empty()) return;
                drawText(renderer, fontTiny, tr(key), contentX, fy, kColTextDim);
                drawText(renderer, fontSmall, truncated(fontSmall, val, factsW - 8), contentX, fy + 18, kColTextMuted);
                fy += 48;
            };
            fact("game.titleid", detailTid);
            for (const auto& b : detailBuilds) {
                if (!b.players.empty()) { fact("game.players", b.players); break; }
            }
            for (const auto& b : detailBuilds) {
                if (!b.languages.empty()) { fact("game.languages", b.languages); break; }
            }
            for (const auto& b : detailBuilds) {
                if (!b.rating.empty()) { fact("game.rating", b.rating); break; }
            }
            {
                int inst = 0;
                for (const auto& b : detailBuilds) {
                    if (installer::isInstalled(b.titleId, b.buildId)) inst++;
                }
                char ib[64];
                snprintf(ib, sizeof(ib), "%d / %d%s", inst,
                         static_cast<int>(detailBuilds.size()), tr("game.installed.suffix"));
                fact("game.install.state", ib);
            }
            drawText(renderer, fontTiny, tr("game.hint"), contentX, cfg::kScreenH - footerH - 34, kColTextDim);

            // Rechte Spalte: Build-Karten
            int bx = contentX + factsW + 24;
            int bw = contentW - factsW - 24;
            char hbuf[64];
            snprintf(hbuf, sizeof(hbuf), "%d%s", static_cast<int>(detailBuilds.size()),
                     tr("game.builds.suffix"));
            drawText(renderer, fontBody, hbuf, bx, dy, kColText);
            int listY = dy + 36;
            int availH = cfg::kScreenH - footerH - listY - 8;

            int nB = static_cast<int>(detailBuilds.size());
            if (nB == 0) {
                drawText(renderer, fontSmall, tr("game.nobuilds"), bx, listY + 8, kColTextMuted);
            } else {
                int cardH2 = 64;
                int visCards = availH / (cardH2 + 8);
                if (visCards < 1) visCards = 1;
                if (detailSel < detailScroll) detailScroll = detailSel;
                if (detailSel >= detailScroll + visCards) detailScroll = detailSel - visCards + 1;

                int yy = listY;
                for (int vi = 0; vi < visCards; vi++) {
                    int idx = detailScroll + vi;
                    if (idx >= nB) break;
                    const auto& b = detailBuilds[idx];
                    bool sel = idx == detailSel;
                    bool inst = installer::isInstalled(b.titleId, b.buildId);

                    // Bei aufgeklapptem Zustand nimmt die gewaehlte Karte den
                    // restlichen Platz fuer die Cheat-Namen ein.
                    int hThis = cardH2;
                    if (sel && detailExpanded) {
                        hThis = availH - vi * (cardH2 + 8) - 4;
                        if (hThis < cardH2) hThis = cardH2;
                    }
                    drawCard(renderer, bx, yy, bw, hThis, sel ? kColItemHover : kColPanel,
                             sel ? kColAccent : kColHairline);
                    drawText(renderer, fontSmall, b.buildId, bx + 16, yy + 10, sel ? kColText : kColTextMuted);
                    std::string sub = b.source;
                    if (!b.version.empty()) sub = "v" + b.version + "  \xc2\xb7  " + sub;
                    char cc[64];
                    snprintf(cc, sizeof(cc), "  \xc2\xb7  %d Cheat(s)", b.cheatCount);
                    sub += cc;
                    drawText(renderer, fontTiny, truncated(fontTiny, sub, bw - 180), bx + 16, yy + 36, kColTextDim);
                    if (inst) {
                        std::string instLbl = tr("game.installed");
                        int ilw = textWidth(fontSmall, instLbl);
                        drawText(renderer, fontSmall, instLbl, bx + bw - 16 - ilw, yy + 10, kColSuccess);
                        drawCheckmark(renderer, bx + bw - 16 - ilw - 16, yy + 22, 13, kColSuccess);
                    }

                    if (sel && detailExpanded && hThis > cardH2 + 20) {
                        // Cheat-Namen aus der DB (cheat_names JSON)
                        auto itc = nameCache.find(b.buildId);
                        if (itc == nameCache.end()) {
                            itc = nameCache.emplace(b.buildId,
                                                    db::parseNameArray(b.cheatNamesJson)).first;
                        }
                        const auto& names = itc->second;
                        int ny = yy + 62;
                        fillRect(renderer, bx + 16, ny - 4, bw - 32, 1, kColHairline);
                        int maxLines = (yy + hThis - ny - 8) / 24;
                        if (maxLines < 1) maxLines = 1;
                        if (names.empty()) {
                            drawText(renderer, fontTiny, tr("game.cheats.none"), bx + 16, ny + 4, kColTextDim);
                        } else {
                            int total = static_cast<int>(names.size());
                            if (detailNameScroll > total - maxLines) detailNameScroll = total - maxLines;
                            if (detailNameScroll < 0) detailNameScroll = 0;
                            for (int li = 0; li < maxLines; li++) {
                                int niIdx = detailNameScroll + li;
                                if (niIdx >= total) break;
                                drawText(renderer, fontTiny,
                                         truncated(fontTiny, names[niIdx], bw - 60),
                                         bx + 24, ny + 4 + li * 24, kColTextMuted);
                            }
                            if (total > maxLines) {
                                char more[48];
                                snprintf(more, sizeof(more), "%d/%d", detailNameScroll + maxLines < total
                                             ? detailNameScroll + maxLines : total, total);
                                drawTextRight(renderer, fontTiny, more, bx + bw - 16, yy + hThis - 26, kColTextDim);
                            }
                        }
                    }

                    HitBox hb;
                    hb.rect = {bx, yy, bw, hThis};
                    hb.fn = [&, idx]() {
                        if (detailSel == idx) {
                            detailExpanded = !detailExpanded;
                            detailNameScroll = 0;
                        } else {
                            detailSel = idx;
                            detailExpanded = false;
                        }
                    };
                    hits.push_back(hb);

                    yy += hThis + 8;
                    if (sel && detailExpanded) break; // Rest ist verdeckt
                }
            }
        }

        // ------------------------------------------------------------------
        // Seite: CHEAT-EDITOR (ZR auf einem installierten Build)
        // ------------------------------------------------------------------
        else if (page == Page::Editor) {
            int dy = headerH + 20;
            drawText(renderer, fontTiny, std::string("B  ") + tr("ed.back"), contentX, dy, kColTextDim);
            dy += 26;
            drawText(renderer, fontTiny, std::string("\xe2\x80\x94  ") + spaced(tr("ed.eyebrow")),
                     contentX, dy, kColAccent);
            dy += 24;
            drawText(renderer, fontTitle, edBid + ".txt", contentX, dy, kColText);
            dy += 42;

            // Fehlerzaehler (Validierung wie der Windows-Editor)
            int errors = 0;
            for (const auto& l : edLines) {
                if (classifyCheatLine(l) == LineKind::Error) errors++;
            }
            char stat[160];
            snprintf(stat, sizeof(stat), "%d %s  \xc2\xb7  %d %s%s", static_cast<int>(edLines.size()),
                     tr("ed.lines"), errors, tr("ed.errors"), edDirty ? tr("ed.dirty") : "");
            drawText(renderer, fontSmall, stat, contentX, dy,
                     errors > 0 ? kColError : kColTextMuted);
            dy += 30;
            fillRect(renderer, contentX, dy, contentW, 1, kColHairline);
            dy += 8;

            int lineH = 28;
            int visLines = (cfg::kScreenH - footerH - dy - 8) / lineH;
            if (visLines < 1) visLines = 1;
            int n = static_cast<int>(edLines.size());
            if (edSel < edScroll) edScroll = edSel;
            if (edSel >= edScroll + visLines) edScroll = edSel - visLines + 1;
            if (edScroll < 0) edScroll = 0;

            for (int vi = 0; vi < visLines; vi++) {
                int idx = edScroll + vi;
                if (idx >= n) break;
                int y = dy + vi * lineH;
                bool sel = idx == edSel;
                if (sel) {
                    fillRect(renderer, contentX, y, contentW, lineH - 2, kColItemHover);
                    fillRect(renderer, contentX, y, 4, lineH - 2, kColAccent);
                }
                LineKind kind = classifyCheatLine(edLines[idx]);
                SDL_Color col = kColTextMuted;
                if (kind == LineKind::Header) col = kColGold;
                else if (kind == LineKind::Master) col = kColAccent2;
                else if (kind == LineKind::Error) col = kColError;
                else if (kind == LineKind::Code) col = kColText;
                char lno[16];
                snprintf(lno, sizeof(lno), "%3d", idx + 1);
                drawTextCentered(renderer, fontTiny, lno, contentX + 8, y, lineH - 2, kColTextDim);
                std::string shown = edLines[idx].empty() ? " " : edLines[idx];
                drawTextCentered(renderer, fontSmall,
                                 truncated(fontSmall, shown, contentW - 80),
                                 contentX + 52, y, lineH - 2, col);
                HitBox hb;
                hb.rect = {contentX, y, contentW, lineH - 2};
                hb.fn = [&, idx]() { edSel = idx; };
                hits.push_back(hb);
            }
        }

        // ------------------------------------------------------------------
        // Seite: EINSTELLUNGEN
        // ------------------------------------------------------------------
        else if (page == Page::Settings) {
            std::string appResultMsg, appRemoteVersion;
            bool appResultOk = false, appHaveResult = false, appChecked = false,
                 appAvailable = false, appJustInstalled = false;
            {
                std::lock_guard<std::mutex> lk(g_dataMutex);
                appResultMsg = g_appResultLine;
                appResultOk = g_appResultSuccess;
                appHaveResult = g_appHaveResult;
                appChecked = g_appChecked;
                appAvailable = g_appUpdateAvailable;
                appJustInstalled = g_appJustInstalled;
                appRemoteVersion = g_appRemoteVersion;
            }

            // -- Karte 1: Sprache ------------------------------------------
            int cardH1 = 88;
            drawCard(renderer, contentX, cy, contentW, cardH1,
                     kColPanel, setSel == 0 ? kColAccent : kColHairline);
            drawText(renderer, fontBody, tr("set.section.lang"), contentX + 20, cy + 8, kColText);
            {
                int lbW = 96, lbH = 34;
                int lx2 = contentX + 20;
                int lyy = cy + 44;
                int cur = static_cast<int>(i18n::getLang());
                for (int i = 0; i < static_cast<int>(i18n::Lang::Count); i++) {
                    bool isCur = i == cur;
                    fillRect(renderer, lx2, lyy, lbW, lbH, isCur ? kColItemHover : kColItem);
                    drawRectOutline(renderer, lx2, lyy, lbW, lbH, isCur ? kColAccent : kColHairline);
                    std::string code = i18n::langCode(static_cast<i18n::Lang>(i));
                    drawTextCentered(renderer, fontSmall, code,
                                     lx2 + (lbW - textWidth(fontSmall, code)) / 2, lyy, lbH,
                                     isCur ? kColText : kColTextMuted);
                    HitBox hb;
                    hb.rect = {lx2, lyy, lbW, lbH};
                    hb.fn = [i]() { i18n::setLang(static_cast<i18n::Lang>(i)); };
                    hits.push_back(hb);
                    lx2 += lbW + 12;
                }
            }
            cy += cardH1 + 10;

            // -- Karte 2: App-Update ----------------------------------------
            int cardH2 = 92;
            drawCard(renderer, contentX, cy, contentW, cardH2,
                     kColPanel, setSel == 1 ? kColAccent : kColHairline);
            drawText(renderer, fontBody, tr("set.section.app"), contentX + 20, cy + 8, kColText);
            {
                std::lock_guard<std::mutex> lk(g_dataMutex);
                if (g_appUpdateAvailable) {
                    drawTextRight(renderer, fontSmall,
                                  std::string(tr("result.appUpdateAvailablePrefix")) + g_appRemoteVersion,
                                  contentX + contentW - 20, cy + 14, kColGold);
                }
            }
            {
                std::string line;
                SDL_Color col = kColTextMuted;
                if (curAction == Action::AppChecking || curAction == Action::AppInstalling) {
                    line = getStatus();
                    col = kColAccent;
                    long long done = g_bytesDone.load(), total = g_bytesTotal.load();
                    if (curAction == Action::AppInstalling && total > 0) {
                        drawProgressBar(renderer, contentX + 20, cy + 66, contentW - 300, 14,
                                        (double)done / (double)total, kColAccent);
                    }
                } else if (appHaveResult) {
                    line = appResultMsg;
                    col = appResultOk ? kColSuccess : kColError;
                    if (appChecked && appAvailable) {
                        drawText(renderer, fontTiny, tr("appupdate.pressAgain"),
                                 contentX + 20, cy + 64, kColAccent);
                    } else if (appJustInstalled) {
                        drawText(renderer, fontTiny, tr("appupdate.restartHint"),
                                 contentX + 20, cy + 64, kColAccent);
                    }
                } else {
                    line = std::string(tr("info.version")) + cfg::kAppVersion +
                           "  \xc2\xb7  A = " + tr("btn.check");
                }
                drawText(renderer, fontSmall, truncated(fontSmall, line, contentW - 60),
                         contentX + 20, cy + 38, col);
            }
            {
                HitBox hb;
                hb.rect = {contentX, cy, contentW, cardH2};
                hb.fn = [&]() {
                    setSel = 1;
                    if (!busy) {
                        bool checked, available;
                        {
                            std::lock_guard<std::mutex> lk(g_dataMutex);
                            checked = g_appChecked;
                            available = g_appUpdateAvailable;
                        }
                        if (checked && available) startAppInstall();
                        else startAppCheck();
                    }
                };
                hits.push_back(hb);
            }
            cy += cardH2 + 10;

            // -- Karte 3: Daten ---------------------------------------------
            int cardH3 = 62;
            drawCard(renderer, contentX, cy, contentW, cardH3,
                     kColPanel, setSel == 2 ? kColAccent : kColHairline);
            drawText(renderer, fontBody, tr("set.reload"), contentX + 20, cy + 6, kColText);
            drawText(renderer, fontTiny, tr("set.reload.desc"), contentX + 20, cy + 38, kColTextDim);
            {
                HitBox hb;
                hb.rect = {contentX, cy, contentW, cardH3};
                hb.fn = [&]() {
                    setSel = 2;
                    db::reload();
                    installer::startScan();
                    libDirty = true;
                    applog::add(tr("set.reload.done"));
                };
                hits.push_back(hb);
            }
            cy += cardH3 + 10;

            // -- Karte 4: Export (ZIP auf die SD-Wurzel) ----------------------
            int cardH4 = 62;
            drawCard(renderer, contentX, cy, contentW, cardH4,
                     kColPanel, setSel == 3 ? kColAccent : kColHairline);
            drawText(renderer, fontBody, tr("exp.title"), contentX + 20, cy + 6, kColText);
            if (curAction == Action::Export) {
                char eb[96];
                snprintf(eb, sizeof(eb), "%s  (%d)", tr("exp.running"), g_zipIndex.load());
                drawText(renderer, fontTiny, eb, contentX + 20, cy + 38, kColAccent);
            } else {
                drawText(renderer, fontTiny, tr("exp.desc"), contentX + 20, cy + 38, kColTextDim);
            }
            {
                HitBox hb;
                hb.rect = {contentX, cy, contentW, cardH4};
                hb.fn = [&]() {
                    setSel = 3;
                    if (!busy) startExport();
                };
                hits.push_back(hb);
            }
            cy += cardH4 + 10;

            // -- Karte 5: Saeubern (Cheats + Cover von der SD) ---------------
            int cardH5 = 62;
            drawCard(renderer, contentX, cy, contentW, cardH5,
                     kColPanel, setSel == 4 ? (cleanArmed ? kColError : kColAccent) : kColHairline);
            drawText(renderer, fontBody, tr("clean.title"), contentX + 20, cy + 6,
                     cleanArmed ? kColError : kColText);
            if (curAction == Action::Clean) {
                drawText(renderer, fontTiny, tr("clean.running"), contentX + 20, cy + 38, kColAccent);
            } else if (cleanArmed) {
                drawText(renderer, fontTiny, tr("clean.confirm"), contentX + 20, cy + 38, kColError);
            } else {
                drawText(renderer, fontTiny, tr("clean.desc"), contentX + 20, cy + 38, kColTextDim);
            }
            {
                HitBox hb;
                hb.rect = {contentX, cy, contentW, cardH5};
                hb.fn = [&]() {
                    if (setSel != 4) {
                        setSel = 4;
                        cleanArmed = false;
                    } else if (!busy) {
                        if (!cleanArmed) cleanArmed = true;
                        else { cleanArmed = false; startClean(); }
                    }
                };
                hits.push_back(hb);
            }
            cy += cardH5 + 10;

            // -- Info-Zeile ---------------------------------------------------
            drawText(renderer, fontTiny,
                     std::string(tr("info.source")) + "github.com/" + cfg::kRepoOwner + "/" + cfg::kRepoName +
                     "   \xc2\xb7   " + tr("info.target") + cfg::kSdRoot + " (Atmosphere)",
                     contentX, cy, kColTextDim);
        }

        // ------------------------------------------------------------------
        // Seite: SYSTEM (laufendes Spiel + installierte Spiele)
        // ------------------------------------------------------------------
        else if (page == Page::System) {
            // --- Karte: laufendes Spiel -------------------------------------
            int cardH = 118;
            drawCard(renderer, contentX, cy, contentW, cardH, kColPanel, kColHairline);
            int px = contentX + 20, py = cy + 14;
            drawText(renderer, fontTiny, spaced(tr("sys.running")), px, py, kColAccent);
            py += 24;
            if (uiRunning.running) {
                std::string nm = uiRunning.name.empty()
                    ? sysinfo::hex16(uiRunning.titleId) : uiRunning.name;
                drawText(renderer, fontBody, truncated(fontBody, nm, contentW - 240),
                         px, py, kColGold);
                py += 30;
                std::string l1 = std::string(tr("sys.tid")) + " " +
                                 sysinfo::hex16(uiRunning.titleId);
                if (!uiRunning.version.empty())
                    l1 += "    " + std::string(tr("sys.ver")) + " " + uiRunning.version;
                drawText(renderer, fontSmall, l1, px, py, kColTextMuted);
                py += 24;
                std::string bid = uiRunning.buildId.empty()
                    ? std::string(tr("sys.bid.unknown")) : uiRunning.buildId;
                drawText(renderer, fontSmall,
                         std::string(tr("sys.bid")) + " " + bid, px, py, kColText);
                bool has = titleHasCheats(uiRunning.titleId);
                drawTextRight(renderer, fontSmall,
                              has ? tr("sys.cheats.yes") : tr("sys.cheats.no"),
                              contentX + contentW - 20, cy + 40,
                              has ? kColSuccess : kColTextDim);
                if (has) {
                    drawTextRight(renderer, fontTiny, tr("sys.open.zr"),
                                  contentX + contentW - 20, cy + 70, kColAccent);
                    HitBox hb; hb.rect = {contentX, cy, contentW, cardH};
                    uint64_t tid = uiRunning.titleId;
                    hb.fn = [&, tid]() { openCheatsForTid(tid); };
                    hits.push_back(hb);
                }
            } else {
                drawText(renderer, fontBody, tr("sys.norunning"), px, py, kColTextMuted);
                py += 30;
                drawText(renderer, fontSmall, tr("sys.norunning.hint"), px, py, kColTextDim);
            }
            cy += cardH + 16;

            // --- Liste: installierte Spiele ---------------------------------
            char hdr[96];
            snprintf(hdr, sizeof(hdr), "%s (%d)", tr("sys.installed"),
                     static_cast<int>(uiTitles.size()));
            drawText(renderer, fontBody, hdr, contentX, cy, kColText);
            drawTextRight(renderer, fontTiny,
                          g_sysScanned.load() ? tr("sys.rescan") : tr("sys.scanhint"),
                          contentX + contentW, cy + 4, kColTextDim);
            cy += 34;
            fillRect(renderer, contentX, cy, contentW, 1, kColHairline);
            cy += 10;

            int rowH = 50;
            int listBottom = cfg::kScreenH - footerH - 12;
            int visible = (listBottom - cy) / rowH;
            if (visible < 1) visible = 1;
            int n = static_cast<int>(uiTitles.size());
            if (sysSel < sysScroll) sysScroll = sysSel;
            if (sysSel >= sysScroll + visible) sysScroll = sysSel - visible + 1;
            if (sysScroll < 0) sysScroll = 0;

            if (n == 0) {
                if (!busy && !sysinfo::isApplicationMode()) {
                    // Applet-Modus (Album-Start): ns/fs sind gesperrt. Klare
                    // Anleitung statt "keine Spiele" (sieht sonst wie ein Bug aus).
                    int wy = cy + 6;
                    drawText(renderer, fontBody, tr("sys.appmode.title"),
                             contentX + 4, wy, kColGold);
                    wy += 34;
                    for (const auto& wl : wrapText(fontSmall, tr("sys.appmode.hint"),
                                                   contentW - 8)) {
                        drawText(renderer, fontSmall, wl, contentX + 4, wy, kColTextMuted);
                        wy += 26;
                    }
                } else {
                    drawText(renderer, fontSmall, busy ? tr("sys.scanning") : tr("sys.empty"),
                             contentX + 4, cy + 8, kColTextMuted);
                }
            }
            for (int i = sysScroll; i < n && i < sysScroll + visible; i++) {
                int ry = cy + (i - sysScroll) * rowH;
                bool sel = (i == sysSel);
                if (sel) {
                    fillRect(renderer, contentX, ry, contentW, rowH - 6, kColItemHover);
                    fillRect(renderer, contentX, ry, 4, rowH - 6, kColAccent);
                }
                const auto& t = uiTitles[i];
                drawText(renderer, fontSmall, truncated(fontSmall, t.name, contentW - 270),
                         contentX + 16, ry + 5, sel ? kColText : kColTextMuted);
                std::string sub = sysinfo::hex16(t.titleId);
                if (!t.version.empty()) sub += "   v" + t.version;
                drawText(renderer, fontTiny, sub, contentX + 16, ry + 27, kColTextDim);
                if (titleHasCheats(t.titleId)) {
                    drawCheckmark(renderer, contentX + contentW - 128, ry + 18, 16, kColSuccess);
                    drawText(renderer, fontTiny, tr("sys.hascheats"),
                             contentX + contentW - 110, ry + 10, kColSuccess);
                }
                HitBox hb; hb.rect = {contentX, ry, contentW, rowH - 6};
                int idx = i; hb.fn = [&sysSel, idx]() { sysSel = idx; };
                hits.push_back(hb);
            }
        }

        // ------------------------------------------------------------------
        // Seite: SPEICHERSTAENDE (installierte Spiele -> direkte Save-Verwaltung)
        // ------------------------------------------------------------------
        else if (page == Page::SaveGames) {
            char hdr[96];
            snprintf(hdr, sizeof(hdr), "%s (%d)", tr("sys.installed"),
                     static_cast<int>(uiTitles.size()));
            drawText(renderer, fontBody, hdr, contentX, cy, kColText);
            drawTextRight(renderer, fontTiny,
                          g_sysScanned.load() ? tr("sys.rescan") : tr("sys.scanhint"),
                          contentX + contentW, cy + 4, kColTextDim);
            cy += 34;
            fillRect(renderer, contentX, cy, contentW, 1, kColHairline);
            cy += 10;

            int rowH = 50;
            int listBottom = cfg::kScreenH - footerH - 12;
            int visible = (listBottom - cy) / rowH;
            if (visible < 1) visible = 1;
            int n = static_cast<int>(uiTitles.size());
            if (sgSel < sgScroll) sgScroll = sgSel;
            if (sgSel >= sgScroll + visible) sgScroll = sgSel - visible + 1;
            if (sgScroll < 0) sgScroll = 0;

            if (n == 0) {
                if (!busy && !sysinfo::isApplicationMode()) {
                    // Applet-Modus (Album-Start): ns/fs sind gesperrt. Klare
                    // Anleitung statt "keine Spiele" (sieht sonst wie ein Bug aus).
                    int wy = cy + 6;
                    drawText(renderer, fontBody, tr("sys.appmode.title"),
                             contentX + 4, wy, kColGold);
                    wy += 34;
                    for (const auto& wl : wrapText(fontSmall, tr("sys.appmode.hint"),
                                                   contentW - 8)) {
                        drawText(renderer, fontSmall, wl, contentX + 4, wy, kColTextMuted);
                        wy += 26;
                    }
                } else {
                    drawText(renderer, fontSmall, busy ? tr("sys.scanning") : tr("sys.empty"),
                             contentX + 4, cy + 8, kColTextMuted);
                }
            }
            for (int i = sgScroll; i < n && i < sgScroll + visible; i++) {
                int ry = cy + (i - sgScroll) * rowH;
                bool sel = (i == sgSel);
                if (sel) {
                    fillRect(renderer, contentX, ry, contentW, rowH - 6, kColItemHover);
                    fillRect(renderer, contentX, ry, 4, rowH - 6, kColAccent2);
                }
                const auto& t = uiTitles[i];
                drawText(renderer, fontSmall, truncated(fontSmall, t.name, contentW - 260),
                         contentX + 16, ry + 5, sel ? kColText : kColTextMuted);
                std::string sub = sysinfo::hex16(t.titleId);
                if (!t.version.empty()) sub += "   v" + t.version;
                drawText(renderer, fontTiny, sub, contentX + 16, ry + 27, kColTextDim);
                int nsv = static_cast<int>(curSaves(t.titleId).size());
                if (nsv > 0) {
                    char sm[48];
                    snprintf(sm, sizeof(sm), "%s: %d", tr("sys.saves"), nsv);
                    drawTextRight(renderer, fontTiny, sm,
                                  contentX + contentW - 16, ry + 14, kColSuccess);
                }
                HitBox hb; hb.rect = {contentX, ry, contentW, rowH - 6};
                int idx = i; hb.fn = [&sgSel, idx]() { sgSel = idx; };
                hits.push_back(hb);
            }
        }

        // ------------------------------------------------------------------
        // Seite: SYSTEM-DETAIL (ein installiertes Spiel + DB + Saves-Einstieg)
        // ------------------------------------------------------------------
        else if (page == Page::SysDetail) {
            drawText(renderer, fontTiny,
                     std::string("\xe2\x80\x94  ") + spaced(tr("sys.detail.eyebrow")),
                     contentX, cy, kColAccent);
            cy += 26;
            std::string nm = sysDetailTitle.name.empty()
                ? sysinfo::hex16(sysDetailTitle.titleId) : sysDetailTitle.name;
            drawText(renderer, fontTitle, truncated(fontTitle, nm, contentW),
                     contentX, cy, kColText);
            cy += 44;
            fillRect(renderer, contentX, cy, contentW, 1, kColHairline);
            cy += 16;

            int cardH = 156;
            drawCard(renderer, contentX, cy, contentW, cardH, kColPanel, kColHairline);
            int ix = contentX + 20, iy = cy + 16;
            auto infoRow = [&](const char* label, const std::string& val, SDL_Color c) {
                drawText(renderer, fontSmall, tr(label), ix, iy, kColTextDim);
                drawText(renderer, fontSmall, truncated(fontSmall, val, contentW - 230),
                         ix + 190, iy, c);
                iy += 32;
            };
            infoRow("sys.tid", sysinfo::hex16(sysDetailTitle.titleId), kColTextMuted);
            infoRow("sys.ver", sysDetailTitle.version.empty() ? "-" : sysDetailTitle.version,
                    kColTextMuted);
            infoRow("sys.author", sysDetailTitle.author.empty() ? "-" : sysDetailTitle.author,
                    kColTextMuted);
            bool has = titleHasCheats(sysDetailTitle.titleId);
            infoRow("sys.db", has ? tr("sys.db.yes") : tr("sys.db.no"),
                    has ? kColSuccess : kColTextDim);
            if (has)
                drawTextRight(renderer, fontTiny, tr("sys.open.zr"),
                              contentX + contentW - 20, cy + cardH - 28, kColAccent);
            cy += cardH + 16;

            // --- Build-ID(s) ---------------------------------------------
            // Live-Build-ID (laufendes Spiel, autoritativ per pm/ldr) + die aus
            // unserer Cheat-DB bekannten Build-IDs. Die Build-ID eines NICHT
            // laufenden Spiels laesst sich ohne Keys nicht von der Konsole lesen.
            uint64_t mask = 0xFFFFFFFFFFFFFFF0ULL;
            bool running = uiRunning.running &&
                (uiRunning.titleId & mask) == (sysDetailTitle.titleId & mask);
            int nb = static_cast<int>(sysDetailBuilds.size());
            int shown = nb > 3 ? 3 : nb;
            int bcardH = 34 + (running ? 28 : 0) + (shown > 0 ? shown * 26 : 26) + 12;
            drawCard(renderer, contentX, cy, contentW, bcardH, kColPanel, kColHairline);
            int bx = contentX + 20, by = cy + 12;
            drawText(renderer, fontTiny, spaced(tr("sys.bids")), bx, by, kColGold);
            by += 28;
            if (running) {
                std::string lb = uiRunning.buildId.empty()
                    ? std::string(tr("sys.bid.unknown")) : uiRunning.buildId;
                drawText(renderer, fontSmall,
                         std::string(tr("sys.bid.live")) + "  " + lb, bx, by, kColSuccess);
                by += 28;
            }
            if (nb == 0) {
                drawText(renderer, fontSmall, tr("sys.bid.none"), bx, by, kColTextDim);
            } else {
                for (int i = 0; i < shown; i++) {
                    const auto& b = sysDetailBuilds[i];
                    bool matchVer = !sysDetailTitle.version.empty() &&
                                    b.version == sysDetailTitle.version;
                    std::string line = b.buildId;
                    if (!b.version.empty()) line += "   v" + b.version;
                    char cc[40];
                    snprintf(cc, sizeof(cc), "   %d%s", b.cheatCount, tr("gal.cheats.suffix"));
                    line += cc;
                    drawText(renderer, fontSmall, truncated(fontSmall, line, contentW - 60),
                             bx, by, matchVer ? kColAccent : kColTextMuted);
                    by += 26;
                }
                if (nb > shown) {
                    char more[48];
                    snprintf(more, sizeof(more), "+%d %s", nb - shown, tr("sys.bid.more"));
                    drawTextRight(renderer, fontTiny, more,
                                  contentX + contentW - 20, cy + bcardH - 24, kColTextDim);
                }
            }
            cy += bcardH + 14;

            auto cs = curSaves(sysDetailTitle.titleId);
            int scardH = 96;
            drawCard(renderer, contentX, cy, contentW, scardH, kColPanel, kColHairline);
            drawText(renderer, fontTiny, spaced(tr("sys.saves")),
                     contentX + 20, cy + 14, kColAccent2);
            char sl[128];
            snprintf(sl, sizeof(sl), "%s: %d      %s: %d",
                     tr("sys.saves.users"), static_cast<int>(cs.size()),
                     tr("sys.saves.backups"), static_cast<int>(saveBackups.size()));
            drawText(renderer, fontSmall, sl, contentX + 20, cy + 40, kColTextMuted);
            drawText(renderer, fontTiny, tr("sys.saves.enter"),
                     contentX + 20, cy + 66, kColAccent);
            cy += scardH + 8;
        }

        // ------------------------------------------------------------------
        // Seite: SAVES (Backup erstellen / wiederherstellen / loeschen)
        // ------------------------------------------------------------------
        else if (page == Page::Saves) {
            drawText(renderer, fontTiny,
                     std::string("\xe2\x80\x94  ") + spaced(tr("sys.saves.eyebrow")),
                     contentX, cy, kColAccent2);
            cy += 26;
            std::string nm = sysDetailTitle.name.empty()
                ? sysinfo::hex16(sysDetailTitle.titleId) : sysDetailTitle.name;
            drawText(renderer, fontTitle, truncated(fontTitle, nm, contentW),
                     contentX, cy, kColText);
            cy += 44;
            fillRect(renderer, contentX, cy, contentW, 1, kColHairline);
            cy += 12;

            auto cs = curSaves(sysDetailTitle.titleId);
            int nUsers = static_cast<int>(cs.size());
            int total = nUsers + static_cast<int>(saveBackups.size());

            int rowH = 50;
            int listBottom = cfg::kScreenH - footerH - 12;
            int visible = (listBottom - cy) / rowH;
            if (visible < 1) visible = 1;
            if (saveSel < saveScroll) saveScroll = saveSel;
            if (saveSel >= saveScroll + visible) saveScroll = saveSel - visible + 1;
            if (saveScroll < 0) saveScroll = 0;

            if (total == 0) {
                drawText(renderer, fontSmall, busy ? getStatus() : tr("sys.saves.none"),
                         contentX + 4, cy + 8, kColTextMuted);
            }
            for (int i = saveScroll; i < total && i < saveScroll + visible; i++) {
                int ry = cy + (i - saveScroll) * rowH;
                bool sel = (i == saveSel);
                bool isBackup = (i >= nUsers);
                if (sel) {
                    SDL_Color hl = (isBackup && restoreArmed) ? kColError : kColItemHover;
                    fillRect(renderer, contentX, ry, contentW, rowH - 6, hl);
                    fillRect(renderer, contentX, ry, 4, rowH - 6,
                             isBackup ? kColGold : kColAccent);
                }
                if (!isBackup) {
                    const auto& e = cs[i];
                    std::string u = e.user.empty() ? std::string(tr("sys.saves.commonuser"))
                                                   : e.user;
                    drawText(renderer, fontSmall,
                             std::string(tr("sys.saves.backup")) + "   \xc2\xb7   " + u,
                             contentX + 16, ry + 5, sel ? kColText : kColAccent);
                    drawText(renderer, fontTiny, tr("sys.saves.backup.hint"),
                             contentX + 16, ry + 27, kColTextDim);
                } else {
                    const auto& b = saveBackups[i - nUsers];
                    drawText(renderer, fontSmall, b.label,
                             contentX + 16, ry + 5, sel ? kColText : kColTextMuted);
                    const char* hint = (sel && restoreArmed)
                        ? tr("sys.saves.restore.confirm") : tr("sys.saves.restore.hint");
                    drawText(renderer, fontTiny, hint, contentX + 16, ry + 27,
                             (sel && restoreArmed) ? kColError : kColTextDim);
                }
                HitBox hb; hb.rect = {contentX, ry, contentW, rowH - 6};
                int idx = i;
                hb.fn = [&saveSel, &restoreArmed, idx]() { saveSel = idx; restoreArmed = false; };
                hits.push_back(hb);
            }
        }

        // ------------------------------------------------------------------
        // Seite: PROTOKOLL
        // ------------------------------------------------------------------
        else if (page == Page::Log) {
            auto lines = applog::snapshot();
            int lineH = 26;
            int visLines = (cfg::kScreenH - footerH - cy - 8) / lineH;
            if (visLines < 1) visLines = 1;
            int total = static_cast<int>(lines.size());
            if (total == 0) {
                drawText(renderer, fontSmall, tr("log.empty"), contentX + 4, cy + 8, kColTextMuted);
            } else {
                int maxScroll = total > visLines ? total - visLines : 0;
                if (logScroll > maxScroll) logScroll = maxScroll;
                int start = total - visLines - logScroll;
                if (start < 0) start = 0;
                for (int i = 0; i < visLines; i++) {
                    int idx = start + i;
                    if (idx >= total) break;
                    drawText(renderer, fontSmall,
                             truncated(fontSmall, lines[idx], contentW - 20),
                             contentX + 4, cy + i * lineH, kColTextMuted);
                }
            }
        }

        // ---------------- Footer ----------------
        bool online = g_online.load();
        int fy2 = cfg::kScreenH - footerH;
        fillRect(renderer, 0, fy2, cfg::kScreenW, footerH, kColFooter);
        // Duenner Fortschritts-Streifen an der Oberkante bei laufender Aktion
        if (busy) {
            long long done = g_bytesDone.load(), total = g_bytesTotal.load();
            int zi = g_zipIndex.load(), zt = g_zipTotal.load();
            double frac = -1;
            if (zt > 0) frac = (double)zi / (double)zt;
            else if (total > 0) frac = (double)done / (double)total;
            if (frac >= 0) {
                fillRect(renderer, 0, fy2, static_cast<int>(cfg::kScreenW * frac), 3, kColAccent);
            }
        }
        fillRect(renderer, 30, fy2 + 20, 12, 12, online ? kColSuccess : kColError);
        std::string footLeft = online ? tr("footer.online") : tr("footer.offline");
        if (busy) footLeft += "   \xc2\xb7   " + getStatus();
        drawText(renderer, fontTiny, truncated(fontTiny, footLeft, cfg::kScreenW - 420),
                 52, fy2 + 17, kColTextMuted);

        std::string hints;
        if (busy) hints = tr("footer.cancel");
        else if (page == Page::Detail) hints = tr("footer.detail");
        else if (page == Page::Editor) hints = tr("footer.editor");
        else if (page == Page::Library) hints = tr("footer.library");
        else if (page == Page::CheatSlips) hints = tr("footer.cheatslips");
        else if (page == Page::Home) hints = tr("footer.home");
        else if (page == Page::System) hints = tr("footer.system");
        else if (page == Page::SaveGames) hints = tr("footer.savegames");
        else if (page == Page::SysDetail) hints = tr("footer.sysdetail");
        else if (page == Page::Saves) hints = tr("footer.saves");
        else hints = tr("footer.nav");
        drawTextRight(renderer, fontTiny, hints, cfg::kScreenW - 28, fy2 + 17, kColTextMuted);

        textCacheMaintain();
        SDL_RenderPresent(renderer);
    }

    if (g_action.load() != Action::None) {
        g_cancelRequested = true;
    }
    if (g_worker.joinable()) {
        g_worker.join();
    }
    installer::shutdown();
    sysinfo::exit();   // ns/account/pm/dmnt:cht schliessen (No-op, wenn nie init.)

    covers::shutdown();
    textCacheDestroy();
    if (fontTitle) TTF_CloseFont(fontTitle);
    if (fontStat) TTF_CloseFont(fontStat);
    if (fontBody) TTF_CloseFont(fontBody);
    if (fontSmall) TTF_CloseFont(fontSmall);
    if (fontTiny) TTF_CloseFont(fontTiny);
    TTF_Quit();
    IMG_Quit();

    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    SDL_Quit();

    if (R_SUCCEEDED(plRc)) plExit();
    updater::curlGlobalCleanup();
    socketExit();
    romfsExit();

    return 0;
}
