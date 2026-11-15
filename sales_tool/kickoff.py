"""Projektkompass mit Startstatus und Material- und Entscheidungsliste (2.0.0-dev28, Produktreview M38 und M39).

Je angenommenem Auftrag – mehrere Projekte einer Firma laufen unabhängig – gibt es eine Liste der Startvoraussetzungen:
- vorbelegt aus dem bestätigten Angebot: offene Briefing-Punkte der Chance und typische Voraussetzungen je Leistungsbereich,
- je Punkt: Art (Material, Zugang, Entscheidung, Termin, Sonstiges), wer liefert (ich, Kunde, Dritte, optional mit Namen),
  bis wann, was ohne den Punkt nicht geht (Auswirkung), Stand offen/erledigt/entfällt.

Der Startstatus ergibt sich daraus: **Vorbereitung** (eigene Punkte offen), **wartet auf …** (Punkte von Kunde oder Dritten
offen – mit Name, Punkt und Frist), **bereit** (nichts offen), **gestartet** (bewusst gesetzt, auf Wunsch auch trotz
offener Punkte – das steht dann im Verlauf).

Zugänge werden nie als Passwort erfasst: Es gibt kein Passwortfeld, und Eingaben, die wie Zugangsdaten aussehen, werden
abgelehnt. Festgehalten wird nur, wer den Zugang einrichtet und über welchen sicheren Weg er übergeben wird.
"""
from __future__ import annotations

import datetime as dt
import json
import re

KINDS = {'material': 'Material', 'zugang': 'Zugang', 'entscheidung': 'Entscheidung', 'termin': 'Termin', 'sonstiges': 'Sonstiges'}
OWNERS = {'ich': 'ich', 'kunde': 'Kunde', 'dritte': 'Dritte'}
STATES = ('offen', 'erledigt', 'entfaellt')
SECRET_RE = re.compile(r'(pass(wort|word)|kennwort|\bpw\b|\bpin\b|zugangsdaten|login|benutzer(name)?|user(name)?)\s*[:=]|\b(sk|pk|ghp|xox[bp])[-_][A-Za-z0-9]{8,}', re.I)
SECRET_MSG = ('Bitte keine Passwörter oder Zugangsdaten in SignalDesk eintragen. Nur festhalten, wer den Zugang einrichtet und über '
              'welchen sicheren Weg er übergeben wird (z. B. Passwortmanager des Kunden, Einladung als Nutzer).')
BRIEF_KIND = {'schnittstellen': 'zugang', 'ausgang': 'zugang', 'daten': 'material', 'freigabe_medien': 'entscheidung', 'rollen': 'entscheidung',
              'umfang': 'entscheidung', 'budget_kanal': 'entscheidung'}
DEFAULTS = {
    'medien': [('material', 'Logo, Bilder und Texte für den ersten Arbeitsschritt', 'kunde', 'Gestaltung kann nicht beginnen'),
               ('entscheidung', 'Eine Person für gebündeltes Feedback und die finale Freigabe benennen', 'kunde', 'Korrekturschleifen laufen auseinander')],
    'software': [('zugang', 'Testzugang zu den benötigten Systemen einrichten (Einladung als Nutzer, keine Passwörter per Mail)', 'kunde',
                  'Schnittstellen lassen sich nicht testen'),
                 ('entscheidung', 'Priorisierte Anforderungen für die erste Lieferung bestätigen', 'kunde', 'Umfang der ersten Lieferung unklar')],
    'sichtbarkeit': [('zugang', 'Zugang zu Search Console bzw. Werbekonto mit passender Rolle', 'kunde', 'Ausgangsmessung nicht möglich')],
}


def init_kickoff(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS kickoffs (
        proposal_id INTEGER PRIMARY KEY REFERENCES proposals(id) ON DELETE CASCADE,
        started_at TEXT NOT NULL DEFAULT '', start_note TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS kickoff_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proposal_id INTEGER NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
        kind TEXT NOT NULL, label TEXT NOT NULL, owner TEXT NOT NULL DEFAULT 'kunde', owner_name TEXT NOT NULL DEFAULT '',
        due_date TEXT NOT NULL DEFAULT '', impact TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'offen',
        note TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_kickoff_items ON kickoff_items(proposal_id);
    ''')


def _text(v, limit, what, required=False):
    if v is None:
        v = ''
    if not isinstance(v, str) or len(v.strip()) > limit:
        raise ValueError(f'{what}: höchstens {limit} Zeichen.')
    v = re.sub(r'\s+', ' ', v).strip()
    if required and not v:
        raise ValueError(f'{what}: bitte angeben.')
    if SECRET_RE.search(v):
        raise ValueError(SECRET_MSG)
    return v


def _date(v, what, past_only=False):
    if v in (None, ''):
        return ''
    try:
        d = dt.date.fromisoformat(v)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{what}: Datum als JJJJ-MM-TT angeben.') from exc
    if past_only and d > dt.date.today():
        raise ValueError(f'{what}: Ein Datum in der Zukunft lässt sich nicht als geschehen dokumentieren.')
    return d.isoformat()


def _proposal(conn, pid):
    row = conn.execute('SELECT p.*, l.company FROM proposals p JOIN leads l ON l.id=p.lead_id WHERE p.id=?', (pid,)).fetchone()
    if not row:
        raise LookupError('Angebot nicht gefunden.')
    if row['status'] != 'angenommen' or row['superseded_by']:
        raise ValueError('Den Projektkompass gibt es für angenommene, aktuelle Aufträge.')
    return row


def _ensure(conn, row):
    if conn.execute('SELECT 1 FROM kickoffs WHERE proposal_id=?', (row['id'],)).fetchone():
        return
    conn.execute('INSERT INTO kickoffs(proposal_id) VALUES (?)', (row['id'],))
    seen = set()

    def add(kind, label, owner, impact, source):
        label = label.strip()[:300]
        if not label or label.lower() in seen or SECRET_RE.search(label):
            return
        seen.add(label.lower())
        conn.execute('INSERT INTO kickoff_items(proposal_id, kind, label, owner, impact, source) VALUES (?,?,?,?,?,?)',
                     (row['id'], kind, label, owner, impact[:300], source))

    add('termin', 'Startgespräch durchgeführt: Ziel, Ablauf, Ansprechpartner, nächste Termine', 'ich', 'Projekt startet ohne gemeinsame Grundlage', 'standard')
    if row['opportunity_id']:
        from .briefing import get as briefing
        try:
            b = briefing(conn, row['opportunity_id'])
        except LookupError:
            b = {'items': []}
        for i in b['items']:
            if i['status'] == 'offen':
                add(BRIEF_KIND.get(i['key'], 'material'), f"{i['label']}: {i['answer']}", 'kunde', 'Offene Voraussetzung aus dem Briefing', 'briefing')
    from .catalog import SERVICES
    cust = json.loads(row['customer_json'] or '{}')
    areas = {a for p in cust.get('positions') or [] if not p.get('optional') for a in SERVICES.get(p.get('service'), {}).get('areas', [])}
    for area in ('medien', 'software', 'sichtbarkeit'):
        if area in areas:
            for kind, label, owner, impact in DEFAULTS[area]:
                add(kind, label, owner, impact, area)
    conn.commit()


def _status(items, started_at):
    open_ = [i for i in items if i['state'] == 'offen']
    waiting = [i for i in open_ if i['owner'] in ('kunde', 'dritte')]
    if started_at:
        st, label = 'gestartet', f"gestartet am {dt.date.fromisoformat(started_at).strftime('%d.%m.%Y')}"
    elif waiting:
        names = list(dict.fromkeys(i['owner_name'] or OWNERS[i['owner']] for i in waiting))
        st, label = 'wartet', 'wartet auf ' + ', '.join(names)
    elif open_:
        st, label = 'vorbereitung', 'Vorbereitung'
    else:
        st, label = 'bereit', 'bereit zum Start'
    return st, label, open_, waiting


def state(conn, pid):
    row = _proposal(conn, pid)
    _ensure(conn, row)
    k = conn.execute('SELECT * FROM kickoffs WHERE proposal_id=?', (pid,)).fetchone()
    today = dt.date.today().isoformat()
    items = []
    for r in conn.execute('SELECT * FROM kickoff_items WHERE proposal_id=? ORDER BY id', (pid,)):
        i = dict(r)
        i['kind_label'], i['owner_label'] = KINDS.get(i['kind'], i['kind']), OWNERS.get(i['owner'], i['owner'])
        i['overdue'] = i['state'] == 'offen' and bool(i['due_date']) and i['due_date'] < today
        items.append(i)
    st, label, open_, waiting = _status(items, k['started_at'])
    cust = json.loads(row['customer_json'] or '{}')
    return {'proposal_id': pid, 'number': row['number'] or f"#{pid}", 'company': row['company'], 'project_label': cust.get('project_label', ''),
            'status': st, 'status_label': label, 'started_at': k['started_at'], 'start_note': k['start_note'], 'items': items,
            'open': len(open_), 'waiting': [{'label': i['label'], 'owner': i['owner_name'] or i['owner_label'], 'due_date': i['due_date'],
                                             'impact': i['impact']} for i in waiting],
            'kinds': KINDS, 'owners': OWNERS, 'states': STATES, 'secret_hint': SECRET_MSG}


def _log(conn, row, text):
    conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)', (row['lead_id'], 'projekt', f"Auftrag {row['number'] or '#' + str(row['id'])}: {text}"))


def act(conn, pid, data):
    if not isinstance(data, dict) or data.get('action') not in ('add', 'item', 'start'):
        raise ValueError('Aktion: add, item oder start.')
    row = _proposal(conn, pid)
    _ensure(conn, row)
    k = conn.execute('SELECT * FROM kickoffs WHERE proposal_id=?', (pid,)).fetchone()
    action, notice = data['action'], ''
    fields = {'kind', 'label', 'owner', 'owner_name', 'due_date', 'impact', 'note', 'state'}
    if action == 'add':
        if set(data) - fields - {'action'}:
            raise ValueError('Punkt: ' + ', '.join(sorted(fields)))
        kind, owner = data.get('kind') or 'material', data.get('owner') or 'kunde'
        if kind not in KINDS or owner not in OWNERS:
            raise ValueError('Art: ' + ', '.join(KINDS) + '; wer liefert: ' + ', '.join(OWNERS))
        conn.execute('''INSERT INTO kickoff_items(proposal_id, kind, label, owner, owner_name, due_date, impact, source) VALUES (?,?,?,?,?,?,?,'eigen')''',
                     (pid, kind, _text(data.get('label'), 300, 'Punkt', True), owner, _text(data.get('owner_name'), 120, 'Name'),
                      _date(data.get('due_date'), 'Bis wann'), _text(data.get('impact'), 300, 'Auswirkung')))
    elif action == 'item':
        if set(data) - fields - {'action', 'item_id'}:
            raise ValueError('Punkt: item_id, ' + ', '.join(sorted(fields)))
        it = conn.execute('SELECT * FROM kickoff_items WHERE id=? AND proposal_id=?', (data.get('item_id'), pid)).fetchone()
        if not it:
            raise LookupError('Punkt nicht gefunden.')
        upd = {}
        if 'state' in data:
            if data['state'] not in STATES:
                raise ValueError('Stand: offen, erledigt oder entfaellt.')
            upd['state'] = data['state']
        if 'owner' in data:
            if data['owner'] not in OWNERS:
                raise ValueError('Wer liefert: ' + ', '.join(OWNERS))
            upd['owner'] = data['owner']
        for key, limit, what in (('owner_name', 120, 'Name'), ('impact', 300, 'Auswirkung'), ('note', 300, 'Notiz'), ('label', 300, 'Punkt')):
            if key in data:
                upd[key] = _text(data[key], limit, what, key == 'label')
        if 'due_date' in data:
            upd['due_date'] = _date(data['due_date'], 'Bis wann')
        if (upd.get('state') == 'entfaellt') and not (upd.get('note') or it['note']):
            raise ValueError('Bitte kurz begründen, warum der Punkt entfällt.')
        if upd:
            conn.execute(f"UPDATE kickoff_items SET {', '.join(k_ + '=?' for k_ in upd)}, updated_at=datetime('now') WHERE id=?", (*upd.values(), it['id']))
    else:
        if set(data) - {'action', 'date', 'note', 'trotz_offener_punkte'}:
            raise ValueError('Start: date, note, trotz_offener_punkte.')
        if k['started_at']:
            raise ValueError('Der Projektstart ist bereits dokumentiert.')
        s = state(conn, pid)
        if s['open'] and data.get('trotz_offener_punkte') is not True:
            raise ValueError(f"Noch {s['open']} Startvoraussetzung(en) offen. Erledigen, begründet entfallen lassen – oder bewusst trotzdem starten.")
        when = _date(data.get('date'), 'Gestartet am', past_only=True) or dt.date.today().isoformat()
        note = _text(data.get('note'), 300, 'Notiz')
        conn.execute('UPDATE kickoffs SET started_at=?, start_note=? WHERE proposal_id=?', (when, note, pid))
        _log(conn, row, f"Projekt gestartet am {when}" + (f" trotz {s['open']} offener Startvoraussetzung(en): " + '; '.join(i['label'][:60] for i in s['items'] if i['state'] == 'offen')[:400] if s['open'] else '')
             + (f' – {note}' if note else '') + '.')
        notice = 'Projektstart dokumentiert.' + (' Offene Punkte bleiben sichtbar.' if s['open'] else '')
    conn.commit()
    return {**state(conn, pid), 'notice': notice}


def summary(conn, pid):
    """Kurzstatus für Übersichten, ohne Punkte anzulegen."""
    k = conn.execute('SELECT * FROM kickoffs WHERE proposal_id=?', (pid,)).fetchone()
    if not k:
        return {'status': 'vorbereitung', 'label': 'Projektkompass noch nicht geöffnet'}
    items = [dict(r) for r in conn.execute('SELECT owner, owner_name, state FROM kickoff_items WHERE proposal_id=?', (pid,))]
    st, label, _, _ = _status(items, k['started_at'])
    return {'status': st, 'label': label}


def due_items(conn, today=None):
    """Für „Heute“: fällige oder überfällige Startvoraussetzungen noch nicht gestarteter Aufträge."""
    t = (today or dt.date.today()).isoformat()
    return conn.execute("""SELECT i.*, p.number, p.lead_id, l.company FROM kickoff_items i JOIN kickoffs k ON k.proposal_id=i.proposal_id
                           JOIN proposals p ON p.id=i.proposal_id JOIN leads l ON l.id=p.lead_id
                           WHERE i.state='offen' AND i.due_date<>'' AND i.due_date<=? AND k.started_at=''
                           AND p.status='angenommen' AND p.superseded_by IS NULL ORDER BY i.due_date""", (t,)).fetchall()


def route_kickoff(h, conn, method, route):
    m = re.fullmatch(r'/api/workspace/proposals/(\d+)/kompass', route)
    if not m:
        return False
    pid = int(m.group(1))
    if method == 'GET':
        h._send(200, state(conn, pid))
    elif method == 'POST':
        h._send(200, act(conn, pid, h._body()))
    else:
        return False
    return True
