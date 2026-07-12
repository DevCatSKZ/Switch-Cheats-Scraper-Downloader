#pragma once
// ---------------------------------------------------------------------------
// Speicherstand-Verwaltung: Saves erkennen, sichern (Backup) und
// wiederherstellen (Restore) - portiert nach dem Vorbild von Checkpoint.
//
//   Erkennen  -> fsOpenSaveDataInfoReader (Account-Saves) + account (Nicknames)
//   Mounten   -> fsOpen_SaveData -> fsdevMountDevice("save")  => "save:/..."
//   Backup    -> rekursiv "save:/" nach sdmc kopieren
//   Restore   -> "save:/" leeren, Backup zurueckkopieren, fsdevCommitDevice
//
// WICHTIG (Checkpoint-Lehre): nach dem Schreiben in den Save MUSS
// fsdevCommitDevice("save") aufgerufen werden, sonst gehen alle Aenderungen
// beim Unmount verloren. Der Mount-Name ("save") ist ueberall identisch.
//
// Threading: alle Aufrufe laufen im Hintergrund-Worker; account wird ueber
// sysinfo::init() (idempotent) bereitgestellt.
// ---------------------------------------------------------------------------
#include <switch.h>
#include <string>
#include <vector>
#include <cstdint>
#include <functional>

namespace saves {

using LogFn = std::function<void(const std::string&)>;

// Ein Account-Speicherstand: welcher Nutzer hat fuer welches Spiel einen Save.
struct SaveEntry {
    uint64_t titleId = 0;
    AccountUid uid = {};       // Besitzer (Account); {0} = geraeteweit
    std::string user;          // Nickname ("" wenn nicht aufloesbar)
    std::string game;          // Spielname (aufgeloest via sysinfo, "" moeglich)
};

// Ein bereits auf SD liegendes Backup.
struct Backup {
    std::string path;          // voller sdmc-Pfad des Backup-Ordners
    std::string label;         // Ordnername (Zeitstempel)
};

// Alle Account-Saves auf der Konsole (nach Spielname sortiert). Loest die
// Nutzer-Nicknames und Spielnamen gleich mit auf.
std::vector<SaveEntry> listSaves();

// Saves nur fuer eine bestimmte Title-ID (Basis-ID, low nibble egal).
std::vector<SaveEntry> savesForTitle(uint64_t titleId);

// Backup-Wurzelordner fuer eine Title-ID (wird bei Bedarf angelegt).
std::string backupDir(uint64_t titleId);

// Vorhandene Backups einer Title-ID (neueste zuerst).
std::vector<Backup> listBackups(uint64_t titleId);

// Sichert den Save (titleId,uid) unter einem Zeitstempel-Ordner. Bei Erfolg
// steht der Zielpfad in outPath. err erhaelt eine Kurzbeschreibung bei Fehlern.
bool backup(const SaveEntry& e, std::string& outPath, std::string& err,
            const LogFn& log = {});

// Stellt einen Save aus einem Backup-Ordner wieder her (leert den Save zuvor
// vollstaendig und committet danach). ACHTUNG: ueberschreibt den aktuellen
// Speicherstand des Nutzers.
bool restore(const SaveEntry& e, const std::string& backupPath,
             std::string& err, const LogFn& log = {});

// Loescht ein Backup vom SD (rekursiv).
bool deleteBackup(const std::string& backupPath);

} // namespace saves
