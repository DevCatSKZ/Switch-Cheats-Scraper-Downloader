package com.devcatskz.switchcheats.data

import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** Info about a release asset from the GitHub API. */
data class AssetInfo(
    val name: String,
    val size: Long,
    val downloadUrl: String,
    val updatedAt: String,   // ISO-8601, the "reupload without version bump" marker
)

/** Info about a release (for the app self-update: version is in the title). */
data class ReleaseInfo(
    val title: String,
    val assets: List<AssetInfo>,
) {
    fun asset(name: String): AssetInfo? = assets.firstOrNull { it.name == name }
}

object Network {

    private fun open(url: String, rangeFrom: Long? = null): HttpURLConnection {
        val c = URL(url).openConnection() as HttpURLConnection
        c.setRequestProperty("User-Agent", Config.USER_AGENT)
        c.setRequestProperty("Accept", "application/vnd.github+json")
        c.connectTimeout = 15000
        c.readTimeout = 30000
        c.instanceFollowRedirects = true
        if (rangeFrom != null && rangeFrom > 0) {
            c.setRequestProperty("Range", "bytes=$rangeFrom-")
        }
        return c
    }

    /**
     * Open [url] for a binary download, following redirects manually. Android's
     * HttpURLConnection does NOT auto-follow 307/308, and GitHub release-asset
     * downloads (github.com → objects.githubusercontent.com CDN) can use them —
     * which surfaced as a "server didn't answer over HTTP" error on some networks.
     * A neutral Accept avoids CDNs choking on the GitHub API media type.
     */
    private fun openDownload(url: String, rangeFrom: Long?): HttpURLConnection {
        var current = url
        var hops = 0
        while (true) {
            val c = URL(current).openConnection() as HttpURLConnection
            c.setRequestProperty("User-Agent", Config.USER_AGENT)
            c.setRequestProperty("Accept", "*/*")
            c.connectTimeout = 15000
            c.readTimeout = 30000
            c.instanceFollowRedirects = false
            if (rangeFrom != null && rangeFrom > 0) c.setRequestProperty("Range", "bytes=$rangeFrom-")
            val code = c.responseCode
            if (code in 300..399 && code != 304) {
                val loc = c.getHeaderField("Location")
                c.disconnect()
                if (loc.isNullOrBlank() || ++hops > 6) throw IOException("SERVER_HTTP:$code")
                current = try {
                    URL(URL(current), loc).toString()
                } catch (_: Exception) {
                    throw IOException("SERVER_HTTP:$code")
                }
                continue
            }
            return c
        }
    }

    /** Quick connectivity probe — like the desktop/NRO online check. */
    fun isOnline(): Boolean = try {
        val c = open(Config.ONLINE_PROBE)
        c.requestMethod = "HEAD"
        c.connectTimeout = 6000
        c.readTimeout = 6000
        val code = c.responseCode
        c.disconnect()
        code in 200..399
    } catch (_: Exception) {
        false
    }

    /** Fetch a release's info via the GitHub REST API. Returns null on HTTP 404
     *  (release not published yet — not an error). Throws on other failures. */
    fun fetchRelease(apiUrl: String): ReleaseInfo? {
        val c = open(apiUrl)
        try {
            val code = c.responseCode
            if (code == 404) return null
            if (code == 403) throw IOException("RATE_LIMIT")
            if (code != 200) throw IOException("GITHUB_HTTP:$code")
            val body = c.inputStream.readBytes().toString(Charsets.UTF_8)
            val obj = JSONObject(body)
            val title = obj.optString("name", obj.optString("tag_name", ""))
            val arr: JSONArray = obj.optJSONArray("assets") ?: JSONArray()
            val assets = ArrayList<AssetInfo>(arr.length())
            for (i in 0 until arr.length()) {
                val a = arr.getJSONObject(i)
                assets.add(
                    AssetInfo(
                        name = a.optString("name"),
                        size = a.optLong("size"),
                        downloadUrl = a.optString("browser_download_url"),
                        updatedAt = a.optString("updated_at"),
                    )
                )
            }
            return ReleaseInfo(title, assets)
        } finally {
            c.disconnect()
        }
    }

    /** GET [url] as UTF-8 text (follows redirects). Returns null on any failure. */
    fun fetchText(url: String): String? = try {
        val c = openDownload(url, null)
        try {
            if (c.responseCode !in 200..299) null
            else c.inputStream.readBytes().toString(Charsets.UTF_8)
        } finally {
            c.disconnect()
        }
    } catch (_: Exception) {
        null
    }

    /**
     * Download [url] to [sink], resuming from [existing] bytes via an HTTP Range
     * request when the server supports it. [onProgress] gets (done, total).
     * [shouldStop] lets the caller cancel; returns false when cancelled.
     *
     * @return true when the full file was written, false when cancelled.
     */
    fun download(
        url: String,
        existing: Long,
        totalHint: Long,
        sink: DownloadSink,
        onProgress: (Long, Long) -> Unit,
        shouldStop: () -> Boolean,
    ): Boolean {
        val c = openDownload(url, existing.takeIf { it > 0 })
        try {
            val code = c.responseCode
            val resuming = code == 206 && existing > 0
            if (code != 200 && code != 206) throw IOException("SERVER_HTTP:$code")

            var done = if (resuming) existing else 0L
            if (!resuming && existing > 0) sink.truncate()  // server ignored Range
            val contentLen = c.contentLengthLong.let { if (it > 0) it else -1L }
            val total = when {
                resuming && contentLen > 0 -> existing + contentLen
                contentLen > 0 -> contentLen
                totalHint > 0 -> totalHint
                else -> -1L
            }

            c.inputStream.use { input ->
                val buf = ByteArray(64 * 1024)
                while (true) {
                    if (shouldStop()) return false
                    val n = input.read(buf)
                    if (n < 0) break
                    sink.write(buf, n)
                    done += n
                    onProgress(done, total)
                }
            }
            sink.flush()
            return true
        } finally {
            c.disconnect()
        }
    }
}

/** Abstracts appending bytes to a resumable temp file. */
interface DownloadSink {
    fun write(buf: ByteArray, len: Int)
    fun truncate()
    fun flush()
}
