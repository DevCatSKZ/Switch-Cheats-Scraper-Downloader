package com.devcatskz.switchcheats

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.core.content.ContextCompat
import androidx.core.net.toUri
import com.devcatskz.switchcheats.data.Prefs
import com.devcatskz.switchcheats.data.Storage
import com.devcatskz.switchcheats.ui.HomeScreen
import com.devcatskz.switchcheats.ui.theme.SwitchCheatsTheme

class MainActivity : ComponentActivity() {

    private val vm: MainViewModel by viewModels()
    private val prefs by lazy { Prefs(this) }

    // Android 13+: allow the download progress notification to show.
    private val notifPermLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    // Returning from the "All files access" settings screen → re-check + auto-continue.
    private val allFilesLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
            vm.onAllFilesGranted()
        }

    // Android 8–10: runtime WRITE_EXTERNAL_STORAGE request.
    private val writePermLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) {
            vm.onAllFilesGranted()
        }

    // Optional: let the user point the output at a different public folder.
    private val changeFolderLauncher =
        registerForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri: Uri? ->
            uri?.let { vm.setFolder(it) }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            SwitchCheatsTheme {
                HomeScreen(
                    vm = vm,
                    onGrantAllFiles = { grantStorageAccess() },
                    onChangeFolder = { changeFolderLauncher.launch(null) },
                )
            }
        }
        vm.refresh()
        maybeAskNotifications()
    }

    override fun onResume() {
        super.onResume()
        vm.onAllFilesGranted()   // re-evaluate after returning from settings
        vm.recheckOnline()
        maybeAskNotifications()
    }

    private fun maybeAskNotifications() {
        if (Build.VERSION.SDK_INT < 33 || prefs.notifPrompted) return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
            == PackageManager.PERMISSION_GRANTED) { prefs.notifPrompted = true; return }
        prefs.notifPrompted = true
        notifPermLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
    }

    /** Request broad storage write access: All-files-access settings on Android 11+,
     *  or the WRITE_EXTERNAL_STORAGE runtime permission on 8–10. */
    private fun grantStorageAccess() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
                .setData("package:$packageName".toUri())
            try {
                allFilesLauncher.launch(intent)
            } catch (_: Exception) {
                allFilesLauncher.launch(Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION))
            }
        } else {
            writePermLauncher.launch(Manifest.permission.WRITE_EXTERNAL_STORAGE)
        }
    }
}
