# SPDX-License-Identifier: GPL-3.0-or-later
"""Faehrt archinstalls ECHTES _verify_service_stop() - einmal so, wie es
ohne die Reparatur lief, und einmal so, wie runner.py es heute aufruft.

Ein eigener Prozess und kein Aufruf im Testprozess, aus einem Grund, der
das ganze Verfahren traegt: der Fall ohne die Reparatur KEHRT NICHT
ZURUECK. Ein Thread, der in `while True` steht, laesst sich in Python
nicht abbrechen - die Reihe bliebe stehen, und zwar genau an der Stelle,
die beweisen soll, dass etwas stehenbleibt. Ein Kindprozess laesst sich
mit einer Frist erschlagen, und genau das misst der Elternteil.

Aufruf:
    ntp_freeze_child.py <mit-skip|ohne-skip> <site-packages> <arbeitsverzeichnis>
"""
from __future__ import annotations

import os
import sys
import time


def main() -> int:
    fall, site_packages, arbeitsverzeichnis = sys.argv[1:4]

    # VOR dem Import. archinstall legt beim Laden sein Protokoll an und
    # nimmt dafuer das aktuelle Verzeichnis, wenn es /var/log/archinstall
    # nicht beschreiben darf - gemessen am 17.08.2026: ohne diesen
    # Wechsel landet eine `install.log` im Wurzelverzeichnis des Repos,
    # bei jedem Lauf der Reihe.
    os.chdir(arbeitsverzeichnis)
    sys.path.insert(0, site_packages)

    import archinstall.lib.installer as echtes_modul

    # Kein einziger echter Unterprozess. Die Schleife fragt ueber
    # SysCommand nach `timedatectl show --property=NTPSynchronized
    # --value`; hier antwortet immer `no` - das ist buchstaeblich das,
    # was ein Rechner ohne Netz sagt, weil systemd-timesyncd die Uhr nie
    # als gestellt meldet.
    class Antwort:
        def decode(self, *args, **kwargs) -> str:
            return "no"

    echtes_modul.SysCommand = lambda befehl, *a, **k: Antwort()

    class Medium:
        """Der Zustand des ZepOS-Mediums, gemessen am 17.08.2026.

        Der Timer archlinux-keyring-wkd-sync.timer ist ueber
        /usr/lib/systemd/system/timers.target.wants/ vorab aktiviert,
        hat also einen ActiveEnterTimestamp; der Dienst selbst lief nie
        und steht auf `dead`. Beides sorgt dafuer, dass die zwei
        Schleifen hinter der Uhr (installer.py:224 und :228) sofort
        zurueckkehren - gemessen, nicht angenommen.
        """

        def _service_started(self, name: str) -> str:
            return "Mon 2026-08-17 09:58:00 CEST"

        def _service_state(self, name: str) -> str:
            return "dead"

    beginn = time.monotonic()
    echtes_modul.Installer._verify_service_stop(
        Medium(),
        offline=True,
        skip_ntp=fall == "mit-skip",
        skip_wkd=False,
    )
    dauer = time.monotonic() - beginn

    # flush, weil der andere Fall von aussen erschlagen wird und
    # gepufferte Ausgabe dabei verlorenginge.
    print(f"ZURUECKGEKEHRT nach {dauer:.3f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
