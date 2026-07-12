// Stubs fuer POSIX-Funktionen, die SQLites unix-VFS in seiner Syscall-Tabelle
// referenziert, die aber in newlib/libnx fehlen. Beide werden nur fuer
// chown-nach-Anlegen von Journal-Dateien bzw. Rechte-Checks benutzt - unsere
// Datenbank wird ausschliesslich READ-ONLY geoeffnet, die Aufrufe sind also
// tote Pfade. No-op-Implementierungen sind hier korrekt.
#include <sys/types.h>

int fchown(int fd, uid_t owner, gid_t group) {
    (void)fd;
    (void)owner;
    (void)group;
    return 0;
}

uid_t geteuid(void) {
    return 0;
}
