#pragma once
// ---------------------------------------------------------------------------
// Cover-Cache fuer die Galerie: laedt Cover-URLs (image-Spalte der DB) in
// einem Hintergrund-Thread nach sdmc:/switch/SwitchCheatsDownloader/covers/
// (<TID>.jpg) und stellt sie als SDL_Texture bereit. Anfragen stellt der
// Renderer nur fuer SICHTBARE Kacheln - wie der Lazy-Load der Windows-Galerie.
// ---------------------------------------------------------------------------
#include <SDL.h>
#include <string>

namespace covers {

void init();      // Worker starten (laedt erst, wenn curl bereit ist)
void shutdown();  // Worker beenden, Texturen freigeben

// Fordert das Cover fuer tid an (idempotent). url darf leer sein -> no-op.
void request(const std::string& tid, const std::string& url);

// Liefert die Textur (laedt sie bei Bedarf von der SD in den GPU-Speicher)
// oder nullptr, solange nichts vorhanden ist. w/h werden gesetzt.
SDL_Texture* get(SDL_Renderer* r, const std::string& tid, int& w, int& h);

int cachedFiles(); // Anzahl Cover-Dateien auf SD (fuer Statistik/Clean)
void clearDisk();  // loescht den covers-Ordner (Reset/Clean)

} // namespace covers
