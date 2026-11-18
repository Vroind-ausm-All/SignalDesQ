"""Browserprüfung 2.0.0-dev31, Abnahmefall T06: Rückruf nach erfolglosem Versuch planen.

Szenario: Anruf „nicht erreicht“ am Vormittag dokumentieren → SignalDesk plant den nächsten Versuch als Aufgabe zu einer
anderen Tageszeit und setzt den nächsten Schritt der Firma. Nach dem dritten erfolglosen Versuch: Kanalwechsel oder Parken
statt weiterer Anrufe. Es wird niemand angerufen. Fiktive Firma, keine Abrufe nach außen."""
import json
import os
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

from sales_tool.server import make_handler, prepare_database


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class RetryBrowserTests(unittest.TestCase):
    def test_missed_call_plans_next_attempt(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 't06.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Rückruf Fiktiv GmbH', 'stage': 'kontakt', 'permission': 'telefon_einzelfall'})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base + '/#/heute/kontakt-termine')
                        page.wait_for_load_state('networkidle')

                        def missed(slot, expect):
                            page.select_option('#wsCallForm [name=lead_id]', str(lead['id']))
                            page.select_option('#wsCallForm [name=outcome]', 'nicht_erreicht')
                            page.select_option('#wsCallForm [name=slot]', slot)
                            page.locator('#wsCallForm button[type=submit]').click()
                            for _ in range(50):  # warten, bis der Versuch gespeichert und die Ansicht neu geladen ist
                                if api(f'/leads/{lead["id"]}')['next_step'].startswith(expect):
                                    break
                                page.wait_for_timeout(100)
                            else:  # nicht still weiterlaufen: sonst fällt ein verlorener Versuch erst später auf
                                now = api('/leads/' + str(lead['id']))['next_step']
                                self.fail(f'Versuch nicht gespeichert, erwartet „{expect}“, Stand: {now}')
                            # 2.0.0-dev52: Nach dem Speichern baut die Ansicht die Firmenauswahl neu auf. Erst weitermachen, wenn der neue
                            # Stand sichtbar ist – sonst setzt der Neuaufbau die Auswahl des nächsten Versuchs mitten im Ausfüllen zurück.
                            page.wait_for_function('t => document.body.textContent.includes(t)', arg=expect, timeout=10000)
                            page.wait_for_load_state('networkidle')

                        missed('vormittag', 'Erneut anrufen (2. Versuch)')
                        page.wait_for_function('() => document.body.textContent.includes("Erneut anrufen (2. Versuch)")', timeout=10000)
                        tasks = [t for t in api('/tasks') if t['lead_id'] == lead['id'] and not t['done']] if isinstance(api('/tasks'), list) else None
                        l = api(f'/leads/{lead["id"]}')
                        self.assertTrue(l['next_step'].startswith('Erneut anrufen (2. Versuch) – diesmal'), l['next_step'])
                        self.assertNotIn('vormittags', l['next_step'], 'andere Tageszeit als der erfolglose Versuch')
                        self.assertTrue(l['next_date'], 'Frist gesetzt')
                        if tasks is not None:
                            self.assertEqual([t['title'] for t in tasks if t['title'].startswith('Erneut anrufen')], [l['next_step']])
                        missed('mittag', 'Erneut anrufen (3. Versuch)')
                        missed('nachmittag', 'Nicht erreicht nach 3')
                        l = api(f'/leads/{lead["id"]}')
                        self.assertTrue(l['next_step'].startswith('Nicht erreicht nach 3 Versuchen: Kanal wechseln'), l['next_step'])
                        open_retries = [t for t in api('/tasks') if t['lead_id'] == lead['id'] and not t['done'] and t['title'].startswith('Erneut anrufen')] if tasks is not None else []
                        self.assertEqual(open_retries, [], 'kein weiterer Anrufversuch offen')
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
