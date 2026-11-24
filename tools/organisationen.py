"""Organisationen einer Mehrmandanten-Installation verwalten (SDQ-011/013) – eine Datenbank je Organisation.

python tools/organisationen.py --root D:/signaldesk-mandanten anlegen studio-nord "Studio Nord"
python tools/organisationen.py --root ... liste [--alle]
python tools/organisationen.py --root ... archivieren studio-nord
python tools/organisationen.py --root ... export studio-nord --out studio-nord.zip
python tools/organisationen.py --root ... konto-anlegen erika "Erika Beispiel"      (Passwort wird abgefragt)
python tools/organisationen.py --root ... mitglied erika studio-nord vertrieb        (Rolle: admin, vertrieb, buchhaltung, lesen)
python tools/organisationen.py --root ... entziehen erika studio-nord
python tools/organisationen.py --root ... konto-sperren erika   |   konto-freigeben erika   |   konto erika

Die lokale Einzelplatz-Installation braucht das nicht. Gelöscht wird nichts: Archivieren sperrt eine Organisation, die Daten
bleiben erhalten (Rechnungen sind aufbewahrungspflichtig). Der Export enthält keine Zugangsdaten und ist unverschlüsselt.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sales_tool import accounts, tenancy  # noqa: E402


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
    k = sub.add_parser('konto-anlegen', help='zentrales Konto (Passwort aus SIGNALDESK_PASSWORT oder Abfrage)')
    k.add_argument('username')
    k.add_argument('display_name', nargs='?', default='')
    m = sub.add_parser('mitglied', help='Konto einer Organisation zuordnen oder Rolle ändern')
    m.add_argument('username')
    m.add_argument('slug')
    m.add_argument('role')
    e = sub.add_parser('entziehen', help='Zugang zu einer Organisation entziehen (sofort)')
    e.add_argument('username')
    e.add_argument('slug')
    for name in ('konto-sperren', 'konto-freigeben', 'konto'):
        sub.add_parser(name).add_argument('username')
    args = ap.parse_args(argv)
    d = tenancy.Directory(args.root)
    try:
        if args.cmd == 'anlegen':
            out = d.create(args.slug, args.name)
        elif args.cmd == 'liste':
            out = d.list(include_archived=args.alle)
        elif args.cmd == 'archivieren':
            out = d.archive(args.slug)
        elif args.cmd == 'export':
            out = tenancy.export_organization(d.get(args.slug)['db_path'], args.out)
        elif args.cmd == 'konto-anlegen':
            import getpass
            import os
            pw = os.environ.get('SIGNALDESK_PASSWORT') or getpass.getpass('Passwort für das Konto: ')
            out = accounts.create_account(d, args.username, pw, args.display_name)
        elif args.cmd == 'mitglied':
            out = accounts.set_membership(d, args.username, args.slug, args.role)
        elif args.cmd == 'entziehen':
            out = accounts.remove_membership(d, args.username, args.slug)
        elif args.cmd in ('konto-sperren', 'konto-freigeben'):
            out = accounts.set_active(d, args.username, args.cmd == 'konto-freigeben')
        else:
            out = accounts.account_view(d, args.username)
    except (tenancy.TenantError, LookupError, ValueError, PermissionError) as exc:
        print('FEHLER:', exc)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
