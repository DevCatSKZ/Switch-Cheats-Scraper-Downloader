// ---------------------------------------------------------------------------
// saves.cpp - Speicherstaende erkennen, sichern, wiederherstellen.
// Referenz: Checkpoint (switch/source/{title,filesystem,io,directory}.cpp).
// ---------------------------------------------------------------------------
#include "saves.hpp"
#include "sysinfo.hpp"
#include "config.hpp"

#include <switch.h>
#include <cstring>
#include <cstdio>
#include <ctime>
#include <new>
#include <algorithm>
#include <dirent.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {

constexpr const char* kMount = "save";          // Mount-Name -> "save:/..."
constexpr uint64_t kMask = 0xFFFFFFFFFFFFFFF0ULL;
constexpr size_t kBuf = 0x80000;                // 512 KB Kopierpuffer

std::string root() { return std::string(cfg::kAppDir) + "/saves"; }

bool uidZero(const AccountUid& u) { return u.uid[0] == 0 && u.uid[1] == 0; }

// mkdir -p fuer sdmc:/... (Geraetepraefix bleibt unberuehrt).
void mkdirs(const std::string& path) {
    size_t start = path.find(":/");
    start = (start == std::string::npos) ? 0 : start + 2;
    for (size_t i = start; i <= path.size(); i++) {
        if (i == path.size() || path[i] == '/') {
            if (i == 0) continue;
            std::string sub = path.substr(0, i);
            if (!sub.empty() && sub.back() != '/') ::mkdir(sub.c_str(), 0777);
        }
    }
}

bool isDir(const std::string& p) {
    struct stat st;
    if (::stat(p.c_str(), &st) != 0) return false;
    return S_ISDIR(st.st_mode);
}

// Eine Datei kopieren. commitSave=true -> nach dem Schreiben in "save:/"
// committen (Checkpoint sichert so jede einzelne Datei ab).
bool copyFile(const std::string& src, const std::string& dst,
              char* buf, bool commitSave, const saves::LogFn& log) {
    FILE* in = fopen(src.c_str(), "rb");
    if (!in) return false;
    FILE* out = fopen(dst.c_str(), "wb");
    if (!out) { fclose(in); return false; }
    size_t n;
    bool ok = true;
    while ((n = fread(buf, 1, kBuf, in)) > 0) {
        if (fwrite(buf, 1, n, out) != n) { ok = false; break; }
    }
    fclose(in);
    fclose(out);
    if (ok && commitSave) fsdevCommitDevice(kMount);
    return ok;
}

// Verzeichnis rekursiv kopieren (dst wird angelegt).
bool copyDir(const std::string& src, const std::string& dst,
             char* buf, bool commitSave, const saves::LogFn& log) {
    ::mkdir(dst.c_str(), 0777);
    DIR* d = opendir(src.c_str());
    if (!d) return false;
    bool ok = true;
    struct dirent* ent;
    while ((ent = readdir(d)) != nullptr) {
        std::string name = ent->d_name;
        if (name == "." || name == "..") continue;
        std::string s = src + "/" + name;
        std::string t = dst + "/" + name;
        if (isDir(s)) {
            if (!copyDir(s, t, buf, commitSave, log)) { ok = false; }
        } else {
            if (log) log(name);
            if (!copyFile(s, t, buf, commitSave, log)) { ok = false; }
        }
    }
    closedir(d);
    return ok;
}

// Inhalt eines Verzeichnisses loeschen (das Verzeichnis selbst bleibt).
bool rmContents(const std::string& path) {
    DIR* d = opendir(path.c_str());
    if (!d) return false;
    bool ok = true;
    struct dirent* ent;
    while ((ent = readdir(d)) != nullptr) {
        std::string name = ent->d_name;
        if (name == "." || name == "..") continue;
        std::string p = path + "/" + name;
        if (isDir(p)) {
            rmContents(p);
            if (::rmdir(p.c_str()) != 0) ok = false;
        } else {
            if (::remove(p.c_str()) != 0) ok = false;
        }
    }
    closedir(d);
    return ok;
}

std::string userName(const AccountUid& uid) {
    if (uidZero(uid)) return "";
    AccountProfile prof;
    if (R_FAILED(accountGetProfile(&prof, uid))) return "";
    AccountProfileBase base;
    std::memset(&base, 0, sizeof(base));
    Result rc = accountProfileGet(&prof, nullptr, &base);
    accountProfileClose(&prof);
    if (R_FAILED(rc)) return "";
    char nm[0x21] = {0};
    std::memcpy(nm, base.nickname, 0x20);
    return std::string(nm);
}

// Save (titleId,uid) mounten -> "save:/". false bei Fehler.
bool mountSave(uint64_t titleId, const AccountUid& uid, std::string& err) {
    FsFileSystem fs;
    Result rc = fsOpen_SaveData(&fs, titleId, uid);
    if (R_FAILED(rc)) { err = "open-save"; return false; }
    if (fsdevMountDevice(kMount, fs) < 0) { err = "mount"; return false; }
    return true;
}
void unmountSave() { fsdevUnmountDevice(kMount); }

std::string timestampLabel() {
    time_t t = time(nullptr);
    if (t > 0) {
        struct tm tmv;
        localtime_r(&t, &tmv);
        char b[32];
        if (strftime(b, sizeof(b), "%Y-%m-%d_%H-%M-%S", &tmv) > 0)
            return std::string(b);
    }
    return "backup";
}

} // namespace

namespace saves {

std::vector<SaveEntry> listSaves() {
    sysinfo::init();
    std::vector<SaveEntry> out;

    FsSaveDataInfoReader reader;
    if (R_FAILED(fsOpenSaveDataInfoReader(&reader, FsSaveDataSpaceId_User)))
        return out;

    FsSaveDataInfo info;
    s64 total = 0;
    while (R_SUCCEEDED(fsSaveDataInfoReaderRead(&reader, &info, 1, &total)) &&
           total > 0) {
        if (info.save_data_type != FsSaveDataType_Account) continue;
        SaveEntry e;
        e.titleId = info.application_id;
        e.uid = info.uid;
        out.push_back(std::move(e));
    }
    fsSaveDataInfoReaderClose(&reader);

    // Nutzer-Nicknames + Spielnamen aufloesen (gepuffert in sysinfo).
    for (auto& e : out) {
        e.user = userName(e.uid);
        std::string name, author, version;
        if (sysinfo::titleMeta(e.titleId, name, author, version) && !name.empty())
            e.game = name;
        else
            e.game = sysinfo::hex16(e.titleId);
    }

    std::sort(out.begin(), out.end(), [](const SaveEntry& a, const SaveEntry& b) {
        if (a.game != b.game) return a.game < b.game;
        return a.user < b.user;
    });
    return out;
}

std::vector<SaveEntry> savesForTitle(uint64_t titleId) {
    std::vector<SaveEntry> out;
    for (auto& e : listSaves()) {
        if ((e.titleId & kMask) == (titleId & kMask)) out.push_back(e);
    }
    return out;
}

std::string backupDir(uint64_t titleId) {
    return root() + "/" + sysinfo::hex16(titleId & kMask);
}

std::vector<Backup> listBackups(uint64_t titleId) {
    std::vector<Backup> out;
    std::string dir = backupDir(titleId);
    DIR* d = opendir(dir.c_str());
    if (!d) return out;
    struct dirent* ent;
    while ((ent = readdir(d)) != nullptr) {
        std::string name = ent->d_name;
        if (name == "." || name == "..") continue;
        std::string p = dir + "/" + name;
        if (isDir(p)) out.push_back({p, name});
    }
    closedir(d);
    // Neueste zuerst (Zeitstempel-Namen sortieren chronologisch).
    std::sort(out.begin(), out.end(), [](const Backup& a, const Backup& b) {
        return a.label > b.label;
    });
    return out;
}

bool backup(const SaveEntry& e, std::string& outPath, std::string& err,
            const LogFn& log) {
    sysinfo::init();
    if (!mountSave(e.titleId, e.uid, err)) return false;

    std::string dst = backupDir(e.titleId) + "/" + timestampLabel();
    // Bei identischem Zeitstempel: bestehenden Ordner ueberschreiben.
    if (isDir(dst)) { rmContents(dst); ::rmdir(dst.c_str()); }
    mkdirs(dst);

    char* buf = new (std::nothrow) char[kBuf];
    if (!buf) { unmountSave(); err = "oom"; return false; }
    // Kopieren save:/ -> sdmc (kein Commit noetig, Ziel ist sdmc).
    bool ok = copyDir("save:/", dst, buf, /*commitSave=*/false, log);
    delete[] buf;
    unmountSave();

    if (!ok) { err = "copy"; return false; }
    outPath = dst;
    return true;
}

bool restore(const SaveEntry& e, const std::string& backupPath,
             std::string& err, const LogFn& log) {
    sysinfo::init();
    if (!isDir(backupPath)) { err = "no-backup"; return false; }
    if (!mountSave(e.titleId, e.uid, err)) return false;

    char* buf = new (std::nothrow) char[kBuf];
    if (!buf) { unmountSave(); err = "oom"; return false; }

    // 1) Save vollstaendig leeren (keine Altdateien zuruecklassen).
    rmContents("save:/");
    fsdevCommitDevice(kMount);
    // 2) Backup zurueckspielen (commitSave sichert jede Datei ab).
    bool ok = copyDir(backupPath, "save:/", buf, /*commitSave=*/true, log);
    delete[] buf;
    // 3) Abschliessender Commit - OHNE diesen gehen alle Schreibvorgaenge
    //    beim Unmount verloren (die zentrale Checkpoint-Lehre).
    Result rc = fsdevCommitDevice(kMount);
    unmountSave();

    if (!ok) { err = "copy"; return false; }
    if (R_FAILED(rc)) { err = "commit"; return false; }
    return true;
}

bool deleteBackup(const std::string& backupPath) {
    if (!isDir(backupPath)) return false;
    rmContents(backupPath);
    return ::rmdir(backupPath.c_str()) == 0;
}

} // namespace saves
