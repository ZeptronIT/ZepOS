#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
#
# Urspruenglich clipman-daemon.py von azzuriel, aus helpers/ des
# hyprclipx-Baums. Urhebervermerk und Haftungsausschluss stehen in
# plugins/LICENSE.
"""Der Sammler hinter hyprclipx: was kopiert wurde, und wer danach fragt.

WARUM DIESE DATEI SEIT DEM 12.08.2026 IM BAUM LIEGT
    Weil ohne sie die Taste SUPER+SHIFT+V ein leeres Fenster oeffnet,
    und zwar auf JEDER Installation, die ZepOS macht.

    Die Kette ist kurz und war an genau einer Stelle offen. Das Fenster
    (plugins/hyprclipx/src/ClipboardManager.cpp) fragt einen Socket:

        /tmp/clipman.sock                 socket_path, aus der
                                          erzeugten Konfiguration

    Wer diesen Socket bedient, war niemand. Upstream legte den Sammler
    ueber hyprpm.toml nach $HOME/.local/bin - ein pacman-Paket darf
    unterhalb von ~ nichts besitzen (src/paths.py fuehrt das Argument),
    also konnte packaging/zepos-hyprclipx ihn nicht ausliefern, und der
    Kopf jenes Rezepts fuehrte das am 11.08.2026 als offenen Punkt.

    Was STATTDESSEN in hyprland-universal-config.template stand:

        exec-once = wl-paste --watch cliphist store

    Das ist ein Sammler, und es ist der falsche. cliphist schreibt in
    SEINE eigene Datenbank und macht keinen Socket auf; das Fenster
    fragt weiter /tmp/clipman.sock und bekommt weiter keine Antwort.
    GEMESSEN am 12.08.2026 auf der Maschine des Nutzers: der Prozess,
    der den Socket haelt, ist von Hand nach ~/.local/bin gelegt worden
    und traegt das Datum 23.06.2026 - auf einem frisch installierten
    ZepOS gibt es ihn nicht.

WAS AN DER UEBERNOMMENEN QUELLE GEAENDERT WURDE
    Die Konfiguration. Sie stand als Wortverzeichnis im Kopf, mit
    max_items = 700 und dem Socketpfad darin - zwei Zahlen, die
    src/templates/hyprclipx-config.template ebenfalls schreibt, und
    zwar mit max_items = 50. Zwei Antworten auf eine Frage, und die
    Haelfte, die die Oberflaeche fragt, war nicht die, die den Verlauf
    beschnitt: das Fenster holte 50 und der Sammler hob 700 auf.

    Jetzt liest der Sammler dieselbe erzeugte Datei wie beide
    C++-Haelften. Die Grundwerte bleiben stehen, weil die Datei fehlen
    kann und der Verlauf dann trotzdem gesammelt werden soll.

    Und das Datenverzeichnis: $XDG_DATA_HOME statt ~/.local/share fest
    verdrahtet, damit ein Test es umlenken kann, ohne das echte
    anzufassen.
"""

import os
import sys
import json
import sqlite3
import hashlib
import subprocess
import socket
import threading
import uuid
import time
import signal
import re
from pathlib import Path


def _config_dir() -> Path:
    """Dasselbe Verzeichnis, das ConfigParser.cpp::getConfigDir() bildet."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "hyprclipx"


def _data_dir() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local/share"
    return base / "hyprclipx"


def _read_generated_config() -> dict:
    """Die erzeugte Datei, so gelesen, wie ConfigParser.cpp sie liest.

    Also: Zeilen, ein Gleichheitszeichen, Abschnittsueberschriften und
    Kommentare weg, Anfuehrungszeichen weg. KEIN INI-Parser aus der
    Standardbibliothek - configparser wuerde bei einem Schluessel vor
    der ersten Ueberschrift eine Ausnahme werfen, und die C++-Haelfte
    tut das nicht. Zwei Leser derselben Datei, die sich bei einer
    kaputten Zeile verschieden verhalten, sind schlimmer als einer.
    """
    values: dict[str, str] = {}
    path = _config_dir() / "config"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line[0] in "#[":
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _as_int(values: dict, key: str, fallback: int) -> int:
    """Eine Zahl aus der erzeugten Datei, mit geduldetem "px".

    Wortgleich zu parseInt() in beiden ConfigParser.cpp, und aus
    demselben Grund: bei Unfug bleibt der Grundwert stehen, statt eine
    0 zu werden. Ein max_items von 0 waere ein Verlauf, der jeden
    Eintrag sofort wieder wegwirft.
    """
    raw = values.get(key, "").strip()
    if raw.endswith("px"):
        raw = raw[:-2].strip()
    try:
        return int(raw)
    except ValueError:
        return fallback


# Konfiguration. Die Grundwerte gelten, solange die erzeugte Datei
# fehlt; load_config() zieht darueber, was in ihr steht.
CONFIG = {
    "max_items": 50,
    "max_image_size_mb": 10,
    "preview_length": 100,
    "socket_path": "/tmp/clipman.sock",
    "data_dir": _data_dir(),
    "sensitive_ttl_seconds": 60,
}


def load_config() -> None:
    """CONFIG aus der erzeugten Datei nachziehen."""
    values = _read_generated_config()
    if "socket_path" in values:
        CONFIG["socket_path"] = values["socket_path"]
    CONFIG["max_items"] = _as_int(values, "max_items", CONFIG["max_items"])
    CONFIG["preview_length"] = _as_int(values, "preview_chars",
                                       CONFIG["preview_length"])
    CONFIG["data_dir"] = _data_dir()


class ClipmanDB:
    """Die SQLite-Datenbank: was zu einer Zeile bekannt ist."""

    def __init__(self, db_path):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT UNIQUE NOT NULL,
                content_type TEXT NOT NULL,
                preview TEXT,
                content_hash TEXT NOT NULL,
                file_path TEXT NOT NULL,
                thumb_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_favorite INTEGER DEFAULT 0,
                byte_size INTEGER,
                line_count INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_hash ON items(content_hash);
            CREATE INDEX IF NOT EXISTS idx_created ON items(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_favorite ON items(is_favorite);
        ''')
        self.conn.commit()

    def add_item(self, item_uuid, content_type, preview, content_hash,
                 file_path, thumb_path, byte_size, line_count):
        with self.lock:
            # Steht derselbe Inhalt schon drin? Verglichen wird die Pruefsumme.
            existing = self.conn.execute(
                "SELECT uuid FROM items WHERE content_hash = ?", (content_hash,)
            ).fetchone()

            if existing:
                # Dann nur die Zeit neu setzen - die Zeile wandert nach oben
                self.conn.execute(
                    "UPDATE items SET created_at = CURRENT_TIMESTAMP WHERE uuid = ?",
                    (existing['uuid'],)
                )
                self.conn.commit()
                return existing['uuid']

            # Sonst eine neue Zeile
            self.conn.execute('''
                INSERT INTO items (uuid, content_type, preview, content_hash,
                                 file_path, thumb_path, byte_size, line_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (item_uuid, content_type, preview, content_hash,
                  file_path, thumb_path, byte_size, line_count))
            self.conn.commit()
            self._cleanup()
            return item_uuid

    def get_items(self, filter_type="all", favorites_only=False,
                  search="", limit=50):
        with self.lock:
            query = "SELECT * FROM items WHERE 1=1"
            params = []

            if filter_type == "text":
                query += " AND content_type = 'text'"
            elif filter_type == "image":
                query += " AND content_type = 'image'"

            if favorites_only or filter_type == "favorites":
                query += " AND is_favorite = 1"

            if search:
                query += " AND preview LIKE ?"
                params.append(f"%{search}%")

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            return [dict(row) for row in self.conn.execute(query, params).fetchall()]

    def toggle_favorite(self, item_uuid):
        with self.lock:
            self.conn.execute(
                "UPDATE items SET is_favorite = NOT is_favorite WHERE uuid = ?",
                (item_uuid,)
            )
            self.conn.commit()

    def delete_item(self, item_uuid):
        with self.lock:
            row = self.conn.execute(
                "SELECT file_path, thumb_path FROM items WHERE uuid = ?",
                (item_uuid,)
            ).fetchone()

            if row:
                # Die Dateien, die an dieser Zeile haengen, mit loeschen
                for path in [row['file_path'], row['thumb_path']]:
                    if path:
                        full_path = CONFIG["data_dir"] / path
                        if full_path.exists():
                            try:
                                full_path.unlink()
                            except OSError:
                                pass

                self.conn.execute("DELETE FROM items WHERE uuid = ?", (item_uuid,))
                self.conn.commit()

    def clear_non_favorites(self):
        with self.lock:
            rows = self.conn.execute(
                "SELECT file_path, thumb_path FROM items WHERE is_favorite = 0"
            ).fetchall()

            for row in rows:
                for path in [row['file_path'], row['thumb_path']]:
                    if path:
                        full_path = CONFIG["data_dir"] / path
                        if full_path.exists():
                            try:
                                full_path.unlink()
                            except OSError:
                                pass

            self.conn.execute("DELETE FROM items WHERE is_favorite = 0")
            self.conn.commit()

    def _cleanup(self):
        """Die aeltesten Zeilen ohne Stern wegwerfen, sobald es mehr als
        max_items sind."""
        count = self.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]

        if count > CONFIG["max_items"]:
            excess = count - CONFIG["max_items"]
            old_items = self.conn.execute('''
                SELECT uuid FROM items WHERE is_favorite = 0
                ORDER BY created_at ASC LIMIT ?
            ''', (excess,)).fetchall()

            for row in old_items:
                # Ohne Sperre: _cleanup laeuft aus add_item heraus, und
                # das haelt sie schon. Ein zweites Nehmen waere ein
                # Verklemmer.
                item_uuid = row['uuid']
                file_row = self.conn.execute(
                    "SELECT file_path, thumb_path FROM items WHERE uuid = ?",
                    (item_uuid,)
                ).fetchone()

                if file_row:
                    for path in [file_row['file_path'], file_row['thumb_path']]:
                        if path:
                            full_path = CONFIG["data_dir"] / path
                            if full_path.exists():
                                try:
                                    full_path.unlink()
                                except OSError:
                                    pass

                    self.conn.execute("DELETE FROM items WHERE uuid = ?", (item_uuid,))

            self.conn.commit()


class ContentStore:
    """Der Inhalt selbst, als Datei auf der Platte."""

    def __init__(self, base_path):
        self.base_path = Path(base_path)
        (self.base_path / "text").mkdir(parents=True, exist_ok=True)
        (self.base_path / "images").mkdir(parents=True, exist_ok=True)
        (self.base_path / "thumbs").mkdir(parents=True, exist_ok=True)

    def store_text(self, content):
        """Text ablegen. Zurueck kommen uuid, Pfad und Pruefsumme."""
        item_uuid = str(uuid.uuid4())
        content_bytes = content.encode('utf-8')
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        file_path = f"text/{item_uuid}.txt"
        full_path = self.base_path / file_path
        full_path.write_text(content, encoding='utf-8')
        return item_uuid, file_path, content_hash

    def store_image(self, image_bytes):
        """Ein Bild ablegen. Zurueck kommen uuid, Pfad, Pfad des
        Vorschaubildes und Pruefsumme."""
        item_uuid = str(uuid.uuid4())
        content_hash = hashlib.sha256(image_bytes).hexdigest()
        file_path = f"images/{item_uuid}.png"
        thumb_path = f"thumbs/{item_uuid}.png"

        full_path = self.base_path / file_path
        full_path.write_bytes(image_bytes)

        # Das Vorschaubild
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(image_bytes))
            img.thumbnail((100, 65))
            img.save(self.base_path / thumb_path)
        except ImportError:
            # Ohne Pillow gibt es kein Vorschaubild - der Eintrag
            # selbst bleibt trotzdem
            thumb_path = None
        except Exception:
            # Das Bild liess sich nicht verarbeiten
            thumb_path = None

        return item_uuid, file_path, thumb_path, content_hash

    def get_content(self, file_path):
        """Den Inhalt wieder aus der Datei holen."""
        full_path = self.base_path / file_path
        if not full_path.exists():
            return None

        if file_path.startswith("text/"):
            return full_path.read_text(encoding='utf-8')
        return full_path.read_bytes()


class ClipboardWatcher:
    """Was in der Zwischenablage passiert, ueber wl-paste beobachtet."""

    def __init__(self, on_text, on_image):
        self.on_text = on_text
        self.on_image = on_image
        self.running = False
        self.last_text_hash = None
        self.last_image_hash = None
        self.text_proc = None

    def start(self):
        self.running = True
        # Auf Text in der Zwischenablage warten
        threading.Thread(target=self._watch_text, daemon=True).start()
        # Und auf Bilder
        threading.Thread(target=self._watch_image, daemon=True).start()

    def stop(self):
        self.running = False
        if self.text_proc:
            self.text_proc.terminate()

    @staticmethod
    def _run_with_timeout(cmd, timeout=2):
        """Einen Unterprozess starten und ihn bei Zeitueberschreitung
        wirklich beenden - sonst bleiben cat-Prozesse als Zombies stehen."""
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, _ = proc.communicate(timeout=timeout)
            return proc.returncode, stdout
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            return None, None

    def _watch_text(self):
        """Auf neuen Text warten."""
        while self.running:
            try:
                rc, stdout = self._run_with_timeout(["wl-paste", "--no-newline"])

                if rc == 0 and stdout:
                    content_hash = hashlib.sha256(stdout).hexdigest()

                    if content_hash != self.last_text_hash:
                        try:
                            text = stdout.decode('utf-8')
                            if text.strip():
                                self.last_text_hash = content_hash
                                self.on_text(text)
                        except UnicodeDecodeError:
                            pass

            except Exception as e:
                print(f"Fehler beim Beobachten des Textes: {e}", file=sys.stderr)

            time.sleep(0.5)

    def _watch_image(self):
        """Auf neue Bilder warten."""
        while self.running:
            try:
                rc, stdout = self._run_with_timeout(["wl-paste", "--type", "image/png"])

                if rc == 0 and stdout:
                    content_hash = hashlib.sha256(stdout).hexdigest()

                    if content_hash != self.last_image_hash:
                        self.last_image_hash = content_hash
                        self.on_image(stdout)

            except Exception as e:
                print(f"Fehler beim Beobachten der Bilder: {e}", file=sys.stderr)

            time.sleep(0.5)


class IPCServer:
    """Der Unix-Socket, ueber den das Fenster fragt."""

    def __init__(self, socket_path, db, store):
        self.socket_path = socket_path
        self.db = db
        self.store = store
        self.running = False
        self.server = None

    def start(self):
        self.running = True

        # Einen liegengebliebenen Socket wegraeumen
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.socket_path)
        self.server.listen(5)
        self.server.settimeout(1.0)  # Allow periodic check for shutdown

        print(f"Der Sammler hoert auf {self.socket_path}")

        while self.running:
            try:
                conn, _ = self.server.accept()
                threading.Thread(
                    target=self._handle_client,
                    args=(conn,),
                    daemon=True
                ).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Fehler im Sammler: {e}", file=sys.stderr)

    def stop(self):
        self.running = False
        if self.server:
            self.server.close()
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

    def _handle_client(self, conn):
        try:
            data = conn.recv(65536).decode('utf-8')
            request = json.loads(data)
            response = self._process_command(request)
            conn.send(json.dumps(response).encode('utf-8'))
        except Exception as e:
            error_response = {"status": "error", "error": str(e)}
            try:
                conn.send(json.dumps(error_response).encode('utf-8'))
            except Exception:
                pass
        finally:
            conn.close()

    def _process_command(self, request):
        cmd = request.get("cmd")
        args = request.get("args", {})

        if cmd == "list":
            items = self.db.get_items(
                filter_type=args.get("filter", "all"),
                favorites_only=args.get("favorites", False),
                search=args.get("search", ""),
                limit=args.get("limit", 50)
            )

            # Die Zeilen um volle Pfade und einheitliche Felder ergaenzen
            for item in items:
                if item.get("thumb_path"):
                    item["thumb"] = str(CONFIG["data_dir"] / item["thumb_path"])
                item["favorite"] = bool(item.get("is_favorite"))
                item["type"] = item.get("content_type")

            return {"status": "ok", "data": items}

        elif cmd == "paste":
            item_uuid = args.get("uuid")
            row = self.db.conn.execute(
                "SELECT file_path, content_type FROM items WHERE uuid = ?",
                (item_uuid,)
            ).fetchone()

            if row:
                content = self.store.get_content(row["file_path"])
                if content is None:
                    return {"status": "error", "error": "Content file not found"}

                if row["content_type"] == "text":
                    # Leerraum am Zeilenende weg, und leere Zeilen am
                    # Ende des Textes ebenfalls
                    if isinstance(content, str):
                        content = '\n'.join(line.rstrip() for line in content.split('\n'))
                        content = content.rstrip('\n')
                    elif isinstance(content, bytes):
                        content = b'\n'.join(line.rstrip() for line in content.split(b'\n'))
                        content = content.rstrip(b'\n')
                    subprocess.run(
                        ["wl-copy", "--"],
                        input=content.encode('utf-8') if isinstance(content, str) else content,
                        check=True
                    )
                else:
                    subprocess.run(
                        ["wl-copy", "--type", "image/png"],
                        input=content,
                        check=True
                    )
                return {"status": "ok"}

            return {"status": "error", "error": "Item not found"}

        elif cmd == "favorite":
            self.db.toggle_favorite(args.get("uuid"))
            return {"status": "ok"}

        elif cmd == "delete":
            self.db.delete_item(args.get("uuid"))
            return {"status": "ok"}

        elif cmd == "clear":
            self.db.clear_non_favorites()
            return {"status": "ok"}

        elif cmd == "ping":
            return {"status": "ok", "message": "pong"}

        return {"status": "error", "error": f"Unknown command: {cmd}"}


def is_sensitive(text: str) -> bool:
    """Sieht dieser Text aus wie ein Passwort?

    Die Regeln: eine einzige Zeile, 8 bis 128 Zeichen, kein Leerzeichen,
    und mindestens drei der vier Zeichenklassen. Ausgenommen sind Pfade,
    Adressen, Farben als Hexzahl, Mailadressen und reine Zahlen.

    Es ist eine Vermutung und kein Beweis - deshalb wird die Zeile nicht
    abgelehnt, sondern nach sensitive_ttl_seconds wieder geloescht.
    """
    if '\n' in text or '\r' in text:
        return False
    t = text.strip()
    if not (8 <= len(t) <= 128):
        return False
    if ' ' in t:
        return False
    # Was ganz sicher kein Geheimnis ist
    if t.startswith(('/','~')):          # Pfade
        return False
    if re.match(r'https?://', t):        # Adressen
        return False
    if re.match(r'^#[0-9a-fA-F]{3,8}$', t):  # Farben als Hexzahl
        return False
    if '@' in t and '.' in t.split('@')[-1]:  # Mailadressen
        return False
    if t.isdigit():                      # reine Zahlen
        return False
    # Wie viele Zeichenklassen kommen vor?
    classes = sum([
        bool(re.search(r'[A-Z]', t)),
        bool(re.search(r'[a-z]', t)),
        bool(re.search(r'[0-9]', t)),
        bool(re.search(r'[^A-Za-z0-9]', t)),
    ])
    return classes >= 3


# Die laufenden Uhren fuer heikle Zeilen, uuid -> Timer
_sensitive_timers: dict[str, threading.Timer] = {}


def main():
    """Der Einstieg."""
    load_config()
    print("hyprclipx - der Sammler")
    print(f"Datenverzeichnis: {CONFIG['data_dir']}")
    print(f"Socket: {CONFIG['socket_path']}")
    print(f"max_items: {CONFIG['max_items']}")

    # Das Datenverzeichnis anlegen
    CONFIG["data_dir"].mkdir(parents=True, exist_ok=True)

    # Die Teile
    db = ClipmanDB(CONFIG["data_dir"] / "clipman.db")
    store = ContentStore(CONFIG["data_dir"])
    server = IPCServer(CONFIG["socket_path"], db, store)

    def on_text(text):
        """Neuer Text in der Zwischenablage."""
        item_uuid, file_path, content_hash = store.store_text(text)
        sensitive = is_sensitive(text)
        if sensitive:
            preview = "[sensitive] " + "\u2022" * min(len(text), 12)
        else:
            preview = text[:CONFIG["preview_length"]].replace('\n', ' ').replace('\t', ' ')
        line_count = text.count('\n') + 1
        stored_uuid = db.add_item(
            item_uuid, "text", preview, content_hash,
            file_path, None, len(text.encode('utf-8')), line_count
        )
        print(f"Text gemerkt: {preview[:50]} ...")

        if sensitive:
            def auto_delete():
                # Hat der Nutzer die Zeile inzwischen mit einem Stern
                # versehen, bleibt sie stehen
                with db.lock:
                    row = db.conn.execute(
                        "SELECT is_favorite FROM items WHERE uuid = ?",
                        (stored_uuid,)
                    ).fetchone()
                    if row and row['is_favorite']:
                        print(f"Heikle Zeile {stored_uuid[:8]} bleibt - sie traegt einen Stern")
                        return
                db.delete_item(stored_uuid)
                _sensitive_timers.pop(stored_uuid, None)
                print(f"Heikle Zeile {stored_uuid[:8]} nach {CONFIG['sensitive_ttl_seconds']} s geloescht")

            # Wurde dieselbe Zeile noch einmal kopiert, laeuft schon eine
            # Uhr dafuer - die alte wird abgestellt
            old = _sensitive_timers.pop(stored_uuid, None)
            if old:
                old.cancel()
            t = threading.Timer(CONFIG["sensitive_ttl_seconds"], auto_delete)
            t.daemon = True
            t.start()
            _sensitive_timers[stored_uuid] = t
            print(f"Heikle Zeile erkannt, wird in {CONFIG['sensitive_ttl_seconds']} s geloescht")

    def on_image(image_bytes):
        """Ein neues Bild in der Zwischenablage."""
        if len(image_bytes) > CONFIG["max_image_size_mb"] * 1024 * 1024:
            print(f"Bild zu gross ({len(image_bytes)} Byte) - nicht gemerkt")
            return

        item_uuid, file_path, thumb_path, content_hash = store.store_image(image_bytes)
        preview = f"[Image {len(image_bytes)//1024}KB]"
        db.add_item(
            item_uuid, "image", preview, content_hash,
            file_path, thumb_path, len(image_bytes), 0
        )
        print(f"Bild gemerkt: {preview}")

    # Die Beobachtung der Zwischenablage starten
    watcher = ClipboardWatcher(on_text, on_image)
    watcher.start()

    # Das Ende, wenn ein Signal kommt
    def shutdown(signum, frame):
        print("\nEnde.")
        watcher.stop()
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Der Socket-Dienst. Er kehrt nicht zurueck.
    try:
        server.start()
    except KeyboardInterrupt:
        shutdown(None, None)


if __name__ == "__main__":
    main()
