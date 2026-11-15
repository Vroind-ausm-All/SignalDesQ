"""2.0.0-dev32: Abnahmefälle T07, T09, T10 und T13 als Szenarien über die vorhandenen Funktionen.

- T07 Projektanfrage aufnehmen: eingegangene Anfrage einer neuen Firma → Firma, Chance, Bedarf, Angebot aus bestätigtem
  Bedarf; die Anfrage wird fristgerecht als erledigt vermerkt.
- T09 Medienangebot: Logo und Drucksache – Prüfpunkte Mediengestaltung, Korrekturschleifen, Nutzungsrechte, Druck- und
  Lizenzkosten außerhalb des Festpreises; Projektkompass fragt Material und Freigabeperson an.
- T10 Softwareangebot: Prüfpunkte Software (Betrieb, Zugänge, Testdaten, Übergabe); Kompass mit Testzugang ohne Passwörter.
- T13 Zeitüberschreitung: Ist-Zeit über der Kalkulation → Hinweis, Umfang zu prüfen; Mehrarbeit als Zusatzauftrag, ohne den
  Auftrag zu ändern. Kundendokumente enthalten nie Stunden oder Sätze.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5_helpers import confirm_need, release_offer  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import addenda, chances, kickoff, offer_flow as of, postcalc, reach  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.sales_workspace import customer_markdown, make_proposal  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402
from sales_tool.workday import quote_from_need  # noqa: E402

INTERNAL = ('Stundensatz', 'effective_hourly', 'Mindestverdienst', ' h ', 'Puffer', 'Kalkulation')


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 's.sqlite3')
        prepare_database(self.db)
        self.conn = connect(self.db)

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def lead(self, name):
        lid = self.conn.execute("INSERT INTO leads(company, stage) VALUES (?, 'termin')", (name,)).lastrowid
        self.conn.commit()
        return lid

    def accept(self, p):
        release_offer(self.conn, p['id'])
        of.set_status(self.conn, p['id'], {'status': 'gesendet_manuell'})
        of.set_status(self.conn, p['id'], {'status': 'angenommen'})

    def assert_customer_clean(self, p, allow=()):
        md = customer_markdown(p['customer'])
        for word in INTERNAL:
            if word not in allow:
                self.assertNotIn(word, md)
        keys = set(p['customer']) | {k for pos in p['customer'].get('positions') or [] for k in pos}
        self.assertFalse(keys & of.INTERNAL_KEYS, 'keine internen Felder im Kundendokument')
        self.assertNotRegex(md, r'\d\.\d\d EUR', 'Beträge in deutscher Schreibweise')
        return md


class ScenarioTests(Base):
    def test_t07_project_request_to_offer(self):
        now = dt.datetime.now().replace(second=0, microsecond=0)
        inbound = reach.create_inbound(self.conn, {'who': 'Anfrage Fiktiv GmbH', 'channel': 'formular', 'note': 'Neue Website mit Terminbuchung gewünscht'}, now=now)
        self.assertTrue(inbound['due_at'] >= now.strftime(reach.FMT), 'Rückmeldefrist aus den eigenen Zeiten')
        lid = self.lead('Anfrage Fiktiv GmbH')
        self.conn.execute('UPDATE inbound SET lead_id=? WHERE id=?', (lid, inbound['id']))
        self.conn.commit()
        oid = chances.create(self.conn, lid, {'title': 'Website mit Terminbuchung'})['id']
        confirm_need(self.conn, lid, needs=[{'service': 'webdesign', 'size': 'M'}])
        p = quote_from_need(self.conn, lid, {'tax_mode': 'regel_19', 'opportunity_id': oid})
        self.assertEqual(p['opportunity_id'], oid, 'Angebot gehört zur Chance der Anfrage')
        self.assertEqual([x['service'] for x in p['customer']['positions']], ['webdesign'], 'nur bestätigte Leistungen')
        self.assertIn('Grundlage: Bedarf', p['customer']['assumptions'])
        done = reach.complete_inbound(self.conn, inbound['id'], {'result': f"Angebot {p['number']} erstellt"}, now=now)
        self.assertTrue(done['in_time'])
        self.assert_customer_clean(p)

    def test_t09_media_offer(self):
        lid = self.lead('Medien Fiktiv GmbH')
        confirm_need(self.conn, lid)
        p = make_proposal(self.conn, {'lead_id': lid, 'tax_mode': 'regel_19', 'project_label': 'Logo und Flyer',
                                      'positions': [{'service': 'logo', 'size': 'M'}, {'service': 'print', 'size': 'S'}]})
        checks = {c['area']: c['items'] for c in p['internal']['checks']}
        self.assertIn('medien', checks)
        self.assertIn('Nutzungsumfang und Übergabe von Quelldateien sind geklärt', checks['medien'])
        md = self.assert_customer_clean(p)
        self.assertIn('Korrekturschleifen', md)
        self.assertIn('Nutzungsrechte', md)
        self.assertIn('Druckkosten', md, 'Druckkosten ausdrücklich außerhalb des Festpreises')
        self.accept(p)
        labels = [i['label'] for i in kickoff.state(self.conn, p['id'])['items']]
        self.assertIn('Logo, Bilder und Texte für den ersten Arbeitsschritt', labels)
        self.assertIn('Eine Person für gebündeltes Feedback und die finale Freigabe benennen', labels)

    def test_t10_software_offer(self):
        lid = self.lead('Software Fiktiv GmbH')
        confirm_need(self.conn, lid)
        p = make_proposal(self.conn, {'lead_id': lid, 'tax_mode': 'regel_19', 'project_label': 'Kundenportal',
                                      'positions': [{'service': 'software', 'size': 'M'}, {'service': 'pflege', 'size': 'S'}]})
        checks = {c['area']: c['items'] for c in p['internal']['checks']}
        self.assertEqual(checks['software'][:2], ['Betrieb ist geklärt: wer hostet, aktualisiert, überwacht',
                                                   'Schnittstellen und Zugänge sind benannt (keine Passwörter in Mail oder Notizen)'])
        self.assert_customer_clean(p)
        self.assertEqual(p['customer']['billing'], 'gemischt', 'Betrieb als laufende Leistung getrennt ausgewiesen')
        self.accept(p)
        k = kickoff.state(self.conn, p['id'])
        z = next(i for i in k['items'] if i['kind'] == 'zugang')
        self.assertIn('keine Passwörter', z['label'])
        with self.assertRaisesRegex(ValueError, 'keine Passwörter'):
            kickoff.act(self.conn, p['id'], {'action': 'item', 'item_id': z['id'], 'note': 'Passwort: Sommer2026'})

    def test_t13_time_overrun(self):
        lid = self.lead('Aufwand Fiktiv GmbH')
        confirm_need(self.conn, lid)
        p = make_proposal(self.conn, {'lead_id': lid, 'tax_mode': 'regel_19', 'project_label': 'Logo', 'positions': [{'service': 'logo', 'size': 'S'}]})
        self.accept(p)
        before = self.conn.execute('SELECT customer_json FROM proposals WHERE id=?', (p['id'],)).fetchone()[0]
        est = next(x for x in postcalc.overview(self.conn)['projects'] if x['proposal_id'] == p['id'])['estimated_hours']
        postcalc.add_entry(self.conn, {'proposal_id': p['id'], 'hours': round(est + 4, 2), 'position': 1, 'note': 'zusätzliche Varianten'})
        card = next(x for x in postcalc.overview(self.conn)['projects'] if x['proposal_id'] == p['id'])
        self.assertEqual(card['status'], 'ueberzogen')
        self.assertIn('Umfang mit dem Kunden prüfen', card['verdict'])
        self.assertEqual(card['remaining_hours'], 0)
        self.assertGreater(card['positions'][0]['variance_pct'], 0)
        z = make_proposal(self.conn, {'lead_id': lid, 'tax_mode': 'regel_19', 'positions': [{'service': 'aufwand', 'qty': 4}],
                                      'addendum_of': p['id'], 'addendum_reason': 'Kundenwunsch: zwei weitere Logo-Varianten'})
        self.assertEqual(z['number'], p['number'] + '-Z1')
        self.assertEqual(self.conn.execute('SELECT customer_json FROM proposals WHERE id=?', (p['id'],)).fetchone()[0], before, 'Auftrag unverändert')
        self.assertEqual(len(addenda.scope(self.conn, p['id'])['addenda']), 1)
        md = self.assert_customer_clean(z, allow=('Stundensatz',))  # „nach Aufwand“ wird ausdrücklich nach Stunden abgerechnet
        self.assertRegex(md, r'\*\*[\d.]+,\d\d € netto\*\*')


if __name__ == '__main__':
    unittest.main()
