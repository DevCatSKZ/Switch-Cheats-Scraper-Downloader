package com.devcatskz.switchcheats.data

import android.content.Context
import android.net.Uri
import androidx.documentfile.provider.DocumentFile
import java.io.File

/** Writes one cheat file (already re-laid-out) into the target backend. */
interface CheatWriter {
    /** Write [bytes] to <base>/<TitleID>/<modName>/cheats/<BuildID>.txt, where
     *  [modName] is the game's name (falling back to the Title ID). */
    fun write(target: CheatLayout.Target, modName: String, bytes: ByteArray)
    fun close() {}
}

/** Direct java.io.File writer — fast. Works for Suyu (public path) and, on
 *  Android ≤ 10 or rooted devices, for Android/data too. */
class FileCheatWriter(private val loadBase: File) : CheatWriter {
    override fun write(target: CheatLayout.Target, modName: String, bytes: ByteArray) {
        val dir = File(loadBase, "${target.titleId}/$modName/cheats")
        if (!dir.exists()) dir.mkdirs()
        File(dir, "${target.buildId}.txt").writeBytes(bytes)
    }

    companion object {
        /** True if we can actually create+write under [loadBase] right now. */
        fun canWrite(loadBase: File): Boolean {
            return try {
                if (!loadBase.exists() && !loadBase.mkdirs()) return false
                val probe = File(loadBase, ".scd_write_probe")
                probe.writeBytes(byteArrayOf(1)); probe.delete()
                true
            } catch (_: Exception) {
                false
            }
        }
    }
}

/**
 * SAF writer for a granted tree (the emulator's `load` folder, or a parent).
 * DocumentFile directory creation is slow, so every folder is cached and reused.
 */
class SafCheatWriter(
    private val context: Context,
    treeUri: Uri,
) : CheatWriter {
    private val root: DocumentFile =
        DocumentFile.fromTreeUri(context, treeUri)
            ?: throw IllegalStateException("Bad tree URI")

    // Cache: relative dir path ("<tid>/<mod>/cheats") -> DocumentFile
    private val dirCache = HashMap<String, DocumentFile>()

    private fun dirFor(vararg segments: String): DocumentFile {
        val key = segments.joinToString("/")
        dirCache[key]?.let { return it }
        var cur = root
        val sb = StringBuilder()
        for (seg in segments) {
            if (sb.isNotEmpty()) sb.append('/')
            sb.append(seg)
            val cached = dirCache[sb.toString()]
            if (cached != null) { cur = cached; continue }
            val existing = cur.findFile(seg)
            cur = if (existing != null && existing.isDirectory) existing
            else cur.createDirectory(seg)
                ?: throw java.io.IOException("mkdir failed: $seg")
            dirCache[sb.toString()] = cur
        }
        return cur
    }

    override fun write(target: CheatLayout.Target, modName: String, bytes: ByteArray) {
        val dir = dirFor(target.titleId, modName, "cheats")
        val fileName = "${target.buildId}.txt"
        val file = dir.findFile(fileName) ?: dir.createFile("text/plain", fileName)
        ?: throw java.io.IOException("create failed: $fileName")
        context.contentResolver.openOutputStream(file.uri, "wt")!!.use { it.write(bytes) }
    }
}
