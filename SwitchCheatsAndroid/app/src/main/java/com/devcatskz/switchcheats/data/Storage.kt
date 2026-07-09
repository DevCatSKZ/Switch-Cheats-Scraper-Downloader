package com.devcatskz.switchcheats.data

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.DocumentsContract
import androidx.core.content.ContextCompat
import java.io.File

/**
 * Where the cheats are written and how.
 *
 * The app writes the ready-to-import layout into a PUBLIC folder and the user
 * then imports it per game via the emulator's own "Add-ons → Mods and cheats"
 * importer (no third-party app can write into an emulator's private Android/data
 * on Android 11+, so pushing straight into the emulator is impossible anyway).
 *
 * Writing is done with plain java.io.File under "All files access"
 * (MANAGE_EXTERNAL_STORAGE) — ~5300 small files land in seconds, whereas the
 * Storage-Access-Framework would take many minutes for the same job.
 */
object Storage {

    /** Default output folder on the primary shared storage. */
    fun defaultDir(): File = File(Environment.getExternalStorageDirectory(), "SwitchCheats")

    /** Broad write access to shared storage, needed for java.io.File writes into a
     *  public folder. Android 11+: "All files access"; 8–10: WRITE_EXTERNAL_STORAGE. */
    fun hasAllFilesAccess(context: Context): Boolean =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R)
            Environment.isExternalStorageManager()
        else
            ContextCompat.checkSelfPermission(
                context, Manifest.permission.WRITE_EXTERNAL_STORAGE,
            ) == PackageManager.PERMISSION_GRANTED

    /** Resolve a SAF tree URI (from the folder picker) to a filesystem path, so we
     *  can write to it fast with java.io.File. Works for the primary volume and
     *  named removable volumes; null if it can't be mapped. */
    fun treeUriToPath(uri: Uri): String? = try {
        val docId = DocumentsContract.getTreeDocumentId(uri)
        val parts = docId.split(":", limit = 2)
        val sub = parts.getOrElse(1) { "" }
        when (parts[0]) {
            "primary" -> File(Environment.getExternalStorageDirectory(), sub).path
            else -> "/storage/${parts[0]}/$sub".trimEnd('/')
        }
    } catch (_: Exception) {
        null
    }
}
