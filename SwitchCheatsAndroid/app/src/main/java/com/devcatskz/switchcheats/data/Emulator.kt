package com.devcatskz.switchcheats.data

/**
 * A supported Switch emulator on Android and where its cheats live.
 *
 * The cheats source (switch-cheats.zip from the GitHub `data` release) is laid
 * out in the Atmosphère format used by the real console:
 *
 *     atmosphere/contents/<TitleID>/cheats/<BuildID>.txt
 *
 * The Yuzu-family Android emulators (Eden / Suyu / Sudachi) instead read cheats
 * from a per-game "mod" folder:
 *
 *     <load>/<TitleID>/<CheatName>/cheats/<BuildID>.txt
 *
 * so every entry is re-laid-out into the selected emulator's `load` folder.
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
 * Re-layout of the Atmosphère cheat paths into the emulator's `load` folder.
 * Shared by every write backend (direct File and SAF/DocumentFile).
 */
object CheatLayout {
    private val ENTRY =
        Regex("^atmosphere/contents/([0-9A-Fa-f]{16})/cheats/([0-9A-Fa-f]{16})\\.txt$")

    /** A cheat file to write. The Yuzu family (Eden/Suyu/Sudachi) reads cheats
     *  from `load/<TitleID>/<ModName>/cheats/<BuildID>.txt`; the mod folder is
     *  resolved at write time to the game's name (see Names). */
    data class Target(val titleId: String, val buildId: String)

    /** Map one zip entry to its target under the load folder, or null if the
     *  entry is not a cheat file (e.g. a directory). */
    fun targetFor(zipEntryName: String): Target? {
        val m = ENTRY.matchEntire(zipEntryName.replace('\\', '/')) ?: return null
        return Target(m.groupValues[1].uppercase(), m.groupValues[2].uppercase())
    }
}
