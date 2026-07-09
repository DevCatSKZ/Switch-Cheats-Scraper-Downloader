package com.devcatskz.switchcheats.data

import android.content.Context
import com.devcatskz.switchcheats.i18n.Lang

/** Small SharedPreferences wrapper for the app's settings and prepare state. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("scd_prefs", Context.MODE_PRIVATE)

    var langCode: String
        // Until the user picks one, follow the device language (if supported).
        get() = sp.getString("lang", null) ?: deviceLang()
        set(v) = sp.edit().putString("lang", v).apply()

    private fun deviceLang(): String {
        val dev = java.util.Locale.getDefault().language.lowercase()
        return Lang.entries.firstOrNull { it.code.lowercase() == dev }?.code ?: Lang.EN.code
    }

    var lang: Lang
        get() = Lang.fromCode(langCode)
        set(v) { langCode = v.code }

    var emulatorId: String
        get() = sp.getString("emulator", Emulator.EDEN.id)!!
        set(v) = sp.edit().putString("emulator", v).apply()

    var emulator: Emulator
        get() = Emulator.fromId(emulatorId)
        set(v) { emulatorId = v.id }

    /**
     * Absolute filesystem path of the PUBLIC output folder the cheats are written
     * into. Defaults to /storage/emulated/0/SwitchCheats; the user can point it
     * elsewhere. Written with java.io.File under "All files access".
     */
    var outputPath: String
        get() = sp.getString("output_path", null) ?: Storage.defaultDir().path
        set(v) = sp.edit().putString("output_path", v).apply()

    /** Whether the one-time storage-permission onboarding was already shown. */
    var permPrompted: Boolean
        get() = sp.getBoolean("perm_prompted", false)
        set(v) = sp.edit().putBoolean("perm_prompted", v).apply()

    /** Whether the app already asked for the POST_NOTIFICATIONS runtime permission
     *  (Android 13+), so the download progress notification can show. Asked once. */
    var notifPrompted: Boolean
        get() = sp.getBoolean("notif_prompted", false)
        set(v) = sp.edit().putBoolean("notif_prompted", v).apply()

    /** The cheats source's release `updated_at` we last prepared. */
    fun lastPrepared(): String? = sp.getString("last_prepared", null)
    fun setLastPrepared(updatedAt: String) =
        sp.edit().putString("last_prepared", updatedAt).apply()
}
