package com.devcatskz.switchcheats.i18n

/**
 * Runtime-switchable localisation, mirroring the desktop tool (i18n.py) and the
 * Switch homebrew (i18n.cpp): the same 6 languages with real diacritics.
 * Array order per key: [EN, DE, ES, FR, IT, JA].
 */
enum class Lang(val code: String, val displayName: String) {
    EN("EN", "English"),
    DE("DE", "Deutsch"),
    ES("ES", "Español"),
    FR("FR", "Français"),
    IT("IT", "Italiano"),
    JA("JA", "日本語");

    companion object {
        fun fromCode(c: String?): Lang = entries.firstOrNull { it.code == c } ?: EN
    }
}

object Strings {
    // key -> [EN, DE, ES, FR, IT, JA]
    private val T: Map<String, Array<String>> = mapOf(
        "app.name" to a("Switch Cheats Downloader", "Switch Cheats Downloader", "Switch Cheats Downloader", "Switch Cheats Downloader", "Switch Cheats Downloader", "Switch Cheats Downloader"),
        "app.subtitle" to a("Android edition — by DevCatSKZ", "Android-Edition — von DevCatSKZ", "Edición Android — por DevCatSKZ", "Édition Android — par DevCatSKZ", "Edizione Android — di DevCatSKZ", "Android版 — DevCatSKZ"),

        // ---- Emulator selection ----
        "emu.title" to a("Emulator", "Emulator", "Emulador", "Émulateur", "Emulatore", "エミュレーター"),
        "emu.hint" to a("Choose the emulator you use — cheats are placed in its folder.", "Wähle deinen Emulator — die Cheats landen in seinem Ordner.", "Elige el emulador que usas: los cheats se colocan en su carpeta.", "Choisis ton émulateur — les cheats sont placés dans son dossier.", "Scegli l'emulatore che usi: i cheat vengono messi nella sua cartella.", "使用するエミュレーターを選択 — チートはそのフォルダに配置されます。"),
        "emu.installed" to a("installed", "installiert", "instalado", "installé", "installato", "インストール済み"),
        "emu.notInstalled" to a("not detected", "nicht erkannt", "no detectado", "non détecté", "non rilevato", "未検出"),

        // ---- Update check ----
        "check.local" to a("Locally installed: ", "Lokal installiert: ", "Instalado localmente: ", "Installé localement : ", "Installato localmente: ", "ローカルのバージョン: "),
        "check.never" to a("never", "noch nie", "nunca", "jamais", "mai", "なし"),
        "check.remote" to a("Latest version: ", "Neueste Version: ", "Última versión: ", "Dernière version : ", "Ultima versione: ", "最新バージョン: "),
        "check.available" to a("→ An update is available!", "→ Ein Update ist verfügbar!", "→ ¡Hay una actualización disponible!", "→ Une mise à jour est disponible !", "→ È disponibile un aggiornamento!", "→ アップデートがあります！"),
        "check.uptodate" to a("→ You already have the latest version.", "→ Du hast bereits die neueste Version.", "→ Ya tienes la última versión.", "→ Vous avez déjà la dernière version.", "→ Hai già l'ultima versione.", "→ 最新バージョンです。"),

        // ---- Install section ----
        "install.title" to a("Download & Install", "Herunterladen & Installieren", "Descargar e instalar", "Télécharger et installer", "Scarica e installa", "ダウンロードしてインストール"),
        "install.desc" to a("Downloads the latest switch-cheats.zip and installs it into the selected emulator's cheats folder.", "Lädt die neueste switch-cheats.zip und installiert sie in den Cheats-Ordner des gewählten Emulators.", "Descarga el switch-cheats.zip más reciente y lo instala en la carpeta de cheats del emulador elegido.", "Télécharge le dernier switch-cheats.zip et l'installe dans le dossier de cheats de l'émulateur choisi.", "Scarica l'ultimo switch-cheats.zip e lo installa nella cartella cheat dell'emulatore scelto.", "最新の switch-cheats.zip をダウンロードし、選択したエミュレーターのチートフォルダにインストールします。"),
        "install.download" to a("Download:", "Download:", "Descarga:", "Téléchargement :", "Download:", "ダウンロード:"),
        "install.extract" to a("Installing:", "Installiere:", "Instalando:", "Installation :", "Installazione:", "インストール中:"),
        "install.filesSuffix" to a(" files", " Dateien", " archivos", " fichiers", " file", " ファイル"),
        "install.hint" to a("Tap Start to begin.", "Tippe auf Starten.", "Toca Iniciar para empezar.", "Appuie sur Démarrer.", "Tocca Avvia per iniziare.", "「スタート」で開始します。"),

        // ---- Storage / permissions ----
        "storage.title" to a("Storage access", "Speicherzugriff", "Acceso al almacenamiento", "Accès au stockage", "Accesso all'archiviazione", "ストレージアクセス"),
        "storage.needAllFiles" to a("This app needs \"All files access\" to write into the emulator folders. Tap to grant it.", "Diese App braucht „Zugriff auf alle Dateien\", um in die Emulator-Ordner zu schreiben. Zum Erteilen tippen.", "Esta app necesita «Acceso a todos los archivos» para escribir en las carpetas del emulador. Toca para concederlo.", "Cette application a besoin de « Accès à tous les fichiers » pour écrire dans les dossiers de l'émulateur. Touche pour l'accorder.", "Questa app richiede «Accesso a tutti i file» per scrivere nelle cartelle dell'emulatore. Tocca per concederlo.", "エミュレーターのフォルダに書き込むには「すべてのファイルへのアクセス」が必要です。タップして許可してください。"),
        "storage.grantAllFiles" to a("Allow \"All files access\"", "„Alle Dateien\" erlauben", "Conceder acceso a todos los archivos", "Accorder l'accès à tous les fichiers", "Concedi accesso a tutti i file", "「すべてのファイル」を許可"),
        "storage.pickFolder" to a("Pick the emulator folder", "Emulator-Ordner wählen", "Elegir la carpeta del emulador", "Choisir le dossier de l'émulateur", "Scegli la cartella dell'emulatore", "エミュレーターのフォルダを選択"),
        "storage.safHint" to a("On newer Android, apps can't write into another app's Android/data folder directly. Pick that emulator's folder once so the app may write there.", "Auf neueren Android-Versionen dürfen Apps nicht direkt in den Android/data-Ordner einer anderen App schreiben. Wähle den Emulator-Ordner einmal aus, damit die App dorthin schreiben darf.", "En Android más nuevo, las apps no pueden escribir directamente en la carpeta Android/data de otra app. Elige esa carpeta del emulador una vez para permitir la escritura.", "Sur Android récent, les apps ne peuvent pas écrire directement dans le dossier Android/data d'une autre app. Choisis ce dossier de l'émulateur une fois pour autoriser l'écriture.", "新しい Android では、アプリは他アプリの Android/data フォルダに直接書き込めません。書き込みを許可するために、そのエミュレーターのフォルダを一度選択してください。", ),
        "storage.folderReady" to a("Folder access granted.", "Ordnerzugriff erteilt.", "Acceso a la carpeta concedido.", "Accès au dossier accordé.", "Accesso alla cartella concesso.", "フォルダへのアクセスを許可しました。"),
        "storage.exportInstead" to a("Or export to a folder and copy it yourself", "Oder in einen Ordner exportieren und selbst kopieren", "O exportar a una carpeta y copiarlo tú mismo", "Ou exporter vers un dossier et copier soi-même", "Oppure esporta in una cartella e copiala tu", "またはフォルダにエクスポートして自分でコピー"),

        // ---- Info ----
        "info.title" to a("Info", "Info", "Información", "Infos", "Informazioni", "情報"),
        "info.source" to a("Source: ", "Quelle: ", "Fuente: ", "Source : ", "Fonte: ", "ソース: "),
        "info.target" to a("Target: ", "Ziel: ", "Destino: ", "Cible : ", "Destinazione: ", "保存先: "),
        "info.appVersion" to a("App version: ", "App-Version: ", "Versión de la app: ", "Version de l'app : ", "Versione app: ", "アプリバージョン: "),
        "info.language" to a("Language", "Sprache", "Idioma", "Langue", "Lingua", "言語"),
        "info.note" to a("The switch-cheats.zip cheats file comes from the GitHub repo above and is updated continuously.", "Die Cheats-Datei switch-cheats.zip stammt aus dem obigen GitHub-Repo und wird laufend aktualisiert.", "El archivo switch-cheats.zip proviene del repositorio de GitHub de arriba y se actualiza continuamente.", "Le fichier switch-cheats.zip provient du dépôt GitHub ci-dessus et est mis à jour en continu.", "Il file switch-cheats.zip proviene dal repository GitHub qui sopra e viene aggiornato continuamente.", "上記の GitHub リポジトリの switch-cheats.zip は継続的に更新されます。"),

        // ---- App update ----
        "appupdate.title" to a("App update", "App-Update", "Actualizar la app", "Mise à jour de l'app", "Aggiorna app", "アプリの更新"),
        "appupdate.desc" to a("Checks whether a new version of this app is available and installs the new .apk if needed.", "Prüft, ob eine neue Version dieser App verfügbar ist, und installiert bei Bedarf die neue .apk.", "Comprueba si hay una nueva versión de esta app e instala el nuevo .apk si es necesario.", "Vérifie si une nouvelle version de cette application est disponible et installe le nouveau .apk si besoin.", "Controlla se è disponibile una nuova versione di questa app e installa il nuovo .apk se necessario.", "このアプリの新しいバージョンを確認し、必要に応じて新しい .apk をインストールします。"),
        "appupdate.check" to a("Check for app update", "Nach App-Update suchen", "Buscar actualización", "Rechercher une mise à jour", "Cerca aggiornamento", "アプリの更新を確認"),
        "appupdate.checking" to a("Checking for app updates...", "Suche nach App-Updates...", "Buscando actualizaciones de la app...", "Recherche de mises à jour...", "Ricerca aggiornamenti...", "アプリの更新を確認中..."),
        "appupdate.upToDate" to a("No app update available.", "Kein App-Update verfügbar.", "No hay actualización de la app disponible.", "Aucune mise à jour disponible.", "Nessun aggiornamento disponibile.", "アプリの更新はありません。"),
        "appupdate.availablePrefix" to a("App update available: v", "App-Update verfügbar: v", "Actualización disponible: v", "Mise à jour disponible : v", "Aggiornamento disponibile: v", "アプリの更新があります: v"),
        "appupdate.installHint" to a("Tap again to download and install.", "Erneut tippen zum Herunterladen und Installieren.", "Toca de nuevo para descargar e instalar.", "Touche à nouveau pour télécharger et installer.", "Tocca di nuovo per scaricare e installare.", "もう一度タップしてダウンロードとインストール。"),

        // ---- Status ----
        "status.checkInternet" to a("Checking internet connection...", "Prüfe Internetverbindung...", "Comprobando la conexión a Internet...", "Vérification de la connexion Internet...", "Controllo della connessione Internet...", "インターネット接続を確認中..."),
        "status.connecting" to a("Connecting to GitHub...", "Verbinde mit GitHub...", "Conectando con GitHub...", "Connexion à GitHub...", "Connessione a GitHub...", "GitHub に接続中..."),
        "status.downloading" to a("Downloading switch-cheats.zip...", "Lade switch-cheats.zip herunter...", "Descargando switch-cheats.zip...", "Téléchargement de switch-cheats.zip...", "Download di switch-cheats.zip...", "switch-cheats.zip をダウンロード中..."),
        "status.extracting" to a("Installing to the emulator folder...", "Installiere in den Emulator-Ordner...", "Instalando en la carpeta del emulador...", "Installation dans le dossier de l'émulateur...", "Installazione nella cartella dell'emulatore...", "エミュレーターのフォルダにインストール中..."),

        // ---- Results ----
        "result.noInternet" to a("No internet connection available.", "Keine Internetverbindung verfügbar.", "No hay conexión a Internet disponible.", "Aucune connexion Internet disponible.", "Nessuna connessione a Internet disponibile.", "インターネット接続がありません。"),
        "result.errorPrefix" to a("Error: ", "Fehler: ", "Error: ", "Erreur : ", "Errore: ", "エラー: "),
        "result.cancelled" to a("Download cancelled.", "Download abgebrochen.", "Descarga cancelada.", "Téléchargement annulé.", "Download annullato.", "ダウンロードを中止しました。"),
        "result.cancelledResume" to a("Cancelled — will resume on the next attempt.", "Abgebrochen — wird beim nächsten Versuch fortgesetzt.", "Cancelado — se reanudará en el próximo intento.", "Annulé — reprendra à la prochaine tentative.", "Annullato — riprenderà al prossimo tentativo.", "中止しました — 次回は続きから再開します。"),
        "result.doneInstalledPrefix" to a("Done! ", "Fertig! ", "¡Listo! ", "Terminé ! ", "Fatto! ", "完了！ "),
        "result.doneInstalledSuffix" to a(" files installed.", " Dateien installiert.", " archivos instalados.", " fichiers installés.", " file installati.", " ファイルをインストールしました。"),
        "result.exportedPrefix" to a("Exported ", "Exportiert: ", "Exportado ", "Exporté ", "Esportati ", "エクスポート済み "),
        "result.exportedSuffix" to a(" files — copy the folder into your emulator.", " Dateien — kopiere den Ordner in deinen Emulator.", " archivos — copia la carpeta en tu emulador.", " fichiers — copie le dossier dans ton émulateur.", " file — copia la cartella nel tuo emulatore.", " ファイル — フォルダをエミュレーターにコピーしてください。"),
        "result.appUpdateDone" to a("App update downloaded — follow the installer prompt.", "App-Update geladen — folge dem Installations-Dialog.", "Actualización descargada — sigue el instalador.", "Mise à jour téléchargée — suivez l'installateur.", "Aggiornamento scaricato — segui l'installer.", "更新をダウンロードしました — インストーラーに従ってください。"),

        // ---- Errors (mirror NRO) ----
        "err.network" to a("Network error: ", "Netzwerkfehler: ", "Error de red: ", "Erreur réseau : ", "Errore di rete: ", "ネットワークエラー: "),
        "err.rateLimit" to a("GitHub rate limit reached - please try again later.", "GitHub-Rate-Limit erreicht - bitte später erneut versuchen.", "Límite de peticiones de GitHub alcanzado - inténtalo más tarde.", "Limite de requêtes GitHub atteinte - réessayez plus tard.", "Limite di richieste GitHub raggiunto - riprova più tardi.", "GitHub の API 制限に達しました。後でお試しください。"),
        "err.githubHttp" to a("GitHub API responded with HTTP ", "GitHub-API antwortete mit HTTP ", "La API de GitHub respondió con HTTP ", "L'API GitHub a répondu avec HTTP ", "L'API GitHub ha risposto con HTTP ", "GitHub API: HTTP "),
        "err.serverHttp" to a("Server responded with HTTP ", "Server antwortete mit HTTP ", "El servidor respondió con HTTP ", "Le serveur a répondu avec HTTP ", "Il server ha risposto con HTTP ", "サーバー: HTTP "),
        "err.assetNotFound" to a("Asset not found in release: ", "Asset nicht im Release gefunden: ", "Recurso no encontrado en el release: ", "Fichier introuvable dans la release : ", "Risorsa non trovata nella release: ", "リリースにアセットが見つかりません: "),
        "err.zipBroken" to a("ZIP archive is invalid or corrupted", "ZIP-Archiv ist ungültig oder beschädigt", "El archivo ZIP no es válido o está dañado", "L'archive ZIP est invalide ou endommagée", "L'archivio ZIP non è valido o danneggiato", "ZIP ファイルが無効か破損しています"),
        "err.writeFile" to a("Write error (storage full or no access?): ", "Schreibfehler (Speicher voll oder kein Zugriff?): ", "Error de escritura (¿sin espacio o sin acceso?): ", "Erreur d'écriture (plein ou pas d'accès ?) : ", "Errore di scrittura (pieno o senza accesso?): ", "書き込みエラー(容量不足またはアクセス不可?): "),
        "err.noAccess" to a("No write access to the emulator folder. Grant access or use Export.", "Kein Schreibzugriff auf den Emulator-Ordner. Zugriff erteilen oder Export nutzen.", "Sin acceso de escritura a la carpeta del emulador. Concede acceso o usa Exportar.", "Pas d'accès en écriture au dossier de l'émulateur. Accorde l'accès ou utilise Exporter.", "Nessun accesso in scrittura alla cartella dell'emulatore. Concedi l'accesso o usa Esporta.", "エミュレーターのフォルダに書き込めません。アクセスを許可するかエクスポートを使用してください。"),

        // ---- Footer / buttons ----
        "footer.online" to a("Online", "Online", "En línea", "En ligne", "Online", "オンライン"),
        "footer.offline" to a("Offline", "Offline", "Sin conexión", "Hors ligne", "Offline", "オフライン"),
        "btn.start" to a("Start", "Starten", "Iniciar", "Démarrer", "Avvia", "スタート"),
        "btn.cancel" to a("Cancel", "Abbrechen", "Cancelar", "Annuler", "Annulla", "キャンセル"),
        "btn.check" to a("Check", "Prüfen", "Comprobar", "Vérifier", "Verifica", "確認"),
        "btn.export" to a("Export", "Exportieren", "Exportar", "Exporter", "Esporta", "エクスポート"),
    )

    private fun a(vararg v: String) = arrayOf(*v)

    fun get(key: String, lang: Lang): String {
        val row = T[key] ?: return key
        val i = lang.ordinal
        return row.getOrElse(i) { row[0] }
    }
}
