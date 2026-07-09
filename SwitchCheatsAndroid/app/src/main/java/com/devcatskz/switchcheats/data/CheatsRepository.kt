package com.devcatskz.switchcheats.data

import android.content.Context
import java.io.File
import java.io.IOException
import java.io.RandomAccessFile
import java.util.zip.ZipInputStream

/** Result of the "is a new cheats build available?" check. */
sealed class UpdateStatus {
    data class Available(val asset: AssetInfo) : UpdateStatus()   // never prepared OR newer
    data class UpToDate(val asset: AssetInfo) : UpdateStatus()
    object Offline : UpdateStatus()
    data class Error(val code: String) : UpdateStatus()
}

/** Progress callbacks for a prepare run. */
interface InstallProgress {
    fun onPhase(phase: Phase)
    fun onDownload(done: Long, total: Long)
    fun onExtract(done: Int, total: Int)
    enum class Phase { CHECK_INTERNET, CONNECTING, DOWNLOADING, EXTRACTING }
}

/** Outcome of a prepare run. */
sealed class InstallResult {
    data class Installed(val files: Int, val games: Int) : InstallResult()
    object Offline : InstallResult()
    object CancelledResume : InstallResult()
    data class Error(val code: String) : InstallResult()
}

class CheatsRepository(private val context: Context, private val prefs: Prefs) {

    private val tmpZip get() = File(context.filesDir, "switch-cheats-emulator.zip.part")
    private val tmpMeta get() = File(context.filesDir, "switch-cheats-emulator.zip.part.meta")

    // ---- update check ---------------------------------------------------
    fun checkUpdate(): UpdateStatus {
        // No separate connectivity probe (it produced false "offline" reports even
        // while the actual GitHub request worked). The fetch itself decides.
        val release = try {
            Network.fetchRelease(Config.DATA_API_URL)
        } catch (e: IOException) {
            return UpdateStatus.Error(mapError(e))
        } ?: return UpdateStatus.Error("assetNotFound")
        val asset = release.asset(Config.ASSET_NAME) ?: return UpdateStatus.Error("assetNotFound")
        val last = prefs.lastPrepared()
        return if (last != null && last == asset.updatedAt) UpdateStatus.UpToDate(asset)
        else UpdateStatus.Available(asset)
    }

    // ---- prepare (download + extract into the public output folder) -----
    fun install(
        writer: CheatWriter,
        progress: InstallProgress,
        shouldStop: () -> Boolean,
    ): InstallResult {
        progress.onPhase(InstallProgress.Phase.CONNECTING)
        val release = try {
            Network.fetchRelease(Config.DATA_API_URL)
        } catch (e: IOException) {
            return InstallResult.Error(mapError(e))
        } ?: return InstallResult.Error("assetNotFound")
        val asset = release.asset(Config.ASSET_NAME) ?: return InstallResult.Error("assetNotFound")
        val url = asset.downloadUrl.ifBlank { Config.ASSET_DOWNLOAD_URL }

        progress.onPhase(InstallProgress.Phase.DOWNLOADING)
        var completed = false
        var lastErr: IOException? = null
        // Attempt 0 resumes a matching .part; a retry starts clean — this recovers
        // from a stale/corrupt partial or a one-off server/redirect hiccup instead
        // of surfacing a hard error.
        for (attempt in 0..1) {
            val metaMatches = tmpMeta.takeIf { it.exists() }?.readText()?.trim() == asset.updatedAt
            if (attempt == 1 || !metaMatches) { tmpZip.delete(); tmpMeta.delete() }
            val existing = if (tmpZip.exists()) tmpZip.length() else 0L
            val raf = RandomAccessFile(tmpZip, "rw")
            raf.seek(existing)
            val sink = object : DownloadSink {
                override fun write(buf: ByteArray, len: Int) = raf.write(buf, 0, len)
                override fun truncate() { raf.setLength(0); raf.seek(0) }
                override fun flush() { raf.fd.sync() }
            }
            try {
                tmpMeta.writeText(asset.updatedAt)
                completed = Network.download(url, existing, asset.size, sink, progress::onDownload, shouldStop)
                lastErr = null
                break
            } catch (e: IOException) {
                lastErr = e
            } finally {
                try { raf.close() } catch (_: Exception) {}
            }
        }
        if (lastErr != null) return InstallResult.Error(mapError(lastErr))
        if (!completed) return InstallResult.CancelledResume

        // ---- extract straight into the output layout ----
        // The package is already <TitleID>/<GameName>/cheats/<BuildID>.txt, so we
        // just write each file where it belongs — no re-layout, no name lookup.
        progress.onPhase(InstallProgress.Phase.EXTRACTING)
        var written = 0
        val gameIds = HashSet<String>()
        try {
            val total = countEntries()
            ZipInputStream(tmpZip.inputStream().buffered()).use { zin ->
                var entry = zin.nextEntry
                val buf = ByteArray(64 * 1024)
                while (entry != null) {
                    if (shouldStop()) return InstallResult.CancelledResume
                    if (!entry.isDirectory) {
                        val e = CheatLayout.parse(entry.name)
                        if (e != null) {
                            val bytes = readAll(zin, buf)
                            writer.write(e.target, e.gameName, bytes)
                            written++
                            gameIds.add(e.titleId)
                            progress.onExtract(written, total)
                        }
                    }
                    zin.closeEntry()
                    entry = zin.nextEntry
                }
            }
        } catch (e: Exception) {
            return InstallResult.Error(if (e.message?.contains("mkdir") == true || e is java.io.IOException) "writeFile" else "zipBroken")
        } finally {
            writer.close()
        }

        // Success: remember the release state and drop the temp file.
        prefs.setLastPrepared(asset.updatedAt)
        tmpZip.delete(); tmpMeta.delete()
        return InstallResult.Installed(written, gameIds.size)
    }

    /** Count cheat entries by reading only the ZIP's central directory (instant),
     *  instead of streaming/decompressing the whole archive a second time. */
    private fun countEntries(): Int {
        var n = 0
        java.util.zip.ZipFile(tmpZip).use { zf ->
            val e = zf.entries()
            while (e.hasMoreElements()) {
                val entry = e.nextElement()
                if (!entry.isDirectory && CheatLayout.parse(entry.name) != null) n++
            }
        }
        return n
    }

    private fun readAll(zin: ZipInputStream, buf: ByteArray): ByteArray {
        val out = java.io.ByteArrayOutputStream()
        while (true) {
            val n = zin.read(buf)
            if (n < 0) break
            out.write(buf, 0, n)
        }
        return out.toByteArray()
    }

    private fun mapError(e: IOException): String = when (e.message) {
        "RATE_LIMIT" -> "rateLimit"
        else -> when {
            e.message?.startsWith("GITHUB_HTTP") == true -> "githubHttp"
            e.message?.startsWith("SERVER_HTTP") == true -> "serverHttp"
            else -> "network"
        }
    }
}
