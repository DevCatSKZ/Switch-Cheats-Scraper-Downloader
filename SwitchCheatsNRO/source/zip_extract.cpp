#include "zip_extract.hpp"
#include "i18n.hpp"

#include "unzip.h"

#include <sys/stat.h>
#include <cstring>
#include <cstdio>
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

} // namespace zipextract
