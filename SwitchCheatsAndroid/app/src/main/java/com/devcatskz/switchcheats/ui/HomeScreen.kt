package com.devcatskz.switchcheats.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.devcatskz.switchcheats.MainViewModel
import com.devcatskz.switchcheats.data.Config
import com.devcatskz.switchcheats.data.Emulator
import com.devcatskz.switchcheats.data.InstallBus
import com.devcatskz.switchcheats.i18n.Lang
import com.devcatskz.switchcheats.ui.theme.Prisma

@Composable
private fun GlassCard(content: @Composable ColumnScope.() -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(Prisma.Panel)
            .border(BorderStroke(1.dp, Prisma.PanelBorder), RoundedCornerShape(18.dp))
            .padding(16.dp),
        content = content,
    )
}

@Composable
private fun HoloButton(text: String, enabled: Boolean = true, onClick: () -> Unit) {
    val shape = RoundedCornerShape(14.dp)
    Box(
        Modifier
            .clip(shape)
            .background(if (enabled) Prisma.AccentGradient else androidx.compose.ui.graphics.SolidColor(Prisma.Muted.copy(alpha = 0.3f)))
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = 22.dp, vertical = 11.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text, color = Prisma.OnAccent, fontWeight = FontWeight.Bold, fontSize = 15.sp)
    }
}

@Composable
private fun SectionTitle(text: String) =
    Text(text, color = Prisma.Accent, fontWeight = FontWeight.Bold, fontSize = 16.sp)

private fun prettyPath(path: String): String =
    path.replace("/storage/emulated/0", "").ifEmpty { "/" }

@Composable
fun HomeScreen(
    vm: MainViewModel,
    onGrantAllFiles: () -> Unit,
    onChangeFolder: () -> Unit,
) {
    LaunchedEffect(vm.installResult) {
        if (vm.installResult is InstallBus.Result.Installed) vm.checkUpdate()
    }

    Box(Modifier.fillMaxSize().background(Prisma.BgGradient)) {
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            // Header
            Column {
                Text(vm.t("app.name"), color = Prisma.Text, fontWeight = FontWeight.Black, fontSize = 24.sp)
                Text(vm.t("app.subtitle"), color = Prisma.Muted, fontSize = 13.sp)
            }

            // Supported emulators + how to import (one combined section — the steps
            // are identical for all three, so there's nothing to switch between).
            GlassCard {
                SectionTitle("Eden / Suyu / Sudachi")
                Spacer(Modifier.height(2.dp))
                Text(vm.t("emu.hint"), color = Prisma.Muted, fontSize = 12.sp)
                Spacer(Modifier.height(12.dp))
                ImportGuide(vm)
            }

            // Download & unpack
            GlassCard {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    SectionTitle(vm.t("prepare.title"))
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick = { vm.checkUpdate() }, enabled = !vm.busy) {
                        Text(vm.t("btn.check"), color = Prisma.Violet)
                    }
                }
                Text(vm.t("prepare.desc"), color = Prisma.Muted, fontSize = 12.sp)
                if (vm.checkText.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Text(
                        vm.checkText,
                        color = if (vm.updateAvailable) Prisma.Gold else Prisma.Text,
                        fontSize = 13.sp,
                    )
                }

                Spacer(Modifier.height(12.dp))
                FolderRow(vm, onChangeFolder)

                if (vm.needAllFiles && !vm.busy) {
                    Spacer(Modifier.height(10.dp))
                    Text(vm.t("storage.needAllFiles"), color = Prisma.Muted, fontSize = 12.sp)
                }

                Spacer(Modifier.height(12.dp))

                if (vm.busy) {
                    if (vm.statusText.isNotEmpty()) Text(vm.statusText, color = Prisma.Text, fontSize = 13.sp)
                    if (vm.downloadText.isNotEmpty()) Text(vm.downloadText, color = Prisma.Muted, fontSize = 12.sp)
                    if (vm.extractText.isNotEmpty()) Text(vm.extractText, color = Prisma.Muted, fontSize = 12.sp)
                    Spacer(Modifier.height(8.dp))
                    if (vm.progress < 0f) LinearProgressIndicator(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(6.dp)),
                        color = Prisma.Accent, trackColor = Prisma.Bg2,
                    ) else LinearProgressIndicator(
                        progress = vm.progress,
                        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(6.dp)),
                        color = Prisma.Accent, trackColor = Prisma.Bg2,
                    )
                    Spacer(Modifier.height(10.dp))
                    HoloButton(vm.t("btn.cancel")) { vm.cancel() }
                } else {
                    HoloButton(if (vm.needAllFiles) vm.t("storage.grantAllFiles") else vm.t("btn.prepare")) {
                        if (vm.needAllFiles) { vm.armAutoPrepare(); onGrantAllFiles() }
                        else vm.startPrepare()
                    }
                }

                if (vm.resultText.isNotEmpty()) {
                    Spacer(Modifier.height(10.dp))
                    Text(
                        vm.resultText,
                        color = if (vm.resultIsError) Prisma.Error else Prisma.Ok,
                        fontSize = 13.sp, fontWeight = FontWeight.Bold,
                    )
                }
            }

            // Info
            GlassCard {
                SectionTitle(vm.t("info.title"))
                Spacer(Modifier.height(6.dp))
                Text(vm.t("info.source") + "github.com/${Config.REPO_OWNER}/${Config.REPO_NAME}",
                    color = Prisma.Muted, fontSize = 12.sp)
                Text(vm.t("info.appVersion") + Config.APP_VERSION, color = Prisma.Muted, fontSize = 12.sp)
                Spacer(Modifier.height(8.dp))
                Text(vm.t("info.note"), color = Prisma.Muted, fontSize = 11.sp)
            }

            // App update
            GlassCard {
                SectionTitle(vm.t("appupdate.title"))
                Text(vm.t("appupdate.desc"), color = Prisma.Muted, fontSize = 12.sp)
                Spacer(Modifier.height(8.dp))
                HoloButton(vm.t("appupdate.check")) { vm.checkAppUpdate(vm.appUpdateReady != null) }
                if (vm.appUpdateText.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Text(vm.appUpdateText, color = Prisma.Text, fontSize = 12.sp)
                }
            }

            // Language bar
            GlassCard {
                SectionTitle(vm.t("info.language"))
                Spacer(Modifier.height(8.dp))
                FlowLangRow(vm)
            }

            // Footer
            Row(verticalAlignment = Alignment.CenterVertically) {
                val onlineTxt = when (vm.online) {
                    true -> "● " + vm.t("footer.online")
                    false -> "● " + vm.t("footer.offline")
                    null -> "…"
                }
                Text(onlineTxt, color = when (vm.online) {
                    true -> Prisma.Ok; false -> Prisma.Error; null -> Prisma.Muted
                }, fontSize = 12.sp)
                Spacer(Modifier.weight(1f))
                Text("by DevCatSKZ", color = Prisma.Muted, fontSize = 11.sp)
            }
            Spacer(Modifier.height(8.dp))
        }
    }
}

/** Always-visible, emulator-specific "how to import" card. */
@Composable
private fun ImportGuide(vm: MainViewModel) {
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(Prisma.Accent.copy(alpha = 0.10f))
            .border(BorderStroke(1.dp, Prisma.Accent.copy(alpha = 0.4f)), RoundedCornerShape(12.dp))
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(vm.t("guide.title"),
            color = Prisma.Accent, fontWeight = FontWeight.Bold, fontSize = 14.sp)
        Text("1. " + vm.t("guide.step1"), color = Prisma.Text, fontSize = 12.sp)
        Text("2. " + vm.t("guide.step2"), color = Prisma.Text, fontSize = 12.sp)
        Text(vm.t("import.pathHint") + " " + prettyPath(vm.outputPath), color = Prisma.Muted, fontSize = 11.sp)
        if (vm.hasEmulatorInstalled) {
            Spacer(Modifier.height(2.dp))
            HoloButton(vm.t("import.open")) { vm.openEmulator() }
        }
    }
}

@Composable
private fun FolderRow(vm: MainViewModel, onChangeFolder: () -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(Prisma.Bg2)
            .border(BorderStroke(1.dp, Prisma.PanelBorder), RoundedCornerShape(12.dp))
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text("📁 " + vm.t("folder.title"), color = Prisma.Text, fontSize = 13.sp, fontWeight = FontWeight.Medium)
        Text(prettyPath(vm.outputPath), color = Prisma.Accent, fontSize = 12.sp)
        TextButton(onClick = onChangeFolder, contentPadding = PaddingValues(0.dp)) {
            Text(vm.t("folder.change"), color = Prisma.Violet, fontSize = 12.sp)
        }
    }
}

@Composable
private fun FlowLangRow(vm: MainViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Lang.entries.chunked(3).forEach { rowLangs ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                rowLangs.forEach { l ->
                    val sel = vm.lang == l
                    Box(
                        Modifier
                            .weight(1f)
                            .clip(RoundedCornerShape(10.dp))
                            .background(if (sel) Prisma.Violet.copy(alpha = 0.22f) else Prisma.Bg2)
                            .border(
                                BorderStroke(1.dp, if (sel) Prisma.Violet else Prisma.PanelBorder),
                                RoundedCornerShape(10.dp)
                            )
                            .clickable { vm.changeLang(l) }
                            .padding(vertical = 9.dp),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text(
                            l.displayName,
                            color = if (sel) Prisma.Text else Prisma.Muted,
                            fontSize = 13.sp,
                            fontWeight = if (sel) FontWeight.Bold else FontWeight.Normal,
                            textAlign = TextAlign.Center,
                        )
                    }
                }
            }
        }
    }
}
