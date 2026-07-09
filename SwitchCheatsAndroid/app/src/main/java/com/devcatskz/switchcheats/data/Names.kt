package com.devcatskz.switchcheats.data

import android.content.Context
import org.json.JSONObject
import java.io.File

/**
 * Title ID → game name map, used to name each game's mod folder in the
 * emulator's load directory:  load/<TitleID>/<GameName>/cheats/<BuildID>.txt
 *
 * The map comes from the always-updated `names.json` in the GitHub `data`
 * release (the desktop tool keeps the full database current). It is cached
 * locally; when a name is unknown the Title ID is used as a safe fallback.
 */
object Names {
    private const val URL =
        "https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader/releases/download/data/names.json"

    @Volatile private var map: Map<String, String> = emptyMap()
    @Volatile private var loaded = false

    /** Fetch the freshest names.json (falling back to the local cache), once. */
    fun ensureLoaded(context: Context) {
        if (loaded) return
        val cache = File(context.filesDir, "names.json")
        val fresh = Network.fetchText(URL)
        val text = when {
            fresh != null -> { runCatching { cache.writeText(fresh) }; fresh }
            cache.exists() -> runCatching { cache.readText() }.getOrNull()
            else -> null
        }
        map = text?.let(::parse) ?: emptyMap()
        loaded = true
    }

    /** The game's name for a Title ID, or null if unknown. */
    fun nameFor(titleId: String): String? =
        map[titleId.uppercase()]?.takeIf { it.isNotBlank() }

    /** Folder-safe mod name for a Title ID: the game name, or the Title ID. */
    fun modFolder(titleId: String): String = sanitize(nameFor(titleId) ?: titleId)

    private val INVALID = Regex("[\\\\/:*?\"<>|\\x00-\\x1f]")
    private fun sanitize(name: String): String {
        val cleaned = INVALID.replace(name, "").trim().trim('.').trim()
        return cleaned.take(60).trim().ifBlank { "Cheats" }
    }

    private fun parse(json: String): Map<String, String> = try {
        val o = JSONObject(json)
        val m = HashMap<String, String>(o.length())
        val keys = o.keys()
        while (keys.hasNext()) { val k = keys.next(); m[k.uppercase()] = o.getString(k) }
        m
    } catch (_: Exception) {
        emptyMap()
    }
}
