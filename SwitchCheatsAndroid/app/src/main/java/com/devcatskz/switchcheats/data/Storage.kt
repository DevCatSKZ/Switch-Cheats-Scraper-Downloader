package com.devcatskz.switchcheats.data

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Environment
import androidx.core.content.ContextCompat
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
        data class Direct(val loadDir: File) : WriteMode()          // java.io.File
        data class Saf(val treeUri: Uri) : WriteMode()              // granted folder
        object NeedsAllFiles : WriteMode()                          // ask for MANAGE_EXTERNAL_STORAGE
        object NeedsFolderGrant : WriteMode()                       // ask for SAF folder
    }

    /**
     * Decide the write strategy. The goal: after the one startup permission, copy
     * straight to the emulator's folder — no manual path picking required unless
     * the OS forces it.
     *
     *  1. A previously granted SAF folder always wins.
     *  2. Otherwise the app needs broad storage access ("All files"); ask if missing.
     *  3. With it granted, try a direct File write — this covers Suyu and any
     *     public path, and Android/data on Android ≤ 10, needing no folder pick.
     *  4. Only when the OS blocks the direct write (another app's Android/data on
     *     Android 11+) do we fall back to a one-time folder grant — the manual
     *     alternative.
     */
    fun resolveWriteMode(context: Context, emu: Emulator, prefs: Prefs): WriteMode {
        val dir = loadDir(emu)

        // 1. A persisted SAF grant always wins if present and still valid.
        prefs.safUri(emu)?.let { s ->
            val uri = Uri.parse(s)
            val ok = context.contentResolver.persistedUriPermissions.any {
                it.uri == uri && it.isWritePermission
            }
            if (ok) return WriteMode.Saf(uri)
        }

        // 2. Broad storage access is the baseline.
        if (!hasAllFilesAccess(context)) return WriteMode.NeedsAllFiles

        // 3. Prefer a direct write — no folder pick needed when it works.
        if (FileCheatWriter.canWrite(dir)) return WriteMode.Direct(dir)

        // 4. OS blocked it (Android/data on 11+) — ask for the folder once.
        return WriteMode.NeedsFolderGrant
    }

    fun writerFor(context: Context, mode: WriteMode): CheatWriter? = when (mode) {
        is WriteMode.Direct -> FileCheatWriter(mode.loadDir)
        is WriteMode.Saf -> SafCheatWriter(context, mode.treeUri)
        else -> null
    }
}
