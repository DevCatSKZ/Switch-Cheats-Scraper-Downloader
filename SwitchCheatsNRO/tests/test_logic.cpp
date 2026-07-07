// Host-Tests fuer die pure Logik der NRO-App (json_util, version_util,
// isSafeEntryName). Kompiliert ohne Switch-Abhaengigkeiten.
#include "json_util.hpp"
#include "version_util.hpp"
#include "zip_extract.hpp"

#include <cstdio>
#include <string>

static int g_failed = 0;
static int g_passed = 0;

#define CHECK(cond) do { \
    if (cond) { g_passed++; } \
    else { g_failed++; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); } \
} while (0)

#define CHECK_EQ(a, b) do { \
    auto va = (a); auto vb = (b); \
    if (va == vb) { g_passed++; } \
    else { g_failed++; printf("FAIL %s:%d: %s == %s  (got \"%s\", want \"%s\")\n", \
        __FILE__, __LINE__, #a, #b, std::string(va).c_str(), std::string(vb).c_str()); } \
} while (0)

// Realistische (gekuerzte) GitHub-Release-Antwort fuer /releases/tags/nro:
// tag_name ist "nro", die Version steht im Titel ("name"), der author-Block
// kommt VOR name/assets und darf nicht faelschlich getroffen werden.
static const std::string kNroRelease = R"JSON({
  "url": "https://api.github.com/repos/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/2001",
  "assets_url": "https://api.github.com/repos/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/2001/assets",
  "html_url": "https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/tag/nro",
  "id": 2001,
  "author": {
    "login": "DevCatSKZ",
    "id": 12345,
    "node_id": "MDQ6VXNlcjEyMzQ1",
    "avatar_url": "https://avatars.githubusercontent.com/u/12345",
    "type": "User",
    "site_admin": false
  },
  "node_id": "RE_kwDOxyz",
  "tag_name": "nro",
  "target_commitish": "main",
  "name": "v1.2.0",
  "draft": false,
  "prerelease": false,
  "created_at": "2026-07-01T10:00:00Z",
  "published_at": "2026-07-01T10:05:00Z",
  "assets": [
    {
      "url": "https://api.github.com/repos/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/assets/9001",
      "id": 9001,
      "name": "SwitchCheatsDownloader.nro",
      "content_type": "application/octet-stream",
      "size": 3500000,
      "created_at": "2026-07-01T10:04:00Z",
      "updated_at": "2026-07-01T10:04:30Z",
      "browser_download_url": "https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/download/nro/SwitchCheatsDownloader.nro"
    },
    {
      "url": "https://api.github.com/repos/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/assets/9002",
      "id": 9002,
      "name": "other-file.zip",
      "browser_download_url": "https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/download/nro/other-file.zip"
    }
  ],
  "body": "Changelog: name of things \"quoted\" here"
})JSON";

static void testJsonUtil() {
    // extractJsonString: Basisfaelle
    CHECK_EQ(jsonutil::extractJsonString(kNroRelease, "tag_name"), "nro");
    CHECK_EQ(jsonutil::extractJsonString(kNroRelease, "target_commitish"), "main");
    CHECK_EQ(jsonutil::extractJsonString("{\"k\" :  \"v\"}", "k"), "v");
    CHECK_EQ(jsonutil::extractJsonString("{\"k\": \"a\\/b\\\\c\"}", "k"), "a/b\\c");
    CHECK_EQ(jsonutil::extractJsonString("{}", "missing"), "");
    // null-Wert -> "" (kein String)
    CHECK_EQ(jsonutil::extractJsonString("{\"name\": null}", "name"), "");

    // findAssetObject: richtiges Asset trotz mehrerer Eintraege + author-Objekt
    std::string nroAsset = jsonutil::findAssetObject(kNroRelease, "SwitchCheatsDownloader.nro");
    CHECK(!nroAsset.empty());
    CHECK_EQ(jsonutil::extractJsonString(nroAsset, "browser_download_url"),
             "https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/download/nro/SwitchCheatsDownloader.nro");
    CHECK_EQ(jsonutil::extractJsonString(nroAsset, "updated_at"), "2026-07-01T10:04:30Z");

    std::string otherAsset = jsonutil::findAssetObject(kNroRelease, "other-file.zip");
    CHECK(!otherAsset.empty());
    CHECK_EQ(jsonutil::extractJsonString(otherAsset, "browser_download_url"),
             "https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/download/nro/other-file.zip");

    CHECK(jsonutil::findAssetObject(kNroRelease, "does-not-exist.bin").empty());

    // Titel-Extraktion wie in checkAppUpdate(): "name" nur VOR "assets" suchen
    size_t assetsPos = kNroRelease.find("\"assets\"");
    CHECK(assetsPos != std::string::npos);
    std::string head = kNroRelease.substr(0, assetsPos);
    CHECK_EQ(jsonutil::extractJsonString(head, "name"), "v1.2.0");
    // Gegenprobe: "tag_name" darf NICHT als "name" matchen -> der erste
    // "name"-Treffer im Head ist der Release-Titel, nicht "nro".
    CHECK(jsonutil::extractJsonString(head, "name") != "nro");

    // extractJsonNumber: Asset-Groesse, Top-Level-Zahl, Fehlerfaelle
    CHECK(jsonutil::extractJsonNumber(nroAsset, "size", -1) == 3500000);
    CHECK(jsonutil::extractJsonNumber(kNroRelease, "id", -1) == 2001);
    CHECK(jsonutil::extractJsonNumber(kNroRelease, "missing_num", -1) == -1);
    CHECK(jsonutil::extractJsonNumber("{\"k\": -42}", "k", 0) == -42);
    CHECK(jsonutil::extractJsonNumber("{\"k\": \"kein_int\"}", "k", 7) == 7);
    CHECK(jsonutil::extractJsonNumber("{\"k\"  :  123}", "k", 0) == 123);
}

static void testVersionUtil() {
    using versionutil::normalizeVersion;
    using versionutil::isNewerVersion;

    CHECK_EQ(normalizeVersion("v1.2.3"), "1.2.3");
    CHECK_EQ(normalizeVersion("1.2.3"), "1.2.3");
    CHECK_EQ(normalizeVersion("V2.0"), "2.0");
    CHECK_EQ(normalizeVersion(" v1.1.0 Hotfix"), "1.1.0");
    CHECK_EQ(normalizeVersion("v1.1.0-beta"), "1.1.0");
    CHECK_EQ(normalizeVersion("1.2."), "1.2");
    CHECK_EQ(normalizeVersion("nro"), "");        // der alte Bug: tag_name "nro"
    CHECK_EQ(normalizeVersion(""), "");
    CHECK_EQ(normalizeVersion("Release Juli"), "");

    CHECK(isNewerVersion("1.1.0", "1.0.0"));
    CHECK(isNewerVersion("v1.2.0", "1.1.9"));
    CHECK(isNewerVersion("2.0", "1.9.9"));
    CHECK(isNewerVersion("1.0.1", "1.0.0"));
    CHECK(isNewerVersion("1.10.0", "1.9.0"));     // numerisch, nicht lexikografisch
    CHECK(!isNewerVersion("1.0.0", "1.0.0"));
    CHECK(!isNewerVersion("1.0", "1.0.0"));       // fehlende Komponenten = 0
    CHECK(!isNewerVersion("0.9.9", "1.0.0"));
    CHECK(!isNewerVersion("nro", "1.0.0"));       // der alte Bug: nie "neuer"
    CHECK(!isNewerVersion("", "1.0.0"));
}

static void testSafeEntryName() {
    using zipextract::isSafeEntryName;

    // Legitime Eintraege aus der switch-cheats.zip
    CHECK(isSafeEntryName("atmosphere/contents/0100ABCD01234000/cheats/A1B2C3D4E5F60708.txt"));
    CHECK(isSafeEntryName("a/b/c.txt"));
    CHECK(isSafeEntryName("file.txt"));
    CHECK(isSafeEntryName("a..b/c.txt"));      // Punkte IM Namen sind ok
    CHECK(isSafeEntryName("a/..b/c.txt"));     // "..b" ist keine ".."-Komponente
    CHECK(isSafeEntryName("a/b../c.txt"));

    // Zip-Slip / boese Eintraege
    CHECK(!isSafeEntryName(""));
    CHECK(!isSafeEntryName("/absolute/path.txt"));
    CHECK(!isSafeEntryName("../evil.txt"));
    CHECK(!isSafeEntryName("a/../evil.txt"));
    CHECK(!isSafeEntryName("a/b/.."));
    CHECK(!isSafeEntryName(".."));
    CHECK(!isSafeEntryName("sdmc:/evil.txt"));
    CHECK(!isSafeEntryName("C:\\evil.txt"));
    CHECK(!isSafeEntryName("a\\b.txt"));
}

int main() {
    testJsonUtil();
    testVersionUtil();
    testSafeEntryName();
    printf("\n%d passed, %d failed\n", g_passed, g_failed);
    return g_failed == 0 ? 0 : 1;
}
