"""Mandanten (SDQ-011/012): eine Datenbank je Organisation.

Entscheidung (Architektur E10, 24.11.2026): Organisationen werden physisch getrennt – jede bekommt eine eigene SQLite-Datei.
Ein vergessener Filter im SQL kann so nichts über die Grenze geben; Schema und bestehende Daten bleiben unverändert.
Die lokale Installation ist der Fall „eine Organisation“ und braucht nichts von hier.

Dieses Modul liefert:
- ``db_key`` / ``conn_key``: eindeutiger Schlüssel einer Datenbank (aufgelöster Pfad). Jeder Prozesszustand, der zu einer
  Organisation gehört (Offline-Schalter, Anmeldesperren, laufende Aufträge), wird über diesen Schlüssel getrennt gehalten.
- ``use`` / ``current``: der Mandant der laufenden Anfrage bzw. des laufenden Auftrags (``contextvars``). Server und Auftrags-
  Worker setzen ihn; Code ohne eigenen Datenbankbezug (z. B. Abruf-Bremsen) fragt ihn ab.
- ``Directory``: Verzeichnis der Organisationen einer Mehrmandanten-Installation – Anlage, Pfadregeln, Archivierung.
  Löschen gibt es bewusst nicht: Rechnungsdaten sind aufbewahrungspflichtig (siehe ``data_map``), Löschung braucht eine
  eigene, freigegebene Regel.
"""
from __future__ import annotations

import contextlib
import contextvars
import re
import sqlite3
import threading
from pathlib import Path

_CURRENT: contextvars.ContextVar[str | None] = contextvars.ContextVar('signaldesk_tenant', default=None)

SLUG_RE = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$')
RESERVED = {'admin', 'api', 'static', 'system', 'con', 'prn', 'aux', 'nul', 'com1', 'lpt1'}
DB_NAME = 'signaldesk.sqlite3'
DIRECTORY_DB = 'organisationen.sqlite3'


def db_key(db_path) -> str:
    """Schlüssel einer Datenbankdatei: aufgelöster absoluter Pfad (gleiche Datei = gleicher Schlüssel, auch über Verknüpfungen)."""
    return str(Path(db_path).expanduser().resolve())


def conn_key(conn) -> str:
    """Schlüssel der Hauptdatenbank einer offenen Verbindung; ``:memory:`` je Verbindung eindeutig."""
    for row in conn.execute('PRAGMA database_list'):
        if row[1] == 'main':
            return db_key(row[2]) if row[2] else f':memory:{id(conn)}'
    return f':memory:{id(conn)}'


def current() -> str | None:
    """Schlüssel des Mandanten der laufenden Anfrage oder des laufenden Auftrags (None = nicht gesetzt)."""
    return _CURRENT.get()


@contextlib.contextmanager
def use(db_path):
    """Mandant für den eingeschlossenen Block setzen (Anfrage, Auftragsschritt, Hintergrund-Thread)."""
    token = _CURRENT.set(db_key(db_path))
    try:
        yield
    finally:
        _CURRENT.reset(token)


def thread(target, db_path, *, args=(), name=None, daemon=True):
    """Hintergrund-Thread, der im Mandanten ``db_path`` läuft. Threads übernehmen ``contextvars`` nicht von selbst."""
    def run():
        with use(db_path):
            target(*args)
    return threading.Thread(target=run, daemon=daemon, name=name)


# ---------------------------------------------------------------- Verzeichnis der Organisationen

class TenantError(ValueError):
    pass


class Directory:
    """Organisationen unter einem Wurzelordner: ``<root>/organisationen.sqlite3`` (Verzeichnis) und
    ``<root>/orgs/<kennung>/signaldesk.sqlite3`` (Daten je Organisation)."""

    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'orgs').mkdir(exist_ok=True)
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS organizations (
                slug TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'aktiv',
                created_at TEXT NOT NULL DEFAULT (datetime('now')), archived_at TEXT NOT NULL DEFAULT '')""")
        from . import accounts  # SDQ-014: Konten und Mitgliedschaften der zentralen Anmeldung im selben Verzeichnis
        accounts.init(self)

    @contextlib.contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self.root / DIRECTORY_DB), timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            with conn:  # Transaktion: bei Erfolg festschreiben, bei Fehler zurückrollen
                yield conn
        finally:
            conn.close()

    @staticmethod
    def check_slug(slug):
        if not isinstance(slug, str) or not SLUG_RE.match(slug) or slug in RESERVED or '--' in slug:
            raise TenantError('Kennung: 1–40 Zeichen, nur a–z, 0–9 und einzelne Bindestriche, nicht am Anfang oder Ende.')
        return slug

    def path_for(self, slug) -> Path:
        """Datenbankpfad einer Organisation – nur innerhalb des Wurzelordners (keine Umwege über Verknüpfungen)."""
        self.check_slug(slug)
        folder = self.root / 'orgs' / slug
        resolved = folder.resolve()
        if resolved.parent != (self.root / 'orgs').resolve():
            raise TenantError('Ordner der Organisation liegt außerhalb des Verzeichnisses.')
        return resolved / DB_NAME

    def create(self, slug, name, prepare=None):
        """Organisation anlegen: Eintrag + leere, migrierte Datenbank. ``prepare`` (Standard: ``server.prepare_database``)."""
        self.check_slug(slug)
        name = (name or '').strip()
        if not name or len(name) > 120:
            raise TenantError('Name: 1–120 Zeichen.')
        path = self.path_for(slug)
        with self._connect() as conn:
            if conn.execute('SELECT 1 FROM organizations WHERE slug=?', (slug,)).fetchone():
                raise TenantError(f'Organisation „{slug}“ gibt es schon.')
            if path.exists():
                raise TenantError(f'Für „{slug}“ liegt schon eine Datenbank im Verzeichnis – nicht überschrieben.')
            path.parent.mkdir(parents=True, exist_ok=False)
            if prepare is None:
                from .server import prepare_database as prepare
            prepare(path)
            conn.execute('INSERT INTO organizations(slug, name) VALUES (?, ?)', (slug, name))
        return self.get(slug)

    def get(self, slug):
        self.check_slug(slug)
        with self._connect() as conn:
            row = conn.execute('SELECT * FROM organizations WHERE slug=?', (slug,)).fetchone()
        if not row:
            raise LookupError(f'Organisation „{slug}“ unbekannt.')
        return {**dict(row), 'db_path': str(self.path_for(slug))}

    def list(self, include_archived=False):
        with self._connect() as conn:
            rows = conn.execute('SELECT slug FROM organizations' + ('' if include_archived else " WHERE status='aktiv'")
                                + ' ORDER BY slug').fetchall()
        return [self.get(r['slug']) for r in rows]

    def open(self, slug):
        """Datenbankpfad einer aktiven Organisation (für Anfrage oder Auftrag)."""
        org = self.get(slug)
        if org['status'] != 'aktiv':
            raise TenantError(f'Organisation „{slug}“ ist archiviert.')
        return Path(org['db_path'])

    def archive(self, slug):
        """Organisation stilllegen: keine Anmeldung, keine Aufträge mehr. Die Daten bleiben unverändert erhalten."""
        self.get(slug)
        with self._connect() as conn:
            conn.execute("UPDATE organizations SET status='archiviert', archived_at=datetime('now') WHERE slug=?", (slug,))
        return self.get(slug)


# ---------------------------------------------------------------- Dateien einer Organisation (SDQ-013)

def org_files(db_path):
    """Alle Dateien und Ordner, die zu einer Datenbank gehören – aus denselben Funktionen, die sie anlegen.

    Alle liegen im Ordner der Datenbank oder daneben. Darum gilt: je Organisation ein eigener Ordner (so legt ``Directory``
    sie an). Zwei Datenbanken im selben Ordner teilen sich Sicherungen, Bildschirmfotos und die Altdatei der Zugangsdaten.
    """
    from .accounting_api import _backup_dir
    from .credentials import _legacy_file
    from .research.catalog import catalog_path, upload_dir
    from .website_scorer import screenshot_dir
    db = Path(db_path).resolve()
    return {
        'datenbank': db,
        'datenbank_wal': db.with_name(db.name + '-wal'),
        'datenbank_shm': db.with_name(db.name + '-shm'),
        'sicherungen': Path(_backup_dir(db)),
        'bildschirmfotos': Path(screenshot_dir(db)),
        'firmenkatalog': Path(catalog_path(db)),
        'katalog_uploads': Path(upload_dir(db)),
        'zugangsdaten_altdatei': Path(_legacy_file(db)),
    }


EXPORT_FORMAT = 'signaldesk-organisation-export/1'


def export_organization(db_path, target_zip):
    """Datenexport einer Organisation (Übergabe, Kündigung, Art. 20 DSGVO): eine konsistente Kopie der Datenbank,
    die Bildschirmfotos und ein Verzeichnis mit Zeilenzahlen und Einordnung jeder Tabelle.

    Nicht enthalten: Zugangsdaten (Passwörter für Postfach und Kalender), Anmeldesitzungen, Sicherungen und der öffentliche
    Firmenkatalog. In der Kopie werden Passwort-Hashes und Sitzungen geleert. Die Ausgabe ist unverschlüsselt – sie gehört
    auf ein Speichermedium der Organisation.
    """
    import datetime as dt
    import json
    import tempfile
    import zipfile

    from . import data_map
    files = org_files(db_path)
    target_zip = Path(target_zip)
    if target_zip.exists():
        raise TenantError('Zieldatei gibt es schon – nicht überschrieben.')
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / 'signaldesk.sqlite3'
        src = sqlite3.connect(f'file:{files["datenbank"].as_posix()}?mode=ro', uri=True)
        dst = sqlite3.connect(str(copy))
        try:
            src.backup(dst)
            dst.execute('DELETE FROM sessions')
            dst.execute("UPDATE users SET pw_hash=''")
            dst.commit()
            tables = {}
            for name in sorted(data_map.db_tables(dst)):
                meta = data_map.TABLES.get(name)
                tables[name] = {'rows': dst.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0],
                                'scope': meta.scope if meta else '?', 'personal': bool(meta and meta.personal),
                                'retention': meta.retention if meta else '?'}
            dst.execute('VACUUM')
        finally:
            dst.close()
            src.close()
        shots = files['bildschirmfotos']
        shot_files = sorted(p for p in shots.rglob('*') if p.is_file()) if shots.is_dir() else []
        manifest = {'format': EXPORT_FORMAT, 'created_at': dt.datetime.now().isoformat(timespec='seconds'),
                    'database': 'signaldesk.sqlite3', 'screenshots': len(shot_files), 'tables': tables,
                    'excluded': ['Zugangsdaten', 'Anmeldesitzungen', 'Passwort-Hashes', 'Sicherungen', 'Firmenkatalog (öffentliche Daten)'],
                    'notice': 'Unverschlüsselt. Enthält personenbezogene Daten (siehe tables[].personal) und steuerlich '
                              'aufbewahrungspflichtige Unterlagen (retention = gobd).'}
        target_zip.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target_zip, 'x', zipfile.ZIP_DEFLATED) as zf:
            zf.write(copy, 'signaldesk.sqlite3')
            for p in shot_files:
                zf.write(p, 'bildschirmfotos/' + p.relative_to(shots).as_posix())
            zf.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=1))
    return {'path': str(target_zip), 'size_bytes': target_zip.stat().st_size, **{k: manifest[k] for k in ('format', 'screenshots')},
            'tables': len(tables)}
