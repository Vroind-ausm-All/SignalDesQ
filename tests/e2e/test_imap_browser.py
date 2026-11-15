"""Browserprüfung 2.0.0-dev43 (Produktreview M24 Stufe 3): Postfach in „Einstellungen → Kalender & Postfach“ eintragen,
Verbindung prüfen (Entwürfe-Ordner wird gefunden), dann einen Entwurf aus „Kontakt & Termine“ in den Entwürfe-Ordner legen.
Nichts wird versendet. Fiktive Firma, nur Abrufe auf 127.0.0.1."""
import json
import os
import socketserver
import sys
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

sys.path.insert(0, str(Path(__file__).parent.parent))
from test_v2_imap_drafts import PASS, USER, FakeIMAP  # noqa: E402

from sales_tool import credentials  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class ImapBrowserTests(unittest.TestCase):
    def test_setup_and_put_draft(self):
        FakeIMAP.appended, FakeIMAP.commands = [], []
        FakeIMAP.folders = [(r'\HasNoChildren', 'INBOX'), (r'\HasNoChildren \Drafts', 'Entw&APw-rfe')]
        imap = socketserver.ThreadingTCPServer(('127.0.0.1', 0), FakeIMAP)
        imap.daemon_threads = True
        threading.Thread(target=imap.serve_forever, daemon=True).start()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'im.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Entwurf Fiktiv GmbH', 'stage': 'termin'})
            draft = api('/workspace/mail-drafts', 'POST', {'lead_id': lead['id'], 'draft_type': 'nach_gespraech', 'contact_basis': 'Gespräch vom 10.11.'})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900})
                        errors = []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.goto(base + '/#/einstellungen?abschnitt=kalender')
                        page.wait_for_load_state('networkidle')
                        page.locator('#imForm').wait_for()
                        page.fill('#imHost', '127.0.0.1')
                        page.fill('#imPort', str(imap.server_address[1]))
                        page.fill('#imUser', USER)
                        page.fill('#imSender', USER)
                        page.fill('#imPass', PASS)
                        page.locator('#imForm button[type=submit]').click()
                        page.wait_for_function('() => document.querySelector("#imStatus")?.textContent.includes("hinterlegt")')
                        self.assertNotIn(PASS, page.content())
                        page.locator('#imTest').click()
                        page.wait_for_function('() => document.querySelector("#imStatus")?.textContent.includes("Entwürfe-Ordner: Entwürfe")')
                        page.goto(base + '/#/heute/kontakt-termine')
                        page.wait_for_load_state('networkidle')
                        btn = page.locator(f'[data-ws-imap="{draft["id"]}"]')
                        btn.wait_for()
                        btn.click()
                        page.locator('[data-ws-imap-done]').first.wait_for()
                        self.assertIn('Entw', page.locator('[data-ws-imap-done]').first.inner_text())
                        self.assertEqual(len(FakeIMAP.appended), 1)
                        self.assertIn('\\Draft', FakeIMAP.appended[0][0])
                        self.assertEqual(errors, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()
                imap.shutdown()
                imap.server_close()
                credentials._MEMORY.clear()


if __name__ == '__main__':
    unittest.main()
