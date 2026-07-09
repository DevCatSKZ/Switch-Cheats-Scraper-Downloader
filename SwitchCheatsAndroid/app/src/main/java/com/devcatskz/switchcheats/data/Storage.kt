package com.devcatskz.switchcheats.data

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.DocumentsContract
import androidx.core.content.ContextCompat
import androidx.documentfile.provider.DocumentFile
import java.io.File

/** Resolves WHERE and HOW to write cheats for a given emulator, dealing with
 *  Android's scoped-storage rules. */
object Storage {

    private val externalRoot: File get() = Environment.getExternalStorageDirectory()

    /** A 16-hex-char Title ID (the folder name the emulator uses under `load`). */
    private val TITLE_ID = Regex("^[0-9A-Fa-f]{16}$")

    /** Absolute `load` folder of an emulator on the primary shared storage. */
    fun loadDir(emu: Emulator): File = File(externalRoot, emu.loadRelPath)

    /** Human-readable target path shown in the UI. The mod folder is the game's
     *  name, taken straight from the emulator package's baked-in folder layout. */
    fun targetLabel(emu: Emulator): String =
        "/storage/emulated/0/${emu.loadRelPath}/<TitleID>/<GameName>/cheats/<BuildID>.txt"

    /** Broad write access to shared storage — needed to write outside the app's
     *  own dirs via java.io.File.
     *   - Android 11+ (R): "All files access" (MANAGE_EXTERNAL_STORAGE).
     *   - Android 8–10: the WRITE_EXTERNAL_STORAGE runtime permission. */
    fun hasAllFilesAccess(context: Context): Boolean =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R)
            Environment.isExternalStorageManager()
        else
            ContextCompat.checkSelfPermission(
                context, Manifest.permission.WRITE_EXTERNAL_STORAGE,
            ) == PackageManager.PERMISSION_GRANTED

    /** How the app can write to this emulator right now. */
    sealed class WriteMode {
        data class Direct(val loadDir: File) : WriteMode()                 // java.io.File
        /** A granted SAF tree plus the segments from that tree down to `load`. */
        data class Saf(val treeUri: Uri, val prefix: List<String>) : WriteMode()
        object NeedsAllFiles : WriteMode()                                // ask for MANAGE_EXTERNAL_STORAGE
        object NeedsFolderGrant : WriteMode()                             // ask for a SAF folder
    }

    /**
     * Decide the write strategy. The goal: the user picks *any* folder on the
     * emulator's path and the app sorts the rest — no way to get it wrong.
     *
     *  1. Any persisted SAF grant that *covers* this emulator's load path wins
     *     (so a single Android/data grant can serve every emulator).
     *  2. Otherwise the app needs broad storage access ("All files"); ask if missing.
     *  3. With it granted, try a direct File write (Suyu / public paths / Android ≤ 10).
     *  4. Only when the OS blocks the direct write (another app's Android/data on
     *     Android 11+) do we ask for a folder — resolved back to `load` for the user.
     */
    fun resolveWriteMode(context: Context, emu: Emulator, @Suppress("UNUSED_PARAMETER") prefs: Prefs): WriteMode {
        findSaf(context, emu)?.let { return it }
        if (!hasAllFilesAccess(context)) return WriteMode.NeedsAllFiles
        if (FileCheatWriter.canWrite(loadDir(emu))) return WriteMode.Direct(loadDir(emu))
        return WriteMode.NeedsFolderGrant
    }

    /** A persisted, writable SAF grant that covers [emu]'s load path, if any. */
    private fun findSaf(context: Context, emu: Emulator): WriteMode.Saf? {
        for (p in context.contentResolver.persistedUriPermissions) {
            if (!p.isWritePermission) continue
            val prefix = safPrefixFor(p.uri, emu) ?: continue
            return WriteMode.Saf(p.uri, prefix)
        }
        return null
    }

    /** The path a SAF tree URI points at, relative to primary shared storage,
     *  or null if it's not on the primary (internal) volume. */
    private fun treePath(uri: Uri): String? {
        val docId = try { DocumentsContract.getTreeDocumentId(uri) } catch (_: Exception) { return null }
        val parts = docId.split(":", limit = 2)
        if (parts.size < 2 || parts[0] != "primary") return null
        return parts[1].trim('/')
    }

    /**
     * Segments from the granted [uri] tree DOWN to the emulator's `load` folder,
     * or null when the tree is not on the emulator's path (a wrong pick).
     *   - grant = load            → []
     *   - grant = storage root    → all of loadRelPath
     *   - grant = a parent (files, the emulator/package folder, Android/data) → the rest
     */
    fun safPrefixFor(uri: Uri, emu: Emulator): List<String>? {
        val tree = treePath(uri) ?: return null
        val load = emu.loadRelPath.trim('/')
        return when {
            tree == load -> emptyList()
            tree.isEmpty() -> load.split("/")
            load.startsWith("$tree/") -> load.removePrefix("$tree/").split("/")
            else -> null
        }
    }

    fun writerFor(context: Context, mode: WriteMode): CheatWriter? = when (mode) {
        is WriteMode.Direct -> FileCheatWriter(mode.loadDir)
        is WriteMode.Saf -> SafCheatWriter(context, mode.treeUri, mode.prefix)
        else -> null
    }

    /**
     * The Title IDs the emulator already has set up — i.e. the `<TitleID>` folders
     * directly under its `load` folder. Used by the opt-in "only installed games"
     * mode to write cheats just for these. Works for both the direct-File and the
     * SAF backend. Returns UPPERCASE ids (matching CheatLayout.Target). Empty if
     * the load folder can't be read or has no game folders yet.
     */
    fun installedTitleIds(context: Context, emu: Emulator, prefs: Prefs): Set<String> =
        when (val mode = resolveWriteMode(context, emu, prefs)) {
            is WriteMode.Direct -> mode.loadDir.listFiles()
                ?.asSequence()
                ?.filter { it.isDirectory && TITLE_ID.matches(it.name) }
                ?.map { it.name.uppercase() }
                ?.toSet() ?: emptySet()
            is WriteMode.Saf -> {
                var cur: DocumentFile? = DocumentFile.fromTreeUri(context, mode.treeUri)
                for (seg in mode.prefix) { cur = cur?.findFile(seg); if (cur == null) break }
                cur?.listFiles()
                    ?.asSequence()
                    ?.filter { it.isDirectory && it.name != null && TITLE_ID.matches(it.name!!) }
                    ?.map { it.name!!.uppercase() }
                    ?.toSet() ?: emptySet()
            }
            else -> emptySet()
        }
}
