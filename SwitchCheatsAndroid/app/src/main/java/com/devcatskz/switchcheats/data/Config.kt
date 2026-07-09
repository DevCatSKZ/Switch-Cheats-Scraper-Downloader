package com.devcatskz.switchcheats.data

/** Central configuration — mirrors the Switch homebrew (config.hpp): the same
 *  GitHub `data` release + switch-cheats.zip source, just an Android self-update
 *  feed (an `android` release carrying the .apk) instead of the .nro one. */
object Config {
    const val REPO_OWNER = "DevCatSKZ"
    const val REPO_NAME = "Switch-Cheats-Scraper-Downloader"

    // Cheats source (the desktop tool keeps this up to date).
    const val DATA_TAG = "data"
    const val ASSET_NAME = "switch-cheats.zip"
    const val DATA_API_URL =
        "https://api.github.com/repos/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/tags/data"
    const val ASSET_DOWNLOAD_URL =
        "https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/download/data/switch-cheats.zip"

    // App self-update feed (optional — 404 is handled as "not available").
    const val APP_TAG = "android"
    const val APP_ASSET_NAME = "SwitchCheatsDownloader.apk"
    const val APP_API_URL =
        "https://api.github.com/repos/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/tags/android"

    const val APP_VERSION = "1.1.0"
    const val USER_AGENT = "SwitchCheatsDownloaderAndroid/$APP_VERSION"

    // Connectivity probe (same host as the desktop/NRO online check).
    const val ONLINE_PROBE = "https://www.cheatslips.com"
}
