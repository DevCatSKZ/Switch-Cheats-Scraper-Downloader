package com.devcatskz.switchcheats

import android.app.Application
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import com.devcatskz.switchcheats.data.*
import com.devcatskz.switchcheats.i18n.Lang
import com.devcatskz.switchcheats.i18n.Strings
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class MainViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = Prefs(app)
    private val repo = CheatsRepository(app, prefs)
    private val io = Executors.newSingleThreadExecutor()
    private val mainHandler = android.os.Handler(android.os.Looper.getMainLooper())
    private val stopFlag = AtomicBoolean(false)

    // ---- observable UI state ----
    var lang by mutableStateOf(prefs.lang); private set
    var emulator by mutableStateOf(prefs.emulator); private set
    var online by mutableStateOf<Boolean?>(null); private set

    var checkText by mutableStateOf(""); private set
    var updateAvailable by mutableStateOf(false); private set
    var pendingAsset by mutableStateOf<AssetInfo?>(null); private set

    var busy by mutableStateOf(false); private set
    var statusText by mutableStateOf(""); private set
    var downloadText by mutableStateOf(""); private set
    var extractText by mutableStateOf(""); private set
    var progress by mutableStateOf(0f); private set   // 0..1, -1 = indeterminate
    var resultText by mutableStateOf(""); private set
    var resultIsError by mutableStateOf(false); private set

    var needAllFiles by mutableStateOf(false); private set
    var needFolderGrant by mutableStateOf(false); private set
    // Set when the user picked a folder that isn't on the emulator's path.
    var folderError by mutableStateOf(""); private set

    // Startup permission onboarding: a prominent, explained request shown once
    // per install (persisted) while the general storage grant is missing.
    var showPermDialog by mutableStateOf(false); private set

    var appUpdateText by mutableStateOf(""); private set
    var appUpdateReady by mutableStateOf<AssetInfo?>(null); private set

    fun t(key: String) = Strings.get(key, lang)

    private fun ui(block: () -> Unit) { mainHandler.post(block) }

    // ---- settings ----
    fun changeLang(l: Lang) { lang = l; prefs.lang = l }
    fun changeEmulator(e: Emulator) {
        emulator = e; prefs.emulator = e
        needAllFiles = false; needFolderGrant = false; resultText = ""; folderError = ""
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

    // ---- online indicator ----
    private var lastOnlineCheck = 0L
    /** Re-probe reachability when the app returns to the foreground so the online
     *  dot recovers instead of staying stuck "offline" after a lock/minimise
     *  (the first check right after unlock often hits a not-yet-ready network).
     *  Debounced so transient resumes (dialogs, folder picker) don't re-probe. */
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
                    is UpdateStatus.Offline -> { checkText = "" }   // no longer produced
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
                        // A network failure just means we couldn't reach GitHub now;
                        // reflect it in the status dot, not as a scary popup line.
                        if (status.code == "network") online = false
                        checkText = t("result.errorPrefix") + t("err.${status.code}")
                    }
                }
            }
        }
    }

    // ---- storage grants ----
    // When the user taps Start but a grant is still missing, we remember to
    // continue the download automatically once the grant comes back — so the
    // flow is "tap Start (→ grant once) → it just downloads".
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
        // Foolproof: the folder just has to be somewhere on the emulator's path
        // (the emulator/package folder, files, load, or even Android/data). If it
        // isn't, don't keep it — tell the user and let them pick again.
        if (Storage.safPrefixFor(uri, emulator) == null) {
            autoInstallAfterGrant = false
            folderError = t("storage.wrongFolder")
            return
        }
        try {
            getApplication<Application>().contentResolver.takePersistableUriPermission(
                uri,
                android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION or
                    android.content.Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
            )
        } catch (_: Exception) {}
        folderError = ""
        refreshWriteNeeds()
        if (autoInstallAfterGrant) {
            autoInstallAfterGrant = false
            startInstall()
        }
    }

    // ---- install ----
    fun startInstall() {
        if (busy) return
        val mode = Storage.resolveWriteMode(getApplication(), emulator, prefs)
        val writer = Storage.writerFor(getApplication(), mode)
        if (writer == null) {
            // Missing storage access — for the general permission show the explained
            // dialog; if only the per-emulator folder is missing the inline prompt
            // already offers it, so don't pop the general dialog then.
            refreshWriteNeeds()
            if (needAllFiles) showPermDialog = true
            return
        }

        busy = true; stopFlag.set(false)
        resultText = ""; downloadText = ""; extractText = ""; progress = -1f
        statusText = t("status.connecting")

        io.execute {
            val res = repo.install(emulator, writer, object : InstallProgress {
                override fun onPhase(phase: InstallProgress.Phase) = ui {
                    statusText = when (phase) {
                        InstallProgress.Phase.CHECK_INTERNET -> t("status.checkInternet")
                        InstallProgress.Phase.CONNECTING -> t("status.connecting")
                        InstallProgress.Phase.DOWNLOADING -> t("status.downloading")
                        InstallProgress.Phase.EXTRACTING -> t("status.extracting")
                    }
                    if (phase == InstallProgress.Phase.EXTRACTING) progress = 0f
                }
                override fun onDownload(done: Long, total: Long) = ui {
                    downloadText = t("install.download") + " " + fmtMb(done) +
                        (if (total > 0) " / " + fmtMb(total) else "")
                    progress = if (total > 0) (done.toFloat() / total).coerceIn(0f, 1f) else -1f
                }
                override fun onExtract(done: Int, total: Int) = ui {
                    extractText = t("install.extract") + " $done / $total" + t("install.filesSuffix")
                    progress = if (total > 0) (done.toFloat() / total).coerceIn(0f, 1f) else -1f
                }
            }, stopFlag::get)

            ui {
                busy = false; progress = 0f
                when (res) {
                    is InstallResult.Installed -> {
                        resultIsError = false
                        resultText = t("result.doneInstalledPrefix") + res.files + t("result.doneInstalledSuffix")
                        checkUpdate()
                    }
                    is InstallResult.Offline -> { resultIsError = true; resultText = t("result.noInternet"); online = false }
                    is InstallResult.CancelledResume -> { resultIsError = false; resultText = t("result.cancelledResume") }
                    is InstallResult.Error -> {
                        resultIsError = true
                        resultText = t("result.errorPrefix") + t("err.${res.code}")
                    }
                }
            }
        }
    }

    fun cancel() { stopFlag.set(true) }

    /** Export the ready-to-copy layout into a user-picked folder (SAF), so the
     *  user can move it into any emulator manually. Uses the same install path
     *  with a SAF writer rooted at the chosen tree. */
    fun exportTo(treeUri: Uri) {
        if (busy) return
        try {
            getApplication<Application>().contentResolver.takePersistableUriPermission(
                treeUri,
                android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION or
                    android.content.Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
            )
        } catch (_: Exception) {}
        val writer = SafCheatWriter(getApplication(), treeUri)
        busy = true; stopFlag.set(false)
        resultText = ""; downloadText = ""; extractText = ""; progress = -1f
        statusText = t("status.connecting")
        io.execute {
            val res = repo.install(emulator, writer, object : InstallProgress {
                override fun onPhase(phase: InstallProgress.Phase) = ui {
                    statusText = when (phase) {
                        InstallProgress.Phase.CHECK_INTERNET -> t("status.checkInternet")
                        InstallProgress.Phase.CONNECTING -> t("status.connecting")
                        InstallProgress.Phase.DOWNLOADING -> t("status.downloading")
                        InstallProgress.Phase.EXTRACTING -> t("status.extracting")
                    }
                    if (phase == InstallProgress.Phase.EXTRACTING) progress = 0f
                }
                override fun onDownload(done: Long, total: Long) = ui {
                    downloadText = t("install.download") + " " + fmtMb(done) +
                        (if (total > 0) " / " + fmtMb(total) else "")
                    progress = if (total > 0) (done.toFloat() / total).coerceIn(0f, 1f) else -1f
                }
                override fun onExtract(done: Int, total: Int) = ui {
                    extractText = t("install.extract") + " $done / $total" + t("install.filesSuffix")
                    progress = if (total > 0) (done.toFloat() / total).coerceIn(0f, 1f) else -1f
                }
            }, stopFlag::get)
            ui {
                busy = false; progress = 0f
                when (res) {
                    is InstallResult.Installed -> {
                        resultIsError = false
                        resultText = t("result.exportedPrefix") + res.files + t("result.exportedSuffix")
                    }
                    is InstallResult.Offline -> { resultIsError = true; resultText = t("result.noInternet") }
                    is InstallResult.CancelledResume -> { resultIsError = false; resultText = t("result.cancelledResume") }
                    is InstallResult.Error -> { resultIsError = true; resultText = t("result.errorPrefix") + t("err.${res.code}") }
                }
            }
        }
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
