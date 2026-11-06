"""Messlauf für den Website-Abruf (Sprint 0/1): Impressums-Recherche und Light-Crawl gegen das lokale Testgelände.

Aufruf:  python tools/bench_fetch.py --label baseline --out docs/bench/baseline.json
         python tools/bench_fetch.py --label v1.15 --fetcher http   (nach Sprint 1)
Keine echten Netzwerkzugriffe: tests/webfixtures.py simuliert DNS und lenkt Verbindungen auf einen lokalen Server.
Höflichkeitspausen (imprint.SLEEP) sind abgeschaltet, gemessen wird der Abruf selbst.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]

from webfixtures import FixtureServer, add_rebind_site, simulated_network  # noqa: E402

from sales_tool import imprint  # noqa: E402
from sales_tool import website_analyzer as wa  # noqa: E402

FIELDS = ('legal_name', 'zip', 'city', 'register_number', 'vat_id', 'business_phone', 'business_email')


def norm(v):
    return re.sub(r'\s+', ' ', str(v or '')).strip().casefold()


def classify(exc):
    m = str(exc)
    for key, rx in (('robots', r'robots'), ('ssrf', r'IP-Adresse|privat|öffentlich|Interne|lokal|gesperrt|nicht öffentliche'),
                    ('redirects', r'Weiterleitung'), ('size', r'zu groß|Größe|size'), ('timeout', r'timed out|Zeitüberschreitung|timeout'),
                    ('content_type', r'Content-Type|Keine HTML|Inhaltstyp'), ('http', r'HTTP \d{3}'), ('no_text', r'Kein sichtbarer|keine nutzbaren')):
        if re.search(rx, m, re.I):
            return key
    return 'other'


def run_site(host, spec, server, mode):
    t0 = time.perf_counter()
    n0 = len(server.log)
    try:
        from sales_tool.research import policy
        policy.ROBOTS.clear()  # jede Website kalt messen (Zwischenspeicher wirkt nur innerhalb einer Recherche)
    except ImportError:
        pass
    with simulated_network(server) as net:
        outcome, fields, pages, err, engines = 'ok', {}, 0, '', []
        try:
            if mode == 'imprint':
                res = imprint.research_domain(f'http://{host}/', include_persons=False)
                fields = {k: (v or {}).get('value') for k, v in (res.get('fields') or {}).items()}
                outcome = 'ok' if res.get('status') == 'ok' else 'no_imprint'
            else:
                res = wa.light_crawl(f'http://{host}/', 'website')
                pages = len(res.get('pages', []))
                engines = sorted({p.get('parser', '?') for p in res.get('pages', [])})
        except Exception as exc:  # noqa: BLE001 – Messung, nicht Produktcode
            outcome, err = 'error', f'{exc.__class__.__name__}: {exc}'[:300]
    ms = (time.perf_counter() - t0) * 1000
    hits = server.log[n0:]
    exp = spec.get('expect') or {}
    checks = {k: exp[k] for k in FIELDS if k in exp}
    correct = {k: norm(fields.get(k)) == norm(v) for k, v in checks.items()} if mode == 'imprint' else {}
    applies = ('blocked', 'error', 'no_imprint') if mode == 'imprint' else ('blocked', 'error')
    if any(k in exp for k in applies):
        wanted = exp.get('blocked') or exp.get('error') or 'no_imprint'
        behaved = outcome != 'ok' and not any(fields.values()) and not net.unvalidated
        if wanted in ('ssrf', 'rebind'):
            behaved = behaved and not net.unvalidated
    elif mode == 'imprint':
        behaved = outcome == 'ok' and all(correct.values())
    else:
        behaved = outcome == 'ok' and pages >= 1
    return {'host': host, 'mode': mode, 'outcome': outcome, 'error_class': classify(err) if err else '', 'error': err,
            'ms': round(ms, 1), 'requests': len(hits), 'robots_requests': sum(1 for h in hits if h[1] == '/robots.txt'),
            'unvalidated_connects': len(net.unvalidated), 'dns_lookups': len(net.resolutions), 'pages': pages,
            'fields_expected': len(checks), 'fields_correct': sum(correct.values()), 'wrong': {k: fields.get(k) for k, ok in correct.items() if not ok},
            'expected_behaviour': bool(behaved), 'expect': exp, 'parser_used': engines}


def summarize(rows):
    ms = sorted(r['ms'] for r in rows)
    pct = lambda p: ms[min(len(ms) - 1, int(round(p / 100 * (len(ms) - 1))))] if ms else 0
    fe = sum(r['fields_expected'] for r in rows)
    return {'sites': len(rows), 'expected_behaviour': sum(r['expected_behaviour'] for r in rows),
            'p50_ms': pct(50), 'p95_ms': pct(95), 'total_ms': round(sum(ms)), 'requests': sum(r['requests'] for r in rows),
            'robots_requests': sum(r['robots_requests'] for r in rows), 'unvalidated_connects': sum(r['unvalidated_connects'] for r in rows),
            'dns_lookups': sum(r['dns_lookups'] for r in rows), 'fields_expected': fe, 'fields_correct': sum(r['fields_correct'] for r in rows),
            'field_accuracy': round(100 * sum(r['fields_correct'] for r in rows) / fe, 1) if fe else None,
            'parser_used': sorted({e for r in rows for e in r.get('parser_used', [])})}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--label', default='lauf')
    ap.add_argument('--out', default='')
    ap.add_argument('--only', default='', help='Kommagetrennte Hosts')
    ap.add_argument('--skip-slow', action='store_true', help='langsam.example auslassen')
    ap.add_argument('--fetcher', default='', help='http | legacy (ab v1.15)')
    ap.add_argument('--parser', default='', help='auto | scrapling | stdlib (ab v1.15)')
    args = ap.parse_args()
    imprint.SLEEP = lambda s: None
    try:
        from sales_tool.research import settings, policy
        settings.set_runtime({k: v for k, v in (('fetcher', args.fetcher), ('parser', args.parser)) if v})
        policy.ROBOTS.clear()
    except ImportError:
        pass  # Stand vor v1.15
    result = {'label': args.label, 'fetcher': args.fetcher or 'standard', 'parser': args.parser or 'standard', 'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'python': sys.version.split()[0], 'modes': {}}
    tracemalloc.start()
    with FixtureServer() as server:
        add_rebind_site(server)
        sites = server.manifest['sites']
        hosts = [h for h in sites if (not args.only or h in args.only.split(',')) and not (args.skip_slow and h == 'langsam.example')]
        hosts = [h for h in hosts if h != 'www.kanzlei-berg.example']  # nur über die Weiterleitung erreichbar testen
        t0 = time.perf_counter()
        for mode in ('imprint', 'crawl'):
            rows = [run_site(h, sites[h], server, mode) for h in hosts]
            result['modes'][mode] = {'summary': summarize(rows), 'rows': rows}
        result['wall_s'] = round(time.perf_counter() - t0, 1)
    result['peak_mem_mb'] = round(tracemalloc.get_traced_memory()[1] / 1e6, 1)
    for mode, data in result['modes'].items():
        s = data['summary']
        print(f"[{args.label}] {mode:8} erwartetes Verhalten {s['expected_behaviour']}/{s['sites']} · Felder {s['fields_correct']}/{s['fields_expected']}"
              f" ({s['field_accuracy']} %) · P50 {s['p50_ms']} ms · P95 {s['p95_ms']} ms · Anfragen {s['requests']} (robots {s['robots_requests']})"
              f" · ungeprüfte Verbindungen {s['unvalidated_connects']}" + (f" · Parser {','.join(s['parser_used'])}" if s['parser_used'] else ''))
        for r in data['rows']:
            if not r['expected_behaviour']:
                print(f"    ✗ {r['host']:30} {r['outcome']:10} {r['error_class']:12} {r['error'][:110]} {r['wrong'] or ''}")
    print(f"Gesamtzeit {result['wall_s']} s · Spitzenspeicher {result['peak_mem_mb']} MB")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
