#pragma once
#include <string>
#include <cctype>

// ---------------------------------------------------------------------------
// Sehr kleiner, gezielter "JSON"-Feldextraktor.
//
// Wir brauchen KEINEN vollstaendigen JSON-Parser: die GitHub Releases-API
// liefert ein festes, bekanntes Schema. Diese Helfer suchen gezielt nach dem
// Asset-Objekt mit einem bestimmten "name"-Feld (z.B. "switch-cheats.zip")
// innerhalb des "assets"-Arrays und lesen daraus einzelne String-Felder aus.
//
// Vorgehen:
//   1. findAssetObject() findet den vollstaendigen (klammer-balancierten)
//      Text des Asset-Objekts, dessen "name" Feld == assetName ist.
//   2. extractJsonString() liest ein "key": "value" Feld aus einem
//      beliebigen JSON-Text-Ausschnitt (funktioniert auch auf dem ganzen
//      Response-Text oder auf einem einzelnen Objekt).
// ---------------------------------------------------------------------------

namespace jsonutil {

// Liefert den Inhalt eines "key": "value" Strings aus json (erste Fundstelle).
// Gibt "" zurueck, wenn nicht gefunden. Escapte Anfuehrungszeichen (\") werden
// nicht "entescaped" - fuer URLs/ISO-Datumsangaben nicht noetig.
inline std::string extractJsonString(const std::string& json, const std::string& key) {
    std::string pattern = "\"" + key + "\"";
    size_t pos = json.find(pattern);
    if (pos == std::string::npos) return "";
    pos += pattern.size();

    // ueberspringe Leerzeichen und den Doppelpunkt
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t' || json[pos] == '\n' || json[pos] == '\r'))
        pos++;
    if (pos >= json.size() || json[pos] != ':') return "";
    pos++;
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t' || json[pos] == '\n' || json[pos] == '\r'))
        pos++;

    if (pos >= json.size() || json[pos] != '"') return "";
    pos++; // erstes Anfuehrungszeichen ueberspringen

    std::string out;
    while (pos < json.size() && json[pos] != '"') {
        if (json[pos] == '\\' && pos + 1 < json.size()) {
            // einfaches Unescaping der gaengigen Faelle (\/  \\  \")
            char next = json[pos + 1];
            if (next == '/' || next == '\\' || next == '"') {
                out += next;
                pos += 2;
                continue;
            }
        }
        out += json[pos];
        pos++;
    }
    return out;
}

// Liest ein numerisches "key": 12345 Feld aus json (erste Fundstelle).
// Gibt def zurueck, wenn der Key fehlt oder kein Zahlenwert folgt.
inline long long extractJsonNumber(const std::string& json, const std::string& key, long long def = 0) {
    std::string pattern = "\"" + key + "\"";
    size_t pos = json.find(pattern);
    if (pos == std::string::npos) return def;
    pos += pattern.size();
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t' || json[pos] == '\n' || json[pos] == '\r'))
        pos++;
    if (pos >= json.size() || json[pos] != ':') return def;
    pos++;
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t' || json[pos] == '\n' || json[pos] == '\r'))
        pos++;
    bool neg = false;
    if (pos < json.size() && json[pos] == '-') { neg = true; pos++; }
    if (pos >= json.size() || !std::isdigit(static_cast<unsigned char>(json[pos]))) return def;
    long long v = 0;
    while (pos < json.size() && std::isdigit(static_cast<unsigned char>(json[pos]))) {
        v = v * 10 + (json[pos] - '0');
        pos++;
    }
    return neg ? -v : v;
}

// Findet innerhalb von json das (Klammer-balancierte) Objekt aus dem
// "assets"-Array, dessen "name" Feld genau assetName entspricht.
// Gibt den Objekt-Text (inkl. der umschliessenden { }) zurueck, oder "" wenn
// nichts gefunden wurde.
inline std::string findAssetObject(const std::string& json, const std::string& assetName) {
    size_t assetsPos = json.find("\"assets\"");
    if (assetsPos == std::string::npos) return "";

    size_t arrStart = json.find('[', assetsPos);
    if (arrStart == std::string::npos) return "";

    size_t i = arrStart + 1;
    std::string needle = "\"name\"";
    std::string wantedNameVal = "\"" + assetName + "\"";

    while (i < json.size()) {
        // finde naechstes Array-Element (Objekt) oder das Ende des Arrays
        while (i < json.size() && (json[i] == ' ' || json[i] == ',' || json[i] == '\n' ||
                                    json[i] == '\r' || json[i] == '\t'))
            i++;
        if (i >= json.size() || json[i] == ']') break;
        if (json[i] != '{') { i++; continue; }

        size_t objStart = i;
        int depth = 0;
        size_t j = objStart;
        for (; j < json.size(); j++) {
            if (json[j] == '{') depth++;
            else if (json[j] == '}') {
                depth--;
                if (depth == 0) { j++; break; }
            }
        }
        size_t objEnd = j; // exklusiv
        std::string obj = json.substr(objStart, objEnd - objStart);

        size_t namePos = obj.find(needle);
        if (namePos != std::string::npos) {
            size_t colon = obj.find(':', namePos);
            if (colon != std::string::npos) {
                size_t q1 = obj.find('"', colon + 1);
                if (q1 != std::string::npos && obj.compare(q1, wantedNameVal.size(), wantedNameVal) == 0) {
                    return obj;
                }
            }
        }

        i = objEnd;
    }
    return "";
}

} // namespace jsonutil
