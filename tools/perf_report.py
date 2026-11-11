"""Leistungsbericht (Masterplan 2.0, Sprint 6): „messbare Qualitätsverbesserung“ statt Behauptung.

python tools/perf_report.py [--out docs/bench/v1.19-performance.json] [--install-report bericht.json ...]

1. Website-Abruf im Testgelände (33 fiktive Websites, tools/bench_fetch.py) – Vergleich mit v1.14 und v1.16.
2. Anwendung mit großem Bestand (5.000 Leads, 2.000 Treffer): Start/Migration, Antwortzeiten der Hauptansichten über HTTP
   (P50/P95), Dubletten-Abgleich je Treffer, Sicherung und Wiederherstellung.
Alles lokal und fiktiv, keine Netzabfragen.
"""
from __future__ import annotations

import contextlib
import argparse
import json
import platform
import random
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]

from sales_tool import __version__  # noqa: E402


def ms(t0):
    return round((time.perf_counter() - t0) * 1000, 1)


def pct(values, p):
    v = sorted(values)
    return round(v[min(len(v) - 1, int(round(p / 100 * (len(v) - 1))))], 1)


def fetch_bench(out_dir):
    target = Path(out_dir) / f'v{__version__.rsplit(".", 1)[0]}-fetch.json'
    subprocess.run([sys.executable, str(ROOT / 'tools' / 'bench_fetch.py'), '--label', f'v{__version__}', '--fetcher', 'http',
                    '--out', str(target)], cwd=ROOT, check=True, capture_output=True)
    cur = json.loads(target.read_text(encoding='utf-8'))
    old = {k: json.loads((ROOT / 'docs' / 'bench' / f).read_text(encoding='utf-8')) for k, f in
           (('v1.14', 'baseline_v1.14.json'), ('v1.16', 'v1.16.json'))}
    keys = ('expected_behaviour', 'field_accuracy', 'p50_ms', 'p95_ms', 'requests', 'robots_requests', 'unvalidated_connects', 'evidence_total', 'evidence_missing')
    return {name: {k: d['modes']['imprint']['summary'].get(k) for k in keys} for name, d in (*old.items(), (f'v{__version__}', cur))}


def seed(db, leads=5000, candidates=2000):
    from sales_tool import sweep as sw
    from sales_tool.model import connect, init_db
    rnd = random.Random(7)
    words = ['Nord', 'Süd', 'Kabel', 'Werk', 'Licht', 'Stahl', 'Holz', 'Bau', 'Daten', 'Technik', 'Müller', 'Präzision', 'Glas', 'Druck']
    cities = [('Stuttgart', '70173'), ('Ulm', '89073'), ('Esslingen', '73728'), ('Ludwigsburg', '71634'), ('Böblingen', '71032')]
    with connect(db) as c:
        init_db(c)
        for i in range(leads):
            city, zip_ = cities[i % len(cities)]
            c.execute("""INSERT INTO leads(company, website, city, zip, stage, contact_route, next_step, next_date) VALUES (?,?,?,?,?,?,?,?)""",
                      (f'{rnd.choice(words)}{rnd.choice(words).lower()} {i} GmbH', f'https://firma{i}.example', city, zip_,
                       rnd.choice(['recherche', 'qualifiziert', 'kontakt', 'antwort', 'termin', 'angebot']), 'inbound',
                       'Anrufen' if i % 3 else '', '2026-12-01' if i % 3 else ''))
            if i % 10 == 0:
                c.execute("INSERT INTO activities(lead_id, activity_type, detail) VALUES (?, 'notiz', 'x')", (i + 1,))
                c.execute("INSERT INTO tasks(lead_id, title, due_date) VALUES (?, 'Nachfassen', '2026-11-20')", (i + 1,))
        c.commit()
        sid = c.execute("INSERT INTO sweeps(label, params_json, status) VALUES ('perf', '{}', 'fertig')").lastrowid
        run = sw._run_record(c, 'osm', sid, {})
        items = []
        for i in range(candidates):
            city, zip_ = cities[i % len(cities)]
            items.append({'name': f'{rnd.choice(words)}{rnd.choice(words).lower()} Kandidat {i % 1500} GmbH', 'zip': zip_, 'city': city})
        ctx = {'industries': [], 'keywords': [], 'org_kinds': sw.ORG_KINDS_DEFAULT, 'operative': False}
        t0 = time.perf_counter()
        counts = sw.store_items(c, sid, run, 'osm', items, ctx)
        per_item = round((time.perf_counter() - t0) * 1000 / candidates, 2)
        return sid, counts, per_item


def app_bench():
    from sales_tool.accounting_api import create_backup
    from sales_tool.backup_restore import restore
    from sales_tool.server import make_handler, prepare_database
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp) / 'neu.sqlite3'
        t0 = time.perf_counter()
        prepare_database(fresh)
        out['start_fresh_db_ms'] = ms(t0)
        db = Path(tmp) / 'gross.sqlite3'
        sid, counts, per_item = seed(db)
        out['dedupe_ms_per_candidate'] = per_item
        out['dedupe_result'] = {k: counts.get(k, 0) for k in ('new', 'merged', 'possible')}
        import sqlite3
        with contextlib.closing(sqlite3.connect(db)) as c, c:
            c.execute('PRAGMA user_version = 22')
        t0 = time.perf_counter()
        prepare_database(db)  # Migration 22 → aktuell inkl. Sicherung und Dubletten-Bereinigung
        out['migrate_5000_leads_ms'] = ms(t0)
        out['db_mb'] = round(db.stat().st_size / 1e6, 1)
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]
        lat = {}
        try:
            for name, path in (('Leads (5.000)', '/api/leads'), ('Heute', '/api/today'), ('Sichtung (50 je Seite)', f'/api/sweep-candidates?status=neu&limit=50'),
                               ('Firmenakte', '/api/leads/1/file'), ('Tagesabschluss', '/api/today/close'), ('Pipeline-Statistik', '/api/stats')):
                times = []
                for _ in range(15):
                    c = HTTPConnection('127.0.0.1', port, timeout=30)
                    t0 = time.perf_counter()
                    c.request('GET', path)
                    r = c.getresponse()
                    r.read()
                    times.append((time.perf_counter() - t0) * 1000)
                    c.close()
                    assert r.status == 200, (path, r.status)
                lat[name] = {'p50_ms': pct(times, 50), 'p95_ms': pct(times, 95)}
        finally:
            server.shutdown()
            server.server_close()
        out['latency'] = lat
        t0 = time.perf_counter()
        bk = create_backup(db)['path']
        out['backup_ms'] = ms(t0)
        t0 = time.perf_counter()
        r = restore(db, bk, confirm=True)
        out['restore_ms'] = ms(t0)
        out['restore_leads'] = r['after']['leads']
    try:
        import resource
        out['peak_rss_mb'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except ImportError:
        pass
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(ROOT / 'docs' / 'bench' / f'v{__version__.rsplit(".", 1)[0]}-performance.json'))
    ap.add_argument('--install-report', action='append', default=[])
    a = ap.parse_args(argv)
    report = {'version': __version__, 'python': platform.python_version(), 'system': f'{platform.system()} {platform.machine()}',
              'fetch': fetch_bench(Path(a.out).parent), 'app': app_bench()}
    cat = json.loads((ROOT / 'docs' / 'bench' / 'v1.17-catalog.json').read_text(encoding='utf-8'))
    report['catalog_v1.17'] = {r['engine']: {'import_s': r['import_s'], 'peak_rss_mb': r['peak_rss_mb']} for r in cat['runs']}
    if a.install_report:
        report['install'] = [json.loads(Path(p).read_text(encoding='utf-8')) for p in a.install_report]
    Path(a.out).write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
