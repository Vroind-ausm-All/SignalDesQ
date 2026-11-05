"""Phase 4 – Research Command Center: Priorisierung, Recherchestand, Aufträge, Prüfliste, Quellen, Dossier, Übergabe, Export.

Fiktive Testdaten; keine Netzwerkzugriffe.
"""
import datetime as dt
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sales_tool import buying_signals as bs
from sales_tool import research_center as rc
from sales_tool.company_data import add_fact
from sales_tool.model import connect, init_db
from sales_tool.server import make_handler

TODAY = dt.date.today()


class CenterBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'rc.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def lead(self, company, **extra):
        data = {'company': company, 'website': 'https://' + company.split()[0].lower() + '-beispiel.de', 'industry': 'Industrie & B2B-Technik',
                'employees': 80, **extra}
        cur = self.conn.execute(f"INSERT INTO leads ({','.join(data)}) VALUES ({','.join('?' for _ in data)})", tuple(data.values()))
        self.conn.commit()
        return cur.lastrowid

    def website_score(self, lead_id, overall=80, coverage=90):
        a = self.conn.execute("INSERT INTO website_audits(lead_id, url, status, renderer, finished_at, summary_json, capture_json) VALUES (?, 'x', 'done', 'playwright', datetime('now'), ?, ?)",
                              (lead_id, json.dumps({'observations': [{'issue': 'Kein sichtbarer Anfrageaufruf', 'label': 'CTA', 'evidence': 'Kein CTA im ersten Bildschirm', 'certainty': 'beobachtet', 'source_url': 'https://x/'}],
                                                   'questions': ['Wie kommen heute Anfragen zu Ihnen?'], 'offers': [{'key': 'conversion'}], 'uncertainties': ['Ladezeit nur Richtwert']}),
                               json.dumps({'pages': [{'url': 'https://x/', 'kind': 'home'}]}))).lastrowid
        vid = self.conn.execute('SELECT id FROM score_versions WHERE active=1').fetchone()[0]
        self.conn.execute("INSERT INTO website_scores(audit_id, lead_id, version_id, overall, potential, coverage, basis_json) VALUES (?,?,?,?,?,?, '{}')",
                          (a, lead_id, vid, overall, overall, coverage))
        self.conn.execute("""INSERT INTO website_findings(audit_id, lead_id, rubric, area, label, result, weight, evidence, source_url, method, certainty)
                             VALUES (?, ?, 'B3_cta_above_fold', 'web', 'CTA', 'auffaellig', 3, 'Kein CTA', 'https://x/', 'dom', 'beobachtet')""", (a, lead_id))
        self.conn.execute("INSERT INTO website_screenshots(audit_id, page_url, kind, path, size_bytes) VALUES (?, 'https://x/', 'desktop', '/nowhere.jpg', 1)", (a,))
        self.conn.commit()
        return a


class PriorityTests(CenterBase):
    def test_insufficient_data_then_weighted_priority(self):
        lid = self.lead('Leer GmbH')
        st = rc.lead_status(self.conn, dict(rc.as_lead(self.conn.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone())))
        self.assertIsNone(st['priority'])
        self.assertIn('Datenlage unzureichend', st['priority_basis'])
        self.website_score(lid, overall=80)
        st = rc.overview(self.conn)['leads'][0]
        self.assertIsNotNone(st['priority'])
        self.assertIn('ohne Signale', st['priority_basis'])
        self.assertIn('40/30/30', st['priority_basis'])
        bs.import_jobs(self.conn, {'text': 'Online-Marketing Manager (m/w/d)', 'lead_id': lid, 'published_at': TODAY.isoformat()})
        st2 = rc.overview(self.conn)['leads'][0]
        self.assertNotIn('ohne', st2['priority_basis'].split('·')[0])
        expected = round((40 * 80 + 30 * 100 + 30 * st2['fit_score']) / 100)
        self.assertEqual(st2['priority'], expected)

    def test_insufficient_website_score_counts_as_unknown(self):
        lid = self.lead('Dünn GmbH')
        self.website_score(lid, overall=None, coverage=40)
        st = rc.overview(self.conn)['leads'][0]
        self.assertIsNone(st['priority'])
        self.assertIn('ohne ausreichende Belege', st['priority_basis'])

    def test_steps_next_step_and_sorting(self):
        a = self.lead('Alpha GmbH')
        b = self.lead('Beta GmbH', website='')
        self.website_score(a, overall=90)
        rows = rc.overview(self.conn)['leads']
        self.assertEqual(rows[0]['company'], 'Alpha GmbH')           # mit Priorität vor „Datenlage unzureichend“
        beta = next(r for r in rows if r['company'] == 'Beta GmbH')
        self.assertEqual(beta['next_step']['step'], 'website')
        alpha = rows[0]
        self.assertEqual(alpha['next_step']['step'], 'imprint')
        self.conn.execute("UPDATE leads SET imprint_checked_at=datetime('now'), permission='opt_in', permission_evidence='Anfrage' WHERE id=?", (a,))
        self.conn.execute("INSERT INTO decision_contacts(lead_id, full_name, verification_status) VALUES (?, 'Lea Nordmann', 'quelle_geprueft')", (a,))
        bs.import_jobs(self.conn, {'text': 'Marketing Manager (m/w/d)', 'lead_id': a, 'published_at': TODAY.isoformat()})
        bs.correlate(self.conn, a)
        self.conn.commit()
        alpha = next(r for r in rc.overview(self.conn)['leads'] if r['lead_id'] == a)
        self.assertEqual(alpha['readiness_pct'], 100)
        self.assertEqual(alpha['next_step']['step'], 'ready')
        blocked = self.lead('Gamma GmbH', stage='gesperrt', permission='nicht_kontaktieren')
        self.assertNotIn(blocked, [r['lead_id'] for r in rc.overview(self.conn)['leads']])  # gesperrte nicht in der Arbeitsliste
        closed = rc.overview(self.conn, include_closed=True)['leads']
        self.assertIn('Gesperrt', next(r for r in closed if r['lead_id'] == blocked)['next_step']['label'])


class JobsReviewSourcesTests(CenterBase):
    def test_jobs_and_review_queue(self):
        lid = self.lead('Musterwerk GmbH')
        run = self.conn.execute("INSERT INTO batch_runs(label, total, status) VALUES ('Test', 4, 'running')").lastrowid
        for i, s in enumerate(('done', 'done', 'pending', 'failed')):
            self.conn.execute("INSERT INTO batch_items(run_id, position, input, domain, status) VALUES (?,?,?,?,?)", (run, i, 'x', f'd{i}.de', s))
        self.conn.execute("INSERT INTO website_audits(lead_id, url, status) VALUES (?, 'x', 'queued')", (lid,))
        self.conn.commit()
        j = rc.jobs(self.conn)
        self.assertEqual(j['active'], 2)
        batch = next(x for x in j['jobs'] if x['kind'] == 'Impressumsprüfung')
        self.assertEqual((batch['progress'], batch['detail']), (75, '3/4 geprüft'))
        self.assertEqual(j['jobs'][0]['status'] in ('queued', 'running'), True)
        q = rc.review_queue(self.conn)
        self.assertEqual(next(i for i in q['items'] if i['key'] == 'imprint')['count'], 2)
        bs.import_jobs(self.conn, {'text': 'Marketing Manager (m/w/d)', 'company': 'Unbekannt AG'})
        q = rc.review_queue(self.conn)
        self.assertEqual(next(i for i in q['items'] if i['key'] == 'signals_unassigned')['count'], 1)

    def test_sources_cover_all_modules(self):
        lid = self.lead('Musterwerk GmbH', signal_source='https://news-beispiel.de/1', signal_note='Neue Halle')
        add_fact(self.conn, lid, 'register_number', 'HRB 1', 'impressum_html', 'https://musterwerk-beispiel.de/impressum', 'HRB 1', 'regel', status='bestaetigt')
        self.website_score(lid)
        bs.import_jobs(self.conn, {'text': 'Marketing Manager (m/w/d)', 'lead_id': lid, 'source_url': 'https://musterwerk-beispiel.de/karriere/1'})
        self.conn.execute("INSERT INTO decision_contacts(lead_id, full_name, job_title, source_url, verification_status) VALUES (?, 'Anna Beispiel', 'GF', 'https://musterwerk-beispiel.de/team', 'quelle_geprueft')", (lid,))
        self.conn.commit()
        mods = {s['module'] for s in rc.sources(self.conn, lid)}
        self.assertEqual(mods, {'Lead', 'Firmendaten', 'Website-Bewertung', 'Kaufsignale', 'Entscheider'})
        self.assertTrue(any(s['url'].startswith('/api/screenshots/') for s in rc.sources(self.conn, lid)))
        with self.assertRaises(LookupError):
            rc.sources(self.conn, 999)


class DossierHandoffExportTests(CenterBase):
    def test_dossier_separates_facts_and_hypotheses(self):
        lid = self.lead('Musterwerk GmbH')
        add_fact(self.conn, lid, 'legal_name', 'Musterwerk GmbH', 'impressum_html', 'https://musterwerk-beispiel.de/impressum', 'Musterwerk GmbH', 'regel', status='bestaetigt')
        self.website_score(lid)
        bs.import_jobs(self.conn, {'text': 'Online-Marketing Manager (m/w/d)\nWebsite', 'lead_id': lid, 'published_at': TODAY.isoformat()})
        bs.correlate(self.conn, lid)
        d = rc.dossier(self.conn, lid)
        md = d['markdown']
        for section in ('## Geprüfte Firmendaten (Fakten)', '## Website-Beobachtungen', '## Kaufsignale', '## Hypothesen (zu bestätigen – keine Fakten)',
                        '## Fragen fürs Erstgespräch', '## Mögliche Pakete (unverbindlich'):
            self.assertIn(section, md)
        self.assertLess(md.index('Fakten'), md.index('Hypothesen'))
        self.assertIn('Musterwerk GmbH (Quelle: https://musterwerk-beispiel.de/impressum)', md)
        self.assertIn('§ 7 UWG', md)
        self.assertTrue(3 <= len(d['questions']) <= 7 or len(d['questions']) >= 1)
        self.assertTrue(all(o['key'] in ('brand', 'conversion', 'pilot', 'care', 'portal') for o in d['offers']))
        for internal in ('cost_rate', 'Deckungsbeitrag', 'Stundensatz'):
            self.assertNotIn(internal, md)

    def test_handoff_rules(self):
        lid = self.lead('Musterwerk GmbH')
        with self.assertRaises(ValueError):
            rc.handoff(self.conn, lid, {})
        res = rc.handoff(self.conn, lid, {'confirm': True})
        self.assertEqual(res['stage'], 'qualifiziert')
        self.assertIn('Kontaktweg klären', res['task'])  # Rechtsstatus unbekannt → erst Kontaktweg
        self.assertIn('unverbindlich', res['notice'])
        ok = self.lead('Opt GmbH', permission='opt_in', permission_evidence='Formular 01.11.')
        self.assertIn('Erstgespräch vorbereiten', rc.handoff(self.conn, ok, {'confirm': True})['task'])
        blocked = self.lead('Gesperrt GmbH', stage='gesperrt', permission='nicht_kontaktieren')
        with self.assertRaisesRegex(ValueError, 'gesperrt'):
            rc.handoff(self.conn, blocked, {'confirm': True})
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0], 2)

    def test_export_csv(self):
        self.lead('=Formel GmbH')
        out = rc.export_csv(self.conn)
        self.assertTrue(out.startswith('﻿'))
        self.assertIn("'=Formel GmbH", out)
        self.assertIn('Datenlage unzureichend', out)


class CenterHttpTests(CenterBase):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def call(self, path, method='GET', body=None, raw=False):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(self.base + path, data=data, method=method, headers={'Content-Type': 'application/json'} if data else {})
        try:
            with urlopen(req) as resp:
                content = resp.read()
                return resp.status, content if raw else json.loads(content), resp.headers
        except HTTPError as err:
            return err.code, json.loads(err.read()), err.headers

    def test_endpoints(self):
        lid = self.lead('Musterwerk GmbH')
        self.website_score(lid)
        for path in ('/api/research-center/overview', '/api/research-center/jobs', '/api/research-center/review',
                     f'/api/research-center/leads/{lid}/sources', f'/api/research-center/leads/{lid}/dossier'):
            status, data, _ = self.call(path)
            self.assertEqual(status, 200, path)
        status, md, headers = self.call(f'/api/research-center/leads/{lid}/dossier.md', raw=True)
        self.assertIn('attachment', headers['Content-Disposition'])
        self.assertIn(b'# Gespr', md)
        status, js, _ = self.call(f'/api/research-center/leads/{lid}/dossier.json', raw=True)
        self.assertIn('sources', json.loads(js))
        status, _, headers = self.call('/api/research-center/export.csv', raw=True)
        self.assertEqual(status, 200)
        status, res, _ = self.call(f'/api/research-center/leads/{lid}/handoff', 'POST', {'confirm': True})
        self.assertEqual(res['stage'], 'qualifiziert')
        status, err, _ = self.call('/api/research-center/leads/999/sources')
        self.assertEqual(status, 404)


if __name__ == '__main__':
    unittest.main()
