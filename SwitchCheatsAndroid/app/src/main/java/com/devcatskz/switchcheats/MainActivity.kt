package com.devcatskz.switchcheats

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.DocumentsContract
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

    // Android 8–10: runtime WRITE_EXTERNAL_STORAGE request.
    private val writePermLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) {
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
                    onGrantAllFiles = { grantStorageAccess() },
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
        vm.recheckOnline()       // refresh the online dot after lock/minimise/resume
    }

    /** Request broad storage write access: All-files-access settings on
     *  Android 11+, or the WRITE_EXTERNAL_STORAGE runtime permission on 8–10. */
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
            writePermLauncher.launch(android.Manifest.permission.WRITE_EXTERNAL_STORAGE)
        }
    }

    /** Open the folder picker already pointed at the selected emulator's folder,
     *  so granting it is a single confirmation (best-effort; the OS may ignore it). */
    private fun initialTreeUri(): Uri? = try {
        val docId = "primary:" + vm.emulator.loadRelPath
        DocumentsContract.buildDocumentUri("com.android.externalstorage.documents", docId)
    } catch (_: Exception) {
        null
    }
}
