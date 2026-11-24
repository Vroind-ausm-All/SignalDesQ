"""Inventar aller SQL-Zugriffe (SDQ-010): welches Modul liest und schreibt welche Tabelle.

python tools/sql_inventory.py                 # Übersicht auf der Konsole
python tools/sql_inventory.py --md docs/DATENZUGRIFF.md --json datenzugriff.json

Liest den Quelltext (AST), führt nichts aus und öffnet keine Datenbank. Erkannt werden Aufrufe von execute, executemany und
executescript. Ist der SQL-Text kein fester Text (z. B. aus Variablen zusammengesetzt), zählt der Aufruf als „dynamisch“:
Er lässt sich statisch nicht prüfen und gehört bei einer Mandantenprüfung zuerst angesehen.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sales_tool import data_map  # noqa: E402
from sales_tool import sql_scan  # noqa: E402


def markdown(inv):
    t = inv['totals']
    k = t['kinds']
    main_tables = sum(1 for n in inv['tables'] if n in data_map.TABLES)
    lines = [
        '# Datenzugriff – Inventar', '',
        'Automatisch erzeugt mit `tools/sql_inventory.py` aus dem Quelltext (SDQ-010). Nicht von Hand ändern.', '',
        f"{t['calls']} SQL-Aufrufe in {t['modules']} Modulen: {k['fest']} mit festem SQL-Text, {k['zusammengesetzt']} aus festen Teilen "
        f"zusammengesetzt, {k['indirekt']} über eine Hilfsfunktion, {k['durchgereicht']} Hilfsfunktionen, die SQL nur weiterreichen, und "
        f"{k['dynamisch']} nicht statisch lesbar. {main_tables} von {len(data_map.TABLES)} Tabellen der Hauptdatenbank werden im Quelltext "
        'namentlich angesprochen, dazu die Tabellen des Offline-Firmenkatalogs und des Mandantenverzeichnisses (je eigene Datei).', '',
        'Einordnung der Tabellen (Organisation, Installation, Zugang; Personenbezug; Aufbewahrung): `sales_tool/data_map.py`. '
        '„nur lesen“ nennt Module, die eine Tabelle lesen, aber nicht schreiben.', '',
        '## Tabellen', '',
        '| Tabelle | Bereich | Bezug | Personen | Aufbewahrung | nur lesen | schreiben |',
        '|---|---|---|---|---|---|---|',
    ]
    for name, row in inv['tables'].items():
        meta = data_map.TABLES.get(name)
        area, scope, personal, retention = ((meta.area, meta.scope, 'ja' if meta.personal else 'nein', meta.retention) if meta else
                                            (('Mandantenverzeichnis (eigene Datei)', data_map.DIRECTORY_TABLES[name], 'ja' if name == 'accounts' else 'nein',
                                              'kurz' if name == 'account_sessions' else 'fachlich') if name in data_map.DIRECTORY_TABLES else
                                             ('Firmenkatalog (eigene Datei)', data_map.CATALOG_TABLES.get(name, '?'), 'nein', 'kurz')))
        short = lambda mods: ', '.join(m.replace('sales_tool/', '') for m in mods) or '–'
        lines.append(f"| `{name}` | {area} | {scope} | {personal} | {retention} | {short(row['read'])} | {short(row['write'])} |")
    lines += ['', '## Module', '', '| Modul | Aufrufe | nicht lesbar | Tabellen |', '|---|---:|---:|---:|']
    for mod, row in inv['modules'].items():
        lines.append(f"| `{mod.replace('sales_tool/', '')}` | {row['calls']} | {row['dynamic']} | {len(row['tables'])} |")
    return '\n'.join(lines) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--md')
    ap.add_argument('--json')
    args = ap.parse_args(argv)
    inv = sql_scan.inventory(ROOT / 'sales_tool')
    if args.md:
        Path(args.md).write_text(markdown(inv), encoding='utf-8')
        print('geschrieben:', args.md)
    if args.json:
        Path(args.json).write_text(json.dumps(inv, ensure_ascii=False, indent=1), encoding='utf-8')
        print('geschrieben:', args.json)
    t = inv['totals']
    print(f"{t['calls']} SQL-Aufrufe, {t['dynamic']} dynamisch, {t['modules']} Module, {t['tables']} Tabellen")
    for name in inv['unknown']:
        print('Unbekannter Tabellenname im SQL:', name)
    return 0


if __name__ == '__main__':
    sys.exit(main())
