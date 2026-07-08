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
import com.devcatskz.switchcheats.data.Storage
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

@Composable
fun HomeScreen(
    vm: MainViewModel,
    onGrantAllFiles: () -> Unit,
    onPickFolder: () -> Unit,
    onExport: () -> Unit,
) {
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

            // Emulator selection
            GlassCard {
                SectionTitle(vm.t("emu.title"))
                Spacer(Modifier.height(2.dp))
                Text(vm.t("emu.hint"), color = Prisma.Muted, fontSize = 12.sp)
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Emulator.entries.forEach { e ->
                        val sel = vm.emulator == e
                        Box(
                            Modifier
                                .weight(1f)
                                .clip(RoundedCornerShape(12.dp))
                                .background(if (sel) Prisma.Accent.copy(alpha = 0.18f) else Prisma.Bg2)
                                .border(
                                    BorderStroke(1.dp, if (sel) Prisma.Accent else Prisma.PanelBorder),
                                    RoundedCornerShape(12.dp)
                                )
                                .clickable { vm.changeEmulator(e) }
                                .padding(vertical = 12.dp),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(
                                e.displayName,
                                color = if (sel) Prisma.Accent else Prisma.Text,
                                fontWeight = if (sel) FontWeight.Bold else FontWeight.Normal,
                            )
                        }
                    }
                }
            }

            // Update check
            GlassCard {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    SectionTitle(vm.t("install.title"))
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick = { vm.checkUpdate() }, enabled = !vm.busy) {
                        Text(vm.t("btn.check"), color = Prisma.Violet)
                    }
                }
                Text(vm.t("install.desc"), color = Prisma.Muted, fontSize = 12.sp)
                if (vm.checkText.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Text(
                        vm.checkText,
                        color = if (vm.updateAvailable) Prisma.Gold else Prisma.Text,
                        fontSize = 13.sp,
                    )
                }

                // Storage prompts
                if (vm.needAllFiles) {
                    Spacer(Modifier.height(10.dp))
                    Text(vm.t("storage.needAllFiles"), color = Prisma.Muted, fontSize = 12.sp)
                    Spacer(Modifier.height(8.dp))
                    HoloButton(vm.t("storage.grantAllFiles")) { onGrantAllFiles() }
                } else if (vm.needFolderGrant) {
                    Spacer(Modifier.height(10.dp))
                    Text(vm.t("storage.safHint"), color = Prisma.Muted, fontSize = 12.sp)
                    Spacer(Modifier.height(8.dp))
                    HoloButton(vm.t("storage.pickFolder")) { onPickFolder() }
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
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        HoloButton(vm.t("btn.start"), enabled = !vm.needAllFiles && !vm.needFolderGrant) {
                            vm.startInstall()
                        }
                        OutlinedButton(
                            onClick = onExport,
                            border = BorderStroke(1.dp, Prisma.PanelBorder),
                        ) { Text(vm.t("btn.export"), color = Prisma.Text) }
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
                Text(vm.t("info.target"), color = Prisma.Muted, fontSize = 12.sp)
                Text(Storage.targetLabel(vm.emulator), color = Prisma.Accent, fontSize = 11.sp)
                Spacer(Modifier.height(4.dp))
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
