// Switch Cheats Downloader - Nintendo Switch Homebrew (.nro)
//
// Laedt die von DevCatSKZ gepflegte switch-cheats.zip
// (https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/tag/data)
// herunter und entpackt sie direkt in das richtige Atmosphere-Layout auf der
// SD-Karte. Erkennt Updates anhand des GitHub "updated_at" Zeitstempels des
// Release-Assets (gleiche Logik wie im Desktop-Tool).
//
// UI: dunkles, am Switch-Systemmenue orientiertes Design. Volle
// Joycon/Controller- sowie Touchscreen-Steuerung.

#include <switch.h>
#include <SDL.h>
#include <SDL_ttf.h>
#include <curl/curl.h>

#include <string>
#include <vector>
#include <thread>
#include <atomic>
#include <mutex>
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <ctime>

#include "config.hpp"
#include "updater.hpp"
#include "zip_extract.hpp"
#include "i18n.hpp"

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
// Farbschema: "Prisma (Holo-Glas)" - das Signatur-Design der Windows-Version
// (gui.py THEMES["prisma"]), damit beide Programme einheitlich aussehen.
// Tiefes Petrol-Schwarz, Teal-Mint als Primaerakzent, Elektro-Violett als
// Sekundaerakzent (Verlaufs-Buttons), Gold als Highlight. Halbtransparente
// Toene der Design-Vorgabe sind fest auf ihre Hintergruende gemischt.
// ---------------------------------------------------------------------------
static const SDL_Color kColBg          = {4, 10, 16, 255};     // #040A10 Canvas
static const SDL_Color kColSidebar     = {11, 20, 28, 255};    // #0B141C Panel
static const SDL_Color kColPanel       = {15, 35, 41, 255};    // #0F2329 Glas (7% Teal)
static const SDL_Color kColItem        = {11, 20, 28, 255};    // Button-/Trough-Glas
static const SDL_Color kColItemHover   = {20, 69, 69, 255};    // #144545 aktiv (Akzent 18%)
static const SDL_Color kColAccent      = {45, 225, 194, 255};  // #2DE1C2 Teal-Mint
static const SDL_Color kColAccent2     = {124, 92, 255, 255};  // #7C5CFF Elektro-Violett
static const SDL_Color kColGold        = {255, 194, 75, 255};  // #FFC24B Highlight
static const SDL_Color kColOnAccent    = {4, 33, 28, 255};     // #04211C Text AUF Akzent
static const SDL_Color kColHairline    = {39, 44, 49, 255};    // #272C31 Haarlinie (14% Weiss)
static const SDL_Color kColText        = {240, 251, 248, 255}; // #F0FBF8
static const SDL_Color kColTextMuted   = {207, 220, 217, 255}; // #CFDCD9 (88%)
static const SDL_Color kColSuccess     = {62, 230, 143, 255};  // #3EE68F
static const SDL_Color kColError       = {255, 107, 122, 255}; // #FF6B7A
static const SDL_Color kColFooter      = {3, 7, 11, 255};

// Wenn die System-Uhr VOR diesem Zeitpunkt (2025-01-01 UTC) steht, ist sie
// definitiv falsch gestellt -> TLS-Zertifikatspruefung schlaegt fehl
// ("SSL peer certificate ... was not OK"). Wir warnen dann proaktiv.
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
// Online-Status fuer die Fussleiste: wird periodisch vom UI-Thread (nur wenn
// keine Aktion laeuft) und von den Workern beim Start aktualisiert.
static std::atomic<bool> g_online{false};

static std::mutex g_dataMutex;
static std::string g_statusLine;
static std::string g_resultLine;
static bool g_resultSuccess = false;
static bool g_haveResult = false;
static std::string g_remoteUpdatedAt;
static std::string g_localUpdatedAt;
static long long g_remoteSizeBytes = 0; // Asset-Groesse laut GitHub-API
static bool g_updateAvailable = false;
static bool g_haveRemoteInfo = false;

// App-Self-Update Zustand (getrennt vom Cheats-Update oben)
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
    std::lock_guard<std::mutex> lk(g_dataMutex);
    g_statusLine = s;
}
static std::string getStatus() {
    std::lock_guard<std::mutex> lk(g_dataMutex);
    return g_statusLine;
}
static void setResult(bool success, const std::string& msg) {
    std::lock_guard<std::mutex> lk(g_dataMutex);
    g_resultSuccess = success;
    g_resultLine = msg;
    g_haveResult = true;
}
static void setAppResult(bool success, const std::string& msg) {
    std::lock_guard<std::mutex> lk(g_dataMutex);
    g_appResultSuccess = success;
    g_appResultLine = msg;
    g_appHaveResult = true;
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

    std::string local = updater::readLocalUpdatedAt();
    bool avail = local.empty() || info.updatedAt > local;

    {
        std::lock_guard<std::mutex> lk(g_dataMutex);
        g_remoteUpdatedAt = info.updatedAt;
        g_localUpdatedAt = local;
        g_remoteSizeBytes = info.sizeBytes;
        g_updateAvailable = avail;
        g_haveRemoteInfo = true;
        // Erfolgs-Ergebnis steckt bereits im Statusblock (lokal/neueste
        // Version) - eine alte Fehlermeldung ggf. wegraeumen.
        g_haveResult = false;
        g_resultLine.clear();
    }

    // Stiller App-Update-Check fuer das Badge am "App-Update"-Menuepunkt.
    // Setzt bewusst NICHT g_appChecked/g_appHaveResult - der explizite
    // zweistufige Ablauf ueber den Menuepunkt bleibt unveraendert.
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

    // Resume: eine liegengebliebene Teildatei nur fortsetzen, wenn sie zum
    // SELBEN Release-Stand gehoert (Meta-Datei traegt das updated_at).
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
        // Teildatei + Meta bleiben liegen -> naechster Versuch setzt fort.
        setResult(false, updater::fileExists(cfg::kTmpZipPath)
                             ? tr("result.cancelledResume")
                             : tr("result.cancelled"));
        g_action = Action::None;
        return;
    }
    if (!dlResult.ok) {
        // Hat downloadFile die Teildatei verworfen, ist auch die Meta hinfaellig.
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

// zentriert Text vertikal in einer Zeile der Hoehe lineH, beginnend bei y
static void drawTextCentered(SDL_Renderer* r, TTF_Font* font, const std::string& text, int x, int y, int lineH, SDL_Color color) {
    if (!font) return;
    int tw = 0, th = 0;
    TTF_SizeUTF8(font, text.c_str(), &tw, &th);
    drawText(r, font, text, x, y + (lineH - th) / 2, color);
}

// Horizontaler Farbverlauf (fuer Primaer-Buttons: Teal -> Violett). SDL2 hat
// keine Gradient-Primitive; spaltenweise Linien sind bei Button-Groesse billig.
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

static void drawProgressBar(SDL_Renderer* r, int x, int y, int w, int h, double frac, SDL_Color fg) {
    if (frac < 0) frac = 0;
    if (frac > 1) frac = 1;
    fillRect(r, x, y, w, h, kColItem);
    fillRect(r, x, y, static_cast<int>(w * frac), h, fg);
    drawRectOutline(r, x, y, w, h, kColHairline);
}

// ---------------------------------------------------------------------------
// Hauptprogramm
// ---------------------------------------------------------------------------
int main(int argc, char** argv) {
    romfsInit();
    socketInitializeDefault();
    // curl (und damit der ssl:-Service) wird erst beim ersten Netzwerkzugriff
    // initialisiert - siehe updater::ensureCurlGlobalInit().

    Result plRc = plInitialize(PlServiceType_User);
    i18n::init();
    g_selfNroPath = updater::getSelfNroPath(argc, argv);

    // Reste abgebrochener/abgestuerzter Laeufe aufraeumen. Bewusst nur
    // loeschen, wenn die Datei existiert: remove() auf einen nicht
    // existierenden Pfad ist auf Hardware harmlos, laesst aber den
    // DeleteFile-Handler mancher Emulatoren (Eden/yuzu) crashen.
    // Die switch-cheats-Teildatei bleibt fuer den Download-Resume liegen -
    // aber nur als konsistentes Paar aus .part und .meta.
    updater::removeIfExists(cfg::kTmpNroPath);
    if (updater::fileExists(cfg::kTmpZipPath) != updater::fileExists(cfg::kTmpZipMetaPath)) {
        updater::removeIfExists(cfg::kTmpZipPath);
        updater::removeIfExists(cfg::kTmpZipMetaPath);
    }

    SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER);
    SDL_InitSubSystem(SDL_INIT_JOYSTICK);
    SDL_JoystickEventState(SDL_ENABLE);
    SDL_JoystickOpen(0);
    TTF_Init();

    SDL_Window* window = SDL_CreateWindow("Switch Cheats Downloader",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        cfg::kScreenW, cfg::kScreenH, SDL_WINDOW_SHOWN);
    // PRESENTVSYNC begrenzt die Schleife auf die Display-Refreshrate (statt
    // ungebremst zu rendern - wichtig fuer Akku/Waerme im Handheld-Modus).
    SDL_Renderer* renderer = SDL_CreateRenderer(window, -1,
        SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);

    TTF_Font* fontTitle = nullptr;
    TTF_Font* fontBody  = nullptr;
    TTF_Font* fontSmall = nullptr;

    if (R_SUCCEEDED(plRc)) {
        PlFontData font;
        if (R_SUCCEEDED(plGetSharedFontByType(&font, PlSharedFontType_Standard))) {
            fontTitle = TTF_OpenFontRW(SDL_RWFromConstMem(font.address, font.size), 1, 32);
            fontBody  = TTF_OpenFontRW(SDL_RWFromConstMem(font.address, font.size), 1, 24);
            fontSmall = TTF_OpenFontRW(SDL_RWFromConstMem(font.address, font.size), 1, 19);
        }
    }

    // Lokalen Update-Stand + initialen Online-Status laden
    {
        std::lock_guard<std::mutex> lk(g_dataMutex);
        g_localUpdatedAt = updater::readLocalUpdatedAt();
    }
    g_online = updater::isInternetAvailable();
    Uint32 nextOnlineCheck = SDL_GetTicks() + 5000;

    // Die Update-Pruefung ist in den Bereich "Herunterladen & Installieren"
    // integriert: beim App-Start laeuft einmalig ein reiner Check (kein
    // Download); der Download selbst startet nur per A/Start-Button.
    const int kMenuCount = 4; // install (inkl. Update-Check), info, appupdate, exit
    auto menuLabel = [](int i) -> std::string {
        switch (i) {
            case 0: return tr("menu.install");
            case 1: return tr("menu.info");
            case 2: return tr("menu.appupdate");
            case 3: return tr("menu.exit");
        }
        return "";
    };

    int selected = 0;
    bool exitRequested = false;
    bool autoCheckStarted = false; // einmaliger Update-Check beim Start
    int stickDir = 0; // letzter diskreter Zustand des linken Sticks (-1/0/1)
    // Erst navigieren, nachdem der Stick einmal neutral gelesen wurde -
    // filtert Initialisierungs-/Resync-Bursts (z.B. bei Fokuswechsel im
    // Emulator oder nach Suspend/Resume) heraus.
    bool stickSeenNeutral = false;

    const int sidebarW = 380;
    const int itemH = 74;
    const int itemStartY = 190;

    // Aktions-Button im Panel (fuer Touch/Maus): im Leerlauf "Starten" fuer
    // den ausgewaehlten Menuepunkt, waehrend einer laufenden Aktion
    // "Abbrechen" (Controller-Nutzer druecken A bzw. B). Fest ueber der
    // Fussleiste; beide Zustaende teilen sich dasselbe Rechteck.
    const int panelBtnW = 260;
    const int panelBtnH = 56;
    const int panelBtnX = sidebarW + 48;
    const int panelBtnY = cfg::kScreenH - 60 - 24 - panelBtnH;
    auto inPanelBtn = [&](int px, int py) {
        return px >= panelBtnX && px < panelBtnX + panelBtnW &&
               py >= panelBtnY && py < panelBtnY + panelBtnH;
    };
    // Zweiter Button rechts daneben: manueller Update-Check (nur im
    // Install-Panel sichtbar, Y-Taste oder Tap).
    const int panelBtn2X = panelBtnX + panelBtnW + 24;
    auto inPanelBtn2 = [&](int px, int py) {
        return px >= panelBtn2X && px < panelBtn2X + panelBtnW &&
               py >= panelBtnY && py < panelBtnY + panelBtnH;
    };
    // Sprachauswahl im Info-Panel: eine Reihe mit allen 6 Sprachen zum
    // direkten Antippen (aktuelle Sprache hervorgehoben).
    const int langBtnW = 120;
    const int langBtnStride = langBtnW + 16;
    auto langBtnIndex = [&](int px, int py) -> int {
        if (py < panelBtnY || py >= panelBtnY + panelBtnH) return -1;
        for (int i = 0; i < static_cast<int>(i18n::Lang::Count); i++) {
            int x = panelBtnX + i * langBtnStride;
            if (px >= x && px < x + langBtnW) return i;
        }
        return -1;
    };
    // Menuepunkte mit ausloesbarer Aktion (alles ausser Info)
    auto hasAction = [](int idx) { return idx != 1; };

    auto activateItem = [&](int idx) {
        if (g_action.load() != Action::None) return;
        switch (idx) {
            case 0: startInstall(); break;
            case 1: /* Info - nur Anzeige */ break;
            case 2: {
                bool checked, available;
                {
                    std::lock_guard<std::mutex> lk(g_dataMutex);
                    checked = g_appChecked;
                    available = g_appUpdateAvailable;
                }
                if (checked && available) startAppInstall();
                else startAppCheck();
                break;
            }
            case 3: exitRequested = true; break;
        }
    };

    while (!exitRequested && appletMainLoop()) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) {
                exitRequested = true;
            } else if (event.type == SDL_JOYBUTTONDOWN) {
                bool busy = g_action.load() != Action::None;
                if (event.jbutton.button == JOY_UP && !busy) {
                    selected = (selected + kMenuCount - 1) % kMenuCount;
                } else if (event.jbutton.button == JOY_DOWN && !busy) {
                    selected = (selected + 1) % kMenuCount;
                } else if (event.jbutton.button == JOY_A && !busy) {
                    activateItem(selected);
                } else if (event.jbutton.button == JOY_B) {
                    if (busy) g_cancelRequested = true;
                } else if (event.jbutton.button == JOY_Y && !busy) {
                    // Manueller Update-Check (nur im Install-Panel)
                    if (selected == 0) startCheck();
                } else if (event.jbutton.button == JOY_L) {
                    i18n::prevLang();
                } else if (event.jbutton.button == JOY_R) {
                    i18n::nextLang();
                } else if (event.jbutton.button == JOY_PLUS) {
                    if (g_action.load() != Action::None) g_cancelRequested = true;
                    exitRequested = true;
                }
            } else if (event.type == SDL_JOYAXISMOTION) {
                // Linker Stick, Y-Achse: diskrete Hoch/Runter-Navigation mit
                // Totzone; loest nur beim Wechsel der Richtung aus (kein Repeat).
                if (event.jaxis.axis == 1) {
                    const int kDeadzone = 16000;
                    int dir = (event.jaxis.value < -kDeadzone) ? -1
                            : (event.jaxis.value >  kDeadzone) ?  1 : 0;
                    if (dir == 0) {
                        stickSeenNeutral = true;
                    } else if (stickSeenNeutral && dir != stickDir &&
                               g_action.load() == Action::None) {
                        selected = (selected + kMenuCount + dir) % kMenuCount;
                    }
                    stickDir = dir;
                }
            } else if (event.type == SDL_FINGERDOWN) {
                bool busy = g_action.load() != Action::None;
                int px = static_cast<int>(event.tfinger.x * cfg::kScreenW);
                int py = static_cast<int>(event.tfinger.y * cfg::kScreenH);
                if (!busy) {
                    // Antippen WAEHLT nur aus - gestartet wird ueber den
                    // Start-Button im Panel (oder die A-Taste).
                    if (px < sidebarW && py >= itemStartY) {
                        int idx = (py - itemStartY) / itemH;
                        if (idx >= 0 && idx < kMenuCount) selected = idx;
                    } else if (selected == 1) {
                        int li = langBtnIndex(px, py);
                        if (li >= 0) i18n::setLang(static_cast<i18n::Lang>(li));
                    } else if (inPanelBtn(px, py) && hasAction(selected)) {
                        activateItem(selected);
                    } else if (inPanelBtn2(px, py) && selected == 0) {
                        startCheck();
                    }
                } else if (inPanelBtn(px, py)) {
                    g_cancelRequested = true;
                }
            } else if (event.type == SDL_MOUSEBUTTONDOWN) {
                bool busy = g_action.load() != Action::None;
                int px = event.button.x, py = event.button.y;
                if (!busy) {
                    if (px < sidebarW && py >= itemStartY) {
                        int idx = (py - itemStartY) / itemH;
                        if (idx >= 0 && idx < kMenuCount) selected = idx;
                    } else if (selected == 1) {
                        int li = langBtnIndex(px, py);
                        if (li >= 0) i18n::setLang(static_cast<i18n::Lang>(li));
                    } else if (inPanelBtn(px, py) && hasAction(selected)) {
                        activateItem(selected);
                    } else if (inPanelBtn2(px, py) && selected == 0) {
                        startCheck();
                    }
                } else if (inPanelBtn(px, py)) {
                    g_cancelRequested = true;
                }
            }
        }

        joinWorkerIfDone();

        // Einmaliger automatischer Update-CHECK beim Start (nur Abfrage,
        // KEIN Download - der startet ausschliesslich per A/Start-Button).
        if (!autoCheckStarted) {
            autoCheckStarted = true;
            startCheck();
        }

        // Online-Status periodisch auffrischen - nur wenn kein Worker laeuft,
        // damit nifm nicht von zwei Threads gleichzeitig benutzt wird (die
        // Worker aktualisieren g_online bei ihrem eigenen Internet-Check).
        Uint32 nowTicks = SDL_GetTicks();
        if (static_cast<Sint32>(nowTicks - nextOnlineCheck) >= 0) {
            if (g_action.load() == Action::None) {
                g_online = updater::isInternetAvailable();
            }
            nextOnlineCheck = nowTicks + 5000;
        }

        // ---------------- Zeichnen ----------------
        setColor(renderer, kColBg);
        SDL_RenderClear(renderer);

        // Sidebar
        fillRect(renderer, 0, 0, sidebarW, cfg::kScreenH, kColSidebar);
        drawText(renderer, fontTitle, "Switch Cheats", 32, 42, kColText);
        drawText(renderer, fontTitle, "Downloader", 32, 82, kColAccent);
        drawText(renderer, fontSmall,
            std::string("by DevCatSKZ  \xc2\xb7  v") + cfg::kAppVersion + "  \xc2\xb7  " + i18n::langCode(i18n::getLang()),
            32, 138, kColTextMuted);

        Action curAction = g_action.load();
        bool appBadge;
        {
            std::lock_guard<std::mutex> lk(g_dataMutex);
            appBadge = g_appUpdateAvailable;
        }
        for (int i = 0; i < kMenuCount; i++) {
            int y = itemStartY + i * itemH;
            bool isSelected = (i == selected);
            SDL_Color bg = isSelected ? kColItemHover : kColSidebar;
            fillRect(renderer, 0, y, sidebarW, itemH - 4, bg);
            if (isSelected) {
                fillRect(renderer, 0, y, 6, itemH - 4, kColAccent);
            }
            SDL_Color textColor = isSelected ? kColText : kColTextMuted;
            drawTextCentered(renderer, fontBody, menuLabel(i), 32, y, itemH - 4, textColor);
            // Dezentes Badge am "App-Update"-Eintrag, wenn der stille Check
            // beim Start eine neuere App-Version gefunden hat (Gold-Highlight).
            if (i == 2 && appBadge) {
                fillRect(renderer, sidebarW - 34, y + (itemH - 4) / 2 - 6, 12, 12, kColGold);
            }
        }

        // Rechtes Panel
        int panelX = sidebarW;
        int panelW = cfg::kScreenW - sidebarW;
        fillRect(renderer, panelX, 0, panelW, cfg::kScreenH, kColPanel);

        int contentX = panelX + 48;
        int contentY = 48;

        drawText(renderer, fontTitle, menuLabel(selected), contentX, contentY, kColText);
        contentY += 70;
        fillRect(renderer, contentX, contentY, panelW - 96, 1, kColHairline);
        contentY += 30;

        std::string statusNow = getStatus();
        std::string remoteAt, localAt, resultMsg;
        long long remoteSize = 0;
        bool updateAvail = false, haveRemote = false, resultOk = false, haveResult = false;
        std::string appResultMsg, appRemoteVersion;
        bool appResultOk = false, appHaveResult = false, appChecked = false, appAvailable = false, appJustInstalled = false;
        {
            std::lock_guard<std::mutex> lk(g_dataMutex);
            remoteAt = g_remoteUpdatedAt;
            localAt = g_localUpdatedAt;
            remoteSize = g_remoteSizeBytes;
            updateAvail = g_updateAvailable;
            haveRemote = g_haveRemoteInfo;
            resultMsg = g_resultLine;
            resultOk = g_resultSuccess;
            haveResult = g_haveResult;
            appResultMsg = g_appResultLine;
            appResultOk = g_appResultSuccess;
            appHaveResult = g_appHaveResult;
            appChecked = g_appChecked;
            appAvailable = g_appUpdateAvailable;
            appJustInstalled = g_appJustInstalled;
            appRemoteVersion = g_appRemoteVersion;
        }

        if (selected == 0) {
            // Kombinierter Bereich: Update-Status + Download/Installation
            drawText(renderer, fontBody, tr("install.desc1"), contentX, contentY, kColTextMuted);
            contentY += 34;
            drawText(renderer, fontBody, tr("install.desc2"), contentX, contentY, kColTextMuted);
            contentY += 50;

            // Proaktiver Hinweis: eine falsch gestellte Konsolen-Uhr laesst die
            // TLS-Pruefung scheitern (haeufigste Ursache des SSL-Fehlers, v.a.
            // mit 90DNS). Vor dem Download sichtbar warnen.
            if (time(nullptr) < kMinSaneEpoch) {
                drawText(renderer, fontBody, tr("clock.warn"), contentX, contentY, kColError);
                contentY += 40;
            }

            drawText(renderer, fontBody, std::string(tr("check.local")) +
                (localAt.empty() ? tr("check.never") : localAt), contentX, contentY, kColTextMuted);
            contentY += 40;
            if (haveRemote) {
                std::string remoteLine = std::string(tr("check.remote")) + remoteAt;
                if (remoteSize > 0) remoteLine += "  (" + formatBytes(remoteSize) + ")";
                drawText(renderer, fontBody, remoteLine, contentX, contentY, kColTextMuted);
                contentY += 40;
                drawText(renderer, fontBody,
                    updateAvail ? tr("check.available") : tr("check.uptodate"),
                    contentX, contentY, updateAvail ? kColGold : kColSuccess);
                contentY += 46;
            }

            if (curAction == Action::Installing) {
                long long done = g_bytesDone.load(), total = g_bytesTotal.load();
                int zi = g_zipIndex.load(), zt = g_zipTotal.load();
                if (zt > 0) {
                    double frac = (double)zi / (double)zt;
                    drawText(renderer, fontBody, tr("install.extract"), contentX, contentY, kColText);
                    contentY += 36;
                    drawProgressBar(renderer, contentX, contentY, panelW - 96, 28, frac, kColAccent);
                    contentY += 40;
                    drawText(renderer, fontSmall,
                        std::to_string(zi) + " / " + std::to_string(zt) + tr("install.filesSuffix"), contentX, contentY, kColTextMuted);
                } else if (total > 0) {
                    double frac = (double)done / (double)total;
                    drawText(renderer, fontBody, tr("install.download"), contentX, contentY, kColText);
                    contentY += 36;
                    drawProgressBar(renderer, contentX, contentY, panelW - 96, 28, frac, kColAccent);
                    contentY += 40;
                    drawText(renderer, fontSmall,
                        formatBytes(done) + " / " + formatBytes(total), contentX, contentY, kColTextMuted);
                } else if (done > 0) {
                    // Server ohne Content-Length: wenigstens die geladene Menge zeigen.
                    drawText(renderer, fontBody, tr("install.download"), contentX, contentY, kColText);
                    contentY += 36;
                    drawText(renderer, fontSmall, formatBytes(done), contentX, contentY, kColTextMuted);
                } else {
                    drawText(renderer, fontBody, statusNow, contentX, contentY, kColAccent);
                }
            } else if (curAction == Action::Checking) {
                drawText(renderer, fontBody, statusNow, contentX, contentY, kColAccent);
            } else if (haveResult) {
                drawText(renderer, fontBody, resultMsg, contentX, contentY, resultOk ? kColSuccess : kColError);
            } else {
                drawText(renderer, fontSmall, tr("install.hint"), contentX, contentY, kColTextMuted);
            }
        } else if (selected == 1) {
            drawText(renderer, fontBody, std::string(tr("info.source")) + "github.com/" + cfg::kRepoOwner + "/" + cfg::kRepoName, contentX, contentY, kColTextMuted);
            contentY += 40;
            drawText(renderer, fontBody, std::string(tr("info.tag")) + cfg::kReleaseTag, contentX, contentY, kColTextMuted);
            contentY += 40;
            drawText(renderer, fontBody, std::string(tr("info.asset")) + cfg::kAssetName, contentX, contentY, kColTextMuted);
            contentY += 40;
            drawText(renderer, fontBody, std::string(tr("info.target")) + cfg::kSdRoot + " (Atmosphere)", contentX, contentY, kColTextMuted);
            contentY += 40;
            drawText(renderer, fontBody, std::string(tr("info.localstate")) + (localAt.empty() ? tr("info.neverinstalled") : localAt), contentX, contentY, kColTextMuted);
            contentY += 40;
            drawText(renderer, fontBody, std::string(tr("info.version")) + cfg::kAppVersion, contentX, contentY, kColTextMuted);
            contentY += 40;
            drawText(renderer, fontBody, std::string(tr("info.lang")) + i18n::langCode(i18n::getLang()), contentX, contentY, kColTextMuted);
            contentY += 56;
            drawText(renderer, fontSmall, tr("info.note1"), contentX, contentY, kColTextMuted);
            contentY += 28;
            drawText(renderer, fontSmall, tr("info.note2"), contentX, contentY, kColTextMuted);
        } else if (selected == 2) {
            drawText(renderer, fontBody, tr("appupdate.desc1"), contentX, contentY, kColTextMuted);
            contentY += 34;
            drawText(renderer, fontBody, tr("appupdate.desc2"), contentX, contentY, kColTextMuted);
            contentY += 60;

            if (curAction == Action::AppChecking) {
                drawText(renderer, fontBody, statusNow, contentX, contentY, kColAccent);
            } else if (curAction == Action::AppInstalling) {
                long long done = g_bytesDone.load(), total = g_bytesTotal.load();
                if (total > 0) {
                    double frac = (double)done / (double)total;
                    drawText(renderer, fontBody, tr("install.download"), contentX, contentY, kColText);
                    contentY += 36;
                    drawProgressBar(renderer, contentX, contentY, panelW - 96, 28, frac, kColAccent);
                    contentY += 40;
                    drawText(renderer, fontSmall,
                        formatBytes(done) + " / " + formatBytes(total), contentX, contentY, kColTextMuted);
                } else if (done > 0) {
                    drawText(renderer, fontBody, tr("install.download"), contentX, contentY, kColText);
                    contentY += 36;
                    drawText(renderer, fontSmall, formatBytes(done), contentX, contentY, kColTextMuted);
                } else {
                    drawText(renderer, fontBody, statusNow, contentX, contentY, kColAccent);
                }
            } else if (appHaveResult) {
                drawText(renderer, fontBody, appResultMsg, contentX, contentY, appResultOk ? kColSuccess : kColError);
                contentY += 40;
                if (appChecked && appAvailable) {
                    drawText(renderer, fontSmall, tr("appupdate.pressAgain"), contentX, contentY, kColAccent);
                } else if (appJustInstalled) {
                    drawText(renderer, fontSmall, tr("appupdate.restartHint"), contentX, contentY, kColAccent);
                }
            } else {
                drawText(renderer, fontSmall, tr("install.hint"), contentX, contentY, kColTextMuted);
            }
        } else if (selected == 3) {
            drawText(renderer, fontBody, tr("exit.hint"), contentX, contentY, kColTextMuted);
        }

        // Panel-Buttons fuer Touch/Maus: "Abbrechen" bei laufender Aktion;
        // im Leerlauf je nach Panel Starten/Pruefen (Install), Sprachwechsel
        // (Info) oder Starten/Beenden (App-Update/Exit).
        {
            // Primaer-Buttons tragen den Signatur-Verlauf Teal -> Violett mit
            // dunklem Petrol-Text; Sekundaer-Buttons sind Glasflaechen mit
            // Haarlinien-Rand (Prisma-Designsprache).
            auto drawPanelButton = [&](int x, const std::string& label,
                                       bool primary, SDL_Color outline) {
                if (primary) {
                    // Signaturverlauf Teal -> Violett
                    drawGradientRectH(renderer, x, panelBtnY, panelBtnW, panelBtnH,
                                      kColAccent, kColAccent2);
                } else {
                    fillRect(renderer, x, panelBtnY, panelBtnW, panelBtnH, kColItem);
                    drawRectOutline(renderer, x, panelBtnY, panelBtnW, panelBtnH, outline);
                }
                int cw = 0, ch = 0;
                if (fontBody && TTF_SizeUTF8(fontBody, label.c_str(), &cw, &ch) == 0) {
                    drawText(renderer, fontBody, label,
                        x + (panelBtnW - cw) / 2, panelBtnY + (panelBtnH - ch) / 2,
                        primary ? kColOnAccent : kColText);
                }
            };

            if (curAction != Action::None) {
                drawPanelButton(panelBtnX, std::string("B  ") + tr("btn.cancel"),
                                false, kColHairline);
            } else if (selected == 0) {
                drawPanelButton(panelBtnX, std::string("A  ") + tr("btn.start"),
                                true, kColAccent);
                drawPanelButton(panelBtn2X, std::string("Y  ") + tr("btn.check"),
                                false, kColHairline);
            } else if (selected == 1) {
                // Direkte Sprachauswahl: alle 6 Sprachen als Chips; die aktive
                // traegt Akzent-Rand + Akzent-Fuellung (18%), inaktive nur
                // Haarlinie + Sekundaertext.
                int cur = static_cast<int>(i18n::getLang());
                for (int i = 0; i < static_cast<int>(i18n::Lang::Count); i++) {
                    int x = panelBtnX + i * langBtnStride;
                    bool isCur = (i == cur);
                    fillRect(renderer, x, panelBtnY, langBtnW, panelBtnH, isCur ? kColItemHover : kColItem);
                    drawRectOutline(renderer, x, panelBtnY, langBtnW, panelBtnH, isCur ? kColAccent : kColHairline);
                    std::string code = i18n::langCode(static_cast<i18n::Lang>(i));
                    int cw = 0, ch = 0;
                    if (fontBody && TTF_SizeUTF8(fontBody, code.c_str(), &cw, &ch) == 0) {
                        drawText(renderer, fontBody, code,
                            x + (langBtnW - cw) / 2, panelBtnY + (panelBtnH - ch) / 2,
                            isCur ? kColText : kColTextMuted);
                    }
                }
            } else if (hasAction(selected)) {
                drawPanelButton(panelBtnX, std::string("A  ") + tr(selected == 3 ? "menu.exit" : "btn.start"),
                                true, kColAccent);
            }
        }

        // Fusszeile
        bool online = g_online.load();
        fillRect(renderer, 0, cfg::kScreenH - 60, cfg::kScreenW, 60, kColFooter);
        SDL_Color dotColor = online ? kColSuccess : kColError;
        fillRect(renderer, 30, cfg::kScreenH - 60 + 24, 14, 14, dotColor);
        drawText(renderer, fontSmall, online ? tr("footer.online") : tr("footer.offline"), 54, cfg::kScreenH - 60 + 16, kColTextMuted);

        std::string hints = (curAction != Action::None)
            ? tr("footer.cancel")
            : tr("footer.nav");
        int hw = 0, hh = 0;
        if (fontSmall) TTF_SizeUTF8(fontSmall, hints.c_str(), &hw, &hh);
        drawText(renderer, fontSmall, hints, cfg::kScreenW - hw - 30, cfg::kScreenH - 60 + 16, kColTextMuted);

        SDL_RenderPresent(renderer);
    }

    // Sauber beenden: laufenden Task abbrechen lassen und Thread joinen
    if (g_action.load() != Action::None) {
        g_cancelRequested = true;
    }
    if (g_worker.joinable()) {
        g_worker.join();
    }

    if (fontTitle) TTF_CloseFont(fontTitle);
    if (fontBody) TTF_CloseFont(fontBody);
    if (fontSmall) TTF_CloseFont(fontSmall);
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
