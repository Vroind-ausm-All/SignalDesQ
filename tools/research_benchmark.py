"""Recherche-Benchmark (SDQ-006) – Referenzliste prüfen, Lauf exportieren, auswerten.

python tools/research_benchmark.py validate REFERENZ.json
python tools/research_benchmark.py import-table referenzliste.xlsx|.csv --out REFERENZ.json [--suche q1="Steuerberater 70173–70199"] [--vollstaendig q1]
python tools/research_benchmark.py export-run --db signaldesk.sqlite3 --query q1 [--since 2026-11-20] --out lauf.json
python tools/research_benchmark.py evaluate REFERENZ.json LAUF.json [--out ergebnis.json] [--md ergebnis.md]

Format und Messgrößen: docs/RECHERCHE_BENCHMARK.md. Vorlage für eine Referenzliste: docs/bench/research/vorlage-referenz.json.
Das Werkzeug ruft nichts im Netz ab und erzeugt keine Referenzdaten – die Referenzliste prüfen Menschen.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sales_tool import __version__  # noqa: E402
from sales_tool.research import benchmark as bm  # noqa: E402


def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _write(path, text):
    Path(path).write_text(text, encoding='utf-8')
    print('geschrieben:', path)


def _table_rows(path):
    """Zeilen der Tabelle: erstes Blatt einer xlsx-Datei (braucht openpyxl) oder CSV mit ; oder ,."""
    path = Path(path)
    if path.suffix.lower() == '.xlsx':
        try:
            import openpyxl
        except ImportError:
            raise SystemExit('Für .xlsx wird openpyxl gebraucht (pip install openpyxl) – oder die Tabelle als CSV speichern.')
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    import csv
    text = path.read_text(encoding='utf-8-sig')
    lines = text.splitlines()
    delimiter = ';' if lines and ';' in lines[0] else ','  # Excel speichert in Deutschland mit Semikolon
    return list(csv.reader(lines, delimiter=delimiter))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    v = sub.add_parser('validate', help='Referenzliste prüfen')
    v.add_argument('reference')
    t = sub.add_parser('import-table', help='ausgefüllte Tabellenvorlage (xlsx oder csv) in eine Referenzliste umwandeln')
    t.add_argument('table')
    t.add_argument('--out', required=True)
    t.add_argument('--suche', action='append', default=[], metavar='ID=BESCHREIBUNG')
    t.add_argument('--vollstaendig', action='append', default=[], metavar='ID', help='Suche ist abschließend erfasst')
    t.add_argument('--methode', action='append', default=[], metavar='ID=TEXT', help='Quellen, Stichtag, Prüfende')
    x = sub.add_parser('export-run', help='Firmen einer SignalDesk-Datenbank als Lauf-Datei')
    x.add_argument('--db', required=True)
    x.add_argument('--query', required=True, help='id der Suche in der Referenzliste')
    x.add_argument('--since', default='', help='nur Firmen, die ab diesem Datum angelegt wurden (JJJJ-MM-TT)')
    x.add_argument('--out', required=True)
    e = sub.add_parser('evaluate', help='Lauf gegen Referenzliste auswerten')
    e.add_argument('reference')
    e.add_argument('run')
    e.add_argument('--out', help='Ergebnis als JSON')
    e.add_argument('--md', help='Ergebnis als Markdown')
    args = ap.parse_args(argv)

    if args.cmd == 'validate':
        errs = bm.validate_reference(_load(args.reference))
        for err in errs:
            print('FEHLER:', err)
        print('Referenzliste in Ordnung.' if not errs else f'{len(errs)} Fehler.')
        return 1 if errs else 0
    if args.cmd == 'import-table':
        queries = {}
        for item in args.suche:
            qid, _, text = item.partition('=')
            queries.setdefault(qid.strip(), {})['description'] = text.strip()
        for item in args.methode:
            qid, _, text = item.partition('=')
            queries.setdefault(qid.strip(), {})['method'] = text.strip()
        for qid in args.vollstaendig:
            queries.setdefault(qid.strip(), {})['complete'] = True
        try:
            ref = bm.reference_from_table(_table_rows(args.table), queries, name=Path(args.table).stem)
        except ValueError as exc:
            print('FEHLER:', exc)
            return 1
        errs = bm.validate_reference(ref)
        if not errs:  # eine fehlerhafte Liste wird nicht geschrieben (sonst würde sie später versehentlich ausgewertet)
            _write(args.out, json.dumps(ref, ensure_ascii=False, indent=1))
        for err in errs:
            print('FEHLER:', err)
        print(sum(len(q['companies']) for q in ref['queries']), 'Firmen in', len(ref['queries']), 'Suche(n).',
              'Referenzliste in Ordnung.' if not errs else f'{len(errs)} Fehler – Tabelle korrigieren und erneut umwandeln.')
        return 1 if errs else 0
    if args.cmd == 'export-run':
        run = bm.export_run(args.db, args.query, system=f'SignalDesk {__version__}', since=args.since)
        _write(args.out, json.dumps(run, ensure_ascii=False, indent=1))
        print(len(run['queries'][0]['candidates']), 'Firmen exportiert (nur Firmendaten, keine Personen).')
        return 0
    try:
        res = bm.evaluate(_load(args.reference), _load(args.run))
    except ValueError as exc:
        print('FEHLER:', exc)
        return 1
    md = bm.report_markdown(res)
    if args.out:
        _write(args.out, json.dumps(res, ensure_ascii=False, indent=1))
    if args.md:
        _write(args.md, md)
    if not args.out and not args.md:
        print(md)
    return 0


if __name__ == '__main__':
    sys.exit(main())
