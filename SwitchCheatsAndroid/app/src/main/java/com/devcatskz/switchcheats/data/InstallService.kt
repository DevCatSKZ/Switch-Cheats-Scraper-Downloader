package com.devcatskz.switchcheats.data

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.Uri
import android.os.Build
import android.os.IBinder
import android.os.SystemClock
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import com.devcatskz.switchcheats.MainActivity
import com.devcatskz.switchcheats.i18n.Lang
import com.devcatskz.switchcheats.i18n.Strings
import java.util.concurrent.Executors

/**
 * Runs the cheat download/extract (or a folder export) as a foreground service so
 * a big transfer survives the screen locking or the app being minimised. Progress
 * is mirrored into [InstallBus] for the UI and shown in an ongoing notification
 * (with a Cancel action). The UI reads results back from [InstallBus].
 */
class InstallService : Service() {

    private val exec = Executors.newSingleThreadExecutor()

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_CANCEL -> { InstallBus.stopFlag.set(true); return START_NOT_STICKY }
            ACTION_INSTALL, ACTION_EXPORT -> run(intent)
            else -> stopSelf()
        }
        return START_NOT_STICKY
    }

    private fun run(intent: Intent) {
        val prefs = Prefs(this)
        val lang = prefs.lang
        val export = intent.action == ACTION_EXPORT
        val emu = Emulator.fromId(intent.getStringExtra(EXTRA_EMULATOR))
        val onlyInstalled = intent.getBooleanExtra(EXTRA_ONLY_INSTALLED, false)
        val treeUri = intent.getStringExtra(EXTRA_TREE_URI)?.let { Uri.parse(it) }

        InstallBus.begin()
        ensureChannel()
        startForegroundCompat(buildOngoing(lang, t(lang, "status.connecting"), -1f))

        exec.execute {
            try {
                val writer: CheatWriter? =
                    if (export && treeUri != null) SafCheatWriter(this, treeUri)
                    else Storage.writerFor(this, Storage.resolveWriteMode(this, emu, prefs))
                if (writer == null) { finish(lang, InstallBus.Result.Error("noAccess")); return@execute }

                val allowed: Set<String>? =
                    if (!export && onlyInstalled) {
                        val ids = Storage.installedTitleIds(this, emu, prefs)
                        if (ids.isEmpty()) { finish(lang, InstallBus.Result.NoGames); return@execute }
                        ids
                    } else null

                val repo = CheatsRepository(this, prefs)
                val res = repo.install(emu, writer, progress(lang), InstallBus.stopFlag::get, allowed)
                finish(lang, when (res) {
                    is InstallResult.Installed -> InstallBus.Result.Installed(res.files, res.games, export)
                    is InstallResult.Offline -> InstallBus.Result.Offline
                    is InstallResult.CancelledResume -> InstallBus.Result.CancelledResume
                    is InstallResult.Error -> InstallBus.Result.Error(res.code)
                })
            } catch (e: Exception) {
                finish(lang, InstallBus.Result.Error("network"))
            }
        }
    }

    // ---- progress → InstallBus + throttled notification ----
    private var lastNotify = 0L
    private fun progress(lang: Lang) = object : InstallProgress {
        override fun onPhase(phase: InstallProgress.Phase) {
            InstallBus.phase = phase.toBus()
            if (phase == InstallProgress.Phase.EXTRACTING) InstallBus.progress = 0f
            notifyOngoing(lang, force = true)
        }
        override fun onDownload(done: Long, total: Long) {
            InstallBus.downloadDone = done; InstallBus.downloadTotal = total
            InstallBus.progress = if (total > 0) (done.toFloat() / total).coerceIn(0f, 1f) else -1f
            notifyOngoing(lang)
        }
        override fun onExtract(done: Int, total: Int) {
            InstallBus.extractDone = done; InstallBus.extractTotal = total
            InstallBus.progress = if (total > 0) (done.toFloat() / total).coerceIn(0f, 1f) else -1f
            notifyOngoing(lang)
        }
    }

    private fun notifyOngoing(lang: Lang, force: Boolean = false) {
        val now = SystemClock.elapsedRealtime()
        if (!force && now - lastNotify < 600L) return
        lastNotify = now
        val pct = (InstallBus.progress * 100).toInt()
        val line = when (InstallBus.phase) {
            InstallBus.Phase.DOWNLOADING -> t(lang, "status.downloading") +
                (if (InstallBus.downloadTotal > 0) "  $pct%" else "")
            InstallBus.Phase.EXTRACTING -> t(lang, "status.extracting") +
                "  ${InstallBus.extractDone} / ${InstallBus.extractTotal}"
            else -> t(lang, "status.connecting")
        }
        nm().notify(NOTIF_ID, buildOngoing(lang, line, InstallBus.progress))
    }

    private fun finish(lang: Lang, r: InstallBus.Result) {
        InstallBus.finish(r)
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        // A brief completion notification (dismissible) so the user sees the result
        // even if they never returned to the app.
        val done = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setContentTitle(t(lang, "app.name"))
            .setContentText(resultLine(lang, r))
            .setContentIntent(openAppIntent())
            .setAutoCancel(true)
            .setOnlyAlertOnce(true)
            .build()
        try { nm().notify(NOTIF_ID_DONE, done) } catch (_: Exception) {}
        stopSelf()
    }

    private fun resultLine(lang: Lang, r: InstallBus.Result): String = when (r) {
        is InstallBus.Result.Installed ->
            if (r.wasExport) String.format(t(lang, "result.exportedSummary"), r.files, r.games)
            else String.format(t(lang, "result.installedSummary"), r.files, r.games)
        InstallBus.Result.Offline -> t(lang, "result.noInternet")
        InstallBus.Result.CancelledResume -> t(lang, "result.cancelledResume")
        InstallBus.Result.NoGames -> t(lang, "result.noGames")
        is InstallBus.Result.Error -> t(lang, "result.errorPrefix") + t(lang, "err.${r.code}")
    }

    // ---- notification plumbing ----
    private fun nm() = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(CHANNEL, "Downloads", NotificationManager.IMPORTANCE_LOW)
            ch.setShowBadge(false)
            nm().createNotificationChannel(ch)
        }
    }

    private fun buildOngoing(lang: Lang, text: String, progress: Float): Notification {
        val b = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle(t(lang, "app.name"))
            .setContentText(text)
            .setContentIntent(openAppIntent())
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .addAction(0, t(lang, "btn.cancel"), cancelIntent())
        if (progress < 0f) b.setProgress(0, 0, true) else b.setProgress(100, (progress * 100).toInt(), false)
        return b.build()
    }

    private fun startForegroundCompat(n: Notification) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q)
            ServiceCompat.startForeground(this, NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        else
            ServiceCompat.startForeground(this, NOTIF_ID, n, 0)
    }

    private fun openAppIntent(): PendingIntent {
        val i = Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
        return PendingIntent.getActivity(this, 0, i, piFlags())
    }

    private fun cancelIntent(): PendingIntent {
        val i = Intent(this, InstallService::class.java).setAction(ACTION_CANCEL)
        return PendingIntent.getService(this, 1, i, piFlags())
    }

    private fun piFlags(): Int {
        var f = PendingIntent.FLAG_UPDATE_CURRENT
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) f = f or PendingIntent.FLAG_IMMUTABLE
        return f
    }

    private fun t(lang: Lang, key: String) = Strings.get(key, lang)

    override fun onDestroy() { exec.shutdownNow(); super.onDestroy() }

    companion object {
        const val CHANNEL = "downloads"
        const val NOTIF_ID = 4201
        const val NOTIF_ID_DONE = 4202
        const val ACTION_INSTALL = "com.devcatskz.switchcheats.INSTALL"
        const val ACTION_EXPORT = "com.devcatskz.switchcheats.EXPORT"
        const val ACTION_CANCEL = "com.devcatskz.switchcheats.CANCEL"
        const val EXTRA_EMULATOR = "emulator"
        const val EXTRA_ONLY_INSTALLED = "only_installed"
        const val EXTRA_TREE_URI = "tree_uri"

        fun install(context: Context, emu: Emulator, onlyInstalled: Boolean) {
            val i = Intent(context, InstallService::class.java)
                .setAction(ACTION_INSTALL)
                .putExtra(EXTRA_EMULATOR, emu.id)
                .putExtra(EXTRA_ONLY_INSTALLED, onlyInstalled)
            androidx.core.content.ContextCompat.startForegroundService(context, i)
        }

        fun export(context: Context, emu: Emulator, treeUri: Uri) {
            val i = Intent(context, InstallService::class.java)
                .setAction(ACTION_EXPORT)
                .putExtra(EXTRA_EMULATOR, emu.id)
                .putExtra(EXTRA_TREE_URI, treeUri.toString())
            androidx.core.content.ContextCompat.startForegroundService(context, i)
        }
    }
}

private fun InstallProgress.Phase.toBus(): InstallBus.Phase = when (this) {
    InstallProgress.Phase.CHECK_INTERNET -> InstallBus.Phase.CHECK_INTERNET
    InstallProgress.Phase.CONNECTING -> InstallBus.Phase.CONNECTING
    InstallProgress.Phase.DOWNLOADING -> InstallBus.Phase.DOWNLOADING
    InstallProgress.Phase.EXTRACTING -> InstallBus.Phase.EXTRACTING
}
