/* SPDX-License-Identifier: GPL-3.0-or-later
 *
 * "Gehoert dieses Passwort zu diesem Menschen?" - die ganze Frage, und
 * nichts von der Antwort steht in der Oberflaeche.
 *
 * WARUM DAS EINE EIGENE UEBERSETZUNGSEINHEIT IST
 *     Zwei Gruende, und der zweite ist der wichtigere.
 *
 *     ERSTENS: es ist die einzige Frage in diesem Programm, deren
 *     falsche Antwort jemanden hereinlaesst. Eine Frage, die man ohne
 *     Bildschirm stellen kann, kann man auch ohne Bildschirm MESSEN -
 *     tests/lock/auth_probe.c uebersetzt genau die Datei mit, die auch
 *     im ausgelieferten Programm steckt, und faehrt sie gegen einen
 *     PAM-Stapel, den der Test selbst schreibt. Ohne die Trennung
 *     muesste ein solcher Test einen Compositor, eine Anzeige und eine
 *     Tastatur beibringen, um eine Zeichenkette zu vergleichen.
 *
 *     ZWEITENS: derselbe Bildschirm soll spaeter auch die ANMELDUNG
 *     tragen koennen. Bei Apple sind Anmelde- und Sperrbildschirm
 *     dieselbe Flaeche, und das ist der Grund, aus dem es
 *     zusammengehoerig wirkt. Bei ZepOS sind es heute zwei fremde
 *     Programme - regreet fuer die Anmeldung, hyprlock fuers Sperren -,
 *     und dieses hier ersetzt das zweite.
 *
 * DER EINE UNTERSCHIED ZWISCHEN SPERREN UND ANMELDEN
 *     Woher die Antwort kommt. Sonst nichts:
 *
 *         Sperren    PAM direkt, als der angemeldete Benutzer.
 *                    lock/zepos-lock-pam.c.
 *         Anmelden   greetd, ueber seinen JSON-Sockel in $GREETD_SOCK.
 *                    greetd startet ein BELIEBIGES Programm als Maske
 *                    und fuehrt die Authentisierung selbst; die Maske
 *                    schickt create_session / post_auth_message_response
 *                    und bekommt success oder auth_message zurueck.
 *                    src/login/greetd.toml und src/bin/zepos-greeter
 *                    zeigen, wie ZepOS das heute mit regreet macht.
 *
 *     Fenster, Hintergrund, Uhr, Feld, Fehlermeldung und das Stylesheet
 *     aus brand.py sind in beiden Faellen dasselbe. Deshalb ist die
 *     Pruefung hier abgetrennt statt in die Oberflaeche geflochten: die
 *     Anmeldung waere dann ein zweites HINTERTEIL - eine zweite Datei,
 *     die genau diese drei Funktionen erfuellt - und kein zweites
 *     Programm.
 *
 *     DIESER KOPF NENNT DESHALB PAM NICHT MEHR ALS TYP. Er bindet
 *     security/pam_appl.h nicht ein, er hat keine PAM-Konstante in
 *     seiner Schnittstelle, und `code` unten ist eine Zahl, die der
 *     Hinterbau vergibt. lock/zepos-lock.c kennt ausschliesslich, was
 *     hier steht - tests/lock/test_auth.py haelt das fest, damit die
 *     Naht nicht beim naechsten Anfassen wieder zuwaechst.
 *
 * WAS HIER ABSICHTLICH NICHT STEHT
 *     Eine Funktionszeigertabelle, mit der man den Hinterbau zur
 *     Laufzeit umschaltet. Es gibt heute einen, und ein Sperrbildschirm,
 *     der sich aussuchen kann, wen er nach dem Passwort fragt, ist
 *     genau ein Angriffsweg mehr. Die Auswahl gehoert an den Linker:
 *     lock/meson.build baut zepos-lock gegen zepos-lock-pam.c, und ein
 *     kuenftiges zepos-greeter baute dieselbe Oberflaeche gegen eine
 *     andere Datei.
 */
#ifndef ZEPOS_LOCK_AUTH_H
#define ZEPOS_LOCK_AUTH_H

/* Der Wert von ZepAuthResult.code, wenn der Hinterbau ueberhaupt nicht
 * antworten konnte - kein Dienst, kein Sockel, kein Benutzername.
 *
 * Er ist ungleich null, weil jeder Code ungleich null hier eine
 * Ablehnung ist und `accepted` ohnehin die Entscheidung traegt. Eine
 * eigene Zahl statt einer geliehenen PAM-Konstante, damit dieser Kopf
 * ohne PAM auskommt. */
#define ZEP_AUTH_UNAVAILABLE (-1)

typedef struct {
    /* 1 ausschliesslich dann, wenn der Hinterbau ausdruecklich
     * zugestimmt hat. Jeder andere Ausgang, auch ein unbekannter, ist
     * eine Ablehnung - siehe die Begruendung an der Zuweisung in
     * lock/zepos-lock-pam.c. */
    int accepted;
    /* Was der Hinterbau geantwortet hat, ungefiltert, fuer die
     * Fehlersuche. Beim PAM-Hinterbau ist das der PAM-Rueckgabewert. */
    int code;
    /* Was der Hinterbau zu SAGEN hatte - beim PAM-Hinterbau die Zeilen
     * aus PAM_ERROR_MSG und PAM_TEXT_INFO, sonst pam_strerror(). Gehoert
     * dem Aufrufer, der es mit zep_auth_result_clear() wieder loswird.
     * Kann NULL sein. */
    char *reason;
} ZepAuthResult;

/* Fragt den Hinterbau, ob dieses Passwort zu diesem Benutzer gehoert.
 *
 * Blockiert - der PAM-Hinterbau ruft ueber pam_unix das Hilfsprogramm
 * /usr/bin/unix_chkpwd, und pam_faildelay laesst nach einem Fehlschlag
 * absichtlich Sekunden vergehen. Der Aufrufer hat das in einen eigenen
 * Faden zu legen; der Kopf von zepos-lock.c sagt, warum das hier nicht
 * verhandelbar ist.
 */
void zep_auth_check(const char *user, const char *password,
                    ZepAuthResult *result);

/* Gibt result->reason frei und setzt die Struktur auf Ablehnung zurueck.
 *
 * Auf Ablehnung und nicht auf Null: eine geleerte Struktur, die
 * "angenommen" bedeutet, waere die eine Nachlaessigkeit, die in diesem
 * Programm jemanden hereinliesse.
 */
void zep_auth_result_clear(ZepAuthResult *result);

#endif /* ZEPOS_LOCK_AUTH_H */
