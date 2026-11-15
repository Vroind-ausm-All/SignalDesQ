"""2.0.0-dev31: Abnahmefall T15 – Sicherung in getrennte Testinstallation zurückspielen (nach Etappe C und D).

Szenario: Eine Installation mit allem, was Etappe C und D anlegen (Chancen, Briefing, Revision, Option, Nachfassen mit
Ergebnis, Übergabe/Abnahme, Zusatzauftrag, Betreuung mit Monatsrechnung, Zeiten je Position, Projektkompass, eigene
Vorlage mit Entwurf, Kurzbericht). Die Sicherung wird in eine zweite, getrennte Installation zurückgespielt. Dort sind alle
Daten vorhanden, die Abläufe funktionieren weiter, und die Ausgangsinstallation bleibt unverändert.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import datetime as dt
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5_helpers import confirm_need, release_offer  # noqa: E402
from test_accounting import SELLER  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import accounting as acc  # noqa: E402
from sales_tool import addenda, briefing, care, chances, followups, handover, kickoff, messages, offer_flow as of, postcalc  # noqa: E402
from sales_tool.accounting_api import create_backup  # noqa: E402
from sales_tool.backup_restore import restore  # noqa: E402
from sales_tool.customer_report import build as build_report  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.sales_workspace import create_mail_draft, make_proposal  # noqa: E402
from sales_tool.server import SCHEMA_VERSION, prepare_database  # noqa: E402

TABLES = ('leads', 'opportunities', 'briefing_answers', 'proposals', 'tasks', 'handovers', 'handover_items', 'care_contracts',
          'invoices', 'time_entries', 'kickoffs', 'kickoff_items', 'message_templates', 'mail_drafts', 'customer_reports', 'activities')


def counts(db):
    c = sqlite3.connect(str(db))
    try:
        return {t: c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in TABLES}
    finally:
        c.close()


class RestoreScenarioTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / 'produktiv').mkdir()
        (root / 'test').mkdir()
        self.prod = root / 'produktiv' / 'signaldesk.sqlite3'
        self.test = root / 'test' / 'signaldesk.sqlite3'

    def tearDown(self):
        cleanup_tmp(self.tmp)

    def populate(self):
        prepare_database(self.prod)
        c = connect(str(self.prod))
        acc.save_settings(c, SELLER)
        lead = c.execute("INSERT INTO leads(company, stage, website) VALUES ('Sicherung Fiktiv GmbH', 'termin', 'https://sicherung.example')").lastrowid
        contact = c.execute("INSERT INTO decision_contacts(lead_id, full_name) VALUES (?, 'Maria Beispiel')", (lead,)).lastrowid
        c.commit()
        oid = chances.create(c, lead, {'title': 'Website mit Betreuung'})['id']
        confirm_need(c, lead)
        confirm_need(c, lead, chance=oid)
        briefing.save(c, oid, {'areas': ['medien'], 'answers': [{'key': 'inhalte', 'status': 'offen', 'answer': 'Texte liefert der Kunde bis Monatsende'}]})
        v1 = make_proposal(c, {'lead_id': lead, 'opportunity_id': oid, 'tax_mode': 'regel_19', 'project_label': 'Website mit Betreuung',
                               'positions': [{'service': 'webdesign', 'size': 'S'}, {'service': 'pflege', 'size': 'M'}, {'service': 'texte', 'qty': 2, 'optional': True}]})
        release_offer(c, v1['id'])
        of.set_status(c, v1['id'], {'status': 'gesendet_manuell', 'follow_up': (dt.date.today() + dt.timedelta(days=2)).isoformat()})
        fid = followups.for_proposal(c, v1['id'])['open'][0]['id']
        followups.record(c, fid, {'outcome': 'rueckfragen', 'note': 'Logo kleiner', 'next_date': (dt.date.today() + dt.timedelta(days=3)).isoformat()})
        v2 = make_proposal(c, {'lead_id': lead, 'tax_mode': 'regel_19', 'project_label': 'Website mit Betreuung', 'revision_of': v1['id'],
                               'revision_reason': 'Umfang nach Rückfrage angepasst', 'positions': [{'service': 'webdesign', 'size': 'S'}, {'service': 'pflege', 'size': 'M'}]})
        release_offer(c, v2['id'])
        of.set_status(c, v2['id'], {'status': 'gesendet_manuell'})
        of.set_status(c, v2['id'], {'status': 'angenommen'})
        ko = kickoff.state(c, v2['id'])
        kickoff.act(c, v2['id'], {'action': 'start', 'trotz_offener_punkte': True})
        postcalc.add_entry(c, {'proposal_id': v2['id'], 'hours': 3, 'position': 1})
        h = handover.state(c, v2['id'])
        for i in h['items']:
            if i['kind'] == 'liefer':
                handover.act(c, v2['id'], {'action': 'item', 'item_id': i['id'], 'state': 'erledigt'})
        handover.act(c, v2['id'], {'action': 'uebergabe'})
        handover.act(c, v2['id'], {'action': 'abnahme', 'result': 'vorbehalt', 'points': [{'label': 'Favicon nachliefern'}]})
        acc.invoice_from_proposal(c, {'proposal_id': v2['id'], 'mode': 'monat'})
        z1 = make_proposal(c, {'lead_id': lead, 'tax_mode': 'regel_19', 'positions': [{'service': 'texte', 'qty': 2}],
                               'addendum_of': v2['id'], 'addendum_reason': 'Kundenwunsch: zwei weitere Seiten'})
        tpl = next(t['id'] for t in messages.list_templates(c)['templates'] if t['key'] == 'angebot_versand')
        create_mail_draft(c, {'lead_id': lead, 'template_id': tpl, 'proposal_id': z1['id'], 'contact_id': contact, 'contact_basis': 'Im Termin vereinbart'})
        a = c.execute("INSERT INTO website_audits(lead_id, url, status, finished_at) VALUES (?, 'https://sicherung.example', 'done', datetime('now'))", (lead,)).lastrowid
        f = c.execute("""INSERT INTO website_findings(audit_id, lead_id, rubric, area, label, result, weight, evidence, source_url, method, certainty, review_status)
                         VALUES (?, ?, 'B3', 'web', 'Anfrageweg', 'auffaellig', 3, 'Kein Anfrageweg sichtbar.', 'https://sicherung.example/', 'dom', 'beobachtet', 'bestaetigt')""", (a, lead)).lastrowid
        c.commit()
        build_report(c, lead, {'items': [f'w{f}']})
        c.close()
        return {'lead': lead, 'v1': v1, 'v2': v2, 'z1': z1, 'kickoff_items': len(ko['items'])}

    def test_backup_restores_into_separate_installation(self):
        ids = self.populate()
        before = counts(self.prod)
        self.assertTrue(all(before[t] > 0 for t in TABLES), before)
        backup = create_backup(self.prod)['path']
        self.assertTrue(Path(backup).is_relative_to(self.prod.parent), 'Sicherung liegt bei der Ausgangsinstallation')
        # getrennte Testinstallation: eigener Ordner, eigene (leere) Datenbank
        prepare_database(self.test)
        r = restore(self.test, backup, confirm=True)
        self.assertEqual(r['schema'], SCHEMA_VERSION)
        self.assertEqual(counts(self.test), before, 'alle Daten aus Etappe C und D wiederhergestellt')
        self.assertEqual(counts(self.prod), before, 'Ausgangsinstallation unverändert')
        self.assertTrue(r['safety_backup'] and Path(r['safety_backup']).is_relative_to(self.test.parent),
                        'Sicherheitskopie vor dem Zurückspielen liegt in der Testinstallation')
        # Abläufe in der Testinstallation
        t = connect(str(self.test))
        try:
            self.assertTrue(of.state(t, ids['v1']['id'])['superseded_by'], 'Revision bleibt ersetzt')
            self.assertEqual(handover.state(t, ids['v2']['id'])['status'], 'vorbehalt')
            self.assertEqual(kickoff.state(t, ids['v2']['id'])['status'], 'gestartet')
            self.assertEqual(len(kickoff.state(t, ids['v2']['id'])['items']), ids['kickoff_items'])
            sc = addenda.scope(t, ids['v2']['id'])
            self.assertEqual([a['number'] for a in sc['addenda']], [ids['z1']['number']])
            k = care.overview(t)['firms'][0]['care'][0]
            self.assertNotIn(dt.date.today().isoformat()[:7], k['due_months'], 'Monatsrechnung bleibt zugeordnet')
            with self.assertRaisesRegex(ValueError, 'bereits'):
                acc.invoice_from_proposal(t, {'proposal_id': ids['v2']['id'], 'mode': 'monat'})
            card = next(p for p in postcalc.overview(t)['projects'] if p['proposal_id'] == ids['v2']['id'])
            self.assertEqual(card['positions'][0]['actual_hours'], 3)
            # weiterarbeiten: neue Fassung des Zusatzauftrags in der Testinstallation
            z = make_proposal(t, {'lead_id': ids['lead'], 'tax_mode': 'regel_19', 'positions': [{'service': 'texte', 'qty': 1}],
                                  'revision_of': ids['z1']['id'], 'revision_reason': 'Nur eine Seite'})
            self.assertEqual(z['number'], ids['z1']['number'] + '-R2')
        finally:
            t.close()
        self.assertEqual(counts(self.prod)['proposals'], before['proposals'], 'Arbeit in der Testinstallation berührt die Ausgangsinstallation nicht')

    def test_backup_from_older_schema_is_migrated(self):
        self.populate()
        old = Path(self.tmp.name) / 'alt.sqlite3'
        shutil.copyfile(self.prod, old)
        c = sqlite3.connect(str(old))
        c.execute('PRAGMA user_version=34')  # Stand dev21/dev22 vortäuschen: Spalten sind da, neuere Tabellen fehlen
        for table in ('customer_reports', 'message_templates', 'kickoff_items', 'kickoffs', 'care_contracts', 'handover_items', 'handovers'):
            c.execute(f'DROP TABLE {table}')
        c.commit()
        c.close()
        prepare_database(self.test)
        r = restore(self.test, old, confirm=True)
        self.assertEqual(r['schema'], SCHEMA_VERSION, 'auf das aktuelle Schema migriert')
        n = counts(self.test)
        self.assertEqual(n['handovers'], 0)
        self.assertGreater(n['message_templates'], 0, 'Startvorlagen nach Migration vorhanden')
        self.assertEqual(n['proposals'], counts(self.prod)['proposals'])


if __name__ == '__main__':
    unittest.main()
