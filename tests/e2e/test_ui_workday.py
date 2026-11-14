"""Oberflächen-Test (Chromium) – Masterplan 2.0, Sprint 6 „UI-E2E“.

Läuft NICHT in der normalen Testsuite (eigener Ordner), sondern gezielt:
    python -m unittest tests/e2e/test_ui_workday.py
Voraussetzung: Variante „browser“ (pip install --require-hashes -r requirements-lock-browser.txt; playwright install chromium).
Fehlt Playwright, wird der Test übersprungen. Eigenes Chromium: Umgebungsvariable PLAYWRIGHT_CHROMIUM_EXECUTABLE.

Abgedeckt: Beispieltag (Profil → Sichtung → Firmenakte → Bedarf → Angebot → Tagesabschluss), Firmendaten-Übertragung
mit Website-Vorschlag, gesperrte Firma, Offline-Modus, Wiederherstellen-Liste, Handyansicht. Alles fiktiv, kein Netz.
"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent))

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # Variante ohne Browser
    sync_playwright = None

import test_sprintB_sweep as tb  # noqa: E402
import test_sprintC_report as tc  # noqa: E402

from sales_tool import imprint, lead_finder as lf, lead_imprint, sweep as sw  # noqa: E402
from sales_tool.company_data import add_suppression  # noqa: E402
from sales_tool.model import connect, init_db  # noqa: E402
from sales_tool.research import jobs  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402


@unittest.skipIf(sync_playwright is None, 'Playwright nicht installiert (Variante „browser“)')
class UiWorkdayTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'ui.sqlite3'
        self.patches = [mock.patch.object(lf, 'FETCH', tb.FakeNet()), mock.patch.object(lf, 'SLEEP', lambda s: None),
                        mock.patch.object(sw, 'GLEIF_DELAY', 0), mock.patch.object(sw, 'AUTO_WEB_START', False),
                        mock.patch.object(imprint, 'FETCH', tc.FakeWeb()), mock.patch.object(imprint, 'SLEEP', lambda s: None),
                        mock.patch.object(tc.wa, 'public_url', lambda u: u), mock.patch.object(tc.wa, 'robots_allowed', lambda u: True),
                        mock.patch.object(tc.ws, 'playwright_available', lambda: False),
                        mock.patch.object(tc.ws, 'CAPTURE_FALLBACK', lambda url: tc.capture(renderer='html')),
                        mock.patch.object(lead_imprint, 'ENABLED', True)]
        for p in self.patches:
            p.start()
        tb.gm._STATE['rows'] = []
        prepare_database(self.db)
        with connect(self.db) as c:
            init_db(c)
            c.execute("INSERT INTO leads(company, stage, contact_route) VALUES ('Liegt Rum GmbH', 'kontakt', 'inbound')")
            c.execute("INSERT INTO leads(company, website, stage) VALUES ('Sperrfirma GmbH', 'https://sperrfirma.example', 'qualifiziert')")
            add_suppression(c, 'domain', 'https://sperrfirma.example', 'Widerspruch per Brief')
            res = imprint.research_domain(tc.SITE)
            sid = c.execute("INSERT INTO sweeps(label, params_json, status) VALUES ('Vorlauf', '{}', 'fertig')").lastrowid
            run = sw._run_record(c, 'osm', sid, {})
            c.execute("""INSERT INTO discovery_candidates(run_id, sweep_id, source, name, website, zip, city, status, sources_json, website_status,
                         website_evidence, imprint_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (run, sid, 'osm', 'Kesselwerk Anlagenbau', tc.SITE, '70565', 'Stuttgart', 'neu', '[{"source": "osm", "url": ""}]',
                       'wahrscheinlich', 'Vorschlag: Name und PLZ im Impressum – bitte prüfen',
                       json.dumps({'fields': res['fields'], 'imprint_url': res['imprint_url'], 'source_type': res['source_type'], 'checked_at': res['checked_at']})))
            c.commit()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        jobs.wait_idle(self.db, timeout=20)
        for p in reversed(self.patches):
            p.stop()
        tb.gm._STATE['rows'] = None
        from tmpclean import cleanup_tmp  # erst Worker beenden, dann löschen; Nachzügler-Dateien abwarten (CI dev20)
        cleanup_tmp(self.tmp)

    def test_example_day_in_browser(self):
        exe = os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None
        errors = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=exe)
            page = browser.new_page(viewport={'width': 1400, 'height': 1000})
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('console', lambda m: errors.append(m.text) if m.type == 'error' and not any(c in m.text for c in ('409', '400')) else None)
            page.on('dialog', lambda d: d.accept('Stuttgart Kabel 30 km') if d.type == 'prompt' else d.accept())
            api = lambda p, m='GET', b=None: page.evaluate(
                """async ([p, m, b]) => { const r = await fetch('/api' + p, {method: m, headers: b ? {'Content-Type': 'application/json'} : {}, body: b ? JSON.stringify(b) : undefined}); return r.json(); }""",
                [p, m, b])

            def until(fn, n=80):
                for _ in range(n):
                    if fn():
                        return True
                    page.wait_for_timeout(250)
                return False
            page.goto(self.base)
            page.wait_for_timeout(600)
            # Profil mit Budget speichern und starten
            page.click('[data-view=finder]')
            page.wait_for_timeout(800)
            page.fill('#swForm [name=place]', '70173')
            for cb in page.query_selector_all('#swForm [name=src]'):
                cb.check() if cb.get_attribute('value') == 'gleif' else cb.uncheck()
            page.fill('#swForm [name=max_companies]', '40')
            page.click('#swProfileSave')
            page.wait_for_timeout(500)
            self.assertIn('Budget 40 Firmen', page.text_content('#swProfileInfo'))
            page.click('#swProfileStart')
            self.assertTrue(until(lambda: (lambda s: s and s[0]['status'] not in ('queued', 'running'))(api('/sweeps'))))
            page.wait_for_timeout(2300)
            self.assertIn('neue Firmen', page.text_content('.sw-budget-line'))
            # Firmendaten-Übertragung: Website-Vorschlag nach der Übernahme in der Akte bestätigen
            page.select_option('#swSweep', '')
            page.wait_for_timeout(600)
            page.locator('.sw-item', has_text='Kesselwerk Anlagenbau').locator('[data-sw-do=uebernehmen]').click()
            page.wait_for_timeout(800)
            kessel = next(l for l in api('/leads') if l['company'].startswith('Kesselwerk'))
            page.evaluate('id => showModal(id)', kessel['id'])
            page.wait_for_timeout(1000)
            self.assertIn('Website bestätigen', page.text_content('#lfCd'))
            page.click('[data-lf-sug=bestaetigen]')
            page.wait_for_timeout(1200)
            self.assertIn('übertragen', page.text_content('#lfCd'))
            lead = api(f"/leads/{kessel['id']}")
            self.assertEqual((lead['legal_name'], lead['register_number']), ('Kesselwerk Anlagenbau GmbH', 'HRB 765432'))
            page.evaluate('() => closeModal()')
            # Beispieltag mit Reith: Übernahme → Akte → Bedarf → Angebot aus Bedarf
            page.locator('.sw-item', has_text='Reith Spezialkabel').locator('[data-sw-do=uebernehmen]').click()
            page.wait_for_timeout(800)
            reith = next(l for l in api('/leads') if l['company'].startswith('Reith'))
            api(f"/leads/{reith['id']}", 'PATCH', {'contact_route': 'netzwerk', 'permission_evidence': 'Empfehlung'})
            api('/workspace/calls', 'POST', {'lead_id': reith['id'], 'outcome': 'erreicht', 'notes': 'Relaunch gewünscht'})
            api(f"/leads/{reith['id']}/discovery", 'PUT', {'problem': 'Anfragen per Fax', 'desired_outcome': 'Online-Anfragen'})
            page.evaluate('() => reload()')
            page.evaluate('id => showModal(id)', reith['id'])
            page.wait_for_timeout(1200)
            page.click('#lfNeed summary')
            page.fill('#lfNeedForm [name=note]', 'Relaunch mit Anfrageformular bestätigt')
            page.select_option('#lfNeedForm [data-need=service]', 'webdesign')
            page.click('#lfNeedForm button[type=submit]')
            page.wait_for_timeout(1000)
            page.click('[data-lf-quote]')
            page.wait_for_timeout(1500)
            self.assertEqual(page.evaluate('() => currentView'), 'quotes')
            self.assertEqual(api('/workspace/proposals')[0]['status'], 'entwurf')
            # Gesperrte Firma: Sperre sichtbar, kein Aktionsknopf
            sperr = next(l for l in api('/leads') if l['company'] == 'Sperrfirma GmbH')
            page.evaluate('id => showModal(id)', sperr['id'])
            page.wait_for_timeout(1000)
            self.assertIn('Kontaktsperre', page.text_content('.lf-lock'))
            self.assertEqual(len(page.query_selector_all('.lf-next button')), 0)
            page.evaluate('() => closeModal()')
            # Tagesabschluss
            page.evaluate("() => switchView('dashboard')")
            page.wait_for_timeout(1200)
            self.assertIn('ohne nächsten Schritt', page.text_content('#tdCloseBody'))
            page.click('#tagesabschluss > summary')  # 2.0.0-dev15: Tagesabschluss ist eingeklappt
            page.click('#tdCloseBtn')
            page.wait_for_timeout(1500)
            self.assertIn('Jede Firma in einer Kontaktphase (Qualifiziert bis Angebot) hat einen nächsten Schritt', page.text_content('#tdCloseBody'))
            # Offline-Modus und Wiederherstellen-Liste unter „Einstellungen → Daten & Zugang“ (seit 2.0.0-dev14)
            page.evaluate("() => switchView('settings')")  # 2.0.0-dev14: Offline-Modus unter Einstellungen
            page.wait_for_timeout(1500)
            self.assertIn('signaldesk-', page.text_content('#qBackups'), 'Sicherung aus dem Tagesabschluss wird angeboten')
            page.check('#qOffline')
            page.wait_for_timeout(800)
            self.assertIn('Offline-Modus', page.text_content('#offlineBadge'))
            st, _ = page.evaluate("async () => { const r = await fetch('/api/sweeps', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({place: '70173', radius_km: 30, sources: ['gleif']})}); return [r.status, await r.json()]; }")
            self.assertEqual(st, 400)
            page.uncheck('#qOffline')
            page.wait_for_timeout(500)
            # Handyansicht
            page.set_viewport_size({'width': 390, 'height': 844})
            for view in ('dashboard', 'finder', 'quality', 'settings'):
                page.evaluate('v => switchView(v)', view)
                page.wait_for_timeout(500)
                self.assertFalse(page.evaluate('() => document.documentElement.scrollWidth > window.innerWidth + 1'), view)
            browser.close()
        self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main()
