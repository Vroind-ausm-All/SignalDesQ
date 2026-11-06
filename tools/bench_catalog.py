"""Messung Sprint 4 (Masterplan 2.0): großer Katalog – SQLite (eingebaut) gegen DuckDB (optional) – und
Namensabgleich RapidFuzz (optional) gegen difflib (eingebaut). Synthetische, fiktive GLEIF-Daten.

python tools/bench_catalog.py [zeilen] [--out docs/bench/v1.17-catalog.json]
Jede Variante läuft in einem eigenen Prozess (Spitzen-RSS je Variante messbar).
"""
import json
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

SEARCHES = [('name', 'Mueller Kabel'), ('zip', '70'), ('city', 'Esslingen am Neckar')]


def _rss_mb():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)


def run_sqlite(src, workdir):
    from sales_tool.research import catalog as cat
    p = Path(workdir) / 'b.katalog.sqlite3'
    t = time.perf_counter()
    res = cat.import_file(p, src, 'golden')
    imp = time.perf_counter() - t
    times = {}
    for kind, q in SEARCHES:
        t = time.perf_counter()
        for _ in range(20):
            r = cat.search(p, **({'q': q} if kind == 'name' else {'zip_prefix': q} if kind == 'zip' else {'city': q}), limit=50)
        times[kind] = round((time.perf_counter() - t) / 20 * 1000, 2)
    t = time.perf_counter()
    res2 = cat.import_file(p, src, 'delta')
    return {'engine': 'sqlite', 'import_s': round(imp, 2), 'reimport_s': round(time.perf_counter() - t, 2), 'rows': res['rows'],
            'stored': res['inserted'], 'unchanged_on_reimport': res2['unchanged'], 'search_ms': times, 'hits_name': r['total'],
            'db_mb': round(p.stat().st_size / 1e6, 1), 'peak_rss_mb': _rss_mb()}


def run_duckdb(src, workdir):
    import duckdb
    p = Path(workdir) / 'b.duckdb'
    con = duckdb.connect(str(p))
    t = time.perf_counter()
    con.execute("""CREATE TABLE entities AS SELECT "LEI" AS lei, "Entity.LegalName" AS name, "Entity.LegalAddress.PostalCode" AS zip,
                   "Entity.LegalAddress.City" AS city, "Entity.LegalAddress.Country" AS country, "Registration.LastUpdateDate" AS last_update
                   FROM read_csv(?, header=true, all_varchar=true) WHERE "Entity.LegalAddress.Country"='DE'""", [str(src)])
    con.execute('CREATE UNIQUE INDEX ent_lei ON entities(lei)')
    imp = time.perf_counter() - t
    times = {}
    for kind, q in SEARCHES:
        sql, arg = {'name': ("SELECT * FROM entities WHERE strip_accents(lower(name)) LIKE '%muller%' AND lower(name) LIKE '%kabel%' LIMIT 50", []),
                    'zip': ("SELECT * FROM entities WHERE zip LIKE ? LIMIT 50", [q + '%']),
                    'city': ("SELECT * FROM entities WHERE lower(city)=lower(?) LIMIT 50", [q])}[kind]
        t = time.perf_counter()
        for _ in range(20):
            con.execute(sql, arg).fetchall()
        times[kind] = round((time.perf_counter() - t) / 20 * 1000, 2)
    # Delta als Upsert (gleiche Datei, keine Änderungen)
    t = time.perf_counter()
    con.execute("""INSERT INTO entities SELECT "LEI", "Entity.LegalName", "Entity.LegalAddress.PostalCode", "Entity.LegalAddress.City",
                   "Entity.LegalAddress.Country", "Registration.LastUpdateDate" FROM read_csv(?, header=true, all_varchar=true)
                   WHERE "Entity.LegalAddress.Country"='DE' ON CONFLICT (lei) DO UPDATE SET name=excluded.name, last_update=excluded.last_update""",
                [str(src)])
    reimp = time.perf_counter() - t
    n = con.execute('SELECT COUNT(*) FROM entities').fetchone()[0]
    con.close()
    return {'engine': 'duckdb ' + duckdb.__version__, 'import_s': round(imp, 2), 'reimport_s': round(reimp, 2), 'stored': n, 'search_ms': times,
            'db_mb': round(p.stat().st_size / 1e6, 1), 'peak_rss_mb': _rss_mb(),
            'note': 'Suche ohne Umschrift (Müller ≠ Mueller) und ohne Volltextindex; Upsert über einen eindeutigen Index'}


def run_match(n):
    from sales_tool.research import identity as ident
    import make_gleif_sample as gs
    items = [{'name': r[1], 'zip': r[5], 'city': r[4]} for r in gs.rows(n)]
    probes = [{'name': it['name'].replace('ü', 'ue').replace('GmbH', 'Gesellschaft mit beschränkter Haftung'), 'zip': it['zip'], 'city': it['city']}
              for it in items[::50]]
    t = time.perf_counter()
    idx = ident.Index()
    for i, it in enumerate(items):
        idx.add(i, it)
    build = time.perf_counter() - t
    t = time.perf_counter()
    hits = sum(1 for i, pr in enumerate(probes) if (b := idx.best(pr)) and b[0] == 'same' and b[1] == i * 50)
    per = (time.perf_counter() - t) / len(probes)
    return {'engine': ident.engine(), 'firms': n, 'build_s': round(build, 2), 'match_ms': round(per * 1000, 2), 'found_same': f'{hits}/{len(probes)}',
            'peak_rss_mb': _rss_mb()}


def child(mode, arg, workdir):
    out = {'sqlite': run_sqlite, 'duckdb': run_duckdb}[mode](arg, workdir) if mode != 'match' else run_match(int(arg))
    print(json.dumps(out))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--child':
        child(sys.argv[2], sys.argv[3], sys.argv[4])
        return
    import make_gleif_sample as gs
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 300_000
    out_path = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else ''
    py = sys.executable
    with tempfile.TemporaryDirectory() as d:
        src = gs.write(Path(d) / 'golden.csv', n)
        result = {'rows': n, 'file_mb': round(src.stat().st_size / 1e6, 1), 'python': sys.version.split()[0], 'runs': []}
        for mode in ('sqlite', 'duckdb'):
            sub = Path(d) / mode
            sub.mkdir()
            r = subprocess.run([py, '-I', __file__, '--child', mode, str(src), str(sub)], capture_output=True, text=True, cwd=str(ROOT))
            result['runs'].append(json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else {'engine': mode, 'error': r.stderr.strip()[-300:]})
        r = subprocess.run([py, '-I', __file__, '--child', 'match', '20000', d], capture_output=True, text=True, cwd=str(ROOT))
        result['match'] = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else {'error': r.stderr.strip()[-300:]}
    print(json.dumps(result, indent=1, ensure_ascii=False))
    if out_path:
        Path(out_path).write_text(json.dumps(result, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
