#include "settings.hpp"
#include "config.hpp"

#include <cstdio>
#include <map>
#include <sys/stat.h>

namespace settings {

static std::map<std::string, std::string> g_kv;
static std::set<std::string> g_favs;

static std::string favKey() { return "favorites"; }

static void parseFavs(const std::string& csv) {
    g_favs.clear();
    std::string cur;
    for (char c : csv) {
        if (c == ',') {
            if (!cur.empty()) g_favs.insert(cur);
            cur.clear();
        } else if (c != ' ') {
            cur += c;
        }
    }
    if (!cur.empty()) g_favs.insert(cur);
}

static std::string favsToCsv() {
    std::string out;
    for (const auto& f : g_favs) {
        if (!out.empty()) out += ",";
        out += f;
    }
    return out;
}

void load() {
    g_kv.clear();
    FILE* f = fopen(cfg::kSettingsFile, "rb");
    if (!f) return;
    char line[1024];
    while (fgets(line, sizeof(line), f)) {
        std::string s(line);
        while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
        size_t eq = s.find('=');
        if (eq == std::string::npos || eq == 0) continue;
        g_kv[s.substr(0, eq)] = s.substr(eq + 1);
    }
    fclose(f);
    parseFavs(get(favKey()));
}

void save() {
    mkdir(cfg::kAppDir, 0777);
    g_kv[favKey()] = favsToCsv();
    FILE* f = fopen(cfg::kSettingsFile, "wb");
    if (!f) return;
    for (const auto& [k, v] : g_kv) {
        fprintf(f, "%s=%s\n", k.c_str(), v.c_str());
    }
    fclose(f);
}

std::string get(const std::string& key, const std::string& def) {
    auto it = g_kv.find(key);
    return it != g_kv.end() ? it->second : def;
}

void set(const std::string& key, const std::string& value) {
    g_kv[key] = value;
    save();
}

bool getBool(const std::string& key, bool def) {
    std::string v = get(key, def ? "1" : "0");
    return v == "1" || v == "true";
}

void setBool(const std::string& key, bool v) { set(key, v ? "1" : "0"); }

bool isFavorite(const std::string& baseTid) { return g_favs.count(baseTid) > 0; }

void toggleFavorite(const std::string& baseTid) {
    if (!g_favs.erase(baseTid)) g_favs.insert(baseTid);
    save();
}

const std::set<std::string>& favorites() { return g_favs; }

} // namespace settings
