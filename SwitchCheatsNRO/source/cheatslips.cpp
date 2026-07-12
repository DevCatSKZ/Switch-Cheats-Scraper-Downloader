#include "cheatslips.hpp"
#include "settings.hpp"
#include "updater.hpp"
#include "applog.hpp"
#include "i18n.hpp"

#include <cctype>
#include <cstdio>
#include <map>
#include <sys/stat.h>

using i18n::tr;

namespace cheatslips {

static const char* kApiBase = "https://www.cheatslips.com/api/v1";
static const char* kPlaceholder = "Please register and send APIToken";

std::string token() { return settings::get("cheatslips_token"); }
void setToken(const std::string& t) { settings::set("cheatslips_token", t); }
bool hasToken() { return !token().empty(); }

// ---- Mini-JSON-Helfer -------------------------------------------------------
// Die API-Antwort ist {"cheats":[{"buildid":"...","content":"..."},...]}.
// content enthaelt Escapes (\n, \", \uXXXX) - hier korrekt entescapen.
static std::string unescape(const std::string& in) {
    std::string out;
    out.reserve(in.size());
    for (size_t i = 0; i < in.size(); i++) {
        char c = in[i];
        if (c != '\\' || i + 1 >= in.size()) {
            out += c;
            continue;
        }
        char n = in[++i];
        switch (n) {
            case 'n': out += '\n'; break;
            case 'r': out += '\r'; break;
            case 't': out += '\t'; break;
            case '"': out += '"'; break;
            case '\\': out += '\\'; break;
            case '/': out += '/'; break;
            case 'b': case 'f': break;
            case 'u': {
                if (i + 4 < in.size()) {
                    unsigned int cp = 0;
                    bool okhex = true;
                    for (int k = 1; k <= 4; k++) {
                        char h = in[i + k];
                        cp <<= 4;
                        if (h >= '0' && h <= '9') cp |= (h - '0');
                        else if (h >= 'a' && h <= 'f') cp |= (h - 'a' + 10);
                        else if (h >= 'A' && h <= 'F') cp |= (h - 'A' + 10);
                        else { okhex = false; break; }
                    }
                    if (okhex) {
                        i += 4;
                        // UTF-8-Encoding (BMP reicht fuer Cheat-Texte)
                        if (cp < 0x80) out += static_cast<char>(cp);
                        else if (cp < 0x800) {
                            out += static_cast<char>(0xC0 | (cp >> 6));
                            out += static_cast<char>(0x80 | (cp & 0x3F));
                        } else {
                            out += static_cast<char>(0xE0 | (cp >> 12));
                            out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
                            out += static_cast<char>(0x80 | (cp & 0x3F));
                        }
                    }
                }
                break;
            }
            default: out += n; break;
        }
    }
    return out;
}

// Liest den ROHEN (nicht entescapten) String-Wert eines Keys ab Position pos
// innerhalb eines Objekt-Texts. found=false wenn nicht vorhanden.
static std::string rawString(const std::string& obj, const std::string& key, bool& found) {
    found = false;
    std::string pat = "\"" + key + "\"";
    size_t p = obj.find(pat);
    if (p == std::string::npos) return "";
    p = obj.find(':', p + pat.size());
    if (p == std::string::npos) return "";
    p++;
    while (p < obj.size() && (obj[p] == ' ' || obj[p] == '\n' || obj[p] == '\r' || obj[p] == '\t')) p++;
    if (p >= obj.size() || obj[p] != '"') return "";
    p++;
    std::string out;
    while (p < obj.size()) {
        char c = obj[p];
        if (c == '\\' && p + 1 < obj.size()) {
            out += c;
            out += obj[p + 1];
            p += 2;
            continue;
        }
        if (c == '"') break;
        out += c;
        p++;
    }
    found = true;
    return out;
}

// Iteriert die Objekte des "cheats"-Arrays (klammer-balanciert).
static std::vector<std::string> cheatObjects(const std::string& json) {
    std::vector<std::string> out;
    size_t arr = json.find("\"cheats\"");
    if (arr == std::string::npos) return out;
    arr = json.find('[', arr);
    if (arr == std::string::npos) return out;
    size_t i = arr + 1;
    int strDepth = 0;
    while (i < json.size() && json[i] != ']') {
        if (json[i] == '{') {
            int depth = 0;
            size_t start = i;
            bool inStr = false;
            for (; i < json.size(); i++) {
                char c = json[i];
                if (inStr) {
                    if (c == '\\') i++;
                    else if (c == '"') inStr = false;
                } else if (c == '"') {
                    inStr = true;
                } else if (c == '{') {
                    depth++;
                } else if (c == '}') {
                    depth--;
                    if (depth == 0) { i++; break; }
                }
            }
            out.push_back(json.substr(start, i - start));
        } else {
            i++;
        }
    }
    (void)strDepth;
    return out;
}

static void makeDirs(const std::string& tid) {
    mkdir("sdmc:/atmosphere", 0777);
    mkdir("sdmc:/atmosphere/contents", 0777);
    mkdir(("sdmc:/atmosphere/contents/" + tid).c_str(), 0777);
    mkdir(("sdmc:/atmosphere/contents/" + tid + "/cheats").c_str(), 0777);
}

static std::string upper(std::string s) {
    for (auto& c : s) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    return s;
}

GameCheats fetchAndInstall(const std::string& titleId) {
    GameCheats r;
    std::string tid = upper(titleId);
    std::string url = std::string(kApiBase) + "/cheats/" + tid;
    std::string hdr = hasToken() ? ("X-API-TOKEN: " + token()) : "";
    std::string body, err;
    long code = updater::httpGet(url, hdr, body, err);
    if (code < 0) {
        r.error = err;
        return r;
    }
    if (code == 401 || code == 403) {
        r.error = tr("cs.badtoken");
        return r;
    }
    if (code == 404) {
        r.ok = true; // Spiel nicht auf cheatslips - kein Fehler
        r.error = tr("cs.notfound");
        return r;
    }
    if (code != 200) {
        r.error = std::string(tr("err.serverHttp")) + std::to_string(code);
        return r;
    }

    // Inhalte pro Build sammeln (mehrere Cheats je Build aneinanderhaengen).
    std::map<std::string, std::string> perBuild;
    for (const auto& obj : cheatObjects(body)) {
        bool fb = false, fc = false;
        std::string bid = upper(unescape(rawString(obj, "buildid", fb)));
        std::string content = unescape(rawString(obj, "content", fc));
        if (!fb || bid.size() != 16 || !fc || content.empty()) continue;
        r.cheatsSeen++;
        if (content.find(kPlaceholder) != std::string::npos) {
            r.skippedNoToken++;
            continue;
        }
        std::string& acc = perBuild[bid];
        if (!acc.empty() && acc.back() != '\n') acc += "\n";
        if (!acc.empty()) acc += "\n";
        acc += content;
    }

    for (const auto& [bid, content] : perBuild) {
        makeDirs(tid);
        std::string path = "sdmc:/atmosphere/contents/" + tid + "/cheats/" + bid + ".txt";
        FILE* f = fopen(path.c_str(), "wb");
        if (!f) continue;
        fwrite(content.data(), 1, content.size(), f);
        fclose(f);
        r.filesWritten++;
    }

    r.ok = true;
    return r;
}

bool tokenWorks(std::string& detail) {
    // Referenztitel wie am Desktop (Final Fantasy Tactics).
    std::string url = std::string(kApiBase) + "/cheats/010038B015560000";
    std::string hdr = hasToken() ? ("X-API-TOKEN: " + token()) : "";
    std::string body, err;
    long code = updater::httpGet(url, hdr, body, err);
    if (code < 0) {
        detail = err;
        return false;
    }
    if (code != 200) {
        detail = std::string(tr("err.serverHttp")) + std::to_string(code);
        return false;
    }
    if (body.find(kPlaceholder) != std::string::npos) {
        detail = tr("cs.badtoken");
        return false;
    }
    detail = tr("cs.tokenok");
    return true;
}

} // namespace cheatslips
