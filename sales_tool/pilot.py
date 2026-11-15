"""Recherchepilot: Stichprobe von Hand prüfen (2.0.0-dev45, Produktreview M21).

Gemessen wird, was die Firmensuche wirklich leistet – an deinen eigenen Treffern, geprüft von dir:
- **Zufallsstichprobe** (50–100) aus den gefundenen Firmen, wahlweise nur eine Quelle oder nur eine Suche.
- Beim Ziehen wird festgehalten, was SignalDesk zu diesem Zeitpunkt sagte (Website, Status, Branche) – spätere Änderungen
  verfälschen die Messung nicht.
- Du trägst je Firma ein: Zielbetrieb ja/nein, Website richtig/falsch/fehlt, echte Website vorhanden, Branche richtig.
  „Unklar“ ist immer erlaubt und zählt in keiner Quote.
- **Kennzahlen** mit Anzahl: Anteil Zielbetriebe, Trefferquote der Websites (richtige unter den angezeigten), Abdeckung
  (gefundene unter denen, die eine Website haben), Branche richtig. Kleine Stichproben werden als solche gekennzeichnet.
- Nur lokal; nichts wird abgerufen. Export als CSV für deine Unterlagen.
"""
from __future__ import annotations

import csv
import io
import json
import random
import re

SIZES = (20, 50, 75, 100)
MARKS = {
    'target': ('ja', 'nein', 'unklar'),          # Zielbetrieb (passt zu deiner Zielgruppe)?
    'website': ('richtig', 'falsch', 'fehlt', 'unklar'),  # angezeigte Website richtig? „fehlt“ = SignalDesk zeigte keine
    'has_site': ('ja', 'nein', 'unklar'),        # hat die Firma tatsächlich eine Website?
    'industry': ('richtig', 'falsch', 'unklar'),
}


def init_pilot(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS pilot_samples (
        id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT NOT NULL, filter_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS pilot_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sample_id INTEGER NOT NULL REFERENCES pilot_samples(id) ON DELETE CASCADE,
        candidate_id INTEGER, snapshot_json TEXT NOT NULL,
        target TEXT NOT NULL DEFAULT '', website TEXT NOT NULL DEFAULT '', has_site TEXT NOT NULL DEFAULT '',
        industry TEXT NOT NULL DEFAULT '', true_url TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
        checked_at TEXT NOT NULL DEFAULT ''
      );
      CREATE INDEX IF NOT EXISTS idx_pilot_items_sample ON pilot_items(sample_id);
    ''')


def sources(conn):
    return [dict(r) for r in conn.execute("SELECT source, COUNT(*) AS n FROM discovery_candidates WHERE dup_of IS NULL GROUP BY source ORDER BY n DESC")]


def draw(conn, data, rng=None):
    if not isinstance(data, dict) or set(data) - {'size', 'source', 'sweep_id', 'label'}:
        raise ValueError('Erwartet: size, source, sweep_id, label.')
    size = data.get('size', 50)
    if size not in SIZES:
        raise ValueError('Stichprobe: 20, 50, 75 oder 100 Firmen.')
    where, args = ['dup_of IS NULL'], []
    if data.get('source'):
        where.append('source=?')
        args.append(str(data['source'])[:40])
    if data.get('sweep_id'):
        where.append('sweep_id=?')
        args.append(int(data['sweep_id']))
    ids = [r[0] for r in conn.execute(f"SELECT id FROM discovery_candidates WHERE {' AND '.join(where)} ORDER BY id", args)]
    if len(ids) < 10:
        raise ValueError(f'Zu wenige Firmen für eine Stichprobe ({len(ids)}). Zuerst eine Suche durchführen.')
    pick = sorted((rng or random.SystemRandom()).sample(ids, min(size, len(ids))))
    label = re.sub(r'\s+', ' ', str(data.get('label') or '')).strip()[:80] or f"Stichprobe {len(pick)} Firmen" + (f" · {data['source']}" if data.get('source') else '')
    sid = conn.execute('INSERT INTO pilot_samples(label, filter_json) VALUES (?,?)',
                       (label, json.dumps({k: data.get(k) for k in ('size', 'source', 'sweep_id') if data.get(k)}, ensure_ascii=False))).lastrowid
    for cid in pick:
        c = conn.execute('SELECT * FROM discovery_candidates WHERE id=?', (cid,)).fetchone()
        snap = {k: c[k] for k in ('name', 'source', 'website', 'zip', 'city', 'industry', 'source_url') if k in c.keys()}
        snap['website_status'] = c['website_status'] if 'website_status' in c.keys() else ''
        snap['industry_key'] = c['industry_key'] if 'industry_key' in c.keys() else ''
        conn.execute('INSERT INTO pilot_items(sample_id, candidate_id, snapshot_json) VALUES (?,?,?)', (sid, cid, json.dumps(snap, ensure_ascii=False)))
    conn.commit()
    return view(conn, sid)


def _item(r):
    d = dict(r)
    d['snapshot'] = json.loads(d.pop('snapshot_json'))
    d['done'] = bool(d['target'] and (d['target'] == 'nein' or (d['website'] and d['has_site'])))
    return d


def mark(conn, item_id, data):
    if not isinstance(data, dict) or set(data) - set(MARKS) - {'true_url', 'note'}:
        raise ValueError('Erwartet: ' + ', '.join([*MARKS, 'true_url', 'note']) + '.')
    row = conn.execute('SELECT * FROM pilot_items WHERE id=?', (item_id,)).fetchone()
    if not row:
        raise LookupError('Eintrag nicht gefunden.')
    sets, args = [], []
    for key, allowed in MARKS.items():
        if key in data:
            if data[key] not in ('', *allowed):
                raise ValueError(f'{key}: ' + ' / '.join(allowed) + '.')
            sets.append(f'{key}=?')
            args.append(data[key])
    for key, limit in (('true_url', 300), ('note', 500)):
        if key in data:
            v = data[key]
            if not isinstance(v, str) or len(v) > limit:
                raise ValueError(f'{key}: höchstens {limit} Zeichen.')
            sets.append(f'{key}=?')
            args.append(v.strip())
    if sets:
        conn.execute(f"UPDATE pilot_items SET {', '.join(sets)}, checked_at=datetime('now') WHERE id=?", (*args, item_id))
        conn.commit()
    return _item(conn.execute('SELECT * FROM pilot_items WHERE id=?', (item_id,)).fetchone())


def _rate(hit, total):
    return {'hit': hit, 'of': total, 'pct': round(100 * hit / total) if total else None}


def metrics(items):
    """Quoten nur aus eindeutig beantworteten Einträgen; „unklar“ und Leeres zählen nicht mit."""
    target_known = [i for i in items if i['target'] in ('ja', 'nein')]
    targets = [i for i in items if i['target'] == 'ja']
    shown = [i for i in targets if i['snapshot'].get('website') and i['website'] in ('richtig', 'falsch')]
    with_site = [i for i in targets if i['has_site'] == 'ja']
    ind = [i for i in targets if i['industry'] in ('richtig', 'falsch')]
    m = {'checked': sum(1 for i in items if i['done']), 'total': len(items),
         'target_share': _rate(len(targets), len(target_known)),
         'website_precision': _rate(sum(1 for i in shown if i['website'] == 'richtig'), len(shown)),
         'website_coverage': _rate(sum(1 for i in with_site if i['website'] == 'richtig'), len(with_site)),
         'has_site_share': _rate(len(with_site), sum(1 for i in targets if i['has_site'] in ('ja', 'nein'))),
         'industry_correct': _rate(sum(1 for i in ind if i['industry'] == 'richtig'), len(ind))}
    small = [k for k, v in m.items() if isinstance(v, dict) and v['of'] and v['of'] < 30]
    m['notice'] = ('Kleine Basis (unter 30) bei: ' + ', '.join(LABELS[k] for k in small) + ' – Quoten nur als grobe Richtung lesen.') if small else ''
    return m


LABELS = {'target_share': 'Anteil Zielbetriebe', 'website_precision': 'Trefferquote Websites', 'website_coverage': 'Abdeckung Websites',
          'has_site_share': 'Anteil mit Website', 'industry_correct': 'Branche richtig'}


def view(conn, sid):
    s = conn.execute('SELECT * FROM pilot_samples WHERE id=?', (sid,)).fetchone()
    if not s:
        raise LookupError('Stichprobe nicht gefunden.')
    items = [_item(r) for r in conn.execute('SELECT * FROM pilot_items WHERE sample_id=? ORDER BY id', (sid,))]
    return {**dict(s), 'filter': json.loads(s['filter_json']), 'items': items, 'metrics': metrics(items), 'labels': LABELS, 'marks': MARKS}


def overview(conn):
    out = []
    for s in conn.execute('SELECT * FROM pilot_samples ORDER BY id DESC LIMIT 20'):
        items = [_item(r) for r in conn.execute('SELECT * FROM pilot_items WHERE sample_id=?', (s['id'],))]
        out.append({'id': s['id'], 'label': s['label'], 'created_at': s['created_at'], 'metrics': metrics(items)})
    return {'samples': out, 'sources': sources(conn), 'sizes': SIZES,
            'notice': 'Zufallsstichprobe aus deinen gefundenen Firmen. Du prüfst von Hand; SignalDesk rechnet die Quoten. Nichts wird abgerufen.'}


def delete(conn, sid):
    if not conn.execute('DELETE FROM pilot_samples WHERE id=?', (sid,)).rowcount:
        raise LookupError('Stichprobe nicht gefunden.')
    conn.commit()
    return {'deleted': True}


def export_csv(conn, sid):
    v = view(conn, sid)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(['Firma', 'Quelle', 'PLZ', 'Ort', 'Website laut SignalDesk', 'Status', 'Branche laut SignalDesk',
                'Zielbetrieb', 'Website', 'Hat Website', 'Branche', 'Echte Website', 'Notiz', 'Geprüft am'])
    for i in v['items']:
        s = i['snapshot']
        w.writerow([s.get('name'), s.get('source'), s.get('zip'), s.get('city'), s.get('website'), s.get('website_status'), s.get('industry'),
                    i['target'], i['website'], i['has_site'], i['industry'], i['true_url'], i['note'], i['checked_at']])
    w.writerow([])
    for k, label in LABELS.items():
        r = v['metrics'][k]
        w.writerow([label, f"{r['hit']} von {r['of']}", f"{r['pct']} %" if r['pct'] is not None else '–'])
    return ('﻿' + buf.getvalue()).encode('utf-8')


def route_pilot(h, conn, method, route):
    if route == '/api/pilot':
        if method == 'GET':
            h._send(200, overview(conn))
            return True
        if method == 'POST':
            h._send(201, draw(conn, h._body()))
            return True
        return False
    m = re.fullmatch(r'/api/pilot/(\d+)(/export\.csv)?', route)
    if m:
        sid = int(m.group(1))
        if m.group(2) and method == 'GET':
            h._send_raw(200, export_csv(conn, sid), 'text/csv', f'SignalDesk-Stichprobe-{sid}.csv')
            return True
        if method == 'GET':
            h._send(200, view(conn, sid))
            return True
        if method == 'DELETE':
            h._send(200, delete(conn, sid))
            return True
        return False
    m = re.fullmatch(r'/api/pilot/eintrag/(\d+)', route)
    if m and method == 'POST':
        h._send(200, mark(conn, int(m.group(1)), h._body()))
        return True
    return False
