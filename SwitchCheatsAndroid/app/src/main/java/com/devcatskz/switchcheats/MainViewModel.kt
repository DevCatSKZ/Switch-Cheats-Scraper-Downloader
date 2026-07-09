package com.devcatskz.switchcheats

import android.app.Application
import android.content.Intent
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import com.devcatskz.switchcheats.data.*
import com.devcatskz.switchcheats.i18n.Lang
import com.devcatskz.switchcheats.i18n.Strings
import java.util.concurrent.Executors

class MainViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = Prefs(app)
    private val repo = CheatsRepository(app, prefs)
    private val io = Executors.newSingleThreadExecutor()
    private val mainHandler = android.os.Handler(android.os.Looper.getMainLooper())

    // ---- observable UI state ----
    var lang by mutableStateOf(prefs.lang); private set
    var emulator by mutableStateOf(prefs.emulator); private set
    var online by mutableStateOf<Boolean?>(null); private set

    var checkText by mutableStateOf(""); private set
    var updateAvailable by mutableStateOf(false); private set
    var pendingAsset by mutableStateOf<AssetInfo?>(null); private set

    // Opt-in: only write cheats for games already set up in the emulator. Off by default.
    var onlyInstalled by mutableStateOf(prefs.onlyInstalled); private set

    var needAllFiles by mutableStateOf(false); private set
    var needFolderGrant by mutableStateOf(false); private set
    // Set when the user picked a folder that isn't on the emulator's path.
    var folderError by mutableStateOf(""); private set

    // Startup permission onboarding: a prominent, explained request shown once
    // per install (persisted) while the general storage grant is missing.
    var showPermDialog by mutableStateOf(false); private set

    var appUpdateText by mutableStateOf(""); private set
    var appUpdateReady by mutableStateOf<AssetInfo?>(null); private set

    // ---- install run state (lives in InstallBus so it survives backgrounding;
    //      exposed here as localised strings so the language stays reactive) ----
    val busy: Boolean get() = InstallBus.busy
    val progress: Float get() = InstallBus.progress
    val installResult: InstallBus.Result? get() = InstallBus.result

    val statusText: String get() = when (InstallBus.phase) {
        InstallBus.Phase.CHECK_INTERNET -> t("status.checkInternet")
        InstallBus.Phase.CONNECTING -> t("status.connecting")
        InstallBus.Phase.DOWNLOADING -> t("status.downloading")
        InstallBus.Phase.EXTRACTING -> t("status.extracting")
        null -> ""
    }
    val downloadText: String get() =
        if (InstallBus.phase == InstallBus.Phase.DOWNLOADING && InstallBus.downloadDone > 0)
            t("install.download") + " " + fmtMb(InstallBus.downloadDone) +
                (if (InstallBus.downloadTotal > 0) " / " + fmtMb(InstallBus.downloadTotal) else "")
        else ""
    val extractText: String get() =
        if (InstallBus.phase == InstallBus.Phase.EXTRACTING)
            t("install.extract") + " ${InstallBus.extractDone} / ${InstallBus.extractTotal}" + t("install.filesSuffix")
        else ""

    val resultText: String get() = when (val r = InstallBus.result) {
        null -> ""
        is InstallBus.Result.Installed ->
            if (r.wasExport) String.format(t("result.exportedSummary"), r.files, r.games)
            else String.format(t("result.installedSummary"), r.files, r.games)
        InstallBus.Result.Offline -> t("result.noInternet")
        InstallBus.Result.CancelledResume -> t("result.cancelledResume")
        InstallBus.Result.NoGames -> t("result.noGames")
        is InstallBus.Result.Error -> t("result.errorPrefix") + t("err.${r.code}")
    }
    val resultIsError: Boolean get() = when (InstallBus.result) {
        null, is InstallBus.Result.Installed, InstallBus.Result.CancelledResume -> false
        else -> true
    }

    /** Show the "now enable cheats" hint only after a real install (not export). */
    val showActivationHint: Boolean get() =
        (InstallBus.result as? InstallBus.Result.Installed)?.let { !it.wasExport && it.files > 0 } ?: false

    fun t(key: String) = Strings.get(key, lang)

    private fun ui(block: () -> Unit) { mainHandler.post(block) }

    // ---- settings ----
    fun changeLang(l: Lang) { lang = l; prefs.lang = l }
    fun changeOnlyInstalled(v: Boolean) { onlyInstalled = v; prefs.onlyInstalled = v }
    fun changeEmulator(e: Emulator) {
        emulator = e; prefs.emulator = e
        needAllFiles = false; needFolderGrant = false; folderError = ""
        if (!InstallBus.busy) InstallBus.result = null   // clear last result + hint
        refreshWriteNeeds()
        checkUpdate()
    }

    fun refresh() {
        refreshWriteNeeds()
        // Ask for the GENERAL storage permission ONCE per install (like a normal
        // app): if it's still missing and we haven't asked yet, show the explained
        // prompt. Once granted the app just works; if denied, the Start button
        // re-offers it. The per-emulator folder grant is never the startup prompt.
        if (!prefs.permPrompted && needAllFiles) {
            prefs.permPrompted = true
            showPermDialog = true
        }
        checkUpdate()
    }

    private fun refreshWriteNeeds() {
        val mode = Storage.resolveWriteMode(getApplication(), emulator, prefs)
        needAllFiles = mode is Storage.WriteMode.NeedsAllFiles
        needFolderGrant = mode is Storage.WriteMode.NeedsFolderGrant
        // Grant satisfied → make sure the dialog is closed.
        if (!needAllFiles && !needFolderGrant) showPermDialog = false
    }

    fun openPermDialog() { showPermDialog = true }
    fun dismissPermDialog() { showPermDialog = false }

    // ---- launch the selected emulator ----
    fun emulatorInstalled(): Boolean =
        getApplication<Application>().packageManager.getLaunchIntentForPackage(emulator.launchPackage) != null

    fun openEmulator() {
        val pm = getApplication<Application>().packageManager
        val i = pm.getLaunchIntentForPackage(emulator.launchPackage) ?: return
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        try { getApplication<Application>().startActivity(i) } catch (_: Exception) {}
    }

    // ---- online indicator ----
    private var lastOnlineCheck = 0L
    /** Re-probe reachability when the app returns to the foreground so the online
     *  dot recovers instead of staying stuck "offline" after a lock/minimise. */
    fun recheckOnline() {
        val now = android.os.SystemClock.elapsedRealtime()
        if (now - lastOnlineCheck < 2500L) return
        lastOnlineCheck = now
        io.execute {
            val ok = Network.reachable()
            ui { online = ok }
        }
    }

    // ---- update check ----
    fun checkUpdate() {
        checkText = t("status.connecting")
        io.execute {
            val status = repo.checkUpdate(emulator)
            ui {
                when (status) {
                    is UpdateStatus.Offline -> { checkText = "" }
                    is UpdateStatus.Available -> {
                        online = true; updateAvailable = true; pendingAsset = status.asset
                        val last = prefs.lastInstalled(emulator)
                        checkText = t("check.local") +
                            (last?.take(10) ?: t("check.never")) + "   " + t("check.available")
                    }
                    is UpdateStatus.UpToDate -> {
                        online = true; updateAvailable = false; pendingAsset = status.asset
                        checkText = t("check.local") +
                            (prefs.lastInstalled(emulator)?.take(10) ?: "?") + "   " + t("check.uptodate")
                    }
                    is UpdateStatus.Error -> {
                        if (status.code == "network") online = false
                        checkText = t("result.errorPrefix") + t("err.${status.code}")
                    }
                }
            }
        }
    }

    // ---- storage grants ----
    // When the user taps Start but a grant is still missing, we remember to
    // continue the download automatically once the grant comes back.
    private var autoInstallAfterGrant = false
    fun armAutoInstall() { autoInstallAfterGrant = true }

    fun onAllFilesGranted() {
        refreshWriteNeeds()
        if (autoInstallAfterGrant && !needAllFiles && !needFolderGrant) {
            autoInstallAfterGrant = false
            startInstall()
        }
    }

    fun onFolderGranted(uri: Uri) {
        // Foolproof: the folder just has to be somewhere on the emulator's path.
        if (Storage.safPrefixFor(uri, emulator) == null) {
            autoInstallAfterGrant = false
            folderError = t("storage.wrongFolder")
            return
        }
        try {
            getApplication<Application>().contentResolver.takePersistableUriPermission(
                uri,
                Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
            )
        } catch (_: Exception) {}
        folderError = ""
        refreshWriteNeeds()
        if (autoInstallAfterGrant) {
            autoInstallAfterGrant = false
            startInstall()
        }
    }

    // ---- install / export (run in the foreground service) ----
    fun startInstall() {
        if (InstallBus.busy) return
        val mode = Storage.resolveWriteMode(getApplication(), emulator, prefs)
        if (Storage.writerFor(getApplication(), mode) == null) {
            // Missing storage access — pop the explained dialog only for the general
            // permission; the folder grant is offered inline.
            refreshWriteNeeds()
            if (needAllFiles) showPermDialog = true
            return
        }
        InstallBus.begin()   // flip the UI to busy at once
        InstallService.install(getApplication(), emulator, onlyInstalled)
    }

    fun cancel() { InstallBus.stopFlag.set(true) }

    /** Export the ready-to-copy layout into a user-picked folder (SAF). */
    fun exportTo(treeUri: Uri) {
        if (InstallBus.busy) return
        try {
            getApplication<Application>().contentResolver.takePersistableUriPermission(
                treeUri,
                Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
            )
        } catch (_: Exception) {}
        InstallBus.begin()
        InstallService.export(getApplication(), emulator, treeUri)
    }

    // ---- app self-update ----
    fun checkAppUpdate(installNow: Boolean) {
        if (appUpdateReady != null && installNow) {
            val asset = appUpdateReady!!
            appUpdateText = t("appupdate.checking")
            io.execute {
                val err = AppUpdater.downloadAndInstall(getApplication(), asset,
                    { d, tot -> ui { appUpdateText = fmtMb(d) + (if (tot > 0) " / " + fmtMb(tot) else "") } },
                    { false })
                ui { appUpdateText = if (err == null) t("result.appUpdateDone") else t("result.errorPrefix") + err }
            }
            return
        }
        appUpdateText = t("appupdate.checking")
        io.execute {
            when (val s = AppUpdater.check()) {
                is AppUpdateStatus.Available -> ui {
                    appUpdateReady = s.asset
                    appUpdateText = t("appupdate.availablePrefix") + s.version + "\n" + t("appupdate.installHint")
                }
                is AppUpdateStatus.UpToDate -> ui { appUpdateReady = null; appUpdateText = t("appupdate.upToDate") }
                is AppUpdateStatus.Offline -> ui { appUpdateText = t("result.noInternet") }
                is AppUpdateStatus.Error -> ui { appUpdateText = t("result.errorPrefix") + s.code }
            }
        }
    }

    private fun fmtMb(b: Long): String =
        if (b <= 0) "0.0 MB" else String.format("%.1f MB", b / 1_048_576.0)

    override fun onCleared() { io.shutdownNow() }
}
