package com.devcatskz.switchcheats.data

import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Environment
import java.io.File

/** Resolves WHERE and HOW to write cheats for a given emulator, dealing with
 *  Android's scoped-storage rules. */
object Storage {

    private val externalRoot: File get() = Environment.getExternalStorageDirectory()

    /** Absolute `load` folder of an emulator on the primary shared storage. */
    fun loadDir(emu: Emulator): File = File(externalRoot, emu.loadRelPath)

    /** Human-readable target path shown in the UI. */
    fun targetLabel(emu: Emulator): String =
        "/storage/emulated/0/${emu.loadRelPath}/<TitleID>/${CheatLayout.MOD_NAME}/cheats/<BuildID>.txt"

    /** "All files access" (MANAGE_EXTERNAL_STORAGE) — needed to write outside the
     *  app's own dirs via java.io.File. */
    fun hasAllFilesAccess(): Boolean =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R)
            Environment.isExternalStorageManager()
        else true  // pre-R: WRITE_EXTERNAL_STORAGE runtime permission covers it

    /** How the app can write to this emulator right now. */
    sealed class WriteMode {
        data class Direct(val loadDir: File) : WriteMode()          // java.io.File
        data class Saf(val treeUri: Uri) : WriteMode()              // granted folder
        object NeedsAllFiles : WriteMode()                          // ask for MANAGE_EXTERNAL_STORAGE
        object NeedsFolderGrant : WriteMode()                       // ask for SAF folder
    }

    /**
     * Decide the write strategy:
     *  - Suyu / public paths: direct File once All-files access is granted.
     *  - Eden / Sudachi (Android/data): direct File works on Android ≤ 10; on
     *    11+ the OS blocks it even with All-files access, so we fall back to a
     *    persisted SAF folder grant (or ask for one).
     */
    fun resolveWriteMode(context: Context, emu: Emulator, prefs: Prefs): WriteMode {
        val dir = loadDir(emu)

        // A persisted SAF grant always wins if present and still valid.
        prefs.safUri(emu)?.let { s ->
            val uri = Uri.parse(s)
            val ok = context.contentResolver.persistedUriPermissions.any {
                it.uri == uri && it.isWritePermission
            }
            if (ok) return WriteMode.Saf(uri)
        }

        val androidDataBlocked =
            emu.underAndroidData && Build.VERSION.SDK_INT >= Build.VERSION_CODES.R

        if (!androidDataBlocked) {
            if (!hasAllFilesAccess()) return WriteMode.NeedsAllFiles
            if (FileCheatWriter.canWrite(dir)) return WriteMode.Direct(dir)
            // Some devices still block; fall through to a folder grant.
        }
        return WriteMode.NeedsFolderGrant
    }

    fun writerFor(context: Context, mode: WriteMode): CheatWriter? = when (mode) {
        is WriteMode.Direct -> FileCheatWriter(mode.loadDir)
        is WriteMode.Saf -> SafCheatWriter(context, mode.treeUri)
        else -> null
    }
}
