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
        "install.onlyInstalled" to a("Only installed games", "Nur installierte Spiele", "Solo juegos instalados", "Uniquement les jeux installés", "Solo giochi installati", "インストール済みのゲームのみ"),
        "install.onlyInstalledHint" to a(
            "Writes cheats only for games already set up in the emulator (folders in load).",
            "Schreibt Cheats nur für Spiele, die im Emulator schon angelegt sind (Ordner in load).",
            "Escribe cheats solo para juegos ya configurados en el emulador (carpetas en load).",
            "N'écrit les cheats que pour les jeux déjà présents dans l'émulateur (dossiers dans load).",
            "Scrive i cheat solo per i giochi già presenti nell'emulatore (cartelle in load).",
            "エミュレーターに既に登録済みのゲーム（load 内のフォルダ）にのみチートを書き込みます。"),

        // ---- Storage / permissions ----
        "storage.title" to a("Storage access", "Speicherzugriff", "Acceso al almacenamiento", "Accès au stockage", "Accesso all'archiviazione", "ストレージアクセス"),
        "storage.needAllFiles" to a("This app needs \"All files access\" to write into the emulator folders. Tap to grant it.", "Diese App braucht „Zugriff auf alle Dateien\", um in die Emulator-Ordner zu schreiben. Zum Erteilen tippen.", "Esta app necesita «Acceso a todos los archivos» para escribir en las carpetas del emulador. Toca para concederlo.", "Cette application a besoin de « Accès à tous les fichiers » pour écrire dans les dossiers de l'émulateur. Touche pour l'accorder.", "Questa app richiede «Accesso a tutti i file» per scrivere nelle cartelle dell'emulatore. Tocca per concederlo.", "エミュレーターのフォルダに書き込むには「すべてのファイルへのアクセス」が必要です。タップして許可してください。"),
        "storage.grantAllFiles" to a("Allow \"All files access\"", "„Alle Dateien\" erlauben", "Conceder acceso a todos los archivos", "Accorder l'accès à tous les fichiers", "Concedi accesso a tutti i file", "「すべてのファイル」を許可"),
        "storage.pickFolder" to a("Pick the emulator folder", "Emulator-Ordner wählen", "Elegir la carpeta del emulador", "Choisir le dossier de l'émulateur", "Scegli la cartella dell'emulatore", "エミュレーターのフォルダを選択"),
        "storage.safHint" to a(
            "Just pick your emulator's folder once — its \"load\" folder, or any folder above it (even Android/data). The app finds the right spot and sorts every cheat there automatically.",
            "Wähle einfach einmal den Ordner deines Emulators — seinen „load\"-Ordner oder einen beliebigen Ordner darüber (auch Android/data). Die App findet die richtige Stelle und sortiert jeden Cheat automatisch dorthin.",
            "Solo elige una vez la carpeta de tu emulador — su carpeta «load» o cualquier carpeta superior (incluso Android/data). La app encuentra el lugar correcto y coloca cada cheat allí automáticamente.",
            "Choisis simplement une fois le dossier de ton émulateur — son dossier « load » ou n'importe quel dossier au-dessus (même Android/data). L'app trouve le bon endroit et y range chaque cheat automatiquement.",
            "Scegli una volta la cartella del tuo emulatore — la sua cartella «load» o una qualsiasi cartella superiore (anche Android/data). L'app trova il punto giusto e vi ordina automaticamente ogni cheat.",
            "エミュレーターのフォルダーを一度選ぶだけ —— その「load」フォルダー、またはその上位のフォルダー（Android/data でも可）。アプリが正しい場所を見つけ、各チートを自動で振り分けます。"),
        "storage.wrongFolder" to a(
            "That folder isn't part of the selected emulator. Please pick your emulator's folder (its \"load\" folder or a folder above it).",
            "Dieser Ordner gehört nicht zum gewählten Emulator. Bitte wähle den Ordner deines Emulators (seinen „load\"-Ordner oder einen Ordner darüber).",
            "Esa carpeta no pertenece al emulador seleccionado. Elige la carpeta de tu emulador (su carpeta «load» o una carpeta superior).",
            "Ce dossier ne fait pas partie de l'émulateur sélectionné. Choisis le dossier de ton émulateur (son dossier « load » ou un dossier au-dessus).",
            "Quella cartella non appartiene all'emulatore selezionato. Scegli la cartella del tuo emulatore (la sua cartella «load» o una cartella superiore).",
            "そのフォルダーは選択したエミュレーターのものではありません。エミュレーターのフォルダー（「load」フォルダー、またはその上位のフォルダー）を選んでください。"),
        "storage.folderReady" to a("Folder access granted.", "Ordnerzugriff erteilt.", "Acceso a la carpeta concedido.", "Accès au dossier accordé.", "Accesso alla cartella concesso.", "フォルダへのアクセスを許可しました。"),
        "storage.exportInstead" to a("Or export to a folder and copy it yourself", "Oder in einen Ordner exportieren und selbst kopieren", "O exportar a una carpeta y copiarlo tú mismo", "Ou exporter vers un dossier et copier soi-même", "Oppure esporta in una cartella e copiala tu", "またはフォルダにエクスポートして自分でコピー"),
        // Startup permission onboarding (shown once when a grant is still missing).
        "perm.title" to a("Storage access needed", "Speicherzugriff erforderlich", "Se necesita acceso al almacenamiento", "Accès au stockage requis", "Serve l'accesso all'archiviazione", "ストレージアクセスが必要です"),
        "perm.body" to a(
            "To save the cheats into your emulator's folder, this app needs permission to write to your device storage. It only writes cheat files — nothing else is read, collected or uploaded.",
            "Um die Cheats in den Ordner deines Emulators zu schreiben, braucht die App die Berechtigung, auf den Gerätespeicher zu schreiben. Sie schreibt nur Cheat-Dateien — nichts anderes wird gelesen, gesammelt oder hochgeladen.",
            "Para guardar los cheats en la carpeta de tu emulador, la app necesita permiso para escribir en el almacenamiento del dispositivo. Solo escribe archivos de cheats — no se lee, recopila ni sube nada más.",
            "Pour enregistrer les cheats dans le dossier de ton émulateur, l'app a besoin de l'autorisation d'écrire dans le stockage de l'appareil. Elle n'écrit que des fichiers de cheats — rien d'autre n'est lu, collecté ou envoyé.",
            "Per salvare i cheat nella cartella del tuo emulatore, l'app ha bisogno del permesso di scrivere nell'archiviazione del dispositivo. Scrive solo i file dei cheat — nient'altro viene letto, raccolto o caricato.",
            "チートをエミュレーターのフォルダに保存するには、デバイスのストレージへの書き込み許可が必要です。書き込むのはチートファイルだけで、それ以外は読み取り・収集・アップロードは行いません。"),
        "perm.later" to a("Not now", "Später", "Ahora no", "Plus tard", "Non ora", "後で"),

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
        "result.installedSummary" to a(
            "Done! %1\$d files · %2\$d games installed.",
            "Fertig! %1\$d Dateien · %2\$d Spiele installiert.",
            "¡Listo! %1\$d archivos · %2\$d juegos instalados.",
            "Terminé ! %1\$d fichiers · %2\$d jeux installés.",
            "Fatto! %1\$d file · %2\$d giochi installati.",
            "完了！ %1\$d ファイル・%2\$d ゲームをインストールしました。"),
        "result.exportedSummary" to a(
            "Exported %1\$d files · %2\$d games — copy the folder into your emulator.",
            "%1\$d Dateien · %2\$d Spiele exportiert — kopiere den Ordner in deinen Emulator.",
            "Exportados %1\$d archivos · %2\$d juegos — copia la carpeta en tu emulador.",
            "%1\$d fichiers · %2\$d jeux exportés — copie le dossier dans ton émulateur.",
            "Esportati %1\$d file · %2\$d giochi — copia la cartella nel tuo emulatore.",
            "%1\$d ファイル・%2\$d ゲームをエクスポートしました — フォルダをエミュレーターにコピーしてください。"),
        "result.noGames" to a(
            "No games found in the emulator's load folder. Set up your games in the emulator first, or turn this option off.",
            "Keine Spiele im load-Ordner des Emulators gefunden. Lege deine Spiele zuerst im Emulator an oder schalte diese Option aus.",
            "No se encontraron juegos en la carpeta load del emulador. Configura tus juegos primero en el emulador o desactiva esta opción.",
            "Aucun jeu trouvé dans le dossier load de l'émulateur. Configure d'abord tes jeux dans l'émulateur ou désactive cette option.",
            "Nessun gioco trovato nella cartella load dell'emulatore. Configura prima i tuoi giochi nell'emulatore o disattiva questa opzione.",
            "エミュレーターの load フォルダにゲームが見つかりません。先にエミュレーターでゲームを設定するか、このオプションをオフにしてください。"),

        // ---- Activation hint (after a successful install) ----
        "activate.title" to a("Almost done — enable the cheats", "Fast fertig — Cheats aktivieren", "Casi listo — activa los cheats", "Presque fini — active les cheats", "Quasi fatto — attiva i cheat", "あと一歩 — チートを有効化"),
        "activate.body" to a(
            "In %s, long-press your game → Properties → Cheats and turn on the ones you want. Then start the game.",
            "In %s: lange auf dein Spiel tippen → Eigenschaften → Cheats, dann die gewünschten aktivieren. Danach das Spiel starten.",
            "En %s, mantén pulsado tu juego → Propiedades → Cheats y activa los que quieras. Luego inicia el juego.",
            "Dans %s, appuie longuement sur ton jeu → Propriétés → Cheats et active ceux que tu veux. Puis lance le jeu.",
            "In %s, tieni premuto il gioco → Proprietà → Cheat e attiva quelli che vuoi. Poi avvia il gioco.",
            "%s でゲームを長押し → プロパティ → チート で使いたいものを有効にします。その後ゲームを起動してください。"),
        "activate.open" to a("Open %s", "%s öffnen", "Abrir %s", "Ouvrir %s", "Apri %s", "%s を開く"),

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
