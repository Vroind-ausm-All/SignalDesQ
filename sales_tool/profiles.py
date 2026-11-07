"""Suchprofile mit sichtbarem Budget (Masterplan 2.0, Sprint 5 – SignalDesk v1.18).

Abnahmeablauf des Plans beginnt mit „Profil auswählen → Session starten“. Ein Profil speichert Suchgebiet, Branchen,
Quellen und Filter der Sammelsuche plus das Budget je Lauf (höchstens neue Firmen, Website-Suchen, Minuten). KI-Analysen
starten nie automatisch; externe Kosten fallen nicht an, weil nur kostenlose offene Quellen abgefragt werden.
"""
from __future__ import annotations

import json
import re

from . import sweep as sw

MAX_PROFILES = 50


def init_profiles(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS search_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, params_json TEXT NOT NULL, budget_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')), last_used_at TEXT NOT NULL DEFAULT '', runs INTEGER NOT NULL DEFAULT 0)''')


def _view(r):
    p = json.loads(r['params_json'])
    b = json.loads(r['budget_json'])
    return {'id': r['id'], 'name': r['name'], 'params': p, 'budget': b, 'created_at': r['created_at'], 'last_used_at': r['last_used_at'],
            'runs': r['runs'], 'summary': f"{p['place']} · {p['radius_km']} km · {len(p['sources'])} Quelle(n)"
                                         + (f" · {len(p['industries'])} Branche(n)" if p['industries'] else '')
                                         + f" · Budget {b['max_companies']} Firmen / {b['max_websites']} Websites / {b['max_minutes']} Min.",
            'costs': 'keine externen Kosten (nur kostenlose offene Quellen) · KI-Analysen nur auf Klick'}


def list_profiles(conn):
    return [_view(r) for r in conn.execute('SELECT * FROM search_profiles ORDER BY last_used_at DESC, name')]


def _parse(data):
    if not isinstance(data, dict) or set(data) - {'name', 'params', 'budget'}:
        raise ValueError('Erwartet: {name, params, budget}.')
    name = re.sub(r'\s+', ' ', str(data.get('name') or '')).strip()[:80]
    if len(name) < 2:
        raise ValueError('Profilname angeben (z. B. „Stuttgart Maschinenbau 30 km“).')
    params = dict(data.get('params') or {})
    params.pop('budget', None)
    params.pop('profile_id', None)
    p = sw.validate_params(params)
    p.pop('budget', None)
    p.pop('profile_id', None)
    p['keywords'] = ', '.join(p['keywords']) if isinstance(p['keywords'], list) else p['keywords']
    return name, p, sw.validate_budget(data.get('budget'))


def save_profile(conn, data, profile_id=None):
    name, p, b = _parse(data)
    if profile_id is None:
        if conn.execute('SELECT COUNT(*) FROM search_profiles').fetchone()[0] >= MAX_PROFILES:
            raise ValueError(f'Höchstens {MAX_PROFILES} Suchprofile.')
        if conn.execute('SELECT 1 FROM search_profiles WHERE name=?', (name,)).fetchone():
            raise ValueError('Ein Profil mit diesem Namen gibt es schon.')
        pid = conn.execute('INSERT INTO search_profiles(name, params_json, budget_json) VALUES (?,?,?)',
                           (name, json.dumps(p, ensure_ascii=False), json.dumps(b))).lastrowid
    else:
        if not conn.execute('SELECT 1 FROM search_profiles WHERE id=?', (profile_id,)).fetchone():
            raise LookupError('Profil nicht gefunden.')
        if conn.execute('SELECT 1 FROM search_profiles WHERE name=? AND id<>?', (name, profile_id)).fetchone():
            raise ValueError('Ein Profil mit diesem Namen gibt es schon.')
        conn.execute('UPDATE search_profiles SET name=?, params_json=?, budget_json=? WHERE id=?',
                     (name, json.dumps(p, ensure_ascii=False), json.dumps(b), profile_id))
        pid = profile_id
    conn.commit()
    return _view(conn.execute('SELECT * FROM search_profiles WHERE id=?', (pid,)).fetchone())


def delete_profile(conn, profile_id):
    if not conn.execute('DELETE FROM search_profiles WHERE id=?', (profile_id,)).rowcount:
        raise LookupError('Profil nicht gefunden.')
    conn.commit()
    return {'deleted': True}


def start_profile(conn, profile_id, db_path, start=True):
    r = conn.execute('SELECT * FROM search_profiles WHERE id=?', (profile_id,)).fetchone()
    if not r:
        raise LookupError('Profil nicht gefunden.')
    v = _view(r)
    res = sw.start_sweep(conn, {**v['params'], 'budget': v['budget'], 'profile_id': profile_id}, db_path, start=start)
    conn.execute("UPDATE search_profiles SET last_used_at=datetime('now'), runs=runs+1 WHERE id=?", (profile_id,))
    conn.commit()
    return {**res, 'profile': v['name']}


def route_profiles(h, conn, method, route, query, db_path):
    if route == '/api/search-profiles':
        if method == 'GET':
            h._send(200, {'profiles': list_profiles(conn), 'budget_default': sw.BUDGET_DEFAULT,
                          'budget_limits': {k: list(v) for k, v in sw.BUDGET_LIMITS.items()}})
            return True
        if method == 'POST':
            h._send(201, save_profile(conn, h._body()))
            return True
    m = re.fullmatch(r'/api/search-profiles/(\d+)(/start)?', route)
    if m:
        pid = int(m.group(1))
        if m.group(2) and method == 'POST':
            h._send(202, start_profile(conn, pid, db_path))
            return True
        if not m.group(2) and method == 'PUT':
            h._send(200, save_profile(conn, h._body(), pid))
            return True
        if not m.group(2) and method == 'DELETE':
            h._send(200, delete_profile(conn, pid))
            return True
    return False
