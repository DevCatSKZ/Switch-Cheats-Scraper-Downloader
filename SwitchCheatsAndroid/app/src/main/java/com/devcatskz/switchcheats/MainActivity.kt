package com.devcatskz.switchcheats

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.core.net.toUri
import com.devcatskz.switchcheats.ui.HomeScreen
import com.devcatskz.switchcheats.ui.theme.SwitchCheatsTheme

class MainActivity : ComponentActivity() {

    private val vm: MainViewModel by viewModels()

    // Returning from the "All files access" settings screen.
    private val allFilesLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
            vm.onAllFilesGranted()
        }

    // Grant the emulator's folder (SAF) so the app may write into Android/data.
    private val folderLauncher =
        registerForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri: Uri? ->
            uri?.let { vm.onFolderGranted(it) }
        }

    // Pick a folder to EXPORT the ready-to-copy layout into.
    private val exportLauncher =
        registerForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri: Uri? ->
            uri?.let { vm.exportTo(it) }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            SwitchCheatsTheme {
                HomeScreen(
                    vm = vm,
                    onGrantAllFiles = { openAllFilesAccess() },
                    onPickFolder = { folderLauncher.launch(initialTreeUri()) },
                    onExport = { exportLauncher.launch(null) },
                )
            }
        }
        vm.refresh()
    }

    override fun onResume() {
        super.onResume()
        vm.onAllFilesGranted()   // re-evaluate after returning from settings
    }

    private fun openAllFilesAccess() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
                .setData("package:$packageName".toUri())
            try {
                allFilesLauncher.launch(intent)
            } catch (_: Exception) {
                allFilesLauncher.launch(Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION))
            }
        }
    }

    /** Best-effort starting point for the folder picker (may be ignored by the OS). */
    private fun initialTreeUri(): Uri? = null
}
