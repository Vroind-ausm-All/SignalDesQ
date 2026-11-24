"""Protokoll der Verwaltungs- und Anmeldeaktionen einer Mehrmandanten-Installation (SDQ-022).

Liegt im Verzeichnis (``organisationen.sqlite3``, Tabelle ``audit_events``), nicht in den Datenbanken der Organisationen –
dort gibt es weiterhin das fachliche Protokoll (``audit_log``). Erfasst wird, wer wann was an Konten, Mitgliedschaften,
Organisationen, Sicherungen und Exporten geändert hat, dazu Anmeldungen, Fehlversuche und der zweite Faktor.

Manipulationen fallen auf: Jeder Eintrag enthält den Hash des vorigen (Hash-Kette, SHA-256). ``verify`` rechnet die Kette
nach und nennt den ersten Eintrag, der nicht passt. Das schützt nicht gegen jemanden, der die ganze Datei neu schreibt –
dafür gehören die täglichen Sicherungen (SDQ-018) an einen getrennten Ort.

Nicht protokolliert werden Passwörter, Codes, Sitzungstoken und Inhalte. Benutzernamen werden nur genannt, wenn es das
Konto gibt (ein Tippfehler im Namensfeld ist oft ein Passwort). Die IP-Adresse wird nur bei Anmeldeereignissen gespeichert.
"""
from __future__ import annotations

import contextlib
import getpass
import hashlib
import json
import sqlite3

GENESIS = '0' * 64
FIELDS = ('at', 'actor', 'action', 'target', 'detail', 'ip')
MAX_DETAIL = 500


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS audit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
        target TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '', ip TEXT NOT NULL DEFAULT '',
        prev_hash TEXT NOT NULL, hash TEXT NOT NULL)''')


def operator():
    """Kennung für Aufrufe über die Kommandozeile: der angemeldete Benutzer des Betriebssystems."""
    try:
        return 'betreiber:' + getpass.getuser()
    except Exception:  # noqa: BLE001 – ohne Benutzerkennung (z. B. Container ohne passwd-Eintrag)
        return 'betreiber'


def _digest(prev_hash, row):
    payload = json.dumps([prev_hash] + [row[k] for k in FIELDS], ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


@contextlib.contextmanager
def _writer(directory):
    conn = sqlite3.connect(str(directory.root / 'organisationen.sqlite3'), timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('BEGIN IMMEDIATE')  # Schreibsperre vor dem Lesen des letzten Hashs: keine zwei Einträge mit demselben Vorgänger
        try:
            yield conn
            conn.execute('COMMIT')
        except BaseException:
            conn.execute('ROLLBACK')
            raise
    finally:
        conn.close()


def record(directory, actor, action, target='', detail='', ip=''):
    """Eintrag anhängen. Gibt die Nummer zurück."""
    import datetime as dt
    row = {'at': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'actor': str(actor or '?')[:80],
           'action': str(action)[:60], 'target': str(target or '')[:120], 'detail': str(detail or '')[:MAX_DETAIL],
           'ip': str(ip or '')[:64]}
    with _writer(directory) as conn:
        init(conn)
        last = conn.execute('SELECT hash FROM audit_events ORDER BY id DESC LIMIT 1').fetchone()
        prev = last['hash'] if last else GENESIS
        cur = conn.execute('INSERT INTO audit_events(at, actor, action, target, detail, ip, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?)',
                           (*[row[k] for k in FIELDS], prev, _digest(prev, row)))
        return cur.lastrowid


def events(directory, limit=100, actor=None, target=None, action=None):
    clauses, args = [], []
    for col, val in (('actor', actor), ('target', target), ('action', action)):
        if val:
            clauses.append(f'{col}=?')
            args.append(val)
    with directory._connect() as conn:
        init(conn)
        rows = conn.execute('SELECT id, at, actor, action, target, detail, ip FROM audit_events'
                            + (' WHERE ' + ' AND '.join(clauses) if clauses else '') + ' ORDER BY id DESC LIMIT ?',
                            (*args, max(1, min(int(limit), 10000)))).fetchall()
    return [dict(r) for r in rows]


def verify(directory):
    """Hash-Kette nachrechnen. ``{'ok': bool, 'events': n, 'first_bad': id|None, 'reason': ...}``"""
    with directory._connect() as conn:
        init(conn)
        rows = conn.execute('SELECT * FROM audit_events ORDER BY id').fetchall()
    prev = None
    for r in rows:
        if prev is not None and r['prev_hash'] != prev:
            return {'ok': False, 'events': len(rows), 'first_bad': r['id'], 'reason': 'Vorgänger passt nicht (Eintrag entfernt oder eingefügt).'}
        if _digest(r['prev_hash'], dict(r)) != r['hash']:
            return {'ok': False, 'events': len(rows), 'first_bad': r['id'], 'reason': 'Inhalt verändert.'}
        prev = r['hash']
    if rows and rows[0]['prev_hash'] != GENESIS:
        return {'ok': False, 'events': len(rows), 'first_bad': rows[0]['id'], 'reason': 'Anfang der Kette fehlt.'}
    return {'ok': True, 'events': len(rows), 'first_bad': None, 'reason': ''}


def anchor(directory):
    """Stand der Kette zum externen Hinterlegen (SDQ-043, Prüfbericht F12): Anzahl, Nummer und Hash des letzten Eintrags.

    Wer Schreibrechte an der Datenbank hat, kann das Ende der Kette abschneiden, ohne dass ``verify`` es merkt. Ein Anker,
    der außerhalb des Servers liegt (anderer Speicher, E-Mail an sich selbst, Ticket), macht das sichtbar."""
    import datetime as dt
    with directory._connect() as conn:
        init(conn)
        last = conn.execute('SELECT id, at, hash FROM audit_events ORDER BY id DESC LIMIT 1').fetchone()
        count = conn.execute('SELECT COUNT(*) FROM audit_events').fetchone()[0]
    return {'format': 'signaldesk-protokoll-anker-1', 'created_at': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'events': count, 'last_id': last['id'] if last else 0, 'last_at': last['at'] if last else '',
            'last_hash': last['hash'] if last else GENESIS}


def verify_anchor(directory, saved):
    """Kette prüfen und zusätzlich, ob der hinterlegte Eintrag noch unverändert da ist (nichts am Ende abgeschnitten)."""
    out = verify(directory)
    if not isinstance(saved, dict) or saved.get('format') != 'signaldesk-protokoll-anker-1':
        raise ValueError('Kein Protokoll-Anker (format signaldesk-protokoll-anker-1).')
    with directory._connect() as conn:
        init(conn)
        row = conn.execute('SELECT hash FROM audit_events WHERE id=?', (int(saved.get('last_id') or 0),)).fetchone()
    if saved.get('last_id') and (not row or row['hash'] != saved.get('last_hash')):
        return {**out, 'ok': False, 'anchor_ok': False,
                'reason': f"Eintrag {saved['last_id']} aus dem Anker fehlt oder ist verändert (Protokoll gekürzt oder ersetzt)."}
    if out['events'] < int(saved.get('events') or 0):
        return {**out, 'ok': False, 'anchor_ok': False, 'reason': 'Weniger Einträge als beim Anker (Protokoll gekürzt).'}
    return {**out, 'anchor_ok': True}
