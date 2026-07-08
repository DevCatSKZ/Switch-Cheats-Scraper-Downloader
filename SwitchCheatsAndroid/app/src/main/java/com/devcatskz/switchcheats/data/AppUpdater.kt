package com.devcatskz.switchcheats.data

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.core.content.FileProvider
import java.io.File
import java.io.IOException

sealed class AppUpdateStatus {
    data class Available(val version: String, val asset: AssetInfo) : AppUpdateStatus()
    object UpToDate : AppUpdateStatus()
    object Offline : AppUpdateStatus()
    data class Error(val code: String) : AppUpdateStatus()
}

/** Self-update, mirroring the NRO: the version lives in the release TITLE
 *  (e.g. "v1.1.0"); the tag ("android") only identifies the query. A 404 means
 *  "no such release yet" and is reported as up-to-date, not an error. */
object AppUpdater {

    private val VERSION = Regex("v?(\\d+)\\.(\\d+)\\.(\\d+)")

    fun check(): AppUpdateStatus {
        if (!Network.isOnline()) return AppUpdateStatus.Offline
        val release = try {
            Network.fetchRelease(Config.APP_API_URL)
        } catch (e: IOException) {
            return AppUpdateStatus.Error(e.message ?: "network")
        } ?: return AppUpdateStatus.UpToDate   // 404: not published yet
        val remote = VERSION.find(release.title) ?: return AppUpdateStatus.UpToDate
        val asset = release.asset(Config.APP_ASSET_NAME) ?: return AppUpdateStatus.UpToDate
        return if (isNewer(remote, Config.APP_VERSION))
            AppUpdateStatus.Available(remote.value.removePrefix("v"), asset)
        else AppUpdateStatus.UpToDate
    }

    private fun isNewer(remote: MatchResult, current: String): Boolean {
        val cur = VERSION.find(current) ?: return true
        for (i in 1..3) {
            val r = remote.groupValues[i].toInt()
            val c = cur.groupValues[i].toInt()
            if (r != c) return r > c
        }
        return false
    }

    /** Download the .apk and hand it to the system package installer. */
    fun downloadAndInstall(
        context: Context,
        asset: AssetInfo,
        onProgress: (Long, Long) -> Unit,
        shouldStop: () -> Boolean,
    ): String? {
        val apk = File(context.cacheDir, "app_update.apk")
        apk.delete()
        val raf = java.io.RandomAccessFile(apk, "rw")
        val sink = object : DownloadSink {
            override fun write(buf: ByteArray, len: Int) = raf.write(buf, 0, len)
            override fun truncate() { raf.setLength(0); raf.seek(0) }
            override fun flush() {}
        }
        val ok = try {
            Network.download(asset.downloadUrl, 0, asset.size, sink, onProgress, shouldStop)
        } catch (e: Exception) {
            raf.close(); return e.message ?: "network"
        } finally {
            try { raf.close() } catch (_: Exception) {}
        }
        if (!ok) return "cancelled"

        val uri: Uri = FileProvider.getUriForFile(
            context, "${context.packageName}.fileprovider", apk
        )
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
        return null
    }
}
