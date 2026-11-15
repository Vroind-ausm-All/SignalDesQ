"""Eigene Nachrichtenvorlagen mit Platzhaltern (2.0.0-dev29, Produktreview M37).

- Vorlagen pflegst du selbst (Betreff und Text). Mitgeliefert sind neutrale Startvorlagen; sie lassen sich ändern.
- Platzhalter in doppelten geschweiften Klammern, z. B. {{firma}}. Erlaubt sind nur die Platzhalter aus PLACEHOLDERS;
  unbekannte werden beim Speichern abgelehnt.
- Werte kommen nur aus bestätigten Daten: Firmenname, eine eingetragene Person der Firma, ein Angebot dieser Firma (mit
  freigegebenem Stand), geplanter Termin, Nachfassfrist, eigene Stammdaten. Nichts wird geraten.
- **Anrede:** „Sehr geehrte Frau …/Sehr geehrter Herr …“ nur, wenn die Anrede an der Person ausdrücklich hinterlegt ist –
  nie aus dem Vornamen abgeleitet. Sonst neutral („Guten Tag Vorname Nachname,“ bzw. „Guten Tag,“).
- **Fehlende Werte** erscheinen sichtbar als [FEHLT: …] und werden aufgelistet. Eine Endfassung (zum Kopieren) gibt es erst,
  wenn nichts mehr fehlt.
- Kontaktregeln: Sperre der Firma (assert_contact_allowed) und Einschränkungen der Person (keine E-Mails, nur Post, Widerspruch)
  gelten auch für Vorschau und Entwurf. SignalDesk versendet nichts.
"""
from __future__ import annotations

import datetime as dt
import json
import re

PLACEHOLDERS = {
    'anrede': 'Anrede (neutral, außer die Anrede ist an der Person hinterlegt)',
    'firma': 'Firmenname',
    'ansprechpartner': 'Name der gewählten Person',
    'projekt': 'Projekttitel des Angebots',
    'angebotsnummer': 'Angebotsnummer',
    'festpreis': 'Festpreis netto des Angebots',
    'gueltig_bis': 'Bindefrist des Angebots',
    'angebot_stand': 'Stand der freigegebenen Versandfassung',
    'termin': 'Nächster geplanter Termin',
    'frist': 'Nächste Nachfassfrist zum Angebot',
    'mein_name': 'Dein Name (Stammdaten)',
    'meine_firma': 'Deine Firma (Stammdaten)',
}
TOKEN = re.compile(r'\{\{\s*([a-z_]+)\s*\}\}')
SALUTATIONS = {'': 'nicht hinterlegt (neutral)', 'neutral': 'neutral', 'frau': 'Frau', 'herr': 'Herr'}
BLOCKING = {'keine_email': 'Diese Person möchte keine E-Mails.', 'nur_post': 'Diese Person ist nur per Briefpost erreichbar.',
            'widerspruch': 'Diese Person hat der Ansprache widersprochen.'}

STARTER = [
    ('nach_gespraech', 'Nach einem Gespräch', 'Unser Gespräch – nächste Schritte',
     '{{anrede}}\n\nvielen Dank für das Gespräch. Wie besprochen hier die nächsten Schritte:\n\n- …\n\nFreundliche Grüße\n{{mein_name}}\n{{meine_firma}}'),
    ('angebot_versand', 'Angebot versenden', 'Angebot {{angebotsnummer}}: {{projekt}}',
     '{{anrede}}\n\nanbei erhalten Sie unser Angebot {{angebotsnummer}} für „{{projekt}}“ (Stand {{angebot_stand}}). Der Festpreis beträgt '
     '{{festpreis}}; das Angebot gilt bis {{gueltig_bis}}.\n\nIch melde mich am {{frist}} bei Ihnen, falls bis dahin Fragen offen sind.\n\n'
     'Freundliche Grüße\n{{mein_name}}\n{{meine_firma}}'),
    ('nachfassen', 'Vereinbartes Nachfassen', 'Rückfrage zu Angebot {{angebotsnummer}}',
     '{{anrede}}\n\nwie vereinbart melde ich mich zu unserem Angebot {{angebotsnummer}} („{{projekt}}“). Gibt es Fragen oder Punkte, '
     'die wir noch klären sollten?\n\nFreundliche Grüße\n{{mein_name}}'),
    ('terminbestaetigung', 'Terminbestätigung', 'Bestätigung unseres Termins',
     '{{anrede}}\n\nhiermit bestätige ich unseren Termin am {{termin}}.\n\nFreundliche Grüße\n{{mein_name}}\n{{meine_firma}}'),
]


def init_messages(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS message_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT NOT NULL DEFAULT '', title TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
        builtin INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
    ''')
    if not conn.execute('SELECT 1 FROM message_templates LIMIT 1').fetchone():
        for key, title, subject, body in STARTER:
            conn.execute('INSERT INTO message_templates(key, title, subject, body, builtin) VALUES (?,?,?,?,1)', (key, title, subject, body))
    # Anrede nur, wenn ausdrücklich hinterlegt (Zweck: Anrede in Nachrichten; gelöscht mit der Person)
    cols = {r[1] for r in conn.execute('PRAGMA table_info(decision_contacts)')}
    if 'salutation' not in cols:
        conn.execute("ALTER TABLE decision_contacts ADD COLUMN salutation TEXT NOT NULL DEFAULT ''")
    mcols = {r[1] for r in conn.execute('PRAGMA table_info(mail_drafts)')}
    for name, decl in (('template_id', 'INTEGER'), ('missing_json', "TEXT NOT NULL DEFAULT '[]'"), ('proposal_id', 'INTEGER'), ('contact_id', 'INTEGER')):
        if name not in mcols:
            conn.execute(f'ALTER TABLE mail_drafts ADD COLUMN {name} {decl}')


def _clean(v, limit, what, required=True, multiline=False):
    if not isinstance(v, str) or len(v) > limit:
        raise ValueError(f'{what}: Text mit höchstens {limit} Zeichen.')
    v = v.replace('\r\n', '\n').strip() if multiline else re.sub(r'\s+', ' ', v).strip()
    if required and not v:
        raise ValueError(f'{what}: bitte angeben.')
    return v


def _check_tokens(*texts):
    unknown = sorted({t for s in texts for t in TOKEN.findall(s)} - set(PLACEHOLDERS))
    if unknown:
        raise ValueError('Unbekannte Platzhalter: ' + ', '.join('{{' + u + '}}' for u in unknown) + '. Erlaubt: ' + ', '.join('{{' + p + '}}' for p in PLACEHOLDERS))


def list_templates(conn):
    return {'templates': [dict(r) for r in conn.execute('SELECT id, key, title, subject, body, builtin, updated_at FROM message_templates ORDER BY builtin DESC, title')],
            'placeholders': PLACEHOLDERS, 'salutations': SALUTATIONS}


def save_template(conn, tid, data):
    if not isinstance(data, dict) or set(data) - {'title', 'subject', 'body'}:
        raise ValueError('Vorlage: title, subject, body.')
    title, subject, body = _clean(data.get('title'), 80, 'Name'), _clean(data.get('subject'), 200, 'Betreff'), _clean(data.get('body'), 5000, 'Text', multiline=True)
    _check_tokens(subject, body)
    if tid is None:
        tid = conn.execute('INSERT INTO message_templates(title, subject, body) VALUES (?,?,?)', (title, subject, body)).lastrowid
    else:
        if not conn.execute('UPDATE message_templates SET title=?, subject=?, body=?, updated_at=datetime(\'now\') WHERE id=?', (title, subject, body, tid)).rowcount:
            raise LookupError('Vorlage nicht gefunden.')
    conn.commit()
    return dict(conn.execute('SELECT * FROM message_templates WHERE id=?', (tid,)).fetchone())


def delete_template(conn, tid):
    row = conn.execute('SELECT builtin FROM message_templates WHERE id=?', (tid,)).fetchone()
    if not row:
        raise LookupError('Vorlage nicht gefunden.')
    if row['builtin']:
        raise ValueError('Mitgelieferte Vorlagen lassen sich ändern, aber nicht löschen.')
    conn.execute('DELETE FROM message_templates WHERE id=?', (tid,))
    conn.commit()
    return {'deleted': True}


def _de(iso):
    return dt.date.fromisoformat(iso[:10]).strftime('%d.%m.%Y') if iso else ''


def values(conn, lead, proposal_id=None, contact_id=None):
    """Werte je Platzhalter mit Quelle; None = fehlt."""
    out = {'firma': (lead['company'], 'Firma')}
    c = None
    if contact_id not in (None, ''):
        c = conn.execute('SELECT * FROM decision_contacts WHERE id=? AND lead_id=?', (contact_id, lead['id'])).fetchone()
        if not c:
            raise ValueError('Die Person gehört nicht zu dieser Firma.')
        restr = set(json.loads(c['contact_restrictions'] or '[]')) if 'contact_restrictions' in c.keys() else set()
        for key, msg in BLOCKING.items():
            if key in restr:
                from .workday import ContactLocked
                raise ContactLocked(msg + ' Keine Nachricht vorbereiten.')
    if c:
        name = c['full_name'].strip()
        last = name.split()[-1] if name else ''
        sal = (c['salutation'] or '') if 'salutation' in c.keys() else ''
        out['ansprechpartner'] = (name, 'Person')
        out['anrede'] = ({'frau': f'Sehr geehrte Frau {last},', 'herr': f'Sehr geehrter Herr {last},'}.get(sal) or f'Guten Tag {name},',
                         'Anrede an der Person hinterlegt' if sal in ('frau', 'herr') else 'neutral')
    else:
        out['ansprechpartner'] = (None, 'keine Person gewählt')
        out['anrede'] = ('Guten Tag,', 'neutral (keine Person gewählt)')
    p = None
    if proposal_id not in (None, ''):
        p = conn.execute('SELECT * FROM proposals WHERE id=? AND lead_id=?', (proposal_id, lead['id'])).fetchone()
        if not p:
            raise ValueError('Das Angebot gehört nicht zu dieser Firma.')
    if p:
        cust = json.loads(p['customer_json'])
        money = lambda v: f"{v:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.')
        out['projekt'] = (cust.get('project_label') or None, 'Angebot')
        out['angebotsnummer'] = (p['number'] or None, 'Angebot')
        out['festpreis'] = (f"{money(cust['net_eur'])} netto" if cust.get('net_eur') is not None else None, 'Angebot')
        out['gueltig_bis'] = (_de(p['valid_until']) or None, 'Angebot')
        out['angebot_stand'] = ((p['release_sha'] or '')[:8] or None, 'freigegebene Versandfassung' if p['release_sha'] else 'Angebot noch nicht freigegeben')
        f = conn.execute("""SELECT due_date FROM tasks WHERE proposal_id=? AND action_type='followup' AND done=0 AND due_date<>'' ORDER BY due_date LIMIT 1""",
                         (p['id'],)).fetchone()
        out['frist'] = (_de(f['due_date']) if f else None, 'Nachfassen' if f else 'keine offene Nachfassfrist')
    else:
        for k in ('projekt', 'angebotsnummer', 'festpreis', 'gueltig_bis', 'angebot_stand', 'frist'):
            out[k] = (None, 'kein Angebot gewählt')
    m = conn.execute("""SELECT starts_at, location FROM meetings WHERE lead_id=? AND status IN ('geplant','bestaetigt') AND starts_at>=datetime('now')
                        ORDER BY starts_at LIMIT 1""", (lead['id'],)).fetchone()
    out['termin'] = (f"{_de(m['starts_at'])} um {m['starts_at'][11:16]} Uhr" + (f" ({m['location']})" if m['location'] else '') if m else None,
                     'Termin' if m else 'kein geplanter Termin')
    from .accounting import get_settings
    s = get_settings(conn)
    out['mein_name'] = (s.get('owner_name') or None, 'Stammdaten')
    out['meine_firma'] = (s.get('company_name') or None, 'Stammdaten')
    return out


def render(conn, tid, data):
    if not isinstance(data, dict) or set(data) - {'lead_id', 'proposal_id', 'contact_id'}:
        raise ValueError('Vorschau: lead_id, proposal_id, contact_id.')
    t = conn.execute('SELECT * FROM message_templates WHERE id=?', (tid,)).fetchone()
    if not t:
        raise LookupError('Vorlage nicht gefunden.')
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (data.get('lead_id'),)).fetchone()
    if not lead:
        raise LookupError('Firma nicht gefunden.')
    from .workday import assert_contact_allowed
    assert_contact_allowed(conn, lead, 'Nachricht vorbereiten')
    vals = values(conn, lead, data.get('proposal_id'), data.get('contact_id'))
    missing = []

    def fill(text):
        def rep(m):
            key = m.group(1)
            v, _ = vals.get(key, (None, ''))
            if v is None:
                label = PLACEHOLDERS[key].split(' (')[0]
                if label not in missing:
                    missing.append(label)
                return f'[FEHLT: {label}]'
            return v
        return TOKEN.sub(rep, text)

    subject, body = fill(t['subject']), fill(t['body'])
    tokens = set(TOKEN.findall(t['subject'] + t['body']))
    used = {k: {'value': v, 'source': src} for k, (v, src) in vals.items() if k in tokens}
    return {'template_id': tid, 'title': t['title'], 'subject': subject, 'body': body, 'missing': missing, 'complete': not missing, 'used': used,
            'notice': 'Vorschau, nicht versendet.' + (' Fehlende Angaben sind markiert – Endfassung erst, wenn nichts mehr fehlt.' if missing else
                                                      ' Vor dem Versand Empfänger, Anlass und Inhalt selbst prüfen.')}


def route_messages(h, conn, method, route):
    if route == '/api/vorlagen':
        if method == 'GET':
            h._send(200, list_templates(conn))
            return True
        if method == 'POST':
            h._send(201, save_template(conn, None, h._body()))
            return True
        return False
    m = re.fullmatch(r'/api/vorlagen/(\d+)(/vorschau)?', route)
    if not m:
        return False
    tid = int(m.group(1))
    if m.group(2) and method == 'POST':
        h._send(200, render(conn, tid, h._body()))
    elif not m.group(2) and method == 'PATCH':
        h._send(200, save_template(conn, tid, h._body()))
    elif not m.group(2) and method == 'DELETE':
        h._send(200, delete_template(conn, tid))
    else:
        return False
    return True
