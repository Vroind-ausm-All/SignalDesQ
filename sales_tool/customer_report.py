"""Kundenfähiger Kurzbericht (2.0.0-dev30, Produktreview M25).

Aus den Befunden einer Firma wählst du einzelne aus; daraus entsteht ein kurzer Bericht für den Kunden (Markdown).
- **Nur geprüfte Befunde** sind wählbar: Website-Befunde mit Prüfstatus „bestätigt“ und Beobachtungen der URL-Recherche mit
  Status „freigegeben“. Ungeprüfte oder verworfene Befunde werden abgelehnt, auch wenn sie direkt angefragt werden.
- **Keine internen Angaben:** keine Punktwerte, Gewichte, Prioritäten, Profilnähe, Angebotsideen, Hypothesen über Bedarf,
  Kaufsignale, Personen oder Kalkulationen. Übernommen werden Bezeichnung, Beobachtung, Fundstelle mit Stand und die Frage
  an den Kunden.
- Jeder erzeugte Bericht wird mit den gewählten Befunden gespeichert (Nachweis, was dem Kunden gezeigt wurde).
- Gesperrte Firmen bekommen keinen Bericht (assert_contact_allowed). SignalDesk versendet nichts.
"""
from __future__ import annotations

import datetime as dt
import json
import re

AREA_LABELS = {'design': 'Gestaltung', 'web': 'Technik & Auffindbarkeit', 'process': 'Anfrage & Abläufe', 'prozess': 'Anfrage & Abläufe'}
MAX_ITEMS = 12


def init_customer_report(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS customer_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        items_json TEXT NOT NULL, markdown TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
    ''')


def _lead(conn, lead_id):
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not lead:
        raise LookupError('Firma nicht gefunden.')
    return lead


def _clean(text):
    return re.sub(r'\s+', ' ', str(text or '')).strip()


def candidates(conn, lead_id):
    """Wählbare (geprüfte) Befunde und die Zahl der nicht wählbaren."""
    _lead(conn, lead_id)
    items = []
    for r in conn.execute("""SELECT f.id, f.area, f.label, f.evidence, f.source_url, f.question, f.result, a.finished_at
                             FROM website_findings f JOIN website_audits a ON a.id=f.audit_id
                             WHERE f.lead_id=? AND f.review_status='bestaetigt' ORDER BY a.id DESC, f.weight DESC""", (lead_id,)):
        items.append({'id': f"w{r['id']}", 'kind': 'Website-Bewertung', 'area': AREA_LABELS.get(r['area'], r['area']), 'title': _clean(r['label']),
                      'observation': _clean(r['evidence']), 'source_url': r['source_url'], 'question': _clean(r['question']),
                      'as_of': (r['finished_at'] or '')[:10], 'result': r['result']})
    for r in conn.execute("""SELECT f.id, f.category, f.observation, f.evidence, f.source_url, f.question, f.reviewed_at
                             FROM findings f WHERE f.lead_id=? AND f.review_status='freigegeben' ORDER BY f.id DESC""", (lead_id,)):
        items.append({'id': f"r{r['id']}", 'kind': 'Website-Inhalte', 'area': _clean(r['category']), 'title': _clean(r['observation'])[:140],
                      'observation': _clean(r['evidence']), 'source_url': r['source_url'], 'question': _clean(r['question']),
                      'as_of': (r['reviewed_at'] or '')[:10], 'result': ''})
    hidden = conn.execute("SELECT COUNT(*) FROM website_findings WHERE lead_id=? AND review_status<>'bestaetigt'", (lead_id,)).fetchone()[0] + \
        conn.execute("SELECT COUNT(*) FROM findings WHERE lead_id=? AND review_status<>'freigegeben'", (lead_id,)).fetchone()[0]
    return {'lead_id': lead_id, 'items': items, 'not_selectable': hidden, 'max_items': MAX_ITEMS,
            'notice': 'Wählbar sind nur geprüfte Befunde. Punktwerte, Prioritäten, Angebotsideen und Hypothesen bleiben intern.'}


def build(conn, lead_id, data):
    if not isinstance(data, dict) or set(data) - {'items', 'intro', 'title'}:
        raise ValueError('Kurzbericht: items, intro, title.')
    lead = _lead(conn, lead_id)
    from .workday import assert_contact_allowed
    assert_contact_allowed(conn, lead, 'Kurzbericht für den Kunden erstellen')
    ids = data.get('items')
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
        raise ValueError('Bitte mindestens einen geprüften Befund auswählen.')
    if len(set(ids)) > MAX_ITEMS:
        raise ValueError(f'Höchstens {MAX_ITEMS} Befunde – ein Kurzbericht soll kurz bleiben.')
    by_id = {i['id']: i for i in candidates(conn, lead_id)['items']}
    bad = [i for i in ids if i not in by_id]
    if bad:
        raise ValueError('Nur geprüfte Befunde dieser Firma sind wählbar (nicht wählbar: ' + ', '.join(bad[:5]) + ').')
    chosen = [by_id[i] for i in dict.fromkeys(ids)]
    title = _clean(data.get('title'))[:120] or f"Beobachtungen zur Website von {lead['company']}"
    intro = _clean(data.get('intro'))[:800]
    from .accounting import get_settings
    s = get_settings(conn)
    de = lambda iso: dt.date.fromisoformat(iso).strftime('%d.%m.%Y') if iso else ''
    lines = [f'# {title}', '', f"**Für:** {lead['company']} · **Stand:** {dt.date.today().strftime('%d.%m.%Y')}", '']
    if intro:
        lines += [intro, '']
    lines += ['## Was mir aufgefallen ist', '']
    for n, i in enumerate(chosen, 1):
        lines.append(f"### {n}. {i['title']}" + (f" ({i['area']})" if i['area'] else ''))
        if i['observation']:
            lines.append(i['observation'])
        if i['source_url']:
            lines.append(f"*Fundstelle: {i['source_url']}{' · Stand ' + de(i['as_of']) if i['as_of'] else ''}*")
        if i['question']:
            lines.append(f"**Frage an Sie:** {i['question']}")
        lines.append('')
    lines += ['## Einordnung',
              'Die Beobachtungen sind eine Momentaufnahme der öffentlich sichtbaren Website zum genannten Stand. Sie sind keine vollständige '
              'Prüfung, keine Rechtsberatung und keine Bewertung Ihres Unternehmens. Ob und was davon für Sie wichtig ist, klären wir gern im Gespräch.', '']
    who = ', '.join(x for x in (s.get('owner_name'), s.get('company_name')) if x)
    if who:
        lines.append(who)
    md = '\n'.join(lines).rstrip() + '\n'
    rid = conn.execute('INSERT INTO customer_reports(lead_id, items_json, markdown) VALUES (?,?,?)',
                       (lead_id, json.dumps([i['id'] for i in chosen]), md)).lastrowid
    conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)',
                 (lead_id, 'notiz', f'Kurzbericht für den Kunden erstellt ({len(chosen)} geprüfte Befunde) – nicht versendet.'))
    conn.commit()
    safe = re.sub(r'[^A-Za-z0-9]+', '-', lead['company']).strip('-')[:40] or 'Firma'
    return {'id': rid, 'filename': f'Kurzbericht-{safe}-{dt.date.today().isoformat()}.md', 'markdown': md, 'items': len(chosen),
            'notice': 'Kurzbericht erstellt, nicht versendet. Vor der Weitergabe lesen.'}


def route_customer_report(h, conn, method, route):
    m = re.fullmatch(r'/api/leads/(\d+)/kurzbericht', route)
    if not m:
        return False
    lid = int(m.group(1))
    if method == 'GET':
        h._send(200, candidates(conn, lid))
    elif method == 'POST':
        h._send(200, build(conn, lid, h._body()))
    else:
        return False
    return True
