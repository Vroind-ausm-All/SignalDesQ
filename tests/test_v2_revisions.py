"""2.0.0-dev21: Produktreview M15 Teil 1 – Angebotsrevisionen (Abnahmefall T11).

Abnahme: Eine Revision zeigt ihren Vorgänger und die wesentlichen Änderungen. Nach Annahme bleibt der Stand erhalten.
- Nummer mit Revisionszähler, gleiche Firma und Chance, Änderungsgrund Pflicht.
- Vorgänger unverändert gespeichert, aber ersetzt: keine Freigabe, kein Versand, keine Zusage, keine Erinnerung.
- Angenommene/abgelehnte Angebote werden nicht überarbeitet; ersetzte nur über die neueste Fassung.
- Ältere Angebote ohne gespeicherten Bauplan lassen sich aus dem Kundendokument rekonstruieren.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5_helpers import confirm_need, release_offer  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import offer_flow as of  # noqa: E402
from sales_tool import revisions as rv  # noqa: E402
from sales_tool import today as td  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.sales_workspace import customer_markdown, make_proposal, proposal_rows  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402

V1 = [{'service': 'webdesign', 'size': 'M'}, {'service': 'texte', 'qty': 4}, {'service': 'seo_geo', 'size': 'S'}]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'r.sqlite3')
        prepare_database(self.db)
        self.conn = connect(self.db)
        self.lead = self.conn.execute("INSERT INTO leads(company, stage) VALUES ('Revision Fiktiv GmbH', 'termin')").lastrowid
        self.conn.commit()
        confirm_need(self.conn, self.lead)
        self.v1 = make_proposal(self.conn, {'lead_id': self.lead, 'positions': V1, 'tax_mode': 'regel_19', 'project_label': 'Neue Website'})

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def revise(self, pid, positions, reason='Umfang auf Wunsch reduziert'):
        return make_proposal(self.conn, {'lead_id': self.lead, 'positions': positions, 'tax_mode': 'regel_19', 'project_label': 'Neue Website',
                                         'revision_of': pid, 'revision_reason': reason})


class RevisionTests(Base):
    def test_revision_shows_predecessor_and_changes(self):
        release_offer(self.conn, self.v1['id'])
        of.set_status(self.conn, self.v1['id'], {'status': 'gesendet_manuell'})
        before = self.conn.execute('SELECT customer_json, internal_json FROM proposals WHERE id=?', (self.v1['id'],)).fetchone()
        prep = rv.prepare(self.conn, self.v1['id'])
        self.assertEqual(prep['payload']['positions'], V1, 'Bauplan des Vorgängers')
        v2 = self.revise(self.v1['id'], [{'service': 'webdesign', 'size': 'S'}, {'service': 'texte', 'qty': 4}])
        self.assertEqual(v2['number'], self.v1['number'] + '-R2')
        self.assertEqual((v2['revision_no'], v2['opportunity_id']), (2, self.v1['opportunity_id']))
        ch = v2['customer']['revision']['changes']
        self.assertTrue(any(c.startswith('Geändert: Webdesign & Website-Umsetzung – Standard') for c in ch), ch)
        self.assertTrue(any(c.startswith('Entfällt: SEO- & GEO-Optimierung') for c in ch), ch)
        self.assertTrue(any(c.startswith('Summe einmalig netto:') for c in ch), ch)
        md = customer_markdown(v2['customer'])
        self.assertIn(f"Überarbeitete Fassung 2** – ersetzt Angebot {self.v1['number']}", md)
        self.assertIn(f"## Änderungen gegenüber Angebot {self.v1['number']}", md)
        self.assertIn('Anlass: Umfang auf Wunsch reduziert', md)
        after = self.conn.execute('SELECT customer_json, internal_json, superseded_by, status FROM proposals WHERE id=?', (self.v1['id'],)).fetchone()
        self.assertEqual((after['customer_json'], after['internal_json']), (before['customer_json'], before['internal_json']), 'Vorgänger unverändert')
        self.assertEqual((after['superseded_by'], after['status']), (v2['id'], 'gesendet_manuell'))
        open_tasks = [r['title'] for r in self.conn.execute('SELECT title FROM tasks WHERE lead_id=? AND done=0', (self.lead,))]
        self.assertFalse([t for t in open_tasks if f"(#{self.v1['id']})" in t], 'Nachfassen zum Vorgänger beendet')
        for call in (lambda: of.set_status(self.conn, self.v1['id'], {'status': 'angenommen'}),
                     lambda: rv.prepare(self.conn, self.v1['id']),
                     lambda: self.revise(self.v1['id'], V1)):
            with self.assertRaisesRegex(ValueError, 'ersetzt'):
                call()
        rows = {r['id']: r for r in proposal_rows(self.conn)}
        self.assertTrue(rows[self.v1['id']]['superseded'])
        self.assertEqual(rows[v2['id']]['revision_no'], 2)
        h = rv.history(self.conn, v2['id'])
        self.assertEqual([v['number'] for v in h['versions']], [self.v1['number'], v2['number']])
        self.assertEqual(h['versions'][1]['reason'], 'Umfang auf Wunsch reduziert')
        v3 = self.revise(v2['id'], [{'service': 'webdesign', 'size': 'S'}], 'Texte liefert der Kunde selbst')
        self.assertEqual(v3['number'], self.v1['number'] + '-R3')
        self.assertEqual(len(rv.history(self.conn, self.v1['id'])['versions']), 3)

    def test_superseded_offers_leave_reminders_and_sums(self):
        self.conn.execute("UPDATE proposals SET updated_at=datetime('now','-5 day') WHERE id=?", (self.v1['id'],))
        self.conn.commit()
        self.assertTrue(any(i['ref'] == self.v1['id'] for i in td.wiedervorlage(self.conn)))
        v2 = self.revise(self.v1['id'], V1[:1])
        self.conn.execute("UPDATE proposals SET updated_at=datetime('now','-5 day')")
        self.conn.commit()
        refs = [i['ref'] for i in td.wiedervorlage(self.conn) if i['kind'] == 'angebot_entwurf']
        self.assertNotIn(self.v1['id'], refs)
        self.assertIn(v2['id'], refs)
        pot = td.potential(self.conn)
        self.assertEqual([o['proposal_id'] for o in pot['offers']], [v2['id']], 'ersetzte Fassung zählt nicht doppelt')

    def test_accepted_stays_and_reason_required(self):
        with self.assertRaisesRegex(ValueError, 'Grund'):
            self.revise(self.v1['id'], V1, reason='')
        release_offer(self.conn, self.v1['id'])
        of.set_status(self.conn, self.v1['id'], {'status': 'angenommen'})
        with self.assertRaisesRegex(ValueError, 'Zusatzauftrag'):
            self.revise(self.v1['id'], V1)
        other = self.conn.execute("INSERT INTO leads(company) VALUES ('Andere Fiktiv KG')").lastrowid
        v = make_proposal(self.conn, {'lead_id': other, 'positions': V1, 'tax_mode': 'regel_19'})
        with self.assertRaisesRegex(ValueError, 'andere'):
            make_proposal(self.conn, {'lead_id': self.lead, 'positions': V1, 'revision_of': v['id'], 'revision_reason': 'falsche Firma'})

    def test_old_offer_without_stored_plan_is_reconstructed(self):
        row = self.conn.execute('SELECT internal_json FROM proposals WHERE id=?', (self.v1['id'],)).fetchone()
        internal = json.loads(row['internal_json'])
        internal.pop('payload')
        self.conn.execute('UPDATE proposals SET internal_json=? WHERE id=?', (json.dumps(internal), self.v1['id']))
        self.conn.commit()
        p = rv.prepare(self.conn, self.v1['id'])['payload']
        self.assertEqual([(x['service'], x.get('size'), x.get('qty')) for x in p['positions']],
                         [('webdesign', 'M', None), ('texte', None, 4), ('seo_geo', 'S', None)])
        self.assertEqual(p['project_label'], 'Neue Website')


if __name__ == '__main__':
    unittest.main()
