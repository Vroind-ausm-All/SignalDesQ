"""Firmendaten automatisch aus dem Impressum ins Firmenprofil übertragen (SignalDesk v1.19).

Behebt: „Die automatische Datenübertragung ins Firmenprofil funktioniert nicht.“ Ursachen bis v1.18:
1. Seit Empfehlung A (v1.15) ist eine *gefundene* Website ohne Registernummer-Treffer nur ein Vorschlag. Beim Übernehmen
   wurde sie am Lead entfernt, die schon gelesenen Impressumsdaten nicht übertragen – und bestätigen ließ sich der
   Vorschlag danach nirgends mehr. Damit konnte auch der Firmen-Bericht nichts nachholen (Lead ohne Website).
2. Eine Website „laut Quelle“ (OSM, Wikidata) oder eine von Hand eingetragene Website löste kein Lesen des Impressums aus.
3. „Impressum prüfen“ im Lead-Fenster verlangte eine manuelle Übernahme unter „Import & Prüfung“.

Jetzt: Sobald ein Lead eine bestätigte Website hat (laut Quelle, belegt, von dir bestätigt oder selbst eingetragen),
liest ein Hintergrund-Auftrag das Impressum und überträgt die belegten Firmendaten in LEERE Felder. Vorhandene Werte
werden nie überschrieben, Personen nie automatisch angelegt, die Kontakterlaubnis bleibt unverändert. Ein offener
Website-Vorschlag steht in der Firmenakte mit „Passt / Passt nicht“.
"""
from __future__ import annotations

import json

from .company_data import check_suppressed, normalize_domain
from .research import jobs

ENABLED = False  # schaltet server.main() ein; in Tests aus, damit niemand unbeabsichtigt Websites abruft
SETTING = 'auto_imprint'
SUGGESTION = ('wahrscheinlich', 'nicht_bestaetigt')


def auto_enabled(conn):
    from .quality import get_setting
    return bool(get_setting(conn, SETTING, {'enabled': True}).get('enabled', True))


def apply_for_lead(conn, db_path, lead):
    """Impressum lesen und belegte Firmendaten in leere Felder übernehmen. Gibt (status, hinweis, refs, übernommen) zurück.
    status: 'fertig' | 'hinweis' (kein Impressum) | 'fehler' (nicht erreichbar)."""
    from . import imprint_batch as ib
    from .company_data import add_fact
    run = ib.create_run(conn, {'lead_id': lead['id'], 'label': f"Firmendaten: {lead['company']}"[:120], 'parallel': 1}, db_path, start=False)
    item = run['items'][0]
    if item['status'] == 'pending':
        ib._process(db_path, item['id'], True)
    row = conn.execute('SELECT status, error, result_json FROM batch_items WHERE id=?', (item['id'],)).fetchone()
    if row['status'] != 'done':
        return ('fehler' if row['status'] == 'failed' else 'hinweis'), row['error'] or 'Kein Impressum gefunden.', {'imprint_item': item['id']}, []
    result = json.loads(row['result_json'])
    fields = result.get('fields') or {}
    found = [k for k, v in fields.items() if v and v.get('value')]
    applied, note = [], ''
    try:
        r = ib.review_item(conn, item['id'], {'decision': 'ergaenzen', 'lead_id': lead['id'], 'include_representatives': False})
        applied = r['applied']
        note = f" · {len(applied)} automatisch übernommen" + (f", {len(r['kept_existing'])} vorhandene Werte behalten" if r['kept_existing'] else '')
    except ValueError as exc:
        note = f' · nicht übernommen: {exc}'
    n_struct = 0
    for ev in (result.get('structured') or {}).get('evidence', [])[:20]:
        if add_fact(conn, lead['id'], ev['field'], ev['value'], 'website_strukturiert', ev['source_url'], ev['evidence'], ev['method'], 'mittel', 'ungeprueft'):
            n_struct += 1
    if n_struct:
        note += f' · {n_struct} strukturierte Angaben der Website als Beleg gespeichert'
    legal = (fields.get('legal_name') or {}).get('value')
    if legal and lead['company'] == normalize_domain(lead['website']):
        conn.execute("UPDATE leads SET company=?, updated_at=datetime('now') WHERE id=?", (legal[:200], lead['id']))
    rejected = [w for w in result.get('warnings') or [] if w.startswith('Nicht im Originaltext belegbar')]
    if rejected:
        note += ' · ' + rejected[0]
    conn.commit()
    return 'fertig', f'{len(found)} Felder ausgelesen{note}', {'imprint_item': item['id']}, applied


@jobs.handler('lead_imprint')
def _job(db_path, payload, ctx):
    from .model import connect
    from .website_analyzer import CrawlError  # noqa: F401 – Fehlerarten kommen über batch_items
    with connect(db_path) as conn:
        lead = conn.execute('SELECT * FROM leads WHERE id=?', (payload['lead_id'],)).fetchone()
        if not lead or not lead['website']:
            raise jobs.Skip('Lead ohne Website.')
        if check_suppressed(conn, website=lead['website'], name=lead['company']):
            raise jobs.Skip('Firma auf der Sperrliste – Website wird nicht abgerufen.')
        status, note, refs, applied = apply_for_lead(conn, db_path, lead)
    if status == 'fehler':
        if any(k in note.lower() for k in ('zeitüberschreitung', 'timed out', 'verbindung', 'nicht erreichbar', 'http 5', 'http 429')):
            raise jobs.Retry(note)
        return {'_status': 'failed', '_error': note, **refs}
    if status == 'hinweis':
        return {'_status': 'skipped', '_error': note, **refs}
    return {'note': note, 'applied': applied, **refs}


def queue(conn, db_path, lead_id, reason='', start=True, force=False):
    """Plant das Lesen des Impressums für einen Lead ein. Gibt den Auftrag zurück oder None (nicht nötig/abgeschaltet)."""
    if not force and (not ENABLED or not auto_enabled(conn)):
        return None
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not lead or not lead['website'] or lead['stage'] == 'gesperrt' or lead['permission'] == 'nicht_kontaktieren':
        return None
    if check_suppressed(conn, website=lead['website'], name=lead['company']):
        return None
    if not force and lead['imprint_checked_at']:
        return None  # schon gelesen – erneut nur auf Knopfdruck
    job, _ = jobs.submit(conn, 'lead_imprint', f"Firmendaten aus dem Impressum: {lead['company']}"[:200],
                         [{'key': f'imprint:{lead_id}', 'kind': 'lead_imprint', 'label': lead['company'][:120],
                           'domain': normalize_domain(lead['website']), 'payload': {'lead_id': lead_id, 'reason': reason[:80]}}],
                         job_key=f'imprint:{lead_id}', db_path=db_path, start=start, max_attempts=3)
    return job


def suggestion_for(conn, lead_id):
    r = conn.execute(f"""SELECT * FROM discovery_candidates WHERE lead_id=? AND website<>'' AND website_status IN ({','.join('?' * len(SUGGESTION))})
                         ORDER BY id DESC LIMIT 1""", (lead_id, *SUGGESTION)).fetchone()
    if not r:
        return None
    imp = json.loads(r['imprint_json'] or '{}')
    return {'candidate_id': r['id'], 'website': r['website'], 'evidence': r['website_evidence'],
            'fields': sorted(k for k, v in (imp.get('fields') or {}).items() if v and v.get('value'))}


def review_suggestion(conn, db_path, lead_id, decision):
    """Website-Vorschlag aus der Firmenakte bestätigen oder ablehnen. Bestätigt → Website am Lead, Impressumsdaten übernehmen."""
    from . import sweep as sw
    s = suggestion_for(conn, lead_id)
    if not s:
        raise ValueError('Für diesen Lead gibt es keinen offenen Website-Vorschlag.')
    if decision not in ('bestaetigen', 'ablehnen'):
        raise ValueError('Entscheidung: bestaetigen oder ablehnen.')
    sw.review_website(conn, s['candidate_id'], {'decision': decision})
    conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)',
                 (lead_id, 'notiz', f"Website-Vorschlag {s['website']} " + ('von dir bestätigt.' if decision == 'bestaetigen' else 'von dir abgelehnt.')))
    conn.commit()
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    queued = None
    if decision == 'bestaetigen' and not lead['imprint_checked_at']:
        # Daten aus der Website-Suche wurden (falls vorhanden) gerade übertragen; sonst Impressum jetzt lesen
        queued = queue(conn, db_path, lead_id, 'Website bestätigt', force=True)
    return {'decision': decision, 'website': lead['website'], 'queued': bool(queued), 'status': status(conn, lead_id)}


def status(conn, lead_id):
    """Für die Firmenakte: Wurden Firmendaten übertragen? Wenn nein – warum nicht, und was hilft?"""
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not lead:
        raise LookupError('Lead nicht gefunden.')
    task = conn.execute("""SELECT t.status, t.last_error, t.note, t.result_json, t.next_attempt_at FROM research_tasks t
                           WHERE t.kind='lead_imprint' AND t.task_key=? ORDER BY t.id DESC LIMIT 1""", (f'imprint:{lead_id}',)).fetchone()
    item = conn.execute("""SELECT status, error, review_status, finished_at FROM batch_items WHERE lead_id=? OR duplicate_lead_id=?
                           ORDER BY id DESC LIMIT 1""", (lead_id, lead_id)).fetchone()
    act = conn.execute("""SELECT detail, created_at FROM activities WHERE lead_id=? AND (detail LIKE 'Impressum geprüft%' OR detail LIKE 'Aus dem Impressum automatisch%'
                          OR detail LIKE 'Quellen:%Aus dem Impressum%') ORDER BY id DESC LIMIT 1""", (lead_id,)).fetchone()
    sug = suggestion_for(conn, lead_id)
    filled = [k for k in ('legal_name', 'street', 'zip', 'city', 'register_number', 'vat_id', 'business_phone', 'business_email') if lead[k]]
    base = {'auto': auto_enabled(conn), 'suggestion': sug, 'filled': filled, 'checked_at': lead['imprint_checked_at'] or '',
            'imprint_url': lead['imprint_url'] or '', 'can_run': bool(lead['website']) and lead['stage'] != 'gesperrt'}
    if task and task['status'] in ('queued', 'running'):
        return {**base, 'state': 'laeuft', 'detail': 'Impressum wird gelesen …' if task['status'] == 'running' else (task['note'] or 'wartet auf einen freien Platz')}
    if sug and not lead['website']:
        return {**base, 'state': 'vorschlag', 'detail': f"Website-Vorschlag {sug['website']} bestätigen – danach werden die Firmendaten übertragen."}
    if not lead['website']:
        return {**base, 'state': 'ohne_website', 'detail': 'Keine Website bekannt – Website eintragen, dann werden die Firmendaten automatisch gelesen.'}
    if lead['imprint_checked_at'] and act:
        return {**base, 'state': 'uebernommen', 'detail': act['detail'][:300], 'at': act['created_at']}
    if item and item['status'] in ('failed', 'kein_impressum', 'gesperrt'):
        return {**base, 'state': 'fehler' if item['status'] == 'failed' else 'kein_impressum', 'detail': item['error'] or 'Kein Impressum gefunden.'}
    if task and task['status'] in ('failed', 'skipped'):
        return {**base, 'state': 'fehler', 'detail': task['last_error'] or 'nicht gelesen'}
    if lead['imprint_checked_at']:
        return {**base, 'state': 'uebernommen', 'detail': 'Impressum gelesen.'}
    return {**base, 'state': 'offen', 'detail': 'Impressum noch nicht gelesen.'}


def route_lead_imprint(h, conn, method, route, query, db_path):
    import re
    m = re.fullmatch(r'/api/leads/(\d+)/(company-data|company-data/read|website-suggestion)', route)
    if not m:
        if route == '/api/settings/auto-imprint':
            from .quality import put_setting
            if method == 'GET':
                h._send(200, {'enabled': auto_enabled(conn)})
                return True
            if method == 'PUT':
                b = h._body()
                if set(b) != {'enabled'} or not isinstance(b['enabled'], bool):
                    raise ValueError('Erwartet: {enabled: true/false}.')
                put_setting(conn, SETTING, {'enabled': b['enabled']})
                conn.commit()
                h._send(200, {'enabled': b['enabled']})
                return True
        return False
    lid, what = int(m.group(1)), m.group(2)
    if what == 'company-data' and method == 'GET':
        h._send(200, status(conn, lid))
        return True
    if what == 'company-data/read' and method == 'POST':
        lead = conn.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone()
        if not lead:
            raise LookupError('Lead nicht gefunden.')
        if not lead['website']:
            raise ValueError('Lead hat keine Website.')
        job = queue(conn, db_path, lid, 'auf Knopfdruck', force=True)
        if not job:
            raise ValueError('Für gesperrte Firmen wird die Website nicht abgerufen.')
        h._send(202, {'job': job, 'status': status(conn, lid)})
        return True
    if what == 'website-suggestion' and method == 'POST':
        b = h._body()
        if set(b) != {'decision'}:
            raise ValueError('Erwartet: {decision}.')
        h._send(200, review_suggestion(conn, db_path, lid, b['decision']))
        return True
    return False
