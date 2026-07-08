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

    // Startup permission onboarding: a prominent, explained request shown once
    // per launch while a storage grant is still missing.
    var showPermDialog by mutableStateOf(false); private set
    private var permPromptShown = false

    var appUpdateText by mutableStateOf(""); private set
    var appUpdateReady by mutableStateOf<AssetInfo?>(null); private set

    fun t(key: String) = Strings.get(key, lang)

    private fun ui(block: () -> Unit) { mainHandler.post(block) }

    // ---- settings ----
    fun changeLang(l: Lang) { lang = l; prefs.lang = l }
    fun changeEmulator(e: Emulator) {
        emulator = e; prefs.emulator = e
        needAllFiles = false; needFolderGrant = false; resultText = ""
        refreshWriteNeeds()
        checkUpdate()
    }

    fun refresh() {
        refreshWriteNeeds()
        // On first launch (or any launch where a grant is still missing) show the
        // explained onboarding once, so new users learn WHY it's needed.
        if (!permPromptShown && (needAllFiles || needFolderGrant)) {
            permPromptShown = true
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
    fun onAllFilesGranted() { refreshWriteNeeds() }

    fun onFolderGranted(uri: Uri) {
        try {
            getApplication<Application>().contentResolver.takePersistableUriPermission(
                uri,
                android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION or
                    android.content.Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
            )
            prefs.setSafUri(emulator, uri.toString())
        } catch (_: Exception) {}
        refreshWriteNeeds()
    }

    // ---- install ----
    fun startInstall() {
        if (busy) return
        val mode = Storage.resolveWriteMode(getApplication(), emulator, prefs)
        val writer = Storage.writerFor(getApplication(), mode)
        if (writer == null) {
            // Missing a storage grant — explain and offer to grant instead of failing.
            refreshWriteNeeds()
            showPermDialog = true
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
