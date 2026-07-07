#pragma once

// ---------------------------------------------------------------------------
// Zentrale Konfiguration der Switch Cheats Downloader NRO-App
// ---------------------------------------------------------------------------

// Die Versionsnummer wird zentral im Makefile gepflegt (APP_VERSION) und per
// -DAPP_VERSION=... durchgereicht (eine Quelle fuer .nacp, kAppVersion und
// User-Agent). Der Fallback hier greift nur bei Builds ausserhalb des Makefiles.
#ifndef APP_VERSION
#define APP_VERSION "1.2.0"
#endif

namespace cfg {

// GitHub-Repository, das die "data"-Release mit switch-cheats.zip bereitstellt
constexpr const char* kRepoOwner = "DevCatSKZ";
constexpr const char* kRepoName  = "Switch-Cheats-Scraper-Downloader";
constexpr const char* kReleaseTag = "data";
constexpr const char* kAssetName  = "switch-cheats.zip";

// GitHub REST API Endpunkt fuer die "data" Release (liefert Asset-Liste inkl.
// browser_download_url und updated_at, siehe README des Hauptprojekts: die
// gleiche "Reupload ohne Versionsbump"-Erkennung wie im Desktop-Tool).
inline const char* kApiUrl =
    "https://api.github.com/repos/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/tags/data";

// Ablageorte auf der SD-Karte (sdmc:/...)
constexpr const char* kAppDir        = "sdmc:/switch/SwitchCheatsDownloader";
constexpr const char* kStateFile     = "sdmc:/switch/SwitchCheatsDownloader/last_update.txt";
constexpr const char* kTmpZipPath    = "sdmc:/switch/SwitchCheatsDownloader/switch-cheats.zip.part";
// Merkt sich, zu welchem Release-Stand (updated_at) die .part-Datei gehoert -
// nur dann darf ein abgebrochener Download fortgesetzt werden.
constexpr const char* kTmpZipMetaPath = "sdmc:/switch/SwitchCheatsDownloader/switch-cheats.zip.part.meta";
constexpr const char* kSdRoot        = "sdmc:/";
constexpr const char* kLangFile      = "sdmc:/switch/SwitchCheatsDownloader/lang.txt";

constexpr const char* kAppVersion = APP_VERSION;
constexpr const char* kUserAgent  = "SwitchCheatsDownloaderNRO/" APP_VERSION;

// ---------------------------------------------------------------------------
// Self-Update der App (.nro) selbst.
// Erwartet ein GitHub-Release mit diesem Tag, das die aktuelle .nro als
// Asset enthaelt. Die Version steht im Release-TITEL ("name"-Feld, z.B.
// "v1.1.0") und wird gegen kAppVersion verglichen - der tag_name ist immer
// "nro" (das ist der Abfrage-Tag) und traegt daher keine Versionsinfo.
// Solange der Maintainer noch kein solches Release veroeffentlicht hat,
// meldet der Check einfach "nicht verfuegbar" (HTTP 404 wird sauber
// behandelt, kein Fehlerfall fuer den Nutzer).
// ---------------------------------------------------------------------------
constexpr const char* kNroReleaseTag = "nro";
constexpr const char* kNroAssetName  = "SwitchCheatsDownloader.nro";

inline const char* kNroApiUrl =
    "https://api.github.com/repos/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/tags/nro";

// Fallback-Pfad der eigenen .nro, falls argv[0] beim Start nicht verfuegbar ist
// (sollte laut README dem Installationsort entsprechen).
constexpr const char* kSelfNroFallbackPath = "sdmc:/switch/SwitchCheatsDownloader.nro";
constexpr const char* kTmpNroPath = "sdmc:/switch/SwitchCheatsDownloader/app_update.nro.part";

// Bildschirmaufloesung (logische Render-Aufloesung, wird von der Switch
// automatisch skaliert - Handheld & Docked)
constexpr int kScreenW = 1280;
constexpr int kScreenH = 720;

} // namespace cfg
