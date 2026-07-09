package com.devcatskz.switchcheats.data

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Process-wide, Compose-observable state for a running "prepare cheats" job.
 *
 * The work runs in [InstallService] (a foreground service) so it survives the
 * screen locking or the app being minimised — the notification keeps the process
 * alive. The service writes structured progress here; the ViewModel exposes it to
 * the UI as localised strings (so the language stays reactive). Being a plain
 * singleton, this state simply persists as long as the process lives.
 */
object InstallBus {

    enum class Phase { CHECK_INTERNET, CONNECTING, DOWNLOADING, EXTRACTING }

    /** Final outcome of the last run (null while none has finished this session). */
    sealed class Result {
        data class Installed(val files: Int, val games: Int) : Result()
        object Offline : Result()
        object CancelledResume : Result()
        data class Error(val code: String) : Result()
    }

    var busy by mutableStateOf(false)
    var phase by mutableStateOf<Phase?>(null)
    var downloadDone by mutableStateOf(0L)
    var downloadTotal by mutableStateOf(0L)
    var extractDone by mutableStateOf(0)
    var extractTotal by mutableStateOf(0)
    var progress by mutableStateOf(-1f)   // 0..1, or -1 = indeterminate
    var result by mutableStateOf<Result?>(null)

    /** Cooperative cancel flag polled by the running job. */
    val stopFlag = AtomicBoolean(false)

    /** Arm a fresh run: clear progress + previous result, reset the stop flag. */
    fun begin() {
        phase = null; downloadDone = 0L; downloadTotal = 0L
        extractDone = 0; extractTotal = 0; progress = -1f
        result = null; stopFlag.set(false); busy = true
    }

    fun finish(r: Result) { result = r; busy = false; phase = null }
}
