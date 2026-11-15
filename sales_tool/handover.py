"""Schlanke Auftragsübergabe und Abnahme (2.0.0-dev24, Produktreview M17, Abnahmefall T12).

Ablauf je angenommenem Angebot:
1. Liefergegenstände und Abnahmekriterien kommen aus dem angenommenen Angebot (eigene Punkte lassen sich ergänzen).
   Jeder Punkt ist offen, erledigt oder entfällt (mit Begründung).
2. Übergabe dokumentieren, sobald kein Liefergegenstand mehr offen ist: Datum, Weg und eine Frist für die Abnahme.
3. Abnahme dokumentieren: abgenommen, abgenommen mit Restpunkten (Vorbehalt) oder Nachbesserung nötig. Restpunkte und
   Nachbesserungen werden Aufgaben mit Frist; nach einer Nachbesserung folgt eine neue Übergabe.
4. Abnahmeprotokoll als Markdown für den Kunden – vor der Abnahme als Entwurf zum Unterschreiben, danach mit Ergebnis.

SignalDesk versendet nichts und stellt keine Rechnung von selbst; es weist auf eine fällige Schlussrechnung hin.
Dokumentierte Übergaben und Abnahmen lassen sich nicht zurücknehmen (Nachweis); Irrtümer bitte als Notiz festhalten.
"""
from __future__ import annotations

import datetime as dt
import json
import re

CHANNELS = {'email': 'per E-Mail', 'termin': 'im Termin', 'telefon': 'telefonisch', 'brief': 'per Brief', 'portal': 'über ein Kundenportal'}
RESULTS = {'abgenommen': 'Abgenommen', 'vorbehalt': 'Abgenommen mit Restpunkten', 'nachbesserung': 'Nachbesserung nötig'}
KINDS = {'liefer': 'Liefergegenstand', 'kriterium': 'Abnahmekriterium', 'restpunkt': 'Restpunkt', 'nachbesserung': 'Nachbesserung'}
STATES = ('offen', 'erledigt', 'entfaellt')
STATUS_LABEL = {'in_arbeit': 'in Arbeit', 'uebergeben': 'übergeben – Abnahme ausstehend', 'nachbesserung': 'Nachbesserung läuft',
                'vorbehalt': 'abgenommen, Restpunkte offen', 'abgenommen': 'abgenommen'}


def init_handover(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS handovers (
        proposal_id INTEGER PRIMARY KEY REFERENCES proposals(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'in_arbeit', round INTEGER NOT NULL DEFAULT 1,
        handed_at TEXT NOT NULL DEFAULT '', handed_channel TEXT NOT NULL DEFAULT '', handed_note TEXT NOT NULL DEFAULT '',
        accepted_at TEXT NOT NULL DEFAULT '', accepted_channel TEXT NOT NULL DEFAULT '', accepted_person TEXT NOT NULL DEFAULT '',
        accepted_note TEXT NOT NULL DEFAULT '', result TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS handover_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proposal_id INTEGER NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
        kind TEXT NOT NULL, label TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'offen', note TEXT NOT NULL DEFAULT '',
        due_date TEXT NOT NULL DEFAULT '', task_id INTEGER, round INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_handover_items ON handover_items(proposal_id, kind);
    ''')


def _clean(v, limit, what, required=False):
    if v is None:
        v = ''
    if not isinstance(v, str) or len(v.strip()) > limit:
        raise ValueError(f'{what}: höchstens {limit} Zeichen.')
    v = re.sub(r'\s+', ' ', v).strip()
    if required and not v:
        raise ValueError(f'{what}: bitte angeben.')
    return v


def _past(value, what, not_before=''):
    if value in (None, ''):
        d = dt.date.today()
    else:
        try:
            d = dt.date.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'{what}: Datum als JJJJ-MM-TT angeben.') from exc
    if d > dt.date.today():
        raise ValueError(f'{what}: Ein Datum in der Zukunft lässt sich nicht als geschehen dokumentieren.')
    if not_before and d.isoformat() < not_before:
        raise ValueError(f'{what}: liegt vor der Übergabe am {dt.date.fromisoformat(not_before).strftime("%d.%m.%Y")}.')
    return d.isoformat()


def _due(value, default_days=7):
    if value in (None, ''):
        return (dt.date.today() + dt.timedelta(days=default_days)).isoformat()
    try:
        d = dt.date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Frist: Datum als JJJJ-MM-TT angeben.') from exc
    if d < dt.date.today() or d > dt.date.today() + dt.timedelta(days=180):
        raise ValueError('Frist: ab heute, höchstens 180 Tage im Voraus.')
    return d.isoformat()


def _proposal(conn, pid):
    row = conn.execute('SELECT p.*, l.company FROM proposals p JOIN leads l ON l.id=p.lead_id WHERE p.id=?', (pid,)).fetchone()
    if not row:
        raise LookupError('Angebot nicht gefunden.')
    if row['status'] != 'angenommen' or row['superseded_by']:
        raise ValueError('Übergabe und Abnahme gibt es nur für ein angenommenes, aktuelles Angebot.')
    return row


def _number(row):
    return row['number'] or f"#{row['id']}"


def _ensure(conn, row):
    """Beim ersten Öffnen: Punkte aus dem angenommenen Angebot übernehmen (Liefergegenstände, Abnahmekriterien)."""
    if conn.execute('SELECT 1 FROM handovers WHERE proposal_id=?', (row['id'],)).fetchone():
        return
    cust = json.loads(row['customer_json'] or '{}')
    deliver = cust.get('deliverables') or cust.get('included') or []
    if not deliver:
        deliver = [f"{p.get('title')} – {p.get('scope')}" for p in cust.get('positions') or [] if not p.get('optional')]
    conn.execute('INSERT INTO handovers(proposal_id) VALUES (?)', (row['id'],))
    for kind, items in (('liefer', deliver), ('kriterium', cust.get('acceptance_criteria') or [])):
        for label in dict.fromkeys(str(x).strip() for x in items if str(x).strip()):
            conn.execute('INSERT INTO handover_items(proposal_id, kind, label) VALUES (?,?,?)', (row['id'], kind, label[:300]))
    conn.commit()


def state(conn, pid):
    row = _proposal(conn, pid)
    _ensure(conn, row)
    h = conn.execute('SELECT * FROM handovers WHERE proposal_id=?', (pid,)).fetchone()
    items = [dict(r) for r in conn.execute('SELECT id, kind, label, state, note, due_date, round FROM handover_items WHERE proposal_id=? ORDER BY id', (pid,))]
    for i in items:
        i['kind_label'] = KINDS.get(i['kind'], i['kind'])
    blocking = [i for i in items if i['kind'] in ('liefer', 'nachbesserung') and i['state'] == 'offen']
    rest_open = [i for i in items if i['kind'] == 'restpunkt' and i['state'] == 'offen']
    cust = json.loads(row['customer_json'] or '{}')
    final_invoice = 'nach Abnahme' in (cust.get('payment_plan') or '')
    return {'proposal_id': pid, 'number': _number(row), 'company': row['company'], 'project_label': cust.get('project_label', ''),
            'status': h['status'], 'status_label': STATUS_LABEL.get(h['status'], h['status']), 'round': h['round'],
            'handed_at': h['handed_at'], 'handed_channel': h['handed_channel'], 'handed_note': h['handed_note'],
            'accepted_at': h['accepted_at'], 'accepted_channel': h['accepted_channel'], 'accepted_person': h['accepted_person'],
            'accepted_note': h['accepted_note'], 'result': h['result'], 'result_label': RESULTS.get(h['result'], ''),
            'items': items, 'blocking': len(blocking), 'rest_open': len(rest_open),
            'can_hand_over': h['status'] in ('in_arbeit', 'nachbesserung') and not blocking,
            'can_accept': h['status'] == 'uebergeben', 'final_invoice_due': final_invoice and h['status'] in ('abgenommen', 'vorbehalt'),
            'channels': CHANNELS, 'results': RESULTS, 'states': STATES, 'default_due': _due(None)}


def _log(conn, row, text):
    conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)', (row['lead_id'], 'projekt', f"Auftrag {_number(row)}: {text}"))


def _task(conn, row, title, due, kind):
    return conn.execute('''INSERT INTO tasks(lead_id, title, due_date, proposal_id, opportunity_id, reason, action_type) VALUES (?,?,?,?,?,?,?)''',
                        (row['lead_id'], f"{_number(row)}: {title}"[:250], due, row['id'], row['opportunity_id'], title[:160], kind)).lastrowid


def _close_tasks(conn, pid, kind, outcome):
    conn.execute("UPDATE tasks SET done=1, done_at=datetime('now'), outcome=? WHERE proposal_id=? AND action_type=? AND done=0", (outcome, pid, kind))


def act(conn, pid, data):
    if not isinstance(data, dict) or data.get('action') not in ('item', 'add', 'uebergabe', 'abnahme'):
        raise ValueError('Aktion: item, add, uebergabe oder abnahme.')
    row = _proposal(conn, pid)
    _ensure(conn, row)
    h = conn.execute('SELECT * FROM handovers WHERE proposal_id=?', (pid,)).fetchone()
    action, notice = data['action'], ''
    if action == 'item':
        if set(data) - {'action', 'item_id', 'state', 'note'} or data.get('state') not in STATES:
            raise ValueError('Punkt: Status offen, erledigt oder entfaellt.')
        it = conn.execute('SELECT * FROM handover_items WHERE id=? AND proposal_id=?', (data.get('item_id'), pid)).fetchone()
        if not it:
            raise LookupError('Punkt nicht gefunden.')
        note = _clean(data.get('note'), 300, 'Notiz')
        if data['state'] == 'entfaellt' and not note:
            raise ValueError('Bitte begründen, warum der Punkt entfällt (z. B. „auf Kundenwunsch gestrichen“).')
        if it['kind'] in ('liefer', 'kriterium') and h['status'] in ('abgenommen', 'vorbehalt'):
            raise ValueError('Nach der Abnahme bleibt der abgenommene Stand, wie er ist. Neue Arbeit ist ein Restpunkt oder ein Zusatzauftrag.')
        conn.execute("UPDATE handover_items SET state=?, note=?, updated_at=datetime('now') WHERE id=?", (data['state'], note, it['id']))
        if it['task_id']:
            conn.execute("UPDATE tasks SET done=?, done_at=CASE WHEN ?=1 THEN datetime('now') ELSE '' END WHERE id=?",
                         (int(data['state'] != 'offen'), int(data['state'] != 'offen'), it['task_id']))
        if it['kind'] == 'restpunkt' and h['status'] == 'vorbehalt' and not conn.execute(
                "SELECT 1 FROM handover_items WHERE proposal_id=? AND kind='restpunkt' AND state='offen'", (pid,)).fetchone():
            conn.execute("UPDATE handovers SET status='abgenommen' WHERE proposal_id=?", (pid,))
            _log(conn, row, 'Alle Restpunkte der Abnahme erledigt.')
            notice = 'Alle Restpunkte erledigt – der Auftrag gilt jetzt als vollständig abgenommen.'
    elif action == 'add':
        if set(data) - {'action', 'kind', 'label'} or data.get('kind') not in ('liefer', 'kriterium'):
            raise ValueError('Eigener Punkt: Art liefer oder kriterium.')
        if h['status'] not in ('in_arbeit', 'nachbesserung'):
            raise ValueError('Nach der Übergabe lassen sich keine Liefergegenstände mehr ergänzen.')
        conn.execute('INSERT INTO handover_items(proposal_id, kind, label, round) VALUES (?,?,?,?)',
                     (pid, data['kind'], _clean(data.get('label'), 300, 'Bezeichnung', True), h['round']))
    elif action == 'uebergabe':
        if set(data) - {'action', 'date', 'channel', 'note', 'due'}:
            raise ValueError('Übergabe: date, channel, note, due.')
        if h['status'] not in ('in_arbeit', 'nachbesserung'):
            raise ValueError('Die Übergabe ist bereits dokumentiert.')
        open_ = conn.execute("SELECT label FROM handover_items WHERE proposal_id=? AND kind IN ('liefer','nachbesserung') AND state='offen'", (pid,)).fetchall()
        if open_:
            raise ValueError(f"Noch {len(open_)} Liefergegenstand/Nachbesserung offen (z. B. „{open_[0]['label'][:80]}“). Erledigen oder begründet entfallen lassen.")
        channel = data.get('channel') or 'email'
        if channel not in CHANNELS:
            raise ValueError('Weg: ' + ', '.join(CHANNELS))
        when, due, note = _past(data.get('date'), 'Übergabe am'), _due(data.get('due')), _clean(data.get('note'), 500, 'Notiz')
        conn.execute("UPDATE handovers SET status='uebergeben', handed_at=?, handed_channel=?, handed_note=? WHERE proposal_id=?", (when, channel, note, pid))
        _task(conn, row, 'Abnahme einholen', due, 'abnahme')
        _log(conn, row, f"{'Erneute ' if h['round'] > 1 else ''}Übergabe am {when} {CHANNELS[channel]} dokumentiert" + (f' – {note}' if note else '') + '.')
        notice = f"Übergabe dokumentiert. Abnahme einholen bis {dt.date.fromisoformat(due).strftime('%d.%m.%Y')}."
    else:
        if set(data) - {'action', 'result', 'date', 'channel', 'person', 'note', 'points'} or data.get('result') not in RESULTS:
            raise ValueError('Abnahme: Ergebnis ' + ', '.join(RESULTS))
        if h['status'] != 'uebergeben':
            raise ValueError('Erst die Übergabe dokumentieren – abgenommen wird ein übergebener Stand.')
        channel = data.get('channel') or 'email'
        if channel not in CHANNELS:
            raise ValueError('Weg: ' + ', '.join(CHANNELS))
        result = data['result']
        when = _past(data.get('date'), 'Abnahme am', h['handed_at'])
        person, note = _clean(data.get('person'), 120, 'Person'), _clean(data.get('note'), 500, 'Notiz')
        points = data.get('points') or []
        if not isinstance(points, list) or len(points) > 30:
            raise ValueError('Punkte: Liste mit höchstens 30 Einträgen.')
        clean_points = []
        for p in points:
            if not isinstance(p, dict) or set(p) - {'label', 'due'}:
                raise ValueError('Punkt: {label, due}.')
            clean_points.append((_clean(p.get('label'), 300, 'Punkt', True), _due(p.get('due'))))
        if result != 'abgenommen' and not clean_points:
            raise ValueError('Bitte die Restpunkte bzw. Nachbesserungen einzeln nennen – sie werden zu Aufgaben mit Frist.')
        if result == 'abgenommen' and clean_points:
            raise ValueError('Bei offenen Punkten bitte „Abgenommen mit Restpunkten“ wählen.')
        _close_tasks(conn, pid, 'abnahme', result)
        kind = 'nachbesserung' if result == 'nachbesserung' else 'restpunkt'
        for label, due in clean_points:
            tid = _task(conn, row, f"{KINDS[kind]}: {label}", due, kind)
            conn.execute('INSERT INTO handover_items(proposal_id, kind, label, due_date, task_id, round) VALUES (?,?,?,?,?,?)',
                         (pid, kind, label, due, tid, h['round']))
        if result == 'nachbesserung':
            conn.execute("""UPDATE handovers SET status='nachbesserung', round=round+1, result=?, accepted_note=? WHERE proposal_id=?""", (result, note, pid))
            notice = f'{len(clean_points)} Nachbesserung(en) als Aufgaben angelegt. Danach erneut übergeben.'
        else:
            conn.execute("""UPDATE handovers SET status=?, result=?, accepted_at=?, accepted_channel=?, accepted_person=?, accepted_note=?
                            WHERE proposal_id=?""", ('vorbehalt' if clean_points else 'abgenommen', result, when, channel, person, note, pid))
            notice = 'Abnahme dokumentiert.' + (f' {len(clean_points)} Restpunkt(e) als Aufgaben angelegt.' if clean_points else '')
        who = ', '.join(x for x in (CHANNELS[channel], f'von {person}' if person else '') if x)
        _log(conn, row, f"{RESULTS[result]} am {when} ({who})" + (f": {'; '.join(lbl for lbl, _ in clean_points)}" if clean_points else '')
             + (f' – {note}' if note else '') + '.')
    conn.commit()
    s = state(conn, pid)
    if action == 'abnahme' and s['final_invoice_due']:
        notice += ' Laut Zahlungsplan ist jetzt die Schlussrechnung fällig – bitte unter „Abrechnen“ erstellen.'
    return {**s, 'notice': notice.strip()}


def protocol(conn, pid):
    """Abnahmeprotokoll für den Kunden: ohne interne Kalkulation, Notizen nur, wo sie den Kunden betreffen (entfallene Punkte)."""
    s = state(conn, pid)
    row = _proposal(conn, pid)
    from .accounting import get_settings
    try:
        me = get_settings(conn).get('company_name') or ''
    except Exception:  # noqa: BLE001 – Protokoll auch ohne Firmendaten
        me = ''
    fmt = lambda iso: dt.date.fromisoformat(iso).strftime('%d.%m.%Y') if iso else '…………'
    sign = {'offen': '☐', 'erledigt': '☑', 'entfaellt': '–'}
    done = s['status'] in ('abgenommen', 'vorbehalt')
    lines = [f"# Abnahmeprotokoll{'' if done else ' (Entwurf zur Abnahme)'}", '',
             f"**Projekt:** {s['project_label'] or 'Auftrag'}  ", f"**Grundlage:** Angebot {s['number']}  ",
             f"**Auftraggeber:** {row['company']}  "]
    if me:
        lines.append(f"**Auftragnehmer:** {me}  ")
    lines.append(f"**Übergabe:** {fmt(s['handed_at']) if s['handed_at'] else 'noch nicht erfolgt'}")
    for kind, title in (('liefer', 'Liefergegenstände'), ('kriterium', 'Abnahmekriterien'), ('nachbesserung', 'Nachbesserungen')):
        its = [i for i in s['items'] if i['kind'] == kind]
        if its:
            lines += ['', f'## {title}'] + [f"- {sign[i['state']]} {i['label']}" + (f" (entfällt: {i['note']})" if i['state'] == 'entfaellt' else '') for i in its]
    rest = [i for i in s['items'] if i['kind'] == 'restpunkt']
    lines += ['', '## Ergebnis']
    if done:
        lines.append(f"{s['result_label']} am {fmt(s['accepted_at'])}" + (f" durch {s['accepted_person']}" if s['accepted_person'] else '') + '.')
        if rest:
            lines += ['', 'Restpunkte, die nach der Abnahme erledigt werden:'] + [f"- {sign[i['state']]} {i['label']} – bis {fmt(i['due_date'])}" for i in rest]
    else:
        lines += ['☐ Abgenommen', '☐ Abgenommen mit folgenden Restpunkten:', '', '……………………………………………………', '', '☐ Nicht abgenommen – Nachbesserung nötig:', '', '……………………………………………………']
    lines += ['', 'Mit der Abnahme bestätigt der Auftraggeber, dass die Liefergegenstände im Wesentlichen vertragsgemäß erbracht sind. '
              'Restpunkte werden innerhalb der genannten Fristen erledigt.', '',
              'Ort, Datum: ……………………………………', '', 'Auftraggeber: ……………………………………      Auftragnehmer: ……………………………………']
    safe = re.sub(r'[^A-Za-z0-9-]+', '-', s['number']).strip('-')
    return {'filename': f"Abnahmeprotokoll-{safe}{'' if done else '-Entwurf'}.md", 'markdown': '\n'.join(lines) + '\n'}


def summary(conn, pid):
    """Kurzstatus für Auftragskarten (ohne Punkte anzulegen)."""
    h = conn.execute('SELECT status FROM handovers WHERE proposal_id=?', (pid,)).fetchone()
    st = h['status'] if h else 'in_arbeit'
    return {'status': st, 'label': STATUS_LABEL[st]}


def route_handover(h, conn, method, route):
    m = re.fullmatch(r'/api/workspace/proposals/(\d+)/abnahme(/protokoll)?', route)
    if not m:
        return False
    pid = int(m.group(1))
    if m.group(2) and method == 'GET':
        h._send(200, protocol(conn, pid))
    elif not m.group(2) and method == 'GET':
        h._send(200, state(conn, pid))
    elif not m.group(2) and method == 'POST':
        h._send(200, act(conn, pid, h._body()))
    else:
        return False
    return True
