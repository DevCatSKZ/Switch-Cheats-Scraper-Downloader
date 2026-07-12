#include "i18n.hpp"
#include "config.hpp"

#include <switch.h>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <sys/stat.h>

namespace i18n {

namespace {

struct Entry {
    const char* key;
    // Reihenfolge: DE, EN, ES, FR, IT, JA
    const char* text[6];
};

// clang-format off
const Entry kTable[] = {
    {"menu.install",   {"Herunterladen & Installieren", "Download & Install", "Descargar e instalar", "Télécharger et installer", "Scarica e installa", "\xe3\x83\x80\xe3\x82\xa6\xe3\x83\xb3\xe3\x83\xad\xe3\x83\xbc\xe3\x83\x89\xe3\x81\x97\xe3\x81\xa6\xe3\x82\xa4\xe3\x83\xb3\xe3\x82\xb9\xe3\x83\x88\xe3\x83\xbc\xe3\x83\xab"}},
    {"menu.info",      {"Info", "Info", "Información", "Infos", "Informazioni", "\xe6\x83\x85\xe5\xa0\xb1"}},
    {"menu.appupdate", {"App-Update", "App Update", "Actualizar la app", "Mise à jour de l'app", "Aggiorna app", "\xe3\x82\xa2\xe3\x83\x97\xe3\x83\xaa\xe3\x81\xae\xe6\x9b\xb4\xe6\x96\xb0"}},
    {"menu.exit",      {"Beenden", "Exit", "Salir", "Quitter", "Esci", "\xe7\xb5\x82\xe4\xba\x86"}},

    {"check.local",     {"Lokal installiert: ", "Locally installed: ", "Instalado localmente: ", "Installé localement : ", "Installato localmente: ", "\xe3\x83\xad\xe3\x83\xbc\xe3\x82\xab\xe3\x83\xab\xe3\x81\xae\xe3\x83\x90\xe3\x83\xbc\xe3\x82\xb8\xe3\x83\xa7\xe3\x83\xb3: "}},
    {"check.never",     {"noch nie", "never", "nunca", "jamais", "mai", "\xe3\x81\xaa\xe3\x81\x97"}},
    {"check.remote",    {"Neueste Version:  ", "Latest version:  ", "Última versión:  ", "Dernière version : ", "Ultima versione: ", "\xe6\x9c\x80\xe6\x96\xb0\xe3\x83\x90\xe3\x83\xbc\xe3\x82\xb8\xe3\x83\xa7\xe3\x83\xb3: "}},
    {"check.available", {"-> Ein Update ist verfügbar!", "-> An update is available!", "-> ¡Hay una actualización disponible!", "-> Une mise à jour est disponible !", "-> È disponibile un aggiornamento!", "-> \xe3\x82\xa2\xe3\x83\x83\xe3\x83\x97\xe3\x83\x87\xe3\x83\xbc\xe3\x83\x88\xe3\x81\x8c\xe3\x81\x82\xe3\x82\x8a\xe3\x81\xbe\xe3\x81\x99\xef\xbc\x81"}},
    {"check.uptodate",  {"-> Du hast bereits die neueste Version.", "-> You already have the latest version.", "-> Ya tienes la última versión.", "-> Vous avez déjà la dernière version.", "-> Hai già l'ultima versione.", "-> \xe6\x9c\x80\xe6\x96\xb0\xe3\x83\x90\xe3\x83\xbc\xe3\x82\xb8\xe3\x83\xa7\xe3\x83\xb3\xe3\x81\xa7\xe3\x81\x99\xe3\x80\x82"}},

    {"install.desc1",   {"Lädt die neueste switch-cheats.zip herunter und entpackt", "Downloads the latest switch-cheats.zip and extracts", "Descarga el switch-cheats.zip más reciente y lo extrae", "Télécharge le dernier switch-cheats.zip et l'extrait", "Scarica l'ultimo switch-cheats.zip e lo estrae", "\xe6\x9c\x80\xe6\x96\xb0\xe3\x81\xaeswitch-cheats.zip\xe3\x82\x92\xe3\x83\x80\xe3\x82\xa6\xe3\x83\xb3\xe3\x83\xad\xe3\x83\xbc\xe3\x83\x89\xe3\x81\x97\xe3\x80\x81"}},
    {"install.desc2",   {"sie direkt im Atmosphere-Layout auf die SD-Karte.", "it directly onto the SD card in Atmosphere layout.", "directamente en la tarjeta SD con el formato de Atmosphere.", "directement sur la carte SD au format Atmosphere.", "direttamente sulla scheda SD nel formato Atmosphere.", "SD\xe3\x82\xab\xe3\x83\xbc\xe3\x83\x89\xe3\x81\xae" "Atmosphere" "\xe5\xbd\xa2\xe5\xbc\x8f\xe3\x81\xab\xe7\x9b\xb4\xe6\x8e\xa5\xe5\xb1\x95\xe9\x96\x8b\xe3\x81\x97\xe3\x81\xbe\xe3\x81\x99\xe3\x80\x82"}},
    {"install.download",{"Download:", "Download:", "Descarga:", "Téléchargement :", "Download:", "\xe3\x83\x80\xe3\x82\xa6\xe3\x83\xb3\xe3\x83\xad\xe3\x83\xbc\xe3\x83\x89:"}},
    {"install.extract", {"Entpacken:", "Extracting:", "Extrayendo:", "Extraction :", "Estrazione:", "\xe5\xb1\x95\xe9\x96\x8b\xe4\xb8\xad:"}},
    {"install.filesSuffix", {" Dateien", " files", " archivos", " fichiers", " file", " \xe3\x83\x95\xe3\x82\xa1\xe3\x82\xa4\xe3\x83\xab"}},
    {"install.hint",    {"Drücke A um zu starten.", "Press A to start.", "Pulsa A para empezar.", "Appuyez sur A pour commencer.", "Premi A per iniziare.", "A\xe3\x83\x9c\xe3\x82\xbf\xe3\x83\xb3\xe3\x81\xa7\xe9\x96\x8b\xe5\xa7\x8b\xe3\x81\x97\xe3\x81\xbe\xe3\x81\x99\xe3\x80\x82"}},

    {"info.source",       {"Quelle: ", "Source: ", "Fuente: ", "Source : ", "Fonte: ", "\xe3\x82\xbd\xe3\x83\xbc\xe3\x82\xb9: "}},
    {"info.tag",          {"Release-Tag: ", "Release tag: ", "Etiqueta de lanzamiento: ", "Tag de version : ", "Tag di rilascio: ", "\xe3\x83\xaa\xe3\x83\xaa\xe3\x83\xbc\xe3\x82\xb9\xe3\x82\xbf\xe3\x82\xb0: "}},
    {"info.asset",        {"Asset: ", "Asset: ", "Recurso: ", "Fichier : ", "Risorsa: ", "\xe3\x82\xa2\xe3\x82\xbb\xe3\x83\x83\xe3\x83\x88: "}},
    {"info.target",       {"Ziel: ", "Target: ", "Destino: ", "Cible : ", "Destinazione: ", "\xe4\xbf\x9d\xe5\xad\x98\xe5\x85\x88: "}},
    {"info.localstate",   {"Lokaler Stand: ", "Local state: ", "Estado local: ", "État local : ", "Stato locale: ", "\xe3\x83\xad\xe3\x83\xbc\xe3\x82\xab\xe3\x83\xab\xe7\x8a\xb6\xe6\x85\x8b: "}},
    {"info.neverinstalled",{"noch nie installiert", "never installed", "nunca instalado", "jamais installé", "mai installato", "\xe6\x9c\xaa\xe3\x82\xa4\xe3\x83\xb3\xe3\x82\xb9\xe3\x83\x88\xe3\x83\xbc\xe3\x83\xab"}},
    {"info.version",      {"App-Version: ", "App version: ", "Versión de la app: ", "Version de l'app : ", "Versione app: ", "\xe3\x82\xa2\xe3\x83\x97\xe3\x83\xaa\xe3\x83\x90\xe3\x83\xbc\xe3\x82\xb8\xe3\x83\xa7\xe3\x83\xb3: "}},
    {"info.lang",         {"Sprache (L/R zum Wechseln): ", "Language (L/R to switch): ", "Idioma (L/R para cambiar): ", "Langue (L/R pour changer) : ", "Lingua (L/R per cambiare): ", "\xe8\xa8\x80\xe8\xaa\x9e (L/R\xe3\x81\xa7\xe5\x88\x87\xe6\x9b\xbf): "}},
    {"info.note1",        {"Die Cheats-Datei switch-cheats.zip stammt aus dem obigen GitHub-Repo", "The switch-cheats.zip cheats file comes from the GitHub repo above", "El archivo switch-cheats.zip proviene del repositorio de GitHub de arriba", "Le fichier switch-cheats.zip provient du dépôt GitHub ci-dessus", "Il file switch-cheats.zip proviene dal repository GitHub qui sopra", "\xe4\xb8\x8a\xe8\xa8\x98\xe3\x81\xae" "GitHub" "\xe3\x83\xaa\xe3\x83\x9d\xe3\x82\xb8\xe3\x83\x88\xe3\x83\xaa\xe3\x81\xae" "switch-cheats.zip" "\xe3\x81\xaf"}},
    {"info.note2",        {"und wird dort laufend aktualisiert.", "and is updated continuously.", "y se actualiza continuamente.", "et est mis à jour en continu.", "e viene aggiornato continuamente.", "\xe5\xb8\xb8\xe3\x81\xab\xe6\x9b\xb4\xe6\x96\xb0\xe3\x81\x95\xe3\x82\x8c\xe3\x81\xa6\xe3\x81\x84\xe3\x81\xbe\xe3\x81\x99\xe3\x80\x82"}},

    {"appupdate.desc1",     {"Prüft, ob eine neue Version dieser App verfügbar ist,", "Checks whether a new version of this app is available,", "Comprueba si hay una nueva versión de esta app", "Vérifie si une nouvelle version de cette application", "Controlla se è disponibile una nuova versione di questa app,", "\xe3\x81\x93\xe3\x81\xae\xe3\x82\xa2\xe3\x83\x97\xe3\x83\xaa\xe3\x81\xae\xe6\x96\xb0\xe3\x81\x97\xe3\x81\x84\xe3\x83\x90\xe3\x83\xbc\xe3\x82\xb8\xe3\x83\xa7\xe3\x83\xb3\xe3\x81\x8c\xe3\x81\x82\xe3\x82\x8b\xe3\x81\x8b\xe7\xa2\xba\xe8\xaa\x8d\xe3\x81\x97\xe3\x80\x81"}},
    {"appupdate.desc2",     {"und ersetzt bei Bedarf die aktuelle .nro-Datei.", "and replaces the current .nro file if needed.", "y reemplaza el archivo .nro actual si es necesario.", "est disponible et remplace le fichier .nro actuel si besoin.", "e sostituisce il file .nro attuale se necessario.", "\xe5\xbf\x85\xe8\xa6\x81\xe3\x81\xab\xe5\xbf\x9c\xe3\x81\x98\xe3\x81\xa6\xe7\x8f\xbe\xe5\x9c\xa8\xe3\x81\xae.nro\xe3\x83\x95\xe3\x82\xa1\xe3\x82\xa4\xe3\x83\xab\xe3\x82\x92\xe7\xbd\xae\xe3\x81\x8d\xe6\x8f\x9b\xe3\x81\x88\xe3\x81\xbe\xe3\x81\x99\xe3\x80\x82"}},
    {"appupdate.checking",  {"Suche nach App-Updates...", "Checking for app updates...", "Buscando actualizaciones de la app...", "Recherche de mises à jour de l'application...", "Ricerca aggiornamenti dell'app...", "\xe3\x82\xa2\xe3\x83\x97\xe3\x83\xaa\xe3\x81\xae\xe6\x9b\xb4\xe6\x96\xb0\xe3\x82\x92\xe7\xa2\xba\xe8\xaa\x8d\xe4\xb8\xad..."}},
    {"appupdate.pressAgain",{"Drücke A erneut um zu installieren.", "Press A again to install.", "Pulsa A de nuevo para instalar.", "Appuyez à nouveau sur A pour installer.", "Premi di nuovo A per installare.", "\xe3\x82\x82\xe3\x81\x86\xe4\xb8\x80\xe5\xba\xa6" "A" "\xe3\x83\x9c\xe3\x82\xbf\xe3\x83\xb3\xe3\x82\x92\xe6\x8a\xbc\xe3\x81\x99\xe3\x81\xa8\xe3\x82\xa4\xe3\x83\xb3\xe3\x82\xb9\xe3\x83\x88\xe3\x83\xbc\xe3\x83\xab\xe3\x81\x97\xe3\x81\xbe\xe3\x81\x99\xe3\x80\x82"}},
    {"appupdate.installing",{"Installiere App-Update...", "Installing app update...", "Instalando actualización...", "Installation de la mise a jour...", "Installazione aggiornamento...", "\xe3\x82\xa2\xe3\x83\x97\xe3\x83\xaa\xe3\x82\x92\xe6\x9b\xb4\xe6\x96\xb0\xe4\xb8\xad..."}},
    {"appupdate.restartHint",{"Bitte die App über das Homebrew-Menü neu starten.", "Please restart the app via the Homebrew Menu.", "Reinicia la app desde el Homebrew Menu.", "Veuillez redémarrer l'application via le Homebrew Menu.", "Riavvia l'app tramite l'Homebrew Menu.", "\xe3\x83\x9b\xe3\x83\xbc\xe3\x83\xa0\xe3\x83\x96\xe3\x83\xaa\xe3\x83\xa5\xe3\x83\xbc\xe3\x83\xa1\xe3\x83\x8b\xe3\x83\xa5\xe3\x83\xbc\xe3\x81\x8b\xe3\x82\x89\xe3\x82\xa2\xe3\x83\x97\xe3\x83\xaa\xe3\x82\x92\xe5\x86\x8d\xe8\xb5\xb7\xe5\x8b\x95\xe3\x81\x97\xe3\x81\xa6\xe3\x81\x8f\xe3\x81\xa0\xe3\x81\x95\xe3\x81\x84\xe3\x80\x82"}},

    {"exit.hint",  {"Drücke A um die App zu beenden.", "Press A to exit the app.", "Pulsa A para salir de la app.", "Appuyez sur A pour quitter l'application.", "Premi A per uscire dall'app.", "A\xe3\x83\x9c\xe3\x82\xbf\xe3\x83\xb3\xe3\x81\xa7\xe3\x82\xa2\xe3\x83\x97\xe3\x83\xaa\xe3\x82\x92\xe7\xb5\x82\xe4\xba\x86\xe3\x81\x97\xe3\x81\xbe\xe3\x81\x99\xe3\x80\x82"}},

    {"footer.online",  {"Online", "Online", "En línea", "En ligne", "Online", "\xe3\x82\xaa\xe3\x83\xb3\xe3\x83\xa9\xe3\x82\xa4\xe3\x83\xb3"}},
    {"footer.offline", {"Offline", "Offline", "Sin conexión", "Hors ligne", "Offline", "\xe3\x82\xaa\xe3\x83\x95\xe3\x83\xa9\xe3\x82\xa4\xe3\x83\xb3"}},
    {"footer.cancel",  {"B Abbrechen     +  Beenden erzwingen", "B Cancel     +  Force Exit", "B Cancelar     +  Forzar salida", "B Annuler     +  Forcer la sortie", "B Annulla     +  Forza uscita", "B \xe3\x82\xad\xe3\x83\xa3\xe3\x83\xb3\xe3\x82\xbb\xe3\x83\xab   + \xe5\xbc\xb7\xe5\x88\xb6\xe7\xb5\x82\xe4\xba\x86"}},
    {"footer.nav",     {"L/R Seite   Hoch/Runter Wählen   A OK   + Beenden", "L/R Page   Up/Down Select   A OK   + Exit", "L/R Página   Arriba/Abajo Elegir   A OK   + Salir", "L/R Page   Haut/Bas Choisir   A OK   + Quitter", "L/R Pagina   Su/Giù Scegli   A OK   + Esci", "L/R \xe3\x83\x9a\xe3\x83\xbc\xe3\x82\xb8   \xe4\xb8\x8a\xe4\xb8\x8b \xe9\x81\xb8\xe6\x8a\x9e   A \xe6\xb1\xba\xe5\xae\x9a   + \xe7\xb5\x82\xe4\xba\x86"}},
    {"footer.library", {"A Öffnen   X Filter   Y Suche   - Galerie", "A Open   X Filter   Y Search   - Gallery", "A Abrir   X Filtro   Y Buscar   - Galería", "A Ouvrir   X Filtre   Y Recherche   - Galerie", "A Apri   X Filtro   Y Cerca   - Galleria", "A \xe9\x96\x8b\xe3\x81\x8f   X \xe3\x83\x95\xe3\x82\xa3\xe3\x83\xab\xe3\x82\xbf   Y \xe6\xa4\x9c\xe7\xb4\xa2   - \xe3\x82\xae\xe3\x83\xa3\xe3\x83\xa9\xe3\x83\xaa\xe3\x83\xbc"}},
    {"footer.detail",  {"A Cheats   Y CheatSlips laden   ZR Editor   X Favorit   B Zurück", "A Cheats   Y Fetch CheatSlips   ZR Editor   X Favorite   B Back", "A Trucos   Y CheatSlips   ZR Editor   X Favorito   B Volver", "A Cheats   Y CheatSlips   ZR Éditeur   X Favori   B Retour", "A Trucchi   Y CheatSlips   ZR Editor   X Preferito   B Indietro", "A \xe3\x83\x81\xe3\x83\xbc\xe3\x83\x88   Y CheatSlips   ZR \xe3\x82\xa8\xe3\x83\x87\xe3\x82\xa3\xe3\x82\xbf\xe3\x83\xbc   X \xe3\x81\x8a\xe6\xb0\x97\xe3\x81\xab\xe5\x85\xa5\xe3\x82\x8a   B \xe6\x88\xbb\xe3\x82\x8b"}},

    {"status.checkinternet", {"Prüfe Internetverbindung...", "Checking internet connection...", "Comprobando la conexión a Internet...", "Vérification de la connexion Internet...", "Controllo della connessione Internet...", "\xe3\x82\xa4\xe3\x83\xb3\xe3\x82\xbf\xe3\x83\xbc\xe3\x83\x8d\xe3\x83\x83\xe3\x83\x88\xe6\x8e\xa5\xe7\xb6\x9a\xe3\x82\x92\xe7\xa2\xba\xe8\xaa\x8d\xe4\xb8\xad..."}},
    {"status.connecting",    {"Verbinde mit GitHub...", "Connecting to GitHub...", "Conectando con GitHub...", "Connexion à GitHub...", "Connessione a GitHub...", "GitHub\xe3\x81\xab\xe6\x8e\xa5\xe7\xb6\x9a\xe4\xb8\xad..."}},
    {"status.downloading",   {"Lade switch-cheats.zip herunter...", "Downloading switch-cheats.zip...", "Descargando switch-cheats.zip...", "Téléchargement de switch-cheats.zip...", "Download di switch-cheats.zip...", "switch-cheats.zip\xe3\x82\x92\xe3\x83\x80\xe3\x82\xa6\xe3\x83\xb3\xe3\x83\xad\xe3\x83\xbc\xe3\x83\x89\xe4\xb8\xad..."}},
    {"status.extracting",    {"Entpacke auf SD-Karte...", "Extracting to SD card...", "Extrayendo a la tarjeta SD...", "Extraction sur la carte SD...", "Estrazione sulla scheda SD...", "SD\xe3\x82\xab\xe3\x83\xbc\xe3\x83\x89\xe3\x81\xab\xe5\xb1\x95\xe9\x96\x8b\xe4\xb8\xad..."}},

    {"result.noInternet",   {"Keine Internetverbindung verfügbar.", "No internet connection available.", "No hay conexión a Internet disponible.", "Aucune connexion Internet disponible.", "Nessuna connessione a Internet disponibile.", "\xe3\x82\xa4\xe3\x83\xb3\xe3\x82\xbf\xe3\x83\xbc\xe3\x83\x8d\xe3\x83\x83\xe3\x83\x88\xe6\x8e\xa5\xe7\xb6\x9a\xe3\x81\x8c\xe3\x81\x82\xe3\x82\x8a\xe3\x81\xbe\xe3\x81\x9b\xe3\x82\x93\xe3\x80\x82"}},
    {"result.errorPrefix",  {"Fehler: ", "Error: ", "Error: ", "Erreur : ", "Errore: ", "\xe3\x82\xa8\xe3\x83\xa9\xe3\x83\xbc: "}},
    {"result.cancelled",    {"Download abgebrochen.", "Download cancelled.", "Descarga cancelada.", "Téléchargement annulé.", "Download annullato.", "\xe3\x83\x80\xe3\x82\xa6\xe3\x83\xb3\xe3\x83\xad\xe3\x83\xbc\xe3\x83\x89\xe3\x82\x92\xe4\xb8\xad\xe6\xad\xa2\xe3\x81\x97\xe3\x81\xbe\xe3\x81\x97\xe3\x81\x9f\xe3\x80\x82"}},
    {"result.cancelledResume", {"Download abgebrochen - wird beim nächsten Versuch fortgesetzt.", "Download cancelled - will resume on next attempt.", "Descarga cancelada - se reanudará en el próximo intento.", "Téléchargement annulé - reprendra à la prochaine tentative.", "Download annullato - riprenderà al prossimo tentativo.", "\xe3\x83\x80\xe3\x82\xa6\xe3\x83\xb3\xe3\x83\xad\xe3\x83\xbc\xe3\x83\x89\xe3\x82\x92\xe4\xb8\xad\xe6\xad\xa2\xe3\x81\x97\xe3\x81\xbe\xe3\x81\x97\xe3\x81\x9f\xe3\x80\x82\xe6\xac\xa1\xe5\x9b\x9e\xe3\x81\xaf\xe7\xb6\x9a\xe3\x81\x8d\xe3\x81\x8b\xe3\x82\x89\xe5\x86\x8d\xe9\x96\x8b\xe3\x81\x97\xe3\x81\xbe\xe3\x81\x99\xe3\x80\x82"}},
    {"result.cancelledInstall", {"Installation abgebrochen (teilweise entpackt).", "Installation cancelled (partially extracted).", "Instalación cancelada (extracción parcial).", "Installation annulée (extraction partielle).", "Installazione annullata (estrazione parziale).", "\xe3\x82\xa4\xe3\x83\xb3\xe3\x82\xb9\xe3\x83\x88\xe3\x83\xbc\xe3\x83\xab\xe3\x82\x92\xe4\xb8\xad\xe6\xad\xa2\xe3\x81\x97\xe3\x81\xbe\xe3\x81\x97\xe3\x81\x9f\xef\xbc\x88\xe4\xb8\x80\xe9\x83\xa8\xe5\xb1\x95\xe9\x96\x8b\xe6\xb8\x88\xe3\x81\xbf\xef\xbc\x89\xe3\x80\x82"}},
    {"result.extractErrorPrefix", {"Fehler beim Entpacken: ", "Extraction error: ", "Error al extraer: ", "Erreur d'extraction : ", "Errore di estrazione: ", "\xe5\xb1\x95\xe9\x96\x8b\xe3\x82\xa8\xe3\x83\xa9\xe3\x83\xbc: "}},
    {"result.doneInstalledPrefix", {"Fertig! ", "Done! ", "¡Listo! ", "Terminé ! ", "Fatto! ", "\xe5\xae\x8c\xe4\xba\x86\xef\xbc\x81 "}},
    {"result.doneInstalledSuffix", {" Dateien installiert.", " files installed.", " archivos instalados.", " fichiers installés.", " file installati.", " \xe3\x83\x95\xe3\x82\xa1\xe3\x82\xa4\xe3\x83\xab\xe3\x82\x92\xe3\x82\xa4\xe3\x83\xb3\xe3\x82\xb9\xe3\x83\x88\xe3\x83\xbc\xe3\x83\xab\xe3\x81\x97\xe3\x81\xbe\xe3\x81\x97\xe3\x81\x9f\xe3\x80\x82"}},

    {"result.appUpToDate", {"Kein App-Update verfügbar.", "No app update available.", "No hay actualización de la app disponible.", "Aucune mise à jour de l'application disponible.", "Nessun aggiornamento dell'app disponibile.", "\xe3\x82\xa2\xe3\x83\x97\xe3\x83\xaa\xe3\x81\xae\xe6\x9b\xb4\xe6\x96\xb0\xe3\x81\xaf\xe3\x81\x82\xe3\x82\x8a\xe3\x81\xbe\xe3\x81\x9b\xe3\x82\x93\xe3\x80\x82"}},
    {"result.appUpdateAvailablePrefix", {"App-Update verfügbar: v", "App update available: v", "Actualización de la app disponible: v", "Mise à jour de l'application disponible : v", "Aggiornamento dell'app disponibile: v", "\xe3\x82\xa2\xe3\x83\x97\xe3\x83\xaa\xe3\x81\xae\xe6\x9b\xb4\xe6\x96\xb0\xe3\x81\x8c\xe3\x81\x82\xe3\x82\x8a\xe3\x81\xbe\xe3\x81\x99: v"}},
    {"result.appUpdateDone", {"App-Update installiert! Bitte neu starten.", "App update installed! Please restart.", "¡Actualización instalada! Reinicia la app.", "Mise à jour installée ! Veuillez redémarrer.", "Aggiornamento installato! Riavvia l'app.", "\xe3\x82\xa2\xe3\x83\x97\xe3\x83\xaa\xe3\x82\x92\xe6\x9b\xb4\xe6\x96\xb0\xe3\x81\x97\xe3\x81\xbe\xe3\x81\x97\xe3\x81\x9f\xef\xbc\x81\xe5\x86\x8d\xe8\xb5\xb7\xe5\x8b\x95\xe3\x81\x97\xe3\x81\xa6\xe3\x81\x8f\xe3\x81\xa0\xe3\x81\x95\xe3\x81\x84\xe3\x80\x82"}},

    {"btn.cancel", {"Abbrechen", "Cancel", "Cancelar", "Annuler", "Annulla", "\xe3\x82\xad\xe3\x83\xa3\xe3\x83\xb3\xe3\x82\xbb\xe3\x83\xab"}},
    {"btn.start",  {"Starten", "Start", "Iniciar", "Démarrer", "Avvia", "\xe3\x82\xb9\xe3\x82\xbf\xe3\x83\xbc\xe3\x83\x88"}},
    {"btn.check",  {"Prüfen", "Check", "Comprobar", "Vérifier", "Verifica", "\xe7\xa2\xba\xe8\xaa\x8d"}},

    // Fehlertexte aus updater.cpp / zip_extract.cpp (Prefixe enden mit ": ",
    // dahinter haengt der Code dynamische Teile wie Pfade oder curl-Meldungen).
    {"err.internal",         {"Interner Fehler (curl)", "Internal error (curl)", "Error interno (curl)", "Erreur interne (curl)", "Errore interno (curl)", "\xe5\x86\x85\xe9\x83\xa8\xe3\x82\xa8\xe3\x83\xa9\xe3\x83\xbc (curl)"}},
    {"err.network",          {"Netzwerkfehler: ", "Network error: ", "Error de red: ", "Erreur réseau : ", "Errore di rete: ", "\xe3\x83\x8d\xe3\x83\x83\xe3\x83\x88\xe3\x83\xaf\xe3\x83\xbc\xe3\x82\xaf\xe3\x82\xa8\xe3\x83\xa9\xe3\x83\xbc: "}},
    {"clock.warn",           {"Konsolen-Uhr falsch! Datum & Uhrzeit korrigieren (sonst SSL-Fehler).", "Console clock is wrong! Fix date & time (else SSL error).", "\xc2\xa1Reloj de consola incorrecto! Corrige fecha y hora (o error SSL).", "Horloge console incorrecte ! Corrigez date et heure (sinon erreur SSL).", "Orologio console errato! Correggi data e ora (altrimenti errore SSL).", "\xe6\x9c\xac\xe4\xbd\x93\xe3\x81\xae\xe6\x99\x82\xe8\xa8\x88\xe3\x81\x8c\xe3\x81\x9a\xe3\x82\x8c\xe3\x81\xa6\xe3\x81\x84\xe3\x81\xbe\xe3\x81\x99\xe3\x80\x82\xe6\x97\xa5\xe4\xbb\x98\xe3\x81\xa8\xe6\x99\x82\xe5\x88\xbb\xe3\x82\x92\xe4\xbf\xae\xe6\xad\xa3\xe3\x81\x97\xe3\x81\xa6\xe3\x81\x8f\xe3\x81\xa0\xe3\x81\x95\xe3\x81\x84\xef\xbc\x88" "SSL" "\xef\xbc\x89\xe3\x80\x82"}},
    {"err.rateLimit",        {"GitHub-Rate-Limit erreicht - bitte später erneut versuchen.", "GitHub rate limit reached - please try again later.", "Límite de peticiones de GitHub alcanzado - inténtalo más tarde.", "Limite de requêtes GitHub atteinte - réessayez plus tard.", "Limite di richieste GitHub raggiunto - riprova più tardi.", "GitHub\xe3\x81\xae" "API" "\xe5\x88\xb6\xe9\x99\x90\xe3\x81\xab\xe9\x81\x94\xe3\x81\x97\xe3\x81\xbe\xe3\x81\x97\xe3\x81\x9f\xe3\x80\x82\xe5\xbe\x8c\xe3\x81\xa7\xe3\x81\x8a\xe8\xa9\xa6\xe3\x81\x97\xe3\x81\x8f\xe3\x81\xa0\xe3\x81\x95\xe3\x81\x84\xe3\x80\x82"}},
    {"err.githubHttp",       {"GitHub-API antwortete mit HTTP ", "GitHub API responded with HTTP ", "La API de GitHub respondió con HTTP ", "L'API GitHub a répondu avec HTTP ", "L'API GitHub ha risposto con HTTP ", "GitHub API: HTTP "}},
    {"err.serverHttp",       {"Server antwortete mit HTTP ", "Server responded with HTTP ", "El servidor respondió con HTTP ", "Le serveur a répondu avec HTTP ", "Il server ha risposto con HTTP ", "\xe3\x82\xb5\xe3\x83\xbc\xe3\x83\x90\xe3\x83\xbc: HTTP "}},
    {"err.assetNotFound",    {"Asset nicht im Release gefunden: ", "Asset not found in release: ", "Recurso no encontrado en el release: ", "Fichier introuvable dans la release : ", "Risorsa non trovata nella release: ", "\xe3\x83\xaa\xe3\x83\xaa\xe3\x83\xbc\xe3\x82\xb9\xe3\x81\xab\xe3\x82\xa2\xe3\x82\xbb\xe3\x83\x83\xe3\x83\x88\xe3\x81\x8c\xe8\xa6\x8b\xe3\x81\xa4\xe3\x81\x8b\xe3\x82\x8a\xe3\x81\xbe\xe3\x81\x9b\xe3\x82\x93: "}},
    {"err.noDownloadUrl",    {"Download-URL nicht gefunden", "Download URL not found", "URL de descarga no encontrada", "URL de telechargement introuvable", "URL di download non trovato", "\xe3\x83\x80\xe3\x82\xa6\xe3\x83\xb3\xe3\x83\xad\xe3\x83\xbc\xe3\x83\x89" "URL" "\xe3\x81\x8c\xe8\xa6\x8b\xe3\x81\xa4\xe3\x81\x8b\xe3\x82\x8a\xe3\x81\xbe\xe3\x81\x9b\xe3\x82\x93"}},
    {"err.createFile",       {"Konnte Zieldatei nicht anlegen: ", "Could not create target file: ", "No se pudo crear el archivo de destino: ", "Impossible de créer le fichier cible : ", "Impossibile creare il file di destinazione: ", "\xe3\x83\x95\xe3\x82\xa1\xe3\x82\xa4\xe3\x83\xab\xe3\x82\x92\xe4\xbd\x9c\xe6\x88\x90\xe3\x81\xa7\xe3\x81\x8d\xe3\x81\xbe\xe3\x81\x9b\xe3\x82\x93: "}},
    {"err.downloadFailed",   {"Download fehlgeschlagen: ", "Download failed: ", "Descarga fallida: ", "Échec du téléchargement : ", "Download non riuscito: ", "\xe3\x83\x80\xe3\x82\xa6\xe3\x83\xb3\xe3\x83\xad\xe3\x83\xbc\xe3\x83\x89\xe3\x81\xab\xe5\xa4\xb1\xe6\x95\x97\xe3\x81\x97\xe3\x81\xbe\xe3\x81\x97\xe3\x81\x9f: "}},
    {"err.noVersionInTitle", {"Release-Titel enthaelt keine Version (z.B. v1.1.0)", "Release title contains no version (e.g. v1.1.0)", "El título del release no contiene una versión (ej. v1.1.0)", "Le titre de la release ne contient pas de version (ex. v1.1.0)", "Il titolo della release non contiene una versione (es. v1.1.0)", "\xe3\x83\xaa\xe3\x83\xaa\xe3\x83\xbc\xe3\x82\xb9\xe5\x90\x8d\xe3\x81\xab\xe3\x83\x90\xe3\x83\xbc\xe3\x82\xb8\xe3\x83\xa7\xe3\x83\xb3\xe3\x81\x8c\xe3\x81\x82\xe3\x82\x8a\xe3\x81\xbe\xe3\x81\x9b\xe3\x82\x93 (\xe4\xbe\x8b: v1.1.0)"}},
    {"err.nroInvalid",       {"Heruntergeladene .nro ist ungültig (keine NRO-Datei)", "Downloaded .nro is invalid (not an NRO file)", "El .nro descargado no es válido (no es un archivo NRO)", "Le .nro téléchargé est invalide (pas un fichier NRO)", "Il .nro scaricato non è valido (non è un file NRO)", "\xe3\x83\x80\xe3\x82\xa6\xe3\x83\xb3\xe3\x83\xad\xe3\x83\xbc\xe3\x83\x89\xe3\x81\x97\xe3\x81\x9f.nro\xe3\x81\x8c\xe7\x84\xa1\xe5\x8a\xb9\xe3\x81\xa7\xe3\x81\x99"}},
    {"err.tmpRead",          {"Konnte temporäre Datei nicht lesen", "Could not read temporary file", "No se pudo leer el archivo temporal", "Impossible de lire le fichier temporaire", "Impossibile leggere il file temporaneo", "\xe4\xb8\x80\xe6\x99\x82\xe3\x83\x95\xe3\x82\xa1\xe3\x82\xa4\xe3\x83\xab\xe3\x82\x92\xe8\xaa\xad\xe3\x82\x81\xe3\x81\xbe\xe3\x81\x9b\xe3\x82\x93"}},
    {"err.replaceFailed",    {"Konnte App-Datei nicht ersetzen: ", "Could not replace app file: ", "No se pudo reemplazar el archivo de la app: ", "Impossible de remplacer le fichier de l'app : ", "Impossibile sostituire il file dell'app: ", "\xe3\x82\xa2\xe3\x83\x97\xe3\x83\xaa\xe3\x83\x95\xe3\x82\xa1\xe3\x82\xa4\xe3\x83\xab\xe3\x82\x92\xe7\xbd\xae\xe3\x81\x8d\xe6\x8f\x9b\xe3\x81\x88\xe3\x81\xa7\xe3\x81\x8d\xe3\x81\xbe\xe3\x81\x9b\xe3\x82\x93: "}},
    {"err.writeFile",        {"Schreibfehler (SD-Karte voll?): ", "Write error (SD card full?): ", "Error de escritura (¿tarjeta SD llena?): ", "Erreur d'écriture (carte SD pleine ?) : ", "Errore di scrittura (scheda SD piena?): ", "\xe6\x9b\xb8\xe3\x81\x8d\xe8\xbe\xbc\xe3\x81\xbf\xe3\x82\xa8\xe3\x83\xa9\xe3\x83\xbc (SD\xe3\x82\xab\xe3\x83\xbc\xe3\x83\x89\xe6\xba\x80\xe6\x9d\xaf?): "}},
    {"err.zipOpen",          {"Konnte ZIP-Datei nicht öffnen: ", "Could not open ZIP file: ", "No se pudo abrir el archivo ZIP: ", "Impossible d'ouvrir le fichier ZIP : ", "Impossibile aprire il file ZIP: ", "ZIP\xe3\x83\x95\xe3\x82\xa1\xe3\x82\xa4\xe3\x83\xab\xe3\x82\x92\xe9\x96\x8b\xe3\x81\x91\xe3\x81\xbe\xe3\x81\x9b\xe3\x82\x93: "}},
    {"err.zipBroken",        {"ZIP-Archiv ist ungültig oder beschädigt", "ZIP archive is invalid or corrupted", "El archivo ZIP no es válido o está dañado", "L'archive ZIP est invalide ou endommagée", "L'archivio ZIP non è valido o danneggiato", "ZIP\xe3\x83\x95\xe3\x82\xa1\xe3\x82\xa4\xe3\x83\xab\xe3\x81\x8c\xe7\x84\xa1\xe5\x8a\xb9\xe3\x81\x8b\xe7\xa0\xb4\xe6\x90\x8d\xe3\x81\x97\xe3\x81\xa6\xe3\x81\x84\xe3\x81\xbe\xe3\x81\x99"}},
    {"err.zipEntry",         {"Konnte ZIP-Eintrag nicht lesen: ", "Could not read ZIP entry: ", "No se pudo leer la entrada del ZIP: ", "Impossible de lire l'entrée du ZIP : ", "Impossibile leggere la voce dello ZIP: ", "ZIP\xe3\x82\xa8\xe3\x83\xb3\xe3\x83\x88\xe3\x83\xaa\xe3\x82\x92\xe8\xaa\xad\xe3\x82\x81\xe3\x81\xbe\xe3\x81\x9b\xe3\x82\x93: "}},
    {"err.unsafePath",       {"Unsicherer Pfad im ZIP: ", "Unsafe path in ZIP: ", "Ruta insegura en el ZIP: ", "Chemin non sûr dans le ZIP : ", "Percorso non sicuro nello ZIP: ", "ZIP\xe5\x86\x85\xe3\x81\xae\xe4\xb8\x8d\xe6\xad\xa3\xe3\x81\xaa\xe3\x83\x91\xe3\x82\xb9: "}},

    // ------------------------------------------------------------------
    // v2.0 - Holo-Glass-Shell (Sidebar, Seiten, Bibliothek, Detailseite).
    // Japanisch ab hier als literales UTF-8 (GCC kompiliert die Quelldatei
    // als UTF-8; identisches Ergebnis wie die \x-Escapes darueber).
    // ------------------------------------------------------------------
    {"nav.menu",     {"Menü", "Menu", "Menú", "Menu", "Menu", "メニュー"}},
    {"nav.home",     {"Start", "Home", "Inicio", "Accueil", "Home", "ホーム"}},
    {"nav.library",  {"Bibliothek", "Library", "Biblioteca", "Bibliothèque", "Libreria", "ライブラリ"}},
    {"nav.settings", {"Einstellungen", "Settings", "Ajustes", "Réglages", "Impostazioni", "設定"}},
    {"nav.log",      {"Protokoll", "Log", "Registro", "Journal", "Registro", "ログ"}},

    {"eyebrow.home",     {"Überblick", "Overview", "Resumen", "Aperçu", "Panoramica", "概要"}},
    {"eyebrow.library",  {"Stöbern", "Browse", "Explorar", "Parcourir", "Sfoglia", "ブラウズ"}},
    {"eyebrow.settings", {"Einrichten", "Configure", "Configurar", "Configurer", "Configura", "設定"}},
    {"eyebrow.log",      {"Verlauf", "History", "Historial", "Historique", "Cronologia", "履歴"}},
    {"eyebrow.game",     {"Spiel", "Game", "Juego", "Jeu", "Gioco", "ゲーム"}},

    {"sub.home",     {"Alles für deine Switch-Cheats — gesammelt, verwaltet, geliefert.", "Everything for your Switch cheats — collected, managed, delivered.", "Todo para tus trucos de Switch: recopilados, gestionados, entregados.", "Tout pour vos cheats Switch — collectés, gérés, livrés.", "Tutto per i tuoi trucchi Switch: raccolti, gestiti, consegnati.", "Switchのチートをすべて — 収集・管理・お届け。"}},
    {"sub.library",  {"Durchsuche und verwalte jeden Cheat in deiner Datenbank.", "Search, browse and manage every cheat in your database.", "Busca y gestiona cada truco de tu base de datos.", "Cherchez et gérez chaque cheat de votre base.", "Cerca e gestisci ogni trucco del tuo database.", "データベースのチートを検索・管理。"}},
    {"sub.settings", {"Sprache, App-Update und Daten an einem Ort.", "Language, app update and data in one place.", "Idioma, actualización y datos en un solo lugar.", "Langue, mise à jour et données au même endroit.", "Lingua, aggiornamento e dati in un unico posto.", "言語・アプリ更新・データをここで。"}},
    {"sub.log",      {"Was die App zuletzt getan hat.", "What the app has been doing.", "Lo que la app ha hecho últimamente.", "Ce que l'application a fait récemment.", "Cosa ha fatto l'app di recente.", "アプリの最近の動作。"}},

    {"stat.games",     {"Spiele in deiner Datenbank", "games in your database", "juegos en tu base de datos", "jeux dans votre base", "giochi nel tuo database", "データベースのゲーム数"}},
    {"stat.cheats",    {"Cheats gesamt", "cheats total", "trucos en total", "cheats au total", "trucchi in totale", "チート合計"}},
    {"stat.installed", {"Cheat-Dateien auf SD", "cheat files on SD", "archivos de trucos en la SD", "fichiers de cheats sur la SD", "file di trucchi sulla SD", "SDのチートファイル"}},
    {"stat.dbsize",    {"Datenbankgröße", "database size", "tamaño de la base", "taille de la base", "dimensione database", "データベースサイズ"}},

    {"home.card.title", {"Alles aus dem DevCatSKZ-GitHub-Repo holen", "Get everything from the DevCatSKZ GitHub repo", "Obtener todo del repo de GitHub de DevCatSKZ", "Tout récupérer depuis le dépôt GitHub DevCatSKZ", "Prendi tutto dal repo GitHub di DevCatSKZ", "DevCatSKZのGitHubリポジトリからすべて取得"}},
    {"home.card.d1",    {"Lädt die Datenbank (database.db) und alle Cheat-Dateien", "Downloads the database (database.db) and every cheat file", "Descarga la base de datos (database.db) y todos los archivos", "Télécharge la base (database.db) et tous les fichiers", "Scarica il database (database.db) e tutti i file", "データベース(database.db)と全チートファイルを"}},
    {"home.card.d2",    {"(switch-cheats.zip) im Atmosphère-Layout auf die SD-Karte.", "(switch-cheats.zip) onto the SD card in Atmosphère layout.", "(switch-cheats.zip) a la SD con el formato de Atmosphère.", "(switch-cheats.zip) sur la carte SD au format Atmosphère.", "(switch-cheats.zip) sulla SD nel formato Atmosphère.", "(switch-cheats.zip) SDカードへAtmosphère形式で保存します。"}},
    {"home.dbstate",    {"Datenbank-Stand: ", "Database state: ", "Estado de la base: ", "État de la base : ", "Stato del database: ", "データベースの状態: "}},
    {"home.btn.getall", {"Komplett holen", "Get everything", "Descargar todo", "Tout télécharger", "Scarica tutto", "すべて取得"}},
    {"home.btn.cheatsonly", {"Nur Cheats", "Cheats only", "Solo trucos", "Cheats seulement", "Solo trucchi", "チートのみ"}},
    {"home.recent",     {"Zuletzt aktualisiert", "Recently updated", "Actualizado recientemente", "Mises à jour récentes", "Aggiornati di recente", "最近の更新"}},
    {"home.norecent",   {"Noch keine Einträge.", "No entries yet.", "Aún no hay entradas.", "Pas encore d'entrées.", "Ancora nessuna voce.", "まだ項目がありません。"}},

    {"status.dbdownload", {"Lade database.db herunter...", "Downloading database.db...", "Descargando database.db...", "Téléchargement de database.db...", "Download di database.db...", "database.dbをダウンロード中..."}},
    {"log.dbupdated",     {"Datenbank aktualisiert.", "Database updated.", "Base de datos actualizada.", "Base de données mise à jour.", "Database aggiornato.", "データベースを更新しました。"}},
    {"log.dbrenamefail",  {"Konnte Datenbank nicht ersetzen.", "Could not replace the database.", "No se pudo reemplazar la base.", "Impossible de remplacer la base.", "Impossibile sostituire il database.", "データベースを置き換えられません。"}},
    {"log.kbdfail",       {"Tastatur nicht verfügbar.", "Keyboard not available.", "Teclado no disponible.", "Clavier indisponible.", "Tastiera non disponibile.", "キーボードを利用できません。"}},

    {"lib.search",         {"Suche", "Search", "Buscar", "Rechercher", "Cerca", "検索"}},
    {"lib.search.prefix",  {"Suche: ", "Search: ", "Búsqueda: ", "Recherche : ", "Ricerca: ", "検索: "}},
    {"lib.search.header",  {"Spiel suchen (Name oder Title-ID)", "Find a game (name or Title ID)", "Buscar juego (nombre o Title ID)", "Chercher un jeu (nom ou Title ID)", "Cerca un gioco (nome o Title ID)", "ゲームを検索（名前またはタイトルID）"}},
    {"lib.filter.all",       {"Alle", "All", "Todos", "Tous", "Tutti", "すべて"}},
    {"lib.filter.cheats",    {"Mit Cheats", "Has cheats", "Con trucos", "Avec cheats", "Con trucchi", "チートあり"}},
    {"lib.filter.installed", {"Installiert", "Installed", "Instalados", "Installés", "Installati", "インストール済み"}},
    {"lib.filter.favs",      {"Favoriten", "Favorites", "Favoritos", "Favoris", "Preferiti", "お気に入り"}},
    {"lib.games.suffix",   {" Spiele", " games", " juegos", " jeux", " giochi", " 件"}},
    {"lib.col.game",   {"Spiel", "Game", "Juego", "Jeu", "Gioco", "ゲーム"}},
    {"lib.col.region", {"Region", "Region", "Región", "Région", "Regione", "リージョン"}},
    {"lib.col.builds", {"Builds", "Builds", "Builds", "Builds", "Build", "ビルド"}},
    {"lib.col.cheats", {"Cheats", "Cheats", "Trucos", "Cheats", "Trucchi", "チート"}},
    {"lib.unnamed",    {"(unbenannt)", "(unnamed)", "(sin nombre)", "(sans nom)", "(senza nome)", "（名称未設定）"}},
    {"lib.nodb",       {"Keine Datenbank - auf der Start-Seite 'Komplett holen' drücken.", "No database yet - press 'Get everything' on the Home page.", "Sin base de datos: pulsa 'Descargar todo' en Inicio.", "Pas de base : utilisez 'Tout télécharger' sur l'accueil.", "Nessun database: premi 'Scarica tutto' nella Home.", "データベースがありません。ホームで「すべて取得」を実行してください。"}},
    {"lib.noresults",  {"Keine Treffer.", "No matches.", "Sin resultados.", "Aucun résultat.", "Nessun risultato.", "該当なし。"}},

    {"game.back",             {"Zurück zur Bibliothek", "Back to Library", "Volver a la biblioteca", "Retour à la bibliothèque", "Torna alla libreria", "ライブラリに戻る"}},
    {"game.titleid",          {"Title ID", "Title ID", "Title ID", "Title ID", "Title ID", "タイトルID"}},
    {"game.players",          {"Spieler", "Players", "Jugadores", "Joueurs", "Giocatori", "プレイ人数"}},
    {"game.languages",        {"Sprachen", "Languages", "Idiomas", "Langues", "Lingue", "対応言語"}},
    {"game.rating",           {"Einstufung", "Rating", "Clasificación", "Classification", "Classificazione", "レーティング"}},
    {"game.install.state",    {"Installiert", "Installed", "Instalado", "Installé", "Installato", "インストール状況"}},
    {"game.installed.suffix", {" installiert", " installed", " instalados", " installés", " installati", " インストール済み"}},
    {"game.builds.suffix",    {" Build(s)", " build(s)", " build(s)", " build(s)", " build", " ビルド"}},
    {"game.installed",        {"installiert", "installed", "instalado", "installé", "installato", "インストール済み"}},
    {"game.nobuilds",         {"Keine Builds gefunden.", "No builds found.", "No hay builds.", "Aucun build.", "Nessuna build.", "ビルドがありません。"}},
    {"game.cheats.none",      {"(keine Cheat-Namen hinterlegt)", "(no cheat names stored)", "(sin nombres de trucos)", "(pas de noms de cheats)", "(nessun nome di trucco)", "（チート名がありません）"}},
    {"game.hint",             {"Y = Cheats von CheatSlips laden   ZR = Editor", "Y = fetch cheats from CheatSlips   ZR = editor", "Y = trucos de CheatSlips   ZR = editor", "Y = cheats depuis CheatSlips   ZR = éditeur", "Y = trucchi da CheatSlips   ZR = editor", "Y = CheatSlipsから取得   ZR = エディター"}},

    {"set.section.lang", {"Sprache", "Language", "Idioma", "Langue", "Lingua", "言語"}},
    {"set.section.app",  {"App-Update", "App update", "Actualización de la app", "Mise à jour de l'app", "Aggiornamento app", "アプリの更新"}},
    {"set.reload",       {"Bibliothek neu laden", "Reload library", "Recargar biblioteca", "Recharger la bibliothèque", "Ricarica libreria", "ライブラリを再読み込み"}},
    {"set.reload.desc",  {"Liest die Datenbank neu ein und scannt die SD-Karte.", "Re-reads the database and rescans the SD card.", "Relee la base de datos y reescanea la SD.", "Relit la base et rescanne la carte SD.", "Rilegge il database e riscansiona la SD.", "データベースを再読み込みし、SDカードを再スキャンします。"}},
    {"set.reload.done",  {"Bibliothek neu geladen.", "Library reloaded.", "Biblioteca recargada.", "Bibliothèque rechargée.", "Libreria ricaricata.", "ライブラリを再読み込みしました。"}},

    {"log.empty", {"Noch keine Einträge.", "No entries yet.", "Aún no hay entradas.", "Pas encore d'entrées.", "Ancora nessuna voce.", "まだ項目がありません。"}},

    // ------------------------------------------------------------------
    // v2.0 Phase 2/3 - Quellen, CheatSlips, Galerie, Editor, Export/Clean
    // ------------------------------------------------------------------
    {"nav.sources",    {"Quellen", "Sources", "Fuentes", "Sources", "Fonti", "ソース"}},
    {"nav.cheatslips", {"CheatSlips", "CheatSlips", "CheatSlips", "CheatSlips", "CheatSlips", "CheatSlips"}},
    {"eyebrow.sources",    {"Sammeln", "Collect", "Recopilar", "Collecter", "Raccogli", "収集"}},
    {"eyebrow.cheatslips", {"Konto", "Account", "Cuenta", "Compte", "Account", "アカウント"}},
    {"sub.sources",    {"Community-Archive direkt auf die SD-Karte laden.", "Load community archives straight onto the SD card.", "Carga archivos de la comunidad directamente a la SD.", "Chargez les archives communautaires directement sur la SD.", "Carica gli archivi della community direttamente sulla SD.", "コミュニティのアーカイブを直接SDカードへ。"}},
    {"sub.cheatslips", {"API-Token verwalten und Cheats pro Spiel laden.", "Manage your API token and fetch cheats per game.", "Gestiona tu token y descarga trucos por juego.", "Gérez votre jeton et récupérez des cheats par jeu.", "Gestisci il token e scarica trucchi per gioco.", "APIトークンの管理とゲーム別チート取得。"}},

    {"src.hamlet.name",   {"Hamlet TitleDB (komplett)", "Hamlet TitleDB (complete)", "Hamlet TitleDB (completo)", "Hamlet TitleDB (complet)", "Hamlet TitleDB (completo)", "Hamlet TitleDB（完全版）"}},
    {"src.hamlet.desc",   {"Das komplette switch-cheats-db-Archiv (GBAtemp + TitleDB).", "The complete switch-cheats-db archive (GBAtemp + TitleDB).", "El archivo completo de switch-cheats-db.", "L'archive complète switch-cheats-db.", "L'archivio completo di switch-cheats-db.", "switch-cheats-dbの完全アーカイブ。"}},
    {"src.hamlet60.name", {"Hamlet 60FPS/Res/GFX", "Hamlet 60FPS/Res/GFX", "Hamlet 60FPS/Res/GFX", "Hamlet 60FPS/Res/GFX", "Hamlet 60FPS/Res/GFX", "Hamlet 60FPS/Res/GFX"}},
    {"src.hamlet60.desc", {"Nur Performance-/Grafik-Cheats (60 FPS, Auflösung).", "Performance/graphics cheats only (60 FPS, resolution).", "Solo trucos de rendimiento/gráficos.", "Uniquement les cheats performance/graphismes.", "Solo trucchi di prestazioni/grafica.", "パフォーマンス/グラフィック系チートのみ。"}},
    {"src.sthetix.name",  {"Sthetix TitleDB (aggregiert)", "Sthetix TitleDB (aggregated)", "Sthetix TitleDB (agregado)", "Sthetix TitleDB (agrégé)", "Sthetix TitleDB (aggregato)", "Sthetix TitleDB（集約版）"}},
    {"src.sthetix.desc",  {"Täglich aggregiert: GBAtemp + GFX + switch-cheats-db + CheatSlips.", "Aggregated daily: GBAtemp + GFX + switch-cheats-db + CheatSlips.", "Agregado a diario de varias fuentes.", "Agrégé quotidiennement depuis plusieurs sources.", "Aggregato ogni giorno da più fonti.", "毎日複数ソースを集約。"}},
    {"src.breeze.name",   {"Breeze / NXCheatCode", "Breeze / NXCheatCode", "Breeze / NXCheatCode", "Breeze / NXCheatCode", "Breeze / NXCheatCode", "Breeze / NXCheatCode"}},
    {"src.breeze.desc",   {"Die Breeze/EdiZon-SE-Datenbank (eigenes Code-Korpus).", "The Breeze/EdiZon-SE database (separate code corpus).", "La base de datos de Breeze/EdiZon-SE.", "La base Breeze/EdiZon-SE.", "Il database Breeze/EdiZon-SE.", "Breeze/EdiZon-SEのデータベース。"}},
    {"src.note",  {"A lädt das gewählte Archiv und installiert es ins Atmosphère-Layout.", "A downloads the selected archive and installs it in Atmosphère layout.", "A descarga el archivo elegido y lo instala en formato Atmosphère.", "A télécharge l'archive choisie et l'installe au format Atmosphère.", "A scarica l'archivio scelto e lo installa nel formato Atmosphère.", "Aで選択したアーカイブをAtmosphère形式でインストールします。"}},
    {"src.note2", {"Die übrigen Desktop-Quellen stecken bereits im Daten-Release (Start-Seite).", "The remaining desktop sources are already in the data release (Home page).", "Las demás fuentes ya están en el data-release (Inicio).", "Les autres sources sont déjà dans la data-release (Accueil).", "Le altre fonti sono già nel data-release (Home).", "その他のソースはデータリリース（ホーム）に含まれています。"}},
    {"status.downloading.src", {"Lade Archiv herunter...", "Downloading archive...", "Descargando archivo...", "Téléchargement de l'archive...", "Download dell'archivio...", "アーカイブをダウンロード中..."}},
    {"unit.files", {"Dateien", "files", "archivos", "fichiers", "file", "ファイル"}},
    {"unit.games", {"Spiele", "games", "juegos", "jeux", "giochi", "ゲーム"}},

    {"cs.fetching",      {"Hole Cheats von CheatSlips...", "Fetching cheats from CheatSlips...", "Obteniendo trucos de CheatSlips...", "Récupération des cheats depuis CheatSlips...", "Recupero trucchi da CheatSlips...", "CheatSlipsからチートを取得中..."}},
    {"cs.badtoken",      {"Token fehlt/ungültig - auf der CheatSlips-Seite eintragen.", "Token missing/invalid - set it on the CheatSlips page.", "Token ausente/no válido: configúralo en la página CheatSlips.", "Jeton absent/invalide : réglez-le sur la page CheatSlips.", "Token mancante/non valido: impostalo nella pagina CheatSlips.", "トークンが無効です。CheatSlipsページで設定してください。"}},
    {"cs.notfound",      {"Spiel nicht auf cheatslips.com.", "Game not on cheatslips.com.", "El juego no está en cheatslips.com.", "Jeu absent de cheatslips.com.", "Gioco non presente su cheatslips.com.", "cheatslips.comにないゲームです。"}},
    {"cs.tokenok",       {"Token funktioniert - Inhalte werden geliefert.", "Token works - content is being served.", "El token funciona.", "Le jeton fonctionne.", "Il token funziona.", "トークンは有効です。"}},
    {"cs.token.header",  {"CheatSlips-API-Token eingeben (leer = löschen)", "Enter CheatSlips API token (empty = clear)", "Introduce el token de CheatSlips (vacío = borrar)", "Saisir le jeton CheatSlips (vide = effacer)", "Inserisci il token CheatSlips (vuoto = cancella)", "CheatSlips APIトークンを入力（空=削除）"}},
    {"cs.token.title",   {"API-Token", "API token", "Token de API", "Jeton API", "Token API", "APIトークン"}},
    {"cs.token.set",     {"Token gespeichert: ", "Token saved: ", "Token guardado: ", "Jeton enregistré : ", "Token salvato: ", "トークン保存済み: "}},
    {"cs.token.none",    {"Kein Token - A drücken und Token aus deinem CheatSlips-Konto eintragen.", "No token - press A and paste the token from your CheatSlips account.", "Sin token: pulsa A e introduce el token de tu cuenta.", "Pas de jeton : appuyez sur A et saisissez le jeton du compte.", "Nessun token: premi A e inserisci il token del tuo account.", "トークン未設定。Aを押してアカウントのトークンを入力。"}},
    {"cs.token.hint",    {"A = Token eingeben/ändern   ·   Y = Token testen", "A = enter/change token   ·   Y = test token", "A = introducir/cambiar token   ·   Y = probar token", "A = saisir/modifier le jeton   ·   Y = tester", "A = inserisci/cambia token   ·   Y = prova token", "A = トークン入力/変更   ·   Y = テスト"}},
    {"cs.token.saved",   {"Token gespeichert.", "Token saved.", "Token guardado.", "Jeton enregistré.", "Token salvato.", "トークンを保存しました。"}},
    {"cs.token.cleared", {"Token gelöscht.", "Token cleared.", "Token borrado.", "Jeton effacé.", "Token cancellato.", "トークンを削除しました。"}},
    {"cs.token.missing", {"Kein CheatSlips-Token - zuerst auf der CheatSlips-Seite eintragen.", "No CheatSlips token - set one on the CheatSlips page first.", "Sin token de CheatSlips: configúralo primero.", "Pas de jeton CheatSlips : réglez-le d'abord.", "Nessun token CheatSlips: impostalo prima.", "CheatSlipsトークンがありません。先に設定してください。"}},
    {"cs.how.title",     {"So funktioniert's", "How it works", "Cómo funciona", "Comment ça marche", "Come funziona", "使い方"}},
    {"cs.how.1",         {"1. Kostenloses Konto auf cheatslips.com anlegen und das API-Token kopieren.", "1. Create a free account on cheatslips.com and copy the API token.", "1. Crea una cuenta gratis en cheatslips.com y copia el token.", "1. Créez un compte gratuit sur cheatslips.com et copiez le jeton.", "1. Crea un account gratuito su cheatslips.com e copia il token.", "1. cheatslips.comで無料アカウントを作成しトークンをコピー。"}},
    {"cs.how.2",         {"2. Token hier mit A eintragen (einmalig).", "2. Enter the token here with A (once).", "2. Introduce el token aquí con A (una vez).", "2. Saisissez le jeton ici avec A (une fois).", "2. Inserisci il token qui con A (una volta).", "2. ここでAを押してトークンを入力（1回のみ）。"}},
    {"cs.how.3",         {"3. Auf einer Spielseite Y drücken - die Cheats landen direkt auf der SD.", "3. Press Y on a game page - cheats go straight to the SD card.", "3. Pulsa Y en la página de un juego: los trucos van a la SD.", "3. Appuyez sur Y sur une page de jeu : les cheats vont sur la SD.", "3. Premi Y nella pagina di un gioco: i trucchi vanno sulla SD.", "3. ゲームページでYを押すとチートがSDへ保存されます。"}},
    {"cs.note",          {"Hinweis: Die Download-Quota deines Kontos gilt auch für die API.", "Note: your account's download quota also applies to the API.", "Nota: la cuota de tu cuenta también aplica a la API.", "Note : le quota de votre compte s'applique aussi à l'API.", "Nota: la quota del tuo account vale anche per l'API.", "注意: アカウントのダウンロード枠はAPIにも適用されます。"}},

    {"exp.title",       {"Cheats als ZIP exportieren", "Export cheats as ZIP", "Exportar trucos como ZIP", "Exporter les cheats en ZIP", "Esporta trucchi come ZIP", "チートをZIPにエクスポート"}},
    {"exp.desc",        {"Packt alle installierten Cheats nach sdmc:/switch-cheats-export.zip.", "Packs every installed cheat into sdmc:/switch-cheats-export.zip.", "Empaqueta todos los trucos en sdmc:/switch-cheats-export.zip.", "Regroupe tous les cheats dans sdmc:/switch-cheats-export.zip.", "Impacchetta tutti i trucchi in sdmc:/switch-cheats-export.zip.", "全チートをsdmc:/switch-cheats-export.zipへ。"}},
    {"exp.running",     {"Exportiere...", "Exporting...", "Exportando...", "Exportation...", "Esportazione...", "エクスポート中..."}},
    {"exp.done.prefix", {"Export fertig: ", "Export done: ", "Exportación lista: ", "Export terminé : ", "Esportazione completata: ", "エクスポート完了: "}},
    {"exp.done.suffix", {" Dateien -> sdmc:/switch-cheats-export.zip", " files -> sdmc:/switch-cheats-export.zip", " archivos -> sdmc:/switch-cheats-export.zip", " fichiers -> sdmc:/switch-cheats-export.zip", " file -> sdmc:/switch-cheats-export.zip", " ファイル -> sdmc:/switch-cheats-export.zip"}},

    {"clean.title",       {"Alle Cheats von der SD entfernen", "Remove all cheats from the SD card", "Eliminar todos los trucos de la SD", "Supprimer tous les cheats de la SD", "Rimuovi tutti i trucchi dalla SD", "SDからすべてのチートを削除"}},
    {"clean.desc",        {"Löscht alle Cheat-Dateien + Cover. Datenbank und Einstellungen bleiben.", "Deletes every cheat file + covers. Database and settings stay.", "Borra todos los trucos y carátulas. La base y ajustes quedan.", "Supprime cheats et jaquettes. Base et réglages conservés.", "Elimina trucchi e copertine. Database e impostazioni restano.", "チートとカバーを削除。DBと設定は残ります。"}},
    {"clean.confirm",     {"Wirklich? A erneut drücken zum Löschen - B bricht ab.", "Really? Press A again to delete - B cancels.", "¿Seguro? Pulsa A de nuevo para borrar.", "Vraiment ? Rappuyez sur A pour supprimer.", "Sicuro? Premi di nuovo A per eliminare.", "本当に削除しますか？もう一度Aで削除。"}},
    {"clean.running",     {"Entferne Cheats...", "Removing cheats...", "Eliminando trucos...", "Suppression des cheats...", "Rimozione trucchi...", "チートを削除中..."}},
    {"clean.done.prefix", {"Säuberung fertig: ", "Cleanup done: ", "Limpieza lista: ", "Nettoyage terminé : ", "Pulizia completata: ", "クリーンアップ完了: "}},
    {"clean.done.suffix", {" Dateien entfernt.", " files removed.", " archivos eliminados.", " fichiers supprimés.", " file rimossi.", " ファイルを削除しました。"}},

    {"ed.eyebrow",        {"Editor", "Editor", "Editor", "Éditeur", "Editor", "エディター"}},
    {"ed.back",           {"Zurück (ohne Speichern)", "Back (without saving)", "Volver (sin guardar)", "Retour (sans enregistrer)", "Indietro (senza salvare)", "戻る（保存しない）"}},
    {"ed.lines",          {"Zeilen", "lines", "líneas", "lignes", "righe", "行"}},
    {"ed.errors",         {"Fehler", "errors", "errores", "erreurs", "errori", "エラー"}},
    {"ed.dirty",          {"  ·  ungespeichert!", "  ·  unsaved!", "  ·  ¡sin guardar!", "  ·  non enregistré !", "  ·  non salvato!", "  ·  未保存！"}},
    {"ed.saved",          {"Cheat-Datei gespeichert.", "Cheat file saved.", "Archivo guardado.", "Fichier enregistré.", "File salvato.", "チートファイルを保存しました。"}},
    {"ed.discarded",      {"Editor ohne Speichern verlassen.", "Left the editor without saving.", "Saliste sin guardar.", "Éditeur quitté sans enregistrer.", "Uscito senza salvare.", "保存せずに終了しました。"}},
    {"ed.notinstalled",   {"Build ist nicht installiert - erst Cheats laden.", "Build is not installed - fetch cheats first.", "El build no está instalado.", "Le build n'est pas installé.", "La build non è installata.", "ビルドが未インストールです。"}},
    {"ed.line.header",    {"Zeile bearbeiten", "Edit line", "Editar línea", "Modifier la ligne", "Modifica riga", "行を編集"}},
    {"ed.newline.header", {"Neue Zeile einfügen", "Insert new line", "Insertar línea nueva", "Insérer une ligne", "Inserisci nuova riga", "新しい行を挿入"}},

    {"gal.cheats.suffix", {" Cheats", " cheats", " trucos", " cheats", " trucchi", " チート"}},
    {"footer.editor",     {"A Zeile bearbeiten   Y Neue Zeile   X Löschen   - Speichern   B Zurück", "A Edit line   Y New line   X Delete   - Save   B Back", "A Editar   Y Nueva línea   X Borrar   - Guardar   B Volver", "A Modifier   Y Nouvelle ligne   X Supprimer   - Enregistrer   B Retour", "A Modifica   Y Nuova riga   X Elimina   - Salva   B Indietro", "A 編集   Y 新規行   X 削除   - 保存   B 戻る"}},
    {"footer.cheatslips", {"A Token eingeben   Y Token testen   L/R Seite", "A Enter token   Y Test token   L/R Page", "A Token   Y Probar   L/R Página", "A Jeton   Y Tester   L/R Page", "A Token   Y Prova   L/R Pagina", "A トークン入力   Y テスト   L/R ページ"}},
    {"footer.home", {"A Komplett holen   X Nur Cheats   Y Prüfen   L/R Seite", "A Get everything   X Cheats only   Y Check   L/R Page", "A Descargar todo   X Solo trucos   Y Comprobar   L/R Página", "A Tout télécharger   X Cheats seulement   Y Vérifier   L/R Page", "A Scarica tutto   X Solo trucchi   Y Verifica   L/R Pagina", "A すべて取得   X チートのみ   Y 確認   L/R ページ"}},
};
// clang-format on

const int kTableSize = sizeof(kTable) / sizeof(kTable[0]);

// atomic, weil tr() auch aus den Hintergrund-Workern gerufen wird, waehrend
// der UI-Thread per L/R (auch bei laufender Aktion erlaubt) umschalten kann.
std::atomic<int> g_lang{static_cast<int>(Lang::EN)};

const char* kLangCodes[6] = {"DE", "EN", "ES", "FR", "IT", "JA"};

void persist() {
    // Zielordner ggf. anlegen: vor dem ersten Download existiert
    // sdmc:/switch/SwitchCheatsDownloader noch nicht - ohne mkdir ginge die
    // Sprachwahl dann verloren (fopen schluege still fehl).
    mkdir("sdmc:/switch", 0777);
    mkdir(cfg::kAppDir, 0777);
    FILE* f = fopen(cfg::kLangFile, "wb");
    if (!f) return;
    // Sprachkuerzel als Text ("DE", "EN", ...) - konsistent zum Desktop-Tool
    // und robust gegen zukuenftige Umsortierung des Lang-Enums.
    const char* code = kLangCodes[g_lang.load()];
    fwrite(code, 1, strlen(code), f);
    fclose(f);
}

Lang detectSystemLang() {
    Lang result = Lang::EN;
    if (R_FAILED(setInitialize())) return result;

    u64 code = 0;
    if (R_SUCCEEDED(setGetSystemLanguage(&code))) {
        SetLanguage sl;
        if (R_SUCCEEDED(setMakeLanguage(code, &sl))) {
            switch (sl) {
                case SetLanguage_DE: result = Lang::DE; break;
                case SetLanguage_JA: result = Lang::JA; break;
                case SetLanguage_FR:
                case SetLanguage_FRCA: result = Lang::FR; break;
                case SetLanguage_IT: result = Lang::IT; break;
                case SetLanguage_ES:
                case SetLanguage_ES419: result = Lang::ES; break;
                default: result = Lang::EN; break;
            }
        }
    }
    setExit();
    return result;
}

} // namespace

void init() {
    g_lang = static_cast<int>(detectSystemLang());

    FILE* f = fopen(cfg::kLangFile, "rb");
    if (!f) return;
    char buf[16] = {0};
    size_t n = fread(buf, 1, sizeof(buf) - 1, f);
    fclose(f);

    // Aktuelles Format: Sprachkuerzel als Text ("DE", "EN", ...).
    for (int i = 0; i < static_cast<int>(Lang::Count); i++) {
        if (n >= 2 && strncmp(buf, kLangCodes[i], 2) == 0 &&
            (n == 2 || buf[2] == '\0' || buf[2] == '\n' || buf[2] == '\r')) {
            g_lang = i;
            return;
        }
    }
    // Altes Format (v1.0.0): roher int (4 Bytes, little-endian).
    if (n == 4) {
        int idx = 0;
        memcpy(&idx, buf, 4);
        if (idx >= 0 && idx < static_cast<int>(Lang::Count)) g_lang = idx;
    }
}

void setLang(Lang lang) {
    g_lang = static_cast<int>(lang);
    persist();
}

Lang getLang() { return static_cast<Lang>(g_lang.load()); }

Lang nextLang() {
    int idx = (g_lang.load() + 1) % static_cast<int>(Lang::Count);
    setLang(static_cast<Lang>(idx));
    return getLang();
}

Lang prevLang() {
    int idx = g_lang.load() - 1;
    if (idx < 0) idx = static_cast<int>(Lang::Count) - 1;
    setLang(static_cast<Lang>(idx));
    return getLang();
}

const char* langCode(Lang lang) {
    int idx = static_cast<int>(lang);
    if (idx < 0 || idx >= 6) return "EN";
    return kLangCodes[idx];
}

const char* tr(const char* key) {
    int li = g_lang.load();
    if (li < 0 || li >= static_cast<int>(Lang::Count)) li = static_cast<int>(Lang::EN);
    for (int i = 0; i < kTableSize; i++) {
        if (strcmp(kTable[i].key, key) == 0) {
            return kTable[i].text[li];
        }
    }
    return key; // Fallback: Key selbst zurueckgeben (erleichtert das Debuggen fehlender Eintraege)
}

} // namespace i18n
