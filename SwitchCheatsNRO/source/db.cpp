#include "db.hpp"
#include "config.hpp"

#include <algorithm>
#include <atomic>
#include <cctype>
#include <map>
#include <sys/stat.h>

#include "sqlite3.h"

namespace db {

static std::vector<GameRow> g_games;
// atomar, weil die DB seit v2.1.2 im Hintergrund geladen wird: der UI-Thread
// liest g_games NUR wenn loaded()==true; der Loader setzt loaded erst nach dem
// vollstaendigen Befuellen (und false VOR jeder Aenderung) -> keine Race.
static std::atomic<bool> g_loaded{false};
static std::atomic<int> g_loadPct{0};   // 0..100 Ladefortschritt (fuer den Balken)
static std::string g_error;
static long long g_dbSize = 0;

const std::string& lastError() { return g_error; }
bool loaded() { return g_loaded.load(); }
int loadPercent() { return g_loadPct.load(); }
const std::vector<GameRow>& games() { return g_games; }

static std::string upper(std::string s) {
    for (auto& c : s) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    return s;
}

// Basis-Title-ID einer Gruppe: erste 13 Zeichen + "000" (Windows-Konvention).
static std::string baseOf(const std::string& tid) {
    std::string t = upper(tid);
    if (t.size() >= 13) return t.substr(0, 13) + "000";
    return t;
}

static std::string colText(sqlite3_stmt* st, int idx) {
    const unsigned char* p = sqlite3_column_text(st, idx);
    return p ? reinterpret_cast<const char*>(p) : "";
}

// libnx nutzt Devicepfade ("sdmc:/...") OHNE fuehrenden '/': SQLites
// unix-VFS haelt die fuer relativ und klebt getcwd() davor -> CANTOPEN.
// Loesung: ein Klon des "unix-none"-VFS (keine fcntl-Locks - auf libnx nicht
// implementiert; wir sind ohnehin der einzige Prozess), dessen xFullPathname
// den Pfad unveraendert durchreicht.
static sqlite3_vfs g_nxVfs;
static int nxFullPathname(sqlite3_vfs*, const char* zName, int nOut, char* zOut) {
    sqlite3_snprintf(nOut, zOut, "%s", zName);
    return SQLITE_OK;
}
static bool ensureNxVfs() {
    static bool registered = false;
    if (registered) return true;
    sqlite3_vfs* base = sqlite3_vfs_find("unix-none");
    if (!base) {
        g_error = "vfs unix-none missing";
        return false;
    }
    g_nxVfs = *base;
    g_nxVfs.zName = "nx";
    g_nxVfs.xFullPathname = nxFullPathname;
    if (sqlite3_vfs_register(&g_nxVfs, 0) != SQLITE_OK) {
        g_error = "vfs register failed";
        return false;
    }
    registered = true;
    return true;
}

// Oeffnet die DB read-only ueber das "nx"-VFS.
static sqlite3* openDb() {
    if (!ensureNxVfs()) return nullptr;
    sqlite3* h = nullptr;
    int rc = sqlite3_open_v2(cfg::kDbPath, &h,
                             SQLITE_OPEN_READONLY, "nx");
    if (rc != SQLITE_OK) {
        g_error = h ? sqlite3_errmsg(h) : sqlite3_errstr(rc);
        if (h) sqlite3_close(h);
        return nullptr;
    }
    return h;
}

static std::atomic<bool> g_loading{false};

bool reload() {
    // Nie zwei Reloads gleichzeitig (Startup-Hintergrund-Load vs. UI-Reload-Button)
    // - sonst wuerden beide g_games modifizieren. Der zweite kehrt einfach zurueck.
    if (g_loading.exchange(true)) return false;
    struct Guard { ~Guard() { g_loading = false; } } guard;

    // WICHTIG: erst loaded=false (sperrt UI-Lesezugriffe), DANN g_games leeren -
    // sonst koennte der UI-Thread waehrend des clear() lesen.
    g_loaded = false;
    g_loadPct = 0;
    g_games.clear();
    g_error.clear();
    g_dbSize = 0;

    struct stat st;
    if (stat(cfg::kDbPath, &st) != 0 || st.st_size == 0) {
        g_error = "no database file";
        return false;
    }
    g_dbSize = static_cast<long long>(st.st_size);

    sqlite3* h = openDb();
    if (!h) return false;

    // Gesamtzahl der Zeilen fuer den Fortschrittsbalken (leichter Scan ohne
    // Textextraktion, daher deutlich schneller als die Hauptabfrage).
    long long totalRows = 0;
    {
        sqlite3_stmt* cst = nullptr;
        if (sqlite3_prepare_v2(h,
                "SELECT COUNT(*) FROM builds WHERE title_id IS NOT NULL AND title_id<>''",
                -1, &cst, nullptr) == SQLITE_OK) {
            if (sqlite3_step(cst) == SQLITE_ROW) totalRows = sqlite3_column_int64(cst, 0);
            sqlite3_finalize(cst);
        }
    }

    // Eine flache Abfrage; gruppiert wird in C++ (haelt SQL trivial und
    // erlaubt es, die (tid,bid)-Paare fuer den Installiert-Check mitzunehmen).
    const char* sql =
        "SELECT title_id, build_id, game_title, region, cheat_count, last_updated, image "
        "FROM builds WHERE title_id IS NOT NULL AND title_id<>''";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(h, sql, -1, &stmt, nullptr) != SQLITE_OK) {
        g_error = sqlite3_errmsg(h);
        sqlite3_close(h);
        return false;
    }

    std::map<std::string, GameRow> groups;
    long long doneRows = 0;
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        // Fortschritt bis 95% fuers Zeilenlesen (Rest fuer Gruppieren/Sortieren).
        if (totalRows > 0 && ((++doneRows) & 127) == 0)
            g_loadPct = static_cast<int>(doneRows * 95 / totalRows);
        std::string tid = upper(colText(stmt, 0));
        std::string bid = upper(colText(stmt, 1));
        std::string name = colText(stmt, 2);
        std::string region = colText(stmt, 3);
        int cheats = sqlite3_column_int(stmt, 4);
        std::string updated = colText(stmt, 5);
        std::string image = colText(stmt, 6);

        GameRow& g = groups[baseOf(tid)];
        if (g.baseTid.empty()) g.baseTid = baseOf(tid);
        if (g.title.empty() && !name.empty()) g.title = name;
        if (g.region.empty() && !region.empty()) g.region = region;
        if (g.image.empty() && !image.empty()) g.image = image;
        g.builds += 1;
        g.cheats += cheats;
        if (updated > g.lastUpdated) g.lastUpdated = updated;
        if (!bid.empty()) g.pairs.emplace_back(tid, bid);
    }
    sqlite3_finalize(stmt);
    sqlite3_close(h);

    g_loadPct = 97;   // Zeilen gelesen; jetzt gruppieren + sortieren
    g_games.reserve(groups.size());
    for (auto& [k, v] : groups) g_games.push_back(std::move(v));

    // Nach Titel sortieren (case-insensitiv), Unbenannte ans Ende - die
    // gleiche Ordnung wie die Windows-Bibliothek.
    std::sort(g_games.begin(), g_games.end(), [](const GameRow& a, const GameRow& b) {
        bool an = a.title.empty(), bn = b.title.empty();
        if (an != bn) return bn;
        std::string al = a.title, bl = b.title;
        for (auto& c : al) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        for (auto& c : bl) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        if (al != bl) return al < bl;
        return a.baseTid < b.baseTid;
    });

    g_loadPct = 100;
    g_loaded = true;
    return true;
}

Stats stats() {
    Stats s;
    s.dbSizeBytes = g_dbSize;
    if (!g_loaded.load()) return s;   // laedt noch -> g_games nicht anfassen (Race)
    s.games = static_cast<int>(g_games.size());
    for (const auto& g : g_games) {
        s.builds += g.builds;
        s.cheats += g.cheats;
    }
    return s;
}

std::vector<BuildRow> gameBuilds(const std::string& baseTid) {
    std::vector<BuildRow> out;
    sqlite3* h = openDb();
    if (!h) return out;

    const char* sql =
        "SELECT title_id, build_id, version, source, region, cheat_count, "
        "       cheat_names, publisher, developer, category, release_date, "
        "       players, languages, rating "
        "FROM builds WHERE UPPER(substr(title_id,1,13))=substr(?,1,13) "
        "ORDER BY (version IS NULL), version, build_id";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(h, sql, -1, &stmt, nullptr) == SQLITE_OK) {
        std::string key = upper(baseTid);
        sqlite3_bind_text(stmt, 1, key.c_str(), -1, SQLITE_TRANSIENT);
        while (sqlite3_step(stmt) == SQLITE_ROW) {
            BuildRow b;
            b.titleId = upper(colText(stmt, 0));
            b.buildId = upper(colText(stmt, 1));
            b.version = colText(stmt, 2);
            b.source = colText(stmt, 3);
            b.region = colText(stmt, 4);
            b.cheatCount = sqlite3_column_int(stmt, 5);
            b.cheatNamesJson = colText(stmt, 6);
            b.publisher = colText(stmt, 7);
            b.developer = colText(stmt, 8);
            b.category = colText(stmt, 9);
            b.releaseDate = colText(stmt, 10);
            b.players = colText(stmt, 11);
            b.languages = colText(stmt, 12);
            b.rating = colText(stmt, 13);
            out.push_back(std::move(b));
        }
        sqlite3_finalize(stmt);
    } else {
        g_error = sqlite3_errmsg(h);
    }
    sqlite3_close(h);
    return out;
}

std::vector<const GameRow*> recent(int n) {
    std::vector<const GameRow*> ptrs;
    if (!g_loaded.load()) return ptrs;   // laedt noch -> keine g_games-Iteration (Race)
    ptrs.reserve(g_games.size());
    for (const auto& g : g_games) {
        if (!g.lastUpdated.empty() && !g.title.empty()) ptrs.push_back(&g);
    }
    std::sort(ptrs.begin(), ptrs.end(), [](const GameRow* a, const GameRow* b) {
        return a->lastUpdated > b->lastUpdated;
    });
    if (static_cast<int>(ptrs.size()) > n) ptrs.resize(n);
    return ptrs;
}

std::vector<std::string> parseNameArray(const std::string& json) {
    // Minimaler Parser fuer ein flaches JSON-Array aus Strings:
    // ["Name 1", "Name \"2\"", ...] - genau das Format von cheat_names.
    std::vector<std::string> out;
    size_t i = json.find('[');
    if (i == std::string::npos) return out;
    i++;
    while (i < json.size()) {
        while (i < json.size() && json[i] != '"' && json[i] != ']') i++;
        if (i >= json.size() || json[i] == ']') break;
        i++; // oeffnendes "
        std::string cur;
        while (i < json.size() && json[i] != '"') {
            if (json[i] == '\\' && i + 1 < json.size()) {
                char n = json[i + 1];
                if (n == '"' || n == '\\' || n == '/') { cur += n; i += 2; continue; }
                if (n == 'n' || n == 't') { cur += ' '; i += 2; continue; }
                if (n == 'u' && i + 5 < json.size()) { i += 6; cur += '?'; continue; }
            }
            cur += json[i];
            i++;
        }
        i++; // schliessendes "
        out.push_back(cur);
    }
    return out;
}

} // namespace db
