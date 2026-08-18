/* SPDX-License-Identifier: GPL-3.0-or-later
 *
 * DER PAM-HINTERBAU von zepos-lock-auth.h - eine von zwei denkbaren
 * Antworten auf "gehoert dieses Passwort zu diesem Menschen?".
 *
 * Diese hier fragt PAM direkt und laeuft als der angemeldete Benutzer;
 * das ist der Fall SPERREN. Der andere Fall waere ANMELDEN, wo greetd
 * die Authentisierung fuehrt und die Maske nur seinen JSON-Sockel
 * bedient - dieselbe Oberflaeche, dieselben drei Funktionen, eine
 * andere Datei. Der Kopf von zepos-lock-auth.h fuehrt die Aufteilung
 * aus; lock/meson.build entscheidet mit der Quelldateiliste, welcher
 * Hinterbau in ein Programm kommt.
 *
 * Der Dienstname steht deshalb HIER und nicht im Kopf: er ist eine
 * Eigenschaft dieses Hinterbaus, und ein greetd-Hinterbau haette
 * keinen.
 */
/* strdup() ist POSIX und nicht ISO C, und meson stellt hier `c11` ein -
 * ohne diese Zeile deklariert glibc es nicht, gcc nimmt den impliziten
 * int-Rueckgabewert an und der Bau faellt mit -Wint-conversion aus.
 * Muss vor dem ersten Systemkopf stehen. */
#define _DEFAULT_SOURCE

#include "zepos-lock-auth.h"

#include <security/pam_appl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Der Name der eigenen Datei unter /etc/pam.d/.
 *
 * EIGEN, UND NICHT DIE EINES ANDEREN PROGRAMMS
 *     hyprlock brachte /etc/pam.d/hyprlock mit vier Zeilen mit, davon
 *     eine wirksame: `auth include login`. swaylock und gtklock auf
 *     derselben Maschine haben wortgleich dasselbe. Alle drei leihen
 *     sich damit den Stapel der Textanmeldung, und das ist der Grund,
 *     aus dem hier eine eigene Datei steht statt eines
 *     `include hyprlock`: ein Programm, das den PAM-Dienst eines
 *     anderen benutzt, wird stumm zu einem Programm ohne
 *     Authentisierung, sobald dieses andere Paket entfernt wird - und
 *     genau das passiert hier, denn hyprlock geht mit dieser Aenderung.
 *
 * WAS PASSIERT, WENN DIE DATEI FEHLT - GEMESSEN, NICHT GEHOFFT
 *     Linux-PAM faellt fuer einen unbekannten Dienst auf
 *     /etc/pam.d/other zurueck. Gemessen am 12.08.2026 auf dieser
 *     Maschine: Archs `other` ist viermal pam_deny.so und viermal
 *     pam_warn.so, also faellt der Rueckfall ZU. Und wenn auch `other`
 *     fehlt, antwortet pam_start() selbst mit 26 (PAM_ABORT), was
 *     zep_auth_check() unten als Ablehnung behandelt.
 *
 *     Beide Wege wurden im Namensraum eines `unshare -Urm` mit eigenem
 *     /etc/pam.d nachgestellt; die Messung steht in
 *     tests/lock/test_auth.py.
 */
#define ZEPOS_LOCK_PAM_SERVICE "zepos-lock"

typedef struct {
    const char *password;
    const char *user;
    char *notice;       /* was PAM gesagt hat, Zeile fuer Zeile */
} ZepConversation;

static char *
zep_append_line(char *existing, const char *line)
{
    size_t length;
    char *joined;

    if (line == NULL || line[0] == '\0')
        return existing;
    if (existing == NULL) {
        joined = strdup(line);
        return joined != NULL ? joined : existing;
    }
    length = strlen(existing) + 1 + strlen(line) + 1;
    joined = malloc(length);
    if (joined == NULL)
        return existing;
    snprintf(joined, length, "%s\n%s", existing, line);
    free(existing);
    return joined;
}

/* Das Gespraech mit PAM.
 *
 * WARUM EIN ECHOENDES FELD NICHT DAS PASSWORT BEKOMMT
 *     PAM_PROMPT_ECHO_ON ist die Aufforderung, etwas einzugeben, das man
 *     dabei SIEHT - der Benutzername, eine Token-Nummer, eine
 *     Rueckfrage. Eine Antwortfunktion, die auf jede Aufforderung das
 *     Passwort schickt, schickt es damit an jedes Modul, das eine solche
 *     Frage stellt, und diese Module rechnen nicht damit, dass ihre
 *     Antwort geheim ist: pam_echo protokolliert, pam_exec kann sie
 *     ohne expose_authtok gar nicht anfordern und bekaeme sie trotzdem.
 *     Also bekommt ein echoendes Feld den Benutzernamen, den PAM
 *     ohnehin schon hat, und nur PAM_PROMPT_ECHO_OFF bekommt das
 *     Passwort.
 *
 * WARUM DIE MELDUNGEN AUFGEHOBEN WERDEN
 *     Weil die interessanteste Ablehnung nicht "falsches Passwort"
 *     heisst. Archs Stapel fuehrt pam_faillock; nach `deny` Fehlversuchen
 *     (Vorgabe 3) weist er auch das RICHTIGE Passwort ab und sagt
 *     dazu, wie lange noch. Ein Sperrbildschirm, der darauf mit
 *     "Falsches Passwort" antwortet, schickt seinen Benutzer los, ein
 *     Passwort zu suchen, das er schon hat. Also zeigt dieser hier, was
 *     PAM gesagt hat.
 */
static int
zep_conversation(int count, const struct pam_message **messages,
                 struct pam_response **responses, void *data)
{
    ZepConversation *state = data;
    struct pam_response *replies;
    int index;

    if (count <= 0 || count > PAM_MAX_NUM_MSG)
        return PAM_CONV_ERR;

    replies = calloc((size_t) count, sizeof *replies);
    if (replies == NULL)
        return PAM_BUF_ERR;

    for (index = 0; index < count; index++) {
        const char *text = messages[index]->msg;

        switch (messages[index]->msg_style) {
        case PAM_PROMPT_ECHO_OFF:
            replies[index].resp =
                strdup(state->password != NULL ? state->password : "");
            break;
        case PAM_PROMPT_ECHO_ON:
            replies[index].resp =
                strdup(state->user != NULL ? state->user : "");
            break;
        case PAM_ERROR_MSG:
        case PAM_TEXT_INFO:
            state->notice = zep_append_line(state->notice, text);
            break;
        default:
            break;
        }

        if (messages[index]->msg_style == PAM_PROMPT_ECHO_OFF
            || messages[index]->msg_style == PAM_PROMPT_ECHO_ON) {
            if (replies[index].resp == NULL) {
                int done;
                for (done = 0; done < index; done++)
                    free(replies[done].resp);
                free(replies);
                return PAM_BUF_ERR;
            }
        }
    }

    *responses = replies;
    return PAM_SUCCESS;
}

void
zep_auth_result_clear(ZepAuthResult *result)
{
    if (result == NULL)
        return;
    free(result->reason);
    result->reason = NULL;
    result->accepted = 0;
    result->code = ZEP_AUTH_UNAVAILABLE;
}

void
zep_auth_check(const char *user, const char *password, ZepAuthResult *result)
{
    ZepConversation state = { password, user, NULL };
    struct pam_conv conversation = { zep_conversation, &state };
    pam_handle_t *pam = NULL;
    const char *strerror_text;
    int code;

    if (result == NULL)
        return;
    result->reason = NULL;
    result->accepted = 0;
    result->code = ZEP_AUTH_UNAVAILABLE;

    if (user == NULL || user[0] == '\0') {
        /* Ohne Benutzernamen gibt es niemanden, gegen den zu pruefen
         * waere. PAM wuerde ihn ueber das Gespraech erfragen und die
         * Antwortfunktion oben gaebe eine leere Zeichenkette zurueck -
         * also eine Pruefung gegen ein Konto namens "". Lieber hier
         * abweisen, wo der Grund noch dasteht. */
        result->reason = strdup("kein Benutzername");
        return;
    }

    code = pam_start(ZEPOS_LOCK_PAM_SERVICE, user, &conversation, &pam);
    if (code != PAM_SUCCESS) {
        /* Der Fall, der eintritt, wenn es weder /etc/pam.d/zepos-lock
         * noch /etc/pam.d/other gibt: gemessen 26 (PAM_ABORT). pam ist
         * dann nicht benutzbar, also kommt der Text nicht aus
         * pam_strerror(). */
        result->code = code;
        result->reason = strdup("PAM liess sich nicht starten");
        free(state.notice);
        return;
    }

    code = pam_authenticate(pam, 0);

    /* DIE ZEILE, AUF DIE ES ANKOMMT.
     *
     * Gleich PAM_SUCCESS, nicht ungleich PAM_AUTH_ERR. PAM kennt ein
     * Dutzend Rueckgabewerte, und nur einer davon heisst "dieser Mensch
     * ist, wer er sagt". Eine Pruefung auf ungleich PAM_AUTH_ERR liesse
     * PAM_PERM_DENIED, PAM_MAXTRIES, PAM_ABORT, PAM_CRED_INSUFFICIENT
     * und jeden kuenftigen Code als Erfolg durch - also genau die
     * Faelle, in denen der Stapel abgebrochen hat, statt zuzustimmen.
     *
     * tests/lock/test_auth.py bricht diese Zeile einmal und faehrt einen
     * pam_deny-Stapel dagegen, der PAM_PERM_DENIED liefert. */
    result->accepted = (code == PAM_SUCCESS) ? 1 : 0;
    result->code = code;

    if (state.notice != NULL) {
        result->reason = state.notice;
        state.notice = NULL;
    } else {
        /* Vor pam_end kopieren: danach zeigt der Handle ins Nichts. */
        strerror_text = pam_strerror(pam, code);
        result->reason = strerror_text != NULL ? strdup(strerror_text) : NULL;
    }

    pam_end(pam, code);
    free(state.notice);
}
