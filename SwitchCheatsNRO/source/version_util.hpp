#pragma once
#include <string>
#include <vector>
#include <cctype>
#include <cstdlib>

// ---------------------------------------------------------------------------
// Reine Versions-String-Logik fuer das App-Self-Update.
//
// Die Version kommt aus dem TITEL ("name"-Feld) des GitHub-Releases mit dem
// festen Tag "nro" (dessen tag_name ist immer "nro" und traegt daher keine
// Versionsinformation). Erwartetes Titelformat: "v1.1.0" bzw. "1.1.0",
// optional gefolgt von weiterem Text ("v1.1.0 Hotfix").
//
// Bewusst ohne Switch-Abhaengigkeiten gehalten, damit die Logik auf einem
// Host-Rechner testbar ist (siehe CONTINUATION.md).
// ---------------------------------------------------------------------------

namespace versionutil {

// Extrahiert aus einem Release-Titel die nackte Versionsnummer:
// "v1.2.3 Hotfix" -> "1.2.3". Liefert "" wenn keine Version erkennbar ist.
inline std::string normalizeVersion(const std::string& raw) {
    size_t i = 0;
    while (i < raw.size() && (raw[i] == ' ' || raw[i] == '\t')) i++;
    if (i < raw.size() && (raw[i] == 'v' || raw[i] == 'V')) i++;
    size_t start = i;
    while (i < raw.size() && (std::isdigit(static_cast<unsigned char>(raw[i])) || raw[i] == '.')) i++;
    std::string out = raw.substr(start, i - start);
    // Trailing-Punkte abschneiden ("1.2." -> "1.2")
    while (!out.empty() && out.back() == '.') out.pop_back();
    if (out.empty() || !std::isdigit(static_cast<unsigned char>(out[0]))) return "";
    return out;
}

// Vergleicht zwei Versionsstrings numerisch pro Komponente ("X.Y.Z").
// Nicht parsebare Strings gelten als Version 0. true wenn remote > local.
inline bool isNewerVersion(const std::string& remoteRaw, const std::string& localRaw) {
    std::string remote = normalizeVersion(remoteRaw);
    std::string local = normalizeVersion(localRaw);
    if (remote.empty()) return false; // unbekanntes Remote-Format: nie "neuer"

    auto parts = [](const std::string& s) {
        std::vector<int> out;
        size_t start = 0;
        while (start <= s.size()) {
            size_t dot = s.find('.', start);
            std::string tok = (dot == std::string::npos) ? s.substr(start) : s.substr(start, dot - start);
            out.push_back(std::atoi(tok.c_str()));
            if (dot == std::string::npos) break;
            start = dot + 1;
        }
        return out;
    };

    std::vector<int> r = parts(remote);
    std::vector<int> l = parts(local);
    size_t n = (r.size() > l.size()) ? r.size() : l.size();
    for (size_t i = 0; i < n; i++) {
        int rv = (i < r.size()) ? r[i] : 0;
        int lv = (i < l.size()) ? l[i] : 0;
        if (rv != lv) return rv > lv;
    }
    return false;
}

} // namespace versionutil
