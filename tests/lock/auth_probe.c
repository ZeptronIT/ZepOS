/* SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Faehrt lock/zepos-lock-pam.c ohne Bildschirm.
 *
 * Es uebersetzt GENAU DIE DATEI mit, die auch im ausgelieferten
 * Programm steckt - nicht eine Nachbildung ihrer Logik. Was hier
 * gemessen wird, ist deshalb der Code, der auf dem Schreibtisch des
 * Nutzers ueber ein Passwort entscheidet.
 *
 *     auth_probe BENUTZER PASSWORT
 *
 *     Rueckgabe 0   PAM hat angenommen
 *     Rueckgabe 1   PAM hat abgelehnt
 *     Rueckgabe 64  falscher Aufruf
 *
 * Auf stdout steht eine Zeile "accepted=<0|1> code=<n>", damit ein Test
 * die Ablehnung von einem Absturz unterscheiden kann, und danach der
 * Text, den PAM zu sagen hatte.
 */
#include <stdio.h>
#include <stdlib.h>

#include "zepos-lock-auth.h"

int
main(int argc, char **argv)
{
    ZepAuthResult result;

    if (argc != 3) {
        fprintf(stderr, "auth_probe BENUTZER PASSWORT\n");
        return 64;
    }

    zep_auth_check(argv[1], argv[2], &result);
    printf("accepted=%d code=%d\n", result.accepted, result.code);
    printf("reason=%s\n", result.reason != NULL ? result.reason : "");
    fflush(stdout);

    {
        int accepted = result.accepted;
        zep_auth_result_clear(&result);
        return accepted ? 0 : 1;
    }
}
