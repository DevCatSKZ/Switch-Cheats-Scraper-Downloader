#include "zip_extract.hpp"
#include "i18n.hpp"

#include "unzip.h"
#include "zip.h"

#include <sys/stat.h>
#include <dirent.h>
#include <cctype>
#include <cstring>
#include <cstdio>
#include <set>
#include <vector>

using i18n::tr;

namespace zipextract {

// Legt alle fehlenden Verzeichnis-Teile eines Dateipfads an (mkdir -p auf den
// Ordneranteil von filePath). filePath ist z.B. "sdmc:/atmosphere/contents/..".
static void makeDirsForFile(const std::string& filePath) {
    // Suche das letzte '/' -> alles davor ist der Ordnerpfad.
    size_t lastSlash = filePath.find_last_of('/');
    if (lastSlash == std::string::npos) return;
    std::string dirPath = filePath.substr(0, lastSlash);

    // "sdmc:/a/b/c" -> baue schrittweise "sdmc:/a", "sdmc:/a/b", "sdmc:/a/b/c" auf.
    size_t pos = 0;
    // "sdmc:/" enthaelt bereits einen Doppelpunkt+Slash; wir suchen ab dort weiter.
    size_t start = dirPath.find(":/");
    if (start == std::string::npos) start = 0; else start += 2;

    pos = start;
    while (true) {
        size_t slash = dirPath.find('/', pos);
        std::string partial = (slash == std::string::npos) ? dirPath : dirPath.substr(0, slash);
        if (!partial.empty()) {
            mkdir(partial.c_str(), 0777);
        }
        if (slash == std::string::npos) break;
        pos = slash + 1;
    }
}

ExtractResult extractZipToPath(const std::string& zipPath, const std::string& destRoot, const ProgressCb& progress) {
    ExtractResult result;

    unzFile zf = unzOpen64(zipPath.c_str());
    if (!zf) {
        result.error = std::string(tr("err.zipOpen")) + zipPath;
        return result;
    }

    unz_global_info64 globalInfo;
    if (unzGetGlobalInfo64(zf, &globalInfo) != UNZ_OK) {
        unzClose(zf);
        result.error = tr("err.zipBroken");
        return result;
    }

    int total = static_cast<int>(globalInfo.number_entry);
    int index = 0;

    if (unzGoToFirstFile(zf) != UNZ_OK) {
        unzClose(zf);
        result.error = tr("err.zipBroken");
        return result;
    }

    std::vector<char> buffer(64 * 1024);

    do {
        char nameBuf[1024] = {0};
        unz_file_info64 fileInfo;
        if (unzGetCurrentFileInfo64(zf, &fileInfo, nameBuf, sizeof(nameBuf) - 1,
                                     nullptr, 0, nullptr, 0) != UNZ_OK) {
            result.error = tr("err.zipBroken");
            unzClose(zf);
            return result;
        }

        std::string entryName(nameBuf);
        index++;

        if (progress && !progress(index, total, entryName)) {
            result.cancelled = true;
            result.error = "cancelled";
            unzClose(zf);
            return result;
        }

        // Verzeichnis-Eintraege (enden auf '/') ueberspringen - Ordner werden
        // beim Anlegen der Zieldateien automatisch erstellt.
        bool isDir = !entryName.empty() && entryName.back() == '/';

        if (!isDir) {
            if (!isSafeEntryName(entryName)) {
                result.error = std::string(tr("err.unsafePath")) + entryName;
                unzClose(zf);
                return result;
            }

            std::string destPath = destRoot;
            if (!destPath.empty() && destPath.back() != '/') destPath += '/';
            destPath += entryName;

            makeDirsForFile(destPath);

            if (unzOpenCurrentFile(zf) != UNZ_OK) {
                result.error = std::string(tr("err.zipEntry")) + entryName;
                unzClose(zf);
                return result;
            }

            FILE* out = fopen(destPath.c_str(), "wb");
            if (!out) {
                unzCloseCurrentFile(zf);
                result.error = std::string(tr("err.createFile")) + destPath;
                unzClose(zf);
                return result;
            }

            bool fileOk = true;
            int readBytes = 0;
            do {
                readBytes = unzReadCurrentFile(zf, buffer.data(), static_cast<unsigned int>(buffer.size()));
                if (readBytes < 0) {
                    result.error = std::string(tr("err.zipEntry")) + entryName;
                    fileOk = false;
                    break;
                }
                if (readBytes > 0 &&
                    fwrite(buffer.data(), 1, static_cast<size_t>(readBytes), out) != static_cast<size_t>(readBytes)) {
                    // z.B. SD-Karte voll - NICHT still als Erfolg werten.
                    result.error = std::string(tr("err.writeFile")) + destPath;
                    fileOk = false;
                    break;
                }
            } while (readBytes > 0);

            unzCloseCurrentFile(zf);
            if (fclose(out) != 0 && fileOk) {
                result.error = std::string(tr("err.writeFile")) + destPath;
                fileOk = false;
            }

            if (!fileOk) {
                remove(destPath.c_str()); // halb geschriebene Datei nicht liegen lassen
                unzClose(zf);
                return result;
            }
            result.filesWritten++;
        }

    } while (unzGoToNextFile(zf) == UNZ_OK);

    unzClose(zf);
    result.ok = true;
    return result;
}

// ".../<TID>/cheats/<BID>.txt" am Pfadende erkennen (16 Hex je ID, Praefix
// beliebig) - das Muster aller Community-Archive (Hamlet/Sthetix/Breeze).
static bool isHex16(const std::string& s) {
    if (s.size() != 16) return false;
    for (char c : s) {
        if (!std::isxdigit(static_cast<unsigned char>(c))) return false;
    }
    return true;
}
static bool matchCheatEntry(const std::string& name, std::string& tid, std::string& bid) {
    if (name.size() < 16 + 8 + 16 + 4) return false;
    if (name.compare(name.size() - 4, 4, ".txt") != 0 &&
        name.compare(name.size() - 4, 4, ".TXT") != 0) return false;
    std::string stem = name.substr(0, name.size() - 4);
    size_t s1 = stem.find_last_of('/');
    if (s1 == std::string::npos) return false;
    bid = stem.substr(s1 + 1);
    std::string rest = stem.substr(0, s1);
    size_t s2 = rest.find_last_of('/');
    if (s2 == std::string::npos) return false;
    std::string cheatsDir = rest.substr(s2 + 1);
    if (cheatsDir != "cheats") return false;
    std::string rest2 = rest.substr(0, s2);
    size_t s3 = rest2.find_last_of('/');
    tid = (s3 == std::string::npos) ? rest2 : rest2.substr(s3 + 1);
    if (!isHex16(tid) || !isHex16(bid)) return false;
    for (auto& c : tid) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    for (auto& c : bid) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    return true;
}

ArchiveResult extractCheatArchive(const std::string& zipPath, const ProgressCb& progress) {
    ArchiveResult result;

    unzFile zf = unzOpen64(zipPath.c_str());
    if (!zf) {
        result.error = std::string(tr("err.zipOpen")) + zipPath;
        return result;
    }
    unz_global_info64 globalInfo;
    if (unzGetGlobalInfo64(zf, &globalInfo) != UNZ_OK || unzGoToFirstFile(zf) != UNZ_OK) {
        unzClose(zf);
        result.error = tr("err.zipBroken");
        return result;
    }

    int total = static_cast<int>(globalInfo.number_entry);
    int index = 0;
    std::vector<char> buffer(64 * 1024);
    std::set<std::string> games;

    do {
        char nameBuf[1024] = {0};
        unz_file_info64 fileInfo;
        if (unzGetCurrentFileInfo64(zf, &fileInfo, nameBuf, sizeof(nameBuf) - 1,
                                     nullptr, 0, nullptr, 0) != UNZ_OK) {
            result.error = tr("err.zipBroken");
            unzClose(zf);
            return result;
        }
        std::string entryName(nameBuf);
        index++;
        if (progress && !progress(index, total, entryName)) {
            result.cancelled = true;
            result.error = "cancelled";
            unzClose(zf);
            return result;
        }

        std::string tid, bid;
        if (!entryName.empty() && entryName.back() != '/' &&
            matchCheatEntry(entryName, tid, bid)) {
            std::string destPath = "sdmc:/atmosphere/contents/" + tid + "/cheats/" + bid + ".txt";
            makeDirsForFile(destPath);
            if (unzOpenCurrentFile(zf) == UNZ_OK) {
                FILE* out = fopen(destPath.c_str(), "wb");
                if (out) {
                    bool fileOk = true;
                    int readBytes = 0;
                    do {
                        readBytes = unzReadCurrentFile(zf, buffer.data(),
                                                       static_cast<unsigned int>(buffer.size()));
                        if (readBytes < 0) { fileOk = false; break; }
                        if (readBytes > 0 &&
                            fwrite(buffer.data(), 1, static_cast<size_t>(readBytes), out) !=
                                static_cast<size_t>(readBytes)) {
                            result.error = std::string(tr("err.writeFile")) + destPath;
                            fileOk = false;
                            break;
                        }
                    } while (readBytes > 0);
                    if (fclose(out) != 0) fileOk = false;
                    if (fileOk) {
                        result.filesWritten++;
                        games.insert(tid);
                    } else {
                        remove(destPath.c_str());
                        if (!result.error.empty()) { // SD voll -> abbrechen
                            unzCloseCurrentFile(zf);
                            unzClose(zf);
                            return result;
                        }
                    }
                }
                unzCloseCurrentFile(zf);
            }
        }
    } while (unzGoToNextFile(zf) == UNZ_OK);

    unzClose(zf);
    result.gamesSeen = static_cast<int>(games.size());
    result.ok = true;
    return result;
}

ExtractResult zipInstalledCheats(const std::string& zipPath, const ProgressCb& progress) {
    ExtractResult result;

    zipFile zout = zipOpen64(zipPath.c_str(), APPEND_STATUS_CREATE);
    if (!zout) {
        result.error = std::string(tr("err.createFile")) + zipPath;
        return result;
    }

    std::string root = "sdmc:/atmosphere/contents";
    DIR* d = opendir(root.c_str());
    int index = 0;
    std::vector<char> buffer(64 * 1024);
    if (d) {
        struct dirent* e;
        while ((e = readdir(d)) != nullptr) {
            std::string tid = e->d_name;
            if (tid == "." || tid == ".." || !isHex16(tid)) continue;
            std::string cheatsDir = root + "/" + tid + "/cheats";
            DIR* cd = opendir(cheatsDir.c_str());
            if (!cd) continue;
            struct dirent* ce;
            while ((ce = readdir(cd)) != nullptr) {
                std::string fn = ce->d_name;
                if (fn.size() < 5 || fn.compare(fn.size() - 4, 4, ".txt") != 0) continue;
                index++;
                if (progress && !progress(index, 0, fn)) {
                    result.cancelled = true;
                    closedir(cd);
                    closedir(d);
                    zipClose(zout, nullptr);
                    remove(zipPath.c_str());
                    return result;
                }
                std::string srcPath = cheatsDir + "/" + fn;
                FILE* in = fopen(srcPath.c_str(), "rb");
                if (!in) continue;
                std::string entry = "atmosphere/contents/" + tid + "/cheats/" + fn;
                if (zipOpenNewFileInZip64(zout, entry.c_str(), nullptr, nullptr, 0,
                                          nullptr, 0, nullptr, Z_DEFLATED,
                                          Z_DEFAULT_COMPRESSION, 0) == ZIP_OK) {
                    size_t n;
                    while ((n = fread(buffer.data(), 1, buffer.size(), in)) > 0) {
                        zipWriteInFileInZip(zout, buffer.data(), static_cast<unsigned int>(n));
                    }
                    zipCloseFileInZip(zout);
                    result.filesWritten++;
                }
                fclose(in);
            }
            closedir(cd);
        }
        closedir(d);
    }
    zipClose(zout, nullptr);
    result.ok = true;
    return result;
}

} // namespace zipextract
