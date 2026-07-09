package com.devcatskz.switchcheats.data

import java.io.File

/** Writes one cheat file (already laid out) into the output folder. */
interface CheatWriter {
    /** Write [bytes] to <base>/<TitleID>/<modName>/cheats/<BuildID>.txt, where
     *  [modName] is the game's name (falling back to the Title ID). */
    fun write(target: CheatLayout.Target, modName: String, bytes: ByteArray)
    fun close() {}
}

/**
 * Direct java.io.File writer into a PUBLIC folder (under "All files access").
 * Fast — plain filesystem writes land ~5300 small files in seconds. Each game
 * directory is created once (an `exists()` stat is cheap), then the cheat files
 * are written straight in.
 */
class FileCheatWriter(private val base: File) : CheatWriter {
    init { if (!base.exists()) base.mkdirs() }

    // Cheat entries arrive grouped by game, so remember the last cheats dir and
    // skip the exists()/mkdirs round-trip while writing the same game's files.
    private var lastRel: String? = null
    private var lastDir: File? = null

    override fun write(target: CheatLayout.Target, modName: String, bytes: ByteArray) {
        val rel = "${target.titleId}/$modName/cheats"
        val dir = if (rel == lastRel) lastDir!! else {
            val d = File(base, rel)
            if (!d.exists() && !d.mkdirs() && !d.exists())
                throw java.io.IOException("mkdir failed: $d")
            lastRel = rel; lastDir = d; d
        }
        File(dir, "${target.buildId}.txt").writeBytes(bytes)
    }

    companion object {
        /** True if we can actually create + write under [base] right now. */
        fun canWrite(base: File): Boolean = try {
            if (!base.exists()) base.mkdirs()
            val probe = File(base, ".scd_write_probe")
            probe.writeBytes(byteArrayOf(1)); probe.delete()
            true
        } catch (_: Exception) {
            false
        }
    }
}
