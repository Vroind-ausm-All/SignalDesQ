"""2.0.0-dev18: Produktreview M13 Teil 1 – mehrere Verkaufschancen je Firma.

Abnahme (Review): Zwei offene Chancen einer Firma haben getrennte Bedürfnisse, Phasen und Termine (T08). Der Verlust einer
Chance beendet keine andere und verändert keine Rechnung. Eine neue Chance erzeugt kein Duplikat der Firma.
Zusätzlich: Firmenphase folgt den Chancen nur nach oben bzw. zum Abschluss; Bestand bekommt genau eine erste Chance mit
zugeordneten Angeboten und Terminen (geprüft an einer Kopie einer älteren Datenbank), ohne Duplikate bei erneutem Start.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5_helpers import confirm_need, release_offer  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import chances as ch  # noqa: E402
from sales_tool import offer_flow as of  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.sales_workspace import create_meeting, make_proposal  # noqa: E402
from sales_tool.server import SCHEMA_VERSION, make_handler, prepare_database  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOGO = [{'service': 'logo', 'size': 'M'}]
SOFT = [{'service': 'software', 'size': 'S'}]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'c.sqlite3')
        prepare_database(self.db)
        self.conn = connect(self.db)
        self.lead = self.conn.execute("INSERT INTO leads(company, stage) VALUES ('Chancen Fiktiv GmbH', 'kontakt')").lastrowid
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def stage(self):
        return self.conn.execute('SELECT stage FROM leads WHERE id=?', (self.lead,)).fetchone()['stage']

    def chance(self, oid):
        return next(c for c in ch.list_chances(self.conn, self.lead)['chances'] if c['id'] == oid)


class TwoChancesTests(Base):
    def test_t08_separate_needs_stages_and_meetings(self):
        self.conn.execute("INSERT INTO discovery(lead_id, problem, desired_outcome) VALUES (?, 'Website veraltet', 'Mehr Anfragen')", (self.lead,))
        a = ch.create(self.conn, self.lead, {'title': 'Neue Website', 'offer': 'conversion'})
        b = ch.create(self.conn, self.lead, {'title': 'Kundenportal', 'offer': 'portal', 'problem': 'Statusanfragen per Telefon', 'timing': 'Q3'})
        self.assertEqual((a['is_first'], b['is_first']), (1, 0))
        self.assertEqual(a['problem'], 'Website veraltet')  # erste Chance: Bedarfsanalyse der Firma
        self.assertEqual((b['problem'], b['timing']), ('Statusanfragen per Telefon', 'Q3'))
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM leads').fetchone()[0], 1, 'keine zweite Firma')
        with self.assertRaisesRegex(ValueError, 'mehrere offene Chancen'):
            create_meeting(self.conn, {'lead_id': self.lead, 'title': 'Termin', 'starts_at': '2026-12-01T10:00'})
        create_meeting(self.conn, {'lead_id': self.lead, 'title': 'Portal-Workshop', 'starts_at': '2026-12-02T10:00', 'opportunity_id': b['id']})
        a2, b2 = self.chance(a['id']), self.chance(b['id'])
        self.assertEqual((a2['stage'], b2['stage']), ('bedarf', 'termin'))
        self.assertEqual(([m['title'] for m in a2['meetings']], [m['title'] for m in b2['meetings']]), ([], ['Portal-Workshop']))
        self.assertEqual(self.stage(), 'termin', 'Firmenphase folgt der weitesten offenen Chance')
        with self.assertRaisesRegex(ValueError, 'erste Chance'):
            ch.update(self.conn, a['id'], {'problem': 'anders'})
        ch.update(self.conn, b['id'], {'problem': 'Statusanfragen und Rückfragen', 'next_step': 'Prozess aufnehmen', 'next_date': '2026-12-03'})
        self.assertEqual(self.chance(b['id'])['next_step'], 'Prozess aufnehmen')
        self.assertEqual(self.chance(a['id'])['next_step'], '')

    def test_loss_of_one_chance_ends_no_other_and_no_invoice(self):
        from sales_tool import accounting as acc
        acc.save_settings(self.conn, {'company_name': 'Fiktiv Studio', 'street': 'Musterweg 1', 'zip': '70191', 'city': 'Stuttgart',
                                      'tax_number': '99/999/99999', 'iban': 'DE89370400440532013000'})
        a = ch.create(self.conn, self.lead, {'title': 'Logo'})
        b = ch.create(self.conn, self.lead, {'title': 'Software'})
        confirm_need(self.conn, self.lead)
        p = make_proposal(self.conn, {'lead_id': self.lead, 'positions': LOGO, 'tax_mode': 'regel_19', 'opportunity_id': a['id']})
        release_offer(self.conn, p['id'])
        of.set_status(self.conn, p['id'], {'status': 'angenommen'})
        inv = acc.invoice_from_proposal(self.conn, {'proposal_id': p['id'], 'mode': 'abschlag'})
        before = [dict(r) for r in self.conn.execute('SELECT id, net_cents, status FROM invoices')]
        self.assertEqual((self.chance(a['id'])['stage'], self.chance(b['id'])['stage']), ('gewonnen', 'bedarf'))
        self.assertEqual(self.stage(), 'gewonnen')
        with self.assertRaisesRegex(ValueError, 'Verlustgrund'):
            ch.update(self.conn, b['id'], {'stage': 'verloren'})
        ch.update(self.conn, b['id'], {'stage': 'verloren', 'lost_reason': 'kein_budget'})
        self.assertEqual(self.chance(a['id'])['stage'], 'gewonnen')
        self.assertEqual(self.chance(b['id'])['lost_label'], 'Kein Budget')
        self.assertEqual(self.stage(), 'gewonnen', 'Kunde bleibt Kunde')
        self.assertEqual([dict(r) for r in self.conn.execute('SELECT id, net_cents, status FROM invoices')], before)
        self.assertTrue(inv['id'])
        with self.assertRaisesRegex(ValueError, 'gewonnen'):
            ch.update(self.conn, a['id'], {'stage': 'verloren', 'lost_reason': 'preis'})

    def test_open_chance_survives_loss_of_the_other(self):
        a = ch.create(self.conn, self.lead, {'title': 'A'})
        b = ch.create(self.conn, self.lead, {'title': 'B'})
        ch.update(self.conn, b['id'], {'stage': 'angebot'})
        ch.update(self.conn, b['id'], {'stage': 'verloren', 'lost_reason': 'wettbewerber'})
        self.assertEqual(self.chance(a['id'])['stage'], 'bedarf')
        self.assertEqual(self.stage(), 'angebot', 'Firmenphase fällt durch einen Verlust nicht zurück')
        ch.update(self.conn, a['id'], {'stage': 'verloren', 'lost_reason': 'zeitpunkt', 'lost_note': 'Frühjahr'})
        row = self.conn.execute('SELECT stage, lost_reason, lost_note FROM leads WHERE id=?', (self.lead,)).fetchone()
        self.assertEqual(tuple(row), ('verloren', 'zeitpunkt', 'Frühjahr'), 'erst wenn alle Chancen verloren sind')
        ch.update(self.conn, a['id'], {'stage': 'bedarf'})  # wieder aufgenommen
        self.assertEqual(self.stage(), 'antwort')
        self.assertEqual(self.chance(a['id'])['lost_reason'], '')


class OfferLinkTests(Base):
    def test_offer_needs_choice_when_several_open_and_new_creates(self):
        p1 = make_proposal(self.conn, {'lead_id': self.lead, 'positions': LOGO, 'tax_mode': 'regel_19', 'project_label': 'Markenauftritt'})
        first = ch.list_chances(self.conn, self.lead)['chances']
        self.assertEqual([(c['title'], c['is_first'], c['source']) for c in first], [('Markenauftritt', 1, 'angebot')])
        self.assertEqual(self.stage(), 'antwort', 'mit einer offenen Chance steht die Firma mindestens bei „Rückmeldung“ – nicht bei „Angebot“')
        p2 = make_proposal(self.conn, {'lead_id': self.lead, 'positions': LOGO, 'tax_mode': 'regel_19'})
        self.assertEqual(p2['opportunity_id'], p1['opportunity_id'], 'einzige offene Chance')
        p3 = make_proposal(self.conn, {'lead_id': self.lead, 'positions': SOFT, 'tax_mode': 'regel_19', 'opportunity_id': 'neu', 'project_label': 'Werkzeug'})
        self.assertNotEqual(p3['opportunity_id'], p1['opportunity_id'])
        with self.assertRaisesRegex(ValueError, 'mehrere offene Chancen'):
            make_proposal(self.conn, {'lead_id': self.lead, 'positions': SOFT, 'tax_mode': 'regel_19'})
        other = self.conn.execute("INSERT INTO leads(company) VALUES ('Andere Fiktiv KG')").lastrowid
        with self.assertRaisesRegex(ValueError, 'andere'):
            make_proposal(self.conn, {'lead_id': other, 'positions': SOFT, 'opportunity_id': p1['opportunity_id']})
        chances = {c['id']: c for c in ch.list_chances(self.conn, self.lead)['chances']}
        self.assertEqual([x['number'] for x in chances[p1['opportunity_id']]['proposals']], [p1['number'], p2['number']])

    def test_sending_and_acceptance_move_only_their_chance(self):
        a = ch.create(self.conn, self.lead, {'title': 'A'})
        b = ch.create(self.conn, self.lead, {'title': 'B'})
        confirm_need(self.conn, self.lead)
        p = make_proposal(self.conn, {'lead_id': self.lead, 'positions': LOGO, 'tax_mode': 'regel_19', 'opportunity_id': b['id']})
        release_offer(self.conn, p['id'])
        of.set_status(self.conn, p['id'], {'status': 'gesendet_manuell'})
        self.assertEqual((self.chance(a['id'])['stage'], self.chance(b['id'])['stage']), ('bedarf', 'angebot'))
        of.set_status(self.conn, p['id'], {'status': 'angenommen'})
        self.assertEqual((self.chance(a['id'])['stage'], self.chance(b['id'])['stage']), ('bedarf', 'gewonnen'))
        self.assertEqual(self.stage(), 'gewonnen')
        c = ch.create(self.conn, self.lead, {'title': 'Folgeprojekt'})
        self.assertEqual(c['stage'], 'bedarf')
        self.assertEqual(self.stage(), 'gewonnen', 'neue Chance stuft den Kunden nicht zurück')

    def test_firm_marked_lost_closes_open_chances_via_api(self):
        a = ch.create(self.conn, self.lead, {'title': 'A'})
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            def call(method, path, body=None):
                c = HTTPConnection('127.0.0.1', server.server_port, timeout=10)
                c.request(method, path, body=json.dumps(body) if body is not None else None,
                          headers={'Content-Type': 'application/json', 'Origin': f'http://127.0.0.1:{server.server_port}'})
                r = c.getresponse()
                out = (r.status, json.loads(r.read() or b'null'))
                c.close()
                return out
            st, created = call('POST', f'/api/leads/{self.lead}/chances', {'title': 'B', 'problem': 'Neues Anliegen'})
            self.assertEqual(st, 201)
            st, lst = call('GET', f'/api/leads/{self.lead}/chances')
            self.assertEqual((st, lst['open']), (200, 2))
            self.assertIn('kein_budget', lst['lost_reasons'])
            st, err = call('PATCH', f"/api/chances/{created['id']}", {'stage': 'unbekannt'})
            self.assertEqual(st, 400)
            st, _ = call('PATCH', f'/api/leads/{self.lead}', {'stage': 'verloren', 'lost_reason': 'kein_bedarf'})
            self.assertEqual(st, 200)
            st, lst = call('GET', f'/api/leads/{self.lead}/chances')
            self.assertEqual({c['stage'] for c in lst['chances']}, {'verloren'})
            self.assertEqual({c['lost_reason'] for c in lst['chances']}, {'kein_bedarf'})
            self.assertEqual(a['is_first'], 1)
        finally:
            server.shutdown()
            server.server_close()

    def test_blocked_firm_gets_no_chance(self):
        self.conn.execute("UPDATE leads SET stage='gesperrt', permission='nicht_kontaktieren' WHERE id=?", (self.lead,))
        with self.assertRaisesRegex(ValueError, 'Gesperrte'):
            ch.create(self.conn, self.lead, {'title': 'X'})


class MigrationTests(unittest.TestCase):
    def test_existing_data_gets_exactly_one_first_chance(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / 'kopie.sqlite3')
            raw = sqlite3.connect(db)
            raw.executescript((ROOT / 'tests' / 'fixtures' / 'migration' / 'v1_6.sql').read_text(encoding='utf-8'))
            raw.execute('PRAGMA user_version = 15')  # Stand der Vorlage (siehe Kopfzeile der Datei)
            leads = {name: raw.execute("INSERT INTO leads(company, stage, offer, next_step) VALUES (?,?,?,?)", (name, st, off, step)).lastrowid
                     for name, st, off, step in (('Recherche Fiktiv', 'recherche', 'conversion', ''), ('Termin Fiktiv', 'termin', 'brand', 'Termin vorbereiten'),
                                                ('Kunde Fiktiv', 'gewonnen', 'pilot', ''), ('Verloren Fiktiv', 'verloren', 'portal', ''),
                                                ('Angebot Fiktiv', 'kontakt', 'automation', 'Angebot nachfassen'))}
            cust = json.dumps({'project_label': 'Altes Angebot', 'net_eur': 1000.0, 'tax_mode': 'regel_19'})
            raw.execute("INSERT INTO proposals(lead_id, status, internal_json, customer_json) VALUES (?, 'angenommen', '{}', ?)", (leads['Kunde Fiktiv'], cust))
            raw.execute("INSERT INTO proposals(lead_id, status, internal_json, customer_json) VALUES (?, 'entwurf', '{}', ?)", (leads['Angebot Fiktiv'], cust))
            raw.execute("INSERT INTO meetings(lead_id, title, starts_at) VALUES (?, 'Erstgespräch', '2026-10-01T10:00')", (leads['Termin Fiktiv'],))
            raw.commit()
            raw.close()
            prepare_database(db)
            prepare_database(db)  # zweiter Start: nichts doppelt
            with connect(db) as conn:
                self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
                rows = {r['company']: dict(r) for r in conn.execute('SELECT o.*, l.company FROM opportunities o JOIN leads l ON l.id=o.lead_id')}
                self.assertNotIn('Recherche Fiktiv', rows)
                self.assertIn('Altbestand Maschinenbau GmbH', rows)  # Firma aus der Vorlage mit Bedarfsanalyse
                self.assertEqual(len(rows), 5)
                self.assertEqual({k: v['stage'] for k, v in rows.items() if k != 'Altbestand Maschinenbau GmbH'},
                                 {'Termin Fiktiv': 'termin', 'Kunde Fiktiv': 'gewonnen', 'Verloren Fiktiv': 'verloren', 'Angebot Fiktiv': 'angebot'})
                self.assertTrue(all(v['is_first'] == 1 and v['source'] == 'bestand' for v in rows.values()))
                self.assertEqual(rows['Termin Fiktiv']['title'], 'Brand- & Design-System')
                self.assertEqual(rows['Termin Fiktiv']['next_step'], 'Termin vorbereiten')
                self.assertEqual(rows['Verloren Fiktiv']['lost_reason'], 'sonstiges')
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM proposals WHERE opportunity_id IS NULL').fetchone()[0], 0)
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM meetings WHERE opportunity_id IS NULL').fetchone()[0], 0)
                stages = {r['company']: r['stage'] for r in conn.execute('SELECT company, stage FROM leads')}
                self.assertEqual(stages['Angebot Fiktiv'], 'kontakt', 'Bestand: Firmenphase wird durch die Migration nicht verändert')
                self.assertEqual(json.loads(conn.execute("SELECT customer_json FROM proposals WHERE status='angenommen'").fetchone()[0])['net_eur'], 1000.0)


class WiringTests(unittest.TestCase):
    def test_script_served_shipped_and_ordered(self):
        from sales_tool.server import STATIC_FILES
        from tools.build_release import RELEASE_ADDITIONS
        html = (ROOT / 'sales_tool' / 'public' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('/chances.js', STATIC_FILES)
        self.assertIn('sales_tool/chances.py', RELEASE_ADDITIONS)
        self.assertIn('sales_tool/public/chances.js', RELEASE_ADDITIONS)
        self.assertLess(html.index('<script src="/salesint.js"'), html.index('<script src="/chances.js"'))
        self.assertLess(html.index('<script src="/chances.js"'), html.index('<script src="/nav.js"'))
        self.assertEqual(html.count('data-ch-select='), 2)  # Angebot und Termin


if __name__ == '__main__':
    unittest.main()
