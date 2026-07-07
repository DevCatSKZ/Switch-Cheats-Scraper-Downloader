#pragma once
#include <string>

// ---------------------------------------------------------------------------
// Mehrsprachigkeit (Deutsch, Englisch, Spanisch, Franzoesisch, Italienisch,
// Japanisch) - analog zu i18n.py im Desktop-Tool.
// Die Systemsprache der Switch wird automatisch erkannt (setGetSystemLanguage);
// der Nutzer kann per L/R durchschalten, die Wahl wird persistiert.
// ---------------------------------------------------------------------------

namespace i18n {

enum class Lang : int { DE = 0, EN, ES, FR, IT, JA, Count };

// Erkennt die Systemsprache und laedt eine evtl. gespeicherte manuelle Wahl.
void init();

void setLang(Lang lang);
Lang getLang();
Lang nextLang();     // schaltet zyklisch weiter (fuer L/R), gibt neue Sprache zurueck
Lang prevLang();

// Kuerzel fuer die Anzeige (DE/EN/ES/FR/IT/JA)
const char* langCode(Lang lang);

// Uebersetzung fuer den aktuellen Sprachstand.
const char* tr(const char* key);

} // namespace i18n
