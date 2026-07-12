#include "covers.hpp"
#include "config.hpp"
#include "updater.hpp"

#include <SDL_image.h>

#include <atomic>
#include <condition_variable>
#include <deque>
#include <dirent.h>
#include <map>
#include <mutex>
#include <set>
#include <sys/stat.h>
#include <thread>
#include <utility>

namespace covers {

static const char* kDir = "sdmc:/switch/SwitchCheatsDownloader/covers";

static std::mutex g_mtx;
static std::condition_variable g_cv;
static std::deque<std::pair<std::string, std::string>> g_queue; // (tid, url)
static std::set<std::string> g_queued;   // tid in Arbeit/Warteschlange
static std::set<std::string> g_failed;   // nicht erneut versuchen (Session)
static std::thread g_thread;
static std::atomic<bool> g_stop{false};

struct Tex {
    SDL_Texture* tex = nullptr;
    int w = 0, h = 0;
    bool tried = false; // Datei fehlte/Decode schlug fehl -> nicht neu laden
};
static std::map<std::string, Tex> g_texCache;

static std::string pathFor(const std::string& tid) {
    return std::string(kDir) + "/" + tid + ".jpg";
}

static void worker() {
    while (!g_stop.load()) {
        std::pair<std::string, std::string> job;
        {
            std::unique_lock<std::mutex> lk(g_mtx);
            g_cv.wait(lk, [] { return g_stop.load() || !g_queue.empty(); });
            if (g_stop.load()) return;
            job = g_queue.front();
            g_queue.pop_front();
        }
        // curl darf erst nach der ersten UI-Initialisierung benutzt werden
        // (ssl:-Service; siehe updater::ensureCurlGlobalInit) - solange
        // zurueckstellen.
        if (!updater::curlReady()) {
            std::lock_guard<std::mutex> lk(g_mtx);
            g_queue.push_back(job);
            g_queued.insert(job.first);
            // kleine Pause ueber die condition_variable-Runde hinaus
            std::this_thread::sleep_for(std::chrono::milliseconds(500));
            continue;
        }
        mkdir(kDir, 0777);
        std::string tmp = pathFor(job.first) + ".part";
        auto res = updater::downloadFile(job.second, tmp,
            [](long long, long long) { return !g_stop.load(); });
        {
            std::lock_guard<std::mutex> lk(g_mtx);
            g_queued.erase(job.first);
            if (res.ok) {
                remove(pathFor(job.first).c_str());
                rename(tmp.c_str(), pathFor(job.first).c_str());
            } else {
                remove(tmp.c_str());
                g_failed.insert(job.first);
            }
        }
    }
}

void init() {
    mkdir(kDir, 0777);
    g_stop = false;
    g_thread = std::thread(worker);
}

void shutdown() {
    g_stop = true;
    g_cv.notify_all();
    if (g_thread.joinable()) g_thread.join();
    for (auto& [k, t] : g_texCache) {
        if (t.tex) SDL_DestroyTexture(t.tex);
    }
    g_texCache.clear();
}

void request(const std::string& tid, const std::string& url) {
    if (url.empty()) return;
    std::lock_guard<std::mutex> lk(g_mtx);
    if (g_queued.count(tid) || g_failed.count(tid)) return;
    // Datei schon auf SD? Dann laedt get() sie direkt.
    struct stat st;
    if (stat(pathFor(tid).c_str(), &st) == 0 && st.st_size > 0) return;
    g_queued.insert(tid);
    g_queue.emplace_back(tid, url);
    g_cv.notify_one();
}

SDL_Texture* get(SDL_Renderer* r, const std::string& tid, int& w, int& h) {
    auto it = g_texCache.find(tid);
    if (it != g_texCache.end()) {
        w = it->second.w;
        h = it->second.h;
        return it->second.tex;
    }
    struct stat st;
    std::string p = pathFor(tid);
    if (stat(p.c_str(), &st) != 0 || st.st_size == 0) {
        w = h = 0;
        return nullptr; // (noch) nicht auf SD
    }
    Tex t;
    SDL_Surface* surf = IMG_Load(p.c_str());
    if (surf) {
        t.tex = SDL_CreateTextureFromSurface(r, surf);
        t.w = surf->w;
        t.h = surf->h;
        SDL_FreeSurface(surf);
    } else {
        t.tried = true; // kaputte Datei - nicht jede Frame neu versuchen
        remove(p.c_str());
    }
    // GPU-Speicher begrenzen: bei > 90 Texturen aelteste rauswerfen (simpel:
    // kompletter Reset - die sichtbaren laden sofort wieder).
    if (g_texCache.size() > 90) {
        for (auto& [k, tx] : g_texCache) {
            if (tx.tex) SDL_DestroyTexture(tx.tex);
        }
        g_texCache.clear();
    }
    g_texCache[tid] = t;
    w = t.w;
    h = t.h;
    return t.tex;
}

int cachedFiles() {
    int n = 0;
    DIR* d = opendir(kDir);
    if (!d) return 0;
    struct dirent* e;
    while ((e = readdir(d)) != nullptr) {
        std::string fn = e->d_name;
        if (fn.size() > 4 && fn.compare(fn.size() - 4, 4, ".jpg") == 0) n++;
    }
    closedir(d);
    return n;
}

void clearDisk() {
    DIR* d = opendir(kDir);
    if (!d) return;
    struct dirent* e;
    while ((e = readdir(d)) != nullptr) {
        std::string fn = e->d_name;
        if (fn == "." || fn == "..") continue;
        remove((std::string(kDir) + "/" + fn).c_str());
    }
    closedir(d);
    // Texturen invalidieren
    for (auto& [k, t] : g_texCache) {
        if (t.tex) SDL_DestroyTexture(t.tex);
    }
    g_texCache.clear();
}

} // namespace covers
