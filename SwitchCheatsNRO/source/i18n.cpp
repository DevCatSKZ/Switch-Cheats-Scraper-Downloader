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
    {"footer.nav",     {"Hoch/Runter Navigieren   L/R Sprache   A Auswählen   + Beenden", "Up/Down Navigate   L/R Language   A Select   + Exit", "Arriba/Abajo Navegar   L/R Idioma   A Seleccionar   + Salir", "Haut/Bas Naviguer   L/R Langue   A Valider   + Quitter", "Su/Giù Naviga   L/R Lingua   A Seleziona   + Esci", "\xe4\xb8\x8a\xe4\xb8\x8b \xe7\xa7\xbb\xe5\x8b\x95   L/R \xe8\xa8\x80\xe8\xaa\x9e   A \xe6\xb1\xba\xe5\xae\x9a   + \xe7\xb5\x82\xe4\xba\x86"}},

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
