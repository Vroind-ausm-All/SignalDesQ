"""Organisationen einer Mehrmandanten-Installation verwalten (SDQ-011 bis SDQ-023) – eine Datenbank je Organisation.

Aufruf: ``python -m sales_tool.betreiber --root …`` (gleichwertig: ``python tools/organisationen.py --root …``).

Organisationen
  python -m sales_tool.betreiber --root /srv/signaldesk anlegen studio-nord "Studio Nord"
  ... liste [--alle]   |   archivieren studio-nord
  ... export studio-nord --out studio-nord.zip.sdenc --verschluesselt     (Passwort: SIGNALDESK_EXPORT_PASSWORT oder Abfrage)

Konten
  ... konto-anlegen erika "Erika Beispiel"      (Passwort: SIGNALDESK_PASSWORT oder Abfrage)
  ... mitglied erika studio-nord vertrieb        (Rolle: admin, vertrieb, buchhaltung, lesen)
  ... entziehen erika studio-nord   |   konto-sperren erika   |   konto-freigeben erika   |   konto erika
  ... passwort-setzen erika                      (Passwort vergessen; beendet alle Sitzungen)
  ... zwei-faktor-pflicht an|aus   |   zwei-faktor-zuruecksetzen erika

Betrieb
  ... zustand                                    (Bereitschaft; Rückgabewert 1, wenn nicht bereit)
  ... sichern [--ziel ORDNER] [--verschluesselt] [--pruefen]   (Passwort: SIGNALDESK_SICHERUNG_PASSWORT oder Abfrage)
  ... sicherungen   |   sicherung-pruefen 20261124-020000   |   zurueckspielen 20261124-020000 studio-nord --ja
  ... sicherungen-aufraeumen --behalten 14       (löscht ältere Sätze – nur auf ausdrücklichen Aufruf)
  ... protokoll [--anzahl 50] [--konto erika]   |   protokoll-pruefen

Die lokale Einzelplatz-Installation braucht das nicht. Organisationen werden nie gelöscht: Archivieren sperrt eine
Organisation, die Daten bleiben erhalten (Rechnungen sind aufbewahrungspflichtig). Jede Änderung steht im Protokoll.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from . import abrechnung, accounts, audit_trail, mailer, ops, tenancy


def _secret(env, prompt, confirm=True):
    value = os.environ.get(env)
    if value:
        return value
    value = getpass.getpass(prompt)
    if confirm and getpass.getpass('Wiederholen: ') != value:
        raise ValueError('Die beiden Eingaben stimmen nicht überein.')
    return value


def _parser():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--root', required=True, help='Ordner des Mandantenverzeichnisses')
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('anlegen')
    a.add_argument('slug')
    a.add_argument('name')
    a.add_argument('--admin', help='vorhandenes Konto gleich als Verwaltung der neuen Organisation eintragen')
    sub.add_parser('liste').add_argument('--alle', action='store_true', help='auch archivierte')
    sub.add_parser('archivieren').add_argument('slug')
    ex = sub.add_parser('export')
    ex.add_argument('slug')
    ex.add_argument('--out', required=True)
    ex.add_argument('--verschluesselt', action='store_true', help='AES-256-GCM, Dateiendung .zip.sdenc')
    k = sub.add_parser('konto-anlegen', help='zentrales Konto (Passwort aus SIGNALDESK_PASSWORT oder Abfrage)')
    k.add_argument('username')
    k.add_argument('display_name', nargs='?', default='')
    k.add_argument('--email', default='')
    ke = sub.add_parser('konto-email', help='E-Mail-Adresse eines Kontos setzen (leer: entfernen)')
    ke.add_argument('username')
    ke.add_argument('email', nargs='?', default='')
    st = sub.add_parser('einstellung', help='registrierung (aus|offen), public_url, testphase_tage, leerlauf_minuten (Standard 60, 0 = aus)')
    st.add_argument('schluessel', choices=sorted(accounts.SETTINGS))
    st.add_argument('wert')
    ab = sub.add_parser('tarif', help='Tarif und Abrechnungsstand einer Organisation ansehen oder setzen (Anbieter: manuell)')
    ab.add_argument('slug')
    ab.add_argument('--plan', choices=sorted(abrechnung.PLANS))
    ab.add_argument('--status', choices=abrechnung.STATUSES)
    ab.add_argument('--bis', help='bezahlt bis JJJJ-MM-TT (bei gekuendigt: Ende)')
    sub.add_parser('postausgang', help='abgelegte Nachrichten (Einladungen, Bestätigungen)').add_argument('--anzahl', type=int, default=20)
    m = sub.add_parser('mitglied', help='Konto einer Organisation zuordnen oder Rolle ändern')
    m.add_argument('username')
    m.add_argument('slug')
    m.add_argument('role')
    e = sub.add_parser('entziehen', help='Zugang zu einer Organisation entziehen (sofort)')
    e.add_argument('username')
    e.add_argument('slug')
    for name in ('konto-sperren', 'konto-freigeben', 'konto', 'passwort-setzen', 'zwei-faktor-zuruecksetzen'):
        sub.add_parser(name).add_argument('username')
    sub.add_parser('zwei-faktor-pflicht').add_argument('schalter', choices=('an', 'aus'))
    sub.add_parser('zustand', help='Bereitschaft der Installation').add_argument('--ziel', help='Ordner der Sicherungssätze')
    s = sub.add_parser('sichern', help='Sicherungssatz: Verzeichnis und alle Organisationen')
    s.add_argument('--ziel', help='anderer Ordner für die Sätze (z. B. eingehängter Sicherungsspeicher)')
    s.add_argument('--verschluesselt', action='store_true')
    s.add_argument('--pruefen', action='store_true', help='danach sofort den Wiederherstellungstest ausführen')
    sub.add_parser('sicherungen').add_argument('--ziel')
    sp = sub.add_parser('sicherung-pruefen', help='Wiederherstellungstest eines Satzes')
    sp.add_argument('name')
    sp.add_argument('--ziel')
    z = sub.add_parser('zurueckspielen', help='eine Organisation aus einem Satz wiederherstellen')
    z.add_argument('name')
    z.add_argument('slug')
    z.add_argument('--ziel')
    z.add_argument('--ja', action='store_true', help='Bestätigung: aktueller Stand wird ersetzt (vorher gesichert)')
    kp = sub.add_parser('sicherung-kopieren', help='Satz an einen zweiten Ort kopieren und Prüfsummen nachrechnen')
    kp.add_argument('name')
    kp.add_argument('--nach', required=True, help='Ordner am zweiten Ort (anderer Datenträger, eingehängter Speicher)')
    kp.add_argument('--ziel', help='Ordner der Sätze, falls nicht der Standard')
    gw = sub.add_parser('gesamt-wiederherstellen', help='ganze Installation aus einem Satz in den (leeren) --root-Ordner')
    gw.add_argument('satz', help='Pfad des Sicherungssatzes')
    gw.add_argument('--ja', action='store_true', help='Bestätigung')
    pr = sub.add_parser('sicherungen-aufraeumen')
    pr.add_argument('--behalten', type=int, required=True)
    pr.add_argument('--ziel')
    p = sub.add_parser('protokoll', help='Verwaltungs- und Anmeldeprotokoll')
    p.add_argument('--anzahl', type=int, default=50)
    p.add_argument('--konto', help='nur Einträge zu diesem Konto')
    sub.add_parser('protokoll-pruefen', help='Hash-Kette des Protokolls nachrechnen')
    return ap


def _set_password(name):
    return _secret('SIGNALDESK_SICHERUNG_PASSWORT', f'Passwort für {name}: ', confirm=False)


def run(args, d):  # noqa: C901 – eine Verzweigung je Befehl
    actor = audit_trail.operator()
    cmd = args.cmd
    if cmd == 'anlegen':
        if args.admin:
            accounts.account_view(d, args.admin)  # Konto muss vorhanden sein, bevor die Organisation entsteht
        org = d.create(args.slug, args.name, actor=actor)
        if args.admin:
            org['admin'] = accounts.set_membership(d, args.admin, args.slug, 'admin', actor=actor)
        return org, 0
    if cmd == 'liste':
        return d.list(include_archived=args.alle), 0
    if cmd == 'archivieren':
        return d.archive(args.slug, actor=actor), 0
    if cmd == 'export':
        pw = _secret('SIGNALDESK_EXPORT_PASSWORT', 'Passwort für den Export: ') if args.verschluesselt else None
        out = tenancy.export_organization(d.get(args.slug)['db_path'], args.out, password=pw)
        audit_trail.record(d, actor, 'export', args.slug, 'verschlüsselt' if pw else 'unverschlüsselt')
        if not pw:
            print('Hinweis: Export unverschlüsselt – nur auf verschlüsseltem Speicher ablegen oder --verschluesselt nutzen.', file=sys.stderr)
        return out, 0
    if cmd == 'konto-anlegen':
        pw = _secret('SIGNALDESK_PASSWORT', 'Passwort für das Konto: ')
        return accounts.create_account(d, args.username, pw, args.display_name, actor=actor, email=args.email), 0
    if cmd == 'konto-email':
        return accounts.set_email(d, args.username, args.email, actor=actor), 0
    if cmd == 'einstellung':
        return accounts.set_setting(d, args.schluessel, args.wert, actor=actor), 0
    if cmd == 'tarif':
        if args.plan or args.status or args.bis:
            return abrechnung.set_subscription(d, args.slug, args.plan, args.status, args.bis, actor=actor), 0
        d.get(args.slug)
        return abrechnung.state(d, args.slug), 0
    if cmd == 'postausgang':
        return {'ordner': str(d.root / mailer.FOLDER), 'nachrichten': mailer.outbox(d, args.anzahl)}, 0
    if cmd == 'mitglied':
        return accounts.set_membership(d, args.username, args.slug, args.role, actor=actor), 0
    if cmd == 'entziehen':
        return accounts.remove_membership(d, args.username, args.slug, actor=actor), 0
    if cmd in ('konto-sperren', 'konto-freigeben'):
        return accounts.set_active(d, args.username, cmd == 'konto-freigeben', actor=actor), 0
    if cmd == 'konto':
        return accounts.account_view(d, args.username), 0
    if cmd == 'passwort-setzen':
        return accounts.reset_password(d, args.username, _secret('SIGNALDESK_PASSWORT', 'Neues Passwort: '), actor=actor), 0
    if cmd == 'zwei-faktor-zuruecksetzen':
        return accounts.mfa_reset(d, args.username, actor=actor), 0
    if cmd == 'zwei-faktor-pflicht':
        return accounts.set_require_2fa(d, args.schalter == 'an', actor=actor), 0
    if cmd == 'zustand':
        out = ops.readiness(d, detail=True, backup_target=args.ziel)
        return out, 0 if out['status'] == 'bereit' else 1
    if cmd == 'sichern':
        pw = _secret('SIGNALDESK_SICHERUNG_PASSWORT', 'Passwort für die Sicherung: ') if args.verschluesselt else None
        out = ops.backup_all(d, args.ziel, password=pw, actor=actor)
        if not pw:
            print('Hinweis: Satz unverschlüsselt (enthält Kundendaten und Passwort-Hashes) – außerhalb des Servers nur mit '
                  '--verschluesselt ablegen.', file=sys.stderr)
        if args.pruefen:
            out['pruefung'] = ops.verify_backup(d, out['name'], args.ziel, password=pw, actor=actor)
            return out, 0 if out['pruefung']['ok'] else 1
        return out, 0
    if cmd == 'sicherungen':
        return ops.list_backups(d, args.ziel), 0
    if cmd == 'sicherung-pruefen':
        folder = ops.backup_root(d, args.ziel) / args.name
        encrypted = (folder / 'manifest.json').exists() and json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))['encrypted']
        out = ops.verify_backup(d, args.name, args.ziel, password=_set_password(args.name) if encrypted else None, actor=actor)
        return out, 0 if out['ok'] else 1
    if cmd == 'zurueckspielen':
        folder = ops.backup_root(d, args.ziel) / args.name
        encrypted = (folder / 'manifest.json').exists() and json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))['encrypted']
        return ops.restore_org(d, args.name, args.slug, args.ziel, password=_set_password(args.name) if encrypted else None,
                               confirm=args.ja, actor=actor), 0
    if cmd == 'sicherung-kopieren':
        return ops.copy_backup(d, args.name, args.nach, target=args.ziel, actor=actor), 0
    if cmd == 'sicherungen-aufraeumen':
        return ops.prune_backups(d, args.behalten, args.ziel, actor=actor), 0
    if cmd == 'protokoll':
        return audit_trail.events(d, args.anzahl, target=args.konto), 0
    if cmd == 'protokoll-pruefen':
        out = audit_trail.verify(d)
        return out, 0 if out['ok'] else 1
    raise ValueError(f'Unbekannter Befehl {cmd}')


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.cmd == 'gesamt-wiederherstellen':  # --root ist hier der neue, leere Ordner: nichts vorher anlegen
            manifest = Path(args.satz).expanduser() / 'manifest.json'
            encrypted = manifest.exists() and json.loads(manifest.read_text(encoding='utf-8')).get('encrypted')
            pw = _secret('SIGNALDESK_SICHERUNG_PASSWORT', 'Passwort der Sicherung: ', confirm=False) if encrypted else None
            out, code = ops.restore_installation(args.satz, args.root, password=pw or None, confirm=args.ja), 0
        else:
            out, code = run(args, tenancy.Directory(args.root))
    except (tenancy.TenantError, LookupError, ValueError, PermissionError) as exc:
        print('FEHLER:', exc)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    return code


if __name__ == '__main__':
    sys.exit(main())
