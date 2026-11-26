"""Website-Zuordnung mit mehreren Merkmalen (2.0.0-dev66).

- Eine geratene Domain ohne DNS-Eintrag ist kein Abruffehler („gibt es nicht“) – außer die Namensauflösung fehlt ganz.
- Kandidaten auch aus der E-Mail-Domain der Quelle (nur die Domain wird gespeichert, Freemail zählt nicht) und weiteren Schreibweisen.
- Abgleich über Name, Anschrift, Telefon-Prüfwert und E-Mail-Domain; Marke ↔ Firmenname wird Vorschlag, harte Gegenbelege bleiben.
- Gesperrte Firmen: keine Abgleichsmerkmale gespeichert, keine Website-Suche.
Alle Firmen, Nummern und Domains sind erfunden; Netzabfragen sind durch Attrappen ersetzt.
"""
import json
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import test_sprintB_sweep as tb  # noqa: E402

from sales_tool import imprint  # noqa: E402
from sales_tool import sweep as sw  # noqa: E402
from sales_tool.company_data import add_suppression  # noqa: E402
from sales_tool.research import homepage as hp  # noqa: E402
from sales_tool.research import osm_local  # noqa: E402
from sales_tool.research import safe_urls  # noqa: E402
from sales_tool.research.safe_urls import DomainMissing, DnsUnavailable  # noqa: E402

PHONE = '0711 5550123'  # fiktiv


def gai_error(code):
    def raiser(*a, **k):
        raise socket.gaierror(code, 'fiktiver Resolver-Fehler')
    return raiser


class DnsTests(unittest.TestCase):
    def test_nxdomain_is_domain_missing(self):
        with mock.patch.object(socket, 'getaddrinfo', gai_error(socket.EAI_NONAME)):
            with self.assertRaises(DomainMissing):
                safe_urls.resolve_public('gibt-es-nicht.example', 443)

    def test_windows_host_not_found_is_domain_missing(self):
        with mock.patch.object(socket, 'getaddrinfo', gai_error(11001)):
            with self.assertRaises(DomainMissing):
                safe_urls.resolve_public('gibt-es-nicht.example', 443)

    def test_temporary_failure_is_not_domain_missing(self):
        with mock.patch.object(socket, 'getaddrinfo', gai_error(socket.EAI_AGAIN)):
            with self.assertRaises(DnsUnavailable) as ctx:
                safe_urls.resolve_public('vielleicht.example', 443)
        self.assertNotIsInstance(ctx.exception, DomainMissing)
        self.assertNotEqual(getattr(ctx.exception, 'kind', ''), 'network', 'kein http-Rückfall bei DNS-Störung')

    def test_dns_probe_is_cached(self):
        safe_urls._DNS_STATE.update(at=-1e9, ok=True)
        calls = []
        with mock.patch.object(socket, 'getaddrinfo', lambda *a, **k: calls.append(a[0]) or gai_error(socket.EAI_NONAME)()):
            self.assertFalse(safe_urls.dns_available())
            self.assertFalse(safe_urls.dns_available())
        self.assertEqual(calls, list(safe_urls._DNS_PROBE), 'nur bekannte Namen, keine Firmendaten; Ergebnis gemerkt')
        safe_urls._DNS_STATE.update(at=-1e9, ok=True)


class HintTests(unittest.TestCase):
    def test_phone_variants_give_same_key(self):
        keys = {hp.phone_key(x) for x in ('0711 5550123', '+49 (0)711 555-0123', '0049 711 5550123', '+49 711 5550123')}
        self.assertEqual(len(keys), 1)
        self.assertNotIn('5550123', next(iter(keys)))
        self.assertEqual(hp.phone_key('123'), '', 'zu kurz – kein Prüfwert')

    def test_email_domain_only_and_no_freemail(self):
        self.assertEqual(hp.email_domain('info@huber-strom.example'), 'huber-strom.example')
        self.assertEqual(hp.email_domain('mailto:Info@WWW.Huber-Strom.example'), 'huber-strom.example')
        for addr in ('max.huber@gmail.com', 'huber@web.de', 'kein-at-zeichen', ''):
            self.assertEqual(hp.email_domain(addr), '', addr)
        h = hp.hints_from(PHONE, 'max.huber@huber-strom.example')
        text = json.dumps(h)
        self.assertNotIn('max.huber', text)
        self.assertNotIn('5550123', text)
        self.assertEqual(h['email_domains'], ['huber-strom.example'])

    def test_extra_spellings(self):
        doms = [d for d, _ in hp.candidate_domains('Elektro Müller GmbH', 'Stuttgart', {'email_domains': ['mueller-strom.example']})]
        self.assertEqual(doms[0], 'mueller-strom.example', 'E-Mail-Domain der Quelle zuerst')
        for d in ('elektro-mueller.de', 'mueller-elektro.de', 'elektro-mueller-gmbh.de', 'elektro-muller.de'):
            self.assertIn(d, doms)
        self.assertTrue(any(d.startswith('xn--') for d in doms), 'Umlaut-Domain als Punycode')
        self.assertNotIn('elektro.de', doms, 'Gattungsbegriff allein gehört keinem Betrieb')
        self.assertLessEqual(len(doms), hp.MAX_DOMAINS)
        self.assertNotIn('elektro-mueller.de', [d for d, _ in hp.candidate_domains('Elektro Müller GmbH', 'Stuttgart', rejected={'elektro-mueller.de'})])

    def test_osm_place_keeps_only_email_domain(self):
        p = osm_local.place_from_tags('node', 1, {'name': 'Huber Strom', 'craft': 'electrician', 'contact:email': 'max.huber@huber-strom.example'}, 48.7, 9.1)
        self.assertEqual(p['email_domain'], 'huber-strom.example')
        self.assertNotIn('max.huber', json.dumps(p))


def cand(**kw):
    base = {'name': '', 'zip': '', 'city': '', 'street': '', 'register_id': '', 'register_court': '', 'legal_form': ''}
    base.update(kw)
    return base


def fields(**kw):
    return {k: {'value': v} for k, v in kw.items()}


class AssessTests(unittest.TestCase):
    hints = {'phone_keys': [hp.phone_key(PHONE)]}

    def test_brand_vs_legal_name_with_address_and_phone_is_suggestion(self):
        c = cand(name='Elektro Huber', street='Hauptstraße 5', zip='70173', city='Stuttgart')
        f = fields(legal_name='Huber Elektrotechnik e.K.', street='Hauptstr. 5', zip='70173', city='Stuttgart', business_phone='+49 711 555-0123')
        status, why, sig = hp.assess(c, f, self.hints)
        self.assertEqual(status, 'wahrscheinlich')
        self.assertIn('Marke', why)
        self.assertEqual(set(sig), {'plz', 'strasse', 'telefon'})
        self.assertIsNone(hp.assess(c, f, {})[0], 'ohne Kontaktmerkmal bleibt der abweichende Name ein Gegenbeleg')

    def test_name_address_phone_is_proven_without_register(self):
        c = cand(name='Malerbetrieb Huber', street='Gartenweg 12', zip='73728', city='Esslingen')
        f = fields(legal_name='Huber Malerbetrieb e.K.', street='Gartenweg 12', zip='73728', business_phone=PHONE)
        status, why, _ = hp.assess(c, f, self.hints)
        self.assertEqual(status, 'belegt')
        self.assertIn('Telefon', why)
        f2 = fields(legal_name='Huber Malerbetrieb e.K.', street='Gartenweg 12', zip='73728', business_phone='0711 9990000')
        self.assertEqual(hp.assess(c, f2, self.hints)[0], 'wahrscheinlich', 'andere Nummer: nur Name + PLZ')

    def test_hard_counter_evidence_beats_matching_phone(self):
        c = cand(name='Huber Elektro GmbH', street='Hauptstraße 5', zip='70173', register_id='HRB 111')
        f = fields(legal_name='Huber Elektro GmbH', street='Hauptstraße 5', zip='70173', register_number='HRB 999', business_phone=PHONE)
        self.assertIsNone(hp.assess(c, f, self.hints)[0])
        c2 = cand(name='Elektro Huber GmbH', street='Hauptstraße 5', zip='70173')
        f2 = fields(legal_name='Huber Elektrotechnik AG', street='Hauptstraße 5', zip='70173', business_phone=PHONE)
        status, why, _ = hp.assess(c2, f2, self.hints)
        self.assertIsNone(status, 'andere Rechtsform bleibt Gegenbeleg, auch bei gleicher Anschrift')
        self.assertIn('anderer Firmenname', why)

    def test_email_domain_counts_like_phone(self):
        c = cand(name='Elektro Huber', street='Hauptstraße 5', zip='70173')
        f = fields(legal_name='Huber Elektrotechnik e.K.', street='Hauptstraße 5', zip='70173')
        self.assertEqual(hp.assess(c, f, {'email_domains': ['huber-strom.example']}, site_domain='huber-strom.example')[0], 'wahrscheinlich')


class FinderTests(tb.SweepBase):
    def add(self, name, **item):
        sid = self.conn.execute("INSERT INTO sweeps(label, params_json, status) VALUES ('t', '{}', 'fertig')").lastrowid
        run = sw._run_record(self.conn, 'osm', sid, {})
        ctx = {'industries': [], 'keywords': [], 'org_kinds': sw.ORG_KINDS_DEFAULT, 'operative': False}
        sw.store_items(self.conn, sid, run, 'osm', [{'name': name, 'zip': '70173', 'city': 'Stuttgart', **item}], ctx)
        return self.conn.execute('SELECT * FROM discovery_candidates WHERE name=?', (name,)).fetchone()

    def test_hints_stored_without_plain_contact_data(self):
        c = self.add('Elektro Huber', street='Hauptstraße 5', _phone=PHONE, _email='max.huber@huber-strom.example')
        stored = c['match_hints_json']
        self.assertIn('huber-strom.example', stored)
        self.assertNotIn('max.huber', stored)
        self.assertNotIn('5550123', stored)
        row = dict(c)
        self.assertFalse(any('5550123' in str(v) or 'max.huber' in str(v) for v in row.values()), 'nirgends im Treffer im Klartext')

    def test_email_domain_is_tried_first_and_brand_found(self):
        c = self.add('Elektro Huber', street='Hauptstraße 5', _phone=PHONE, _email='info@huber-strom.example')
        tried = []

        def research(domain, include_persons=True):
            tried.append(domain)
            if domain == 'huber-strom.example':
                return {'status': 'ok', 'home_url': 'https://huber-strom.example/', 'imprint_url': 'https://huber-strom.example/impressum',
                        'site_domain': 'huber-strom.example',
                        'fields': fields(legal_name='Huber Elektrotechnik e.K.', street='Hauptstr. 5', zip='70173', business_phone='+49 711 5550123')}
            raise DomainMissing('Domain existiert nicht (kein DNS-Eintrag).')
        with mock.patch.object(imprint, 'research_domain', side_effect=research):
            res = sw.find_website(self.conn, c['id'])
        self.assertEqual(tried, ['huber-strom.example'])
        self.assertEqual(res['status'], 'wahrscheinlich', 'Marke ↔ Firmenname: nur Vorschlag (Empfehlung A)')
        row = self.conn.execute('SELECT * FROM discovery_candidates WHERE id=?', (c['id'],)).fetchone()
        self.assertIn('E-Mail-Adresse der Quelle', row['website_evidence'])
        self.assertEqual(row['register_id'], '')

    def test_missing_domains_are_not_fetch_errors(self):
        c = self.add('Nirgendwo Werkstatt GmbH')
        safe_urls._DNS_STATE.update(at=1e12, ok=True)  # Namensauflösung funktioniert
        try:
            with mock.patch.object(imprint, 'research_domain', side_effect=DomainMissing('Domain existiert nicht (kein DNS-Eintrag).')):
                res = sw.find_website(self.conn, c['id'])
        finally:
            safe_urls._DNS_STATE.update(at=-1e9, ok=True)
        self.assertEqual(res['status'], 'nicht_gefunden')
        row = self.conn.execute('SELECT website_status, website_evidence FROM discovery_candidates WHERE id=?', (c['id'],)).fetchone()
        self.assertEqual(row['website_status'], 'nicht_gefunden')
        self.assertIn('gibt es nicht', row['website_evidence'])

    def test_without_dns_nothing_is_concluded(self):
        c = self.add('Nirgendwo Werkstatt GmbH')
        safe_urls._DNS_STATE.update(at=1e12, ok=False)  # z. B. Firmennetz nur mit Proxy
        try:
            with mock.patch.object(imprint, 'research_domain', side_effect=DomainMissing('Domain existiert nicht (kein DNS-Eintrag).')):
                res = sw.find_website(self.conn, c['id'])
        finally:
            safe_urls._DNS_STATE.update(at=-1e9, ok=True)
        self.assertEqual(res['status'], 'pruefung_fehlgeschlagen')
        self.assertIn('DNS', res['evidence'])

    def test_dead_source_website_falls_back_to_guesses(self):
        c = self.add('Malerbetrieb Huber', website='https://alt-huber.example', street='Gartenweg 12', _phone=PHONE)

        def research(domain, include_persons=True):
            if domain == 'malerbetrieb-huber.de':
                return {'status': 'ok', 'home_url': 'https://malerbetrieb-huber.de/', 'site_domain': 'malerbetrieb-huber.de',
                        'fields': fields(legal_name='Huber Malerbetrieb e.K.', street='Gartenweg 12', zip='70173', business_phone=PHONE)}
            raise DomainMissing('Domain existiert nicht (kein DNS-Eintrag).')
        with mock.patch.object(imprint, 'research_domain', side_effect=research):
            res = sw.find_website(self.conn, c['id'])
        self.assertEqual((res['status'], res['website']), ('belegt', 'https://malerbetrieb-huber.de'))

    def test_suppressed_company_gets_no_hints_and_no_search(self):
        add_suppression(self.conn, 'name', 'Gesperrt Elektro GmbH', 'Widerspruch')
        c = self.add('Gesperrt Elektro GmbH', _phone=PHONE, _email='info@gesperrt-elektro.example')
        self.assertEqual(c['status'], 'gesperrt')
        self.assertEqual(c['match_hints_json'], '{}', 'Datensparsamkeit: für gesperrte Firmen nichts merken')
        self.assertEqual(sw.queue_websites(self.conn, {'ids': [c['id']]}, self.db, start=False)['queued'], 0)


class MigrationTests(unittest.TestCase):
    """Schema 48 → 49: neue Spalten mit Vorgabewert, vorhandene Treffer und OSM-Einträge bleiben, Sicherung vor der Migration."""
    def test_old_database_gets_new_columns(self):
        import contextlib
        import sqlite3
        import tempfile
        from sales_tool.model import connect
        from sales_tool.server import SCHEMA_VERSION, prepare_database
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'alt.sqlite3'
            prepare_database(db)
            with contextlib.closing(sqlite3.connect(db)) as raw, raw:
                sid = raw.execute("INSERT INTO sweeps(label, params_json, status) VALUES ('alt', '{}', 'fertig')").lastrowid
                run = raw.execute("INSERT INTO discovery_runs(source, params_json) VALUES ('osm', '{}')").lastrowid
                raw.execute("INSERT INTO discovery_candidates(run_id, sweep_id, source, name, zip) VALUES (?, ?, 'osm', 'Altbestand Elektro', '70173')", (run, sid))
                raw.execute("INSERT INTO osm_places(osm_id, name, kind_key, kind, phone, import_id) VALUES ('node/1', 'Alt Elektro', 'craft', 'electrician', '0711 1', 1)")
                raw.execute('ALTER TABLE discovery_candidates DROP COLUMN match_hints_json')
                raw.execute('ALTER TABLE osm_places DROP COLUMN email_domain')
                raw.execute('PRAGMA user_version = 48')
            backup = prepare_database(db)
            self.assertTrue(backup, 'Sicherung vor der Migration')
            prepare_database(db)  # zweiter Start: nichts doppelt
            with connect(db) as conn:
                self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
                row = conn.execute("SELECT name, match_hints_json FROM discovery_candidates").fetchone()
                self.assertEqual((row['name'], row['match_hints_json']), ('Altbestand Elektro', '{}'))
                place = conn.execute("SELECT phone, email_domain FROM osm_places WHERE osm_id='node/1'").fetchone()
                self.assertEqual((place['phone'], place['email_domain']), ('0711 1', ''))


if __name__ == '__main__':
    unittest.main()
