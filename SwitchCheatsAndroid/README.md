# Switch Cheats Downloader — Android edition

A 1:1 Android port of the Switch homebrew app (`SwitchCheatsNRO/`): it downloads
the always‑current **`switch-cheats.zip`** from the GitHub **`data`** release and
installs the cheats **directly into an Android Switch‑emulator's cheats folder**.
Same data source, same update detection, same 6 languages, same Prisma
(Holo‑Glass) look and the same app icon as the Windows and Switch versions — the
only thing that differs is the **target path**, adapted per emulator.

## What it does (like the Switch version)

- **Update detection**: queries the GitHub API for the `switch-cheats.zip`
  asset's `updated_at` timestamp and compares it with the last installed state
  (per emulator). Runs on start and can be re-checked any time.
- **Download & install** in one step, with a **download/extract progress** bar
  and a **resume** for interrupted downloads (HTTP Range, only when the `.part`
  still belongs to the same release state).
- **App self‑update**: can pull a newer `.apk` from an `android` release and
  hand it to the system installer.
- **6 languages** (EN/DE/ES/FR/IT/JA) with real diacritics, switchable at
  runtime.
- **Offline detection** with a footer indicator.

## Emulator paths

The cheats source is laid out in the Atmosphère format
`atmosphere/contents/<TitleID>/cheats/<BuildID>.txt`. Each entry is re-laid-out
into the selected emulator's mod/cheats layout
`<load>/<TitleID>/SwitchCheatsDownloader/cheats/<BuildID>.txt`:

| Emulator | `load` folder |
|---|---|
| **Eden** | `/Android/data/dev.eden.eden_emulator/files/load` |
| **Suyu** | `suyu/load` (in shared storage) |
| **Sudachi** | `/Android/data/org.sudachi.sudachi/files/load` |

## Storage access (Android's scoped-storage rules)

- **Suyu** and pre‑Android‑11 devices: the app writes directly with
  *All files access* (`MANAGE_EXTERNAL_STORAGE`).
- **Eden / Sudachi on Android 11+**: the OS blocks direct writes into another
  app's `Android/data`. The app then asks you to **grant that emulator's folder
  once** via the system folder picker (SAF) and writes there.
- **Export fallback**: on any device you can **Export** the ready‑to‑copy layout
  into a folder you pick and move it into the emulator with a file manager.

## Build

Requires the Android SDK (platform 34, build‑tools 34) and a JDK 17–21.

```bash
./gradlew assembleDebug      # app/build/outputs/apk/debug/app-debug.apk
./gradlew assembleRelease    # unsigned release APK
```

Only the data source (the maintainer's `switch-cheats.zip`) is shared with the
desktop tool and the Switch homebrew — no code is shared.
