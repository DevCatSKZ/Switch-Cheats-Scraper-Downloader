package com.devcatskz.switchcheats.data

/**
 * A supported Switch emulator on Android and where its cheats live.
 *
 * The cheats source is the ready-made emulator package
 * (switch-cheats-emulator.zip from the GitHub `data` release), already in the
 * Yuzu-family load layout:
 *
 *     <TitleID>/<GameName>/cheats/<BuildID>.txt
 *
 * so each file is written straight into the selected emulator's `load` folder
 * (Eden / Suyu / Sudachi) — no re-layout and no name lookup on the device.
 */
enum class Emulator(
    val id: String,
    val displayName: String,
    /** Path of the emulator's `load` folder, relative to the external storage
     *  root (/storage/emulated/0). */
    val loadRelPath: String,
    /** The emulator's Android package (null for Suyu, whose data is not under
     *  Android/data). Used to detect an installed emulator. */
    val packageName: String?,
    /** Package to launch the emulator app with. Usually == packageName; set
     *  separately for Suyu (whose data folder doesn't reveal it). A wrong guess is
     *  harmless — the launch intent just resolves to null and the button hides. */
    val launchPackage: String,
    /** True when the load folder is under Android/data, which needs the
     *  Storage-Access-Framework grant on Android 11+ (direct File writes are
     *  blocked by the OS there). */
    val underAndroidData: Boolean,
) {
    EDEN(
        id = "eden",
        displayName = "Eden",
        loadRelPath = "Android/data/dev.eden.eden_emulator/files/load",
        packageName = "dev.eden.eden_emulator",
        launchPackage = "dev.eden.eden_emulator",
        underAndroidData = true,
    ),
    SUYU(
        id = "suyu",
        displayName = "Suyu",
        loadRelPath = "suyu/load",
        packageName = null,
        launchPackage = "org.suyu.suyu_emulator",
        underAndroidData = false,
    ),
    SUDACHI(
        id = "sudachi",
        displayName = "Sudachi",
        loadRelPath = "Android/data/org.sudachi.sudachi/files/load",
        packageName = "org.sudachi.sudachi",
        launchPackage = "org.sudachi.sudachi",
        underAndroidData = true,
    );

    companion object {
        fun fromId(id: String?): Emulator =
            entries.firstOrNull { it.id == id } ?: EDEN
    }
}

/**
 * Parses entries of the ready-made emulator package (switch-cheats-emulator.zip),
 * whose paths are already the Yuzu-family load layout:
 *     <TitleID>/<GameName>/cheats/<BuildID>.txt
 * The game name is baked into the path, so the app writes each file straight into
 * <load>/<same path> — no re-layout and no names.json lookup on the phone.
 */
object CheatLayout {
    private val ENTRY =
        Regex("^([0-9A-Fa-f]{16})/([^/]+)/cheats/([0-9A-Fa-f]{16})\\.txt$")

    /** Title ID + build ID for a write backend to place the file. */
    data class Target(val titleId: String, val buildId: String)

    /** A parsed cheat entry: Title ID, game (mod-folder) name and build ID. */
    data class Entry(val titleId: String, val gameName: String, val buildId: String) {
        val target get() = Target(titleId, buildId)
    }

    /** Parse one zip entry, or null if it isn't a cheat file (e.g. a directory). */
    fun parse(zipEntryName: String): Entry? {
        val m = ENTRY.matchEntire(zipEntryName.replace('\\', '/')) ?: return null
        return Entry(m.groupValues[1].uppercase(), m.groupValues[2], m.groupValues[3].uppercase())
    }
}
