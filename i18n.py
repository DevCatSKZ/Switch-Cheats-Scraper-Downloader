"""Lightweight internationalisation for the Switch Cheats Scraper GUI.

Design
------
* English is the *source* language: the English string is also the lookup key,
  so a missing translation transparently falls back to readable English.
* ``t("English text")`` returns the translation for the active language.
  Interpolated strings use named placeholders, e.g.
  ``t("Downloading {name}…", name=x)``.
* ``install_tk_i18n()`` monkey-patches the Tk/ttk widget factories, menus,
  treeview headings, window titles and ``messagebox`` so that every *static*
  ``text=`` / ``label=`` / ``title=`` / ``message=`` argument is passed through
  ``t()`` automatically at build time — no need to wrap hundreds of call sites.
  Only genuinely dynamic (f-string) text is wrapped by hand with ``t(...)``.

The active language is chosen once at start-up (from settings.json, or the
installer-provided ``default_lang.txt``); changing it in the GUI saves the
choice and restarts the app so every widget is rebuilt in the new language.
"""

from __future__ import annotations

# ---------------------------------------------------------------- languages
# code -> native display name (shown in the language picker).
LANGUAGES = {
    "en": "English",
    "de": "Deutsch",
    "es": "Español",
    "fr": "Français",
    "it": "Italiano",
    "ja": "日本語",
}

# Map an Inno Setup language *name* (the internal [Languages] Name:) to our
# program language code, so the installer can pre-select the program language.
INSTALLER_LANG_MAP = {
    "english": "en",
    "german": "de",
    "spanish": "es",
    "french": "fr",
    "italian": "it",
    "japanese": "ja",
}

_CURRENT = "en"


def available_languages() -> dict:
    return dict(LANGUAGES)


def normalize_lang(code: str) -> str:
    """Return a supported language code, defaulting to English."""
    if not code:
        return "en"
    code = str(code).strip().lower().replace("_", "-")
    if code in LANGUAGES:
        return code
    short = code.split("-", 1)[0]
    return short if short in LANGUAGES else "en"


def set_language(code: str) -> str:
    global _CURRENT
    _CURRENT = normalize_lang(code)
    return _CURRENT


def get_language() -> str:
    return _CURRENT


def language_name(code: str) -> str:
    return LANGUAGES.get(normalize_lang(code), "English")


def t(text, **kwargs):
    """Translate ``text`` into the active language (English fallback).

    Named ``kwargs`` are substituted with ``str.format`` afterwards, so the same
    ``{placeholder}`` works in every language.
    """
    if not isinstance(text, str) or not text:
        return text
    table = TRANSLATIONS.get(_CURRENT)
    s = table.get(text, text) if table else text
    if kwargs:
        try:
            s = s.format(**kwargs)
        except Exception:
            try:
                s = text.format(**kwargs)
            except Exception:
                pass
    return s


# ------------------------------------------------------------- Tk auto-hook
_INSTALLED = False


def _tr_kw(kw, keys=("text",)):
    for k in keys:
        v = kw.get(k)
        if isinstance(v, str) and v:
            kw[k] = t(v)
    return kw


def _wrap_widget(cls):
    """Translate the ``text=`` option in a widget's __init__ and configure()."""
    orig_init = cls.__init__

    def __init__(self, *a, **kw):
        _tr_kw(kw)
        orig_init(self, *a, **kw)

    cls.__init__ = __init__

    for name in ("configure", "config"):
        orig_cfg = getattr(cls, name, None)
        if orig_cfg is None:
            continue

        def make(orig_cfg):
            def cfg(self, cnf=None, **kw):
                _tr_kw(kw)
                return orig_cfg(self, cnf, **kw)
            return cfg

        try:
            setattr(cls, name, make(orig_cfg))
        except Exception:
            pass


def _wrap_menu(menu_cls):
    for name in ("add_command", "add_cascade", "add_checkbutton",
                 "add_radiobutton", "insert_command", "insert_cascade",
                 "entryconfigure", "entryconfig"):
        orig = getattr(menu_cls, name, None)
        if orig is None:
            continue

        def make(orig):
            def wrapper(self, *a, **kw):
                _tr_kw(kw, ("label",))
                return orig(self, *a, **kw)
            return wrapper

        try:
            setattr(menu_cls, name, make(orig))
        except Exception:
            pass


def _wrap_heading(tree_cls):
    orig = getattr(tree_cls, "heading", None)
    if orig is None:
        return

    def heading(self, column, option=None, **kw):
        _tr_kw(kw)
        return orig(self, column, option, **kw)

    try:
        tree_cls.heading = heading
    except Exception:
        pass


def _wrap_title(*classes):
    for cls in classes:
        orig = getattr(cls, "title", None)
        if orig is None:
            continue

        def make(orig):
            def title(self, string=None):
                if isinstance(string, str) and string:
                    string = t(string)
                return orig(self, string)
            return title

        try:
            cls.title = make(orig)
        except Exception:
            pass


def _wrap_messagebox(mb):
    for name in ("showinfo", "showwarning", "showerror",
                 "askyesno", "askokcancel", "askquestion",
                 "askretrycancel", "askyesnocancel"):
        orig = getattr(mb, name, None)
        if orig is None:
            continue

        def make(orig):
            def wrapper(*a, **kw):
                a = list(a)
                if a and isinstance(a[0], str):
                    a[0] = t(a[0])          # title
                if len(a) > 1 and isinstance(a[1], str):
                    a[1] = t(a[1])          # message
                for k in ("title", "message", "detail"):
                    if isinstance(kw.get(k), str):
                        kw[k] = t(kw[k])
                return orig(*a, **kw)
            return wrapper

        try:
            setattr(mb, name, make(orig))
        except Exception:
            pass


def install_tk_i18n():
    """Patch the Tk toolkit so static UI text is auto-translated. Idempotent."""
    global _INSTALLED
    if _INSTALLED:
        return
    import tkinter as tk
    from tkinter import ttk
    from tkinter import messagebox

    for cls in (ttk.Button, ttk.Label, ttk.Checkbutton, ttk.Radiobutton,
                ttk.LabelFrame, ttk.Menubutton, tk.Label, tk.Button,
                tk.Checkbutton, tk.Radiobutton, tk.LabelFrame):
        try:
            _wrap_widget(cls)
        except Exception:
            pass
    _wrap_menu(tk.Menu)
    _wrap_heading(ttk.Treeview)
    _wrap_title(tk.Toplevel, tk.Tk)
    _wrap_messagebox(messagebox)

    # File dialogs: translate the window title= keyword.
    try:
        from tkinter import filedialog
        for name in ("askdirectory", "askopenfilename", "asksaveasfilename",
                     "askopenfilenames"):
            orig = getattr(filedialog, name, None)
            if orig is None:
                continue

            def make(orig):
                def wrapper(*a, **kw):
                    if isinstance(kw.get("title"), str):
                        kw["title"] = t(kw["title"])
                    return orig(*a, **kw)
                return wrapper
            setattr(filedialog, name, make(orig))
    except Exception:
        pass

    # simpledialog.askstring(title, prompt, ...): translate title + prompt.
    try:
        from tkinter import simpledialog
        _orig_ask = simpledialog.askstring

        def _askstring(*a, **kw):
            a = list(a)
            if a and isinstance(a[0], str):
                a[0] = t(a[0])
            if len(a) > 1 and isinstance(a[1], str):
                a[1] = t(a[1])
            for k in ("title", "prompt"):
                if isinstance(kw.get(k), str):
                    kw[k] = t(kw[k])
            return _orig_ask(*a, **kw)
        simpledialog.askstring = _askstring
    except Exception:
        pass

    _INSTALLED = True


# =====================================================================
#  Translation catalogue.
#
#  Authored as {english_source: {lang: translation}} so every string's six
#  languages sit together (easy to review). It is pivoted into TRANSLATIONS
#  ({lang: {english: translation}}) at import time. English is the fallback.
#
#  Terms deliberately kept in English across languages (brand / universal tech):
#    Download*, Scrape, Cheats, API, Token, ZIP, CSV, DB, DLC, URL, SD,
#    GitHub, cheatslips.com, DevCatSKZ, TitleDB, GBATemp, Hamlet, Sthetix,
#    Breeze, NXCheatCode, Chansey, MyNXCheats, Ibnux, reCAPTCHA, Atmosphère,
#    EdiZon, Chromium, Firefox, Chrome, 60FPS/Res/GFX.
#  (*In German "Download" is kept as a common loanword; other languages use
#   their natural verb where it reads better.)
# =====================================================================

# Filled by the section dicts below (defined further down, then merged).
TRANSLATIONS = {"de": {}, "es": {}, "fr": {}, "it": {}, "ja": {}}

_CATALOG = {}


def _merge(section):
    _CATALOG.update(section)


def _build():
    for en, per_lang in _CATALOG.items():
        for lang, val in per_lang.items():
            if lang in TRANSLATIONS:
                TRANSLATIONS[lang][en] = val


# ------------------------------------------------------------------ sections
# Each section is merged into _CATALOG; _build() pivots them at the bottom.

# ---- Section / group titles ------------------------------------------------
_merge({
    "External Cheat Sources": {
        "de": "Externe Cheat-Quellen", "es": "Fuentes externas de cheats",
        "fr": "Sources de cheats externes", "it": "Fonti di cheat esterne",
        "ja": "外部チートソース"},
    "Get Cheat Information": {
        "de": "Cheat-Informationen abrufen", "es": "Obtener información de cheats",
        "fr": "Obtenir les infos des cheats", "it": "Ottieni informazioni cheat",
        "ja": "チート情報を取得"},
    "Scrape & Download Cheat Files · cheatslips.com": {
        "de": "Cheat-Dateien scrapen & downloaden · cheatslips.com",
        "es": "Extraer y descargar archivos de cheats · cheatslips.com",
        "fr": "Extraire et télécharger les cheats · cheatslips.com",
        "it": "Estrai e scarica file di cheat · cheatslips.com",
        "ja": "チートファイルの取得とダウンロード · cheatslips.com"},
    "Search": {
        "de": "Suche", "es": "Buscar", "fr": "Recherche", "it": "Cerca",
        "ja": "検索"},
    "Database": {
        "de": "Datenbank", "es": "Base de datos", "fr": "Base de données",
        "it": "Database", "ja": "データベース"},
    "Game": {
        "de": "Spiel", "es": "Juego", "fr": "Jeu", "it": "Gioco", "ja": "ゲーム"},
    "Program": {
        "de": "Programm", "es": "Programa", "fr": "Programme", "it": "Programma",
        "ja": "プログラム"},
    "Data (from DevCatSKZ)": {
        "de": "Daten (von DevCatSKZ)", "es": "Datos (de DevCatSKZ)",
        "fr": "Données (de DevCatSKZ)", "it": "Dati (da DevCatSKZ)",
        "ja": "データ（DevCatSKZ より）"},
    "Updates": {
        "de": "Updates", "es": "Actualizaciones", "fr": "Mises à jour",
        "it": "Aggiornamenti", "ja": "アップデート"},
    "Updating": {
        "de": "Update läuft", "es": "Actualizando", "fr": "Mise à jour",
        "it": "Aggiornamento", "ja": "更新中"},
})

# ---- DevCatSKZ featured card ----------------------------------------------
_merge({
    "★  Get Everything from DevCatSKZ Github Repo": {
        "de": "★  Alles aus dem DevCatSKZ-GitHub-Repo holen",
        "es": "★  Obtener todo del repo de GitHub de DevCatSKZ",
        "fr": "★  Tout récupérer depuis le dépôt GitHub DevCatSKZ",
        "it": "★  Ottieni tutto dal repo GitHub di DevCatSKZ",
        "ja": "★  DevCatSKZ の GitHub リポジトリからすべて取得"},
    "Download Cheats": {
        "de": "Cheats herunterladen", "es": "Descargar cheats",
        "fr": "Télécharger les cheats", "it": "Scarica i cheat",
        "ja": "チートをダウンロード"},
    "Download Database": {
        "de": "Datenbank herunterladen", "es": "Descargar base de datos",
        "fr": "Télécharger la base de données", "it": "Scarica il database",
        "ja": "データベースをダウンロード"},
    "★  Download Complete": {
        "de": "★  Komplett herunterladen", "es": "★  Descargar todo",
        "fr": "★  Tout télécharger", "it": "★  Scarica tutto",
        "ja": "★  すべてダウンロード"},
    "Download Covers": {
        "de": "Cover herunterladen", "es": "Descargar carátulas",
        "fr": "Télécharger les jaquettes", "it": "Scarica le copertine",
        "ja": "カバー画像をダウンロード"},
    "Check updates at startup": {
        "de": "Beim Start auf Updates prüfen",
        "es": "Buscar actualizaciones al iniciar",
        "fr": "Vérifier les mises à jour au démarrage",
        "it": "Controlla aggiornamenti all'avvio",
        "ja": "起動時にアップデートを確認"},
    "Check Updates": {
        "de": "Auf Updates prüfen", "es": "Buscar actualizaciones",
        "fr": "Vérifier les mises à jour", "it": "Controlla aggiornamenti",
        "ja": "アップデートを確認"},
})

# ---- External source buttons ----------------------------------------------
_merge({
    "Download GBATemp Archive": {
        "de": "GBATemp-Archiv herunterladen", "es": "Descargar archivo GBATemp",
        "fr": "Télécharger l'archive GBATemp", "it": "Scarica archivio GBATemp",
        "ja": "GBATemp アーカイブをダウンロード"},
    "Download Hamlet TitleDB": {
        "de": "Hamlet TitleDB herunterladen", "es": "Descargar Hamlet TitleDB",
        "fr": "Télécharger Hamlet TitleDB", "it": "Scarica Hamlet TitleDB",
        "ja": "Hamlet TitleDB をダウンロード"},
    "Download Hamlet 60FPS/Res/GFX": {
        "de": "Hamlet 60FPS/Res/GFX herunterladen",
        "es": "Descargar Hamlet 60FPS/Res/GFX",
        "fr": "Télécharger Hamlet 60FPS/Res/GFX",
        "it": "Scarica Hamlet 60FPS/Res/GFX",
        "ja": "Hamlet 60FPS/Res/GFX をダウンロード"},
    "Download TitleDB": {
        "de": "TitleDB herunterladen", "es": "Descargar TitleDB",
        "fr": "Télécharger TitleDB", "it": "Scarica TitleDB",
        "ja": "TitleDB をダウンロード"},
    "Download Ibnux": {
        "de": "Ibnux herunterladen", "es": "Descargar Ibnux",
        "fr": "Télécharger Ibnux", "it": "Scarica Ibnux",
        "ja": "Ibnux をダウンロード"},
    "Download Sthetix TitleDB": {
        "de": "Sthetix TitleDB herunterladen", "es": "Descargar Sthetix TitleDB",
        "fr": "Télécharger Sthetix TitleDB", "it": "Scarica Sthetix TitleDB",
        "ja": "Sthetix TitleDB をダウンロード"},
    "Download Breeze NXCheatCode": {
        "de": "Breeze NXCheatCode herunterladen",
        "es": "Descargar Breeze NXCheatCode",
        "fr": "Télécharger Breeze NXCheatCode",
        "it": "Scarica Breeze NXCheatCode",
        "ja": "Breeze NXCheatCode をダウンロード"},
    "Download Chansey 60FPS/Res/GFX": {
        "de": "Chansey 60FPS/Res/GFX herunterladen",
        "es": "Descargar Chansey 60FPS/Res/GFX",
        "fr": "Télécharger Chansey 60FPS/Res/GFX",
        "it": "Scarica Chansey 60FPS/Res/GFX",
        "ja": "Chansey 60FPS/Res/GFX をダウンロード"},
    "Download MyNXCheats": {
        "de": "MyNXCheats herunterladen", "es": "Descargar MyNXCheats",
        "fr": "Télécharger MyNXCheats", "it": "Scarica MyNXCheats",
        "ja": "MyNXCheats をダウンロード"},
    "Import Folder": {
        "de": "Ordner importieren", "es": "Importar carpeta",
        "fr": "Importer un dossier", "it": "Importa cartella",
        "ja": "フォルダをインポート"},
    "Import ZIP": {
        "de": "ZIP importieren", "es": "Importar ZIP", "fr": "Importer un ZIP",
        "it": "Importa ZIP", "ja": "ZIP をインポート"},
    "★ Scrape & Download Everything": {
        "de": "★ Alles scrapen & herunterladen",
        "es": "★ Extraer y descargar todo",
        "fr": "★ Tout extraire et télécharger",
        "it": "★ Estrai e scarica tutto",
        "ja": "★ すべて取得してダウンロード"},
})

# ---- Get-cheat-information buttons -----------------------------------------
_merge({
    "Get Names": {
        "de": "Namen abrufen", "es": "Obtener nombres", "fr": "Obtenir les noms",
        "it": "Ottieni nomi", "ja": "名前を取得"},
    "Get Region": {
        "de": "Region abrufen", "es": "Obtener región", "fr": "Obtenir la région",
        "it": "Ottieni regione", "ja": "リージョンを取得"},
    "Get Versions from TitleDB": {
        "de": "Versionen aus TitleDB abrufen",
        "es": "Obtener versiones de TitleDB",
        "fr": "Obtenir les versions depuis TitleDB",
        "it": "Ottieni versioni da TitleDB",
        "ja": "TitleDB からバージョンを取得"},
    "Get Versions Cheatslips": {
        "de": "Versionen von Cheatslips abrufen",
        "es": "Obtener versiones de Cheatslips",
        "fr": "Obtenir les versions Cheatslips",
        "it": "Ottieni versioni da Cheatslips",
        "ja": "Cheatslips からバージョンを取得"},
    "Get Descriptions": {
        "de": "Beschreibungen abrufen", "es": "Obtener descripciones",
        "fr": "Obtenir les descriptions", "it": "Ottieni descrizioni",
        "ja": "説明文を取得"},
})

# ---- Auth + scrape + download rows -----------------------------------------
_merge({
    "Email:": {"de": "E-Mail:", "es": "Correo:", "fr": "E-mail :",
               "it": "E-mail:", "ja": "メール:"},
    "Password:": {"de": "Passwort:", "es": "Contraseña:", "fr": "Mot de passe :",
                  "it": "Password:", "ja": "パスワード:"},
    "remember": {"de": "merken", "es": "recordar", "fr": "mémoriser",
                 "it": "ricorda", "ja": "記憶する"},
    "or Token:": {"de": "oder Token:", "es": "o Token:", "fr": "ou Token :",
                  "it": "o Token:", "ja": "または Token:"},
    "Browser Login": {
        "de": "Browser-Login", "es": "Iniciar sesión en el navegador",
        "fr": "Connexion via le navigateur", "it": "Accedi dal browser",
        "ja": "ブラウザでログイン"},
    "● not checked": {
        "de": "● nicht geprüft", "es": "● sin comprobar", "fr": "● non vérifié",
        "it": "● non verificato", "ja": "● 未確認"},
    "● checking...": {
        "de": "● wird geprüft…", "es": "● comprobando…", "fr": "● vérification…",
        "it": "● verifica…", "ja": "● 確認中…"},
    "● Online": {"de": "● Online", "es": "● En línea", "fr": "● En ligne",
                 "it": "● Online", "ja": "● オンライン"},
    "● OFFLINE": {"de": "● OFFLINE", "es": "● SIN CONEXIÓN", "fr": "● HORS LIGNE",
                  "it": "● OFFLINE", "ja": "● オフライン"},
    "Check Online": {
        "de": "Online prüfen", "es": "Comprobar conexión",
        "fr": "Vérifier la connexion", "it": "Verifica online",
        "ja": "オンライン確認"},
    "check at startup": {
        "de": "beim Start prüfen", "es": "comprobar al iniciar",
        "fr": "vérifier au démarrage", "it": "controlla all'avvio",
        "ja": "起動時に確認"},
    "Scrape": {"de": "Scrapen", "es": "Extraer", "fr": "Extraire",
               "it": "Estrai", "ja": "取得"},
    "Update Recent": {
        "de": "Neue aktualisieren", "es": "Actualizar recientes",
        "fr": "Mettre à jour les récents", "it": "Aggiorna recenti",
        "ja": "最新を更新"},
    "pages:": {"de": "Seiten:", "es": "páginas:", "fr": "pages :",
               "it": "pagine:", "ja": "ページ:"},
    "full catalog (all games, slower)": {
        "de": "vollständiger Katalog (alle Spiele, langsamer)",
        "es": "catálogo completo (todos los juegos, más lento)",
        "fr": "catalogue complet (tous les jeux, plus lent)",
        "it": "catalogo completo (tutti i giochi, più lento)",
        "ja": "全カタログ（全ゲーム・低速）"},
    "skip 0-cheat builds": {
        "de": "Builds mit 0 Cheats überspringen",
        "es": "omitir builds con 0 cheats",
        "fr": "ignorer les builds à 0 cheat",
        "it": "salta le build con 0 cheat",
        "ja": "チート0件のビルドをスキップ"},
    "rescan": {"de": "erneut scannen", "es": "reescanear", "fr": "rescanner",
               "it": "riscansiona", "ja": "再スキャン"},
    "download after scrape": {
        "de": "nach dem Scrapen herunterladen",
        "es": "descargar tras extraer",
        "fr": "télécharger après l'extraction",
        "it": "scarica dopo l'estrazione",
        "ja": "取得後にダウンロード"},
    "Stop": {"de": "Stopp", "es": "Detener", "fr": "Arrêter", "it": "Ferma",
             "ja": "停止"},
    "Output:": {"de": "Ausgabe:", "es": "Salida:", "fr": "Sortie :",
                "it": "Output:", "ja": "出力先:"},
    "Open": {"de": "Öffnen", "es": "Abrir", "fr": "Ouvrir", "it": "Apri",
             "ja": "開く"},
    "Download via browser when API is limited (keeps downloading until complete)": {
        "de": "Bei API-Limit über den Browser herunterladen (lädt bis zur Vollständigkeit weiter)",
        "es": "Descargar por navegador cuando la API está limitada (sigue hasta completar)",
        "fr": "Télécharger via le navigateur quand l'API est limitée (jusqu'à la fin)",
        "it": "Scarica dal browser quando l'API è limitata (continua fino al completamento)",
        "ja": "API制限時はブラウザでダウンロード（完了するまで継続）"},
    "Browser:": {"de": "Browser:", "es": "Navegador:", "fr": "Navigateur :",
                 "it": "Browser:", "ja": "ブラウザ:"},
    "Reset API Limit": {
        "de": "API-Limit zurücksetzen", "es": "Restablecer límite de la API",
        "fr": "Réinitialiser la limite de l'API",
        "it": "Reimposta limite API", "ja": "API制限をリセット"},
    "Download:": {"de": "Download:", "es": "Descargar:", "fr": "Télécharger :",
                  "it": "Scarica:", "ja": "ダウンロード:"},
    "Download (API only)": {
        "de": "Download (nur API)", "es": "Descargar (solo API)",
        "fr": "Télécharger (API seule)", "it": "Scarica (solo API)",
        "ja": "ダウンロード（API のみ）"},
    "Download Selected": {
        "de": "Auswahl herunterladen", "es": "Descargar selección",
        "fr": "Télécharger la sélection", "it": "Scarica selezionati",
        "ja": "選択項目をダウンロード"},
    "Download via Browser": {
        "de": "Über Browser herunterladen", "es": "Descargar por navegador",
        "fr": "Télécharger via le navigateur", "it": "Scarica dal browser",
        "ja": "ブラウザでダウンロード"},
    "Build Full Dataset": {
        "de": "Kompletten Datensatz erstellen", "es": "Crear conjunto completo",
        "fr": "Créer le jeu de données complet", "it": "Crea dataset completo",
        "ja": "全データセットを構築"},
})

# ---- Search row + theme/language toggles -----------------------------------
_merge({
    "Auto scan": {"de": "Auto-Scan", "es": "Escaneo automático",
                  "fr": "Analyse auto", "it": "Scansione auto", "ja": "自動スキャン"},
    "Not downloaded": {
        "de": "Nicht heruntergeladen", "es": "No descargados",
        "fr": "Non téléchargés", "it": "Non scaricati", "ja": "未ダウンロード"},
    "Show Unnamed Games": {
        "de": "Unbenannte Spiele zeigen", "es": "Mostrar juegos sin nombre",
        "fr": "Afficher les jeux sans nom", "it": "Mostra giochi senza nome",
        "ja": "名称未設定のゲームを表示"},
    "Hide placeholder builds": {
        "de": "Platzhalter-Builds ausblenden", "es": "Ocultar builds de relleno",
        "fr": "Masquer les builds fictifs", "it": "Nascondi build segnaposto",
        "ja": "プレースホルダのビルドを非表示"},
    "Show Covers": {
        "de": "Cover zeigen", "es": "Mostrar carátulas",
        "fr": "Afficher les jaquettes", "it": "Mostra copertine",
        "ja": "カバー画像を表示"},
    "Save Covers": {
        "de": "Cover speichern", "es": "Guardar carátulas",
        "fr": "Enregistrer les jaquettes", "it": "Salva copertine",
        "ja": "カバー画像を保存"},
    "Show Description": {
        "de": "Beschreibung zeigen", "es": "Mostrar descripción",
        "fr": "Afficher la description", "it": "Mostra descrizione",
        "ja": "説明文を表示"},
    "☀ Light Mode": {
        "de": "☀ Heller Modus", "es": "☀ Modo claro", "fr": "☀ Mode clair",
        "it": "☀ Tema chiaro", "ja": "☀ ライトモード"},
    "☾ Dark Mode": {
        "de": "☾ Dunkler Modus", "es": "☾ Modo oscuro", "fr": "☾ Mode sombre",
        "it": "☾ Tema scuro", "ja": "☾ ダークモード"},
    "Language": {"de": "Sprache", "es": "Idioma", "fr": "Langue",
                 "it": "Lingua", "ja": "言語"},
})

# ---- Table column headings -------------------------------------------------
_merge({
    "DL": {"de": "DL", "es": "DL", "fr": "DL", "it": "DL", "ja": "DL"},
    "Region": {"de": "Region", "es": "Región", "fr": "Région", "it": "Regione",
               "ja": "リージョン"},
    "Version": {"de": "Version", "es": "Versión", "fr": "Version",
                "it": "Versione", "ja": "バージョン"},
    "Title ID": {"de": "Title-ID", "es": "Title ID", "fr": "Title ID",
                 "it": "Title ID", "ja": "Title ID"},
    "Build ID": {"de": "Build-ID", "es": "Build ID", "fr": "Build ID",
                 "it": "Build ID", "ja": "Build ID"},
    "Uploaded": {"de": "Hochgeladen", "es": "Subido", "fr": "Mis en ligne",
                 "it": "Caricato", "ja": "アップロード日"},
    "Cheats": {"de": "Cheats", "es": "Cheats", "fr": "Cheats", "it": "Cheat",
               "ja": "チート数"},
    "Source": {"de": "Quelle", "es": "Fuente", "fr": "Source", "it": "Fonte",
               "ja": "ソース"},
})

# ---- Database bar + repair menu --------------------------------------------
_merge({
    "Refresh": {"de": "Aktualisieren", "es": "Actualizar", "fr": "Actualiser",
                "it": "Aggiorna", "ja": "更新"},
    "Add Entry": {"de": "Eintrag hinzufügen", "es": "Añadir entrada",
                  "fr": "Ajouter une entrée", "it": "Aggiungi voce",
                  "ja": "エントリを追加"},
    "Export CSV": {"de": "CSV exportieren", "es": "Exportar CSV",
                   "fr": "Exporter en CSV", "it": "Esporta CSV",
                   "ja": "CSV をエクスポート"},
    "Export DB": {"de": "DB exportieren", "es": "Exportar BD",
                  "fr": "Exporter la BD", "it": "Esporta DB",
                  "ja": "DB をエクスポート"},
    "Import DB": {"de": "DB importieren", "es": "Importar BD",
                  "fr": "Importer la BD", "it": "Importa DB",
                  "ja": "DB をインポート"},
    "Export to SD": {"de": "Auf SD exportieren", "es": "Exportar a SD",
                     "fr": "Exporter vers la SD", "it": "Esporta su SD",
                     "ja": "SD にエクスポート"},
    "Export to ZIP": {"de": "Als ZIP exportieren", "es": "Exportar a ZIP",
                      "fr": "Exporter en ZIP", "it": "Esporta in ZIP",
                      "ja": "ZIP にエクスポート"},
    "Repair ▾": {"de": "Reparieren ▾", "es": "Reparar ▾", "fr": "Réparer ▾",
                 "it": "Ripara ▾", "ja": "修復 ▾"},
    "Clean invalid cheat files": {
        "de": "Ungültige Cheat-Dateien bereinigen",
        "es": "Limpiar archivos de cheats no válidos",
        "fr": "Nettoyer les fichiers de cheats non valides",
        "it": "Pulisci i file di cheat non validi",
        "ja": "無効なチートファイルを整理"},
    "Retry quota-skipped builds": {
        "de": "Wegen Kontingent übersprungene Builds erneut versuchen",
        "es": "Reintentar builds omitidos por cuota",
        "fr": "Réessayer les builds ignorés (quota)",
        "it": "Riprova le build saltate per quota",
        "ja": "クォータで飛ばしたビルドを再試行"},
    "Retry 'unavailable' builds": {
        "de": "„Nicht verfügbare“ Builds erneut versuchen",
        "es": "Reintentar builds «no disponibles»",
        "fr": "Réessayer les builds « indisponibles »",
        "it": "Riprova le build «non disponibili»",
        "ja": "「利用不可」ビルドを再試行"},
    "Fix 0-cheat entries": {
        "de": "Einträge mit 0 Cheats korrigieren",
        "es": "Corregir entradas con 0 cheats",
        "fr": "Corriger les entrées à 0 cheat",
        "it": "Correggi le voci con 0 cheat",
        "ja": "チート0件のエントリを修正"},
    "Recount cheats from disk": {
        "de": "Cheats von der Festplatte neu zählen",
        "es": "Recontar cheats desde el disco",
        "fr": "Recompter les cheats depuis le disque",
        "it": "Riconta i cheat dal disco",
        "ja": "ディスクからチート数を再集計"},
    "Scan for empty cheat files": {
        "de": "Nach leeren Cheat-Dateien suchen",
        "es": "Buscar archivos de cheats vacíos",
        "fr": "Rechercher les fichiers de cheats vides",
        "it": "Cerca file di cheat vuoti",
        "ja": "空のチートファイルを検索"},
    "Fix ID names": {
        "de": "ID-Namen korrigieren", "es": "Corregir nombres de ID",
        "fr": "Corriger les noms d'ID", "it": "Correggi i nomi ID",
        "ja": "ID 名を修正"},
    "Sync titles folder with DB": {
        "de": "titles-Ordner mit DB abgleichen",
        "es": "Sincronizar la carpeta titles con la BD",
        "fr": "Synchroniser le dossier titles avec la BD",
        "it": "Sincronizza la cartella titles con il DB",
        "ja": "titles フォルダを DB と同期"},
    "Clear DB": {"de": "DB leeren", "es": "Vaciar BD", "fr": "Vider la BD",
                 "it": "Svuota DB", "ja": "DB を消去"},
    "Update/DLC IDs": {
        "de": "Update/DLC-IDs", "es": "IDs de update/DLC",
        "fr": "ID update/DLC", "it": "ID update/DLC", "ja": "アップデート/DLC ID"},
    "DB:": {"de": "DB:", "es": "BD:", "fr": "BD :", "it": "DB:", "ja": "DB:"},
})

# ---- Context menu + generic dialog buttons ---------------------------------
_merge({
    "Download via API": {
        "de": "Über API herunterladen", "es": "Descargar por API",
        "fr": "Télécharger via l'API", "it": "Scarica tramite API",
        "ja": "API でダウンロード"},
    "Download via browser (bypass API limit)": {
        "de": "Über Browser herunterladen (API-Limit umgehen)",
        "es": "Descargar por navegador (evitar límite de API)",
        "fr": "Télécharger via le navigateur (contourner la limite API)",
        "it": "Scarica dal browser (aggira il limite API)",
        "ja": "ブラウザでダウンロード（API制限を回避）"},
    "Download this": {
        "de": "Dies herunterladen", "es": "Descargar esto",
        "fr": "Télécharger ceci", "it": "Scarica questo", "ja": "これをダウンロード"},
    "Check Cheat File": {
        "de": "Cheat-Datei prüfen", "es": "Comprobar archivo de cheats",
        "fr": "Vérifier le fichier de cheats", "it": "Controlla file di cheat",
        "ja": "チートファイルを確認"},
    "Download cover (selected)": {
        "de": "Cover herunterladen (Auswahl)",
        "es": "Descargar carátula (selección)",
        "fr": "Télécharger la jaquette (sélection)",
        "it": "Scarica copertina (selezione)",
        "ja": "カバーをダウンロード（選択）"},
    "Download Covers (all)": {
        "de": "Cover herunterladen (alle)", "es": "Descargar carátulas (todas)",
        "fr": "Télécharger les jaquettes (toutes)",
        "it": "Scarica copertine (tutte)", "ja": "カバーをダウンロード（すべて）"},
    "Delete entry": {
        "de": "Eintrag löschen", "es": "Eliminar entrada",
        "fr": "Supprimer l'entrée", "it": "Elimina voce", "ja": "エントリを削除"},
    "Open link(s) in browser": {
        "de": "Link(s) im Browser öffnen", "es": "Abrir enlace(s) en el navegador",
        "fr": "Ouvrir le(s) lien(s) dans le navigateur",
        "it": "Apri link nel browser", "ja": "リンクをブラウザで開く"},
    "Reveal in Explorer": {
        "de": "Im Explorer anzeigen", "es": "Mostrar en el Explorador",
        "fr": "Afficher dans l'Explorateur", "it": "Mostra in Esplora file",
        "ja": "エクスプローラーで表示"},
    "Edit entry": {
        "de": "Eintrag bearbeiten", "es": "Editar entrada",
        "fr": "Modifier l'entrée", "it": "Modifica voce", "ja": "エントリを編集"},
    "Edit IDs": {"de": "IDs bearbeiten", "es": "Editar IDs", "fr": "Modifier les ID",
                 "it": "Modifica ID", "ja": "ID を編集"},
    "Copy": {"de": "Kopieren", "es": "Copiar", "fr": "Copier", "it": "Copia",
             "ja": "コピー"},
    "Cancel": {"de": "Abbrechen", "es": "Cancelar", "fr": "Annuler",
               "it": "Annulla", "ja": "キャンセル"},
    "Save": {"de": "Speichern", "es": "Guardar", "fr": "Enregistrer",
             "it": "Salva", "ja": "保存"},
    "Import": {"de": "Importieren", "es": "Importar", "fr": "Importer",
               "it": "Importa", "ja": "インポート"},
    "Export": {"de": "Exportieren", "es": "Exportar", "fr": "Exporter",
               "it": "Esporta", "ja": "エクスポート"},
    "Close": {"de": "Schließen", "es": "Cerrar", "fr": "Fermer", "it": "Chiudi",
              "ja": "閉じる"},
    "Browse…": {"de": "Durchsuchen…", "es": "Examinar…", "fr": "Parcourir…",
                "it": "Sfoglia…", "ja": "参照…"},
    "Save As…": {"de": "Speichern unter…", "es": "Guardar como…",
                 "fr": "Enregistrer sous…", "it": "Salva con nome…",
                 "ja": "名前を付けて保存…"},
    "Auto-detect": {"de": "Automatisch erkennen", "es": "Detección automática",
                    "fr": "Détection auto", "it": "Rilevamento automatico",
                    "ja": "自動検出"},
    "show": {"de": "zeigen", "es": "mostrar", "fr": "afficher", "it": "mostra",
             "ja": "表示"},
    "hide": {"de": "verbergen", "es": "ocultar", "fr": "masquer", "it": "nascondi",
             "ja": "非表示"},
})

# ---- Dialog: Add / edit entry ----------------------------------------------
_merge({
    "Add entry": {"de": "Eintrag hinzufügen", "es": "Añadir entrada",
                  "fr": "Ajouter une entrée", "it": "Aggiungi voce",
                  "ja": "エントリを追加"},
    "Title ID * (16 hex)": {
        "de": "Title-ID * (16 Hex)", "es": "Title ID * (16 hex)",
        "fr": "Title ID * (16 hex)", "it": "Title ID * (16 hex)",
        "ja": "Title ID *（16桁の16進数）"},
    "Build ID * (16 hex)": {
        "de": "Build-ID * (16 Hex)", "es": "Build ID * (16 hex)",
        "fr": "Build ID * (16 hex)", "it": "Build ID * (16 hex)",
        "ja": "Build ID *（16桁の16進数）"},
    "Game name": {"de": "Spielname", "es": "Nombre del juego",
                  "fr": "Nom du jeu", "it": "Nome del gioco", "ja": "ゲーム名"},
    "Credits": {"de": "Credits", "es": "Créditos", "fr": "Crédits",
                "it": "Crediti", "ja": "クレジット"},
    "Cheat code *\n(Atmosphere format,\n[Name] headers)": {
        "de": "Cheat-Code *\n(Atmosphère-Format,\n[Name]-Überschriften)",
        "es": "Código del cheat *\n(formato Atmosphère,\nencabezados [Nombre])",
        "fr": "Code du cheat *\n(format Atmosphère,\nen-têtes [Nom])",
        "it": "Codice cheat *\n(formato Atmosphère,\nintestazioni [Nome])",
        "ja": "チートコード *\n（Atmosphère 形式、\n[名前] ヘッダー）"},
    "Title ID and Build ID must be exactly 16 hex characters.": {
        "de": "Title-ID und Build-ID müssen genau 16 Hex-Zeichen lang sein.",
        "es": "El Title ID y el Build ID deben tener exactamente 16 caracteres hex.",
        "fr": "Le Title ID et le Build ID doivent faire exactement 16 caractères hex.",
        "it": "Title ID e Build ID devono avere esattamente 16 caratteri esadecimali.",
        "ja": "Title ID と Build ID は正確に16桁の16進数である必要があります。"},
    "Please paste the cheat code.": {
        "de": "Bitte den Cheat-Code einfügen.",
        "es": "Pega el código del cheat.",
        "fr": "Veuillez coller le code du cheat.",
        "it": "Incolla il codice del cheat.",
        "ja": "チートコードを貼り付けてください。"},
})

# ---- Dialog: Export to SD / ZIP (shared modes + labels) --------------------
_merge({
    "Export cheats to Switch SD card": {
        "de": "Cheats auf die Switch-SD-Karte exportieren",
        "es": "Exportar cheats a la tarjeta SD de Switch",
        "fr": "Exporter les cheats vers la carte SD Switch",
        "it": "Esporta i cheat sulla scheda SD della Switch",
        "ja": "チートを Switch の SD カードにエクスポート"},
    "Export cheats to a ZIP file": {
        "de": "Cheats in eine ZIP-Datei exportieren",
        "es": "Exportar cheats a un archivo ZIP",
        "fr": "Exporter les cheats dans un fichier ZIP",
        "it": "Esporta i cheat in un file ZIP",
        "ja": "チートを ZIP ファイルにエクスポート"},
    "Export cheats to ZIP": {
        "de": "Cheats als ZIP exportieren", "es": "Exportar cheats a ZIP",
        "fr": "Exporter les cheats en ZIP", "it": "Esporta i cheat in ZIP",
        "ja": "チートを ZIP にエクスポート"},
    "Switch SD-card root:": {
        "de": "Switch-SD-Karten-Stammverzeichnis:",
        "es": "Raíz de la tarjeta SD de Switch:",
        "fr": "Racine de la carte SD Switch :",
        "it": "Radice della scheda SD della Switch:",
        "ja": "Switch SD カードのルート:"},
    "Select the Switch SD-card root": {
        "de": "Switch-SD-Karten-Stammverzeichnis auswählen",
        "es": "Selecciona la raíz de la tarjeta SD de Switch",
        "fr": "Sélectionner la racine de la carte SD Switch",
        "it": "Seleziona la radice della scheda SD della Switch",
        "ja": "Switch SD カードのルートを選択"},
    "Export for:": {"de": "Exportieren für:", "es": "Exportar para:",
                    "fr": "Exporter pour :", "it": "Esporta per:",
                    "ja": "エクスポート先:"},
    "Layout inside the ZIP (for which tool):": {
        "de": "Struktur innerhalb der ZIP (für welches Tool):",
        "es": "Estructura dentro del ZIP (para qué herramienta):",
        "fr": "Structure dans le ZIP (pour quel outil) :",
        "it": "Struttura dentro lo ZIP (per quale strumento):",
        "ja": "ZIP 内のレイアウト（対象ツール）:"},
    "Save ZIP as:": {"de": "ZIP speichern unter:", "es": "Guardar ZIP como:",
                     "fr": "Enregistrer le ZIP sous :", "it": "Salva ZIP come:",
                     "ja": "ZIP の保存名:"},
    "Scope:": {"de": "Umfang:", "es": "Alcance:", "fr": "Portée :",
               "it": "Ambito:", "ja": "対象範囲:"},
    "All downloaded cheats": {
        "de": "Alle heruntergeladenen Cheats", "es": "Todos los cheats descargados",
        "fr": "Tous les cheats téléchargés", "it": "Tutti i cheat scaricati",
        "ja": "ダウンロード済みのすべてのチート"},
    "Only files with real cheats are copied; empty/stub files are "
    "skipped.\nExisting cheats on the card are merged, not overwritten.": {
        "de": "Nur Dateien mit echten Cheats werden kopiert; leere/Platzhalter-Dateien "
              "werden übersprungen.\nVorhandene Cheats auf der Karte werden zusammengeführt, "
              "nicht überschrieben.",
        "es": "Solo se copian los archivos con cheats reales; los archivos vacíos o de "
              "relleno se omiten.\nLos cheats existentes en la tarjeta se combinan, no se "
              "sobrescriben.",
        "fr": "Seuls les fichiers contenant de vrais cheats sont copiés ; les fichiers "
              "vides/fictifs sont ignorés.\nLes cheats déjà présents sur la carte sont "
              "fusionnés, pas écrasés.",
        "it": "Vengono copiati solo i file con cheat reali; i file vuoti/segnaposto vengono "
              "saltati.\nI cheat già presenti sulla scheda vengono uniti, non sovrascritti.",
        "ja": "実際のチートを含むファイルのみコピーされ、空/スタブのファイルはスキップされます。\n"
              "カードにある既存のチートは上書きされず統合されます。"},
    "Only files with real cheats are included; empty/stub files are "
    "skipped.\nUnzip the archive onto your SD-card root to install "
    "the cheats.": {
        "de": "Nur Dateien mit echten Cheats werden aufgenommen; leere/Platzhalter-Dateien "
              "werden übersprungen.\nEntpacke das Archiv in das Stammverzeichnis der "
              "SD-Karte, um die Cheats zu installieren.",
        "es": "Solo se incluyen los archivos con cheats reales; los vacíos o de relleno se "
              "omiten.\nDescomprime el archivo en la raíz de la tarjeta SD para instalar los "
              "cheats.",
        "fr": "Seuls les fichiers contenant de vrais cheats sont inclus ; les fichiers "
              "vides/fictifs sont ignorés.\nDézippez l'archive à la racine de la carte SD "
              "pour installer les cheats.",
        "it": "Vengono inclusi solo i file con cheat reali; quelli vuoti/segnaposto vengono "
              "saltati.\nEstrai l'archivio nella radice della scheda SD per installare i cheat.",
        "ja": "実際のチートを含むファイルのみが含まれ、空/スタブのファイルはスキップされます。\n"
              "アーカイブを SD カードのルートに展開するとチートがインストールされます。"},
})

# ---- Export SD/ZIP: layout descriptions ------------------------------------
_merge({
    "atmosphere/contents/<TitleID>/cheats/<BuildID>.txt\n"
    "→ auto-loads when you start the game. Works for Atmosphère, EdiZon-SE\n"
    "   and Breeze — this is the recommended option.": {
        "de": "atmosphere/contents/<TitleID>/cheats/<BuildID>.txt\n"
              "→ lädt automatisch beim Spielstart. Funktioniert mit Atmosphère, EdiZon-SE\n"
              "   und Breeze — die empfohlene Option.",
        "es": "atmosphere/contents/<TitleID>/cheats/<BuildID>.txt\n"
              "→ se carga solo al iniciar el juego. Funciona con Atmosphère, EdiZon-SE\n"
              "   y Breeze — la opción recomendada.",
        "fr": "atmosphere/contents/<TitleID>/cheats/<BuildID>.txt\n"
              "→ se charge automatiquement au lancement du jeu. Compatible Atmosphère,\n"
              "   EdiZon-SE et Breeze — l'option recommandée.",
        "it": "atmosphere/contents/<TitleID>/cheats/<BuildID>.txt\n"
              "→ si carica da solo all'avvio del gioco. Funziona con Atmosphère, EdiZon-SE\n"
              "   e Breeze — l'opzione consigliata.",
        "ja": "atmosphere/contents/<TitleID>/cheats/<BuildID>.txt\n"
              "→ ゲーム起動時に自動で読み込まれます。Atmosphère・EdiZon-SE・Breeze で動作\n"
              "   — 推奨オプションです。"},
    "switch/breeze/cheats/<TitleID>/<BuildID>.txt\n"
    "→ inactive until you enable them inside the Breeze app.": {
        "de": "switch/breeze/cheats/<TitleID>/<BuildID>.txt\n"
              "→ inaktiv, bis du sie in der Breeze-App aktivierst.",
        "es": "switch/breeze/cheats/<TitleID>/<BuildID>.txt\n"
              "→ inactivos hasta que los actives dentro de la app Breeze.",
        "fr": "switch/breeze/cheats/<TitleID>/<BuildID>.txt\n"
              "→ inactifs tant que vous ne les activez pas dans l'appli Breeze.",
        "it": "switch/breeze/cheats/<TitleID>/<BuildID>.txt\n"
              "→ inattivi finché non li abiliti nell'app Breeze.",
        "ja": "switch/breeze/cheats/<TitleID>/<BuildID>.txt\n"
              "→ Breeze アプリ内で有効にするまで無効です。"},
    "switch/EdiZon/cheats/<BuildID>.txt\n"
    "→ EdiZon loads the file when the game launches, then moves it to the\n"
    "   Atmosphère folder itself.": {
        "de": "switch/EdiZon/cheats/<BuildID>.txt\n"
              "→ EdiZon lädt die Datei beim Spielstart und verschiebt sie dann selbst\n"
              "   in den Atmosphère-Ordner.",
        "es": "switch/EdiZon/cheats/<BuildID>.txt\n"
              "→ EdiZon carga el archivo al iniciar el juego y luego lo mueve él mismo\n"
              "   a la carpeta de Atmosphère.",
        "fr": "switch/EdiZon/cheats/<BuildID>.txt\n"
              "→ EdiZon charge le fichier au lancement du jeu, puis le déplace lui-même\n"
              "   vers le dossier Atmosphère.",
        "it": "switch/EdiZon/cheats/<BuildID>.txt\n"
              "→ EdiZon carica il file all'avvio del gioco e poi lo sposta da solo\n"
              "   nella cartella di Atmosphère.",
        "ja": "switch/EdiZon/cheats/<BuildID>.txt\n"
              "→ EdiZon がゲーム起動時にファイルを読み込み、その後自動で Atmosphère\n"
              "   フォルダへ移動します。"},
})

# ---- Dialog: Import database -----------------------------------------------
_merge({
    "Import database": {"de": "Datenbank importieren", "es": "Importar base de datos",
                        "fr": "Importer la base de données", "it": "Importa database",
                        "ja": "データベースをインポート"},
    "How should the imported data be applied?": {
        "de": "Wie sollen die importierten Daten angewendet werden?",
        "es": "¿Cómo deben aplicarse los datos importados?",
        "fr": "Comment appliquer les données importées ?",
        "it": "Come applicare i dati importati?",
        "ja": "インポートしたデータをどう適用しますか？"},
    "Merge into the current database (recommended)": {
        "de": "In die aktuelle Datenbank einfügen (empfohlen)",
        "es": "Combinar con la base de datos actual (recomendado)",
        "fr": "Fusionner avec la base de données actuelle (recommandé)",
        "it": "Unisci al database attuale (consigliato)",
        "ja": "現在のデータベースに統合（推奨）"},
    "Add and update builds from the imported database. Nothing is removed;\n"
    "existing entries keep their data and never lose a real cheat count.": {
        "de": "Builds aus der importierten Datenbank hinzufügen und aktualisieren. Nichts "
              "wird entfernt;\nvorhandene Einträge behalten ihre Daten und verlieren nie "
              "eine echte Cheat-Anzahl.",
        "es": "Añade y actualiza builds de la base de datos importada. No se elimina nada;\n"
              "las entradas existentes conservan sus datos y nunca pierden un recuento real "
              "de cheats.",
        "fr": "Ajoute et met à jour les builds de la base importée. Rien n'est supprimé ;\n"
              "les entrées existantes conservent leurs données et ne perdent jamais un vrai "
              "compte de cheats.",
        "it": "Aggiunge e aggiorna le build dal database importato. Nulla viene rimosso;\n"
              "le voci esistenti mantengono i loro dati e non perdono mai un conteggio reale "
              "dei cheat.",
        "ja": "インポートしたデータベースからビルドを追加・更新します。何も削除されません。\n"
              "既存のエントリはデータを保持し、実際のチート数を失うことはありません。"},
    "Replace the current database entirely": {
        "de": "Die aktuelle Datenbank vollständig ersetzen",
        "es": "Reemplazar por completo la base de datos actual",
        "fr": "Remplacer entièrement la base de données actuelle",
        "it": "Sostituisci completamente il database attuale",
        "ja": "現在のデータベースを完全に置き換える"},
    "Overwrite the current database with the imported one. A backup of the\n"
    "current database is saved first.": {
        "de": "Überschreibt die aktuelle Datenbank mit der importierten. Zuvor wird ein\n"
              "Backup der aktuellen Datenbank gespeichert.",
        "es": "Sobrescribe la base de datos actual con la importada. Antes se guarda una\n"
              "copia de seguridad de la base de datos actual.",
        "fr": "Écrase la base de données actuelle par celle importée. Une sauvegarde de la\n"
              "base actuelle est enregistrée au préalable.",
        "it": "Sovrascrive il database attuale con quello importato. Prima viene salvato un\n"
              "backup del database attuale.",
        "ja": "現在のデータベースをインポートしたもので上書きします。先に現在のデータベースの\n"
              "バックアップが保存されます。"},
})

# ---- Dialog: Updates / update progress -------------------------------------
_merge({
    "Updates available": {"de": "Updates verfügbar", "es": "Actualizaciones disponibles",
                          "fr": "Mises à jour disponibles", "it": "Aggiornamenti disponibili",
                          "ja": "アップデートがあります"},
    "You are up to date": {
        "de": "Du bist auf dem neuesten Stand", "es": "Estás al día",
        "fr": "Vous êtes à jour", "it": "Sei aggiornato", "ja": "最新の状態です"},
    "What's new:": {"de": "Was ist neu:", "es": "Novedades:", "fr": "Nouveautés :",
                    "it": "Novità:", "ja": "変更点:"},
    "The current release was re-uploaded (a fix without a "
    "version bump).": {
        "de": "Das aktuelle Release wurde erneut hochgeladen (ein Fix ohne "
              "Versionssprung).",
        "es": "La versión actual se volvió a subir (una corrección sin cambio de "
              "versión).",
        "fr": "La version actuelle a été re-téléversée (un correctif sans changement "
              "de version).",
        "it": "La release attuale è stata ricaricata (una correzione senza cambio di "
              "versione).",
        "ja": "現在のリリースが再アップロードされました（バージョンを上げない修正）。"},
    "Downloaded and merged into your database "
    "(nothing is removed).": {
        "de": "Wird heruntergeladen und in deine Datenbank eingefügt "
              "(nichts wird entfernt).",
        "es": "Se descarga y se combina con tu base de datos "
              "(no se elimina nada).",
        "fr": "Téléchargé et fusionné dans votre base de données "
              "(rien n'est supprimé).",
        "it": "Scaricato e unito al tuo database "
              "(nulla viene rimosso).",
        "ja": "ダウンロードしてデータベースに統合されます（何も削除されません）。"},
    "Download data update": {
        "de": "Daten-Update herunterladen", "es": "Descargar actualización de datos",
        "fr": "Télécharger la mise à jour des données",
        "it": "Scarica l'aggiornamento dei dati", "ja": "データ更新をダウンロード"},
    "Program, cheats and database are all current.": {
        "de": "Programm, Cheats und Datenbank sind alle aktuell.",
        "es": "El programa, los cheats y la base de datos están al día.",
        "fr": "Le programme, les cheats et la base de données sont à jour.",
        "it": "Programma, cheat e database sono tutti aggiornati.",
        "ja": "プログラム・チート・データベースはすべて最新です。"},
    "Update & Restart": {
        "de": "Aktualisieren & neu starten", "es": "Actualizar y reiniciar",
        "fr": "Mettre à jour et redémarrer", "it": "Aggiorna e riavvia",
        "ja": "更新して再起動"},
    "Open download page": {
        "de": "Download-Seite öffnen", "es": "Abrir página de descarga",
        "fr": "Ouvrir la page de téléchargement", "it": "Apri la pagina di download",
        "ja": "ダウンロードページを開く"},
    "Open GitHub release": {
        "de": "GitHub-Release öffnen", "es": "Abrir la publicación de GitHub",
        "fr": "Ouvrir la release GitHub", "it": "Apri la release su GitHub",
        "ja": "GitHub リリースを開く"},
    "Preparing update…": {
        "de": "Update wird vorbereitet…", "es": "Preparando la actualización…",
        "fr": "Préparation de la mise à jour…", "it": "Preparazione dell'aggiornamento…",
        "ja": "アップデートを準備中…"},
})

# ---- Messagebox titles -----------------------------------------------------
_merge({
    "Download": {"de": "Download", "es": "Descargar", "fr": "Télécharger",
                 "it": "Scarica", "ja": "ダウンロード"},
    "Download via API": {  # title reuse handled above
        "de": "Über API herunterladen", "es": "Descargar por API",
        "fr": "Télécharger via l'API", "it": "Scarica tramite API",
        "ja": "API でダウンロード"},
    "Download covers": {"de": "Cover herunterladen", "es": "Descargar carátulas",
                        "fr": "Télécharger les jaquettes", "it": "Scarica copertine",
                        "ja": "カバーをダウンロード"},
    "Download game info": {
        "de": "Spiel-Infos herunterladen", "es": "Descargar información del juego",
        "fr": "Télécharger les infos du jeu", "it": "Scarica info del gioco",
        "ja": "ゲーム情報をダウンロード"},
    "Download via browser": {
        "de": "Über Browser herunterladen", "es": "Descargar por navegador",
        "fr": "Télécharger via le navigateur", "it": "Scarica dal browser",
        "ja": "ブラウザでダウンロード"},
    "Check cheat file": {
        "de": "Cheat-Datei prüfen", "es": "Comprobar archivo de cheats",
        "fr": "Vérifier le fichier de cheats", "it": "Controlla file di cheat",
        "ja": "チートファイルを確認"},
    "Update": {"de": "Update", "es": "Actualización", "fr": "Mise à jour",
               "it": "Aggiornamento", "ja": "アップデート"},
    "Open Link": {"de": "Link öffnen", "es": "Abrir enlace", "fr": "Ouvrir le lien",
                  "it": "Apri link", "ja": "リンクを開く"},
    "Open in Explorer": {
        "de": "Im Explorer öffnen", "es": "Abrir en el Explorador",
        "fr": "Ouvrir dans l'Explorateur", "it": "Apri in Esplora file",
        "ja": "エクスプローラーで開く"},
    "Open folder": {"de": "Ordner öffnen", "es": "Abrir carpeta",
                    "fr": "Ouvrir le dossier", "it": "Apri cartella",
                    "ja": "フォルダを開く"},
    "Delete entries": {"de": "Einträge löschen", "es": "Eliminar entradas",
                       "fr": "Supprimer les entrées", "it": "Elimina voci",
                       "ja": "エントリを削除"},
    "Browser": {"de": "Browser", "es": "Navegador", "fr": "Navigateur",
                "it": "Browser", "ja": "ブラウザ"},
    "Download Firefox": {
        "de": "Firefox herunterladen", "es": "Descargar Firefox",
        "fr": "Télécharger Firefox", "it": "Scarica Firefox",
        "ja": "Firefox をダウンロード"},
    "Chrome not found": {
        "de": "Chrome nicht gefunden", "es": "Chrome no encontrado",
        "fr": "Chrome introuvable", "it": "Chrome non trovato",
        "ja": "Chrome が見つかりません"},
    "Export database": {"de": "Datenbank exportieren", "es": "Exportar base de datos",
                        "fr": "Exporter la base de données", "it": "Esporta database",
                        "ja": "データベースをエクスポート"},
    "Export database to CSV": {
        "de": "Datenbank als CSV exportieren", "es": "Exportar base de datos a CSV",
        "fr": "Exporter la base de données en CSV", "it": "Esporta database in CSV",
        "ja": "データベースを CSV にエクスポート"},
    "Export full database": {
        "de": "Vollständige Datenbank exportieren", "es": "Exportar base de datos completa",
        "fr": "Exporter la base de données complète", "it": "Esporta l'intero database",
        "ja": "データベース全体をエクスポート"},
    "Import database (.db)": {
        "de": "Datenbank importieren (.db)", "es": "Importar base de datos (.db)",
        "fr": "Importer une base de données (.db)", "it": "Importa database (.db)",
        "ja": "データベースをインポート（.db）"},
    "Import cheat ZIP": {
        "de": "Cheat-ZIP importieren", "es": "Importar ZIP de cheats",
        "fr": "Importer un ZIP de cheats", "it": "Importa ZIP di cheat",
        "ja": "チート ZIP をインポート"},
    "Import disk": {"de": "Von Datenträger importieren", "es": "Importar del disco",
                    "fr": "Importer depuis le disque", "it": "Importa da disco",
                    "ja": "ディスクからインポート"},
    "Replace database": {"de": "Datenbank ersetzen", "es": "Reemplazar base de datos",
                         "fr": "Remplacer la base de données", "it": "Sostituisci database",
                         "ja": "データベースを置き換え"},
    "Select cheats database": {
        "de": "Cheat-Datenbank auswählen", "es": "Seleccionar base de datos de cheats",
        "fr": "Sélectionner la base de données de cheats",
        "it": "Seleziona il database dei cheat", "ja": "チートデータベースを選択"},
    "Select output folder": {
        "de": "Ausgabeordner auswählen", "es": "Seleccionar carpeta de salida",
        "fr": "Sélectionner le dossier de sortie", "it": "Seleziona la cartella di output",
        "ja": "出力フォルダを選択"},
    "Edit Title ID": {"de": "Title-ID bearbeiten", "es": "Editar Title ID",
                      "fr": "Modifier le Title ID", "it": "Modifica Title ID",
                      "ja": "Title ID を編集"},
    "Edit Build ID": {"de": "Build-ID bearbeiten", "es": "Editar Build ID",
                      "fr": "Modifier le Build ID", "it": "Modifica Build ID",
                      "ja": "Build ID を編集"},
    "Title ID (16 hex):": {
        "de": "Title-ID (16 Hex):", "es": "Title ID (16 hex):",
        "fr": "Title ID (16 hex) :", "it": "Title ID (16 hex):",
        "ja": "Title ID（16桁の16進数）:"},
    "Build ID (16 hex):": {
        "de": "Build-ID (16 Hex):", "es": "Build ID (16 hex):",
        "fr": "Build ID (16 hex) :", "it": "Build ID (16 hex):",
        "ja": "Build ID（16桁の16進数）:"},
    "Quit": {"de": "Beenden", "es": "Salir", "fr": "Quitter", "it": "Esci",
             "ja": "終了"},
    "Error": {"de": "Fehler", "es": "Error", "fr": "Erreur", "it": "Errore",
              "ja": "エラー"},
    "Fix 0-cheat": {"de": "0-Cheat korrigieren", "es": "Corregir 0 cheats",
                    "fr": "Corriger 0 cheat", "it": "Correggi 0 cheat",
                    "ja": "チート0件を修正"},
    "Scrape & Download Everything": {
        "de": "Alles scrapen & herunterladen", "es": "Extraer y descargar todo",
        "fr": "Tout extraire et télécharger", "it": "Estrai e scarica tutto",
        "ja": "すべて取得してダウンロード"},
    "Clear database & downloaded files": {
        "de": "Datenbank & heruntergeladene Dateien löschen",
        "es": "Vaciar base de datos y archivos descargados",
        "fr": "Vider la base et les fichiers téléchargés",
        "it": "Svuota database e file scaricati",
        "ja": "データベースとダウンロード済みファイルを消去"},
})

# ---- Short messagebox messages ---------------------------------------------
_merge({
    "No valid title id selected.": {
        "de": "Keine gültige Title-ID ausgewählt.",
        "es": "No hay ningún Title ID válido seleccionado.",
        "fr": "Aucun Title ID valide sélectionné.",
        "it": "Nessun Title ID valido selezionato.",
        "ja": "有効な Title ID が選択されていません。"},
    "No valid title id in the selection.": {
        "de": "Keine gültige Title-ID in der Auswahl.",
        "es": "No hay ningún Title ID válido en la selección.",
        "fr": "Aucun Title ID valide dans la sélection.",
        "it": "Nessun Title ID valido nella selezione.",
        "ja": "選択項目に有効な Title ID がありません。"},
    "No row selected.": {
        "de": "Keine Zeile ausgewählt.", "es": "No hay ninguna fila seleccionada.",
        "fr": "Aucune ligne sélectionnée.", "it": "Nessuna riga selezionata.",
        "ja": "行が選択されていません。"},
    "Select one or more rows in the table first.": {
        "de": "Wähle zuerst eine oder mehrere Zeilen in der Tabelle aus.",
        "es": "Selecciona primero una o varias filas de la tabla.",
        "fr": "Sélectionnez d'abord une ou plusieurs lignes du tableau.",
        "it": "Seleziona prima una o più righe nella tabella.",
        "ja": "先にテーブルで1つ以上の行を選択してください。"},
    "Database is empty — run Scrape first.": {
        "de": "Die Datenbank ist leer — führe zuerst „Scrapen“ aus.",
        "es": "La base de datos está vacía: ejecuta «Extraer» primero.",
        "fr": "La base de données est vide — lancez d'abord « Extraire ».",
        "it": "Il database è vuoto — esegui prima «Estrai».",
        "ja": "データベースが空です。先に「取得」を実行してください。"},
    "Database is empty - run Scrape first.": {
        "de": "Die Datenbank ist leer — führe zuerst „Scrapen“ aus.",
        "es": "La base de datos está vacía: ejecuta «Extraer» primero.",
        "fr": "La base de données est vide — lancez d'abord « Extraire ».",
        "it": "Il database è vuoto — esegui prima «Estrai».",
        "ja": "データベースが空です。先に「取得」を実行してください。"},
    "No database yet. Scrape first.": {
        "de": "Noch keine Datenbank. Zuerst scrapen.",
        "es": "Aún no hay base de datos. Extrae primero.",
        "fr": "Pas encore de base de données. Extrayez d'abord.",
        "it": "Nessun database ancora. Estrai prima.",
        "ja": "まだデータベースがありません。先に取得してください。"},
    "No database file yet. Scrape first.": {
        "de": "Noch keine Datenbankdatei. Zuerst scrapen.",
        "es": "Aún no hay archivo de base de datos. Extrae primero.",
        "fr": "Pas encore de fichier de base de données. Extrayez d'abord.",
        "it": "Nessun file di database ancora. Estrai prima.",
        "ja": "まだデータベースファイルがありません。先に取得してください。"},
    "Please choose a valid SD-card root folder.": {
        "de": "Bitte einen gültigen SD-Karten-Stammordner wählen.",
        "es": "Elige una carpeta raíz de tarjeta SD válida.",
        "fr": "Veuillez choisir un dossier racine de carte SD valide.",
        "it": "Scegli una cartella radice della scheda SD valida.",
        "ja": "有効な SD カードのルートフォルダを選択してください。"},
    "Please choose where to save the ZIP file.": {
        "de": "Bitte wählen, wo die ZIP-Datei gespeichert werden soll.",
        "es": "Elige dónde guardar el archivo ZIP.",
        "fr": "Veuillez choisir où enregistrer le fichier ZIP.",
        "it": "Scegli dove salvare il file ZIP.",
        "ja": "ZIP ファイルの保存先を選択してください。"},
    "Select exactly one entry to edit its IDs.": {
        "de": "Genau einen Eintrag zum Bearbeiten der IDs auswählen.",
        "es": "Selecciona exactamente una entrada para editar sus IDs.",
        "fr": "Sélectionnez exactement une entrée pour modifier ses ID.",
        "it": "Seleziona esattamente una voce per modificarne gli ID.",
        "ja": "ID を編集するエントリを1つだけ選択してください。"},
    "Select exactly one entry to edit.": {
        "de": "Genau einen Eintrag zum Bearbeiten auswählen.",
        "es": "Selecciona exactamente una entrada para editar.",
        "fr": "Sélectionnez exactement une entrée à modifier.",
        "it": "Seleziona esattamente una voce da modificare.",
        "ja": "編集するエントリを1つだけ選択してください。"},
    "Both IDs must be exactly 16 hex characters.": {
        "de": "Beide IDs müssen genau 16 Hex-Zeichen lang sein.",
        "es": "Ambos IDs deben tener exactamente 16 caracteres hex.",
        "fr": "Les deux ID doivent faire exactement 16 caractères hex.",
        "it": "Entrambi gli ID devono avere esattamente 16 caratteri esadecimali.",
        "ja": "両方の ID は正確に16桁の16進数である必要があります。"},
    "An entry with those IDs already exists.": {
        "de": "Ein Eintrag mit diesen IDs existiert bereits.",
        "es": "Ya existe una entrada con esos IDs.",
        "fr": "Une entrée avec ces ID existe déjà.",
        "it": "Esiste già una voce con quegli ID.",
        "ja": "その ID のエントリは既に存在します。"},
    "No builds are currently marked as unavailable.": {
        "de": "Derzeit sind keine Builds als nicht verfügbar markiert.",
        "es": "Actualmente no hay builds marcados como no disponibles.",
        "fr": "Aucun build n'est actuellement marqué comme indisponible.",
        "it": "Al momento nessuna build è contrassegnata come non disponibile.",
        "ja": "現在「利用不可」とされているビルドはありません。"},
    "No builds listed in the file.": {
        "de": "Keine Builds in der Datei aufgeführt.",
        "es": "No hay builds en el archivo.",
        "fr": "Aucun build listé dans le fichier.",
        "it": "Nessuna build elencata nel file.",
        "ja": "ファイルにビルドが記載されていません。"},
    "No empty cheat files found.": {
        "de": "Keine leeren Cheat-Dateien gefunden.",
        "es": "No se encontraron archivos de cheats vacíos.",
        "fr": "Aucun fichier de cheats vide trouvé.",
        "it": "Nessun file di cheat vuoto trovato.",
        "ja": "空のチートファイルは見つかりませんでした。"},
    "No entries with 0 cheats found.": {
        "de": "Keine Einträge mit 0 Cheats gefunden.",
        "es": "No se encontraron entradas con 0 cheats.",
        "fr": "Aucune entrée à 0 cheat trouvée.",
        "it": "Nessuna voce con 0 cheat trovata.",
        "ja": "チート0件のエントリは見つかりませんでした。"},
    "That file is already the current database.": {
        "de": "Diese Datei ist bereits die aktuelle Datenbank.",
        "es": "Ese archivo ya es la base de datos actual.",
        "fr": "Ce fichier est déjà la base de données actuelle.",
        "it": "Quel file è già il database attuale.",
        "ja": "そのファイルは既に現在のデータベースです。"},
    "This file has no 'builds' table — it is not a "
    "Switch Cheats database.": {
        "de": "Diese Datei hat keine „builds“-Tabelle — es ist keine "
              "Switch-Cheats-Datenbank.",
        "es": "Este archivo no tiene una tabla «builds»: no es una base de datos "
              "de Switch Cheats.",
        "fr": "Ce fichier n'a pas de table « builds » — ce n'est pas une base de "
              "données Switch Cheats.",
        "it": "Questo file non ha una tabella «builds» — non è un database di "
              "Switch Cheats.",
        "ja": "このファイルには「builds」テーブルがありません — Switch Cheats の"
              "データベースではありません。"},
    "Choose a different file than the live database.": {
        "de": "Wähle eine andere Datei als die aktive Datenbank.",
        "es": "Elige un archivo distinto de la base de datos activa.",
        "fr": "Choisissez un fichier différent de la base de données active.",
        "it": "Scegli un file diverso dal database attivo.",
        "ja": "使用中のデータベースとは別のファイルを選択してください。"},
    "Please wait for the current task to finish, then try again.": {
        "de": "Bitte warte, bis die aktuelle Aufgabe fertig ist, und versuche es "
              "dann erneut.",
        "es": "Espera a que termine la tarea actual y vuelve a intentarlo.",
        "fr": "Veuillez attendre la fin de la tâche en cours, puis réessayez.",
        "it": "Attendi il completamento dell'attività in corso e riprova.",
        "ja": "現在の処理が完了するのを待ってから、もう一度お試しください。"},
    "Please wait for the current task to finish before switching the browser.": {
        "de": "Bitte warte, bis die aktuelle Aufgabe fertig ist, bevor du den "
              "Browser wechselst.",
        "es": "Espera a que termine la tarea actual antes de cambiar de navegador.",
        "fr": "Veuillez attendre la fin de la tâche en cours avant de changer de "
              "navigateur.",
        "it": "Attendi il completamento dell'attività in corso prima di cambiare "
              "browser.",
        "ja": "ブラウザを切り替える前に、現在の処理が完了するのを待ってください。"},
    "Google Chrome wasn't found on your system.\n\nInstall Chrome, or use "
    "Firefox or the built-in Chromium instead.": {
        "de": "Google Chrome wurde auf deinem System nicht gefunden.\n\nInstalliere "
              "Chrome oder verwende stattdessen Firefox oder das eingebaute Chromium.",
        "es": "No se encontró Google Chrome en tu sistema.\n\nInstala Chrome o usa "
              "Firefox o el Chromium integrado en su lugar.",
        "fr": "Google Chrome est introuvable sur votre système.\n\nInstallez Chrome, "
              "ou utilisez plutôt Firefox ou le Chromium intégré.",
        "it": "Google Chrome non è stato trovato sul tuo sistema.\n\nInstalla Chrome "
              "oppure usa Firefox o il Chromium integrato.",
        "ja": "システムに Google Chrome が見つかりませんでした。\n\nChrome を"
              "インストールするか、Firefox または内蔵の Chromium をご利用ください。"},
    "Download the Firefox browser component for the app? (~85 MB)\n\n"
    "It is stored in the app's own data folder.\n\n"
    "Choose No to keep the built-in Chromium.": {
        "de": "Die Firefox-Browser-Komponente für die App herunterladen? (~85 MB)\n\n"
              "Sie wird im eigenen Datenordner der App gespeichert.\n\n"
              "Wähle Nein, um beim eingebauten Chromium zu bleiben.",
        "es": "¿Descargar el componente del navegador Firefox para la app? (~85 MB)\n\n"
              "Se guarda en la propia carpeta de datos de la app.\n\n"
              "Elige No para mantener el Chromium integrado.",
        "fr": "Télécharger le composant navigateur Firefox pour l'appli ? (~85 Mo)\n\n"
              "Il est stocké dans le dossier de données de l'appli.\n\n"
              "Choisissez Non pour conserver le Chromium intégré.",
        "it": "Scaricare il componente del browser Firefox per l'app? (~85 MB)\n\n"
              "Viene salvato nella cartella dati dell'app.\n\n"
              "Scegli No per mantenere il Chromium integrato.",
        "ja": "アプリ用の Firefox ブラウザコンポーネントをダウンロードしますか？（約85MB）\n\n"
              "アプリ専用のデータフォルダに保存されます。\n\n"
              "「いいえ」を選ぶと内蔵の Chromium を使い続けます。"},
})

# ---- Longer confirmation / info bodies -------------------------------------
_merge({
    "Download cheats from DevCatSKZ": {
        "de": "Cheats von DevCatSKZ herunterladen",
        "es": "Descargar cheats de DevCatSKZ",
        "fr": "Télécharger les cheats depuis DevCatSKZ",
        "it": "Scarica i cheat da DevCatSKZ",
        "ja": "DevCatSKZ からチートをダウンロード"},
    "Download the maintainer's ready-made cheats archive and import it?\n\n"
    "You get every cheat file without scraping cheatslips yourself. Your "
    "existing cheats are kept (merged).": {
        "de": "Das fertige Cheats-Archiv des Betreuers herunterladen und importieren?\n\n"
              "Du erhältst jede Cheat-Datei, ohne cheatslips selbst zu scrapen. Deine "
              "vorhandenen Cheats bleiben erhalten (zusammengeführt).",
        "es": "¿Descargar el archivo de cheats ya preparado del responsable e importarlo?\n\n"
              "Obtienes todos los archivos de cheats sin extraer cheatslips tú mismo. Tus "
              "cheats existentes se conservan (se combinan).",
        "fr": "Télécharger l'archive de cheats prête du mainteneur et l'importer ?\n\n"
              "Vous obtenez tous les fichiers de cheats sans extraire cheatslips vous-même. "
              "Vos cheats existants sont conservés (fusionnés).",
        "it": "Scaricare l'archivio di cheat già pronto del manutentore e importarlo?\n\n"
              "Ottieni ogni file di cheat senza estrarre cheatslips da solo. I tuoi cheat "
              "esistenti vengono mantenuti (uniti).",
        "ja": "メンテナが用意した既製のチートアーカイブをダウンロードしてインポートしますか？\n\n"
              "cheatslips を自分で取得しなくても、すべてのチートファイルが手に入ります。"
              "既存のチートは保持されます（統合）。"},
    "Download DevCatSKZ database": {
        "de": "DevCatSKZ-Datenbank herunterladen",
        "es": "Descargar base de datos de DevCatSKZ",
        "fr": "Télécharger la base de données DevCatSKZ",
        "it": "Scarica il database di DevCatSKZ",
        "ja": "DevCatSKZ のデータベースをダウンロード"},
    "Download the maintainer's complete database and merge it into yours?\n\n"
    "You get all names, regions, versions, descriptions and cover URLs. "
    "Nothing is removed; your own entries are kept and enriched.": {
        "de": "Die vollständige Datenbank des Betreuers herunterladen und in deine "
              "einfügen?\n\nDu erhältst alle Namen, Regionen, Versionen, Beschreibungen und "
              "Cover-URLs. Nichts wird entfernt; deine eigenen Einträge bleiben erhalten und "
              "werden ergänzt.",
        "es": "¿Descargar la base de datos completa del responsable y combinarla con la "
              "tuya?\n\nObtienes todos los nombres, regiones, versiones, descripciones y URLs "
              "de carátulas. No se elimina nada; tus propias entradas se conservan y se "
              "enriquecen.",
        "fr": "Télécharger la base de données complète du mainteneur et la fusionner avec "
              "la vôtre ?\n\nVous obtenez tous les noms, régions, versions, descriptions et "
              "URLs de jaquettes. Rien n'est supprimé ; vos propres entrées sont conservées "
              "et enrichies.",
        "it": "Scaricare il database completo del manutentore e unirlo al tuo?\n\nOttieni "
              "tutti i nomi, le regioni, le versioni, le descrizioni e gli URL delle "
              "copertine. Nulla viene rimosso; le tue voci vengono mantenute e arricchite.",
        "ja": "メンテナの完全なデータベースをダウンロードして自分のものに統合しますか？\n\n"
              "すべての名前・リージョン・バージョン・説明・カバー URL が手に入ります。"
              "何も削除されず、あなた自身のエントリは保持され充実します。"},
    "Download complete from DevCatSKZ": {
        "de": "Komplett von DevCatSKZ herunterladen",
        "es": "Descargar todo de DevCatSKZ",
        "fr": "Tout télécharger depuis DevCatSKZ",
        "it": "Scarica tutto da DevCatSKZ",
        "ja": "DevCatSKZ からすべてダウンロード"},
    "Download the maintainer's complete database AND cheats archive?\n\n"
    "This is the fastest way to get everything — the full GUI database plus "
    "every cheat file. Nothing is removed.": {
        "de": "Die vollständige Datenbank UND das Cheats-Archiv des Betreuers "
              "herunterladen?\n\nDer schnellste Weg, alles zu bekommen — die komplette "
              "GUI-Datenbank plus jede Cheat-Datei. Nichts wird entfernt.",
        "es": "¿Descargar la base de datos completa Y el archivo de cheats del "
              "responsable?\n\nEs la forma más rápida de obtener todo: la base de datos "
              "completa de la GUI más todos los archivos de cheats. No se elimina nada.",
        "fr": "Télécharger la base de données complète ET l'archive de cheats du "
              "mainteneur ?\n\nC'est le moyen le plus rapide de tout obtenir — la base "
              "complète de l'interface plus tous les fichiers de cheats. Rien n'est supprimé.",
        "it": "Scaricare il database completo E l'archivio di cheat del manutentore?\n\n"
              "È il modo più veloce per ottenere tutto — l'intero database della GUI più "
              "ogni file di cheat. Nulla viene rimosso.",
        "ja": "メンテナの完全なデータベースとチートアーカイブの両方をダウンロードしますか？\n\n"
              "すべてを手に入れる最速の方法です — GUI の完全なデータベースとすべての"
              "チートファイル。何も削除されません。"},
    "Playwright is not installed.\n\nInstall it in a terminal:\n"
    "    pip install playwright\n    playwright install": {
        "de": "Playwright ist nicht installiert.\n\nInstalliere es in einem Terminal:\n"
              "    pip install playwright\n    playwright install",
        "es": "Playwright no está instalado.\n\nInstálalo en una terminal:\n"
              "    pip install playwright\n    playwright install",
        "fr": "Playwright n'est pas installé.\n\nInstallez-le dans un terminal :\n"
              "    pip install playwright\n    playwright install",
        "it": "Playwright non è installato.\n\nInstallalo in un terminale:\n"
              "    pip install playwright\n    playwright install",
        "ja": "Playwright がインストールされていません。\n\nターミナルでインストールしてください:\n"
              "    pip install playwright\n    playwright install"},
    "Playwright is not installed. Install it with:\n\n"
    "    pip install playwright\n    playwright install": {
        "de": "Playwright ist nicht installiert. Installiere es mit:\n\n"
              "    pip install playwright\n    playwright install",
        "es": "Playwright no está instalado. Instálalo con:\n\n"
              "    pip install playwright\n    playwright install",
        "fr": "Playwright n'est pas installé. Installez-le avec :\n\n"
              "    pip install playwright\n    playwright install",
        "it": "Playwright non è installato. Installalo con:\n\n"
              "    pip install playwright\n    playwright install",
        "ja": "Playwright がインストールされていません。次でインストールしてください:\n\n"
              "    pip install playwright\n    playwright install"},
    "Open a browser, log in (if not already cached), and click the "
    "'Reset my quota' button on cheatslips.com?\n\n"
    "Make sure your email/password are filled in.": {
        "de": "Einen Browser öffnen, anmelden (falls nicht zwischengespeichert) und auf "
              "cheatslips.com auf „Reset my quota“ klicken?\n\nStelle sicher, dass "
              "E-Mail/Passwort ausgefüllt sind.",
        "es": "¿Abrir un navegador, iniciar sesión (si no está en caché) y pulsar el botón "
              "«Reset my quota» en cheatslips.com?\n\nAsegúrate de haber rellenado el "
              "correo y la contraseña.",
        "fr": "Ouvrir un navigateur, se connecter (si non mis en cache) et cliquer sur le "
              "bouton « Reset my quota » sur cheatslips.com ?\n\nAssurez-vous que votre "
              "e-mail/mot de passe sont renseignés.",
        "it": "Aprire un browser, accedere (se non già in cache) e fare clic sul pulsante "
              "«Reset my quota» su cheatslips.com?\n\nAssicurati di aver inserito "
              "e-mail e password.",
        "ja": "ブラウザを開いてログインし（キャッシュされていない場合）、cheatslips.com の"
              "「Reset my quota」ボタンをクリックしますか？\n\nメールとパスワードが入力"
              "されていることを確認してください。"},
    "No email/password entered — the login form will open empty and "
    "you type the credentials in the browser yourself.\n\n"
    "Tip: enter email + password in the GUI first, then only the "
    "reCAPTCHA is left to solve.\n\nOpen the browser anyway?": {
        "de": "Keine E-Mail/kein Passwort eingegeben — das Anmeldeformular öffnet sich "
              "leer und du gibst die Zugangsdaten selbst im Browser ein.\n\nTipp: Gib "
              "E-Mail + Passwort zuerst in der GUI ein, dann bleibt nur noch das "
              "reCAPTCHA zu lösen.\n\nTrotzdem den Browser öffnen?",
        "es": "No se introdujo correo/contraseña: el formulario de acceso se abrirá vacío "
              "y escribirás las credenciales en el navegador.\n\nConsejo: introduce el "
              "correo y la contraseña en la GUI primero; así solo quedará resolver el "
              "reCAPTCHA.\n\n¿Abrir el navegador de todos modos?",
        "fr": "Aucun e-mail/mot de passe saisi — le formulaire de connexion s'ouvrira vide "
              "et vous saisirez les identifiants dans le navigateur.\n\nAstuce : saisissez "
              "d'abord l'e-mail et le mot de passe dans l'interface ; il ne restera plus "
              "qu'à résoudre le reCAPTCHA.\n\nOuvrir le navigateur quand même ?",
        "it": "Nessuna e-mail/password inserita — il modulo di accesso si aprirà vuoto e "
              "digiterai tu le credenziali nel browser.\n\nSuggerimento: inserisci prima "
              "e-mail e password nella GUI, così resterà solo da risolvere il "
              "reCAPTCHA.\n\nAprire comunque il browser?",
        "ja": "メール/パスワードが未入力です — ログインフォームは空で開き、ブラウザで"
              "自分で認証情報を入力します。\n\nヒント: 先に GUI でメールとパスワードを"
              "入力しておくと、あとは reCAPTCHA を解くだけになります。\n\nそれでも"
              "ブラウザを開きますか？"},
    "No rows selected — download ALL still-missing builds directly via "
    "the browser?\n\nThis opens a browser (log in once / solve the "
    "reCAPTCHA), resets the quota automatically and can take a very long "
    "time for many builds. Stop anytime.": {
        "de": "Keine Zeilen ausgewählt — ALLE noch fehlenden Builds direkt über den "
              "Browser herunterladen?\n\nDabei öffnet sich ein Browser (einmal anmelden / "
              "reCAPTCHA lösen), das Kontingent wird automatisch zurückgesetzt, und es kann "
              "bei vielen Builds sehr lange dauern. Jederzeit stoppbar.",
        "es": "No hay filas seleccionadas: ¿descargar TODOS los builds que aún faltan "
              "directamente por el navegador?\n\nSe abre un navegador (inicia sesión una vez "
              "/ resuelve el reCAPTCHA), restablece la cuota automáticamente y puede tardar "
              "mucho con muchos builds. Puedes detenerlo cuando quieras.",
        "fr": "Aucune ligne sélectionnée — télécharger TOUS les builds encore manquants "
              "directement via le navigateur ?\n\nUn navigateur s'ouvre (connexion unique / "
              "reCAPTCHA à résoudre), le quota est réinitialisé automatiquement et cela peut "
              "être très long pour de nombreux builds. Arrêtez à tout moment.",
        "it": "Nessuna riga selezionata — scaricare TUTTE le build ancora mancanti "
              "direttamente dal browser?\n\nSi apre un browser (accedi una volta / risolvi "
              "il reCAPTCHA), la quota viene reimpostata automaticamente e può richiedere "
              "molto tempo con molte build. Puoi fermarti in qualsiasi momento.",
        "ja": "行が選択されていません — まだ不足しているすべてのビルドをブラウザで直接"
              "ダウンロードしますか？\n\nブラウザが開き（1回ログイン / reCAPTCHA を解く）、"
              "クォータは自動でリセットされます。ビルドが多いと非常に時間がかかることが"
              "あります。いつでも停止できます。"},
    "You are running from source. Pull the latest code from GitHub "
    "(git pull) — the release page has been opened in your browser.": {
        "de": "Du führst das Programm aus dem Quellcode aus. Hole den neuesten Code von "
              "GitHub (git pull) — die Release-Seite wurde in deinem Browser geöffnet.",
        "es": "Estás ejecutando desde el código fuente. Descarga el código más reciente de "
              "GitHub (git pull); la página de la versión se abrió en tu navegador.",
        "fr": "Vous exécutez depuis les sources. Récupérez le dernier code depuis GitHub "
              "(git pull) — la page de la release a été ouverte dans votre navigateur.",
        "it": "Stai eseguendo dai sorgenti. Scarica il codice più recente da GitHub "
              "(git pull) — la pagina della release è stata aperta nel tuo browser.",
        "ja": "ソースから実行しています。GitHub から最新コードを取得してください"
              "（git pull）— リリースページをブラウザで開きました。"},
    "Couldn't update automatically (no matching download, or the app "
    "folder is read-only). The release page has been opened so you can "
    "update manually.": {
        "de": "Automatisches Update nicht möglich (kein passender Download oder der "
              "App-Ordner ist schreibgeschützt). Die Release-Seite wurde geöffnet, damit du "
              "manuell aktualisieren kannst.",
        "es": "No se pudo actualizar automáticamente (no hay descarga compatible o la "
              "carpeta de la app es de solo lectura). Se abrió la página de la versión para "
              "que actualices manualmente.",
        "fr": "Impossible de mettre à jour automatiquement (aucun téléchargement "
              "compatible, ou le dossier de l'appli est en lecture seule). La page de la "
              "release a été ouverte pour une mise à jour manuelle.",
        "it": "Impossibile aggiornare automaticamente (nessun download compatibile o la "
              "cartella dell'app è di sola lettura). La pagina della release è stata aperta "
              "per aggiornare manualmente.",
        "ja": "自動更新できませんでした（対応するダウンロードがない、またはアプリ"
              "フォルダが読み取り専用です）。手動で更新できるようリリースページを開きました。"},
    "The update could not be started (the elevation prompt was declined "
    "or blocked). Nothing has changed — try again, or update manually "
    "from the GitHub release page.": {
        "de": "Das Update konnte nicht gestartet werden (die Rechteerhöhung wurde "
              "abgelehnt oder blockiert). Es hat sich nichts geändert — versuche es erneut "
              "oder aktualisiere manuell über die GitHub-Release-Seite.",
        "es": "No se pudo iniciar la actualización (se rechazó o bloqueó la solicitud de "
              "elevación). No ha cambiado nada: inténtalo de nuevo o actualiza manualmente "
              "desde la página de la versión de GitHub.",
        "fr": "La mise à jour n'a pas pu démarrer (l'élévation de privilèges a été refusée "
              "ou bloquée). Rien n'a changé — réessayez, ou mettez à jour manuellement "
              "depuis la page de release GitHub.",
        "it": "Impossibile avviare l'aggiornamento (la richiesta di elevazione è stata "
              "rifiutata o bloccata). Nulla è cambiato — riprova, oppure aggiorna "
              "manualmente dalla pagina della release su GitHub.",
        "ja": "アップデートを開始できませんでした（昇格の要求が拒否またはブロックされ"
              "ました）。何も変更されていません — もう一度試すか、GitHub のリリース"
              "ページから手動で更新してください。"},
    "Empty the database AND delete every downloaded file on disk?\n\n"
    "This removes:\n"
    "  - all cheat files (titles/ and by_bid/)\n"
    "  - all downloaded covers (coversdownload/)\n"
    "  - the packaged ZIP, meta/ folder and cache/skip files\n\n"
    "Region title databases (titledb_*.json) are kept.\n"
    "This CANNOT be undone.": {
        "de": "Die Datenbank leeren UND jede heruntergeladene Datei auf der Festplatte "
              "löschen?\n\nDies entfernt:\n"
              "  - alle Cheat-Dateien (titles/ und by_bid/)\n"
              "  - alle heruntergeladenen Cover (coversdownload/)\n"
              "  - die gepackte ZIP, den meta/-Ordner und Cache-/Skip-Dateien\n\n"
              "Regionale Titel-Datenbanken (titledb_*.json) bleiben erhalten.\n"
              "Dies kann NICHT rückgängig gemacht werden.",
        "es": "¿Vaciar la base de datos Y eliminar todos los archivos descargados del "
              "disco?\n\nEsto elimina:\n"
              "  - todos los archivos de cheats (titles/ y by_bid/)\n"
              "  - todas las carátulas descargadas (coversdownload/)\n"
              "  - el ZIP empaquetado, la carpeta meta/ y los archivos de caché/skip\n\n"
              "Las bases de datos de títulos por región (titledb_*.json) se conservan.\n"
              "Esto NO se puede deshacer.",
        "fr": "Vider la base de données ET supprimer tous les fichiers téléchargés sur le "
              "disque ?\n\nCela supprime :\n"
              "  - tous les fichiers de cheats (titles/ et by_bid/)\n"
              "  - toutes les jaquettes téléchargées (coversdownload/)\n"
              "  - le ZIP empaqueté, le dossier meta/ et les fichiers de cache/skip\n\n"
              "Les bases de titres par région (titledb_*.json) sont conservées.\n"
              "Cette action est IRRÉVERSIBLE.",
        "it": "Svuotare il database E cancellare ogni file scaricato su disco?\n\n"
              "Questo rimuove:\n"
              "  - tutti i file di cheat (titles/ e by_bid/)\n"
              "  - tutte le copertine scaricate (coversdownload/)\n"
              "  - lo ZIP pacchettizzato, la cartella meta/ e i file di cache/skip\n\n"
              "I database dei titoli per regione (titledb_*.json) vengono mantenuti.\n"
              "Questa azione NON può essere annullata.",
        "ja": "データベースを空にし、ディスク上のダウンロード済みファイルをすべて削除"
              "しますか？\n\n削除される対象:\n"
              "  - すべてのチートファイル（titles/ と by_bid/）\n"
              "  - ダウンロード済みのすべてのカバー（coversdownload/）\n"
              "  - パッケージ ZIP、meta/ フォルダ、キャッシュ/スキップファイル\n\n"
              "リージョン別タイトルDB（titledb_*.json）は保持されます。\n"
              "この操作は元に戻せません。"},
    "Build the COMPLETE database in one go:\n\n"
    "   1. Scrape all cheats from cheatslips.com\n"
    "   2. Import the GBATemp archive\n"
    "   3. Import the HamletDuFromage TitleDB archive\n"
    "   4. Import the HamletDuFromage TitleDB 60FPS/Res/GFX archive\n"
    "   5. Import the Sthetix TitleDB archive (daily aggregate)\n"
    "   6. Import the Breeze NXCheatCode database\n"
    "   7. Import the Chansey 60FPS/Res/GFX repo\n"
    "   8. Import the MyNXCheats repo\n"
    "   9. Import titledb cheats\n"
    "  10. Import ibnux/switch-cheat archive\n"
    "  11. Fill names, covers, region + versions\n"
    "  12. Download all cheat files (API, then browser when quota is hit)\n"
    "  13. Download all cover images\n\n"
    "For step 12, enable 'Download via browser when API is limited' so the\n"
    "browser fetches whatever the API can't (daily limit).\n\n"
    "This can take a long while and downloads a lot of data.\n"
    "You can press Stop at any time. Proceed?": {
        "de": "Die KOMPLETTE Datenbank in einem Durchgang aufbauen:\n\n"
              "   1. Alle Cheats von cheatslips.com scrapen\n"
              "   2. Das GBATemp-Archiv importieren\n"
              "   3. Das HamletDuFromage-TitleDB-Archiv importieren\n"
              "   4. Das HamletDuFromage-TitleDB-60FPS/Res/GFX-Archiv importieren\n"
              "   5. Das Sthetix-TitleDB-Archiv importieren (tägliches Aggregat)\n"
              "   6. Die Breeze-NXCheatCode-Datenbank importieren\n"
              "   7. Das Chansey-60FPS/Res/GFX-Repo importieren\n"
              "   8. Das MyNXCheats-Repo importieren\n"
              "   9. titledb-Cheats importieren\n"
              "  10. ibnux/switch-cheat-Archiv importieren\n"
              "  11. Namen, Cover, Region + Versionen füllen\n"
              "  12. Alle Cheat-Dateien herunterladen (API, dann Browser bei Kontingent)\n"
              "  13. Alle Cover-Bilder herunterladen\n\n"
              "Aktiviere für Schritt 12 „Bei API-Limit über den Browser herunterladen“,\n"
              "damit der Browser holt, was die API nicht liefert (Tageslimit).\n\n"
              "Das kann lange dauern und lädt viele Daten.\n"
              "Du kannst jederzeit auf Stopp drücken. Fortfahren?",
        "es": "Construir la base de datos COMPLETA de una vez:\n\n"
              "   1. Extraer todos los cheats de cheatslips.com\n"
              "   2. Importar el archivo GBATemp\n"
              "   3. Importar el archivo HamletDuFromage TitleDB\n"
              "   4. Importar el archivo HamletDuFromage TitleDB 60FPS/Res/GFX\n"
              "   5. Importar el archivo Sthetix TitleDB (agregado diario)\n"
              "   6. Importar la base de datos Breeze NXCheatCode\n"
              "   7. Importar el repo Chansey 60FPS/Res/GFX\n"
              "   8. Importar el repo MyNXCheats\n"
              "   9. Importar cheats de titledb\n"
              "  10. Importar el archivo ibnux/switch-cheat\n"
              "  11. Rellenar nombres, carátulas, región y versiones\n"
              "  12. Descargar todos los cheats (API y luego navegador al llegar a la cuota)\n"
              "  13. Descargar todas las carátulas\n\n"
              "Para el paso 12, activa «Descargar por navegador cuando la API está\n"
              "limitada» para que el navegador obtenga lo que la API no puede (límite diario).\n\n"
              "Esto puede tardar mucho y descarga muchos datos.\n"
              "Puedes pulsar Detener en cualquier momento. ¿Continuar?",
        "fr": "Construire la base de données COMPLÈTE d'un coup :\n\n"
              "   1. Extraire tous les cheats de cheatslips.com\n"
              "   2. Importer l'archive GBATemp\n"
              "   3. Importer l'archive HamletDuFromage TitleDB\n"
              "   4. Importer l'archive HamletDuFromage TitleDB 60FPS/Res/GFX\n"
              "   5. Importer l'archive Sthetix TitleDB (agrégat quotidien)\n"
              "   6. Importer la base Breeze NXCheatCode\n"
              "   7. Importer le dépôt Chansey 60FPS/Res/GFX\n"
              "   8. Importer le dépôt MyNXCheats\n"
              "   9. Importer les cheats titledb\n"
              "  10. Importer l'archive ibnux/switch-cheat\n"
              "  11. Remplir noms, jaquettes, région + versions\n"
              "  12. Télécharger tous les cheats (API, puis navigateur au quota)\n"
              "  13. Télécharger toutes les jaquettes\n\n"
              "Pour l'étape 12, activez « Télécharger via le navigateur quand l'API est\n"
              "limitée » pour que le navigateur récupère ce que l'API ne peut pas (limite "
              "quotidienne).\n\n"
              "Cela peut être long et télécharge beaucoup de données.\n"
              "Vous pouvez appuyer sur Arrêter à tout moment. Continuer ?",
        "it": "Costruire il database COMPLETO in una volta:\n\n"
              "   1. Estrarre tutti i cheat da cheatslips.com\n"
              "   2. Importare l'archivio GBATemp\n"
              "   3. Importare l'archivio HamletDuFromage TitleDB\n"
              "   4. Importare l'archivio HamletDuFromage TitleDB 60FPS/Res/GFX\n"
              "   5. Importare l'archivio Sthetix TitleDB (aggregato giornaliero)\n"
              "   6. Importare il database Breeze NXCheatCode\n"
              "   7. Importare il repo Chansey 60FPS/Res/GFX\n"
              "   8. Importare il repo MyNXCheats\n"
              "   9. Importare i cheat di titledb\n"
              "  10. Importare l'archivio ibnux/switch-cheat\n"
              "  11. Riempire nomi, copertine, regione + versioni\n"
              "  12. Scaricare tutti i cheat (API, poi browser al raggiungimento della quota)\n"
              "  13. Scaricare tutte le copertine\n\n"
              "Per il passo 12, attiva «Scarica dal browser quando l'API è limitata» così\n"
              "il browser recupera ciò che l'API non fornisce (limite giornaliero).\n\n"
              "Può richiedere molto tempo e scarica molti dati.\n"
              "Puoi premere Ferma in qualsiasi momento. Procedere?",
        "ja": "完全なデータベースを一度に構築します:\n\n"
              "   1. cheatslips.com からすべてのチートを取得\n"
              "   2. GBATemp アーカイブをインポート\n"
              "   3. HamletDuFromage TitleDB アーカイブをインポート\n"
              "   4. HamletDuFromage TitleDB 60FPS/Res/GFX アーカイブをインポート\n"
              "   5. Sthetix TitleDB アーカイブをインポート（日次集約）\n"
              "   6. Breeze NXCheatCode データベースをインポート\n"
              "   7. Chansey 60FPS/Res/GFX リポジトリをインポート\n"
              "   8. MyNXCheats リポジトリをインポート\n"
              "   9. titledb のチートをインポート\n"
              "  10. ibnux/switch-cheat アーカイブをインポート\n"
              "  11. 名前・カバー・リージョン・バージョンを補完\n"
              "  12. すべてのチートをダウンロード（API、クォータ到達後はブラウザ）\n"
              "  13. すべてのカバー画像をダウンロード\n\n"
              "手順12では「API制限時はブラウザでダウンロード」を有効にすると、API が"
              "取得できない分（日次制限）をブラウザが取得します。\n\n"
              "長時間かかり、大量のデータをダウンロードします。\n"
              "いつでも「停止」を押せます。続行しますか？"},
    "Build a complete dataset for {n} game(s)?\nRuns in order:\n"
    "  1. Download all cheat files (API)\n"
    "  2. Fill names, region + versions (titledb / API)\n"
    "  3. Fix ID names\n"
    "  4. Fix 0-cheat entries\n\n"
    "Each step continues even if a previous one fails.\n"
    "Already-downloaded builds are skipped automatically.": {
        "de": "Einen kompletten Datensatz für {n} Spiel(e) erstellen?\nLäuft der Reihe "
              "nach:\n  1. Alle Cheat-Dateien herunterladen (API)\n"
              "  2. Namen, Region + Versionen füllen (titledb / API)\n"
              "  3. ID-Namen korrigieren\n  4. Einträge mit 0 Cheats korrigieren\n\n"
              "Jeder Schritt läuft weiter, auch wenn ein vorheriger fehlschlägt.\n"
              "Bereits heruntergeladene Builds werden automatisch übersprungen.",
        "es": "¿Crear un conjunto de datos completo para {n} juego(s)?\nSe ejecuta en "
              "orden:\n  1. Descargar todos los cheats (API)\n"
              "  2. Rellenar nombres, región y versiones (titledb / API)\n"
              "  3. Corregir nombres de ID\n  4. Corregir entradas con 0 cheats\n\n"
              "Cada paso continúa aunque falle el anterior.\n"
              "Los builds ya descargados se omiten automáticamente.",
        "fr": "Créer un jeu de données complet pour {n} jeu(x) ?\nS'exécute dans "
              "l'ordre :\n  1. Télécharger tous les cheats (API)\n"
              "  2. Remplir noms, région + versions (titledb / API)\n"
              "  3. Corriger les noms d'ID\n  4. Corriger les entrées à 0 cheat\n\n"
              "Chaque étape continue même si la précédente échoue.\n"
              "Les builds déjà téléchargés sont ignorés automatiquement.",
        "it": "Creare un dataset completo per {n} gioco/i?\nEsegue in ordine:\n"
              "  1. Scaricare tutti i cheat (API)\n"
              "  2. Riempire nomi, regione + versioni (titledb / API)\n"
              "  3. Correggere i nomi ID\n  4. Correggere le voci con 0 cheat\n\n"
              "Ogni passo continua anche se il precedente fallisce.\n"
              "Le build già scaricate vengono saltate automaticamente.",
        "ja": "{n} 件のゲームの完全なデータセットを構築しますか？\n順番に実行:\n"
              "  1. すべてのチートをダウンロード（API）\n"
              "  2. 名前・リージョン・バージョンを補完（titledb / API）\n"
              "  3. ID 名を修正\n  4. チート0件のエントリを修正\n\n"
              "各手順は前の手順が失敗しても続行します。\n"
              "ダウンロード済みのビルドは自動的にスキップされます。"},
    "Download cheat files for all {n} game(s) via the official API only "
    "(no browser)?\n\nAlready-downloaded builds are skipped.\n"
    "If the API daily quota is hit, it stops — use 'Download Selected' with "
    "the browser option for those.": {
        "de": "Cheat-Dateien für alle {n} Spiel(e) nur über die offizielle API "
              "herunterladen (kein Browser)?\n\nBereits heruntergeladene Builds werden "
              "übersprungen.\nWird das API-Tageslimit erreicht, stoppt es — nutze dafür "
              "„Auswahl herunterladen“ mit der Browser-Option.",
        "es": "¿Descargar los cheats de los {n} juego(s) solo por la API oficial (sin "
              "navegador)?\n\nLos builds ya descargados se omiten.\nSi se alcanza la cuota "
              "diaria de la API, se detiene: para esos usa «Descargar selección» con la "
              "opción del navegador.",
        "fr": "Télécharger les cheats des {n} jeu(x) uniquement via l'API officielle (sans "
              "navigateur) ?\n\nLes builds déjà téléchargés sont ignorés.\nSi le quota "
              "quotidien de l'API est atteint, cela s'arrête — utilisez « Télécharger la "
              "sélection » avec l'option navigateur pour ceux-là.",
        "it": "Scaricare i cheat di tutti i {n} gioco/i solo tramite l'API ufficiale "
              "(senza browser)?\n\nLe build già scaricate vengono saltate.\nSe si raggiunge "
              "la quota giornaliera dell'API, si ferma — per quelle usa «Scarica "
              "selezionati» con l'opzione browser.",
        "ja": "{n} 件すべてのゲームのチートを公式 API のみでダウンロードしますか"
              "（ブラウザなし）？\n\nダウンロード済みのビルドはスキップされます。\n"
              "API の日次クォータに達すると停止します — その分は「選択項目を"
              "ダウンロード」のブラウザオプションを使ってください。"},
    "Refresh game metadata (name, cover, build list, credits) for {n} selected game(s)?": {
        "de": "Spiel-Metadaten (Name, Cover, Build-Liste, Credits) für {n} ausgewählte(s) "
              "Spiel(e) aktualisieren?",
        "es": "¿Actualizar los metadatos (nombre, carátula, lista de builds, créditos) de "
              "{n} juego(s) seleccionado(s)?",
        "fr": "Actualiser les métadonnées (nom, jaquette, liste de builds, crédits) de {n} "
              "jeu(x) sélectionné(s) ?",
        "it": "Aggiornare i metadati (nome, copertina, elenco build, crediti) di {n} "
              "gioco/i selezionato/i?",
        "ja": "{n} 件の選択したゲームのメタデータ（名前・カバー・ビルド一覧・クレジット）"
              "を更新しますか？"},
    "Open a browser and download {n} game(s) directly from "
    "cheatslips.com?\n\n"
    "You log in once (solve the reCAPTCHA if asked); the quota is reset "
    "automatically when needed.": {
        "de": "Einen Browser öffnen und {n} Spiel(e) direkt von cheatslips.com "
              "herunterladen?\n\nDu meldest dich einmal an (löse ggf. das reCAPTCHA); das "
              "Kontingent wird bei Bedarf automatisch zurückgesetzt.",
        "es": "¿Abrir un navegador y descargar {n} juego(s) directamente de "
              "cheatslips.com?\n\nInicias sesión una vez (resuelve el reCAPTCHA si se "
              "pide); la cuota se restablece automáticamente cuando hace falta.",
        "fr": "Ouvrir un navigateur et télécharger {n} jeu(x) directement depuis "
              "cheatslips.com ?\n\nVous vous connectez une fois (résolvez le reCAPTCHA si "
              "demandé) ; le quota est réinitialisé automatiquement au besoin.",
        "it": "Aprire un browser e scaricare {n} gioco/i direttamente da "
              "cheatslips.com?\n\nAccedi una volta (risolvi il reCAPTCHA se richiesto); la "
              "quota viene reimpostata automaticamente quando serve.",
        "ja": "ブラウザを開いて {n} 件のゲームを cheatslips.com から直接"
              "ダウンロードしますか？\n\n1回ログインします（求められたら reCAPTCHA を"
              "解きます）。クォータは必要に応じて自動でリセットされます。"},
    "Open a browser and download {n} selected game(s) directly "
    "from cheatslips.com?\n\nYou log in once (solve the reCAPTCHA if "
    "asked); the quota is reset automatically when needed.": {
        "de": "Einen Browser öffnen und {n} ausgewählte(s) Spiel(e) direkt von "
              "cheatslips.com herunterladen?\n\nDu meldest dich einmal an (löse ggf. das "
              "reCAPTCHA); das Kontingent wird bei Bedarf automatisch zurückgesetzt.",
        "es": "¿Abrir un navegador y descargar {n} juego(s) seleccionado(s) directamente "
              "de cheatslips.com?\n\nInicias sesión una vez (resuelve el reCAPTCHA si se "
              "pide); la cuota se restablece automáticamente cuando hace falta.",
        "fr": "Ouvrir un navigateur et télécharger {n} jeu(x) sélectionné(s) directement "
              "depuis cheatslips.com ?\n\nVous vous connectez une fois (résolvez le "
              "reCAPTCHA si demandé) ; le quota est réinitialisé automatiquement au besoin.",
        "it": "Aprire un browser e scaricare {n} gioco/i selezionato/i direttamente da "
              "cheatslips.com?\n\nAccedi una volta (risolvi il reCAPTCHA se richiesto); la "
              "quota viene reimpostata automaticamente quando serve.",
        "ja": "ブラウザを開いて {n} 件の選択したゲームを cheatslips.com から直接"
              "ダウンロードしますか？\n\n1回ログインします（求められたら reCAPTCHA を"
              "解きます）。クォータは必要に応じて自動でリセットされます。"},
    "Download cover images for all entries in the database and save them to\n"
    "{dir}?\n\n"
    "Already-saved covers are skipped. (Entries without a cover URL are ignored.)": {
        "de": "Cover-Bilder für alle Einträge in der Datenbank herunterladen und "
              "speichern unter\n{dir}?\n\nBereits gespeicherte Cover werden übersprungen. "
              "(Einträge ohne Cover-URL werden ignoriert.)",
        "es": "¿Descargar las carátulas de todas las entradas de la base de datos y "
              "guardarlas en\n{dir}?\n\nLas carátulas ya guardadas se omiten. (Se ignoran "
              "las entradas sin URL de carátula.)",
        "fr": "Télécharger les jaquettes de toutes les entrées de la base et les "
              "enregistrer dans\n{dir} ?\n\nLes jaquettes déjà enregistrées sont ignorées. "
              "(Les entrées sans URL de jaquette sont ignorées.)",
        "it": "Scaricare le copertine di tutte le voci del database e salvarle in\n{dir}?"
              "\n\nLe copertine già salvate vengono saltate. (Le voci senza URL della "
              "copertina vengono ignorate.)",
        "ja": "データベース内のすべてのエントリのカバー画像をダウンロードして\n{dir} に"
              "保存しますか？\n\n保存済みのカバーはスキップされます（カバー URL のない"
              "エントリは無視されます）。"},
    "Delete {n} selected entries?\n"
    "This also deletes the downloaded cheat file(s) on disk.": {
        "de": "{n} ausgewählte Einträge löschen?\nDies löscht auch die "
              "heruntergeladenen Cheat-Datei(en) auf der Festplatte.",
        "es": "¿Eliminar {n} entradas seleccionadas?\nEsto también elimina los archivos "
              "de cheats descargados en el disco.",
        "fr": "Supprimer {n} entrées sélectionnées ?\nCela supprime aussi les fichiers de "
              "cheats téléchargés sur le disque.",
        "it": "Eliminare {n} voci selezionate?\nQuesto elimina anche i file di cheat "
              "scaricati su disco.",
        "ja": "選択した {n} 件のエントリを削除しますか？\nディスク上のダウンロード済み"
              "チートファイルも削除されます。"},
    "Import cheats from:\n{path}\n\nAdd them to the database and the "
    "output folder?": {
        "de": "Cheats importieren aus:\n{path}\n\nZur Datenbank und zum Ausgabeordner "
              "hinzufügen?",
        "es": "Importar cheats desde:\n{path}\n\n¿Añadirlos a la base de datos y a la "
              "carpeta de salida?",
        "fr": "Importer les cheats depuis :\n{path}\n\nLes ajouter à la base de données et "
              "au dossier de sortie ?",
        "it": "Importare i cheat da:\n{path}\n\nAggiungerli al database e alla cartella di "
              "output?",
        "ja": "次からチートをインポート:\n{path}\n\nデータベースと出力フォルダに"
              "追加しますか？"},
    "No titles/ or by_bid/ folder found in:\n{path}\n\n"
    "Download or place cheat files there first.": {
        "de": "Kein titles/- oder by_bid/-Ordner gefunden in:\n{path}\n\nLade oder lege "
              "dort zuerst Cheat-Dateien ab.",
        "es": "No se encontró ninguna carpeta titles/ ni by_bid/ en:\n{path}\n\nDescarga "
              "o coloca primero archivos de cheats ahí.",
        "fr": "Aucun dossier titles/ ou by_bid/ trouvé dans :\n{path}\n\nTéléchargez ou "
              "placez-y d'abord des fichiers de cheats.",
        "it": "Nessuna cartella titles/ o by_bid/ trovata in:\n{path}\n\nScarica o "
              "inserisci prima dei file di cheat lì.",
        "ja": "titles/ または by_bid/ フォルダが見つかりません:\n{path}\n\n先にそこへ"
              "チートファイルをダウンロードまたは配置してください。"},
    "Scan {path} for titles/ and by_bid/ cheat files and import missing entries into the DB?\n\n"
    "Known build ids (e.g. Potion Permit) will be linked automatically.": {
        "de": "{path} nach titles/- und by_bid/-Cheat-Dateien durchsuchen und fehlende "
              "Einträge in die DB importieren?\n\nBekannte Build-IDs (z. B. Potion Permit) "
              "werden automatisch verknüpft.",
        "es": "¿Analizar {path} en busca de archivos de cheats titles/ y by_bid/ e "
              "importar las entradas que faltan a la BD?\n\nLos build IDs conocidos (p. ej. "
              "Potion Permit) se enlazan automáticamente.",
        "fr": "Analyser {path} pour les fichiers de cheats titles/ et by_bid/ et importer "
              "les entrées manquantes dans la BD ?\n\nLes build IDs connus (p. ex. Potion "
              "Permit) sont liés automatiquement.",
        "it": "Analizzare {path} per i file di cheat titles/ e by_bid/ e importare le voci "
              "mancanti nel DB?\n\nI build ID noti (es. Potion Permit) verranno collegati "
              "automaticamente.",
        "ja": "{path} を titles/ と by_bid/ のチートファイルについてスキャンし、"
              "不足しているエントリを DB にインポートしますか？\n\n既知の build ID"
              "（例: Potion Permit）は自動的にリンクされます。"},
    "{n} build(s) are marked as having no codes on cheatslips and "
    "are skipped during downloads.\n\nClear these marks so they are "
    "retried on the next download?": {
        "de": "{n} Build(s) sind als „keine Codes auf cheatslips“ markiert und werden bei "
              "Downloads übersprungen.\n\nDiese Markierungen entfernen, damit sie beim "
              "nächsten Download erneut versucht werden?",
        "es": "{n} build(s) están marcados como «sin códigos en cheatslips» y se omiten en "
              "las descargas.\n\n¿Quitar estas marcas para que se reintenten en la próxima "
              "descarga?",
        "fr": "{n} build(s) sont marqués comme « sans codes sur cheatslips » et sont "
              "ignorés lors des téléchargements.\n\nEffacer ces marques pour les réessayer "
              "au prochain téléchargement ?",
        "it": "{n} build sono contrassegnate come «senza codici su cheatslips» e vengono "
              "saltate durante i download.\n\nRimuovere questi contrassegni per riprovarle "
              "al prossimo download?",
        "ja": "{n} 件のビルドが「cheatslips にコードなし」と記録され、ダウンロード時に"
              "スキップされます。\n\nこの記録を消して次回のダウンロードで再試行しますか？"},
    "No quota-skipped list found.\n\nExpected file:\n{path}\n\n"
    "Run a download first; skipped builds are recorded automatically.": {
        "de": "Keine Liste kontingentübersprungener Builds gefunden.\n\nErwartete Datei:\n"
              "{path}\n\nFühre zuerst einen Download aus; übersprungene Builds werden "
              "automatisch aufgezeichnet.",
        "es": "No se encontró ninguna lista de builds omitidos por cuota.\n\nArchivo "
              "esperado:\n{path}\n\nEjecuta una descarga primero; los builds omitidos se "
              "registran automáticamente.",
        "fr": "Aucune liste de builds ignorés (quota) trouvée.\n\nFichier attendu :\n"
              "{path}\n\nLancez d'abord un téléchargement ; les builds ignorés sont "
              "enregistrés automatiquement.",
        "it": "Nessun elenco di build saltate per quota trovato.\n\nFile previsto:\n{path}"
              "\n\nEsegui prima un download; le build saltate vengono registrate "
              "automaticamente.",
        "ja": "クォータでスキップされたビルドの一覧が見つかりません。\n\n想定される"
              "ファイル:\n{path}\n\n先にダウンロードを実行してください。スキップされた"
              "ビルドは自動的に記録されます。"},
    "Retry {n} build(s) from {name}?\n\n"
    "Make sure your quota has reset first.": {
        "de": "{n} Build(s) aus {name} erneut versuchen?\n\nStelle sicher, dass dein "
              "Kontingent zuvor zurückgesetzt wurde.",
        "es": "¿Reintentar {n} build(s) de {name}?\n\nAsegúrate de que tu cuota se haya "
              "restablecido primero.",
        "fr": "Réessayer {n} build(s) depuis {name} ?\n\nAssurez-vous d'abord que votre "
              "quota est réinitialisé.",
        "it": "Riprovare {n} build da {name}?\n\nAssicurati prima che la tua quota sia "
              "stata reimpostata.",
        "ja": "{name} の {n} 件のビルドを再試行しますか？\n\n先にクォータが"
              "リセットされていることを確認してください。"},
    "Replace the ENTIRE current database with the imported one?\n\n"
    "A timestamped backup of the current database is saved first.": {
        "de": "Die GESAMTE aktuelle Datenbank durch die importierte ersetzen?\n\nZuvor "
              "wird ein Backup der aktuellen Datenbank mit Zeitstempel gespeichert.",
        "es": "¿Reemplazar TODA la base de datos actual por la importada?\n\nAntes se "
              "guarda una copia de seguridad con marca de tiempo de la base actual.",
        "fr": "Remplacer TOUTE la base de données actuelle par celle importée ?\n\nUne "
              "sauvegarde horodatée de la base actuelle est enregistrée au préalable.",
        "it": "Sostituire l'INTERO database attuale con quello importato?\n\nPrima viene "
              "salvato un backup con data e ora del database attuale.",
        "ja": "現在のデータベース全体をインポートしたもので置き換えますか？\n\n先に"
              "現在のデータベースのタイムスタンプ付きバックアップが保存されます。"},
    "Afterwards: names + covers + region, versions "
    "(titledb only) and a\ncheat-count recount from disk.": {
        "de": "Danach: Namen + Cover + Region, Versionen (nur titledb) und eine\n"
              "Cheat-Anzahl-Neuzählung von der Festplatte.",
        "es": "Después: nombres + carátulas + región, versiones (solo titledb) y un\n"
              "recuento de cheats desde el disco.",
        "fr": "Ensuite : noms + jaquettes + région, versions (titledb uniquement) et un\n"
              "recomptage des cheats depuis le disque.",
        "it": "Successivamente: nomi + copertine + regione, versioni (solo titledb) e un\n"
              "riconteggio dei cheat dal disco.",
        "ja": "その後: 名前 + カバー + リージョン、バージョン（titledb のみ）、および\n"
              "ディスクからのチート数の再集計。"},
})

# ---- Archive-import button titles + messages -------------------------------
_merge({
    "Download GBAtemp Archive": {
        "de": "GBAtemp-Archiv herunterladen", "es": "Descargar archivo GBAtemp",
        "fr": "Télécharger l'archive GBAtemp", "it": "Scarica archivio GBAtemp",
        "ja": "GBAtemp アーカイブをダウンロード"},
    "Download the latest GBAtemp/HamletDuFromage cheat archive,\n"
    "extract all cheat files and add them to the database?": {
        "de": "Das neueste GBAtemp/HamletDuFromage-Cheat-Archiv herunterladen,\nalle "
              "Cheat-Dateien extrahieren und zur Datenbank hinzufügen?",
        "es": "¿Descargar el último archivo de cheats GBAtemp/HamletDuFromage,\nextraer "
              "todos los archivos y añadirlos a la base de datos?",
        "fr": "Télécharger la dernière archive de cheats GBAtemp/HamletDuFromage,\nen "
              "extraire tous les fichiers et les ajouter à la base de données ?",
        "it": "Scaricare l'ultimo archivio di cheat GBAtemp/HamletDuFromage,\nestrarre "
              "tutti i file e aggiungerli al database?",
        "ja": "最新の GBAtemp/HamletDuFromage チートアーカイブをダウンロードし、\n"
              "すべてのチートファイルを展開してデータベースに追加しますか？"},
    "Download HamletDuFromage TitleDB": {
        "de": "HamletDuFromage TitleDB herunterladen",
        "es": "Descargar HamletDuFromage TitleDB",
        "fr": "Télécharger HamletDuFromage TitleDB",
        "it": "Scarica HamletDuFromage TitleDB",
        "ja": "HamletDuFromage TitleDB をダウンロード"},
    "Download HamletDuFromage's titles_complete.zip from the LATEST\n"
    "switch-cheats-db release (always the newest), extract all cheat\n"
    "files and add them to the database?": {
        "de": "HamletDuFromages titles_complete.zip aus dem NEUESTEN\nswitch-cheats-db-"
              "Release (immer das aktuellste) herunterladen, alle\nCheat-Dateien "
              "extrahieren und zur Datenbank hinzufügen?",
        "es": "¿Descargar titles_complete.zip de HamletDuFromage de la ÚLTIMA\nversión de "
              "switch-cheats-db (siempre la más reciente), extraer todos\nlos archivos y "
              "añadirlos a la base de datos?",
        "fr": "Télécharger le titles_complete.zip de HamletDuFromage depuis la DERNIÈRE\n"
              "release switch-cheats-db (toujours la plus récente), en extraire tous\nles "
              "fichiers et les ajouter à la base de données ?",
        "it": "Scaricare titles_complete.zip di HamletDuFromage dall'ULTIMA\nrelease di "
              "switch-cheats-db (sempre la più recente), estrarre tutti\ni file e "
              "aggiungerli al database?",
        "ja": "HamletDuFromage の titles_complete.zip を最新の switch-cheats-db\n"
              "リリース（常に最新）からダウンロードし、すべてのチートファイルを展開して\n"
              "データベースに追加しますか？"},
    "Download HamletDuFromage TitleDB 60FPS/Res/GFX": {
        "de": "HamletDuFromage TitleDB 60FPS/Res/GFX herunterladen",
        "es": "Descargar HamletDuFromage TitleDB 60FPS/Res/GFX",
        "fr": "Télécharger HamletDuFromage TitleDB 60FPS/Res/GFX",
        "it": "Scarica HamletDuFromage TitleDB 60FPS/Res/GFX",
        "ja": "HamletDuFromage TitleDB 60FPS/Res/GFX をダウンロード"},
    "Download HamletDuFromage's titles_60fps-res-gfx.zip (60 FPS /\n"
    "resolution / GFX cheats) from the LATEST switch-cheats-db release\n"
    "(always the newest), extract all cheat files and add them to the\n"
    "database?": {
        "de": "HamletDuFromages titles_60fps-res-gfx.zip (60 FPS /\nAuflösung / GFX-Cheats) "
              "aus dem NEUESTEN switch-cheats-db-Release\n(immer das aktuellste) "
              "herunterladen, alle Cheat-Dateien extrahieren\nund zur Datenbank hinzufügen?",
        "es": "¿Descargar titles_60fps-res-gfx.zip de HamletDuFromage (cheats de 60 FPS /\n"
              "resolución / GFX) de la ÚLTIMA versión de switch-cheats-db\n(siempre la más "
              "reciente), extraer todos los archivos y añadirlos a la\nbase de datos?",
        "fr": "Télécharger le titles_60fps-res-gfx.zip de HamletDuFromage (cheats 60 FPS /\n"
              "résolution / GFX) depuis la DERNIÈRE release switch-cheats-db\n(toujours la "
              "plus récente), en extraire tous les fichiers et les ajouter\nà la base de "
              "données ?",
        "it": "Scaricare titles_60fps-res-gfx.zip di HamletDuFromage (cheat 60 FPS /\n"
              "risoluzione / GFX) dall'ULTIMA release di switch-cheats-db\n(sempre la più "
              "recente), estrarre tutti i file e aggiungerli al\ndatabase?",
        "ja": "HamletDuFromage の titles_60fps-res-gfx.zip（60FPS /\n解像度 / GFX チート）"
              "を最新の switch-cheats-db リリース\n（常に最新）からダウンロードし、すべての"
              "チートファイルを展開して\nデータベースに追加しますか？"},
    "Download Sthetix TitleDB": {
        "de": "Sthetix TitleDB herunterladen", "es": "Descargar Sthetix TitleDB",
        "fr": "Télécharger Sthetix TitleDB", "it": "Scarica Sthetix TitleDB",
        "ja": "Sthetix TitleDB をダウンロード"},
    "Download titles_complete.zip from the LATEST sthetix/nx-cheats-db\n"
    "release — a DAILY-updated aggregate of GBAtemp + graphics cheats +\n"
    "switch-cheats-db + cheatslips (~141k cheats) — and add all cheats\n"
    "to the database?": {
        "de": "titles_complete.zip aus dem NEUESTEN sthetix/nx-cheats-db-Release\n"
              "herunterladen — ein TÄGLICH aktualisiertes Aggregat aus GBAtemp + "
              "Grafik-Cheats +\nswitch-cheats-db + cheatslips (~141k Cheats) — und alle "
              "Cheats\nzur Datenbank hinzufügen?",
        "es": "¿Descargar titles_complete.zip de la ÚLTIMA versión de sthetix/nx-cheats-db"
              "\n— un agregado actualizado A DIARIO de GBAtemp + cheats gráficos +\n"
              "switch-cheats-db + cheatslips (~141k cheats) — y añadir todos los cheats\na "
              "la base de datos?",
        "fr": "Télécharger titles_complete.zip depuis la DERNIÈRE release sthetix/nx-cheats-db"
              "\n— un agrégat mis à jour QUOTIDIENNEMENT de GBAtemp + cheats graphiques +\n"
              "switch-cheats-db + cheatslips (~141k cheats) — et ajouter tous les cheats\nà "
              "la base de données ?",
        "it": "Scaricare titles_complete.zip dall'ULTIMA release di sthetix/nx-cheats-db\n"
              "— un aggregato aggiornato OGNI GIORNO di GBAtemp + cheat grafici +\n"
              "switch-cheats-db + cheatslips (~141k cheat) — e aggiungere tutti i cheat\nal "
              "database?",
        "ja": "最新の sthetix/nx-cheats-db リリースから titles_complete.zip を\n"
              "ダウンロードしますか — GBAtemp + グラフィックチート +\nswitch-cheats-db + "
              "cheatslips を毎日更新した集約（約141kチート）— そして\nすべてのチートを"
              "データベースに追加しますか？"},
    "Download Breeze NXCheatCode": {
        "de": "Breeze NXCheatCode herunterladen", "es": "Descargar Breeze NXCheatCode",
        "fr": "Télécharger Breeze NXCheatCode", "it": "Scarica Breeze NXCheatCode",
        "ja": "Breeze NXCheatCode をダウンロード"},
    "Download titles.zip (the Breeze/EdiZon-SE cheat database) from the\n"
    "LATEST tomvita/NXCheatCode release — GBAtemp community codes,\n"
    "partly different from cheatslips — and add all cheats to the\n"
    "database?": {
        "de": "titles.zip (die Breeze/EdiZon-SE-Cheat-Datenbank) aus dem\nNEUESTEN "
              "tomvita/NXCheatCode-Release herunterladen — GBAtemp-Community-Codes,\nteils "
              "anders als cheatslips — und alle Cheats zur\nDatenbank hinzufügen?",
        "es": "¿Descargar titles.zip (la base de datos de cheats Breeze/EdiZon-SE) de la\n"
              "ÚLTIMA versión de tomvita/NXCheatCode — códigos de la comunidad de GBAtemp,\n"
              "en parte distintos de cheatslips — y añadir todos los cheats a la\nbase de "
              "datos?",
        "fr": "Télécharger titles.zip (la base de cheats Breeze/EdiZon-SE) depuis la\n"
              "DERNIÈRE release tomvita/NXCheatCode — codes de la communauté GBAtemp,\nen "
              "partie différents de cheatslips — et ajouter tous les cheats à la\nbase de "
              "données ?",
        "it": "Scaricare titles.zip (il database di cheat Breeze/EdiZon-SE) dall'\nULTIMA "
              "release di tomvita/NXCheatCode — codici della community GBAtemp,\nin parte "
              "diversi da cheatslips — e aggiungere tutti i cheat al\ndatabase?",
        "ja": "titles.zip（Breeze/EdiZon-SE のチートデータベース）を最新の\n"
              "tomvita/NXCheatCode リリースからダウンロードしますか — GBAtemp "
              "コミュニティコード、\ncheatslips とは一部異なります — そしてすべての"
              "チートを\nデータベースに追加しますか？"},
    "Download Chansey 60FPS/Res/GFX": {
        "de": "Chansey 60FPS/Res/GFX herunterladen",
        "es": "Descargar Chansey 60FPS/Res/GFX",
        "fr": "Télécharger Chansey 60FPS/Res/GFX",
        "it": "Scarica Chansey 60FPS/Res/GFX",
        "ja": "Chansey 60FPS/Res/GFX をダウンロード"},
    "Import the LIVE ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats repo —\n"
    "the ORIGINAL source of the 60 FPS / resolution / graphics cheats,\n"
    "always current — and add all cheats to the database?": {
        "de": "Das LIVE-Repo ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats importieren —\ndie "
              "ORIGINAL-Quelle der 60-FPS-/Auflösungs-/Grafik-Cheats,\nimmer aktuell — und "
              "alle Cheats zur Datenbank hinzufügen?",
        "es": "¿Importar el repo EN VIVO ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats —\nla "
              "fuente ORIGINAL de los cheats de 60 FPS / resolución / gráficos,\nsiempre "
              "actual — y añadir todos los cheats a la base de datos?",
        "fr": "Importer le dépôt EN DIRECT ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats —\nla "
              "source ORIGINALE des cheats 60 FPS / résolution / graphismes,\ntoujours à "
              "jour — et ajouter tous les cheats à la base de données ?",
        "it": "Importare il repo LIVE ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats —\nla fonte "
              "ORIGINALE dei cheat 60 FPS / risoluzione / grafica,\nsempre aggiornata — e "
              "aggiungere tutti i cheat al database?",
        "ja": "ライブリポジトリ ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats を\n"
              "インポートしますか — 60FPS / 解像度 / グラフィックチートの本家、\n常に最新 "
              "— そしてすべてのチートをデータベースに追加しますか？"},
    "Download MyNXCheats": {
        "de": "MyNXCheats herunterladen", "es": "Descargar MyNXCheats",
        "fr": "Télécharger MyNXCheats", "it": "Scarica MyNXCheats",
        "ja": "MyNXCheats をダウンロード"},
    "Import the LIVE Arch9SK7/MyNXCheats repo — a curated collection\n"
    "for ~50 recent big titles (TotK, Scarlet/Violet, ...) — and add\n"
    "all cheats to the database?": {
        "de": "Das LIVE-Repo Arch9SK7/MyNXCheats importieren — eine kuratierte Sammlung\n"
              "für ~50 aktuelle große Titel (TotK, Karmesin/Purpur, …) — und alle\nCheats "
              "zur Datenbank hinzufügen?",
        "es": "¿Importar el repo EN VIVO Arch9SK7/MyNXCheats — una colección curada\npara "
              "~50 grandes títulos recientes (TotK, Escarlata/Púrpura, ...) — y añadir\n"
              "todos los cheats a la base de datos?",
        "fr": "Importer le dépôt EN DIRECT Arch9SK7/MyNXCheats — une collection "
              "sélectionnée\npour ~50 grands titres récents (TotK, Écarlate/Violet, ...) — "
              "et ajouter\ntous les cheats à la base de données ?",
        "it": "Importare il repo LIVE Arch9SK7/MyNXCheats — una raccolta curata\nper ~50 "
              "grandi titoli recenti (TotK, Scarlatto/Violetto, ...) — e aggiungere\ntutti "
              "i cheat al database?",
        "ja": "ライブリポジトリ Arch9SK7/MyNXCheats をインポートしますか — 最近の"
              "大型タイトル\n約50本（TotK、スカーレット/バイオレットなど）向けの厳選"
              "コレクション — そして\nすべてのチートをデータベースに追加しますか？"},
    "titledb Cheats": {"de": "titledb-Cheats", "es": "Cheats de titledb",
                       "fr": "Cheats titledb", "it": "Cheat titledb",
                       "ja": "titledb チート"},
    "Import titledb's own cheat database (cheats.json) as an extra source?": {
        "de": "titledbs eigene Cheat-Datenbank (cheats.json) als zusätzliche Quelle "
              "importieren?",
        "es": "¿Importar la propia base de datos de cheats de titledb (cheats.json) como "
              "fuente adicional?",
        "fr": "Importer la base de cheats propre à titledb (cheats.json) comme source "
              "supplémentaire ?",
        "it": "Importare il database di cheat di titledb (cheats.json) come fonte "
              "aggiuntiva?",
        "ja": "titledb 独自のチートデータベース（cheats.json）を追加ソースとして"
              "インポートしますか？"},
    "ibnux/switch-cheat": {"de": "ibnux/switch-cheat", "es": "ibnux/switch-cheat",
                           "fr": "ibnux/switch-cheat", "it": "ibnux/switch-cheat",
                           "ja": "ibnux/switch-cheat"},
    "Download the latest ibnux/switch-cheat archive, extract all cheats\n"
    "and add them to the database?": {
        "de": "Das neueste ibnux/switch-cheat-Archiv herunterladen, alle Cheats "
              "extrahieren\nund zur Datenbank hinzufügen?",
        "es": "¿Descargar el último archivo ibnux/switch-cheat, extraer todos los cheats\ny "
              "añadirlos a la base de datos?",
        "fr": "Télécharger la dernière archive ibnux/switch-cheat, en extraire tous les "
              "cheats\net les ajouter à la base de données ?",
        "it": "Scaricare l'ultimo archivio ibnux/switch-cheat, estrarre tutti i cheat\ne "
              "aggiungerli al database?",
        "ja": "最新の ibnux/switch-cheat アーカイブをダウンロードし、すべてのチートを"
              "展開して\nデータベースに追加しますか？"},
})

# ---- Status-bar messages (static) ------------------------------------------
_merge({
    "Ready.": {"de": "Bereit.", "es": "Listo.", "fr": "Prêt.", "it": "Pronto.",
               "ja": "準備完了。"},
    "Browser download...": {
        "de": "Browser-Download…", "es": "Descarga por navegador…",
        "fr": "Téléchargement via le navigateur…", "it": "Download dal browser…",
        "ja": "ブラウザでダウンロード中…"},
    "Check cheat file: nothing checked.": {
        "de": "Cheat-Datei prüfen: nichts geprüft.",
        "es": "Comprobar archivo de cheats: nada comprobado.",
        "fr": "Vérifier le fichier de cheats : rien de vérifié.",
        "it": "Controlla file di cheat: nulla controllato.",
        "ja": "チートファイル確認: 何も確認されませんでした。"},
    "SD export failed — see log.": {
        "de": "SD-Export fehlgeschlagen — siehe Log.",
        "es": "Fallo al exportar a SD: consulta el registro.",
        "fr": "Échec de l'export vers la SD — voir le journal.",
        "it": "Esportazione su SD non riuscita — vedi il log.",
        "ja": "SD へのエクスポートに失敗 — ログを参照してください。"},
    "ZIP export failed — see log.": {
        "de": "ZIP-Export fehlgeschlagen — siehe Log.",
        "es": "Fallo al exportar a ZIP: consulta el registro.",
        "fr": "Échec de l'export en ZIP — voir le journal.",
        "it": "Esportazione in ZIP non riuscita — vedi il log.",
        "ja": "ZIP へのエクスポートに失敗 — ログを参照してください。"},
    "ZIP export: nothing to export (no downloaded cheats).": {
        "de": "ZIP-Export: nichts zu exportieren (keine heruntergeladenen Cheats).",
        "es": "Exportar a ZIP: nada que exportar (no hay cheats descargados).",
        "fr": "Export ZIP : rien à exporter (aucun cheat téléchargé).",
        "it": "Esportazione ZIP: nulla da esportare (nessun cheat scaricato).",
        "ja": "ZIP エクスポート: エクスポート対象なし（ダウンロード済みチートなし）。"},
    "Import database failed — see log.": {
        "de": "Datenbankimport fehlgeschlagen — siehe Log.",
        "es": "Fallo al importar la base de datos: consulta el registro.",
        "fr": "Échec de l'import de la base de données — voir le journal.",
        "it": "Importazione del database non riuscita — vedi il log.",
        "ja": "データベースのインポートに失敗 — ログを参照してください。"},
    "Downloading from DevCatSKZ...": {
        "de": "Wird von DevCatSKZ heruntergeladen…", "es": "Descargando de DevCatSKZ…",
        "fr": "Téléchargement depuis DevCatSKZ…", "it": "Download da DevCatSKZ…",
        "ja": "DevCatSKZ からダウンロード中…"},
    "Downloading update…": {
        "de": "Update wird heruntergeladen…", "es": "Descargando actualización…",
        "fr": "Téléchargement de la mise à jour…", "it": "Download dell'aggiornamento…",
        "ja": "アップデートをダウンロード中…"},
    "Update installing — the app will close and reopen…": {
        "de": "Update wird installiert — die App wird geschlossen und neu geöffnet…",
        "es": "Instalando actualización: la app se cerrará y volverá a abrirse…",
        "fr": "Installation de la mise à jour — l'appli va se fermer et rouvrir…",
        "it": "Installazione dell'aggiornamento — l'app si chiuderà e riaprirà…",
        "ja": "アップデートをインストール中 — アプリが終了して再度開きます…"},
    "Updating — the app will close and reopen…": {
        "de": "Update läuft — die App wird geschlossen und neu geöffnet…",
        "es": "Actualizando: la app se cerrará y volverá a abrirse…",
        "fr": "Mise à jour — l'appli va se fermer et rouvrir…",
        "it": "Aggiornamento — l'app si chiuderà e riaprirà…",
        "ja": "更新中 — アプリが終了して再度開きます…"},
    "Downloading data update from DevCatSKZ…": {
        "de": "Daten-Update wird von DevCatSKZ heruntergeladen…",
        "es": "Descargando actualización de datos de DevCatSKZ…",
        "fr": "Téléchargement de la mise à jour des données depuis DevCatSKZ…",
        "it": "Download dell'aggiornamento dei dati da DevCatSKZ…",
        "ja": "DevCatSKZ からデータ更新をダウンロード中…"},
    "Opening browser for cheatslips login...": {
        "de": "Browser für cheatslips-Login wird geöffnet…",
        "es": "Abriendo el navegador para iniciar sesión en cheatslips…",
        "fr": "Ouverture du navigateur pour la connexion cheatslips…",
        "it": "Apertura del browser per l'accesso a cheatslips…",
        "ja": "cheatslips ログイン用にブラウザを開いています…"},
    "Downloading covers...": {
        "de": "Cover werden heruntergeladen…", "es": "Descargando carátulas…",
        "fr": "Téléchargement des jaquettes…", "it": "Download delle copertine…",
        "ja": "カバー画像をダウンロード中…"},
    "Scrape & Download Everything started...": {
        "de": "„Alles scrapen & herunterladen“ gestartet…",
        "es": "«Extraer y descargar todo» iniciado…",
        "fr": "« Tout extraire et télécharger » démarré…",
        "it": "«Estrai e scarica tutto» avviato…",
        "ja": "「すべて取得してダウンロード」を開始しました…"},
    "Firefox is ready.": {
        "de": "Firefox ist bereit.", "es": "Firefox está listo.",
        "fr": "Firefox est prêt.", "it": "Firefox è pronto.",
        "ja": "Firefox の準備ができました。"},
    "Checking for new cheats...": {
        "de": "Suche nach neuen Cheats…", "es": "Buscando cheats nuevos…",
        "fr": "Recherche de nouveaux cheats…", "it": "Ricerca di nuovi cheat…",
        "ja": "新しいチートを確認中…"},
    "Importing cheat files from disk...": {
        "de": "Cheat-Dateien von der Festplatte werden importiert…",
        "es": "Importando archivos de cheats desde el disco…",
        "fr": "Import des fichiers de cheats depuis le disque…",
        "it": "Importazione dei file di cheat dal disco…",
        "ja": "ディスクからチートファイルをインポート中…"},
    "Fixing title-id placeholders...": {
        "de": "Title-ID-Platzhalter werden korrigiert…",
        "es": "Corrigiendo marcadores de Title ID…",
        "fr": "Correction des espaces réservés de Title ID…",
        "it": "Correzione dei segnaposto Title ID…",
        "ja": "Title ID のプレースホルダを修正中…"},
    "Clearing database and downloaded files...": {
        "de": "Datenbank und heruntergeladene Dateien werden gelöscht…",
        "es": "Vaciando la base de datos y los archivos descargados…",
        "fr": "Suppression de la base de données et des fichiers téléchargés…",
        "it": "Cancellazione del database e dei file scaricati…",
        "ja": "データベースとダウンロード済みファイルを消去中…"},
    "Recounting cheats from disk...": {
        "de": "Cheats werden von der Festplatte neu gezählt…",
        "es": "Recontando cheats desde el disco…",
        "fr": "Recomptage des cheats depuis le disque…",
        "it": "Riconteggio dei cheat dal disco…",
        "ja": "ディスクからチート数を再集計中…"},
    "Connecting to the API...": {
        "de": "Verbindung zur API…", "es": "Conectando con la API…",
        "fr": "Connexion à l'API…", "it": "Connessione all'API…",
        "ja": "API に接続中…"},
    "Downloading via API...": {
        "de": "Download über die API…", "es": "Descargando por la API…",
        "fr": "Téléchargement via l'API…", "it": "Download tramite API…",
        "ja": "API でダウンロード中…"},
    "Scraping done - starting download...": {
        "de": "Scrapen fertig – Download wird gestartet…",
        "es": "Extracción terminada: iniciando la descarga…",
        "fr": "Extraction terminée — démarrage du téléchargement…",
        "it": "Estrazione completata — avvio del download…",
        "ja": "取得完了 — ダウンロードを開始します…"},
    "Scraping started...": {
        "de": "Scrapen gestartet…", "es": "Extracción iniciada…",
        "fr": "Extraction démarrée…", "it": "Estrazione avviata…",
        "ja": "取得を開始しました…"},
    "Stopping after the current item...": {
        "de": "Stoppt nach dem aktuellen Element…",
        "es": "Deteniendo tras el elemento actual…",
        "fr": "Arrêt après l'élément en cours…",
        "it": "Arresto dopo l'elemento corrente…",
        "ja": "現在の項目の後で停止します…"},
    "Building complete dataset...": {
        "de": "Kompletter Datensatz wird erstellt…",
        "es": "Creando el conjunto de datos completo…",
        "fr": "Création du jeu de données complet…",
        "it": "Creazione del dataset completo…",
        "ja": "完全なデータセットを構築中…"},
})

# ---- Status-bar messages (templated) ---------------------------------------
_merge({
    "Checking {n} cheat file(s)...": {
        "de": "{n} Cheat-Datei(en) werden geprüft…",
        "es": "Comprobando {n} archivo(s) de cheats…",
        "fr": "Vérification de {n} fichier(s) de cheats…",
        "it": "Controllo di {n} file di cheat…",
        "ja": "{n} 件のチートファイルを確認中…"},
    "Exporting cheats to SD ({mode})...": {
        "de": "Cheats werden auf SD exportiert ({mode})…",
        "es": "Exportando cheats a SD ({mode})…",
        "fr": "Export des cheats vers la SD ({mode})…",
        "it": "Esportazione dei cheat su SD ({mode})…",
        "ja": "チートを SD にエクスポート中（{mode}）…"},
    "Exporting cheats to ZIP ({mode})...": {
        "de": "Cheats werden als ZIP exportiert ({mode})…",
        "es": "Exportando cheats a ZIP ({mode})…",
        "fr": "Export des cheats en ZIP ({mode})…",
        "it": "Esportazione dei cheat in ZIP ({mode})…",
        "ja": "チートを ZIP にエクスポート中（{mode}）…"},
    "Importing database ({mode})...": {
        "de": "Datenbank wird importiert ({mode})…",
        "es": "Importando la base de datos ({mode})…",
        "fr": "Import de la base de données ({mode})…",
        "it": "Importazione del database ({mode})…",
        "ja": "データベースをインポート中（{mode}）…"},
    "Downloading {name}…": {
        "de": "{name} wird heruntergeladen…", "es": "Descargando {name}…",
        "fr": "Téléchargement de {name}…", "it": "Download di {name}…",
        "ja": "{name} をダウンロード中…"},
    "Downloading {name}...": {
        "de": "{name} wird heruntergeladen…", "es": "Descargando {name}…",
        "fr": "Téléchargement de {name}…", "it": "Download di {name}…",
        "ja": "{name} をダウンロード中…"},
    "Downloading update ({method})…": {
        "de": "Update wird heruntergeladen ({method})…",
        "es": "Descargando actualización ({method})…",
        "fr": "Téléchargement de la mise à jour ({method})…",
        "it": "Download dell'aggiornamento ({method})…",
        "ja": "アップデートをダウンロード中（{method}）…"},
    "Using your installed {name}.": {
        "de": "Dein installiertes {name} wird verwendet.",
        "es": "Usando tu {name} instalado.",
        "fr": "Utilisation de votre {name} installé.",
        "it": "Uso del tuo {name} installato.",
        "ja": "インストール済みの {name} を使用します。"},
    "Copied {n} row(s) to clipboard.": {
        "de": "{n} Zeile(n) in die Zwischenablage kopiert.",
        "es": "{n} fila(s) copiada(s) al portapapeles.",
        "fr": "{n} ligne(s) copiée(s) dans le presse-papiers.",
        "it": "{n} riga/e copiata/e negli appunti.",
        "ja": "{n} 行をクリップボードにコピーしました。"},
    "Copied: {value}": {
        "de": "Kopiert: {value}", "es": "Copiado: {value}", "fr": "Copié : {value}",
        "it": "Copiato: {value}", "ja": "コピーしました: {value}"},
    "Opened {n} link(s) in browser.": {
        "de": "{n} Link(s) im Browser geöffnet.",
        "es": "{n} enlace(s) abierto(s) en el navegador.",
        "fr": "{n} lien(s) ouvert(s) dans le navigateur.",
        "it": "{n} link aperti nel browser.",
        "ja": "{n} 件のリンクをブラウザで開きました。"},
    "Revealed {name} in Explorer.": {
        "de": "{name} im Explorer angezeigt.",
        "es": "{name} mostrado en el Explorador.",
        "fr": "{name} affiché dans l'Explorateur.",
        "it": "{name} mostrato in Esplora file.",
        "ja": "{name} をエクスプローラーで表示しました。"},
    "Cleared {n} 'unavailable' mark(s) — they will be retried next download.": {
        "de": "{n} „nicht verfügbar“-Markierung(en) entfernt — sie werden beim nächsten "
              "Download erneut versucht.",
        "es": "{n} marca(s) de «no disponible» eliminada(s): se reintentarán en la próxima "
              "descarga.",
        "fr": "{n} marque(s) « indisponible » effacée(s) — elles seront réessayées au "
              "prochain téléchargement.",
        "it": "{n} contrassegno/i «non disponibile» rimosso/i — verranno riprovati al "
              "prossimo download.",
        "ja": "{n} 件の「利用不可」の記録を消しました — 次回のダウンロードで再試行"
              "されます。"},
    "Added {tid}/{bid} ({n} cheat(s)).": {
        "de": "{tid}/{bid} hinzugefügt ({n} Cheat(s)).",
        "es": "Añadido {tid}/{bid} ({n} cheat(s)).",
        "fr": "{tid}/{bid} ajouté ({n} cheat(s)).",
        "it": "Aggiunto {tid}/{bid} ({n} cheat).",
        "ja": "{tid}/{bid} を追加しました（{n} 件のチート）。"},
    "Saved {tid}/{bid} ({n} cheat(s)).": {
        "de": "{tid}/{bid} gespeichert ({n} Cheat(s)).",
        "es": "Guardado {tid}/{bid} ({n} cheat(s)).",
        "fr": "{tid}/{bid} enregistré ({n} cheat(s)).",
        "it": "Salvato {tid}/{bid} ({n} cheat).",
        "ja": "{tid}/{bid} を保存しました（{n} 件のチート）。"},
    "Exported {n} row(s) to {dest}": {
        "de": "{n} Zeile(n) nach {dest} exportiert",
        "es": "{n} fila(s) exportada(s) a {dest}",
        "fr": "{n} ligne(s) exportée(s) vers {dest}",
        "it": "{n} riga/e esportata/e in {dest}",
        "ja": "{n} 行を {dest} にエクスポートしました"},
    "Database exported to {dest} ({size} MB)": {
        "de": "Datenbank nach {dest} exportiert ({size} MB)",
        "es": "Base de datos exportada a {dest} ({size} MB)",
        "fr": "Base de données exportée vers {dest} ({size} Mo)",
        "it": "Database esportato in {dest} ({size} MB)",
        "ja": "データベースを {dest} にエクスポートしました（{size} MB）"},
    "Entry updated": {
        "de": "Eintrag aktualisiert", "es": "Entrada actualizada",
        "fr": "Entrée mise à jour", "it": "Voce aggiornata", "ja": "エントリを更新しました"},
})

# ---- Tooltips --------------------------------------------------------------
_merge({
    "Skip scraping — grab all cheats and the complete database "
    "straight from the maintainer's GitHub. 'Download Cheats' = the "
    "ready-made cheat archive, 'Download Database' = the full GUI "
    "database (merged in), '★ Download Complete' = both. Tick "
    "'Download Covers' to also fetch the cover images.": {
        "de": "Ohne Scrapen — hole alle Cheats und die komplette Datenbank direkt vom "
              "GitHub des Betreuers. „Download Cheats“ = das fertige Cheat-Archiv, "
              "„Download Database“ = die vollständige GUI-Datenbank (wird eingefügt), "
              "„★ Download Complete“ = beides. Aktiviere „Download Covers“, um auch die "
              "Cover-Bilder zu holen.",
        "es": "Sin extraer: obtén todos los cheats y la base de datos completa directamente "
              "del GitHub del responsable. «Download Cheats» = el archivo de cheats ya "
              "preparado, «Download Database» = la base de datos completa de la GUI (se "
              "combina), «★ Download Complete» = ambos. Marca «Download Covers» para obtener "
              "también las carátulas.",
        "fr": "Sans extraction — récupérez tous les cheats et la base complète directement "
              "depuis le GitHub du mainteneur. « Download Cheats » = l'archive de cheats "
              "prête, « Download Database » = la base complète de l'interface (fusionnée), "
              "« ★ Download Complete » = les deux. Cochez « Download Covers » pour récupérer "
              "aussi les jaquettes.",
        "it": "Senza estrazione — prendi tutti i cheat e il database completo direttamente "
              "dal GitHub del manutentore. «Download Cheats» = l'archivio di cheat già "
              "pronto, «Download Database» = l'intero database della GUI (unito), "
              "«★ Download Complete» = entrambi. Spunta «Download Covers» per scaricare "
              "anche le copertine.",
        "ja": "取得なしで — メンテナの GitHub からすべてのチートと完全なデータベースを"
              "直接入手します。「Download Cheats」= 既製のチートアーカイブ、"
              "「Download Database」= GUI の完全なデータベース（統合）、"
              "「★ Download Complete」= 両方。「Download Covers」を有効にすると"
              "カバー画像も取得します。"},
    "When ON, each DevCatSKZ download also fetches the cover images "
    "afterwards. Off by default — covers are not part of the archive "
    "(the database stores only cover URLs) and downloading them takes "
    "extra time. Already-saved covers are skipped.": {
        "de": "Wenn aktiv, holt jeder DevCatSKZ-Download anschließend auch die "
              "Cover-Bilder. Standardmäßig aus — Cover sind nicht Teil des Archivs (die "
              "Datenbank speichert nur Cover-URLs) und das Herunterladen kostet extra Zeit. "
              "Bereits gespeicherte Cover werden übersprungen.",
        "es": "Si está activado, cada descarga de DevCatSKZ obtiene después también las "
              "carátulas. Desactivado por defecto: las carátulas no forman parte del archivo "
              "(la base de datos solo guarda las URLs) y descargarlas lleva tiempo extra. "
              "Las carátulas ya guardadas se omiten.",
        "fr": "Si activé, chaque téléchargement DevCatSKZ récupère ensuite aussi les "
              "jaquettes. Désactivé par défaut — les jaquettes ne font pas partie de "
              "l'archive (la base ne stocke que les URLs) et leur téléchargement prend du "
              "temps. Les jaquettes déjà enregistrées sont ignorées.",
        "it": "Se attivo, ogni download di DevCatSKZ scarica poi anche le copertine. "
              "Disattivato per impostazione predefinita — le copertine non fanno parte "
              "dell'archivio (il database memorizza solo gli URL) e scaricarle richiede "
              "tempo extra. Le copertine già salvate vengono saltate.",
        "ja": "オンにすると、DevCatSKZ の各ダウンロード後にカバー画像も取得します。"
              "既定ではオフ — カバーはアーカイブに含まれず（データベースはカバー URL のみ"
              "保存）、ダウンロードに追加の時間がかかります。保存済みのカバーはスキップ"
              "されます。"},
    "Check GitHub for a newer program build AND newer cheats/database "
    "packages. Detects both a new version (e.g. 1.1) and a re-upload "
    "of the current release/data (a fix without a version bump, via "
    "the upload date). Found program updates install themselves "
    "(the app restarts); data updates are downloaded and imported.": {
        "de": "Prüft GitHub auf einen neueren Programm-Build UND neuere "
              "Cheats-/Datenbank-Pakete. Erkennt sowohl eine neue Version (z. B. 1.1) als "
              "auch ein erneutes Hochladen des aktuellen Release/Daten (ein Fix ohne "
              "Versionssprung, über das Upload-Datum). Gefundene Programm-Updates "
              "installieren sich selbst (die App startet neu); Daten-Updates werden "
              "heruntergeladen und importiert.",
        "es": "Comprueba en GitHub si hay una versión más nueva del programa Y paquetes de "
              "cheats/base de datos más nuevos. Detecta tanto una versión nueva (p. ej. 1.1) "
              "como una resubida de la versión/datos actuales (una corrección sin cambio de "
              "versión, por la fecha de subida). Las actualizaciones de programa encontradas "
              "se instalan solas (la app se reinicia); las de datos se descargan e importan.",
        "fr": "Vérifie sur GitHub s'il existe une version plus récente du programme ET des "
              "paquets cheats/base plus récents. Détecte à la fois une nouvelle version "
              "(p. ex. 1.1) et un re-téléversement de la release/données actuelles (un "
              "correctif sans changement de version, via la date). Les mises à jour du "
              "programme trouvées s'installent seules (l'appli redémarre) ; celles des "
              "données sont téléchargées et importées.",
        "it": "Controlla su GitHub una build più recente del programma E pacchetti "
              "cheat/database più recenti. Rileva sia una nuova versione (es. 1.1) sia un "
              "nuovo caricamento della release/dati attuali (una correzione senza cambio di "
              "versione, tramite la data). Gli aggiornamenti del programma trovati si "
              "installano da soli (l'app si riavvia); quelli dei dati vengono scaricati e "
              "importati.",
        "ja": "GitHub で新しいプログラムビルドと新しいチート/データベースパッケージを"
              "確認します。新バージョン（例: 1.1）と、現在のリリース/データの再アップ"
              "ロード（アップロード日による、バージョンを上げない修正）の両方を検出します。"
              "見つかったプログラム更新は自動でインストールされ（アプリが再起動）、"
              "データ更新はダウンロードしてインポートされます。"},
    "ON: quietly check GitHub for updates at every program start and "
    "notify you if something is newer.\nOFF: only check when you click "
    "'Check Updates'.": {
        "de": "AN: prüft bei jedem Programmstart still GitHub auf Updates und benachrichtigt "
              "dich, wenn etwas neuer ist.\nAUS: prüft nur, wenn du auf „Auf Updates prüfen“ "
              "klickst.",
        "es": "ACT.: al iniciar el programa comprueba en silencio si hay actualizaciones en "
              "GitHub y te avisa si hay algo más nuevo.\nDESACT.: solo comprueba cuando "
              "pulsas «Buscar actualizaciones».",
        "fr": "ON : à chaque démarrage, vérifie discrètement les mises à jour sur GitHub et "
              "vous prévient si quelque chose est plus récent.\nOFF : vérifie uniquement "
              "quand vous cliquez sur « Vérifier les mises à jour ».",
        "it": "ON: a ogni avvio controlla silenziosamente gli aggiornamenti su GitHub e ti "
              "avvisa se c'è qualcosa di più recente.\nOFF: controlla solo quando fai clic "
              "su «Controlla aggiornamenti».",
        "ja": "オン: 起動のたびに GitHub の更新を静かに確認し、新しいものがあれば通知"
              "します。\nオフ:「アップデートを確認」をクリックしたときだけ確認します。"},
    "Download the maintainer's ready-made cheats archive and import "
    "it — all cheat files without scraping cheatslips yourself.": {
        "de": "Das fertige Cheats-Archiv des Betreuers herunterladen und importieren — alle "
              "Cheat-Dateien, ohne cheatslips selbst zu scrapen.",
        "es": "Descarga el archivo de cheats ya preparado del responsable e impórtalo: todos "
              "los archivos de cheats sin extraer cheatslips tú mismo.",
        "fr": "Télécharge l'archive de cheats prête du mainteneur et l'importe — tous les "
              "fichiers de cheats sans extraire cheatslips vous-même.",
        "it": "Scarica l'archivio di cheat già pronto del manutentore e lo importa — tutti "
              "i file di cheat senza estrarre cheatslips da solo.",
        "ja": "メンテナの既製チートアーカイブをダウンロードしてインポートします — "
              "cheatslips を自分で取得せずにすべてのチートファイルが手に入ります。"},
    "Download the maintainer's complete database (names, regions, "
    "versions, descriptions, cover URLs) and merge it into yours.": {
        "de": "Die vollständige Datenbank des Betreuers (Namen, Regionen, Versionen, "
              "Beschreibungen, Cover-URLs) herunterladen und in deine einfügen.",
        "es": "Descarga la base de datos completa del responsable (nombres, regiones, "
              "versiones, descripciones, URLs de carátulas) y la combina con la tuya.",
        "fr": "Télécharge la base complète du mainteneur (noms, régions, versions, "
              "descriptions, URLs de jaquettes) et la fusionne avec la vôtre.",
        "it": "Scarica il database completo del manutentore (nomi, regioni, versioni, "
              "descrizioni, URL delle copertine) e lo unisce al tuo.",
        "ja": "メンテナの完全なデータベース（名前・リージョン・バージョン・説明・"
              "カバー URL）をダウンロードして自分のものに統合します。"},
    "Download BOTH the cheats archive and the full database in one go "
    "— the fastest way to get everything. Tick 'Download Covers' "
    "below to fetch the cover images as well.": {
        "de": "SOWOHL das Cheats-Archiv ALS AUCH die vollständige Datenbank auf einmal "
              "herunterladen — der schnellste Weg, alles zu bekommen. Aktiviere unten "
              "„Download Covers“, um auch die Cover-Bilder zu holen.",
        "es": "Descarga TANTO el archivo de cheats COMO la base de datos completa de una "
              "vez: la forma más rápida de obtener todo. Marca «Download Covers» abajo para "
              "obtener también las carátulas.",
        "fr": "Télécharge À LA FOIS l'archive de cheats ET la base complète d'un coup — le "
              "moyen le plus rapide de tout obtenir. Cochez « Download Covers » ci-dessous "
              "pour récupérer aussi les jaquettes.",
        "it": "Scarica SIA l'archivio di cheat SIA l'intero database in una volta — il modo "
              "più veloce per avere tutto. Spunta «Download Covers» sotto per scaricare "
              "anche le copertine.",
        "ja": "チートアーカイブと完全なデータベースの両方を一度にダウンロード — "
              "すべてを手に入れる最速の方法です。下の「Download Covers」を有効にすると"
              "カバー画像も取得します。"},
    "Download the GBATemp/HamletDuFromage cheat archive, import all "
    "cheats (source=gbatemp), then fill names/region + titledb versions "
    "and recount from disk.": {
        "de": "Das GBATemp/HamletDuFromage-Cheat-Archiv herunterladen, alle Cheats "
              "importieren (source=gbatemp), dann Namen/Region + titledb-Versionen füllen "
              "und von der Festplatte neu zählen.",
        "es": "Descarga el archivo de cheats GBATemp/HamletDuFromage, importa todos los "
              "cheats (source=gbatemp), luego rellena nombres/región + versiones de titledb "
              "y recuenta desde el disco.",
        "fr": "Télécharge l'archive de cheats GBATemp/HamletDuFromage, importe tous les "
              "cheats (source=gbatemp), puis remplit noms/région + versions titledb et "
              "recompte depuis le disque.",
        "it": "Scarica l'archivio di cheat GBATemp/HamletDuFromage, importa tutti i cheat "
              "(source=gbatemp), poi riempie nomi/regione + versioni titledb e riconta dal "
              "disco.",
        "ja": "GBATemp/HamletDuFromage のチートアーカイブをダウンロードし、すべての"
              "チートをインポート（source=gbatemp）、その後 名前/リージョン + titledb "
              "バージョンを補完し、ディスクから再集計します。"},
    "Download HamletDuFromage's titles_complete.zip from the LATEST "
    "switch-cheats-db release (always the newest), import all cheats "
    "(source=hamlet-titledb), then fill names/region + titledb versions "
    "and recount from disk.": {
        "de": "HamletDuFromages titles_complete.zip aus dem NEUESTEN switch-cheats-db-Release "
              "(immer das aktuellste) herunterladen, alle Cheats importieren "
              "(source=hamlet-titledb), dann Namen/Region + titledb-Versionen füllen und von "
              "der Festplatte neu zählen.",
        "es": "Descarga titles_complete.zip de HamletDuFromage de la ÚLTIMA versión de "
              "switch-cheats-db (siempre la más reciente), importa todos los cheats "
              "(source=hamlet-titledb), luego rellena nombres/región + versiones de titledb "
              "y recuenta desde el disco.",
        "fr": "Télécharge le titles_complete.zip de HamletDuFromage depuis la DERNIÈRE "
              "release switch-cheats-db (toujours la plus récente), importe tous les cheats "
              "(source=hamlet-titledb), puis remplit noms/région + versions titledb et "
              "recompte depuis le disque.",
        "it": "Scarica titles_complete.zip di HamletDuFromage dall'ULTIMA release di "
              "switch-cheats-db (sempre la più recente), importa tutti i cheat "
              "(source=hamlet-titledb), poi riempie nomi/regione + versioni titledb e "
              "riconta dal disco.",
        "ja": "HamletDuFromage の titles_complete.zip を最新の switch-cheats-db リリース"
              "（常に最新）からダウンロードし、すべてのチートをインポート"
              "（source=hamlet-titledb）、その後 名前/リージョン + titledb バージョンを"
              "補完し、ディスクから再集計します。"},
    "Download HamletDuFromage's titles_60fps-res-gfx.zip (60 FPS / "
    "resolution / GFX cheats) from the LATEST switch-cheats-db release "
    "(always the newest), import all cheats (source=hamlet-60fps), then "
    "fill names/region + titledb versions and recount from disk.": {
        "de": "HamletDuFromages titles_60fps-res-gfx.zip (60 FPS / Auflösung / GFX-Cheats) "
              "aus dem NEUESTEN switch-cheats-db-Release (immer das aktuellste) "
              "herunterladen, alle Cheats importieren (source=hamlet-60fps), dann "
              "Namen/Region + titledb-Versionen füllen und von der Festplatte neu zählen.",
        "es": "Descarga titles_60fps-res-gfx.zip de HamletDuFromage (cheats de 60 FPS / "
              "resolución / GFX) de la ÚLTIMA versión de switch-cheats-db (siempre la más "
              "reciente), importa todos los cheats (source=hamlet-60fps), luego rellena "
              "nombres/región + versiones de titledb y recuenta desde el disco.",
        "fr": "Télécharge le titles_60fps-res-gfx.zip de HamletDuFromage (cheats 60 FPS / "
              "résolution / GFX) depuis la DERNIÈRE release switch-cheats-db (toujours la "
              "plus récente), importe tous les cheats (source=hamlet-60fps), puis remplit "
              "noms/région + versions titledb et recompte depuis le disque.",
        "it": "Scarica titles_60fps-res-gfx.zip di HamletDuFromage (cheat 60 FPS / "
              "risoluzione / GFX) dall'ULTIMA release di switch-cheats-db (sempre la più "
              "recente), importa tutti i cheat (source=hamlet-60fps), poi riempie "
              "nomi/regione + versioni titledb e riconta dal disco.",
        "ja": "HamletDuFromage の titles_60fps-res-gfx.zip（60FPS / 解像度 / GFX チート）"
              "を最新の switch-cheats-db リリース（常に最新）からダウンロードし、すべての"
              "チートをインポート（source=hamlet-60fps）、その後 名前/リージョン + titledb "
              "バージョンを補完し、ディスクから再集計します。"},
    "Download titles_complete.zip from the LATEST sthetix/nx-cheats-db "
    "release — a DAILY-updated aggregate of GBAtemp + graphics cheats + "
    "switch-cheats-db + cheatslips (~141k cheats). Import all cheats "
    "(source=sthetix), then fill names/region + versions + recount.": {
        "de": "titles_complete.zip aus dem NEUESTEN sthetix/nx-cheats-db-Release "
              "herunterladen — ein TÄGLICH aktualisiertes Aggregat aus GBAtemp + "
              "Grafik-Cheats + switch-cheats-db + cheatslips (~141k Cheats). Alle Cheats "
              "importieren (source=sthetix), dann Namen/Region + Versionen füllen + neu "
              "zählen.",
        "es": "Descarga titles_complete.zip de la ÚLTIMA versión de sthetix/nx-cheats-db — "
              "un agregado actualizado A DIARIO de GBAtemp + cheats gráficos + "
              "switch-cheats-db + cheatslips (~141k cheats). Importa todos los cheats "
              "(source=sthetix), luego rellena nombres/región + versiones + recuenta.",
        "fr": "Télécharge titles_complete.zip depuis la DERNIÈRE release sthetix/nx-cheats-db "
              "— un agrégat mis à jour QUOTIDIENNEMENT de GBAtemp + cheats graphiques + "
              "switch-cheats-db + cheatslips (~141k cheats). Importe tous les cheats "
              "(source=sthetix), puis remplit noms/région + versions + recompte.",
        "it": "Scarica titles_complete.zip dall'ULTIMA release di sthetix/nx-cheats-db — un "
              "aggregato aggiornato OGNI GIORNO di GBAtemp + cheat grafici + switch-cheats-db "
              "+ cheatslips (~141k cheat). Importa tutti i cheat (source=sthetix), poi "
              "riempie nomi/regione + versioni + riconta.",
        "ja": "最新の sthetix/nx-cheats-db リリースから titles_complete.zip をダウンロード "
              "— GBAtemp + グラフィックチート + switch-cheats-db + cheatslips を毎日更新した"
              "集約（約141kチート）。すべてのチートをインポート（source=sthetix）、その後 "
              "名前/リージョン + バージョンを補完 + 再集計します。"},
    "Download titles.zip (the Breeze/EdiZon-SE cheat database) from the "
    "LATEST tomvita/NXCheatCode release — GBAtemp community codes, partly "
    "different from cheatslips. Import (source=breeze), then fill "
    "names/region + versions + recount.": {
        "de": "titles.zip (die Breeze/EdiZon-SE-Cheat-Datenbank) aus dem NEUESTEN "
              "tomvita/NXCheatCode-Release herunterladen — GBAtemp-Community-Codes, teils "
              "anders als cheatslips. Importieren (source=breeze), dann Namen/Region + "
              "Versionen füllen + neu zählen.",
        "es": "Descarga titles.zip (la base de cheats Breeze/EdiZon-SE) de la ÚLTIMA versión "
              "de tomvita/NXCheatCode — códigos de la comunidad de GBAtemp, en parte "
              "distintos de cheatslips. Importa (source=breeze), luego rellena "
              "nombres/región + versiones + recuenta.",
        "fr": "Télécharge titles.zip (la base de cheats Breeze/EdiZon-SE) depuis la DERNIÈRE "
              "release tomvita/NXCheatCode — codes de la communauté GBAtemp, en partie "
              "différents de cheatslips. Importe (source=breeze), puis remplit noms/région + "
              "versions + recompte.",
        "it": "Scarica titles.zip (il database di cheat Breeze/EdiZon-SE) dall'ULTIMA "
              "release di tomvita/NXCheatCode — codici della community GBAtemp, in parte "
              "diversi da cheatslips. Importa (source=breeze), poi riempie nomi/regione + "
              "versioni + riconta.",
        "ja": "titles.zip（Breeze/EdiZon-SE のチートデータベース）を最新の "
              "tomvita/NXCheatCode リリースからダウンロード — GBAtemp コミュニティコード、"
              "cheatslips とは一部異なります。インポート（source=breeze）、その後 "
              "名前/リージョン + バージョンを補完 + 再集計します。"},
    "Import the LIVE ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats repo — the "
    "ORIGINAL source of the 60 FPS / resolution / graphics cheats, always "
    "current. Import (source=chansey-60fps), then fill names/region + "
    "versions + recount.": {
        "de": "Das LIVE-Repo ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats importieren — die "
              "ORIGINAL-Quelle der 60-FPS-/Auflösungs-/Grafik-Cheats, immer aktuell. "
              "Importieren (source=chansey-60fps), dann Namen/Region + Versionen füllen + "
              "neu zählen.",
        "es": "Importa el repo EN VIVO ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats — la fuente "
              "ORIGINAL de los cheats de 60 FPS / resolución / gráficos, siempre actual. "
              "Importa (source=chansey-60fps), luego rellena nombres/región + versiones + "
              "recuenta.",
        "fr": "Importe le dépôt EN DIRECT ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats — la "
              "source ORIGINALE des cheats 60 FPS / résolution / graphismes, toujours à "
              "jour. Importe (source=chansey-60fps), puis remplit noms/région + versions + "
              "recompte.",
        "it": "Importa il repo LIVE ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats — la fonte "
              "ORIGINALE dei cheat 60 FPS / risoluzione / grafica, sempre aggiornata. "
              "Importa (source=chansey-60fps), poi riempie nomi/regione + versioni + "
              "riconta.",
        "ja": "ライブリポジトリ ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats をインポート — "
              "60FPS / 解像度 / グラフィックチートの本家、常に最新。インポート"
              "（source=chansey-60fps）、その後 名前/リージョン + バージョンを補完 + "
              "再集計します。"},
    "Import the LIVE Arch9SK7/MyNXCheats repo — a curated collection for "
    "~50 recent big titles (TotK, Scarlet/Violet, ...). Import "
    "(source=mynxcheats), then fill names/region + versions + recount.": {
        "de": "Das LIVE-Repo Arch9SK7/MyNXCheats importieren — eine kuratierte Sammlung für "
              "~50 aktuelle große Titel (TotK, Karmesin/Purpur, …). Importieren "
              "(source=mynxcheats), dann Namen/Region + Versionen füllen + neu zählen.",
        "es": "Importa el repo EN VIVO Arch9SK7/MyNXCheats — una colección curada para ~50 "
              "grandes títulos recientes (TotK, Escarlata/Púrpura, ...). Importa "
              "(source=mynxcheats), luego rellena nombres/región + versiones + recuenta.",
        "fr": "Importe le dépôt EN DIRECT Arch9SK7/MyNXCheats — une collection sélectionnée "
              "pour ~50 grands titres récents (TotK, Écarlate/Violet, ...). Importe "
              "(source=mynxcheats), puis remplit noms/région + versions + recompte.",
        "it": "Importa il repo LIVE Arch9SK7/MyNXCheats — una raccolta curata per ~50 grandi "
              "titoli recenti (TotK, Scarlatto/Violetto, ...). Importa (source=mynxcheats), "
              "poi riempie nomi/regione + versioni + riconta.",
        "ja": "ライブリポジトリ Arch9SK7/MyNXCheats をインポート — 最近の大型タイトル"
              "約50本（TotK、スカーレット/バイオレットなど）向けの厳選コレクション。"
              "インポート（source=mynxcheats）、その後 名前/リージョン + バージョンを"
              "補完 + 再集計します。"},
    "Import titledb's own cheats.json as an extra source "
    "(source=titledb), then fill names/region + versions + recount.": {
        "de": "titledbs eigene cheats.json als zusätzliche Quelle importieren "
              "(source=titledb), dann Namen/Region + Versionen füllen + neu zählen.",
        "es": "Importa la propia cheats.json de titledb como fuente adicional "
              "(source=titledb), luego rellena nombres/región + versiones + recuenta.",
        "fr": "Importe le cheats.json propre à titledb comme source supplémentaire "
              "(source=titledb), puis remplit noms/région + versions + recompte.",
        "it": "Importa il cheats.json di titledb come fonte aggiuntiva (source=titledb), "
              "poi riempie nomi/regione + versioni + riconta.",
        "ja": "titledb 独自の cheats.json を追加ソースとしてインポート（source=titledb）、"
              "その後 名前/リージョン + バージョンを補完 + 再集計します。"},
    "Download the ibnux/switch-cheat archive and import its cheats "
    "(source=ibnux), then fill names/region + versions + recount.": {
        "de": "Das ibnux/switch-cheat-Archiv herunterladen und dessen Cheats importieren "
              "(source=ibnux), dann Namen/Region + Versionen füllen + neu zählen.",
        "es": "Descarga el archivo ibnux/switch-cheat e importa sus cheats (source=ibnux), "
              "luego rellena nombres/región + versiones + recuenta.",
        "fr": "Télécharge l'archive ibnux/switch-cheat et importe ses cheats (source=ibnux), "
              "puis remplit noms/région + versions + recompte.",
        "it": "Scarica l'archivio ibnux/switch-cheat e importa i suoi cheat (source=ibnux), "
              "poi riempie nomi/regione + versioni + riconta.",
        "ja": "ibnux/switch-cheat アーカイブをダウンロードしてそのチートをインポート"
              "（source=ibnux）、その後 名前/リージョン + バージョンを補完 + 再集計します。"},
    "Scan the output folder (titles/ and by_bid/) and import cheat "
    "files that aren't in the database yet (source=disk). No download.": {
        "de": "Den Ausgabeordner (titles/ und by_bid/) durchsuchen und Cheat-Dateien "
              "importieren, die noch nicht in der Datenbank sind (source=disk). Kein "
              "Download.",
        "es": "Analiza la carpeta de salida (titles/ y by_bid/) e importa los archivos de "
              "cheats que aún no están en la base de datos (source=disk). Sin descarga.",
        "fr": "Analyse le dossier de sortie (titles/ et by_bid/) et importe les fichiers de "
              "cheats absents de la base (source=disk). Aucun téléchargement.",
        "it": "Analizza la cartella di output (titles/ e by_bid/) e importa i file di cheat "
              "non ancora nel database (source=disk). Nessun download.",
        "ja": "出力フォルダ（titles/ と by_bid/）をスキャンし、まだデータベースにない"
              "チートファイルをインポートします（source=disk）。ダウンロードなし。"},
    "Import a cheat ZIP archive (e.g. one exported with 'Export to "
    "ZIP', or any Atmosphère/Breeze/EdiZon-layout archive) back into "
    "the database + output folder (source=import-zip).": {
        "de": "Ein Cheat-ZIP-Archiv (z. B. eines, das mit „Als ZIP exportieren“ erstellt "
              "wurde, oder ein beliebiges Archiv im Atmosphère-/Breeze-/EdiZon-Layout) "
              "zurück in die Datenbank + den Ausgabeordner importieren (source=import-zip).",
        "es": "Importa un archivo ZIP de cheats (p. ej. uno exportado con «Exportar a ZIP», "
              "o cualquier archivo con estructura Atmosphère/Breeze/EdiZon) de nuevo a la "
              "base de datos y la carpeta de salida (source=import-zip).",
        "fr": "Importe une archive ZIP de cheats (p. ex. une exportée avec « Exporter en "
              "ZIP », ou toute archive au format Atmosphère/Breeze/EdiZon) dans la base et "
              "le dossier de sortie (source=import-zip).",
        "it": "Importa un archivio ZIP di cheat (es. uno esportato con «Esporta in ZIP», o "
              "qualsiasi archivio con struttura Atmosphère/Breeze/EdiZon) di nuovo nel "
              "database + cartella di output (source=import-zip).",
        "ja": "チート ZIP アーカイブ（例:「ZIP にエクスポート」で書き出したもの、または "
              "Atmosphère/Breeze/EdiZon 形式の任意のアーカイブ）をデータベース + "
              "出力フォルダに戻してインポートします（source=import-zip）。"},
    "One click: cheatslips scrape (/entry feed) + ALL external "
    "archives (GBATemp, HamletDuFromage ×2, Sthetix, Breeze, Chansey, "
    "MyNXCheats, titledb, ibnux), then names/covers/region/versions, "
    "download all cheat files and covers. Long-running; Stop anytime.": {
        "de": "Ein Klick: cheatslips-Scrape (/entry-Feed) + ALLE externen Archive (GBATemp, "
              "HamletDuFromage ×2, Sthetix, Breeze, Chansey, MyNXCheats, titledb, ibnux), "
              "dann Namen/Cover/Region/Versionen, alle Cheat-Dateien und Cover "
              "herunterladen. Läuft lange; jederzeit stoppbar.",
        "es": "Un clic: extracción de cheatslips (feed /entry) + TODOS los archivos externos "
              "(GBATemp, HamletDuFromage ×2, Sthetix, Breeze, Chansey, MyNXCheats, titledb, "
              "ibnux), luego nombres/carátulas/región/versiones, descargar todos los cheats "
              "y carátulas. Tarda mucho; puedes detenerlo cuando quieras.",
        "fr": "Un clic : extraction cheatslips (flux /entry) + TOUTES les archives externes "
              "(GBATemp, HamletDuFromage ×2, Sthetix, Breeze, Chansey, MyNXCheats, titledb, "
              "ibnux), puis noms/jaquettes/région/versions, télécharger tous les cheats et "
              "jaquettes. Long ; arrêtez à tout moment.",
        "it": "Un clic: estrazione cheatslips (feed /entry) + TUTTI gli archivi esterni "
              "(GBATemp, HamletDuFromage ×2, Sthetix, Breeze, Chansey, MyNXCheats, titledb, "
              "ibnux), poi nomi/copertine/regione/versioni, scarica tutti i cheat e le "
              "copertine. Lungo; fermati quando vuoi.",
        "ja": "ワンクリック: cheatslips 取得（/entry フィード）+ すべての外部アーカイブ"
              "（GBATemp、HamletDuFromage ×2、Sthetix、Breeze、Chansey、MyNXCheats、titledb、"
              "ibnux）、その後 名前/カバー/リージョン/バージョン、すべてのチートファイルと"
              "カバーをダウンロード。長時間実行。いつでも停止可能。"},
    "Fill missing game names + covers + metadata from titledb regions, "
    "then the CheatSlips API, switchbrew, tinfoil, GitHub lists and "
    "finally by inheriting from the base game.": {
        "de": "Fehlende Spielnamen + Cover + Metadaten aus titledb-Regionen füllen, dann "
              "über die CheatSlips-API, switchbrew, tinfoil, GitHub-Listen und schließlich "
              "durch Vererbung vom Basisspiel.",
        "es": "Rellena nombres de juego + carátulas + metadatos que faltan desde las "
              "regiones de titledb, luego la API de CheatSlips, switchbrew, tinfoil, listas "
              "de GitHub y, por último, heredando del juego base.",
        "fr": "Complète les noms de jeux + jaquettes + métadonnées manquants depuis les "
              "régions titledb, puis l'API CheatSlips, switchbrew, tinfoil, les listes "
              "GitHub et enfin par héritage du jeu de base.",
        "it": "Riempie nomi di gioco + copertine + metadati mancanti dalle regioni titledb, "
              "poi dall'API CheatSlips, switchbrew, tinfoil, elenchi GitHub e infine "
              "ereditando dal gioco base.",
        "ja": "不足しているゲーム名 + カバー + メタデータを titledb のリージョンから"
              "補完し、続いて CheatSlips API、switchbrew、tinfoil、GitHub のリスト、"
              "最後にベースゲームからの継承で補います。"},
    "Tag every title with its eShop region(s) (US/EU/AU/JP/KR/HK) "
    "from the titledb region files.": {
        "de": "Jeden Titel mit seiner/seinen eShop-Region(en) (US/EU/AU/JP/KR/HK) aus den "
              "titledb-Regionsdateien kennzeichnen.",
        "es": "Etiqueta cada título con su(s) región(es) de eShop (US/EU/AU/JP/KR/HK) desde "
              "los archivos de región de titledb.",
        "fr": "Étiquette chaque titre avec sa/ses région(s) eShop (US/EU/AU/JP/KR/HK) à "
              "partir des fichiers de région titledb.",
        "it": "Contrassegna ogni titolo con la/le regione/i eShop (US/EU/AU/JP/KR/HK) dai "
              "file di regione di titledb.",
        "ja": "各タイトルに titledb のリージョンファイルから eShop リージョン"
              "（US/EU/AU/JP/KR/HK）を付与します。"},
    "Fill build versions from titledb only (builds.json / "
    "versions.json) — fast, no cheatslips.": {
        "de": "Build-Versionen nur aus titledb füllen (builds.json / versions.json) — "
              "schnell, kein cheatslips.",
        "es": "Rellena las versiones de build solo desde titledb (builds.json / "
              "versions.json): rápido, sin cheatslips.",
        "fr": "Complète les versions de build depuis titledb uniquement (builds.json / "
              "versions.json) — rapide, sans cheatslips.",
        "it": "Riempie le versioni di build solo da titledb (builds.json / versions.json) — "
              "veloce, senza cheatslips.",
        "ja": "ビルドのバージョンを titledb のみ（builds.json / versions.json）から"
              "補完します — 高速、cheatslips 不要。"},
    "Fill the remaining build versions from cheatslips' game pages "
    "(HTML) — slower; only needed for builds titledb doesn't cover.": {
        "de": "Die restlichen Build-Versionen aus cheatslips' Spielseiten (HTML) füllen — "
              "langsamer; nur nötig für Builds, die titledb nicht abdeckt.",
        "es": "Rellena las versiones de build restantes desde las páginas de juego de "
              "cheatslips (HTML): más lento; solo hace falta para builds que titledb no "
              "cubre.",
        "fr": "Complète les versions de build restantes depuis les pages de jeu de "
              "cheatslips (HTML) — plus lent ; nécessaire seulement pour les builds que "
              "titledb ne couvre pas.",
        "it": "Riempie le versioni di build rimanenti dalle pagine di gioco di cheatslips "
              "(HTML) — più lento; serve solo per le build non coperte da titledb.",
        "ja": "残りのビルドバージョンを cheatslips のゲームページ（HTML）から補完します "
              "— 低速。titledb が対象外のビルドにのみ必要です。"},
    "Fill missing game descriptions + intro texts for all titles from "
    "titledb (English regions). Downloads/caches the region files.": {
        "de": "Fehlende Spielbeschreibungen + Introtexte für alle Titel aus titledb "
              "(englische Regionen) füllen. Lädt/cacht die Regionsdateien.",
        "es": "Rellena las descripciones + textos de introducción que faltan para todos los "
              "títulos desde titledb (regiones en inglés). Descarga/almacena en caché los "
              "archivos de región.",
        "fr": "Complète les descriptions + textes d'intro manquants pour tous les titres "
              "depuis titledb (régions anglaises). Télécharge/met en cache les fichiers de "
              "région.",
        "it": "Riempie le descrizioni + testi introduttivi mancanti per tutti i titoli da "
              "titledb (regioni in inglese). Scarica/memorizza nella cache i file di "
              "regione.",
        "ja": "すべてのタイトルの不足している説明文 + 紹介文を titledb（英語リージョン）"
              "から補完します。リージョンファイルをダウンロード/キャッシュします。"},
    "Download the cover images of all database entries to "
    "coversdownload/ (already-saved covers are skipped).": {
        "de": "Die Cover-Bilder aller Datenbankeinträge nach coversdownload/ herunterladen "
              "(bereits gespeicherte Cover werden übersprungen).",
        "es": "Descarga las carátulas de todas las entradas de la base de datos a "
              "coversdownload/ (las ya guardadas se omiten).",
        "fr": "Télécharge les jaquettes de toutes les entrées de la base vers "
              "coversdownload/ (les jaquettes déjà enregistrées sont ignorées).",
        "it": "Scarica le copertine di tutte le voci del database in coversdownload/ (le "
              "copertine già salvate vengono saltate).",
        "ja": "すべてのデータベースエントリのカバー画像を coversdownload/ に"
              "ダウンロードします（保存済みのカバーはスキップされます）。"},
    "Whether cheatslips.com is currently reachable — green = online, "
    "red = offline. Checked at program start (if enabled) and via "
    "'Check Online'.": {
        "de": "Ob cheatslips.com derzeit erreichbar ist — grün = online, rot = offline. "
              "Wird beim Programmstart (falls aktiviert) und über „Online prüfen“ geprüft.",
        "es": "Si cheatslips.com está accesible ahora mismo: verde = en línea, rojo = sin "
              "conexión. Se comprueba al iniciar el programa (si está activado) y con "
              "«Comprobar conexión».",
        "fr": "Indique si cheatslips.com est actuellement joignable — vert = en ligne, "
              "rouge = hors ligne. Vérifié au démarrage (si activé) et via « Vérifier la "
              "connexion ».",
        "it": "Se cheatslips.com è attualmente raggiungibile — verde = online, rosso = "
              "offline. Controllato all'avvio del programma (se abilitato) e con «Verifica "
              "online».",
        "ja": "cheatslips.com に現在アクセスできるか — 緑 = オンライン、赤 = オフライン。"
              "起動時（有効な場合）と「オンライン確認」で確認します。"},
    "Check right now whether cheatslips.com is online. Works any "
    "time, even while a download or scrape is running.": {
        "de": "Jetzt prüfen, ob cheatslips.com online ist. Funktioniert jederzeit, auch "
              "während ein Download oder Scrape läuft.",
        "es": "Comprueba ahora mismo si cheatslips.com está en línea. Funciona en cualquier "
              "momento, incluso mientras se ejecuta una descarga o extracción.",
        "fr": "Vérifie immédiatement si cheatslips.com est en ligne. Fonctionne à tout "
              "moment, même pendant un téléchargement ou une extraction.",
        "it": "Controlla subito se cheatslips.com è online. Funziona in qualsiasi momento, "
              "anche mentre è in corso un download o un'estrazione.",
        "ja": "cheatslips.com がオンラインか今すぐ確認します。ダウンロードや取得の実行中"
              "でも、いつでも動作します。"},
    "ON: automatically check whether cheatslips.com is online at "
    "every program start.\nOFF: no automatic check (use the "
    "'Check Online' button instead).": {
        "de": "AN: bei jedem Programmstart automatisch prüfen, ob cheatslips.com online "
              "ist.\nAUS: keine automatische Prüfung (nutze stattdessen den Button „Online "
              "prüfen“).",
        "es": "ACT.: comprueba automáticamente si cheatslips.com está en línea en cada "
              "inicio del programa.\nDESACT.: sin comprobación automática (usa el botón "
              "«Comprobar conexión»).",
        "fr": "ON : vérifie automatiquement si cheatslips.com est en ligne à chaque "
              "démarrage.\nOFF : pas de vérification automatique (utilisez le bouton "
              "« Vérifier la connexion »).",
        "it": "ON: controlla automaticamente se cheatslips.com è online a ogni avvio del "
              "programma.\nOFF: nessun controllo automatico (usa il pulsante «Verifica "
              "online»).",
        "ja": "オン: 起動のたびに cheatslips.com がオンラインかを自動で確認します。\n"
              "オフ: 自動確認なし（代わりに「オンライン確認」ボタンを使用）。"},
    "One-time cheatslips login in the embedded browser: your "
    "email/password are pre-filled, you only solve the reCAPTCHA. "
    "The session cookies are saved to the persistent profile, so "
    "every future browser download / quota reset logs in "
    "automatically — you never have to log in again.": {
        "de": "Einmaliger cheatslips-Login im eingebetteten Browser: deine "
              "E-Mail/dein Passwort sind vorausgefüllt, du löst nur das reCAPTCHA. Die "
              "Sitzungs-Cookies werden im dauerhaften Profil gespeichert, sodass sich jeder "
              "zukünftige Browser-Download / jede Kontingent-Rücksetzung automatisch "
              "anmeldet — du musst dich nie wieder anmelden.",
        "es": "Inicio de sesión único en cheatslips en el navegador integrado: tu "
              "correo/contraseña se rellenan automáticamente, solo resuelves el reCAPTCHA. "
              "Las cookies de sesión se guardan en el perfil persistente, así cada futura "
              "descarga por navegador / reinicio de cuota inicia sesión sola: no tendrás que "
              "volver a entrar.",
        "fr": "Connexion cheatslips unique dans le navigateur intégré : votre "
              "e-mail/mot de passe sont pré-remplis, vous ne résolvez que le reCAPTCHA. Les "
              "cookies de session sont enregistrés dans le profil persistant, ainsi chaque "
              "futur téléchargement / réinitialisation de quota se connecte automatiquement "
              "— vous n'avez plus jamais à vous connecter.",
        "it": "Accesso a cheatslips una tantum nel browser integrato: la tua "
              "e-mail/password sono precompilate, risolvi solo il reCAPTCHA. I cookie di "
              "sessione vengono salvati nel profilo persistente, così ogni futuro download "
              "dal browser / reset della quota accede automaticamente — non dovrai più "
              "accedere.",
        "ja": "組み込みブラウザでの一度きりの cheatslips ログイン: メール/パスワードは"
              "自動入力され、reCAPTCHA を解くだけです。セッション Cookie は永続プロファイル"
              "に保存されるため、今後のブラウザダウンロード / クォータリセットは自動で"
              "ログインします — 二度とログインする必要はありません。"},
    "Scrape cheat metadata from cheatslips.com (Title/Build IDs, names, "
    "cheat names). With a valid token the cheat files are saved in the "
    "same pass.": {
        "de": "Cheat-Metadaten von cheatslips.com scrapen (Title-/Build-IDs, Namen, "
              "Cheat-Namen). Mit gültigem Token werden die Cheat-Dateien im selben Durchgang "
              "gespeichert.",
        "es": "Extrae los metadatos de cheats de cheatslips.com (Title/Build IDs, nombres, "
              "nombres de cheats). Con un token válido, los archivos de cheats se guardan en "
              "la misma pasada.",
        "fr": "Extrait les métadonnées des cheats de cheatslips.com (Title/Build IDs, noms, "
              "noms des cheats). Avec un token valide, les fichiers de cheats sont "
              "enregistrés dans la même passe.",
        "it": "Estrae i metadati dei cheat da cheatslips.com (Title/Build ID, nomi, nomi "
              "dei cheat). Con un token valido i file di cheat vengono salvati nella stessa "
              "passata.",
        "ja": "cheatslips.com からチートのメタデータ（Title/Build ID、名前、チート名）を"
              "取得します。有効なトークンがあれば、同じ処理でチートファイルも保存されます。"},
    "Only scan the newest 'latest cheats' pages (set 'pages') to pick up "
    "recently added/updated cheats — much faster than a full scrape.": {
        "de": "Nur die neuesten „latest cheats“-Seiten scannen („Seiten“ einstellen), um "
              "kürzlich hinzugefügte/aktualisierte Cheats zu erfassen — viel schneller als "
              "ein vollständiger Scrape.",
        "es": "Analiza solo las páginas más recientes de «latest cheats» (ajusta "
              "«páginas») para captar los cheats añadidos/actualizados recientemente: mucho "
              "más rápido que una extracción completa.",
        "fr": "Analyse uniquement les pages « latest cheats » les plus récentes (réglez "
              "« pages ») pour récupérer les cheats récemment ajoutés/mis à jour — bien plus "
              "rapide qu'une extraction complète.",
        "it": "Analizza solo le pagine più recenti «latest cheats» (imposta «pagine») per "
              "rilevare i cheat aggiunti/aggiornati di recente — molto più veloce di "
              "un'estrazione completa.",
        "ja": "最新の「latest cheats」ページのみをスキャン（「ページ」を設定）して、"
              "最近追加/更新されたチートを取得します — 完全な取得よりずっと高速です。"},
    "ON: scan the COMPLETE cheatslips catalog (~29k games) — slower.\n"
    "OFF: use the fast /entry 'latest cheats' feed (~1900 games). Both find "
    "the same cheat-having builds.": {
        "de": "AN: den KOMPLETTEN cheatslips-Katalog scannen (~29k Spiele) — langsamer.\n"
              "AUS: den schnellen /entry-„latest cheats“-Feed nutzen (~1900 Spiele). Beide "
              "finden dieselben Builds mit Cheats.",
        "es": "ACT.: analiza el catálogo COMPLETO de cheatslips (~29k juegos): más lento.\n"
              "DESACT.: usa el feed rápido /entry «latest cheats» (~1900 juegos). Ambos "
              "encuentran los mismos builds con cheats.",
        "fr": "ON : analyse le catalogue COMPLET de cheatslips (~29k jeux) — plus lent.\n"
              "OFF : utilise le flux rapide /entry « latest cheats » (~1900 jeux). Les deux "
              "trouvent les mêmes builds avec cheats.",
        "it": "ON: analizza il catalogo COMPLETO di cheatslips (~29k giochi) — più lento.\n"
              "OFF: usa il veloce feed /entry «latest cheats» (~1900 giochi). Entrambi "
              "trovano le stesse build con cheat.",
        "ja": "オン: cheatslips の全カタログ（約29kゲーム）をスキャン — 低速。\n"
              "オフ: 高速な /entry「latest cheats」フィード（約1900ゲーム）を使用。"
              "どちらも同じチートありビルドを見つけます。"},
    "ON: drop builds that show 0 cheats during the scrape.\n"
    "OFF (default): keep them, so nothing is hidden and 0-cheat builds stay "
    "visible under 'Not downloaded'.": {
        "de": "AN: Builds verwerfen, die beim Scrape 0 Cheats zeigen.\nAUS (Standard): sie "
              "behalten, damit nichts verborgen wird und 0-Cheat-Builds unter „Nicht "
              "heruntergeladen“ sichtbar bleiben.",
        "es": "ACT.: descarta los builds que muestran 0 cheats durante la extracción.\n"
              "DESACT. (predet.): consérvalos, así no se oculta nada y los builds con 0 "
              "cheats siguen visibles en «No descargados».",
        "fr": "ON : abandonne les builds affichant 0 cheat pendant l'extraction.\nOFF "
              "(défaut) : les conserve, ainsi rien n'est masqué et les builds à 0 cheat "
              "restent visibles sous « Non téléchargés ».",
        "it": "ON: scarta le build che mostrano 0 cheat durante l'estrazione.\nOFF "
              "(predefinito): le mantiene, così nulla viene nascosto e le build con 0 cheat "
              "restano visibili in «Non scaricati».",
        "ja": "オン: 取得中にチート0件と表示されるビルドを除外します。\nオフ（既定）: "
              "残すので何も隠されず、チート0件のビルドは「未ダウンロード」に表示された"
              "ままになります。"},
    "ON: re-scrape games that are already in the database.\n"
    "OFF: skip known games (much faster incremental scan).": {
        "de": "AN: Spiele, die bereits in der Datenbank sind, erneut scrapen.\nAUS: bekannte "
              "Spiele überspringen (viel schnellerer inkrementeller Scan).",
        "es": "ACT.: vuelve a extraer los juegos que ya están en la base de datos.\n"
              "DESACT.: omite los juegos conocidos (análisis incremental mucho más rápido).",
        "fr": "ON : ré-extrait les jeux déjà présents dans la base.\nOFF : ignore les jeux "
              "connus (analyse incrémentale bien plus rapide).",
        "it": "ON: riesegue l'estrazione dei giochi già nel database.\nOFF: salta i giochi "
              "noti (scansione incrementale molto più veloce).",
        "ja": "オン: すでにデータベースにあるゲームを再取得します。\nオフ: 既知のゲームを"
              "スキップ（はるかに高速な増分スキャン）。"},
    "ON: right after the scrape finishes, automatically start downloading "
    "the cheat files.": {
        "de": "AN: direkt nach dem Scrape automatisch mit dem Herunterladen der "
              "Cheat-Dateien beginnen.",
        "es": "ACT.: justo después de terminar la extracción, empieza a descargar "
              "automáticamente los archivos de cheats.",
        "fr": "ON : juste après la fin de l'extraction, démarre automatiquement le "
              "téléchargement des fichiers de cheats.",
        "it": "ON: subito dopo la fine dell'estrazione, avvia automaticamente il download "
              "dei file di cheat.",
        "ja": "オン: 取得の完了直後に、チートファイルのダウンロードを自動的に開始します。"},
    "Browser used for login / quota reset. Built-in Chromium ships "
    "with the app. Firefox is downloaded on demand into your data "
    "folder (no admin). Chrome uses your installed Google Chrome.": {
        "de": "Browser für Login / Kontingent-Rücksetzung. Das eingebaute Chromium wird mit "
              "der App geliefert. Firefox wird bei Bedarf in deinen Datenordner "
              "heruntergeladen (keine Admin-Rechte). Chrome nutzt dein installiertes Google "
              "Chrome.",
        "es": "Navegador para el inicio de sesión / reinicio de cuota. El Chromium "
              "integrado viene con la app. Firefox se descarga bajo demanda en tu carpeta de "
              "datos (sin admin). Chrome usa tu Google Chrome instalado.",
        "fr": "Navigateur utilisé pour la connexion / réinitialisation du quota. Le Chromium "
              "intégré est fourni avec l'appli. Firefox est téléchargé à la demande dans "
              "votre dossier de données (sans admin). Chrome utilise votre Google Chrome "
              "installé.",
        "it": "Browser usato per login / reset della quota. Il Chromium integrato è incluso "
              "nell'app. Firefox viene scaricato su richiesta nella tua cartella dati (senza "
              "admin). Chrome usa il tuo Google Chrome installato.",
        "ja": "ログイン / クォータリセットに使うブラウザ。内蔵の Chromium はアプリに"
              "同梱されています。Firefox は必要に応じてデータフォルダにダウンロードされます"
              "（管理者不要）。Chrome はインストール済みの Google Chrome を使用します。"},
    "Open the browser and click cheatslips' 'reset my quota' once. "
    "Resets the WEBSITE download limit (helps browser downloads), NOT "
    "the API daily quota.": {
        "de": "Den Browser öffnen und einmal auf cheatslips' „reset my quota“ klicken. "
              "Setzt das WEBSITE-Download-Limit zurück (hilft bei Browser-Downloads), NICHT "
              "das tägliche API-Kontingent.",
        "es": "Abre el navegador y pulsa una vez «reset my quota» de cheatslips. Restablece "
              "el límite de descargas del SITIO WEB (ayuda a las descargas por navegador), "
              "NO la cuota diaria de la API.",
        "fr": "Ouvre le navigateur et clique une fois sur « reset my quota » de cheatslips. "
              "Réinitialise la limite de téléchargement du SITE (utile pour les "
              "téléchargements navigateur), PAS le quota quotidien de l'API.",
        "it": "Apre il browser e fa clic una volta su «reset my quota» di cheatslips. "
              "Reimposta il limite di download del SITO WEB (utile per i download dal "
              "browser), NON la quota giornaliera dell'API.",
        "ja": "ブラウザを開いて cheatslips の「reset my quota」を一度クリックします。"
              "ウェブサイトのダウンロード制限をリセットします（ブラウザダウンロードに"
              "有効）。API の日次クォータはリセットしません。"},
    "Download cheat files via the official API ONLY (never the browser). "
    "Uses the selected rows, or ALL games if nothing is selected. "
    "Stops when the API daily quota is hit.": {
        "de": "Cheat-Dateien NUR über die offizielle API herunterladen (nie den Browser). "
              "Nutzt die ausgewählten Zeilen oder ALLE Spiele, wenn nichts ausgewählt ist. "
              "Stoppt, wenn das tägliche API-Kontingent erreicht ist.",
        "es": "Descarga los cheats SOLO por la API oficial (nunca el navegador). Usa las "
              "filas seleccionadas o TODOS los juegos si no hay selección. Se detiene al "
              "alcanzar la cuota diaria de la API.",
        "fr": "Télécharge les cheats UNIQUEMENT via l'API officielle (jamais le navigateur). "
              "Utilise les lignes sélectionnées, ou TOUS les jeux si rien n'est sélectionné. "
              "S'arrête quand le quota quotidien de l'API est atteint.",
        "it": "Scarica i cheat SOLO tramite l'API ufficiale (mai il browser). Usa le righe "
              "selezionate, o TUTTI i giochi se non è selezionato nulla. Si ferma al "
              "raggiungimento della quota giornaliera dell'API.",
        "ja": "チートを公式 API のみでダウンロード（ブラウザは使いません）。選択した行、"
              "または何も選択されていなければ全ゲームを対象にします。API の日次クォータに"
              "達すると停止します。"},
    "Download the SELECTED rows. Uses the API and — if 'Download via "
    "browser when API is limited' is ticked — falls back to the browser "
    "for whatever the API can't deliver.": {
        "de": "Die AUSGEWÄHLTEN Zeilen herunterladen. Nutzt die API und — wenn „Bei "
              "API-Limit über den Browser herunterladen“ aktiv ist — greift für alles, was "
              "die API nicht liefert, auf den Browser zurück.",
        "es": "Descarga las filas SELECCIONADAS. Usa la API y —si «Descargar por navegador "
              "cuando la API está limitada» está marcado— recurre al navegador para lo que "
              "la API no pueda entregar.",
        "fr": "Télécharge les lignes SÉLECTIONNÉES. Utilise l'API et — si « Télécharger via "
              "le navigateur quand l'API est limitée » est coché — bascule sur le navigateur "
              "pour ce que l'API ne peut pas fournir.",
        "it": "Scarica le righe SELEZIONATE. Usa l'API e — se «Scarica dal browser quando "
              "l'API è limitata» è spuntato — ripiega sul browser per ciò che l'API non può "
              "fornire.",
        "ja": "選択した行をダウンロードします。API を使い、「API制限時はブラウザで"
              "ダウンロード」が有効なら、API が取得できない分はブラウザにフォールバック"
              "します。"},
    "Download via the logged-in browser directly (bypass the API limit). "
    "Uses the selected rows, or ALL still-missing builds if nothing is "
    "selected. Resets the website quota automatically; uses the chosen "
    "Browser. Fetches all source pages of a build and merges them.": {
        "de": "Direkt über den angemeldeten Browser herunterladen (API-Limit umgehen). "
              "Nutzt die ausgewählten Zeilen oder ALLE noch fehlenden Builds, wenn nichts "
              "ausgewählt ist. Setzt das Website-Kontingent automatisch zurück; nutzt den "
              "gewählten Browser. Holt alle Quellseiten eines Builds und führt sie zusammen.",
        "es": "Descarga directamente por el navegador con sesión iniciada (evita el límite "
              "de la API). Usa las filas seleccionadas o TODOS los builds que aún faltan si "
              "no hay selección. Restablece la cuota del sitio automáticamente; usa el "
              "navegador elegido. Obtiene todas las páginas de origen de un build y las "
              "combina.",
        "fr": "Télécharge directement via le navigateur connecté (contourne la limite API). "
              "Utilise les lignes sélectionnées, ou TOUS les builds encore manquants si rien "
              "n'est sélectionné. Réinitialise le quota du site automatiquement ; utilise le "
              "navigateur choisi. Récupère toutes les pages source d'un build et les fusionne.",
        "it": "Scarica direttamente dal browser con l'accesso effettuato (aggira il limite "
              "API). Usa le righe selezionate, o TUTTE le build ancora mancanti se non è "
              "selezionato nulla. Reimposta la quota del sito automaticamente; usa il "
              "browser scelto. Recupera tutte le pagine di origine di una build e le unisce.",
        "ja": "ログイン済みのブラウザで直接ダウンロード（API制限を回避）。選択した行、"
              "または何も選択されていなければまだ不足しているすべてのビルドを対象にします。"
              "ウェブサイトのクォータを自動でリセットし、選択したブラウザを使用します。"
              "ビルドのすべてのソースページを取得して統合します。"},
    "Build the COMPLETE dataset for ALL games: download every cheat "
    "file (API + optional browser fallback), then fill names/region/"
    "versions, fix ID names and fix 0-cheat entries.": {
        "de": "Den KOMPLETTEN Datensatz für ALLE Spiele erstellen: jede Cheat-Datei "
              "herunterladen (API + optionaler Browser-Fallback), dann Namen/Region/"
              "Versionen füllen, ID-Namen korrigieren und Einträge mit 0 Cheats korrigieren.",
        "es": "Crea el conjunto de datos COMPLETO para TODOS los juegos: descarga cada "
              "archivo de cheats (API + navegador opcional de reserva), luego rellena "
              "nombres/región/versiones, corrige nombres de ID y entradas con 0 cheats.",
        "fr": "Construit le jeu de données COMPLET pour TOUS les jeux : télécharge chaque "
              "fichier de cheats (API + navigateur de secours optionnel), puis remplit "
              "noms/région/versions, corrige les noms d'ID et les entrées à 0 cheat.",
        "it": "Costruisce il dataset COMPLETO per TUTTI i giochi: scarica ogni file di cheat "
              "(API + browser di riserva opzionale), poi riempie nomi/regione/versioni, "
              "corregge i nomi ID e le voci con 0 cheat.",
        "ja": "すべてのゲームの完全なデータセットを構築: すべてのチートファイルを"
              "ダウンロード（API + 任意のブラウザフォールバック）、その後 名前/リージョン/"
              "バージョンを補完し、ID 名とチート0件のエントリを修正します。"},
    "Switch between dark and light mode (saved between runs).": {
        "de": "Zwischen dunklem und hellem Modus wechseln (wird zwischen Sitzungen "
              "gespeichert).",
        "es": "Cambia entre modo oscuro y claro (se guarda entre sesiones).",
        "fr": "Basculer entre le mode sombre et clair (conservé entre les sessions).",
        "it": "Passa tra tema scuro e chiaro (salvato tra le sessioni).",
        "ja": "ダークモードとライトモードを切り替えます（実行間で保存されます）。"},
    "Choose the program language. The app restarts to apply it.": {
        "de": "Die Programmsprache wählen. Die App startet neu, um sie anzuwenden.",
        "es": "Elige el idioma del programa. La app se reinicia para aplicarlo.",
        "fr": "Choisir la langue du programme. L'appli redémarre pour l'appliquer.",
        "it": "Scegli la lingua del programma. L'app si riavvia per applicarla.",
        "ja": "プログラムの言語を選択します。適用のためアプリが再起動します。"},
    "Import a previously exported database (.db). Merge it into the "
    "current database (nothing removed) or replace the current one "
    "entirely (a backup is made first).": {
        "de": "Eine zuvor exportierte Datenbank (.db) importieren. In die aktuelle Datenbank "
              "einfügen (nichts wird entfernt) oder die aktuelle vollständig ersetzen (zuvor "
              "wird ein Backup erstellt).",
        "es": "Importa una base de datos exportada previamente (.db). Combínala con la base "
              "actual (no se elimina nada) o reemplaza por completo la actual (antes se hace "
              "una copia de seguridad).",
        "fr": "Importe une base de données précédemment exportée (.db). Fusionnez-la avec la "
              "base actuelle (rien n'est supprimé) ou remplacez entièrement l'actuelle (une "
              "sauvegarde est faite d'abord).",
        "it": "Importa un database esportato in precedenza (.db). Uniscilo al database "
              "attuale (nulla viene rimosso) o sostituisci completamente quello attuale "
              "(prima viene fatto un backup).",
        "ja": "以前にエクスポートしたデータベース（.db）をインポートします。現在の"
              "データベースに統合（何も削除しない）するか、現在のものを完全に置き換え"
              "ます（先にバックアップを作成）。"},
    "Copy the downloaded cheat files onto a Switch SD card in the "
    "layout Atmosphère / Breeze / EdiZon expects. Auto-detects the "
    "card; skips empty/stub files; merges with existing SD cheats.": {
        "de": "Die heruntergeladenen Cheat-Dateien im von Atmosphère / Breeze / EdiZon "
              "erwarteten Layout auf eine Switch-SD-Karte kopieren. Erkennt die Karte "
              "automatisch; überspringt leere/Platzhalter-Dateien; führt mit vorhandenen "
              "SD-Cheats zusammen.",
        "es": "Copia los archivos de cheats descargados a una tarjeta SD de Switch con la "
              "estructura que esperan Atmosphère / Breeze / EdiZon. Detecta la tarjeta "
              "automáticamente; omite archivos vacíos o de relleno; se combina con los "
              "cheats existentes en la SD.",
        "fr": "Copie les fichiers de cheats téléchargés sur une carte SD Switch dans la "
              "structure attendue par Atmosphère / Breeze / EdiZon. Détecte la carte "
              "automatiquement ; ignore les fichiers vides/fictifs ; fusionne avec les "
              "cheats déjà présents sur la SD.",
        "it": "Copia i file di cheat scaricati su una scheda SD della Switch nella struttura "
              "attesa da Atmosphère / Breeze / EdiZon. Rileva la scheda automaticamente; "
              "salta i file vuoti/segnaposto; unisce ai cheat già presenti sulla SD.",
        "ja": "ダウンロード済みのチートファイルを、Atmosphère / Breeze / EdiZon が期待する"
              "レイアウトで Switch の SD カードにコピーします。カードを自動検出し、"
              "空/スタブのファイルをスキップし、SD 上の既存チートと統合します。"},
    "Export all downloaded cheats into a ZIP with the SD-card layout "
    "(Atmosphère / Breeze / EdiZon). Unzip it onto the SD-card root "
    "to install. Skips empty/stub files.": {
        "de": "Alle heruntergeladenen Cheats in eine ZIP mit dem SD-Karten-Layout "
              "(Atmosphère / Breeze / EdiZon) exportieren. Entpacke sie in das "
              "SD-Karten-Stammverzeichnis, um sie zu installieren. Überspringt leere/"
              "Platzhalter-Dateien.",
        "es": "Exporta todos los cheats descargados a un ZIP con la estructura de la tarjeta "
              "SD (Atmosphère / Breeze / EdiZon). Descomprímelo en la raíz de la SD para "
              "instalarlos. Omite archivos vacíos o de relleno.",
        "fr": "Exporte tous les cheats téléchargés dans un ZIP avec la structure de la carte "
              "SD (Atmosphère / Breeze / EdiZon). Dézippez-le à la racine de la SD pour "
              "installer. Ignore les fichiers vides/fictifs.",
        "it": "Esporta tutti i cheat scaricati in uno ZIP con la struttura della scheda SD "
              "(Atmosphère / Breeze / EdiZon). Estrailo nella radice della SD per "
              "installarli. Salta i file vuoti/segnaposto.",
        "ja": "ダウンロード済みのすべてのチートを、SD カードレイアウト（Atmosphère / "
              "Breeze / EdiZon）で ZIP にエクスポートします。SD カードのルートに展開すると"
              "インストールできます。空/スタブのファイルはスキップします。"},
    "Reconcile every build's cheat count with the actual .txt files "
    "on disk, then rescan downloaded status and redraw the table.": {
        "de": "Die Cheat-Anzahl jedes Builds mit den tatsächlichen .txt-Dateien auf der "
              "Festplatte abgleichen, dann den Download-Status neu scannen und die Tabelle "
              "neu zeichnen.",
        "es": "Concilia el recuento de cheats de cada build con los archivos .txt reales del "
              "disco, luego reescanea el estado de descarga y redibuja la tabla.",
        "fr": "Réconcilie le nombre de cheats de chaque build avec les vrais fichiers .txt "
              "sur le disque, puis rescanne l'état de téléchargement et redessine le tableau.",
        "it": "Riconcilia il conteggio dei cheat di ogni build con i file .txt reali su "
              "disco, poi riscansiona lo stato di download e ridisegna la tabella.",
        "ja": "各ビルドのチート数をディスク上の実際の .txt ファイルと突き合わせ、"
              "ダウンロード状況を再スキャンしてテーブルを再描画します。"},
    "Manually add a cheat entry: Title ID, Build ID, cheat codes "
    "(Atmosphere format), name and version.": {
        "de": "Manuell einen Cheat-Eintrag hinzufügen: Title-ID, Build-ID, Cheat-Codes "
              "(Atmosphère-Format), Name und Version.",
        "es": "Añade manualmente una entrada de cheat: Title ID, Build ID, códigos de cheat "
              "(formato Atmosphère), nombre y versión.",
        "fr": "Ajoute manuellement une entrée de cheat : Title ID, Build ID, codes de cheat "
              "(format Atmosphère), nom et version.",
        "it": "Aggiunge manualmente una voce di cheat: Title ID, Build ID, codici cheat "
              "(formato Atmosphère), nome e versione.",
        "ja": "チートエントリを手動で追加: Title ID、Build ID、チートコード"
              "（Atmosphère 形式）、名前、バージョン。"},
    "Export the (filtered) database to a UTF-8 CSV with all columns "
    "(Excel-compatible).": {
        "de": "Die (gefilterte) Datenbank als UTF-8-CSV mit allen Spalten exportieren "
              "(Excel-kompatibel).",
        "es": "Exporta la base de datos (filtrada) a un CSV UTF-8 con todas las columnas "
              "(compatible con Excel).",
        "fr": "Exporte la base (filtrée) vers un CSV UTF-8 avec toutes les colonnes "
              "(compatible Excel).",
        "it": "Esporta il database (filtrato) in un CSV UTF-8 con tutte le colonne "
              "(compatibile con Excel).",
        "ja": "（フィルタ済みの）データベースを全列付きの UTF-8 CSV にエクスポートします"
              "（Excel 対応）。"},
    "Save a consistent copy of the whole cheats.db (SQLite backup) "
    "to a location you choose.": {
        "de": "Eine konsistente Kopie der gesamten cheats.db (SQLite-Backup) an einem von "
              "dir gewählten Ort speichern.",
        "es": "Guarda una copia consistente de toda la cheats.db (copia SQLite) en la "
              "ubicación que elijas.",
        "fr": "Enregistre une copie cohérente de toute la cheats.db (sauvegarde SQLite) à "
              "l'emplacement de votre choix.",
        "it": "Salva una copia coerente dell'intera cheats.db (backup SQLite) in una "
              "posizione a tua scelta.",
        "ja": "cheats.db 全体の一貫したコピー（SQLite バックアップ）を、選んだ場所に"
              "保存します。"},
    "Export names.json": {
        "de": "names.json exportieren", "es": "Exportar names.json",
        "fr": "Exporter names.json", "it": "Esporta names.json",
        "ja": "names.json をエクスポート"},
    "Export a small Title ID → game name map (names.json) from the "
    "current database. The Android app uses it to name each game's "
    "cheat folder; upload it to the 'data' release to keep names current.": {
        "de": "Exportiert eine kleine Title-ID→Spielname-Zuordnung (names.json) aus der "
              "aktuellen Datenbank. Die Android-App benennt damit den Cheat-Ordner jedes "
              "Spiels; lade sie ins „data“-Release hoch, damit die Namen aktuell bleiben.",
        "es": "Exporta un pequeño mapa Title ID→nombre de juego (names.json) desde la base de "
              "datos actual. La app de Android lo usa para nombrar la carpeta de cheats de "
              "cada juego; súbelo al release «data» para mantener los nombres al día.",
        "fr": "Exporte une petite table Title ID→nom du jeu (names.json) depuis la base "
              "actuelle. L'app Android l'utilise pour nommer le dossier de triche de chaque "
              "jeu ; téléversez-la dans la release « data » pour garder les noms à jour.",
        "it": "Esporta una piccola mappa Title ID→nome del gioco (names.json) dal database "
              "attuale. L'app Android la usa per nominare la cartella dei trucchi di ogni "
              "gioco; caricala nella release «data» per mantenere aggiornati i nomi.",
        "ja": "現在のデータベースから小さな Title ID→ゲーム名の対応表（names.json）を書き出します。"
              "Android アプリは各ゲームのチートフォルダー名に使います。名前を最新に保つには "
              "「data」リリースへアップロードしてください。"},
    "No database file yet. Scrape first.": {
        "de": "Noch keine Datenbank. Zuerst scrapen.",
        "es": "Aún no hay base de datos. Primero haz scraping.",
        "fr": "Pas encore de base de données. Scrapez d'abord.",
        "it": "Nessun database ancora. Prima fai lo scraping.",
        "ja": "まだデータベースがありません。先にスクレイプしてください。"},
    "names.json exported: {n} games": {
        "de": "names.json exportiert: {n} Spiele",
        "es": "names.json exportado: {n} juegos",
        "fr": "names.json exporté : {n} jeux",
        "it": "names.json esportato: {n} giochi",
        "ja": "names.json をエクスポート：{n} 本のゲーム"},
    "names.json exported to:\n{dest}\n\n{n} games\n\nUpload it to the "
    "'data' release so the Android app always gets current game names.": {
        "de": "names.json exportiert nach:\n{dest}\n\n{n} Spiele\n\nLade sie ins „data“-"
              "Release hoch, damit die Android-App immer aktuelle Spielnamen bekommt.",
        "es": "names.json exportado a:\n{dest}\n\n{n} juegos\n\nSúbelo al release «data» "
              "para que la app de Android siempre tenga nombres de juego actuales.",
        "fr": "names.json exporté vers :\n{dest}\n\n{n} jeux\n\nTéléversez-le dans la release "
              "« data » pour que l'app Android ait toujours des noms de jeu à jour.",
        "it": "names.json esportato in:\n{dest}\n\n{n} giochi\n\nCaricalo nella release «data» "
              "così l'app Android ha sempre nomi di gioco aggiornati.",
        "ja": "names.json をエクスポートしました：\n{dest}\n\n{n} 本のゲーム\n\nAndroid アプリが"
              "常に最新のゲーム名を取得できるよう、「data」リリースへアップロードしてください。"},
    "Maintenance tools: clean invalid files, retry quota-skipped / "
    "'unavailable' builds, fix 0-cheat entries, recount from disk, "
    "scan for empty files, fix ID names, sync titles folder.": {
        "de": "Wartungswerkzeuge: ungültige Dateien bereinigen, kontingent-übersprungene / "
              "„nicht verfügbare“ Builds erneut versuchen, Einträge mit 0 Cheats "
              "korrigieren, von der Festplatte neu zählen, nach leeren Dateien suchen, "
              "ID-Namen korrigieren, titles-Ordner abgleichen.",
        "es": "Herramientas de mantenimiento: limpiar archivos no válidos, reintentar builds "
              "omitidos por cuota / «no disponibles», corregir entradas con 0 cheats, "
              "recontar desde el disco, buscar archivos vacíos, corregir nombres de ID, "
              "sincronizar la carpeta titles.",
        "fr": "Outils de maintenance : nettoyer les fichiers non valides, réessayer les "
              "builds ignorés (quota) / « indisponibles », corriger les entrées à 0 cheat, "
              "recompter depuis le disque, rechercher les fichiers vides, corriger les noms "
              "d'ID, synchroniser le dossier titles.",
        "it": "Strumenti di manutenzione: pulire i file non validi, riprovare le build "
              "saltate per quota / «non disponibili», correggere le voci con 0 cheat, "
              "ricontare dal disco, cercare file vuoti, correggere i nomi ID, sincronizzare "
              "la cartella titles.",
        "ja": "メンテナンスツール: 無効なファイルの整理、クォータでスキップ/「利用不可」"
              "ビルドの再試行、チート0件エントリの修正、ディスクからの再集計、空ファイルの"
              "検索、ID 名の修正、titles フォルダの同期。"},
    "Empty the database AND delete all downloaded files on disk "
    "(cheats, covers, ZIP, caches). Keeps titledb caches + settings.": {
        "de": "Die Datenbank leeren UND alle heruntergeladenen Dateien auf der Festplatte "
              "löschen (Cheats, Cover, ZIP, Caches). Behält titledb-Caches + Einstellungen.",
        "es": "Vacía la base de datos Y elimina todos los archivos descargados del disco "
              "(cheats, carátulas, ZIP, cachés). Conserva las cachés de titledb y los "
              "ajustes.",
        "fr": "Vide la base de données ET supprime tous les fichiers téléchargés sur le "
              "disque (cheats, jaquettes, ZIP, caches). Conserve les caches titledb + les "
              "réglages.",
        "it": "Svuota il database E cancella tutti i file scaricati su disco (cheat, "
              "copertine, ZIP, cache). Mantiene le cache di titledb + le impostazioni.",
        "ja": "データベースを空にし、ディスク上のダウンロード済みファイル（チート・"
              "カバー・ZIP・キャッシュ）をすべて削除します。titledb キャッシュ + 設定は"
              "保持します。"},
    "Toggle a filter that shows only update/DLC title ids "
    "(…800 / non-…000) — these need the base id on the console.": {
        "de": "Einen Filter umschalten, der nur Update-/DLC-Title-IDs zeigt (…800 / "
              "nicht-…000) — diese benötigen die Basis-ID auf der Konsole.",
        "es": "Activa un filtro que muestra solo los Title IDs de update/DLC (…800 / no "
              "…000): estos necesitan el ID base en la consola.",
        "fr": "Active un filtre qui n'affiche que les Title IDs update/DLC (…800 / non-…000) "
              "— ceux-ci nécessitent l'ID de base sur la console.",
        "it": "Attiva un filtro che mostra solo i Title ID di update/DLC (…800 / non-…000) — "
              "questi richiedono l'ID base sulla console.",
        "ja": "アップデート/DLC の Title ID（…800 / …000 以外）のみを表示するフィルタを"
              "切り替えます — これらはコンソールでベース ID が必要です。"},
})

# ---- Supplemental keys used at f-string call sites -------------------------
_merge({
    "Working...": {"de": "Arbeitet…", "es": "Trabajando…", "fr": "En cours…",
                   "it": "In corso…", "ja": "処理中…"},
    "checking…": {"de": "wird geprüft…", "es": "comprobando…", "fr": "vérification…",
                  "it": "verifica…", "ja": "確認中…"},
    "{n} games": {"de": "{n} Spiele", "es": "{n} juegos", "fr": "{n} jeux",
                  "it": "{n} giochi", "ja": "{n} 件"},
    "Download ({n})": {"de": "Herunterladen ({n})", "es": "Descargar ({n})",
                       "fr": "Télécharger ({n})", "it": "Scarica ({n})",
                       "ja": "ダウンロード（{n}）"},
    "Download via API ({n})": {
        "de": "Über API herunterladen ({n})", "es": "Descargar por API ({n})",
        "fr": "Télécharger via l'API ({n})", "it": "Scarica tramite API ({n})",
        "ja": "API でダウンロード（{n}）"},
    "Download via browser ({n})": {
        "de": "Über Browser herunterladen ({n})", "es": "Descargar por navegador ({n})",
        "fr": "Télécharger via le navigateur ({n})", "it": "Scarica dal browser ({n})",
        "ja": "ブラウザでダウンロード（{n}）"},
    "Check Cheat Files ({n})": {
        "de": "Cheat-Dateien prüfen ({n})", "es": "Comprobar archivos de cheats ({n})",
        "fr": "Vérifier les fichiers de cheats ({n})", "it": "Controlla file di cheat ({n})",
        "ja": "チートファイルを確認（{n}）"},
    "Export to ZIP ({n} selected)": {
        "de": "Als ZIP exportieren ({n} ausgewählt)",
        "es": "Exportar a ZIP ({n} seleccionados)",
        "fr": "Exporter en ZIP ({n} sélectionnés)",
        "it": "Esporta in ZIP ({n} selezionati)",
        "ja": "ZIP にエクスポート（{n} 件選択）"},
    "Download cover (selected {n})": {
        "de": "Cover herunterladen ({n} ausgewählt)",
        "es": "Descargar carátula ({n} seleccionados)",
        "fr": "Télécharger la jaquette ({n} sélectionnés)",
        "it": "Scarica copertina ({n} selezionati)",
        "ja": "カバーをダウンロード（{n} 件選択）"},
    "Delete ({n})": {"de": "Löschen ({n})", "es": "Eliminar ({n})",
                     "fr": "Supprimer ({n})", "it": "Elimina ({n})",
                     "ja": "削除（{n}）"},
    "✓ Auto-detected SD card: {info}": {
        "de": "✓ SD-Karte automatisch erkannt: {info}",
        "es": "✓ Tarjeta SD detectada automáticamente: {info}",
        "fr": "✓ Carte SD détectée automatiquement : {info}",
        "it": "✓ Scheda SD rilevata automaticamente: {info}",
        "ja": "✓ SD カードを自動検出しました: {info}"},
    " (+{n} more)": {"de": " (+{n} weitere)", "es": " (+{n} más)",
                     "fr": " (+{n} de plus)", "it": " (+{n} altre)",
                     "ja": "（他 {n} 件）"},
    "⚠ No SD card auto-detected — pick the drive root with Browse…": {
        "de": "⚠ Keine SD-Karte automatisch erkannt — wähle das Laufwerk mit „Durchsuchen…“.",
        "es": "⚠ No se detectó ninguna tarjeta SD: elige la raíz de la unidad con «Examinar…».",
        "fr": "⚠ Aucune carte SD détectée — choisissez la racine du lecteur avec « Parcourir… ».",
        "it": "⚠ Nessuna scheda SD rilevata — scegli la radice dell'unità con «Sfoglia…».",
        "ja": "⚠ SD カードを自動検出できませんでした — 「参照…」でドライブのルートを選択してください。"},
    "Choose the SD-card root (e.g. D:\\).": {
        "de": "Wähle das SD-Karten-Stammverzeichnis (z. B. D:\\).",
        "es": "Elige la raíz de la tarjeta SD (p. ej. D:\\).",
        "fr": "Choisissez la racine de la carte SD (p. ex. D:\\).",
        "it": "Scegli la radice della scheda SD (es. D:\\).",
        "ja": "SD カードのルートを選択してください（例: D:\\）。"},
    "✓ Looks like a Switch SD card (CFW folders found).": {
        "de": "✓ Sieht nach einer Switch-SD-Karte aus (CFW-Ordner gefunden).",
        "es": "✓ Parece una tarjeta SD de Switch (se encontraron carpetas CFW).",
        "fr": "✓ Ressemble à une carte SD Switch (dossiers CFW trouvés).",
        "it": "✓ Sembra una scheda SD della Switch (trovate cartelle CFW).",
        "ja": "✓ Switch の SD カードのようです（CFW フォルダを検出）。"},
    "⚠ No atmosphere/ or switch/ folder here — export anyway if you are sure.": {
        "de": "⚠ Kein atmosphere/- oder switch/-Ordner hier — trotzdem exportieren, wenn du sicher bist.",
        "es": "⚠ No hay carpeta atmosphere/ ni switch/ aquí: exporta de todos modos si estás seguro.",
        "fr": "⚠ Aucun dossier atmosphere/ ou switch/ ici — exportez quand même si vous êtes sûr.",
        "it": "⚠ Nessuna cartella atmosphere/ o switch/ qui — esporta comunque se sei sicuro.",
        "ja": "⚠ ここに atmosphere/ または switch/ フォルダがありません — 確実なら、そのままエクスポートしてください。"},
    "{name} ready.": {
        "de": "{name} ist bereit.", "es": "{name} está listo.",
        "fr": "{name} est prêt.", "it": "{name} è pronto.",
        "ja": "{name} の準備ができました。"},
    "loading cover...": {
        "de": "Cover wird geladen…", "es": "cargando carátula…",
        "fr": "chargement de la jaquette…", "it": "caricamento copertina…",
        "ja": "カバーを読み込み中…"},
    "(cover unavailable)": {
        "de": "(Cover nicht verfügbar)", "es": "(carátula no disponible)",
        "fr": "(jaquette indisponible)", "it": "(copertina non disponibile)",
        "ja": "（カバーは利用できません）"},
    "(cover error)": {
        "de": "(Cover-Fehler)", "es": "(error de carátula)",
        "fr": "(erreur de jaquette)", "it": "(errore copertina)",
        "ja": "（カバーのエラー）"},
    "{n} new build(s) found - starting download...": {
        "de": "{n} neue Build(s) gefunden – Download wird gestartet…",
        "es": "{n} build(s) nuevo(s) encontrado(s): iniciando la descarga…",
        "fr": "{n} nouveau(x) build(s) trouvé(s) — démarrage du téléchargement…",
        "it": "{n} nuova/e build trovata/e — avvio del download…",
        "ja": "{n} 件の新しいビルドを発見 — ダウンロードを開始します…"},
    "Update done - {n} new build(s) found.": {
        "de": "Aktualisierung fertig – {n} neue Build(s) gefunden.",
        "es": "Actualización completada: {n} build(s) nuevo(s) encontrado(s).",
        "fr": "Mise à jour terminée — {n} nouveau(x) build(s) trouvé(s).",
        "it": "Aggiornamento completato — {n} nuova/e build trovata/e.",
        "ja": "更新完了 — {n} 件の新しいビルドを発見。"},
    "No database yet at {path} - click 'Scrape all' to build it.": {
        "de": "Noch keine Datenbank unter {path} — klicke auf „Scrapen“, um sie zu "
              "erstellen.",
        "es": "Aún no hay base de datos en {path}: pulsa «Extraer» para crearla.",
        "fr": "Pas encore de base de données à {path} — cliquez sur « Extraire » pour "
              "la créer.",
        "it": "Nessun database ancora in {path} — clicca «Estrai» per crearlo.",
        "ja": "{path} にまだデータベースがありません — 「取得」をクリックして作成して"
              "ください。"},
    "check failed": {"de": "Prüfung fehlgeschlagen", "es": "fallo al comprobar",
                     "fr": "échec de la vérification", "it": "verifica non riuscita",
                     "ja": "確認に失敗"},
    "Scraping...": {"de": "Wird gescrapt…", "es": "Extrayendo…",
                    "fr": "Extraction…", "it": "Estrazione…", "ja": "取得中…"},
    "Updating...": {"de": "Wird aktualisiert…", "es": "Actualizando…",
                    "fr": "Mise à jour…", "it": "Aggiornamento…", "ja": "更新中…"},
    "Checked {n} cheat file(s).": {
        "de": "{n} Cheat-Datei(en) geprüft.", "es": "{n} archivo(s) de cheats comprobado(s).",
        "fr": "{n} fichier(s) de cheats vérifié(s).", "it": "{n} file di cheat controllati.",
        "ja": "{n} 件のチートファイルを確認しました。"},
    "Checked {n} cheat file(s) — {s} count(s) corrected.": {
        "de": "{n} Cheat-Datei(en) geprüft — {s} Anzahl(en) korrigiert.",
        "es": "{n} archivo(s) de cheats comprobado(s) — {s} recuento(s) corregido(s).",
        "fr": "{n} fichier(s) de cheats vérifié(s) — {s} compte(s) corrigé(s).",
        "it": "{n} file di cheat controllati — {s} conteggi corretti.",
        "ja": "{n} 件のチートファイルを確認 — {s} 件の件数を修正しました。"},
    "Entry updated.": {
        "de": "Eintrag aktualisiert.", "es": "Entrada actualizada.",
        "fr": "Entrée mise à jour.", "it": "Voce aggiornata.",
        "ja": "エントリを更新しました。"},
    "Entry updated and file moved.": {
        "de": "Eintrag aktualisiert und Datei verschoben.",
        "es": "Entrada actualizada y archivo movido.",
        "fr": "Entrée mise à jour et fichier déplacé.",
        "it": "Voce aggiornata e file spostato.",
        "ja": "エントリを更新し、ファイルを移動しました。"},
    "DevCatSKZ download done — {parts}": {
        "de": "DevCatSKZ-Download fertig — {parts}",
        "es": "Descarga de DevCatSKZ completada — {parts}",
        "fr": "Téléchargement DevCatSKZ terminé — {parts}",
        "it": "Download da DevCatSKZ completato — {parts}",
        "ja": "DevCatSKZ のダウンロード完了 — {parts}"},
    "Full database exported to:\n{dest}\n\n{size} MB": {
        "de": "Vollständige Datenbank exportiert nach:\n{dest}\n\n{size} MB",
        "es": "Base de datos completa exportada a:\n{dest}\n\n{size} MB",
        "fr": "Base de données complète exportée vers :\n{dest}\n\n{size} Mo",
        "it": "Database completo esportato in:\n{dest}\n\n{size} MB",
        "ja": "データベース全体をエクスポートしました:\n{dest}\n\n{size} MB"},
    "Restart to change language": {
        "de": "Zum Sprachwechsel neu starten",
        "es": "Reiniciar para cambiar el idioma",
        "fr": "Redémarrer pour changer de langue",
        "it": "Riavvia per cambiare lingua",
        "ja": "言語変更のため再起動"},
    "Please close and reopen the app to apply the new language.": {
        "de": "Bitte schließe die App und öffne sie erneut, um die neue Sprache "
              "anzuwenden.",
        "es": "Cierra y vuelve a abrir la app para aplicar el nuevo idioma.",
        "fr": "Veuillez fermer et rouvrir l'application pour appliquer la nouvelle "
              "langue.",
        "it": "Chiudi e riapri l'app per applicare la nuova lingua.",
        "ja": "新しい言語を適用するには、アプリを一度閉じてから再度開いてください。"},
    "Switch the program language now?\n\nThe app will close and reopen "
    "in {lang}.": {
        "de": "Die Programmsprache jetzt wechseln?\n\nDie App wird geschlossen und in "
              "{lang} neu geöffnet.",
        "es": "¿Cambiar ahora el idioma del programa?\n\nLa app se cerrará y volverá a "
              "abrirse en {lang}.",
        "fr": "Changer la langue du programme maintenant ?\n\nL'appli va se fermer et "
              "rouvrir en {lang}.",
        "it": "Cambiare ora la lingua del programma?\n\nL'app si chiuderà e riaprirà in "
              "{lang}.",
        "ja": "今すぐプログラムの言語を切り替えますか？\n\nアプリが終了し、{lang} で"
              "再度開きます。"},
})

# ---- Switch homebrew app download + Prisma theme ---------------------------
_merge({
    "Download Switch App": {
        "de": "Switch-App herunterladen", "es": "Descargar app de Switch",
        "fr": "Télécharger l'app Switch", "it": "Scarica app Switch",
        "ja": "Switch アプリをダウンロード"},
    "Copy to SD card": {
        "de": "Auf SD-Karte kopieren", "es": "Copiar a la tarjeta SD",
        "fr": "Copier sur la carte SD", "it": "Copia sulla scheda SD",
        "ja": "SD カードにコピー"},
    "Download the Switch homebrew app (SwitchCheatsDownloader.nro) — "
    "the on-console counterpart of this tool. It fetches the "
    "always-current cheats archive directly on the Switch. Always "
    "downloads the LATEST app version.": {
        "de": "Die Switch-Homebrew-App (SwitchCheatsDownloader.nro) herunterladen — "
              "das Gegenstück dieses Tools auf der Konsole. Sie lädt das stets "
              "aktuelle Cheats-Archiv direkt auf der Switch. Es wird immer die "
              "NEUESTE App-Version geladen.",
        "es": "Descarga la app homebrew de Switch (SwitchCheatsDownloader.nro): la "
              "contraparte de esta herramienta en la consola. Obtiene el archivo de "
              "cheats siempre actualizado directamente en la Switch. Siempre se "
              "descarga la versión MÁS RECIENTE.",
        "fr": "Télécharger l'app homebrew Switch (SwitchCheatsDownloader.nro) — le "
              "pendant de cet outil sur la console. Elle récupère l'archive de cheats "
              "toujours à jour directement sur la Switch. La DERNIÈRE version de "
              "l'app est toujours téléchargée.",
        "it": "Scarica l'app homebrew per Switch (SwitchCheatsDownloader.nro) — la "
              "controparte di questo strumento sulla console. Recupera l'archivio di "
              "cheat sempre aggiornato direttamente sulla Switch. Viene scaricata "
              "sempre l'ULTIMA versione.",
        "ja": "Switch ホームブリューアプリ（SwitchCheatsDownloader.nro）をダウンロード — "
              "本ツールの本体側カウンターパートです。常に最新のチートアーカイブを "
              "Switch 上で直接取得します。アプリは常に最新バージョンが"
              "ダウンロードされます。"},
    "ON: the downloaded app is copied straight onto your Switch SD "
    "card as /switch/SwitchCheatsDownloader.nro (auto-detected, like "
    "the cheats SD export).\nOFF: you pick where to save the .nro "
    "yourself.": {
        "de": "AN: Die heruntergeladene App wird direkt auf deine Switch-SD-Karte "
              "als /switch/SwitchCheatsDownloader.nro kopiert (automatisch erkannt, "
              "wie beim Cheats-SD-Export).\nAUS: Du wählst selbst, wo die .nro "
              "gespeichert wird.",
        "es": "ACTIVADO: la app descargada se copia directamente a tu tarjeta SD de "
              "Switch como /switch/SwitchCheatsDownloader.nro (detección automática, "
              "como la exportación de cheats a SD).\nDESACTIVADO: eliges dónde "
              "guardar el .nro.",
        "fr": "ON : l'app téléchargée est copiée directement sur votre carte SD "
              "Switch en /switch/SwitchCheatsDownloader.nro (détection automatique, "
              "comme l'export SD des cheats).\nOFF : vous choisissez où enregistrer "
              "le .nro.",
        "it": "ON: l'app scaricata viene copiata direttamente sulla scheda SD della "
              "Switch come /switch/SwitchCheatsDownloader.nro (rilevamento "
              "automatico, come l'esportazione dei cheat su SD).\nOFF: scegli tu "
              "dove salvare il .nro.",
        "ja": "ON: ダウンロードしたアプリを /switch/SwitchCheatsDownloader.nro として "
              "Switch の SD カードへ直接コピーします（チートの SD エクスポートと同様に"
              "自動検出）。\nOFF: .nro の保存先を自分で選択します。"},
    "Choose the theme (saved between runs).": {
        "de": "Design wählen (wird gespeichert).",
        "es": "Elige el tema (se guarda).",
        "fr": "Choisissez le thème (mémorisé).",
        "it": "Scegli il tema (salvato).",
        "ja": "テーマを選択（保存されます）。"},
    "◆ Prisma": {
        "de": "◆ Prisma", "es": "◆ Prisma", "fr": "◆ Prisma",
        "it": "◆ Prisma", "ja": "◆ プリズム"},
    "☾ Dark": {
        "de": "☾ Dunkel", "es": "☾ Oscuro", "fr": "☾ Sombre",
        "it": "☾ Scuro", "ja": "☾ ダーク"},
    "☀ Light": {
        "de": "☀ Hell", "es": "☀ Claro", "fr": "☀ Clair",
        "it": "☀ Chiaro", "ja": "☀ ライト"},
    "Select your Switch SD card root": {
        "de": "Wähle das Wurzelverzeichnis deiner Switch-SD-Karte",
        "es": "Selecciona la raíz de tu tarjeta SD de Switch",
        "fr": "Sélectionnez la racine de votre carte SD Switch",
        "it": "Seleziona la radice della scheda SD della Switch",
        "ja": "Switch の SD カードのルートを選択"},
    "'{path}' does not look like a Switch SD card "
    "(no atmosphere/switch/Nintendo folder). Use it anyway?": {
        "de": "'{path}' sieht nicht nach einer Switch-SD-Karte aus "
              "(kein atmosphere/switch/Nintendo-Ordner). Trotzdem verwenden?",
        "es": "'{path}' no parece una tarjeta SD de Switch "
              "(sin carpeta atmosphere/switch/Nintendo). ¿Usarla de todos modos?",
        "fr": "'{path}' ne ressemble pas à une carte SD Switch "
              "(pas de dossier atmosphere/switch/Nintendo). L'utiliser quand même ?",
        "it": "'{path}' non sembra una scheda SD della Switch "
              "(nessuna cartella atmosphere/switch/Nintendo). Usarla comunque?",
        "ja": "'{path}' は Switch の SD カードではないようです"
              "（atmosphere/switch/Nintendo フォルダなし）。それでも使用しますか？"},
    "Download the latest Switch app and copy it to:\n{target}\n\n"
    "An existing copy on the card is replaced. Proceed?": {
        "de": "Die neueste Switch-App herunterladen und kopieren nach:\n{target}\n\n"
              "Eine vorhandene Kopie auf der Karte wird ersetzt. Fortfahren?",
        "es": "¿Descargar la app de Switch más reciente y copiarla a:\n{target}\n\n"
              "Se reemplaza una copia existente en la tarjeta. ¿Continuar?",
        "fr": "Télécharger la dernière app Switch et la copier vers :\n{target}\n\n"
              "Une copie existante sur la carte sera remplacée. Continuer ?",
        "it": "Scaricare l'app Switch più recente e copiarla in:\n{target}\n\n"
              "Una copia esistente sulla scheda verrà sostituita. Continuare?",
        "ja": "最新の Switch アプリをダウンロードして次へコピーします:\n{target}\n\n"
              "カード上の既存のコピーは置き換えられます。続行しますか？"},
    "Save Switch app as...": {
        "de": "Switch-App speichern unter…", "es": "Guardar app de Switch como…",
        "fr": "Enregistrer l'app Switch sous…", "it": "Salva app Switch come…",
        "ja": "Switch アプリに名前を付けて保存…"},
    "Switch homebrew app": {
        "de": "Switch-Homebrew-App", "es": "App homebrew de Switch",
        "fr": "App homebrew Switch", "it": "App homebrew per Switch",
        "ja": "Switch ホームブリューアプリ"},
    "Downloading Switch app...": {
        "de": "Switch-App wird heruntergeladen…", "es": "Descargando app de Switch…",
        "fr": "Téléchargement de l'app Switch…", "it": "Download dell'app Switch…",
        "ja": "Switch アプリをダウンロード中…"},
    "Switch app download failed — see log.": {
        "de": "Download der Switch-App fehlgeschlagen — siehe Log.",
        "es": "Falló la descarga de la app de Switch: consulta el registro.",
        "fr": "Échec du téléchargement de l'app Switch — voir le journal.",
        "it": "Download dell'app Switch non riuscito — vedi il log.",
        "ja": "Switch アプリのダウンロードに失敗しました — ログを確認してください。"},
    "Switch app v{ver} copied to SD card.": {
        "de": "Switch-App v{ver} auf die SD-Karte kopiert.",
        "es": "App de Switch v{ver} copiada a la tarjeta SD.",
        "fr": "App Switch v{ver} copiée sur la carte SD.",
        "it": "App Switch v{ver} copiata sulla scheda SD.",
        "ja": "Switch アプリ v{ver} を SD カードへコピーしました。"},
    "Switch app v{ver} copied to:\n{target}\n\n"
    "You can now safely eject the card and launch "
    "'Switch Cheats Downloader' from the Homebrew Menu.": {
        "de": "Switch-App v{ver} kopiert nach:\n{target}\n\n"
              "Du kannst die Karte jetzt sicher auswerfen und "
              "'Switch Cheats Downloader' im Homebrew-Menü starten.",
        "es": "App de Switch v{ver} copiada a:\n{target}\n\n"
              "Ya puedes expulsar la tarjeta con seguridad e iniciar "
              "'Switch Cheats Downloader' desde el Homebrew Menu.",
        "fr": "App Switch v{ver} copiée vers :\n{target}\n\n"
              "Vous pouvez maintenant éjecter la carte en toute sécurité et lancer "
              "'Switch Cheats Downloader' depuis le Homebrew Menu.",
        "it": "App Switch v{ver} copiata in:\n{target}\n\n"
              "Ora puoi espellere la scheda in sicurezza e avviare "
              "'Switch Cheats Downloader' dal Homebrew Menu.",
        "ja": "Switch アプリ v{ver} を次へコピーしました:\n{target}\n\n"
              "カードを安全に取り外し、Homebrew メニューから "
              "'Switch Cheats Downloader' を起動できます。"},
    "Switch app v{ver} downloaded.": {
        "de": "Switch-App v{ver} heruntergeladen.",
        "es": "App de Switch v{ver} descargada.",
        "fr": "App Switch v{ver} téléchargée.",
        "it": "App Switch v{ver} scaricata.",
        "ja": "Switch アプリ v{ver} をダウンロードしました。"},
    "Switch app v{ver} saved to:\n{path}\n\n"
    "Copy it into the /switch/ folder on your Switch SD card and "
    "launch it from the Homebrew Menu.": {
        "de": "Switch-App v{ver} gespeichert unter:\n{path}\n\n"
              "Kopiere sie in den /switch/-Ordner deiner Switch-SD-Karte und "
              "starte sie über das Homebrew-Menü.",
        "es": "App de Switch v{ver} guardada en:\n{path}\n\n"
              "Cópiala en la carpeta /switch/ de tu tarjeta SD de Switch e "
              "iníciala desde el Homebrew Menu.",
        "fr": "App Switch v{ver} enregistrée sous :\n{path}\n\n"
              "Copiez-la dans le dossier /switch/ de votre carte SD Switch et "
              "lancez-la depuis le Homebrew Menu.",
        "it": "App Switch v{ver} salvata in:\n{path}\n\n"
              "Copiala nella cartella /switch/ della scheda SD della Switch e "
              "avviala dal Homebrew Menu.",
        "ja": "Switch アプリ v{ver} を次に保存しました:\n{path}\n\n"
              "Switch の SD カードの /switch/ フォルダにコピーし、"
              "Homebrew メニューから起動してください。"},
})

# ---- Restliche Dialoge/Status: vollstaendige Abdeckung (Audit 2026-07-08) --
_merge({
    "Scrape all": {
        "de": "Alles scrapen", "es": "Extraer todo", "fr": "Tout extraire",
        "it": "Estrai tutto", "ja": "すべてスクレイプ"},
    "Scrape metadata for ALL games from cheatslips.com?\n"
    "This can take several minutes (no login required).": {
        "de": "Metadaten für ALLE Spiele von cheatslips.com scrapen?\n"
              "Das kann mehrere Minuten dauern (kein Login erforderlich).",
        "es": "¿Extraer metadatos de TODOS los juegos de cheatslips.com?\n"
              "Puede tardar varios minutos (no requiere inicio de sesión).",
        "fr": "Extraire les métadonnées de TOUS les jeux depuis cheatslips.com ?\n"
              "Cela peut prendre plusieurs minutes (aucune connexion requise).",
        "it": "Estrarre i metadati di TUTTI i giochi da cheatslips.com?\n"
              "Può richiedere diversi minuti (nessun accesso necessario).",
        "ja": "cheatslips.com からすべてのゲームのメタデータを取得しますか？\n"
              "数分かかることがあります（ログイン不要）。"},
    "Update recent cheats": {
        "de": "Neueste Cheats aktualisieren", "es": "Actualizar cheats recientes",
        "fr": "Mettre à jour les cheats récents", "it": "Aggiorna cheat recenti",
        "ja": "最近のチートを更新"},
    "Scan the {pages} most recent 'latest cheat codes' page(s) on "
    "cheatslips.com\nand add any new builds - this also re-checks "
    "games already in the database\nthat show up there, since that "
    "means cheatslips just updated them.\n\nMuch faster than a full "
    "rescan since only the recent pages are fetched.": {
        "de": "Die {pages} neuesten 'latest cheat codes'-Seiten auf cheatslips.com "
              "durchsuchen\nund neue Builds hinzufügen - dort auftauchende, bereits "
              "bekannte Spiele werden ebenfalls\nneu geprüft, denn das heißt, "
              "cheatslips hat sie gerade aktualisiert.\n\nViel schneller als ein "
              "kompletter Rescan, da nur die neuesten Seiten geladen werden.",
        "es": "Analizar las {pages} páginas más recientes de 'latest cheat codes' en "
              "cheatslips.com\ny añadir builds nuevas; también se recomprueban los "
              "juegos ya existentes\nque aparezcan ahí, pues significa que cheatslips "
              "los acaba de actualizar.\n\nMucho más rápido que un reescaneo completo.",
        "fr": "Analyser les {pages} pages les plus récentes de 'latest cheat codes' "
              "sur cheatslips.com\net ajouter les nouvelles builds ; les jeux déjà "
              "connus qui y figurent sont\naussi revérifiés, car cheatslips vient de "
              "les mettre à jour.\n\nBien plus rapide qu'un rescan complet.",
        "it": "Analizza le {pages} pagine più recenti di 'latest cheat codes' su "
              "cheatslips.com\ne aggiungi le nuove build; i giochi già in database "
              "che vi compaiono vengono\nricontrollati, perché cheatslips li ha "
              "appena aggiornati.\n\nMolto più veloce di una nuova scansione completa.",
        "ja": "cheatslips.com の最新 'latest cheat codes' ページ {pages} 件をスキャンして\n"
              "新しいビルドを追加します。そこに表示される既存のゲームも再チェックされます\n"
              "（cheatslips が更新したばかりだからです）。\n\n"
              "最新ページのみ取得するため、完全な再スキャンよりずっと高速です。"},
    "Scraping/downloading in progress. Really quit?": {
        "de": "Scraping/Download läuft noch. Wirklich beenden?",
        "es": "Extracción/descarga en curso. ¿Salir de todos modos?",
        "fr": "Extraction/téléchargement en cours. Vraiment quitter ?",
        "it": "Estrazione/download in corso. Uscire davvero?",
        "ja": "スクレイプ／ダウンロードが進行中です。本当に終了しますか？"},
    "Browser download cancelled/failed — using Built-in.": {
        "de": "Browser-Download abgebrochen/fehlgeschlagen — Built-in wird verwendet.",
        "es": "Descarga del navegador cancelada/fallida — se usa el integrado.",
        "fr": "Téléchargement du navigateur annulé/échoué — utilisation de l'intégré.",
        "it": "Download del browser annullato/non riuscito — si usa quello integrato.",
        "ja": "ブラウザのダウンロードが中止/失敗 — 内蔵ブラウザを使用します。"},
    "Scrape & Download Everything finished.": {
        "de": "Alles scrapen & herunterladen abgeschlossen.",
        "es": "Extraer y descargar todo: finalizado.",
        "fr": "Tout extraire et télécharger : terminé.",
        "it": "Estrai e scarica tutto: completato.",
        "ja": "すべてスクレイプ＆ダウンロードが完了しました。"},
    "Nothing was exported — none of the selected builds have a "
    "downloaded cheat file with real codes yet.": {
        "de": "Nichts exportiert — keiner der ausgewählten Builds hat bisher eine "
              "heruntergeladene Cheat-Datei mit echten Codes.",
        "es": "No se exportó nada: ninguna de las builds seleccionadas tiene aún un "
              "archivo de cheats descargado con códigos reales.",
        "fr": "Rien n'a été exporté — aucune des builds sélectionnées n'a encore de "
              "fichier de cheats téléchargé avec de vrais codes.",
        "it": "Nulla è stato esportato — nessuna delle build selezionate ha ancora un "
              "file di cheat scaricato con codici reali.",
        "ja": "何もエクスポートされませんでした — 選択したビルドには、実際のコードを含む"
              "ダウンロード済みチートファイルがまだありません。"},
    "Search for rows where the game name is the raw title id and replace it\n"
    "with a real name (known names or derived from the base game).\n\n"
    "Proceed?": {
        "de": "Zeilen suchen, deren Spielname nur die rohe Title-ID ist, und sie\n"
              "durch echte Namen ersetzen (bekannte Namen oder vom Basisspiel "
              "abgeleitet).\n\nFortfahren?",
        "es": "¿Buscar filas cuyo nombre de juego es el title id en bruto y "
              "reemplazarlo\npor un nombre real (nombres conocidos o derivados del "
              "juego base)?\n\n¿Continuar?",
        "fr": "Rechercher les lignes dont le nom de jeu est le title id brut et le\n"
              "remplacer par un vrai nom (noms connus ou dérivés du jeu de base).\n\n"
              "Continuer ?",
        "it": "Cerca le righe il cui nome gioco è il title id grezzo e sostituiscilo\n"
              "con un nome reale (nomi noti o derivati dal gioco base).\n\n"
              "Procedere?",
        "ja": "ゲーム名が生のタイトル ID になっている行を検索し、実名（既知の名前または\n"
              "ベースゲームから導出）に置き換えます。\n\n続行しますか？"},
    "Remove every title_id folder (and any cheat files) that is not in the database, "
    "so the titles folder matches the database exactly?": {
        "de": "Jeden title_id-Ordner (samt Cheat-Dateien) entfernen, der nicht in der "
              "Datenbank ist, damit der titles-Ordner exakt der Datenbank entspricht?",
        "es": "¿Eliminar cada carpeta title_id (y sus archivos de cheats) que no esté "
              "en la base de datos, para que la carpeta titles coincida exactamente?",
        "fr": "Supprimer chaque dossier title_id (et ses fichiers de cheats) absent de "
              "la base, pour que le dossier titles corresponde exactement à la base ?",
        "it": "Rimuovere ogni cartella title_id (e i relativi file di cheat) non "
              "presente nel database, così che la cartella titles vi corrisponda "
              "esattamente?",
        "ja": "データベースにない title_id フォルダ（およびチートファイル）をすべて削除して、"
              "titles フォルダをデータベースと完全に一致させますか？"},
    "Scan every downloaded cheat file on disk and update the cheat count "
    "in the database to match the actual file contents?\n\n"
    "This corrects builds that show 0 cheats even though the .txt file "
    "contains codes. It does not delete anything.": {
        "de": "Alle heruntergeladenen Cheat-Dateien auf der Festplatte scannen und "
              "die Cheat-Anzahl in der Datenbank an den tatsächlichen Inhalt "
              "anpassen?\n\nDas korrigiert Builds, die 0 Cheats anzeigen, obwohl die "
              ".txt-Datei Codes enthält. Es wird nichts gelöscht.",
        "es": "¿Escanear todos los archivos de cheats descargados y actualizar el "
              "recuento en la base de datos según el contenido real?\n\nCorrige "
              "builds que muestran 0 cheats aunque el .txt contenga códigos. No se "
              "elimina nada.",
        "fr": "Analyser tous les fichiers de cheats téléchargés et mettre à jour le "
              "compte dans la base selon le contenu réel ?\n\nCorrige les builds "
              "affichant 0 cheat alors que le .txt contient des codes. Rien n'est "
              "supprimé.",
        "it": "Scansionare tutti i file di cheat scaricati e aggiornare il conteggio "
              "nel database in base al contenuto reale?\n\nCorregge le build che "
              "mostrano 0 cheat anche se il .txt contiene codici. Non viene "
              "eliminato nulla.",
        "ja": "ダウンロード済みのチートファイルをすべてスキャンし、実際の内容に合わせて"
              "データベースのチート数を更新しますか？\n\n.txt にコードがあるのに 0 と"
              "表示されるビルドを修正します。何も削除されません。"},
    "Scan every downloaded cheat file and find the ones that contain NO "
    "usable cheats — empty, a quota/placeholder message, or only names "
    "without any codes.\n\n"
    "They are listed in the log and their cheat count is reset to 0 so "
    "they appear under 'Not downloaded'. No files are deleted.": {
        "de": "Alle heruntergeladenen Cheat-Dateien scannen und diejenigen OHNE "
              "nutzbare Cheats finden — leer, Quota-/Platzhalter-Meldung oder nur "
              "Namen ohne Codes.\n\nSie werden im Log gelistet und ihre Cheat-Anzahl "
              "auf 0 gesetzt, sodass sie unter 'Nicht heruntergeladen' erscheinen. "
              "Es werden keine Dateien gelöscht.",
        "es": "Escanear todos los archivos de cheats y encontrar los que NO tienen "
              "cheats utilizables: vacíos, mensaje de cuota/marcador o solo nombres "
              "sin códigos.\n\nSe listan en el registro y su recuento se pone a 0 "
              "para que aparezcan en 'No descargado'. No se eliminan archivos.",
        "fr": "Analyser tous les fichiers de cheats et trouver ceux SANS cheats "
              "utilisables — vides, message de quota/placeholder ou seulement des "
              "noms sans codes.\n\nIls sont listés dans le journal et leur compte "
              "remis à 0 pour apparaître sous « Non téléchargé ». Aucun fichier "
              "n'est supprimé.",
        "it": "Scansiona tutti i file di cheat e trova quelli SENZA cheat "
              "utilizzabili — vuoti, con messaggio quota/segnaposto o solo nomi "
              "senza codici.\n\nVengono elencati nel log e il conteggio azzerato, "
              "così appaiono in 'Non scaricato'. Nessun file viene eliminato.",
        "ja": "ダウンロード済みのチートファイルをすべてスキャンし、使えるチートが"
              "ないもの（空、クォータ/プレースホルダー、コードなしの名前のみ）を"
              "見つけます。\n\nログに一覧表示され、チート数が 0 にリセットされて"
              "『未ダウンロード』に表示されます。ファイルは削除されません。"},
    "Scan all downloaded cheat files and delete the ones that only contain "
    "a quota message or placeholder?\n\n"
    "The database entries will be reset to 0 cheats so they can be re-downloaded "
    "once the quota resets.": {
        "de": "Alle heruntergeladenen Cheat-Dateien scannen und diejenigen löschen, "
              "die nur eine Quota-Meldung oder einen Platzhalter enthalten?\n\nDie "
              "Datenbankeinträge werden auf 0 Cheats zurückgesetzt, damit sie nach "
              "dem Quota-Reset erneut geladen werden können.",
        "es": "¿Escanear todos los archivos descargados y eliminar los que solo "
              "contienen un mensaje de cuota o un marcador?\n\nLas entradas se "
              "pondrán a 0 cheats para poder redescargarlas cuando se restablezca "
              "la cuota.",
        "fr": "Analyser tous les fichiers téléchargés et supprimer ceux qui ne "
              "contiennent qu'un message de quota ou un placeholder ?\n\nLes entrées "
              "seront remises à 0 cheat pour être retéléchargées après le reset du "
              "quota.",
        "it": "Scansionare tutti i file scaricati ed eliminare quelli che contengono "
              "solo un messaggio di quota o un segnaposto?\n\nLe voci saranno "
              "azzerate per poterle riscaricare al reset della quota.",
        "ja": "ダウンロード済みファイルをすべてスキャンし、クォータメッセージや"
              "プレースホルダーのみのものを削除しますか？\n\nデータベースの項目は "
              "0 チートにリセットされ、クォータ復活後に再ダウンロードできます。"},
    "'{p}' does not look like a Switch SD card (no atmosphere/ or "
    "switch/ folder).\n\nExport there anyway?": {
        "de": "'{p}' sieht nicht nach einer Switch-SD-Karte aus (kein atmosphere/- "
              "oder switch/-Ordner).\n\nTrotzdem dorthin exportieren?",
        "es": "'{p}' no parece una tarjeta SD de Switch (sin carpeta atmosphere/ o "
              "switch/).\n\n¿Exportar ahí de todos modos?",
        "fr": "'{p}' ne ressemble pas à une carte SD Switch (pas de dossier "
              "atmosphere/ ou switch/).\n\nY exporter quand même ?",
        "it": "'{p}' non sembra una scheda SD della Switch (nessuna cartella "
              "atmosphere/ o switch/).\n\nEsportare comunque lì?",
        "ja": "'{p}' は Switch の SD カードではないようです（atmosphere/ や switch/ "
              "フォルダなし）。\n\nそれでもここへエクスポートしますか？"},
    "Result: {verdict}\nFile: {path}": {
        "de": "Ergebnis: {verdict}\nDatei: {path}",
        "es": "Resultado: {verdict}\nArchivo: {path}",
        "fr": "Résultat : {verdict}\nFichier : {path}",
        "it": "Risultato: {verdict}\nFile: {path}",
        "ja": "結果: {verdict}\nファイル: {path}"},
    "— not downloaded —": {
        "de": "— nicht heruntergeladen —", "es": "— no descargado —",
        "fr": "— non téléchargé —", "it": "— non scaricato —",
        "ja": "— 未ダウンロード —"},
    "  … and {n} more": {
        "de": "  … und {n} weitere", "es": "  … y {n} más",
        "fr": "  … et {n} de plus", "it": "  … e altri {n}",
        "ja": "  … 他 {n} 件"},
    "Cheats found:": {
        "de": "Gefundene Cheats:", "es": "Cheats encontrados:",
        "fr": "Cheats trouvés :", "it": "Cheat trovati:",
        "ja": "見つかったチート:"},
    "No usable cheats: the file contains no line with "
    "real cheat codes.\nSuch stub files come from aggregated "
    "databases (names/ads only)\nand correctly count as "
    "'not downloaded' / 0 cheats.": {
        "de": "Keine nutzbaren Cheats: Die Datei enthält keine Zeile mit echten "
              "Cheat-Codes.\nSolche Stub-Dateien stammen aus aggregierten "
              "Datenbanken (nur Namen/Werbung)\nund zählen korrekt als 'nicht "
              "heruntergeladen' / 0 Cheats.",
        "es": "Sin cheats utilizables: el archivo no contiene ninguna línea con "
              "códigos reales.\nEstos archivos stub provienen de bases agregadas "
              "(solo nombres/anuncios)\ny cuentan correctamente como 'no "
              "descargado' / 0 cheats.",
        "fr": "Aucun cheat utilisable : le fichier ne contient aucune ligne avec de "
              "vrais codes.\nCes fichiers stub proviennent de bases agrégées (noms/"
              "pubs seulement)\net comptent à juste titre comme « non téléchargé » / "
              "0 cheat.",
        "it": "Nessun cheat utilizzabile: il file non contiene righe con codici "
              "reali.\nQuesti file stub provengono da database aggregati (solo nomi/"
              "annunci)\ne contano correttamente come 'non scaricato' / 0 cheat.",
        "ja": "使用可能なチートなし: このファイルには実際のチートコードの行が"
              "ありません。\nこうしたスタブは集約データベース由来（名前/広告のみ）で、\n"
              "正しく『未ダウンロード』/ 0 チートと数えられます。"},
    "Checked {n} build(s):": {
        "de": "{n} Build(s) geprüft:", "es": "{n} build(s) comprobada(s):",
        "fr": "{n} build(s) vérifiée(s) :", "it": "{n} build controllate:",
        "ja": "{n} 件のビルドを確認:"},
    "{n} selected game(s)": {
        "de": "{n} ausgewählte(s) Spiel(e)", "es": "{n} juego(s) seleccionado(s)",
        "fr": "{n} jeu(x) sélectionné(s)", "it": "{n} gioco/giochi selezionati",
        "ja": "選択した {n} 件のゲーム"},
    "ALL downloaded cheats": {
        "de": "ALLE heruntergeladenen Cheats", "es": "TODOS los cheats descargados",
        "fr": "TOUS les cheats téléchargés", "it": "TUTTI i cheat scaricati",
        "ja": "すべてのダウンロード済みチート"},
    "Export {scope} to:\n{root}\n\nTarget: {mode}\n\n"
    "Only files with real cheats are copied; existing SD cheats are "
    "merged. Proceed?": {
        "de": "{scope} exportieren nach:\n{root}\n\nZiel: {mode}\n\nNur Dateien mit "
              "echten Cheats werden kopiert; vorhandene SD-Cheats werden "
              "zusammengeführt. Fortfahren?",
        "es": "Exportar {scope} a:\n{root}\n\nDestino: {mode}\n\nSolo se copian "
              "archivos con cheats reales; los cheats existentes en la SD se "
              "combinan. ¿Continuar?",
        "fr": "Exporter {scope} vers :\n{root}\n\nCible : {mode}\n\nSeuls les "
              "fichiers avec de vrais cheats sont copiés ; les cheats existants de "
              "la SD sont fusionnés. Continuer ?",
        "it": "Esporta {scope} in:\n{root}\n\nDestinazione: {mode}\n\nVengono "
              "copiati solo i file con cheat reali; i cheat già sulla SD vengono "
              "uniti. Procedere?",
        "ja": "{scope} を次へエクスポート:\n{root}\n\nターゲット: {mode}\n\n"
              "実際のチートを含むファイルのみコピーされ、SD 上の既存チートは統合"
              "されます。続行しますか？"},
    "SD export ({mode}): {exported} file(s) for {games} game(s).": {
        "de": "SD-Export ({mode}): {exported} Datei(en) für {games} Spiel(e).",
        "es": "Exportación a SD ({mode}): {exported} archivo(s) para {games} juego(s).",
        "fr": "Export SD ({mode}) : {exported} fichier(s) pour {games} jeu(x).",
        "it": "Esportazione SD ({mode}): {exported} file per {games} giochi.",
        "ja": "SD エクスポート ({mode}): {games} 件のゲームに {exported} ファイル。"},
    "Export finished ({mode}):\n\n"
    "  • {exported} cheat file(s) for {games} game(s)\n"
    "  • {stubs} empty/stub file(s) skipped\n"
    "  • {missing} build(s) not downloaded (nothing to copy)\n"
    "  • {errors} error(s)\n\n"
    "You can now safely eject the card and start your games.": {
        "de": "Export abgeschlossen ({mode}):\n\n"
              "  • {exported} Cheat-Datei(en) für {games} Spiel(e)\n"
              "  • {stubs} leere/Stub-Datei(en) übersprungen\n"
              "  • {missing} Build(s) nicht heruntergeladen (nichts zu kopieren)\n"
              "  • {errors} Fehler\n\n"
              "Du kannst die Karte jetzt sicher auswerfen und deine Spiele starten.",
        "es": "Exportación finalizada ({mode}):\n\n"
              "  • {exported} archivo(s) de cheats para {games} juego(s)\n"
              "  • {stubs} archivo(s) vacío(s)/stub omitido(s)\n"
              "  • {missing} build(s) sin descargar (nada que copiar)\n"
              "  • {errors} error(es)\n\n"
              "Ya puedes expulsar la tarjeta con seguridad e iniciar tus juegos.",
        "fr": "Export terminé ({mode}) :\n\n"
              "  • {exported} fichier(s) de cheats pour {games} jeu(x)\n"
              "  • {stubs} fichier(s) vide(s)/stub ignoré(s)\n"
              "  • {missing} build(s) non téléchargée(s) (rien à copier)\n"
              "  • {errors} erreur(s)\n\n"
              "Vous pouvez maintenant éjecter la carte en toute sécurité et lancer "
              "vos jeux.",
        "it": "Esportazione completata ({mode}):\n\n"
              "  • {exported} file di cheat per {games} giochi\n"
              "  • {stubs} file vuoti/stub saltati\n"
              "  • {missing} build non scaricate (nulla da copiare)\n"
              "  • {errors} errori\n\n"
              "Ora puoi espellere la scheda in sicurezza e avviare i tuoi giochi.",
        "ja": "エクスポート完了 ({mode}):\n\n"
              "  • {games} 件のゲームに {exported} 件のチートファイル\n"
              "  • 空/スタブ {stubs} 件をスキップ\n"
              "  • 未ダウンロード {missing} 件（コピー対象なし）\n"
              "  • エラー {errors} 件\n\n"
              "カードを安全に取り外してゲームを起動できます。"},
    "ZIP export ({mode}): {exported} file(s) for {games} game(s) → {path}": {
        "de": "ZIP-Export ({mode}): {exported} Datei(en) für {games} Spiel(e) → {path}",
        "es": "Exportación ZIP ({mode}): {exported} archivo(s) para {games} juego(s) → {path}",
        "fr": "Export ZIP ({mode}) : {exported} fichier(s) pour {games} jeu(x) → {path}",
        "it": "Esportazione ZIP ({mode}): {exported} file per {games} giochi → {path}",
        "ja": "ZIP エクスポート ({mode}): {games} 件のゲームに {exported} ファイル → {path}"},
    "ZIP created ({mode}):\n{path}\n\n"
    "  • {exported} cheat file(s) for {games} game(s)\n"
    "  • {stubs} empty/stub file(s) skipped\n"
    "  • {missing} build(s) not downloaded (nothing to copy)\n"
    "  • {errors} error(s)\n\n"
    "Unzip the archive onto your SD-card root to install the cheats.": {
        "de": "ZIP erstellt ({mode}):\n{path}\n\n"
              "  • {exported} Cheat-Datei(en) für {games} Spiel(e)\n"
              "  • {stubs} leere/Stub-Datei(en) übersprungen\n"
              "  • {missing} Build(s) nicht heruntergeladen (nichts zu kopieren)\n"
              "  • {errors} Fehler\n\n"
              "Entpacke das Archiv ins Wurzelverzeichnis deiner SD-Karte, um die "
              "Cheats zu installieren.",
        "es": "ZIP creado ({mode}):\n{path}\n\n"
              "  • {exported} archivo(s) de cheats para {games} juego(s)\n"
              "  • {stubs} archivo(s) vacío(s)/stub omitido(s)\n"
              "  • {missing} build(s) sin descargar (nada que copiar)\n"
              "  • {errors} error(es)\n\n"
              "Descomprime el archivo en la raíz de tu tarjeta SD para instalar los "
              "cheats.",
        "fr": "ZIP créé ({mode}) :\n{path}\n\n"
              "  • {exported} fichier(s) de cheats pour {games} jeu(x)\n"
              "  • {stubs} fichier(s) vide(s)/stub ignoré(s)\n"
              "  • {missing} build(s) non téléchargée(s) (rien à copier)\n"
              "  • {errors} erreur(s)\n\n"
              "Décompressez l'archive à la racine de votre carte SD pour installer "
              "les cheats.",
        "it": "ZIP creato ({mode}):\n{path}\n\n"
              "  • {exported} file di cheat per {games} giochi\n"
              "  • {stubs} file vuoti/stub saltati\n"
              "  • {missing} build non scaricate (nulla da copiare)\n"
              "  • {errors} errori\n\n"
              "Estrai l'archivio nella radice della scheda SD per installare i cheat.",
        "ja": "ZIP を作成しました ({mode}):\n{path}\n\n"
              "  • {games} 件のゲームに {exported} 件のチートファイル\n"
              "  • 空/スタブ {stubs} 件をスキップ\n"
              "  • 未ダウンロード {missing} 件（コピー対象なし）\n"
              "  • エラー {errors} 件\n\n"
              "アーカイブを SD カードのルートに展開するとチートがインストールされます。"},
    "Database replaced — {n} build(s).": {
        "de": "Datenbank ersetzt — {n} Build(s).",
        "es": "Base de datos reemplazada: {n} build(s).",
        "fr": "Base de données remplacée — {n} build(s).",
        "it": "Database sostituito — {n} build.",
        "ja": "データベースを置き換えました — {n} 件のビルド。"},
    "Database replaced with the imported one.\n\n"
    "  • {n} build(s) now in the database\n": {
        "de": "Datenbank durch die importierte ersetzt.\n\n"
              "  • {n} Build(s) jetzt in der Datenbank\n",
        "es": "Base de datos reemplazada por la importada.\n\n"
              "  • {n} build(s) ahora en la base de datos\n",
        "fr": "Base remplacée par celle importée.\n\n"
              "  • {n} build(s) désormais dans la base\n",
        "it": "Database sostituito con quello importato.\n\n"
              "  • {n} build ora nel database\n",
        "ja": "データベースをインポートしたものに置き換えました。\n\n"
              "  • 現在のビルド数: {n} 件\n"},
    "A backup of the previous database was saved to:\n{path}": {
        "de": "Ein Backup der vorherigen Datenbank wurde gespeichert unter:\n{path}",
        "es": "Se guardó una copia de la base anterior en:\n{path}",
        "fr": "Une sauvegarde de l'ancienne base a été enregistrée dans :\n{path}",
        "it": "Un backup del database precedente è stato salvato in:\n{path}",
        "ja": "以前のデータベースのバックアップを保存しました:\n{path}"},
    "Database merged — {added} added, {updated} updated ({total} total).": {
        "de": "Datenbank zusammengeführt — {added} neu, {updated} aktualisiert "
              "({total} gesamt).",
        "es": "Base combinada: {added} añadidas, {updated} actualizadas ({total} en total).",
        "fr": "Base fusionnée — {added} ajoutées, {updated} mises à jour ({total} au total).",
        "it": "Database unito — {added} aggiunte, {updated} aggiornate ({total} totali).",
        "ja": "データベースを統合 — 追加 {added}、更新 {updated}（合計 {total}）。"},
    "Imported {total} build(s):\n\n"
    "  • {added} new build(s) added\n"
    "  • {updated} existing build(s) updated\n"
    "  • {after} build(s) now in the database\n\n"
    "Nothing was removed; existing entries kept their data.": {
        "de": "{total} Build(s) importiert:\n\n"
              "  • {added} neue Build(s) hinzugefügt\n"
              "  • {updated} vorhandene Build(s) aktualisiert\n"
              "  • {after} Build(s) jetzt in der Datenbank\n\n"
              "Nichts wurde entfernt; bestehende Einträge behielten ihre Daten.",
        "es": "{total} build(s) importada(s):\n\n"
              "  • {added} nueva(s) añadida(s)\n"
              "  • {updated} existente(s) actualizada(s)\n"
              "  • {after} build(s) ahora en la base de datos\n\n"
              "No se eliminó nada; las entradas existentes conservaron sus datos.",
        "fr": "{total} build(s) importée(s) :\n\n"
              "  • {added} nouvelle(s) ajoutée(s)\n"
              "  • {updated} existante(s) mise(s) à jour\n"
              "  • {after} build(s) désormais dans la base\n\n"
              "Rien n'a été supprimé ; les entrées existantes ont gardé leurs "
              "données.",
        "it": "{total} build importate:\n\n"
              "  • {added} nuove aggiunte\n"
              "  • {updated} esistenti aggiornate\n"
              "  • {after} build ora nel database\n\n"
              "Nulla è stato rimosso; le voci esistenti hanno mantenuto i dati.",
        "ja": "{total} 件のビルドをインポート:\n\n"
              "  • 新規追加 {added} 件\n"
              "  • 既存更新 {updated} 件\n"
              "  • 現在のビルド数 {after} 件\n\n"
              "何も削除されていません。既存の項目はデータを保持しています。"},
    "Could not check for updates:\n\n{msg}\n\n"
    "Check your internet connection and try again.": {
        "de": "Update-Prüfung nicht möglich:\n\n{msg}\n\n"
              "Prüfe deine Internetverbindung und versuche es erneut.",
        "es": "No se pudo comprobar actualizaciones:\n\n{msg}\n\n"
              "Comprueba tu conexión a Internet e inténtalo de nuevo.",
        "fr": "Impossible de vérifier les mises à jour :\n\n{msg}\n\n"
              "Vérifiez votre connexion Internet et réessayez.",
        "it": "Impossibile verificare gli aggiornamenti:\n\n{msg}\n\n"
              "Controlla la connessione a Internet e riprova.",
        "ja": "更新を確認できませんでした:\n\n{msg}\n\n"
              "インターネット接続を確認してもう一度お試しください。"},
    "You are up to date.\n\nInstalled version: v{ver}\n"
    "Program, cheats and database are all current.": {
        "de": "Du bist auf dem neuesten Stand.\n\nInstallierte Version: v{ver}\n"
              "Programm, Cheats und Datenbank sind aktuell.",
        "es": "Estás al día.\n\nVersión instalada: v{ver}\n"
              "El programa, los cheats y la base de datos están actualizados.",
        "fr": "Vous êtes à jour.\n\nVersion installée : v{ver}\n"
              "Programme, cheats et base de données sont à jour.",
        "it": "Sei aggiornato.\n\nVersione installata: v{ver}\n"
              "Programma, cheat e database sono aggiornati.",
        "ja": "最新の状態です。\n\nインストール済みバージョン: v{ver}\n"
              "プログラム、チート、データベースはすべて最新です。"},
    "Could not open:\n\n{err}": {
        "de": "Konnte nicht öffnen:\n\n{err}", "es": "No se pudo abrir:\n\n{err}",
        "fr": "Impossible d'ouvrir :\n\n{err}", "it": "Impossibile aprire:\n\n{err}",
        "ja": "開けませんでした:\n\n{err}"},
    "Could not open:\n{path}\n\n{err}": {
        "de": "Konnte nicht öffnen:\n{path}\n\n{err}",
        "es": "No se pudo abrir:\n{path}\n\n{err}",
        "fr": "Impossible d'ouvrir :\n{path}\n\n{err}",
        "it": "Impossibile aprire:\n{path}\n\n{err}",
        "ja": "開けませんでした:\n{path}\n\n{err}"},
    "No cheat file on disk for {tid}/{bid} — opened {folder}.": {
        "de": "Keine Cheat-Datei auf der Festplatte für {tid}/{bid} — {folder} geöffnet.",
        "es": "No hay archivo de cheats en disco para {tid}/{bid}; se abrió {folder}.",
        "fr": "Aucun fichier de cheats sur le disque pour {tid}/{bid} — {folder} ouvert.",
        "it": "Nessun file di cheat su disco per {tid}/{bid} — aperto {folder}.",
        "ja": "{tid}/{bid} のチートファイルがディスクにありません — {folder} を開きました。"},
    "{n} game(s) have entries with 0 cheats.\n"
    "Refresh them from the API and download their cheat codes?": {
        "de": "{n} Spiel(e) haben Einträge mit 0 Cheats.\n"
              "Über die API auffrischen und ihre Cheat-Codes herunterladen?",
        "es": "{n} juego(s) tienen entradas con 0 cheats.\n"
              "¿Actualizarlos desde la API y descargar sus códigos?",
        "fr": "{n} jeu(x) ont des entrées avec 0 cheat.\n"
              "Les rafraîchir via l'API et télécharger leurs codes ?",
        "it": "{n} gioco/giochi hanno voci con 0 cheat.\n"
              "Aggiornarli dall'API e scaricare i loro codici?",
        "ja": "{n} 件のゲームに 0 チートの項目があります。\n"
              "API から更新してチートコードをダウンロードしますか？"},
    "Failed: {err}": {
        "de": "Fehlgeschlagen: {err}", "es": "Falló: {err}",
        "fr": "Échec : {err}", "it": "Non riuscito: {err}",
        "ja": "失敗しました: {err}"},
    "Download cheat files for all {n} game(s) via the official API "
    "(no browser downloads)?\n\nAlready-downloaded builds are skipped. "
    "When the API limit is hit, the quota is reset automatically and "
    "the download continues — the browser opens only for those resets.": {
        "de": "Cheat-Dateien für alle {n} Spiel(e) über die offizielle API laden "
              "(keine Browser-Downloads)?\n\nBereits geladene Builds werden "
              "übersprungen. Wenn das API-Limit erreicht ist, wird das Kontingent "
              "automatisch zurückgesetzt und der Download fortgesetzt — der Browser "
              "öffnet sich nur für diese Resets.",
        "es": "¿Descargar archivos de cheats de los {n} juego(s) mediante la API "
              "oficial (sin descargas por navegador)?\n\nLas builds ya descargadas se "
              "omiten. Cuando se alcanza el límite de la API, la cuota se restablece "
              "automáticamente y la descarga continúa; el navegador solo se abre para "
              "esos restablecimientos.",
        "fr": "Télécharger les fichiers de cheats des {n} jeu(x) via l'API officielle "
              "(sans téléchargements par le navigateur) ?\n\nLes builds déjà "
              "téléchargées sont ignorées. Lorsque la limite de l'API est atteinte, le "
              "quota est réinitialisé automatiquement et le téléchargement continue — "
              "le navigateur ne s'ouvre que pour ces réinitialisations.",
        "it": "Scaricare i file di cheat per tutti i {n} giochi tramite l'API "
              "ufficiale (senza download dal browser)?\n\nLe build già scaricate "
              "vengono saltate. Quando si raggiunge il limite dell'API, la quota viene "
              "reimpostata automaticamente e il download continua: il browser si apre "
              "solo per questi reset.",
        "ja": "{n} 件すべてのゲームのチートファイルを公式 API 経由で"
              "ダウンロードしますか（ブラウザによるダウンロードなし）？\n\n"
              "ダウンロード済みのビルドはスキップされます。API の上限に達すると、"
              "クォータが自動的にリセットされてダウンロードが続行されます。"
              "ブラウザはそのリセットのときだけ開きます。"},
    "Download cheat files via the official API. Uses the selected rows, "
    "or ALL games if nothing is selected. When the API limit is hit the "
    "quota is reset automatically and the download continues — the "
    "browser opens only for those resets, never to download cheats.": {
        "de": "Cheat-Dateien über die offizielle API laden. Nutzt die ausgewählten "
              "Zeilen oder ALLE Spiele, wenn nichts ausgewählt ist. Bei erreichtem "
              "API-Limit wird das Kontingent automatisch zurückgesetzt und der "
              "Download fortgesetzt — der Browser öffnet sich nur für diese Resets, "
              "nie um Cheats zu laden.",
        "es": "Descarga archivos de cheats mediante la API oficial. Usa las filas "
              "seleccionadas, o TODOS los juegos si no hay selección. Cuando se "
              "alcanza el límite de la API, la cuota se restablece automáticamente y "
              "la descarga continúa; el navegador solo se abre para esos "
              "restablecimientos, nunca para descargar cheats.",
        "fr": "Télécharge les fichiers de cheats via l'API officielle. Utilise les "
              "lignes sélectionnées, ou TOUS les jeux si rien n'est sélectionné. "
              "Quand la limite de l'API est atteinte, le quota est réinitialisé "
              "automatiquement et le téléchargement continue — le navigateur ne "
              "s'ouvre que pour ces réinitialisations, jamais pour télécharger.",
        "it": "Scarica i file di cheat tramite l'API ufficiale. Usa le righe "
              "selezionate, o TUTTI i giochi se non c'è selezione. Quando si "
              "raggiunge il limite dell'API, la quota viene reimpostata "
              "automaticamente e il download continua: il browser si apre solo per "
              "quei reset, mai per scaricare cheat.",
        "ja": "公式 API でチートファイルをダウンロードします。選択行、または未選択なら"
              "すべてのゲームを対象にします。API の上限に達するとクォータが自動的に"
              "リセットされてダウンロードが続行されます — ブラウザはそのリセットの"
              "ときだけ開き、チートのダウンロードには使いません。"},
    "Could not start the updater:\n{err}": {
        "de": "Updater konnte nicht gestartet werden:\n{err}",
        "es": "No se pudo iniciar el actualizador:\n{err}",
        "fr": "Impossible de lancer le programme de mise à jour :\n{err}",
        "it": "Impossibile avviare l'updater:\n{err}",
        "ja": "アップデーターを起動できませんでした:\n{err}"},
    "Not a valid database file:\n{err}": {
        "de": "Keine gültige Datenbankdatei:\n{err}",
        "es": "No es un archivo de base de datos válido:\n{err}",
        "fr": "Fichier de base de données non valide :\n{err}",
        "it": "File di database non valido:\n{err}",
        "ja": "有効なデータベースファイルではありません:\n{err}"},
    "Exported {n} row(s) to:\n{dest}\n\n"
    "Columns included:\n"
    "• Game Title, Title/Build ID, Version, Upload Date\n"
    "• Cheat Count & Names, Credits, Description\n"
    "• Cover/Banner URLs, Source (GBatemp/titledb/cheatslips)\n"
    "• Publisher, Developer, Genre, Release Date\n"
    "• Player Count, Size, Rating, and more": {
        "de": "{n} Zeile(n) exportiert nach:\n{dest}\n\n"
              "Enthaltene Spalten:\n"
              "• Spieltitel, Title/Build-ID, Version, Upload-Datum\n"
              "• Cheat-Anzahl & -Namen, Credits, Beschreibung\n"
              "• Cover-/Banner-URLs, Quelle (GBatemp/titledb/cheatslips)\n"
              "• Publisher, Entwickler, Genre, Erscheinungsdatum\n"
              "• Spieleranzahl, Größe, Bewertung und mehr",
        "es": "{n} fila(s) exportada(s) a:\n{dest}\n\n"
              "Columnas incluidas:\n"
              "• Título del juego, Title/Build ID, versión, fecha de subida\n"
              "• Número y nombres de cheats, créditos, descripción\n"
              "• URLs de carátula/banner, fuente (GBatemp/titledb/cheatslips)\n"
              "• Editor, desarrollador, género, fecha de lanzamiento\n"
              "• Número de jugadores, tamaño, valoración y más",
        "fr": "{n} ligne(s) exportée(s) vers :\n{dest}\n\n"
              "Colonnes incluses :\n"
              "• Titre du jeu, Title/Build ID, version, date d'envoi\n"
              "• Nombre et noms des cheats, crédits, description\n"
              "• URLs de jaquette/bannière, source (GBatemp/titledb/cheatslips)\n"
              "• Éditeur, développeur, genre, date de sortie\n"
              "• Nombre de joueurs, taille, note et plus",
        "it": "{n} riga/righe esportate in:\n{dest}\n\n"
              "Colonne incluse:\n"
              "• Titolo del gioco, Title/Build ID, versione, data di caricamento\n"
              "• Numero e nomi dei cheat, crediti, descrizione\n"
              "• URL copertina/banner, fonte (GBatemp/titledb/cheatslips)\n"
              "• Editore, sviluppatore, genere, data di uscita\n"
              "• Numero di giocatori, dimensioni, valutazione e altro",
        "ja": "{n} 行を次へエクスポート:\n{dest}\n\n"
              "含まれる列:\n"
              "• ゲームタイトル、Title/Build ID、バージョン、アップロード日\n"
              "• チート数と名前、クレジット、説明\n"
              "• カバー/バナー URL、ソース (GBatemp/titledb/cheatslips)\n"
              "• パブリッシャー、開発元、ジャンル、発売日\n"
              "• プレイ人数、サイズ、評価など"},
})

# ---- Export for emulators --------------------------------------------------
_merge({
    "Export for Emulators": {
        "de": "Für Emulatoren exportieren", "es": "Exportar para emuladores",
        "fr": "Exporter pour les émulateurs", "it": "Esporta per emulatori",
        "ja": "エミュレーター用にエクスポート"},
    "Export cheats for emulators": {
        "de": "Cheats für Emulatoren exportieren", "es": "Exportar cheats para emuladores",
        "fr": "Exporter les cheats pour émulateurs", "it": "Esporta i cheat per emulatori",
        "ja": "エミュレーター用にチートをエクスポート"},
    "Export cheats for emulators (ZIP)": {
        "de": "Cheats für Emulatoren exportieren (ZIP)",
        "es": "Exportar cheats para emuladores (ZIP)",
        "fr": "Exporter les cheats pour émulateurs (ZIP)",
        "it": "Esporta i cheat per emulatori (ZIP)",
        "ja": "エミュレーター用にチートをエクスポート（ZIP）"},
    "Export every downloaded cheat into the emulator \"load\" layout, named after the game.": {
        "de": "Exportiert jeden heruntergeladenen Cheat in die „load\"-Struktur des Emulators, benannt nach dem Spiel.",
        "es": "Exporta cada cheat descargado a la estructura «load» del emulador, con el nombre del juego.",
        "fr": "Exporte chaque cheat téléchargé dans la structure « load » de l'émulateur, au nom du jeu.",
        "it": "Esporta ogni cheat scaricato nella struttura «load» dell'emulatore, con il nome del gioco.",
        "ja": "ダウンロード済みの各チートを、ゲーム名でエミュレーターの「load」構造に書き出します。"},
    "Emulator:": {
        "de": "Emulator:", "es": "Emulador:", "fr": "Émulateur :",
        "it": "Emulatore:", "ja": "エミュレーター:"},
    "Export as:": {
        "de": "Exportieren als:", "es": "Exportar como:", "fr": "Exporter comme :",
        "it": "Esporta come:", "ja": "エクスポート形式:"},
    "Folder": {
        "de": "Ordner", "es": "Carpeta", "fr": "Dossier", "it": "Cartella",
        "ja": "フォルダー"},
    "ZIP file": {
        "de": "ZIP-Datei", "es": "Archivo ZIP", "fr": "Fichier ZIP",
        "it": "File ZIP", "ja": "ZIPファイル"},
    "Destination folder:": {
        "de": "Zielordner:", "es": "Carpeta de destino:", "fr": "Dossier de destination :",
        "it": "Cartella di destinazione:", "ja": "保存先フォルダー:"},
    "All games in the database": {
        "de": "Alle Spiele in der Datenbank", "es": "Todos los juegos de la base de datos",
        "fr": "Tous les jeux de la base", "it": "Tutti i giochi nel database",
        "ja": "データベース内のすべてのゲーム"},
    "Choose the destination folder": {
        "de": "Zielordner wählen", "es": "Elegir la carpeta de destino",
        "fr": "Choisir le dossier de destination", "it": "Scegli la cartella di destinazione",
        "ja": "保存先フォルダーを選択"},
    "Please choose a destination.": {
        "de": "Bitte ein Ziel wählen.", "es": "Elige un destino.",
        "fr": "Choisis une destination.", "it": "Scegli una destinazione.",
        "ja": "保存先を選択してください。"},
    "Generic — a 'load' or 'mods' folder": {
        "de": "Generisch — ein „load\"- oder „mods\"-Ordner",
        "es": "Genérico — una carpeta «load» o «mods»",
        "fr": "Générique — un dossier « load » ou « mods »",
        "it": "Generico — una cartella «load» o «mods»",
        "ja": "汎用 — 「load」または「mods」フォルダー"},
    "Ryujinx (Windows) — mods folder": {
        "de": "Ryujinx (Windows) — mods-Ordner",
        "es": "Ryujinx (Windows) — carpeta mods",
        "fr": "Ryujinx (Windows) — dossier mods",
        "it": "Ryujinx (Windows) — cartella mods",
        "ja": "Ryujinx (Windows) — mods フォルダー"},
    "Folder names come from the database (special characters removed); the Title ID is used when a game has no name.\nOnly files with real cheats are written; empty/stub files are skipped.": {
        "de": "Die Ordnernamen stammen aus der Datenbank (Sonderzeichen entfernt); fehlt ein Spielname, wird die Title-ID verwendet.\nEs werden nur Dateien mit echten Cheats geschrieben; leere/Stub-Dateien werden übersprungen.",
        "es": "Los nombres de carpeta vienen de la base de datos (sin caracteres especiales); si un juego no tiene nombre, se usa el Title ID.\nSolo se escriben archivos con cheats reales; los vacíos/stub se omiten.",
        "fr": "Les noms de dossier proviennent de la base (caractères spéciaux retirés) ; si un jeu n'a pas de nom, le Title ID est utilisé.\nSeuls les fichiers avec de vrais cheats sont écrits ; les fichiers vides/stub sont ignorés.",
        "it": "I nomi delle cartelle provengono dal database (caratteri speciali rimossi); se un gioco non ha nome si usa il Title ID.\nVengono scritti solo i file con cheat reali; quelli vuoti/stub vengono saltati.",
        "ja": "フォルダー名はデータベース由来です（特殊文字は除去）。名前がない場合は Title ID を使用します。\n実際のチートを含むファイルのみ書き込み、空/スタブファイルはスキップします。"},
    "Build an emulator package: export the cheats into the <TitleID>/<GameName>/cheats/<BuildID>.txt layout that Eden, Suyu, Sudachi (and desktop yuzu/Ryujinx) read from their 'load' folder. Game names come from the database (special characters removed). Folder or ZIP; pick a specific emulator to prepend its load path.": {
        "de": "Erstellt ein Emulator-Paket: exportiert die Cheats in die Struktur <TitleID>/<GameName>/cheats/<BuildID>.txt, die Eden, Suyu, Sudachi (und Desktop-yuzu/Ryujinx) aus ihrem „load\"-Ordner lesen. Spielnamen stammen aus der Datenbank (Sonderzeichen entfernt). Ordner oder ZIP; wähle einen Emulator, um dessen load-Pfad voranzustellen.",
        "es": "Crea un paquete para emuladores: exporta los cheats a la estructura <TitleID>/<GameName>/cheats/<BuildID>.txt que Eden, Suyu, Sudachi (y yuzu/Ryujinx de escritorio) leen de su carpeta «load». Los nombres vienen de la base de datos (sin caracteres especiales). Carpeta o ZIP; elige un emulador para anteponer su ruta load.",
        "fr": "Crée un paquet pour émulateurs : exporte les cheats dans la structure <TitleID>/<GameName>/cheats/<BuildID>.txt que Eden, Suyu, Sudachi (et yuzu/Ryujinx sur PC) lisent depuis leur dossier « load ». Les noms viennent de la base (caractères spéciaux retirés). Dossier ou ZIP ; choisis un émulateur pour préfixer son chemin load.",
        "it": "Crea un pacchetto per emulatori: esporta i cheat nella struttura <TitleID>/<GameName>/cheats/<BuildID>.txt che Eden, Suyu, Sudachi (e yuzu/Ryujinx desktop) leggono dalla cartella «load». I nomi provengono dal database (caratteri speciali rimossi). Cartella o ZIP; scegli un emulatore per anteporre il suo percorso load.",
        "ja": "エミュレーター用パッケージを作成：Eden・Suyu・Sudachi（およびデスクトップの yuzu/Ryujinx）が「load」フォルダーから読み込む <TitleID>/<GameName>/cheats/<BuildID>.txt 構造にチートを書き出します。ゲーム名はデータベース由来（特殊文字は除去）。フォルダーまたは ZIP。特定のエミュレーターを選ぶと、その load パスが先頭に付きます。"},
    "Selected rows only ({n})": {
        "de": "Nur ausgewählte Zeilen ({n})", "es": "Solo filas seleccionadas ({n})",
        "fr": "Lignes sélectionnées uniquement ({n})", "it": "Solo righe selezionate ({n})",
        "ja": "選択した行のみ（{n}）"},
    "Exporting cheats for emulators ({label})...": {
        "de": "Exportiere Cheats für Emulatoren ({label})...",
        "es": "Exportando cheats para emuladores ({label})...",
        "fr": "Exportation des cheats pour émulateurs ({label})...",
        "it": "Esportazione cheat per emulatori ({label})...",
        "ja": "エミュレーター用にチートをエクスポート中（{label}）..."},
    "folder": {
        "de": "Ordner", "es": "carpeta", "fr": "dossier", "it": "cartella",
        "ja": "フォルダー"},
    "Emulator export ({kind}): {exported} file(s) for {games} game(s) → {dest}": {
        "de": "Emulator-Export ({kind}): {exported} Datei(en) für {games} Spiel(e) → {dest}",
        "es": "Exportación para emulador ({kind}): {exported} archivo(s) para {games} juego(s) → {dest}",
        "fr": "Export émulateur ({kind}) : {exported} fichier(s) pour {games} jeu(x) → {dest}",
        "it": "Esportazione emulatore ({kind}): {exported} file per {games} gioco/i → {dest}",
        "ja": "エミュレーターエクスポート（{kind}）：{games} ゲームの {exported} ファイル → {dest}"},
    "Emulator export finished ({kind}):\n{dest}\n\n  • {exported} cheat file(s) for {games} game(s)\n  • {stubs} empty/stub file(s) skipped\n  • {missing} build(s) not downloaded (nothing to copy)\n  • {errors} error(s)\n\nCopy the <TitleID>/<GameName>/cheats/… structure into your emulator's load folder.": {
        "de": "Emulator-Export fertig ({kind}):\n{dest}\n\n  • {exported} Cheat-Datei(en) für {games} Spiel(e)\n  • {stubs} leere/Stub-Datei(en) übersprungen\n  • {missing} Build(s) nicht heruntergeladen (nichts zu kopieren)\n  • {errors} Fehler\n\nKopiere die Struktur <TitleID>/<GameName>/cheats/… in den load-Ordner deines Emulators.",
        "es": "Exportación para emulador finalizada ({kind}):\n{dest}\n\n  • {exported} archivo(s) de cheats para {games} juego(s)\n  • {stubs} archivo(s) vacío(s)/stub omitidos\n  • {missing} build(s) sin descargar (nada que copiar)\n  • {errors} error(es)\n\nCopia la estructura <TitleID>/<GameName>/cheats/… en la carpeta load de tu emulador.",
        "fr": "Export émulateur terminé ({kind}) :\n{dest}\n\n  • {exported} fichier(s) de cheats pour {games} jeu(x)\n  • {stubs} fichier(s) vide(s)/stub ignorés\n  • {missing} build(s) non téléchargé(s) (rien à copier)\n  • {errors} erreur(s)\n\nCopie la structure <TitleID>/<GameName>/cheats/… dans le dossier load de ton émulateur.",
        "it": "Esportazione emulatore completata ({kind}):\n{dest}\n\n  • {exported} file di cheat per {games} gioco/i\n  • {stubs} file vuoti/stub saltati\n  • {missing} build non scaricate (niente da copiare)\n  • {errors} errore/i\n\nCopia la struttura <TitleID>/<GameName>/cheats/… nella cartella load del tuo emulatore.",
        "ja": "エミュレーターエクスポート完了（{kind}）：\n{dest}\n\n  • {games} ゲームの {exported} チートファイル\n  • {stubs} 個の空/スタブファイルをスキップ\n  • {missing} 個のビルドは未ダウンロード（コピー対象なし）\n  • {errors} 件のエラー\n\n<TitleID>/<GameName>/cheats/… 構造をエミュレーターの load フォルダーにコピーしてください。"},
})

# --------------------------------------------------------------------------
_build()






