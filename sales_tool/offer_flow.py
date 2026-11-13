"""Versandfassung, Versand, Zusage und Projektstart eines Angebots (2.0.0-dev17).

Ergänzungen aus dem Leitfaden zum Kundenonboarding vom 13.11.2026 (Roadmap M35, M36):

- **Versandfassung (M35).** Ein Angebot ist zunächst ein Entwurf; der Export trägt dann sichtbar „Entwurf – nicht zum Versand
  freigegeben“. Erst nach einer bewussten Freigabe (automatische Prüfungen bestanden, vier Prüfpunkte bestätigt) gibt es die
  Versandfassung ohne Entwurfshinweis, mit Stand-Kennung (Prüfsumme des gespeicherten Kundendokuments). Versand und Zusage
  lassen sich nur für einen freigegebenen Stand dokumentieren; gespeichert werden Ereignis, Zeitpunkt, Weg und der Stand.
- **Übergang nach Annahme (M36).** Die Zusage schlägt Startaufgaben vor und listet die noch offenen Nachfassaufgaben zu diesem
  Angebot. Angelegt bzw. beendet wird nur, was du bestätigst; ein erneuter Klick legt nichts doppelt an.

SignalDesk versendet weiterhin nichts. Ein Status dokumentiert nur, was außerhalb der App geschehen ist.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re

CHANNELS = {'email': 'per E-Mail', 'post': 'per Post', 'persoenlich': 'persönlich übergeben', 'portal': 'über ein Portal des Kunden',
            'sonstiges': 'auf anderem Weg'}
DECISION_CHANNELS = {'email': 'schriftlich per E-Mail', 'unterschrift': 'unterschriebenes Angebot', 'bestellung': 'Bestellung / Bestellnummer',
                     'muendlich': 'mündlich oder telefonisch', 'sonstiges': 'auf anderem Weg'}
# Die letzten Prüfungen vor dem Versand (Leitfaden Kundenonboarding, Kap. 4) – bewusst von Hand zu bestätigen
CONFIRMATIONS = {
    'empfaenger': 'Ansprechpartner, Unternehmen, Anrede, Projektbezeichnung und Angebotsnummer stimmen.',
    'inhalt': 'Preis, Umfang, Termine und Korrekturschleifen stimmen mit der geplanten Nachricht überein.',
    'lesbar': 'Anhang bzw. Link ist richtig benannt und auch auf dem Smartphone lesbar.',
    'naechster_schritt': 'Der Empfänger erfährt, was er jetzt tun kann und wann er wieder von mir hört.',
}
INTERNAL_KEYS = {'hours', 'rate', 'formula', 'effective_hourly', 'labor_eur', 'buffer_eur', 'calculated_eur', 'open_points', 'checks',
                 'catalog_version', 'need_confirmed_at', 'estimated_hours', 'cost_rate_eur', 'contribution_eur', 'contribution_pct',
                 'cost_with_buffer_eur', 'warnings', 'min_hourly_earning', 'hourly_rate'}
FOLLOWUP_RE = re.compile(r'nachfass|Rückfrage|prüfen und manuell versenden', re.I)


def init_offer_flow(conn):
    cols = {r[1] for r in conn.execute('PRAGMA table_info(proposals)')}
    for name in ('released_at', 'release_sha', 'sent_at', 'sent_channel', 'sent_sha', 'decided_at', 'decision_channel',
                 'decision_person', 'decision_note'):
        if name not in cols:
            conn.execute(f"ALTER TABLE proposals ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")


def stand(customer_json):
    """Stand-Kennung: Prüfsumme des gespeicherten Kundendokuments."""
    return hashlib.sha256(customer_json.encode('utf-8')).hexdigest()


def _row(conn, pid):
    row = conn.execute('SELECT * FROM proposals WHERE id=?', (pid,)).fetchone()
    if not row:
        raise LookupError('Angebot nicht gefunden.')
    return row


def _number(row):
    return row['number'] or f"#{row['id']}"


def _leaks(obj, path=''):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in INTERNAL_KEYS:
                out.append(path + k)
            out += _leaks(v, path + k + '.')
    elif isinstance(obj, list):
        for v in obj:
            out += _leaks(v, path)
    return out


def checks(conn, row):
    from .workday import contact_lock, need_status
    cust = json.loads(row['customer_json'])
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (row['lead_id'],)).fetchone()
    lock = contact_lock(conn, lead) if lead else 'nicht mehr vorhanden'
    need = need_status(conn, row['lead_id'], row['opportunity_id'])  # 2.0.0-dev19: Bedarf der Chance dieses Angebots
    today = dt.date.today().isoformat()
    leaks = sorted(set(_leaks(cust)))
    items = [
        {'key': 'steuer', 'label': 'Steuerstatus ist festgelegt', 'ok': cust.get('tax_mode') not in (None, '', 'offen'), 'detail': cust.get('tax_note', '')},
        {'key': 'bedarf', 'label': 'Bedarf ist im Gespräch bestätigt', 'ok': need['confirmed'],
         'detail': f"bestätigt am {need['confirmed_at'][:10]}" if need['confirmed'] else 'In der Firmenakte „Bedarf bestätigen“'},
        {'key': 'kontakt', 'label': 'Kontakt ist zulässig (keine Sperre, kein Widerspruch)', 'ok': not lock, 'detail': f'Firma ist {lock}' if lock else ''},
        {'key': 'frist', 'label': 'Bindefrist ist nicht abgelaufen', 'ok': not row['valid_until'] or row['valid_until'] >= today,
         'detail': f"gültig bis {row['valid_until']}" if row['valid_until'] else ''},
        {'key': 'intern', 'label': 'Kundendokument enthält keine internen Werte (Stunden, Sätze, Kalkulation)', 'ok': not leaks, 'detail': ', '.join(leaks)},
    ]
    hints = [x for x in json.loads(row['internal_json'] or '{}').get('open_points', []) if 'Zahlungsplan' not in x] if row['internal_json'] else []
    if cust.get('payment_plan'):
        hints.append(f"Zahlungsplan „{cust['payment_plan']}“ mit dem Kunden ausdrücklich vereinbaren.")
    if row['opportunity_id']:  # 2.0.0-dev20 (M14): Briefing der Chance
        from .briefing import get as briefing
        s = briefing(conn, row['opportunity_id'])['summary']
        if s['unbeantwortet']:
            hints.append(f"Briefing: {s['unbeantwortet']} Frage(n) noch unbeantwortet – als geklärt, offen oder entfällt markieren.")
        if s['offen'] and 'Offene Voraussetzungen' not in (cust.get('assumptions') or ''):
            hints.append(f"Briefing: {s['offen']} offene Voraussetzung(en) stehen noch nicht unter „Voraussetzungen“ im Angebot.")
    return {'checks': items, 'hints': hints, 'ready': all(i['ok'] for i in items)}


def state(conn, pid):
    row = _row(conn, pid)
    released = bool(row['released_at'])
    sha = row['release_sha']
    changed = released and stand(row['customer_json']) != sha
    num = _number(row)
    safe_num = re.sub(r'[^A-Za-z0-9-]+', '-', num).strip('-') or str(row['id'])
    return {'id': row['id'], 'number': num, 'status': row['status'], 'released': released, 'released_at': row['released_at'],
            'stand': sha[:8] if released else '', 'stand_changed': changed, 'sent_at': row['sent_at'], 'sent_channel': row['sent_channel'],
            'sent_stand': row['sent_sha'][:8], 'decided_at': row['decided_at'], 'decision_channel': row['decision_channel'],
            'decision_person': row['decision_person'], 'decision_note': row['decision_note'],
            'filename': f"Angebot_{safe_num}_Stand-{sha[:8]}.md" if released else f"ENTWURF_Angebot_{safe_num}.md",
            **checks(conn, row), 'confirmations': CONFIRMATIONS, 'channels': CHANNELS, 'decision_channels': DECISION_CHANNELS}


def release_info(row):
    """Für den Export: Stand-Kennung und Datum, falls freigegeben."""
    if not row['released_at']:
        return None
    return {'stand': row['release_sha'][:8], 'released_at': row['released_at'][:10], 'changed': stand(row['customer_json']) != row['release_sha']}


def release(conn, pid, data):
    if not isinstance(data, dict) or set(data) != {'confirm'} or not isinstance(data['confirm'], list):
        raise ValueError('Erwartet: {confirm: [Prüfpunkte]}.')
    row = _row(conn, pid)
    if row['released_at']:
        return state(conn, pid)  # bereits freigegeben – nichts ändert sich
    if row['status'] == 'abgelehnt':
        raise ValueError('Ein abgelehntes Angebot wird nicht mehr freigegeben.')
    c = checks(conn, row)
    if not c['ready']:
        raise ValueError('Freigabe noch nicht möglich: ' + '; '.join(i['label'] + (f" ({i['detail']})" if i['detail'] else '')
                                                                         for i in c['checks'] if not i['ok']) + '.')
    missing = [CONFIRMATIONS[k] for k in CONFIRMATIONS if k not in data['confirm']]
    if missing or set(data['confirm']) - set(CONFIRMATIONS):
        raise ValueError('Bitte alle Prüfpunkte bestätigen: ' + ' '.join(missing))
    sha = stand(row['customer_json'])
    conn.execute("UPDATE proposals SET released_at=datetime('now'), release_sha=?, updated_at=datetime('now') WHERE id=?", (sha, pid))
    conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)',
                 (row['lead_id'], 'notiz', f"Versandfassung von Angebot {_number(row)} freigegeben (Stand {sha[:8]}). Noch nichts versendet."))
    conn.commit()
    return state(conn, pid)


def _date(value, what):
    if value in (None, ''):
        return dt.date.today().isoformat()
    try:
        d = dt.date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{what}: Datum als JJJJ-MM-TT angeben.') from exc
    if d > dt.date.today():
        raise ValueError(f'{what}: Ein Datum in der Zukunft lässt sich nicht als geschehen dokumentieren.')
    return d.isoformat()


def _text(data, key, limit):
    v = data.get(key, '')
    if not isinstance(v, str) or len(v.strip()) > limit:
        raise ValueError(f'{key}: höchstens {limit} Zeichen.')
    return re.sub(r'\s+', ' ', v).strip()


def set_status(conn, pid, data):
    """Status dokumentieren – nur vorwärts: Entwurf → versendet → angenommen/abgelehnt."""
    from .sales_workspace import QUOTE_STATUSES
    from .workday import after_proposal_sent, assert_contact_allowed, assert_need_confirmed, _advance, _lead
    if not isinstance(data, dict) or 'status' not in data or set(data) - {'status', 'channel', 'date', 'person', 'note'} or data['status'] not in QUOTE_STATUSES:
        raise ValueError('Ungültiger Angebotsstatus.')
    row = _row(conn, pid)
    new, prev = data['status'], row['status']
    if new == prev:
        return {'saved': True, 'status': new, 'unchanged': True, 'notice': 'Status war bereits so dokumentiert – nichts geändert.'}
    if prev in ('angenommen', 'abgelehnt') or new == 'entwurf':
        raise ValueError('Ein dokumentierter Versand oder eine Entscheidung lässt sich nicht zurücknehmen. Bei einem Irrtum bitte eine '
                         'Notiz in der Firmenakte festhalten; für eine geänderte Fassung ein neues Angebot erstellen.')
    cust = json.loads(row['customer_json'])
    num = _number(row)
    if new in ('gesendet_manuell', 'angenommen'):
        if cust['tax_mode'] == 'offen':
            raise ValueError('Steuerstatus noch offen: Angebot nicht als gesendet/angenommen markieren.')
        lead = conn.execute('SELECT * FROM leads WHERE id=?', (row['lead_id'],)).fetchone()
        assert_contact_allowed(conn, lead, 'Angebot versenden/annehmen')
        assert_need_confirmed(conn, row['lead_id'], 'Angebot als gesendet/angenommen markieren', row['opportunity_id'])
        if not row['released_at']:
            from .workday import ContactLocked
            raise ContactLocked('Erst die Versandfassung freigeben: Versand und Zusage beziehen sich immer auf einen geprüften Stand.')
    when = _date(data.get('date'), 'Datum')
    if new == 'gesendet_manuell':
        channel = data.get('channel') or 'email'
        if channel not in CHANNELS:
            raise ValueError('Versandweg: ' + ', '.join(CHANNELS))
        conn.execute("""UPDATE proposals SET status=?, sent_at=?, sent_channel=?, sent_sha=release_sha, updated_at=datetime('now') WHERE id=?""",
                     (new, when, channel, pid))
        conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)',
                     (row['lead_id'], 'angebot', f"Angebot {num} (Stand {row['release_sha'][:8]}) am {when} {CHANNELS[channel]} versendet – außerhalb von SignalDesk."))
        follow = (dt.date.today() + dt.timedelta(days=7)).isoformat()
        conn.execute('INSERT INTO tasks(lead_id,title,due_date) VALUES (?,?,?)', (row['lead_id'], f'Angebotsstatus und zulässige Rückfrage prüfen (#{pid})', follow))
        after_proposal_sent(conn, row['lead_id'], num)
        from .chances import advance
        advance(conn, row['opportunity_id'], 'angebot')  # 2.0.0-dev18: Phase der zugehörigen Chance
        conn.commit()
        return {'saved': True, 'status': new, 'notice': 'Der Versand ist dokumentiert. SignalDesk hat nichts gesendet.'}
    channel = data.get('channel') or ('email' if new == 'angenommen' else '')
    if channel and channel not in DECISION_CHANNELS:
        raise ValueError('Weg der Entscheidung: ' + ', '.join(DECISION_CHANNELS))
    person, note = _text(data, 'person', 120), _text(data, 'note', 500)
    conn.execute("""UPDATE proposals SET status=?, decided_at=?, decision_channel=?, decision_person=?, decision_note=?, updated_at=datetime('now')
                    WHERE id=?""", (new, when, channel, person, note, pid))
    if new == 'angenommen':
        lead = conn.execute('SELECT stage FROM leads WHERE id=?', (row['lead_id'],)).fetchone()
        if lead and lead['stage'] not in ('gesperrt', 'gewonnen'):
            conn.execute("UPDATE leads SET stage='gewonnen', updated_at=datetime('now') WHERE id=?", (row['lead_id'],))
        how = ', '.join(x for x in (DECISION_CHANNELS.get(channel, ''), f'von {person}' if person else '', f'am {when}') if x)
        conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)',
                     (row['lead_id'], 'abschluss', f"Angebot {num} (Stand {row['release_sha'][:8]}) als angenommen dokumentiert: {how}."
                      + (f' {note}' if note else '') + ' Nächster Schritt: Projektstart.'))
        _advance(conn, _lead(conn, row['lead_id']), None, f'Projektstart {num}: Startaufgaben anlegen', 0)
        from .chances import win
        win(conn, row['opportunity_id'])  # 2.0.0-dev18: nur diese Chance ist gewonnen; andere bleiben offen
        notice = 'Zusage dokumentiert. Bitte jetzt den Projektstart festlegen – Startaufgaben und offene Nachfassaufgaben prüfen.'
    else:
        conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)',
                     (row['lead_id'], 'angebot', f"Angebot {num} als abgelehnt dokumentiert ({when})." + (f' {note}' if note else '')))
        notice = 'Absage dokumentiert. Offene Nachfassaufgaben zu diesem Angebot bitte bewusst beenden.'
    conn.commit()
    return {'saved': True, 'status': new, 'notice': notice, 'start': start_plan(conn, pid)}


# ---------------------------------------------------------------- Projektstart (M36)

def _suggestions(row):
    from .catalog import SERVICES, VORLAGEN
    cust = json.loads(row['customer_json'])
    keys = [p.get('service') for p in cust.get('positions') or []] or [p['service'] for p in VORLAGEN.get(cust.get('package'), {}).get('positions', [])]
    areas = {a for k in keys if k in SERVICES for a in SERVICES[k]['areas']}
    if not keys:
        areas = {'medien', 'software'}  # unbekannter Umfang: beides vorschlagen, du wählst ab
    label = (cust.get('project_label') or '').strip()
    label = label if len(label) <= 50 else label[:49] + '…'
    head = f"{_number(row)}{' ' + label if label else ''}"
    items = [('bestaetigung', 'Auftrag persönlich bestätigen: Dank, nächster Schritt, Ansprechpartner', 0),
             ('startgespraech', 'Startgespräch vereinbaren', 2)]
    if 'medien' in areas:
        items.append(('material', 'Benötigte Materialien und Nutzungsrechte anfragen – wer liefert was bis wann', 2))
    if 'software' in areas:
        items.append(('zugaenge', 'Zugänge, Schnittstellen und Testdaten klären – keine Passwörter per Mail', 2))
    items += [('ueberblick', 'Kurzüberblick an den Kunden: Ziel, Umfang, Termine, Abnahme', 3),
              ('zwischenstand', 'Ersten Zwischenstand terminieren', 7)]
    return [{'key': k, 'title': f'{head}: {text}', 'days': days} for k, text, days in items]


def start_plan(conn, pid):
    row = _row(conn, pid)
    num = _number(row)
    sugg = []
    if row['status'] == 'angenommen':
        for s in _suggestions(row):
            ex = conn.execute('SELECT done FROM tasks WHERE lead_id=? AND title=? ORDER BY id DESC LIMIT 1', (row['lead_id'], s['title'])).fetchone()
            sugg.append({**s, 'exists': bool(ex), 'done': bool(ex and ex['done'])})
    follow = [{'id': t['id'], 'title': t['title'], 'due_date': t['due_date']}
              for t in conn.execute('SELECT id, title, due_date FROM tasks WHERE lead_id=? AND done=0 ORDER BY id', (row['lead_id'],))
              if (num in t['title'] or f'#{pid})' in t['title']) and FOLLOWUP_RE.search(t['title'])]
    lead = conn.execute('SELECT next_step FROM leads WHERE id=?', (row['lead_id'],)).fetchone()
    return {'proposal_id': pid, 'number': num, 'status': row['status'], 'suggestions': sugg, 'followups': follow,
            'next_step': lead['next_step'] if lead else ''}


def start(conn, pid, data):
    if not isinstance(data, dict) or set(data) - {'create', 'close'} or not all(isinstance(data.get(k, []), list) for k in ('create', 'close')):
        raise ValueError('Erwartet: {create: [Startaufgaben], close: [Aufgaben-IDs]}.')
    row = _row(conn, pid)
    if row['status'] not in ('angenommen', 'abgelehnt'):
        raise ValueError('Projektstart erst nach einer dokumentierten Zusage; Nachfassaufgaben beenden nach Zusage oder Absage.')
    if data.get('create') and row['status'] != 'angenommen':
        raise ValueError('Startaufgaben nur bei angenommenem Angebot.')
    plan = start_plan(conn, pid)
    by_key = {s['key']: s for s in plan['suggestions']}
    unknown = [k for k in data.get('create', []) if k not in by_key]
    if unknown:
        raise ValueError('Unbekannte Startaufgabe: ' + ', '.join(map(str, unknown)))
    allowed = {f['id'] for f in plan['followups']}
    bad = [i for i in data.get('close', []) if i not in allowed]
    if bad:
        raise ValueError('Nur offene Nachfassaufgaben zu diesem Angebot lassen sich hier beenden.')
    created = 0
    for key in dict.fromkeys(data.get('create', [])):
        s = by_key[key]
        if s['exists']:
            continue  # erneuter Klick: nichts doppelt anlegen
        conn.execute('INSERT INTO tasks(lead_id, title, due_date) VALUES (?,?,?)',
                     (row['lead_id'], s['title'], (dt.date.today() + dt.timedelta(days=s['days'])).isoformat()))
        created += 1
    closed = 0
    for tid in dict.fromkeys(data.get('close', [])):
        closed += conn.execute("UPDATE tasks SET done=1, done_at=datetime('now') WHERE id=? AND done=0", (tid,)).rowcount
    if created or closed:
        conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)',
                     (row['lead_id'], 'notiz', f"Angebot {plan['number']}: {created} Startaufgabe(n) angelegt, {closed} Nachfassaufgabe(n) bewusst beendet."))
    if row['status'] == 'angenommen' and created:
        from .workday import _advance, _lead
        _advance(conn, _lead(conn, row['lead_id']), None, f"Projektstart {plan['number']}: Startgespräch vereinbaren", 2)
    conn.commit()
    return {**start_plan(conn, pid), 'created': created, 'closed': closed}


def route_offer_flow(h, conn, method, route):
    m = re.fullmatch(r'/api/workspace/proposals/(\d+)/(versand|freigabe|start)', route)
    if not m:
        return False
    pid, what = int(m.group(1)), m.group(2)
    if what == 'versand' and method == 'GET':
        h._send(200, state(conn, pid))
    elif what == 'freigabe' and method == 'POST':
        h._send(200, release(conn, pid, h._body()))
    elif what == 'start' and method == 'GET':
        h._send(200, start_plan(conn, pid))
    elif what == 'start' and method == 'POST':
        h._send(200, start(conn, pid, h._body()))
    else:
        return False
    return True
