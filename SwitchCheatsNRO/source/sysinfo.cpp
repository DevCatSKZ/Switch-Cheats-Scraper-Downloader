// ---------------------------------------------------------------------------
// sysinfo.cpp - installierte Spiele, laufendes Spiel und Build-ID.
// Siehe sysinfo.hpp fuer den API-Ueberblick und die Referenz (EdiZon-SE).
// ---------------------------------------------------------------------------
#include "sysinfo.hpp"
#include "applog.hpp"

#include <switch.h>
#include <cstring>
#include <cstdio>
#include <cctype>
#include <memory>
#include <mutex>
#include <unordered_map>
#include <algorithm>

// Diagnose-Logging: schreibt Dienst-Ergebnisse ins In-App-Protokoll, damit
// Hardware-Fehler (Rechte/leere Listen) auf der Konsole sichtbar werden.
static void logrc(const char* what, Result rc) {
    char b[96];
    snprintf(b, sizeof(b), "sysinfo: %s rc=0x%08X", what, (unsigned)rc);
    applog::add(b);
}
static void logmsg(const char* fmt, long v) {
    char b[96];
    snprintf(b, sizeof(b), fmt, v);
    applog::add(b);
}

namespace {

std::mutex g_mtx;                 // serialisiert ns-Zugriffe + Cache
bool g_inited = false;
bool g_nsOk = false, g_accOk = false, g_pmOk = false;

// Metadaten-Cache (Title-ID -> Name/Autor/Version), damit die Listen-Ansicht
// und die Save-Seite ns nicht mehrfach fuer denselben Titel abfragen.
struct Meta { std::string name, author, version; bool ok = false; };
std::unordered_map<uint64_t, Meta> g_metaCache;

constexpr uint64_t kProgramMask = 0xFFFFFFFFFFFFFFF0ULL;

// ---------------------------------------------------------------------------
// dmnt:cht (Atmosphere Cheat-Dienst) - minimaler Wrapper. Stock-libnx bringt
// keinen dmntcht.h mit, also dispatchen wir die drei benoetigten Kommandos
// selbst (identische ABI wie EdiZons gebuendelter Wrapper).
// ---------------------------------------------------------------------------
struct DmntMemoryRegionExtents { u64 base; u64 size; };
struct DmntCheatProcessMetadata {
    u64 process_id;
    u64 title_id;
    DmntMemoryRegionExtents main_nso_extents;
    DmntMemoryRegionExtents heap_extents;
    DmntMemoryRegionExtents alias_extents;
    DmntMemoryRegionExtents address_space_extents;
    u8  main_nso_build_id[0x20];
};

Service g_chtSrv;
bool g_chtOpen = false;

Result chtOpen() {
    if (g_chtOpen) return 0;
    Result rc = smGetService(&g_chtSrv, "dmnt:cht");
    if (R_SUCCEEDED(rc)) g_chtOpen = true;
    return rc;
}
void chtClose() {
    if (g_chtOpen) { serviceClose(&g_chtSrv); g_chtOpen = false; }
}
Result chtHasProcess(bool* out) {
    u8 tmp = 0;
    Result rc = serviceDispatchOut(&g_chtSrv, 65000, tmp);
    if (R_SUCCEEDED(rc) && out) *out = (tmp != 0);
    return rc;
}
Result chtForceOpen() {
    return serviceDispatch(&g_chtSrv, 65003);
}
Result chtGetMetadata(DmntCheatProcessMetadata* out) {
    return serviceDispatchOut(&g_chtSrv, 65002, *out);
}

// NACP-Metadaten fuer eine Title-ID lesen (ns). Ergebnis wird gepuffert.
bool fetchMeta(uint64_t titleId, Meta& out) {
    if (!g_nsOk) return false;
    auto buf = std::make_unique<NsApplicationControlData>();
    std::memset(buf.get(), 0, sizeof(NsApplicationControlData));
    size_t outsize = 0;
    Result rc = nsGetApplicationControlData(
        NsApplicationControlSource_Storage, titleId & kProgramMask,
        buf.get(), sizeof(NsApplicationControlData), &outsize);
    if (R_FAILED(rc) || outsize < sizeof(buf->nacp)) return false;

    NacpLanguageEntry* le = nullptr;
    rc = nacpGetLanguageEntry(&buf->nacp, &le);
    if (R_SUCCEEDED(rc) && le) {
        out.name = le->name;
        out.author = le->author;
    }
    // display_version ist ein fixes char[0x10] - nicht garantiert 0-terminiert.
    char ver[0x11] = {0};
    std::memcpy(ver, buf->nacp.display_version, 0x10);
    out.version = ver;
    out.ok = true;
    return true;
}

} // namespace

namespace sysinfo {

void init() {
    std::lock_guard<std::mutex> lk(g_mtx);
    if (g_inited) return;
    AppletType at = appletGetAppletType();
    logmsg("sysinfo: appletType=%ld", (long)at);
    applog::add((at == AppletType_Application || at == AppletType_SystemApplication)
                ? "sysinfo: mode=APPLICATION (voll)" : "sysinfo: mode=APPLET (eingeschraenkt)");
    Result r;
    r = nsInitialize();                                   g_nsOk  = R_SUCCEEDED(r); logrc("nsInitialize", r);
    r = accountInitialize(AccountServiceType_Application); g_accOk = R_SUCCEEDED(r); logrc("accountInitialize", r);
    // pm:dmnt + pm:info fuer das laufende Spiel (nicht kritisch, wenn es fehlt).
    r = pmdmntInitialize();                                g_pmOk  = R_SUCCEEDED(r); logrc("pmdmntInitialize", r);
    if (g_pmOk) { r = pminfoInitialize(); g_pmOk = R_SUCCEEDED(r); logrc("pminfoInitialize", r); }
    g_inited = true;
}

bool isApplicationMode() {
    // Application / SystemApplication = volle FS/ns-Rechte + voller Speicher.
    // LibraryApplet / OverlayApplet (Album-Start) = eingeschraenkt.
    AppletType t = appletGetAppletType();
    return t == AppletType_Application || t == AppletType_SystemApplication;
}

void exit() {
    std::lock_guard<std::mutex> lk(g_mtx);
    if (!g_inited) return;
    chtClose();
    if (g_pmOk)  { pminfoExit(); pmdmntExit(); }
    if (g_accOk) accountExit();
    if (g_nsOk)  nsExit();
    g_inited = false;
    g_nsOk = g_accOk = g_pmOk = false;
}

std::string hex16(uint64_t v) {
    char b[17];
    snprintf(b, sizeof(b), "%016lX", (unsigned long)v);
    return std::string(b);
}

std::string baseGroup(uint64_t titleId) {
    // substr(0,13)+"000" auf der 16-stelligen Grosshex - exakt db::baseTid.
    std::string h = hex16(titleId);
    return h.substr(0, 13) + "000";
}

std::string buildIdHex(const uint8_t* b, size_t firstN) {
    if (!b) return "";
    std::string s;
    s.reserve(firstN * 2);
    char t[3];
    for (size_t i = 0; i < firstN; i++) {
        snprintf(t, sizeof(t), "%02X", b[i]);
        s += t;
    }
    return s;
}

bool titleMeta(uint64_t titleId, std::string& name, std::string& author,
               std::string& version) {
    std::lock_guard<std::mutex> lk(g_mtx);
    uint64_t key = titleId & kProgramMask;
    auto it = g_metaCache.find(key);
    if (it == g_metaCache.end()) {
        Meta m;
        fetchMeta(key, m);
        it = g_metaCache.emplace(key, m).first;
    }
    if (!it->second.ok) return false;
    name = it->second.name;
    author = it->second.author;
    version = it->second.version;
    return true;
}

std::vector<InstalledTitle> listInstalled() {
    std::vector<InstalledTitle> out;
    std::lock_guard<std::mutex> lk(g_mtx);
    if (!g_nsOk) { applog::add("sysinfo: listInstalled uebersprungen (ns nicht init)"); return out; }

    static constexpr s32 kBatch = 64;
    NsApplicationRecord records[kBatch];
    s32 offset = 0;
    bool loggedFirst = false;
    while (true) {
        s32 count = 0;
        Result rc = nsListApplicationRecord(records, kBatch, offset, &count);
        if (!loggedFirst) { logrc("nsListApplicationRecord", rc); loggedFirst = true; }
        if (R_FAILED(rc) || count <= 0) break;
        for (s32 i = 0; i < count; i++) {
            uint64_t tid = records[i].application_id & kProgramMask;
            InstalledTitle t;
            t.titleId = tid;
            // Metadaten (gepuffert), sonst Hex-ID als Ersatzname.
            auto mit = g_metaCache.find(tid);
            if (mit == g_metaCache.end()) {
                Meta m;
                fetchMeta(tid, m);
                mit = g_metaCache.emplace(tid, m).first;
            }
            if (mit->second.ok && !mit->second.name.empty()) {
                t.name = mit->second.name;
                t.author = mit->second.author;
                t.version = mit->second.version;
            } else {
                t.name = hex16(tid);
            }
            out.push_back(std::move(t));
        }
        offset += count;
        if (count < kBatch) break;
    }
    logmsg("sysinfo: installierte Spiele = %ld", (long)out.size());

    std::sort(out.begin(), out.end(), [](const InstalledTitle& a,
                                         const InstalledTitle& b) {
        // case-insensitiv nach Name, dann nach Title-ID
        std::string x = a.name, y = b.name;
        std::transform(x.begin(), x.end(), x.begin(), ::tolower);
        std::transform(y.begin(), y.end(), y.begin(), ::tolower);
        if (x != y) return x < y;
        return a.titleId < b.titleId;
    });
    return out;
}

RunningGame currentGame() {
    RunningGame g;
    std::lock_guard<std::mutex> lk(g_mtx);

    // 1) Vordergrund-PID + Title-ID via pm (nicht-intrusiv, kein Debugger).
    u64 pid = 0, tid = 0;
    bool havePid = false;
    if (g_pmOk && R_SUCCEEDED(pmdmntGetApplicationProcessId(&pid)) && pid != 0) {
        havePid = true;
        pminfoGetProgramId(&tid, pid);
    }

    if (!havePid || tid == 0) {
        // Kein Anwendungsprozess -> kein Spiel aktiv.
        g.running = false;
        return g;
    }

    g.running = true;
    g.titleId = tid;

    // 2) Build-ID: primaer ldr:dmnt (Haupt-NSO), Fallback dmnt:cht.
    bool gotBid = false;
    {
        LoaderModuleInfo mods[2];
        std::memset(mods, 0, sizeof(mods));
        s32 num = 0;
        if (R_SUCCEEDED(ldrDmntInitialize())) {
            Result rc = ldrDmntGetProcessModuleInfo(pid, mods,
                                                    (s32)(sizeof(mods) / sizeof(mods[0])),
                                                    &num);
            ldrDmntExit();
            if (R_SUCCEEDED(rc) && num > 0) {
                // [0]=rtld, [1]=Haupt-NSO wenn zwei Module vorhanden sind.
                const LoaderModuleInfo* m = (num >= 2) ? &mods[1] : &mods[0];
                g.buildId = buildIdHex(m->build_id, 8);
                gotBid = true;
            }
        }
    }

    if (!gotBid) {
        // Fallback: dmnt:cht liefert main_nso_build_id direkt (Atmosphere).
        if (R_SUCCEEDED(chtOpen())) {
            bool has = false;
            chtHasProcess(&has);
            if (!has) chtForceOpen();
            DmntCheatProcessMetadata md;
            std::memset(&md, 0, sizeof(md));
            if (R_SUCCEEDED(chtGetMetadata(&md))) {
                if (md.title_id != 0) g.titleId = md.title_id;
                g.buildId = buildIdHex(md.main_nso_build_id, 8);
                gotBid = !g.buildId.empty();
            }
        }
        if (!gotBid) g.note = "no-build-id";
    }

    // 3) Name/Version aus dem Cache/ns (ohne Rekursion in den Mutex).
    {
        uint64_t key = g.titleId & kProgramMask;
        auto it = g_metaCache.find(key);
        if (it == g_metaCache.end()) {
            Meta m;
            fetchMeta(key, m);
            it = g_metaCache.emplace(key, m).first;
        }
        if (it->second.ok) {
            g.name = it->second.name;
            g.version = it->second.version;
        }
    }
    return g;
}

} // namespace sysinfo
