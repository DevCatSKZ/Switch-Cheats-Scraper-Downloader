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
    var online by mutableStateOf<Boolean?>(null); private set

    var checkText by mutableStateOf(""); private set
    var updateAvailable by mutableStateOf(false); private set
    var pendingAsset by mutableStateOf<AssetInfo?>(null); private set

    // Public output folder (absolute filesystem path) + whether we may write there.
    var outputPath by mutableStateOf(prefs.outputPath); private set
    var needAllFiles by mutableStateOf(false); private set

    var appUpdateText by mutableStateOf(""); private set
    var appUpdateReady by mutableStateOf<AssetInfo?>(null); private set

    // ---- prepare run state (lives in InstallBus so it survives backgrounding) ----
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
        is InstallBus.Result.Installed -> String.format(t("result.preparedSummary"), r.files, r.games)
        InstallBus.Result.Offline -> t("result.noInternet")
        InstallBus.Result.CancelledResume -> t("result.cancelledResume")
        is InstallBus.Result.Error -> t("result.errorPrefix") + t("err.${r.code}")
    }
    val resultIsError: Boolean get() = when (InstallBus.result) {
        null, is InstallBus.Result.Installed, InstallBus.Result.CancelledResume -> false
        else -> true
    }

    /** Show the "now import in your emulator" confirmation after a successful prepare. */
    val didPrepare: Boolean get() =
        (InstallBus.result as? InstallBus.Result.Installed)?.let { it.files > 0 } ?: false

    fun t(key: String) = Strings.get(key, lang)

    private fun ui(block: () -> Unit) { mainHandler.post(block) }

    // ---- settings ----
    fun changeLang(l: Lang) { lang = l; prefs.lang = l }

    fun refresh() {
        refreshWriteNeeds()
        checkUpdate()
    }

    private fun refreshWriteNeeds() {
        needAllFiles = !Storage.hasAllFilesAccess(getApplication())
    }

    // ---- online indicator ----
    private var lastOnlineCheck = 0L
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
            val status = repo.checkUpdate()
            ui {
                when (status) {
                    is UpdateStatus.Offline -> { checkText = "" }
                    is UpdateStatus.Available -> {
                        online = true; updateAvailable = true; pendingAsset = status.asset
                        val last = prefs.lastPrepared()
                        checkText = t("check.local") +
                            (last?.take(10) ?: t("check.never")) + "   " + t("check.available")
                    }
                    is UpdateStatus.UpToDate -> {
                        online = true; updateAvailable = false; pendingAsset = status.asset
                        checkText = t("check.local") +
                            (prefs.lastPrepared()?.take(10) ?: "?") + "   " + t("check.uptodate")
                    }
                    is UpdateStatus.Error -> {
                        if (status.code == "network") online = false
                        checkText = t("result.errorPrefix") + t("err.${status.code}")
                    }
                }
            }
        }
    }

    // ---- output folder + all-files grant + prepare ----
    // When the user taps the button but the grant is still missing, we remember to
    // continue the download automatically once the grant comes back.
    private var autoAfterGrant = false
    fun armAutoPrepare() { autoAfterGrant = true }

    /** Called after returning from the "All files access" settings screen. */
    fun onAllFilesGranted() {
        refreshWriteNeeds()
        if (autoAfterGrant && !needAllFiles) {
            autoAfterGrant = false
            startPrepare()
        }
    }

    /** The user re-picked the output folder (SAF picker); resolve it to a path and
     *  remember it. Writing itself uses fast java.io.File under All-files access. */
    fun setFolder(uri: Uri) {
        val path = Storage.treeUriToPath(uri) ?: return
        prefs.outputPath = path
        outputPath = path
    }

    fun startPrepare() {
        if (InstallBus.busy) return
        refreshWriteNeeds()
        if (needAllFiles) return           // UI opens the All-files settings screen
        InstallBus.result = null
        InstallBus.begin()
        InstallService.prepare(getApplication(), outputPath)
    }

    fun cancel() { InstallBus.stopFlag.set(true) }

    // ---- launch whichever supported emulator is installed ----
    private fun installedEmu(): Emulator? =
        Emulator.entries.firstOrNull {
            getApplication<Application>().packageManager.getLaunchIntentForPackage(it.launchPackage) != null
        }

    val hasEmulatorInstalled: Boolean get() = installedEmu() != null

    fun openEmulator() {
        val e = installedEmu() ?: return
        val pm = getApplication<Application>().packageManager
        val i = pm.getLaunchIntentForPackage(e.launchPackage) ?: return
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        try { getApplication<Application>().startActivity(i) } catch (_: Exception) {}
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
