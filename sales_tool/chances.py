"""Mehrere Verkaufschancen je Firma (2.0.0-dev18, Produktreview M13 Teil 1).

Eine **Chance** ist ein mögliches Projekt bei einer Firma – mit eigener Phase, eigenem Anliegen, nächstem Schritt, eigenen
Angeboten und Terminen. Eine Firma kann mehrere Chancen haben; eine neue Chance erzeugt keine zweite Firma.

Regeln
- Phasen einer Chance: bedarf → termin → angebot → gewonnen | verloren. „Verloren“ braucht einen Grund.
- Der Verlust einer Chance beendet keine andere und ändert keine Rechnung.
- Die **Firmenphase** (Spalte `leads.stage`) folgt den Chancen nur nach oben bzw. zum Abschluss: offene Chancen heben sie an,
  eine gewonnene Chance macht die Firma zum Kunden, erst wenn alle Chancen verloren sind, gilt die Firma als verloren.
  Eine Sperre bleibt immer bestehen; ein Kunde wird durch eine neue Chance nicht zurückgestuft.
- Die **erste Chance** einer Firma nutzt (Teil 1) weiterhin die Bedarfsanalyse und die Bedarfsfreigabe der Firma. Weitere
  Chancen haben ein eigenes Anliegen; Bedarfsanalyse und Freigabe je Chance folgen in Teil 2 (dev19).
- Bestand: Beim ersten Start legt `ensure_first_chances` für Firmen mit Gespräch, Termin, Bedarf oder Angebot genau eine erste
  Chance an und ordnet ihr vorhandene Angebote und Termine zu. Nichts wird gelöscht oder umgerechnet.
"""
from __future__ import annotations

import re

STAGES = ('bedarf', 'termin', 'angebot', 'gewonnen', 'verloren')
STAGE_LABELS = {'bedarf': 'Bedarf klären', 'termin': 'Termin', 'angebot': 'Angebot', 'gewonnen': 'Gewonnen', 'verloren': 'Verloren'}
OPEN = ('bedarf', 'termin', 'angebot')
ORDER = {s: i for i, s in enumerate(OPEN)}
LEAD_STAGE = {'bedarf': 'antwort', 'termin': 'termin', 'angebot': 'angebot', 'gewonnen': 'gewonnen', 'verloren': 'verloren'}
LEAD_ORDER = {s: i for i, s in enumerate(('recherche', 'qualifiziert', 'kontakt', 'antwort', 'termin', 'angebot'))}
FROM_LEAD = {'antwort': 'bedarf', 'termin': 'termin', 'angebot': 'angebot', 'gewonnen': 'gewonnen', 'verloren': 'verloren'}
BUDGET = ('offen', 'budget_vorhanden', 'freigabe_offen', 'kein_budget')
TEXT_FIELDS = {'title': 120, 'problem': 1000, 'desired_outcome': 1000, 'timing': 200, 'next_step': 300}


def init_chances(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS opportunities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        title TEXT NOT NULL, offer TEXT NOT NULL DEFAULT '', stage TEXT NOT NULL DEFAULT 'bedarf',
        is_first INTEGER NOT NULL DEFAULT 0,
        problem TEXT NOT NULL DEFAULT '', desired_outcome TEXT NOT NULL DEFAULT '', timing TEXT NOT NULL DEFAULT '',
        budget_status TEXT NOT NULL DEFAULT 'offen',
        next_step TEXT NOT NULL DEFAULT '', next_date TEXT NOT NULL DEFAULT '',
        lost_reason TEXT NOT NULL DEFAULT '', lost_note TEXT NOT NULL DEFAULT '', closed_at TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT 'manuell',
        created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_opportunities_lead ON opportunities(lead_id);
    ''')
    for table in ('proposals', 'meetings'):
        cols = {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
        if 'opportunity_id' not in cols:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN opportunity_id INTEGER REFERENCES opportunities(id) ON DELETE SET NULL')


def _title_for(conn, lead):
    from .catalog import VORLAGEN
    if lead['offer'] in VORLAGEN:
        return VORLAGEN[lead['offer']]['title']
    p = conn.execute('SELECT customer_json FROM proposals WHERE lead_id=? ORDER BY id LIMIT 1', (lead['id'],)).fetchone()
    if p:
        import json
        label = (json.loads(p['customer_json']).get('project_label') or '').strip()
        if label:
            return label[:120]
    return 'Erstes Projekt'


def ensure_first_chances(conn):
    """Bestand: genau eine erste Chance für Firmen mit Verkaufsbezug. Mehrfach aufrufbar, legt nichts doppelt an."""
    rows = conn.execute("""SELECT l.* FROM leads l WHERE NOT EXISTS (SELECT 1 FROM opportunities o WHERE o.lead_id=l.id) AND (
                             l.stage IN ('antwort','termin','angebot','gewonnen','verloren')
                             OR EXISTS (SELECT 1 FROM proposals p WHERE p.lead_id=l.id)
                             OR EXISTS (SELECT 1 FROM meetings m WHERE m.lead_id=l.id)
                             OR EXISTS (SELECT 1 FROM discovery d WHERE d.lead_id=l.id AND (d.problem<>'' OR d.desired_outcome<>'')))""").fetchall()
    for lead in rows:
        props = conn.execute('SELECT status FROM proposals WHERE lead_id=?', (lead['id'],)).fetchall()
        if any(p['status'] == 'angenommen' for p in props):
            stage = 'gewonnen'
        elif lead['stage'] in FROM_LEAD:
            stage = FROM_LEAD[lead['stage']]
        elif props:
            stage = 'angebot'
        else:
            stage = 'bedarf'
        lost = (lead['lost_reason'] or 'sonstiges', lead['lost_note'] or 'aus dem Firmenstatus übernommen') if stage == 'verloren' else ('', '')
        oid = conn.execute("""INSERT INTO opportunities(lead_id, title, offer, stage, is_first, next_step, next_date, lost_reason, lost_note,
                                                        closed_at, source)
                              VALUES (?,?,?,?,1,?,?,?,?,?, 'bestand')""",
                           (lead['id'], _title_for(conn, lead), lead['offer'] or '', stage,
                            '' if stage in ('gewonnen', 'verloren') else (lead['next_step'] or ''),
                            '' if stage in ('gewonnen', 'verloren') else (lead['next_date'] or ''),
                            *lost, lead['updated_at'] if stage in ('gewonnen', 'verloren') else '')).lastrowid
        conn.execute('UPDATE proposals SET opportunity_id=? WHERE lead_id=? AND opportunity_id IS NULL', (oid, lead['id']))
        conn.execute('UPDATE meetings SET opportunity_id=? WHERE lead_id=? AND opportunity_id IS NULL', (oid, lead['id']))
    return len(rows)


# ---------------------------------------------------------------- Lesen

def _lead(conn, lead_id):
    row = conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not row:
        raise LookupError('Firma nicht gefunden.')
    return row


def _row(conn, oid):
    row = conn.execute('SELECT * FROM opportunities WHERE id=?', (oid,)).fetchone()
    if not row:
        raise LookupError('Chance nicht gefunden.')
    return row


def _view(conn, row):
    import json
    from .catalog import VORLAGEN
    from .qualification import LOST_REASONS
    d = dict(row)
    if row['is_first']:  # Teil 1: Bedarf der ersten Chance = Bedarfsanalyse der Firma
        disc = conn.execute('SELECT problem, desired_outcome, timing, budget_status FROM discovery WHERE lead_id=?', (row['lead_id'],)).fetchone()
        if disc:
            d.update({k: disc[k] for k in ('problem', 'desired_outcome', 'timing', 'budget_status')})
        d['need_source'] = 'Bedarfsanalyse der Firma'
    else:
        d['need_source'] = 'Anliegen dieser Chance'
    d['stage_label'] = STAGE_LABELS[row['stage']]
    d['open'] = row['stage'] in OPEN
    d['offer_title'] = VORLAGEN[row['offer']]['title'] if row['offer'] in VORLAGEN else ''
    d['lost_label'] = LOST_REASONS.get(row['lost_reason'], '') if row['lost_reason'] else ''
    d['proposals'] = [{'id': p['id'], 'number': p['number'] or f"#{p['id']}", 'status': p['status'],
                       'net_eur': json.loads(p['customer_json']).get('net_eur')}
                      for p in conn.execute('SELECT id, number, status, customer_json FROM proposals WHERE opportunity_id=? ORDER BY id', (row['id'],))]
    d['meetings'] = [dict(m) for m in conn.execute("""SELECT id, title, starts_at, status FROM meetings WHERE opportunity_id=?
                                                      ORDER BY starts_at""", (row['id'],))]
    return d


def list_chances(conn, lead_id):
    _lead(conn, lead_id)
    rows = conn.execute("""SELECT * FROM opportunities WHERE lead_id=?
                           ORDER BY CASE WHEN stage IN ('bedarf','termin','angebot') THEN 0 WHEN stage='gewonnen' THEN 1 ELSE 2 END, id""",
                        (lead_id,)).fetchall()
    from .qualification import LOST_REASONS
    return {'lead_id': lead_id, 'chances': [_view(conn, r) for r in rows], 'stages': STAGE_LABELS, 'lost_reasons': LOST_REASONS,
            'open': sum(1 for r in rows if r['stage'] in OPEN)}


def open_chances(conn, lead_id):
    return conn.execute("SELECT * FROM opportunities WHERE lead_id=? AND stage IN ('bedarf','termin','angebot') ORDER BY id", (lead_id,)).fetchall()


# ---------------------------------------------------------------- Schreiben

def _clean(data):
    out = {}
    for k, limit in TEXT_FIELDS.items():
        if k in data:
            v = data[k]
            if not isinstance(v, str) or len(v.strip()) > limit:
                raise ValueError(f'{k}: Text mit höchstens {limit} Zeichen.')
            out[k] = re.sub(r'[ \t]+', ' ', v).strip()
    if 'title' in out and not out['title']:
        raise ValueError('Bitte einen kurzen Titel für die Chance angeben (z. B. „Neue Website“).')
    if 'offer' in data:
        from .catalog import VORLAGEN
        if data['offer'] not in ('', *VORLAGEN):
            raise ValueError('Leistung: eine Vorlage aus dem Katalog oder leer.')
        out['offer'] = data['offer']
    if 'budget_status' in data:
        if data['budget_status'] not in BUDGET:
            raise ValueError('Budgetstatus: ' + ', '.join(BUDGET))
        out['budget_status'] = data['budget_status']
    if 'next_date' in data:
        v = data['next_date'] or ''
        if v and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(v)):
            raise ValueError('Datum als JJJJ-MM-TT angeben.')
        out['next_date'] = v
    return out


def _log(conn, lead_id, text):
    conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)', (lead_id, 'notiz', text[:900]))


def create(conn, lead_id, data, source='manuell', commit=True):
    if not isinstance(data, dict) or set(data) - {'title', 'offer', 'problem', 'desired_outcome', 'timing', 'budget_status', 'next_step', 'next_date'}:
        raise ValueError('Erwartet: {title, offer?, problem?, desired_outcome?, timing?, budget_status?, next_step?, next_date?}.')
    lead = _lead(conn, lead_id)
    if lead['stage'] == 'gesperrt':
        raise ValueError('Gesperrte Firma: keine neue Chance.')
    vals = _clean({'title': data.get('title', ''), **data})
    first = not conn.execute('SELECT 1 FROM opportunities WHERE lead_id=?', (lead_id,)).fetchone()
    if first:  # die erste Chance nutzt die Bedarfsanalyse der Firma; eigenes Anliegen nicht doppelt speichern
        for k in ('problem', 'desired_outcome', 'timing', 'budget_status'):
            vals.pop(k, None)
    stage = FROM_LEAD.get(lead['stage'], 'bedarf') if source == 'angebot' and FROM_LEAD.get(lead['stage']) in OPEN else 'bedarf'
    cols = ['lead_id', 'is_first', 'source', 'stage', *vals]
    oid = conn.execute(f"INSERT INTO opportunities({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                       (lead_id, int(first), source, stage, *vals.values())).lastrowid
    _log(conn, lead_id, f"Chance „{vals['title']}“ angelegt.")
    sync_lead(conn, lead_id)
    if commit:
        conn.commit()
    return _view(conn, _row(conn, oid))


def update(conn, oid, data):
    allowed = {'title', 'offer', 'problem', 'desired_outcome', 'timing', 'budget_status', 'next_step', 'next_date', 'stage', 'lost_reason', 'lost_note'}
    if not isinstance(data, dict) or not data or set(data) - allowed:
        raise ValueError('Ungültige Felder: ' + ', '.join(sorted(set(data or {}) - allowed)) if isinstance(data, dict) and data else 'Keine Änderung angegeben.')
    row = _row(conn, oid)
    vals = _clean(data)
    if row['is_first'] and set(vals) & {'problem', 'desired_outcome', 'timing', 'budget_status'}:
        raise ValueError('Die erste Chance nutzt die Bedarfsanalyse der Firma – bitte dort ändern.')
    stage = data.get('stage')
    if stage is not None and stage != row['stage']:
        if stage not in STAGES:
            raise ValueError('Phase: ' + ', '.join(STAGES))
        if row['stage'] == 'gewonnen':
            raise ValueError('Eine gewonnene Chance bleibt gewonnen. Für ein weiteres Projekt eine neue Chance anlegen.')
        if stage == 'verloren':
            from .qualification import check_lost
            vals.update(check_lost({'stage': row['stage']}, {'stage': 'verloren'}, data.get('lost_reason'), data.get('lost_note', '')))
            vals['closed_at'] = _now(conn)
            _log(conn, row['lead_id'], f"Chance „{row['title']}“ verloren. Andere Chancen der Firma bleiben offen.")
        elif stage == 'gewonnen':
            vals['closed_at'] = _now(conn)
            _log(conn, row['lead_id'], f"Chance „{row['title']}“ gewonnen.")
        else:
            if row['stage'] == 'verloren':
                vals.update({'lost_reason': '', 'lost_note': '', 'closed_at': ''})
                _log(conn, row['lead_id'], f"Chance „{row['title']}“ wieder aufgenommen.")
        vals['stage'] = stage
    if not vals:
        return _view(conn, row)
    conn.execute(f"UPDATE opportunities SET {', '.join(k + '=?' for k in vals)}, updated_at=datetime('now') WHERE id=?", (*vals.values(), oid))
    sync_lead(conn, row['lead_id'], last_lost=oid if vals.get('stage') == 'verloren' else None)
    conn.commit()
    return _view(conn, _row(conn, oid))


def _now(conn):
    return conn.execute("SELECT datetime('now')").fetchone()[0]


def advance(conn, oid, stage):
    """Ereignis einer Chance (Termin, versendetes Angebot): Phase nur vorwärts, nie aus gewonnen/verloren."""
    if not oid:
        return
    row = conn.execute('SELECT * FROM opportunities WHERE id=?', (oid,)).fetchone()
    if row and row['stage'] in OPEN and ORDER[stage] > ORDER[row['stage']]:
        conn.execute("UPDATE opportunities SET stage=?, updated_at=datetime('now') WHERE id=?", (stage, oid))
        sync_lead(conn, row['lead_id'])


def win(conn, oid):
    if not oid:
        return
    row = conn.execute('SELECT * FROM opportunities WHERE id=?', (oid,)).fetchone()
    if row and row['stage'] != 'gewonnen':
        conn.execute("UPDATE opportunities SET stage='gewonnen', closed_at=datetime('now'), lost_reason='', lost_note='', updated_at=datetime('now') WHERE id=?", (oid,))
        sync_lead(conn, row['lead_id'])


def for_new_offer(conn, lead_id, oid=None, title=''):
    """Chance für ein neues Angebot: angegebene, sonst die einzige offene, sonst eine neue. Mehrere offene → Auswahl nötig.
    oid='neu' legt ausdrücklich eine weitere Chance an."""
    if oid == 'neu':
        return create(conn, lead_id, {'title': (title or 'Neues Projekt')[:120]}, source='angebot', commit=False)['id']
    if oid not in (None, ''):
        if isinstance(oid, bool) or not str(oid).isdigit():
            raise ValueError('Ungültige Chance.')
        row = _row(conn, int(oid))
        if row['lead_id'] != lead_id:
            raise ValueError('Die Chance gehört zu einer anderen Firma.')
        if row['stage'] not in OPEN:
            raise ValueError('Die Chance ist abgeschlossen. Für ein weiteres Projekt eine neue Chance anlegen.')
        return row['id']
    opened = open_chances(conn, lead_id)
    if len(opened) == 1:
        return opened[0]['id']
    if len(opened) > 1:
        raise ValueError('Diese Firma hat mehrere offene Chancen – bitte auswählen, zu welcher das Angebot gehört.')
    return create(conn, lead_id, {'title': (title or 'Neues Projekt')[:120]}, source='angebot', commit=False)['id']


def close_open(conn, lead_id, reason, note):
    """Firma als verloren markiert: alle offenen Chancen mit demselben Grund schließen (eine verlorene Firma hat keine offene Chance)."""
    n = conn.execute("""UPDATE opportunities SET stage='verloren', lost_reason=?, lost_note=?, closed_at=datetime('now'), updated_at=datetime('now')
                        WHERE lead_id=? AND stage IN ('bedarf','termin','angebot')""", (reason or 'sonstiges', note or 'Firma als verloren markiert', lead_id)).rowcount
    return n


def sync_lead(conn, lead_id, last_lost=None):
    """Firmenphase aus den Chancen: offene heben an, gewonnen = Kunde, alle verloren = verloren. Sperre und Kundenstatus bleiben."""
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    rows = conn.execute('SELECT * FROM opportunities WHERE lead_id=?', (lead_id,)).fetchall()
    if not lead or not rows or lead['stage'] == 'gesperrt':
        return
    opened = [r for r in rows if r['stage'] in OPEN]
    upd = {}
    if opened:
        best = LEAD_STAGE[max(opened, key=lambda r: ORDER[r['stage']])['stage']]
        if lead['stage'] == 'verloren' or (lead['stage'] in LEAD_ORDER and LEAD_ORDER[best] > LEAD_ORDER[lead['stage']]):
            upd['stage'] = best
    elif any(r['stage'] == 'gewonnen' for r in rows):
        if lead['stage'] != 'gewonnen':
            upd['stage'] = 'gewonnen'
    elif lead['stage'] != 'verloren':
        last = next((r for r in rows if r['id'] == last_lost), None) or max(rows, key=lambda r: (r['closed_at'], r['id']))
        upd.update({'stage': 'verloren', 'lost_reason': last['lost_reason'] or 'sonstiges', 'lost_note': (last['lost_note'] or '')[:500]})
    if upd:
        conn.execute(f"UPDATE leads SET {', '.join(k + '=?' for k in upd)}, updated_at=datetime('now') WHERE id=?", (*upd.values(), lead_id))


# ---------------------------------------------------------------- HTTP

def route_chances(h, conn, method, route):
    m = re.fullmatch(r'/api/leads/(\d+)/chances', route)
    if m:
        lid = int(m.group(1))
        if method == 'GET':
            h._send(200, list_chances(conn, lid))
            return True
        if method == 'POST':
            h._send(201, create(conn, lid, h._body()))
            return True
        return False
    m = re.fullmatch(r'/api/chances/(\d+)', route)
    if m and method == 'PATCH':
        h._send(200, update(conn, int(m.group(1)), h._body()))
        return True
    return False
