#include "installer.hpp"
#include "config.hpp"

#include <atomic>
#include <cctype>
#include <cstdio>
#include <dirent.h>
#include <mutex>
#include <set>
#include <thread>

namespace installer {

static std::mutex g_mtx;
static std::set<std::string> g_installed; // "TID|BID" (UPPERCASE)
static std::atomic<bool> g_scanning{false};
static std::atomic<bool> g_scannedOnce{false};
static std::atomic<int> g_count{0};
static std::thread g_thread;

static std::string upper(std::string s) {
    for (auto& c : s) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    return s;
}

static bool looksHex16(const std::string& s) {
    if (s.size() != 16) return false;
    for (char c : s) {
        if (!std::isxdigit(static_cast<unsigned char>(c))) return false;
    }
    return true;
}

static void scanWorker() {
    std::set<std::string> found;
    // Layout: atmosphere/contents/<TID>/cheats/<BID>.txt
    std::string root = std::string(cfg::kSdRoot) + "atmosphere/contents";
    DIR* d = opendir(root.c_str());
    if (d) {
        struct dirent* e;
        while ((e = readdir(d)) != nullptr) {
            std::string tid = e->d_name;
            if (tid == "." || tid == "..") continue;
            if (!looksHex16(tid)) continue;
            std::string cheatsDir = root + "/" + tid + "/cheats";
            DIR* cd = opendir(cheatsDir.c_str());
            if (!cd) continue;
            struct dirent* ce;
            while ((ce = readdir(cd)) != nullptr) {
                std::string fn = ce->d_name;
                if (fn.size() < 5) continue;
                std::string ext = fn.substr(fn.size() - 4);
                if (ext != ".txt" && ext != ".TXT") continue;
                std::string bid = fn.substr(0, fn.size() - 4);
                if (!looksHex16(bid)) continue;
                found.insert(upper(tid) + "|" + upper(bid));
            }
            closedir(cd);
        }
        closedir(d);
    }
    {
        std::lock_guard<std::mutex> lk(g_mtx);
        g_installed.swap(found);
        g_count = static_cast<int>(g_installed.size());
    }
    g_scannedOnce = true;
    g_scanning = false;
}

void startScan() {
    if (g_scanning.exchange(true)) return;
    if (g_thread.joinable()) g_thread.join();
    g_thread = std::thread(scanWorker);
}

bool scanning() { return g_scanning.load(); }
bool scannedOnce() { return g_scannedOnce.load(); }
int installedFileCount() { return g_count.load(); }

bool isInstalled(const std::string& tid, const std::string& bid) {
    std::lock_guard<std::mutex> lk(g_mtx);
    return g_installed.count(upper(tid) + "|" + upper(bid)) > 0;
}

bool anyInstalled(const std::vector<std::pair<std::string, std::string>>& pairs) {
    std::lock_guard<std::mutex> lk(g_mtx);
    for (const auto& [t, b] : pairs) {
        if (g_installed.count(t + "|" + b)) return true;
    }
    return false;
}

int countInstalled(const std::vector<std::pair<std::string, std::string>>& pairs) {
    std::lock_guard<std::mutex> lk(g_mtx);
    int n = 0;
    for (const auto& [t, b] : pairs) {
        if (g_installed.count(t + "|" + b)) n++;
    }
    return n;
}

std::string readCheatFile(const std::string& tid, const std::string& bid) {
    std::string path = std::string(cfg::kSdRoot) + "atmosphere/contents/" +
                       upper(tid) + "/cheats/" + upper(bid) + ".txt";
    FILE* f = fopen(path.c_str(), "rb");
    if (!f) return "";
    std::string out;
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), f)) > 0) {
        out.append(buf, n);
        if (out.size() > 512 * 1024) break; // Sicherheitsgrenze
    }
    fclose(f);
    return out;
}

void shutdown() {
    if (g_thread.joinable()) g_thread.join();
}

} // namespace installer
