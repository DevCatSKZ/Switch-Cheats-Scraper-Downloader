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

#include "config.hpp"
#include "updater.hpp"
#include "zip_extract.hpp"
#include "i18n.hpp"
#include "db.hpp"
#include "installer.hpp"
#include "settings.hpp"
#include "applog.hpp"

using i18n::tr;

// SDL Joystick Button-Codes (siehe devkitPro switch-examples sdl2-demo)
#define JOY_A     0
#define JOY_B     1
#define JOY_X     2
#define JOY_Y     3
#define JOY_L     6
#define JOY_R     7
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
enum class Action { None, Checking, Installing, AppChecking, AppInstalling };

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

// "Komplett holen": database.db (Bibliothek) + switch-cheats.zip (Dateien).
static void runInstallWorker() {
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

    // -- Schritt 1: database.db (klein, ohne Resume) ------------------------
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

static void startInstall() {
    if (g_action.load() != Action::None) return;
    joinWorkerIfDone();
    updater::ensureCurlGlobalInit();
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
static void drawText(SDL_Renderer* r, TTF_Font* font, const std::string& text, int x, int y, SDL_Color color) {
    if (text.empty() || !font) return;
    SDL_Surface* surf = TTF_RenderUTF8_Blended(font, text.c_str(), color);
    if (!surf) return;
    SDL_Texture* tex = SDL_CreateTextureFromSurface(r, surf);
    SDL_Rect dst{x, y, surf->w, surf->h};
    SDL_FreeSurface(surf);
    if (tex) {
        SDL_RenderCopy(r, tex, nullptr, &dst);
        SDL_DestroyTexture(tex);
    }
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
enum class Page { Home = 0, Library, Settings, Log, Count, Detail };

struct NavEntry {
    Page page;
    const char* labelKey;
    const char* eyebrowKey;
    const char* subKey;
};
static const NavEntry kNav[] = {
    {Page::Home,     "nav.home",     "eyebrow.home",     "sub.home"},
    {Page::Library,  "nav.library",  "eyebrow.library",  "sub.library"},
    {Page::Settings, "nav.settings", "eyebrow.settings", "sub.settings"},
    {Page::Log,      "nav.log",      "eyebrow.log",      "sub.log"},
};
static constexpr int kNavCount = 4;

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

    // Lokale Staende + Bibliothek laden, Installiert-Scan starten.
    {
        std::lock_guard<std::mutex> lk(g_dataMutex);
        g_localUpdatedAt = updater::readLocalUpdatedAt();
        g_dbLocalUpdatedAt = updater::readTextFile(cfg::kDbStateFile);
    }
    if (!db::reload() && updater::fileExists(cfg::kDbPath)) {
        // DB vorhanden, aber nicht lesbar (z.B. WAL-Modus einer Fremdkopie) -
        // die Ursache gehoert ins Protokoll, nicht ins Nirvana.
        applog::add(std::string("DB: ") + db::lastError());
    }
    installer::startScan();
    g_online = updater::isInternetAvailable();
    Uint32 nextOnlineCheck = SDL_GetTicks() + 5000;

    // ---------------- UI-Zustand ----------------
    Page page = Page::Home;
    Page pageBeforeDetail = Page::Library;
    bool exitRequested = false;
    bool autoCheckStarted = false;

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

    // Einstellungen
    int setSel = 0;                // 0 = Sprache, 1 = App-Update, 2 = Neu laden
    static constexpr int kSetCount = 3;

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
                if (btn == JOY_PLUS) {
                    if (busy) g_cancelRequested = true;
                    exitRequested = true;
                } else if (btn == JOY_B) {
                    if (busy) {
                        g_cancelRequested = true;
                    } else if (page == Page::Detail) {
                        page = pageBeforeDetail;
                    }
                } else if (btn == JOY_L && page != Page::Detail) {
                    int idx = 0;
                    for (int i = 0; i < kNavCount; i++) {
                        if (kNav[i].page == page) idx = i;
                    }
                    page = kNav[(idx + kNavCount - 1) % kNavCount].page;
                } else if (btn == JOY_R && page != Page::Detail) {
                    int idx = 0;
                    for (int i = 0; i < kNavCount; i++) {
                        if (kNav[i].page == page) idx = i;
                    }
                    page = kNav[(idx + 1) % kNavCount].page;
                } else if (btn == JOY_A) {
                    if (page == Page::Home) {
                        if (!busy) startInstall();
                    } else if (page == Page::Library) {
                        if (!libRows.empty() && libSel < static_cast<int>(libRows.size())) {
                            openDetail(db::games()[libRows[libSel]]);
                        }
                    } else if (page == Page::Detail) {
                        detailExpanded = !detailExpanded;
                        detailNameScroll = 0;
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
                        }
                    }
                } else if (btn == JOY_Y) {
                    if (page == Page::Library) {
                        doSearch();
                    } else if (page == Page::Home && !busy) {
                        startCheck();
                    }
                } else if (btn == JOY_X) {
                    if (page == Page::Library) {
                        libFilter = static_cast<LibFilter>(
                            (static_cast<int>(libFilter) + 1) % static_cast<int>(LibFilter::Count));
                        libSel = 0;
                        libScroll = 0;
                        libDirty = true;
                    } else if (page == Page::Detail && !detailTid.empty()) {
                        settings::toggleFavorite(detailTid);
                        libDirty = true;
                    }
                } else if (btn == JOY_LEFT) {
                    if (page == Page::Library) {
                        libSel -= 10;
                        if (libSel < 0) libSel = 0;
                    } else if (page == Page::Settings && setSel == 0) {
                        i18n::prevLang();
                    }
                } else if (btn == JOY_RIGHT) {
                    if (page == Page::Library) {
                        libSel += 10;
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

        if (!autoCheckStarted) {
            autoCheckStarted = true;
            startCheck();
        }

        // Worker hat eine neue database.db abgelegt -> im UI-Thread neu laden.
        if (g_dbNeedsReload.exchange(false)) {
            db::reload();
            installer::startScan();
            libDirty = true;
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
                if (page == Page::Library) {
                    int n = static_cast<int>(libRows.size());
                    if (n > 0) {
                        libSel += step;
                        if (libSel < 0) libSel = 0;
                        if (libSel >= n) libSel = n - 1;
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
            bool active = (kNav[i].page == page) ||
                          (page == Page::Detail && kNav[i].page == Page::Library);
            // Aktive Zeile = EIN durchgehendes Rechteck + Akzentbalken links
            // (exakt der gefixte Windows-Look).
            if (active) {
                fillRect(renderer, 0, y, sidebarW, navItemH, kColItemHover);
                fillRect(renderer, 0, y, 5, navItemH, kColAccent);
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
            hb.fn = [&page, target]() { page = target; };
            hits.push_back(hb);
        }
        drawText(renderer, fontTiny, "by DevCatSKZ", 28, cfg::kScreenH - footerH - 30, kColTextDim);

        // ---------------- Seitenkopf ----------------
        const NavEntry* nav = &kNav[0];
        for (int i = 0; i < kNavCount; i++) {
            if (kNav[i].page == (page == Page::Detail ? Page::Library : page)) nav = &kNav[i];
        }
        int cy = headerH + 20;
        if (page != Page::Detail) {
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
            int cardH = 92;
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
                fillRect(renderer, x + 16, cy + 16, 26, 3, defs[i].col);
                drawText(renderer, fontStat, defs[i].value, x + 16, cy + 24, defs[i].col);
                drawText(renderer, fontTiny, tr(defs[i].labelKey), x + 16, cy + 66, kColTextMuted);
            }
            cy += cardH + 16;

            // Uhr-Warnung (falsche Systemzeit -> SSL-Fehler)
            if (time(nullptr) < kMinSaneEpoch) {
                drawText(renderer, fontSmall, tr("clock.warn"), contentX, cy, kColError);
                cy += 30;
            }

            // Linke Karte: "Alles holen" | rechte Karte: Zuletzt aktualisiert
            int leftW = (contentW - 16) * 55 / 100;
            int rightW = contentW - 16 - leftW;
            int cardsY = cy;
            int cardsH = cfg::kScreenH - footerH - cardsY - 14;
            drawCard(renderer, contentX, cardsY, leftW, cardsH);
            drawCard(renderer, contentX + leftW + 16, cardsY, rightW, cardsH);

            int lx = contentX + 20;
            int ly = cardsY + 16;
            int lTextW = leftW - 40;
            drawText(renderer, fontBody, truncated(fontBody, tr("home.card.title"), lTextW),
                     lx, ly, kColGold);
            ly += 34;
            drawText(renderer, fontSmall, truncated(fontSmall, tr("home.card.d1"), lTextW),
                     lx, ly, kColTextMuted);
            ly += 26;
            drawText(renderer, fontSmall, truncated(fontSmall, tr("home.card.d2"), lTextW),
                     lx, ly, kColTextMuted);
            ly += 34;

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

            drawText(renderer, fontSmall, std::string(tr("check.local")) +
                (localAt.empty() ? tr("check.never") : localAt), lx, ly, kColTextMuted);
            ly += 28;
            drawText(renderer, fontSmall, std::string(tr("home.dbstate")) +
                (dbLocalAt.empty() ? tr("check.never") : dbLocalAt), lx, ly, kColTextMuted);
            ly += 28;
            if (haveRemote) {
                std::string remoteLine = std::string(tr("check.remote")) + remoteAt;
                if (remoteSize > 0) remoteLine += "  (" + formatBytes(remoteSize) + ")";
                drawText(renderer, fontSmall, remoteLine, lx, ly, kColTextMuted);
                ly += 28;
                drawText(renderer, fontSmall,
                    updateAvail ? tr("check.available") : tr("check.uptodate"),
                    lx, ly, updateAvail ? kColGold : kColSuccess);
                ly += 34;
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

            // Buttons unten in der Karte: A = Komplett holen, Y = Pruefen
            int btnW = 250, btnH = 48;
            int btnY = cardsY + cardsH - btnH - 16;
            if (busy) {
                fillRect(renderer, lx, btnY, btnW, btnH, kColItem);
                drawRectOutline(renderer, lx, btnY, btnW, btnH, kColHairline);
                drawTextCentered(renderer, fontSmall, std::string("B  ") + tr("btn.cancel"),
                                 lx + 20, btnY, btnH, kColText);
                HitBox hb;
                hb.rect = {lx, btnY, btnW, btnH};
                hb.fn = []() { g_cancelRequested = true; };
                hits.push_back(hb);
            } else {
                drawGradientRectH(renderer, lx, btnY, btnW, btnH, kColAccent, kColAccent2);
                std::string lbl = std::string("A  ") + tr("home.btn.getall");
                drawTextCentered(renderer, fontSmall, lbl,
                                 lx + (btnW - textWidth(fontSmall, lbl)) / 2, btnY, btnH, kColOnAccent);
                HitBox hb;
                hb.rect = {lx, btnY, btnW, btnH};
                hb.fn = []() { startInstall(); };
                hits.push_back(hb);

                int b2x = lx + btnW + 14;
                fillRect(renderer, b2x, btnY, 200, btnH, kColItem);
                drawRectOutline(renderer, b2x, btnY, 200, btnH, kColHairline);
                std::string lbl2 = std::string("Y  ") + tr("btn.check");
                drawTextCentered(renderer, fontSmall, lbl2,
                                 b2x + (200 - textWidth(fontSmall, lbl2)) / 2, btnY, btnH, kColText);
                HitBox hb2;
                hb2.rect = {b2x, btnY, 200, btnH};
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
                std::string msg = !db::loaded() ? tr("lib.nodb")
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
            int cardH1 = 110;
            drawCard(renderer, contentX, cy, contentW, cardH1,
                     kColPanel, setSel == 0 ? kColAccent : kColHairline);
            drawText(renderer, fontBody, tr("set.section.lang"), contentX + 20, cy + 12, kColText);
            {
                int lbW = 96, lbH = 40;
                int lx2 = contentX + 20;
                int lyy = cy + 52;
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
            cy += cardH1 + 14;

            // -- Karte 2: App-Update ----------------------------------------
            int cardH2 = 120;
            drawCard(renderer, contentX, cy, contentW, cardH2,
                     kColPanel, setSel == 1 ? kColAccent : kColHairline);
            drawText(renderer, fontBody, tr("set.section.app"), contentX + 20, cy + 12, kColText);
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
                        drawProgressBar(renderer, contentX + 20, cy + 76, contentW - 300, 20,
                                        (double)done / (double)total, kColAccent);
                    }
                } else if (appHaveResult) {
                    line = appResultMsg;
                    col = appResultOk ? kColSuccess : kColError;
                    if (appChecked && appAvailable) {
                        drawText(renderer, fontTiny, tr("appupdate.pressAgain"),
                                 contentX + 20, cy + 76, kColAccent);
                    } else if (appJustInstalled) {
                        drawText(renderer, fontTiny, tr("appupdate.restartHint"),
                                 contentX + 20, cy + 76, kColAccent);
                    }
                } else {
                    line = std::string(tr("info.version")) + cfg::kAppVersion +
                           "  \xc2\xb7  A = " + tr("btn.check");
                }
                drawText(renderer, fontSmall, truncated(fontSmall, line, contentW - 60),
                         contentX + 20, cy + 46, col);
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
            cy += cardH2 + 14;

            // -- Karte 3: Daten ---------------------------------------------
            int cardH3 = 84;
            drawCard(renderer, contentX, cy, contentW, cardH3,
                     kColPanel, setSel == 2 ? kColAccent : kColHairline);
            drawText(renderer, fontBody, tr("set.reload"), contentX + 20, cy + 12, kColText);
            drawText(renderer, fontTiny, tr("set.reload.desc"), contentX + 20, cy + 48, kColTextDim);
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
            cy += cardH3 + 14;

            // -- Info-Block ---------------------------------------------------
            drawText(renderer, fontTiny,
                     std::string(tr("info.source")) + "github.com/" + cfg::kRepoOwner + "/" + cfg::kRepoName,
                     contentX, cy, kColTextDim);
            cy += 24;
            drawText(renderer, fontTiny,
                     std::string(tr("info.target")) + cfg::kSdRoot + " (Atmosphere)",
                     contentX, cy, kColTextDim);
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
        else if (page == Page::Library) hints = tr("footer.library");
        else hints = tr("footer.nav");
        drawTextRight(renderer, fontTiny, hints, cfg::kScreenW - 28, fy2 + 17, kColTextMuted);

        SDL_RenderPresent(renderer);
    }

    if (g_action.load() != Action::None) {
        g_cancelRequested = true;
    }
    if (g_worker.joinable()) {
        g_worker.join();
    }
    installer::shutdown();

    if (fontTitle) TTF_CloseFont(fontTitle);
    if (fontStat) TTF_CloseFont(fontStat);
    if (fontBody) TTF_CloseFont(fontBody);
    if (fontSmall) TTF_CloseFont(fontSmall);
    if (fontTiny) TTF_CloseFont(fontTiny);
    TTF_Quit();

    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    SDL_Quit();

    if (R_SUCCEEDED(plRc)) plExit();
    updater::curlGlobalCleanup();
    socketExit();
    romfsExit();

    return 0;
}
