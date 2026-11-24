"""Organisationen einer Mehrmandanten-Installation verwalten (SDQ-011/013) – eine Datenbank je Organisation.

python tools/organisationen.py --root D:/signaldesk-mandanten anlegen studio-nord "Studio Nord"
python tools/organisationen.py --root ... liste [--alle]
python tools/organisationen.py --root ... archivieren studio-nord
python tools/organisationen.py --root ... export studio-nord --out studio-nord.zip

Die lokale Einzelplatz-Installation braucht das nicht. Gelöscht wird nichts: Archivieren sperrt eine Organisation, die Daten
bleiben erhalten (Rechnungen sind aufbewahrungspflichtig). Der Export enthält keine Zugangsdaten und ist unverschlüsselt.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sales_tool import tenancy  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--root', required=True, help='Ordner des Mandantenverzeichnisses')
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('anlegen')
    a.add_argument('slug')
    a.add_argument('name')
    lst = sub.add_parser('liste')
    lst.add_argument('--alle', action='store_true', help='auch archivierte')
    ar = sub.add_parser('archivieren')
    ar.add_argument('slug')
    ex = sub.add_parser('export')
    ex.add_argument('slug')
    ex.add_argument('--out', required=True)
    args = ap.parse_args(argv)
    d = tenancy.Directory(args.root)
    try:
        if args.cmd == 'anlegen':
            out = d.create(args.slug, args.name)
        elif args.cmd == 'liste':
            out = d.list(include_archived=args.alle)
        elif args.cmd == 'archivieren':
            out = d.archive(args.slug)
        else:
            out = tenancy.export_organization(d.get(args.slug)['db_path'], args.out)
    except (tenancy.TenantError, LookupError) as exc:
        print('FEHLER:', exc)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
