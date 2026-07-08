package com.devcatskz.switchcheats.data

import android.content.Context
import com.devcatskz.switchcheats.i18n.Lang

/** Small SharedPreferences wrapper for the app's settings and install state. */
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

    /** Whether the one-time startup storage-permission prompt was already shown
     *  (so we ask once, like a normal app — not on every launch). */
    var permPrompted: Boolean
        get() = sp.getBoolean("perm_prompted", false)
        set(v) = sp.edit().putBoolean("perm_prompted", v).apply()

    var emulator: Emulator
        get() = Emulator.fromId(emulatorId)
        set(v) { emulatorId = v.id }

    /** The cheats source's release `updated_at` we last installed (per emulator,
     *  since a fresh emulator may need re-installing even at the same version). */
    fun lastInstalled(emu: Emulator): String? = sp.getString("last_${emu.id}", null)
    fun setLastInstalled(emu: Emulator, updatedAt: String) =
        sp.edit().putString("last_${emu.id}", updatedAt).apply()

    /** A persisted SAF tree URI for an emulator's folder (used when direct File
     *  writes are blocked, i.e. Android/data on Android 11+). */
    fun safUri(emu: Emulator): String? = sp.getString("saf_${emu.id}", null)
    fun setSafUri(emu: Emulator, uri: String?) =
        sp.edit().putString("saf_${emu.id}", uri).apply()
}
