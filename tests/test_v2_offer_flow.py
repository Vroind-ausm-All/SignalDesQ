"""2.0.0-dev17: P0-Paket aus den Ergänzungen zum Produktreview (13.11.2026).

Abnahme:
- M35 Versandfassung: Ohne Freigabe trägt der Export sichtbar „Entwurf“; Freigabe nur nach bestandenen Prüfungen und vier
  bestätigten Prüfpunkten; danach Export ohne Entwurfshinweis mit Stand-Kennung. Versand und Zusage nur für einen
  freigegebenen Stand, gespeichert mit Zeitpunkt, Weg und Stand; keine internen Werte im Kundendokument.
- M36 Übergang nach Annahme: Startaufgaben werden vorgeschlagen (nicht still angelegt); offene Nachfassaufgaben zu diesem
  Angebot lassen sich bewusst beenden; erneutes Klicken erzeugt keine Duplikate; andere Aufgaben bleiben unberührt.
- M27 Begriffe: Website-Werte heißen „Auffällig“ und „Akquise-Priorität“, nicht Qualität; unbekannte Branche/Größe zählt nie
  als schlechte Profilnähe.
- Migration: ältere Datenbanken bekommen die neuen Spalten; vorhandene Angebote bleiben unverändert und gelten als Entwurf.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import datetime as dt
import json
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5_helpers import confirm_need  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import offer_flow as of  # noqa: E402
from sales_tool import website_scorer as ws  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.sales_workspace import customer_markdown, make_proposal  # noqa: E402
from sales_tool.server import SCHEMA_VERSION, prepare_database  # noqa: E402
from sales_tool.workday import ContactLocked  # noqa: E402

PUBLIC = Path(__file__).resolve().parent.parent / 'sales_tool' / 'public'
ALL = list(of.CONFIRMATIONS)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'o.sqlite3')
        prepare_database(self.db)
        self.conn = connect(self.db)
        self.lead = self.conn.execute("INSERT INTO leads(company, stage) VALUES ('Versand Fiktiv GmbH', 'termin')").lastrowid
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def offer(self, positions=None, tax='regel_19'):
        return make_proposal(self.conn, {'lead_id': self.lead, 'positions': positions or [{'service': 'logo', 'size': 'M'}, {'service': 'software', 'size': 'S'}],
                                         'tax_mode': tax})

    def md(self, pid):
        row = self.conn.execute('SELECT * FROM proposals WHERE id=?', (pid,)).fetchone()
        return customer_markdown(json.loads(row['customer_json']), of.release_info(row))

    def tasks(self, done=None):
        sql = 'SELECT title FROM tasks WHERE lead_id=?' + ('' if done is None else f' AND done={int(done)}')
        return [r['title'] for r in self.conn.execute(sql, (self.lead,))]


class ReleaseTests(Base):
    def test_draft_until_released_then_versioned(self):
        p = self.offer()
        md = self.md(p['id'])
        self.assertIn('ENTWURF – nicht zum Versand freigegeben', md)
        self.assertIn('Angebotsentwurf', md)
        st = of.state(self.conn, p['id'])
        self.assertFalse(st['ready'])
        self.assertEqual([c['key'] for c in st['checks'] if not c['ok']], ['bedarf'])
        self.assertTrue(st['filename'].startswith('ENTWURF_Angebot_AN-'))
        with self.assertRaisesRegex(ValueError, 'Bedarf'):
            of.release(self.conn, p['id'], {'confirm': ALL})
        confirm_need(self.conn, self.lead)
        with self.assertRaisesRegex(ValueError, 'Prüfpunkte'):
            of.release(self.conn, p['id'], {'confirm': ALL[:3]})
        st = of.release(self.conn, p['id'], {'confirm': ALL})
        self.assertTrue(st['released'])
        self.assertRegex(st['stand'], r'^[0-9a-f]{8}$')
        self.assertEqual(st['filename'], f"Angebot_{p['number']}_Stand-{st['stand']}.md")
        md = self.md(p['id'])
        self.assertNotIn('ENTWURF', md)
        self.assertNotIn('Angebotsentwurf', md)
        self.assertIn(f"Versandfassung · Stand {st['stand']}", md)
        for secret in ('€/h', 'Stundensatz', 'catalog_version', 'open_points', 'Puffer'):
            self.assertNotIn(secret, md)
        again = of.release(self.conn, p['id'], {'confirm': ALL})  # zweiter Klick ändert nichts
        self.assertEqual((again['stand'], again['released_at']), (st['stand'], st['released_at']))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM activities WHERE lead_id=? AND detail LIKE 'Versandfassung%'", (self.lead,)).fetchone()[0], 1)

    def test_open_tax_status_blocks_release(self):
        p = self.offer(tax='offen')
        confirm_need(self.conn, self.lead)
        with self.assertRaisesRegex(ValueError, 'Steuerstatus'):
            of.release(self.conn, p['id'], {'confirm': ALL})

    def test_changed_document_after_release_falls_back_to_draft(self):
        p = self.offer()
        confirm_need(self.conn, self.lead)
        of.release(self.conn, p['id'], {'confirm': ALL})
        self.conn.execute("UPDATE proposals SET customer_json=replace(customer_json, 'Logogestaltung', 'Logo neu') WHERE id=?", (p['id'],))
        self.assertTrue(of.state(self.conn, p['id'])['stand_changed'])
        self.assertIn('ENTWURF', self.md(p['id']))

    def test_internal_values_are_detected(self):
        p = self.offer()
        confirm_need(self.conn, self.lead)
        row = self.conn.execute('SELECT * FROM proposals WHERE id=?', (p['id'],)).fetchone()
        cust = json.loads(row['customer_json'])
        cust['positions'][0]['effective_hourly'] = 80
        self.conn.execute('UPDATE proposals SET customer_json=? WHERE id=?', (json.dumps(cust), p['id']))
        bad = [c for c in of.state(self.conn, p['id'])['checks'] if not c['ok']]
        self.assertEqual([c['key'] for c in bad], ['intern'])
        self.assertIn('effective_hourly', bad[0]['detail'])


class StatusTests(Base):
    def released(self):
        p = self.offer()
        confirm_need(self.conn, self.lead)
        of.release(self.conn, p['id'], {'confirm': ALL})
        return p

    def test_send_and_decide_only_for_released_stand(self):
        p = self.offer()
        confirm_need(self.conn, self.lead)
        with self.assertRaisesRegex(ContactLocked, 'Versandfassung'):
            of.set_status(self.conn, p['id'], {'status': 'gesendet_manuell'})
        with self.assertRaisesRegex(ContactLocked, 'Versandfassung'):
            of.set_status(self.conn, p['id'], {'status': 'angenommen'})
        st = of.release(self.conn, p['id'], {'confirm': ALL})
        yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        r = of.set_status(self.conn, p['id'], {'status': 'gesendet_manuell', 'channel': 'post', 'date': yesterday})
        self.assertIn('nichts gesendet', r['notice'])
        s = of.state(self.conn, p['id'])
        self.assertEqual((s['sent_at'], s['sent_channel'], s['sent_stand']), (yesterday, 'post', st['stand']))
        self.assertTrue(of.set_status(self.conn, p['id'], {'status': 'gesendet_manuell'})['unchanged'])
        self.assertEqual(len([t for t in self.tasks(False) if f"(#{p['id']})" in t]), 1)
        with self.assertRaisesRegex(ValueError, 'Zukunft'):
            of.set_status(self.conn, p['id'], {'status': 'angenommen', 'date': (dt.date.today() + dt.timedelta(days=2)).isoformat()})
        with self.assertRaisesRegex(ValueError, 'Weg'):
            of.set_status(self.conn, p['id'], {'status': 'angenommen', 'channel': 'brieftaube'})
        r = of.set_status(self.conn, p['id'], {'status': 'angenommen', 'channel': 'bestellung', 'person': 'Frau Beispiel', 'note': 'Bestellnr. 4711'})
        s = of.state(self.conn, p['id'])
        self.assertEqual((s['status'], s['decision_channel'], s['decision_person'], s['decision_note']), ('angenommen', 'bestellung', 'Frau Beispiel', 'Bestellnr. 4711'))
        act = self.conn.execute("SELECT detail FROM activities WHERE lead_id=? AND activity_type='abschluss'", (self.lead,)).fetchone()['detail']
        self.assertIn(st['stand'], act)
        self.assertIn('Frau Beispiel', act)
        self.assertEqual(self.conn.execute('SELECT stage FROM leads WHERE id=?', (self.lead,)).fetchone()['stage'], 'gewonnen')
        self.assertTrue(r['start']['suggestions'])
        with self.assertRaisesRegex(ValueError, 'nicht zurücknehmen'):
            of.set_status(self.conn, p['id'], {'status': 'gesendet_manuell'})
        with self.assertRaisesRegex(ValueError, 'nicht zurücknehmen'):
            of.set_status(self.conn, p['id'], {'status': 'abgelehnt'})

    def test_draft_can_not_be_reset_after_sending(self):
        p = self.released()
        of.set_status(self.conn, p['id'], {'status': 'gesendet_manuell'})
        with self.assertRaisesRegex(ValueError, 'nicht zurücknehmen'):
            of.set_status(self.conn, p['id'], {'status': 'entwurf'})


class StartTests(StatusTests):
    def test_acceptance_proposes_start_and_ends_followups_without_duplicates(self):
        p = self.released()
        of.set_status(self.conn, p['id'], {'status': 'gesendet_manuell'})
        self.conn.execute("INSERT INTO tasks(lead_id, title, due_date) VALUES (?, ?, '')", (self.lead, f"Angebot {p['number']} telefonisch nachfassen"))
        self.conn.execute("INSERT INTO tasks(lead_id, title, due_date) VALUES (?, 'Rechnungsadresse erfragen', '')", (self.lead,))
        self.conn.commit()
        before = set(self.tasks())
        r = of.set_status(self.conn, p['id'], {'status': 'angenommen'})
        self.assertEqual(set(self.tasks()), before, 'Zusage legt nichts still an')
        plan = r['start']
        keys = [s['key'] for s in plan['suggestions']]
        self.assertEqual(keys, ['bestaetigung', 'startgespraech', 'material', 'zugaenge', 'ueberblick', 'zwischenstand'])  # Logo + Software
        self.assertTrue(all(s['title'].startswith(p['number']) for s in plan['suggestions']))
        follow = {f['title'] for f in plan['followups']}
        self.assertEqual(follow, {f"Angebot {p['number']} nachfassen (#{p['id']}) – zulässigen Weg prüfen: Entscheidung erfragen", f"Angebot {p['number']} telefonisch nachfassen"})
        self.assertTrue(plan['next_step'].startswith(f"Projektstart {p['number']}"))
        out = of.start(self.conn, p['id'], {'create': ['bestaetigung', 'startgespraech', 'zugaenge'], 'close': [f['id'] for f in plan['followups']]})
        self.assertEqual((out['created'], out['closed']), (3, 2))
        again = of.start(self.conn, p['id'], {'create': ['bestaetigung', 'startgespraech', 'zugaenge'], 'close': []})
        self.assertEqual(again['created'], 0, 'erneuter Klick legt nichts doppelt an')
        open_titles = self.tasks(False)
        self.assertIn('Rechnungsadresse erfragen', open_titles, 'andere Aufgaben bleiben unberührt')
        self.assertFalse([t for t in open_titles if 'nachfass' in t or 'Rückfrage' in t])
        self.assertEqual(len([t for t in open_titles if t.startswith(p['number'])]), 3)
        self.assertEqual(out['followups'], [])
        with self.assertRaisesRegex(ValueError, 'Unbekannte'):
            of.start(self.conn, p['id'], {'create': ['raumfahrt']})
        other = self.conn.execute("INSERT INTO tasks(lead_id, title, due_date) VALUES (?, 'Fremde Aufgabe', '')", (self.lead,)).lastrowid
        with self.assertRaisesRegex(ValueError, 'Nachfassaufgaben'):
            of.start(self.conn, p['id'], {'close': [other]})

    def test_rejection_only_ends_followups(self):
        p = self.released()
        of.set_status(self.conn, p['id'], {'status': 'gesendet_manuell'})
        r = of.set_status(self.conn, p['id'], {'status': 'abgelehnt', 'note': 'Budget verschoben'})
        self.assertEqual(r['start']['suggestions'], [])
        self.assertEqual(len(r['start']['followups']), 1)
        with self.assertRaisesRegex(ValueError, 'angenommenem'):
            of.start(self.conn, p['id'], {'create': ['bestaetigung']})
        self.assertEqual(of.start(self.conn, p['id'], {'close': [r['start']['followups'][0]['id']]})['closed'], 1)

    def test_start_needs_a_decision(self):
        p = self.released()
        with self.assertRaisesRegex(ValueError, 'Zusage'):
            of.start(self.conn, p['id'], {'create': ['bestaetigung']})

    def test_media_only_offer_suggests_no_software_access_task(self):
        p = self.offer(positions=[{'service': 'logo', 'size': 'S'}])
        confirm_need(self.conn, self.lead)
        of.release(self.conn, p['id'], {'confirm': ALL})
        keys = [s['key'] for s in of.set_status(self.conn, p['id'], {'status': 'angenommen'})['start']['suggestions']]
        self.assertIn('material', keys)
        self.assertNotIn('zugaenge', keys)


class MigrationTests(unittest.TestCase):
    def test_old_database_gets_columns_and_keeps_offers(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / 'alt.sqlite3')
            raw = sqlite3.connect(db)
            raw.executescript((Path(__file__).parent / 'fixtures' / 'migration' / 'v1_6.sql').read_text(encoding='utf-8'))
            raw.execute("INSERT INTO leads(company) VALUES ('Alt Fiktiv KG')")
            cust = {'project_label': 'Alt', 'goal': 'Ziel', 'included': ['x'], 'excluded': [], 'weeks': '2 Wochen', 'revision_rounds': 2,
                    'net_eur': 1000.0, 'total_eur': 1190.0, 'tax_mode': 'regel_19', 'tax_note': 'zzgl. USt.', 'payment_plan': 'p',
                    'change_requests': 'c', 'guarantee': 'g'}
            raw.execute("INSERT INTO proposals(lead_id, status, internal_json, customer_json, number) VALUES (1, 'gesendet_manuell', '{}', ?, 'AN-2025-0001')",
                        (json.dumps(cust),))
            raw.commit()
            raw.close()
            prepare_database(db)
            with connect(db) as conn:
                self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
                row = conn.execute('SELECT * FROM proposals WHERE id=1').fetchone()
                self.assertEqual((row['status'], row['released_at'], row['sent_at']), ('gesendet_manuell', '', ''))
                self.assertEqual(json.loads(row['customer_json']), cust)
                st = of.state(conn, 1)
                self.assertFalse(st['released'])
                self.assertIn('ENTWURF', customer_markdown(cust, of.release_info(row)))


class WordingTests(unittest.TestCase):
    """M27: Website-Werte sind Auffälligkeiten bzw. eine Akquise-Priorität – keine Qualitätsnote; unbekannt ≠ schlecht."""

    def test_unknown_profile_is_open_not_low(self):
        cap = {'renderer': 'html', 'pages': [], 'errors': []}
        known = ws.score(cap, {'industry': 'Sonstige', 'employees': 0, 'signal_type': 'kein_signal'}, ws.DEFAULT_CONFIG, {'pilot'})
        unknown = ws.score(cap, {'industry': '', 'employees': 0, 'signal_type': 'kein_signal'}, ws.DEFAULT_CONFIG, {'pilot'})
        self.assertIsNotNone(known['fit'])
        self.assertIsNone(unknown['fit'])
        self.assertIn('Profilnähe offen', unknown['fit_basis'])
        partial = ws.score(cap, {'industry': '', 'employees': 80, 'signal_type': 'kein_signal'}, ws.DEFAULT_CONFIG, {'pilot'})
        self.assertIn('Branche unbekannt', partial['fit_basis'])
        self.assertGreater(partial['fit'], 25, 'fehlende Branche zieht die Profilnähe nicht nach unten')

    def test_labels_say_what_the_values_are(self):
        scoring = (PUBLIC / 'scoring.js').read_text(encoding='utf-8')
        html = (PUBLIC / 'index.html').read_text(encoding='utf-8')
        report = (PUBLIC / 'report.js').read_text(encoding='utf-8')
        for old in ("tile('Gesamt (Priorität)'", "tile('Design & UX'", "'Passung zur Agentur'", 'Gewicht Potenzial'):
            self.assertNotIn(old, scoring)
        for new in ('Akquise-Priorität', 'Auffällig: Design & UX', 'Profilnähe', 'zählt nie als schlecht', 'keine Qualitätsnote'):
            self.assertIn(new, scoring + html)
        self.assertNotIn("<th>GESAMT</th><th>DESIGN</th>", html)
        self.assertIn('Auffällig: Design & UX', report)
        self.assertNotIn("['overall', 'Gesamt']", report)
        self.assertNotIn('Qualität', re.sub(r'Datenqualität|Qualitätsnote', '', scoring + report))
        self.assertIn('keine Qualitätsnote', ws.summarize({'findings': [], 'overall': 50}, {'renderer': 'playwright', 'errors': []},
                                                          {'permission': 'unbekannt'}, {})['disclaimer'])


class UiWiringTests(unittest.TestCase):
    def test_offerflow_script_is_served_and_shipped(self):
        from sales_tool.server import STATIC_FILES
        from tools.build_release import RELEASE_ADDITIONS
        html = (PUBLIC / 'index.html').read_text(encoding='utf-8')
        self.assertIn('/offerflow.js', STATIC_FILES)
        self.assertIn('sales_tool/public/offerflow.js', RELEASE_ADDITIONS)
        self.assertIn('sales_tool/offer_flow.py', RELEASE_ADDITIONS)
        self.assertLess(html.index('<script src="/quotes.js"'), html.index('<script src="/offerflow.js"'))
        js = (PUBLIC / 'offerflow.js').read_text(encoding='utf-8')
        self.assertNotIn("$$('[data-of", js)  # $$ nimmt hier nur einen Selektor


if __name__ == '__main__':
    unittest.main()
