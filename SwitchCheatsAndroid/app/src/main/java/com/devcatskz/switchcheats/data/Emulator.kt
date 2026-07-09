package com.devcatskz.switchcheats.data

/**
 * A supported Switch emulator on Android.
 *
 * The app writes the cheats into a public folder the user picks; the emulator is
 * only used to tailor the import instructions and the "Open emulator" button.
 * All of these are Yuzu-family forks and share the same Android importer:
 *     long-press the game → Add-ons → "Mods and cheats" → pick the folder.
 */
enum class Emulator(
    val id: String,
    val displayName: String,
    /** Package used to detect/launch the emulator app. A wrong guess is harmless —
     *  the launch intent just resolves to null and the "Open" button hides. */
    val launchPackage: String,
) {
    EDEN("eden", "Eden", "dev.eden.eden_emulator"),
    SUYU("suyu", "Suyu", "org.suyu.suyu_emulator"),
    SUDACHI("sudachi", "Sudachi", "org.sudachi.sudachi");

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
 * <output>/<same path> — no re-layout and no name lookup on the phone.
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
