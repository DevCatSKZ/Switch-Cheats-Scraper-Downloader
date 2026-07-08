package com.devcatskz.switchcheats.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color

/** Prisma (Holo-Glass) palette — identical spirit to the Windows/Switch apps:
 *  deep petrol-black, teal-mint accent, electric-violet gradient, gold. */
object Prisma {
    val Bg = Color(0xFF040A10)
    val Bg2 = Color(0xFF06121B)
    val Panel = Color(0xE6081722)        // translucent glass panel
    val PanelBorder = Color(0x332DE1C2)
    val Accent = Color(0xFF2DE1C2)       // teal-mint
    val Violet = Color(0xFF7C5CFF)       // electric violet
    val Gold = Color(0xFFFFC24B)
    val OnAccent = Color(0xFF04211C)
    val Text = Color(0xFFE7FBF6)
    val Muted = Color(0xFF8CA6A6)
    val Ok = Color(0xFF3Fe0A0)
    val Error = Color(0xFFFF6B6B)

    val BgGradient = Brush.verticalGradient(listOf(Color(0xFF04121A), Color(0xFF020609)))
    val AccentGradient = Brush.horizontalGradient(listOf(Accent, Violet))
    val GlassGradient = Brush.verticalGradient(listOf(Color(0x22FFFFFF), Color(0x0AFFFFFF)))
}

private val PrismaScheme = darkColorScheme(
    primary = Prisma.Accent,
    onPrimary = Prisma.OnAccent,
    secondary = Prisma.Violet,
    background = Prisma.Bg,
    onBackground = Prisma.Text,
    surface = Prisma.Panel,
    onSurface = Prisma.Text,
    error = Prisma.Error,
)

@Composable
fun SwitchCheatsTheme(content: @Composable () -> Unit) {
    isSystemInDarkTheme() // (theme is always the dark Prisma look)
    MaterialTheme(
        colorScheme = PrismaScheme,
        typography = Typography(),
        content = content,
    )
}
