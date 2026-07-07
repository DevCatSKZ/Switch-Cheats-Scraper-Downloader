#include "updater.hpp"
#include "config.hpp"
#include "json_util.hpp"
#include "version_util.hpp"
#include "i18n.hpp"

#include <curl/curl.h>
#include <switch.h>

#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <vector>
#include <sys/stat.h>

using i18n::tr;

namespace updater {

static size_t writeToString(char* ptr, size_t size, size_t nmemb, void* userdata) {
    auto* out = static_cast<std::string*>(userdata);
    out->append(ptr, size * nmemb);
    return size * nmemb;
}

static size_t writeToFile(char* ptr, size_t size, size_t nmemb, void* userdata) {
    auto* f = static_cast<FILE*>(userdata);
    return fwrite(ptr, size, nmemb, f);
}

struct ProgressCtx {
    const ProgressCb* cb;
    long long offset; // bereits vorhandene Bytes bei Resume (fuer die Anzeige)
};

static int xferInfoTrampoline(void* clientp, curl_off_t dltotal, curl_off_t dlnow,
                               curl_off_t /*ultotal*/, curl_off_t /*ulnow*/) {
    auto* ctx = static_cast<ProgressCtx*>(clientp);
    if (ctx && ctx->cb && *ctx->cb) {
        long long done = static_cast<long long>(dlnow) + ctx->offset;
        long long total = (dltotal > 0) ? static_cast<long long>(dltotal) + ctx->offset : 0;
        bool keepGoing = (*ctx->cb)(done, total);
        if (!keepGoing) return 1; // != 0 bricht den Transfer ab
    }
    return 0;
}

static void ensureAppDir() {
    mkdir("sdmc:/switch", 0777);
    mkdir(cfg::kAppDir, 0777);
}

// Nur vom UI-Thread aufrufen (start*()-Funktionen), nie nebenlaeufig -
// curl_global_init() selbst ist nicht threadsafe.
static bool g_curlInitialized = false;

void ensureCurlGlobalInit() {
    if (!g_curlInitialized) {
        curl_global_init(CURL_GLOBAL_DEFAULT);
        g_curlInitialized = true;
    }
}

void curlGlobalCleanup() {
    if (g_curlInitialized) {
        curl_global_cleanup();
        g_curlInitialized = false;
    }
}

void removeIfExists(const char* path) {
    struct stat st;
    if (stat(path, &st) == 0) {
        remove(path);
    }
}

// Gemeinsame curl-Optionen aller Transfers: TLS-Verifikation gegen das
// RomFS-CA-Bundle und Redirects strikt auf HTTPS begrenzt (GitHub leitet
// Asset-Downloads auf objects.githubusercontent.com um).
static void applyCommonCurlOpts(CURL* curl) {
    curl_easy_setopt(curl, CURLOPT_USERAGENT, cfg::kUserAgent);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(curl, CURLOPT_MAXREDIRS, 10L);
    curl_easy_setopt(curl, CURLOPT_CAINFO, "romfs:/cacert.pem");
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
#if CURL_AT_LEAST_VERSION(7, 85, 0)
    curl_easy_setopt(curl, CURLOPT_PROTOCOLS_STR, "https");
    curl_easy_setopt(curl, CURLOPT_REDIR_PROTOCOLS_STR, "https");
#else
    curl_easy_setopt(curl, CURLOPT_PROTOCOLS, CURLPROTO_HTTPS);
    curl_easy_setopt(curl, CURLOPT_REDIR_PROTOCOLS, CURLPROTO_HTTPS);
#endif
}

// GET auf einen GitHub-API-Endpunkt. Rueckgabe: HTTP-Statuscode, oder -1 bei
// Transportfehler (dann ist error gesetzt).
static long httpGetString(const char* url, std::string& response, std::string& error) {
    CURL* curl = curl_easy_init();
    if (!curl) {
        error = tr("err.internal");
        return -1;
    }

    struct curl_slist* headers = curl_slist_append(nullptr, "Accept: application/vnd.github+json");

    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeToString);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 20L);
    applyCommonCurlOpts(curl);

    CURLcode res = curl_easy_perform(curl);
    long httpCode = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &httpCode);
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK) {
        error = std::string(tr("err.network")) + curl_easy_strerror(res);
        return -1;
    }
    return httpCode;
}

bool isInternetAvailable() {
    Result rc = nifmInitialize(NifmServiceType_User);
    if (R_FAILED(rc)) return false;

    NifmInternetConnectionType type;
    u32 wifiStrength = 0;
    NifmInternetConnectionStatus status;
    rc = nifmGetInternetConnectionStatus(&type, &wifiStrength, &status);
    nifmExit();

    if (R_FAILED(rc)) return false;
    return status == NifmInternetConnectionStatus_Connected;
}

ReleaseInfo fetchLatestReleaseInfo() {
    ReleaseInfo info;

    std::string response;
    long httpCode = httpGetString(cfg::kApiUrl, response, info.error);
    if (httpCode < 0) return info;
    if (httpCode == 403 || httpCode == 429) {
        // Unauthentifizierte GitHub-API: 60 Requests/Stunde pro IP.
        info.error = tr("err.rateLimit");
        return info;
    }
    if (httpCode != 200) {
        info.error = std::string(tr("err.githubHttp")) + std::to_string(httpCode);
        return info;
    }

    std::string assetObj = jsonutil::findAssetObject(response, cfg::kAssetName);
    if (assetObj.empty()) {
        info.error = std::string(tr("err.assetNotFound")) + cfg::kAssetName;
        return info;
    }

    info.downloadUrl = jsonutil::extractJsonString(assetObj, "browser_download_url");
    info.updatedAt   = jsonutil::extractJsonString(assetObj, "updated_at");
    info.sizeBytes   = jsonutil::extractJsonNumber(assetObj, "size");

    if (info.downloadUrl.empty()) {
        info.error = tr("err.noDownloadUrl");
        return info;
    }

    info.ok = true;
    return info;
}

DownloadResult downloadFile(const std::string& url, const std::string& destPath, const ProgressCb& progress,
                            long long resumeFrom, bool keepPartial) {
    DownloadResult result;
    ensureAppDir();

    FILE* f = fopen(destPath.c_str(), resumeFrom > 0 ? "ab" : "wb");
    if (!f) {
        result.error = std::string(tr("err.createFile")) + destPath;
        return result;
    }

    CURL* curl = curl_easy_init();
    if (!curl) {
        fclose(f);
        result.error = tr("err.internal");
        return result;
    }

    ProgressCtx ctx{ &progress, resumeFrom };

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeToFile);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, f);
    curl_easy_setopt(curl, CURLOPT_NOPROGRESS, 0L);
    curl_easy_setopt(curl, CURLOPT_XFERINFOFUNCTION, xferInfoTrampoline);
    curl_easy_setopt(curl, CURLOPT_XFERINFODATA, &ctx);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 30L);
    // Kein Gesamt-Timeout (Downloads duerfen lange dauern), aber eine
    // eingeschlafene Verbindung (< 1 Byte/s fuer 30 s) wird abgebrochen.
    curl_easy_setopt(curl, CURLOPT_LOW_SPEED_LIMIT, 1L);
    curl_easy_setopt(curl, CURLOPT_LOW_SPEED_TIME, 30L);
    if (resumeFrom > 0) {
        curl_easy_setopt(curl, CURLOPT_RESUME_FROM_LARGE, static_cast<curl_off_t>(resumeFrom));
    }
    applyCommonCurlOpts(curl);

    CURLcode res = curl_easy_perform(curl);
    long httpCode = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &httpCode);
    curl_easy_cleanup(curl);
    fclose(f);

    // 200 = kompletter Body, 206 = Teilinhalt (Range-Fortsetzung).
    bool bodyIsPayload = (httpCode == 200 || httpCode == 206);

    if (res == CURLE_ABORTED_BY_CALLBACK) {
        if (!(keepPartial && bodyIsPayload)) remove(destPath.c_str());
        result.cancelled = true;
        result.error = "cancelled";
        return result;
    }
    if (resumeFrom > 0 && httpCode == 200) {
        // Server hat den Range-Header ignoriert und den kompletten Body
        // geliefert - der wurde an die Teildatei ANGEHAENGT und ist damit
        // unbrauchbar. Verwerfen; der naechste Versuch laedt frisch.
        remove(destPath.c_str());
        result.error = std::string(tr("err.downloadFailed")) + "HTTP range";
        return result;
    }
    if (res != CURLE_OK) {
        // Transportabbruch mitten im Body: Teildatei ggf. fuer Resume behalten.
        if (!(keepPartial && bodyIsPayload && fileSize(destPath.c_str()) > resumeFrom)) {
            remove(destPath.c_str());
        }
        result.error = std::string(tr("err.downloadFailed")) + curl_easy_strerror(res);
        return result;
    }
    if (!bodyIsPayload) {
        remove(destPath.c_str());
        result.error = std::string(tr("err.serverHttp")) + std::to_string(httpCode);
        return result;
    }

    result.ok = true;
    return result;
}

bool fileExists(const char* path) {
    struct stat st;
    return stat(path, &st) == 0;
}

long long fileSize(const char* path) {
    struct stat st;
    if (stat(path, &st) != 0) return -1;
    return static_cast<long long>(st.st_size);
}

std::string readTextFile(const char* path) {
    FILE* f = fopen(path, "rb");
    if (!f) return "";
    char buf[128] = {0};
    size_t n = fread(buf, 1, sizeof(buf) - 1, f);
    fclose(f);
    buf[n] = '\0';
    std::string s(buf);
    while (!s.empty() && (s.back() == '\n' || s.back() == '\r' || s.back() == ' '))
        s.pop_back();
    return s;
}

bool writeTextFile(const char* path, const std::string& content) {
    ensureAppDir();
    FILE* f = fopen(path, "wb");
    if (!f) return false;
    size_t written = fwrite(content.data(), 1, content.size(), f);
    bool ok = (written == content.size()) && (fclose(f) == 0);
    return ok;
}

std::string readLocalUpdatedAt() {
    return readTextFile(cfg::kStateFile);
}

bool writeLocalUpdatedAt(const std::string& isoDate) {
    return writeTextFile(cfg::kStateFile, isoDate);
}

AppUpdateInfo checkAppUpdate() {
    AppUpdateInfo info;

    std::string response;
    long httpCode = httpGetString(cfg::kNroApiUrl, response, info.error);
    if (httpCode < 0) return info;

    if (httpCode == 404) {
        // Noch kein NRO-Release veroeffentlicht - kein Fehler fuer den Nutzer.
        info.ok = true;
        info.available = false;
        return info;
    }
    if (httpCode == 403 || httpCode == 429) {
        info.error = tr("err.rateLimit");
        return info;
    }
    if (httpCode != 200) {
        info.error = std::string(tr("err.githubHttp")) + std::to_string(httpCode);
        return info;
    }

    // Die Version steht im Release-TITEL ("name"-Feld), NICHT im tag_name:
    // das Release wird ueber den festen Tag "nro" abgefragt, sein tag_name
    // ist daher immer "nro" und kann keine Versionsinfo tragen. Das "name"-
    // Feld wird nur im Response-Teil VOR dem "assets"-Array gesucht, damit
    // nicht versehentlich ein Asset-"name" getroffen wird.
    size_t assetsPos = response.find("\"assets\"");
    std::string head = (assetsPos == std::string::npos) ? response : response.substr(0, assetsPos);
    std::string title = jsonutil::extractJsonString(head, "name");
    std::string remoteVer = versionutil::normalizeVersion(title);
    if (remoteVer.empty()) {
        info.error = tr("err.noVersionInTitle");
        return info;
    }

    std::string assetObj = jsonutil::findAssetObject(response, cfg::kNroAssetName);
    if (assetObj.empty()) {
        info.error = std::string(tr("err.assetNotFound")) + cfg::kNroAssetName;
        return info;
    }

    info.downloadUrl = jsonutil::extractJsonString(assetObj, "browser_download_url");
    if (info.downloadUrl.empty()) {
        info.error = tr("err.noDownloadUrl");
        return info;
    }

    info.remoteVersion = remoteVer;
    info.available = versionutil::isNewerVersion(remoteVer, cfg::kAppVersion);
    info.ok = true;
    return info;
}

std::string getSelfNroPath(int argc, char** argv) {
    if (argc > 0 && argv && argv[0] && argv[0][0] != '\0') {
        std::string p(argv[0]);
        // hbloader liefert typischerweise bereits einen "sdmc:/..." Pfad.
        if (p.rfind("sdmc:", 0) == 0) return p;
        if (p[0] == '/') return "sdmc:" + p;
    }
    return cfg::kSelfNroFallbackPath;
}

// Prueft die NRO-Magic "NRO0" bei Offset 0x10, damit nie eine HTML-Fehler-
// seite o.ae. als App installiert wird.
static bool hasNroMagic(const std::string& path) {
    FILE* f = fopen(path.c_str(), "rb");
    if (!f) return false;
    unsigned char hdr[0x14] = {0};
    size_t n = fread(hdr, 1, sizeof(hdr), f);
    fclose(f);
    return n == sizeof(hdr) && memcmp(hdr + 0x10, "NRO0", 4) == 0;
}

bool installSelfUpdate(const std::string& tmpPath, const std::string& selfPath, std::string& error) {
    struct stat st;
    if (stat(tmpPath.c_str(), &st) != 0 || st.st_size < 1024 || !hasNroMagic(tmpPath)) {
        error = tr("err.nroInvalid");
        removeIfExists(tmpPath.c_str());
        return false;
    }

    // rename() innerhalb desselben Dateisystems (sdmc:) ist quasi-atomar,
    // schlaegt auf der Switch aber fehl, wenn das Ziel bereits existiert -
    // daher das alte Ziel zuerst entfernen.
    if (rename(tmpPath.c_str(), selfPath.c_str()) == 0) {
        return true;
    }
    removeIfExists(selfPath.c_str());
    if (rename(tmpPath.c_str(), selfPath.c_str()) == 0) {
        return true;
    }

    // Fallback: manuell kopieren, mit vollstaendiger Fehlerpruefung - ein
    // halb geschriebenes Ziel wird entfernt statt als Erfolg gemeldet.
    FILE* in = fopen(tmpPath.c_str(), "rb");
    if (!in) {
        error = tr("err.tmpRead");
        return false;
    }
    FILE* out = fopen(selfPath.c_str(), "wb");
    if (!out) {
        fclose(in);
        error = std::string(tr("err.replaceFailed")) + selfPath;
        return false;
    }

    std::vector<char> buf(64 * 1024);
    bool copyOk = true;
    size_t n;
    while ((n = fread(buf.data(), 1, buf.size(), in)) > 0) {
        if (fwrite(buf.data(), 1, n, out) != n) {
            copyOk = false;
            break;
        }
    }
    if (ferror(in)) copyOk = false;
    fclose(in);
    if (fclose(out) != 0) copyOk = false;

    if (!copyOk) {
        // Korruptes Ziel entfernen; die verifizierte .nro bleibt unter
        // tmpPath fuer eine manuelle Wiederherstellung erhalten.
        remove(selfPath.c_str());
        error = std::string(tr("err.writeFile")) + selfPath;
        return false;
    }
    remove(tmpPath.c_str());
    return true;
}

} // namespace updater
