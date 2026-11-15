"""Wirkung und Aufwand lernen (2.0.0-dev47, Produktreview M34).

Fasst zusammen, was deine eigenen Daten zeigen – mit Stichprobe und Grenzen:
- **Aufwand nach Projektart:** aus der Nachkalkulation (abgeschlossene Aufträge mit Stunden). Projektart = die Leistung mit den
  meisten kalkulierten Stunden im Angebot.
- **Ergebnisse nach Methode:** aus Erlebnisstudien (nur bestätigte Sitzungen) – Aufgabenerfolg je Methode.
- **Wirkung vorher/nachher:** Paare aus Vorher- und Nachher-Studie derselben Firma; Projektart aus dem Angebot der Nachher-Studie.
- Aussagen erst ab 3 Fällen; darunter nur die Anzahl. Keine Ursache-Wirkung-Behauptung: kleine, selbst gewählte Stichproben.
"""
from __future__ import annotations

import json

MIN_CASES = 3
LIMITS = ['Stichproben sind klein und von dir ausgewählt – sie zeigen Richtungen, keine gesicherten Zusammenhänge.',
          'Vorher/Nachher vergleicht verschiedene Testpersonen; Unterschiede können auch an den Personen liegen.',
          'Aufwand stammt aus deinen eigenen Zeiteinträgen; nicht erfasste Zeit fehlt.']


def _primary_service(internal_json):
    try:
        internal = json.loads(internal_json or '{}')
    except ValueError:
        return ''
    pos = [p for p in internal.get('positions') or [] if not p.get('optional')]
    if not pos:
        return ''
    return max(pos, key=lambda p: float(p.get('hours') or 0)).get('service', '')


def _title(key):
    from .catalog import SERVICES
    return SERVICES.get(key, {}).get('title', key or 'ohne Zuordnung')


def _median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else round((xs[m - 1] + xs[m]) / 2, 2)


def effort_by_type(conn):
    from .postcalc import overview as pc
    groups = {}
    for p in pc(conn)['projects']:
        if not (p['done'] and p['estimated_hours'] and p['actual_hours']):
            continue
        row = conn.execute('SELECT internal_json FROM proposals WHERE id=?', (p['proposal_id'],)).fetchone()
        key = _primary_service(row['internal_json'] if row else '')
        groups.setdefault(key, []).append(p)
    out = []
    for key, ps in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        n = len(ps)
        enough = n >= MIN_CASES
        out.append({'type': key, 'title': _title(key), 'n': n, 'enough': enough,
                    'avg_variance_pct': round(sum(p['variance_pct'] for p in ps) / n) if enough else None,
                    'median_hourly': _median([p['actual_hourly'] for p in ps if p['actual_hourly'] is not None]) if enough else None,
                    'below_minimum': sum(1 for p in ps if p['below_minimum']) if enough else None})
    return out


def results_by_method(conn):
    from .studies import analysis
    groups = {}
    for s in conn.execute('SELECT id, method FROM studies'):
        a = analysis(conn, s['id'])
        if a['overall_success_pct'] is None:
            continue
        groups.setdefault(s['method'], []).append(a)
    out = []
    for method, items in sorted(groups.items()):
        n = len(items)
        out.append({'method': method, 'studies': n, 'sessions': sum(a['sample']['sessions'] for a in items), 'enough': n >= MIN_CASES,
                    'avg_success_pct': round(sum(a['overall_success_pct'] for a in items) / n) if n >= MIN_CASES else None})
    return out


def before_after(conn):
    from .studies import analysis
    pairs = []
    for after in conn.execute("SELECT * FROM studies WHERE phase='nachher'"):
        before = conn.execute("SELECT id FROM studies WHERE lead_id=? AND phase='vorher' AND id<? ORDER BY id DESC LIMIT 1",
                              (after['lead_id'], after['id'])).fetchone()
        if not before:
            continue
        a, b = analysis(conn, after['id']), analysis(conn, before['id'])
        if a['overall_success_pct'] is None or b['overall_success_pct'] is None:
            continue
        row = conn.execute('SELECT internal_json FROM proposals WHERE id=?', (after['proposal_id'],)).fetchone() if after['proposal_id'] else None
        pairs.append({'type': _primary_service(row['internal_json']) if row else '', 'delta': a['overall_success_pct'] - b['overall_success_pct'],
                      'sessions': (b['sample']['sessions'], a['sample']['sessions'])})
    groups = {}
    for p in pairs:
        groups.setdefault(p['type'], []).append(p)
    return [{'type': k, 'title': _title(k), 'pairs': len(v), 'enough': len(v) >= MIN_CASES,
             'avg_delta_points': round(sum(p['delta'] for p in v) / len(v)) if len(v) >= MIN_CASES else None}
            for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))]


def overview(conn):
    return {'effort': effort_by_type(conn), 'methods': results_by_method(conn), 'before_after': before_after(conn),
            'min_cases': MIN_CASES, 'limits': LIMITS}


def route_learning(h, conn, method, route):
    if route == '/api/lernen' and method == 'GET':
        h._send(200, overview(conn))
        return True
    return False
