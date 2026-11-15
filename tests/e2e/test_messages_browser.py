"""Browserprüfung 2.0.0-dev29 (Produktreview M37): Eigene Vorlage im Mail-Assistenten – Vorschau zeigt fehlende Werte
markiert und sperrt die Endfassung; mit Angebot und Person ist sie vollständig; Anrede neutral; Entwurf speichern. Nichts wird
versendet. Fiktive Firma und Person, keine Abrufe nach außen."""
import json
import os
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
from s5_helpers import confirm_need, release_offer  # noqa: E402
from test_accounting import SELLER  # noqa: E402

from sales_tool import accounting as acc  # noqa: E402
from sales_tool import offer_flow as of  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class MessagesBrowserTests(unittest.TestCase):
    def test_template_preview_and_draft(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'ms.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Vorlage Fiktiv GmbH', 'stage': 'termin'})
            conn = connect(str(db))
            acc.save_settings(conn, SELLER)
            confirm_need(conn, lead['id'])
            contact = conn.execute("INSERT INTO decision_contacts(lead_id, full_name) VALUES (?, 'Maria Beispiel')", (lead['id'],)).lastrowid
            conn.commit()
            conn.close()
            p = api('/workspace/proposals', 'POST', {'lead_id': lead['id'], 'tax_mode': 'regel_19', 'project_label': 'Neue Website',
                                                     'positions': [{'service': 'webdesign', 'size': 'S'}]})
            conn = connect(str(db))
            release_offer(conn, p['id'])
            of.set_status(conn, p['id'], {'status': 'gesendet_manuell'})
            conn.close()
            tpl = next(t['id'] for t in api('/vorlagen')['templates'] if t['key'] == 'angebot_versand')
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
                        page.select_option('#wsMailForm [name=lead_id]', str(lead['id']))
                        page.locator(f'#msgProposal option[value="{p["id"]}"]').wait_for(state='attached')
                        page.select_option('#msgTemplate', str(tpl))
                        page.locator('#msgPreviewBtn').click()
                        page.locator('#msgPreview [data-msg-missing]').wait_for()
                        self.assertIn('Angebotsnummer', page.locator('#msgPreview [data-msg-missing]').inner_text())
                        self.assertGreater(page.locator('#msgPreview .msg-missing').count(), 0)
                        self.assertTrue(page.locator('#msgCopy').is_disabled(), 'keine Endfassung mit Lücken')
                        page.select_option('#msgProposal', str(p['id']))
                        page.select_option('#msgContact', str(contact))
                        page.locator('#msgPreviewBtn').click()
                        page.wait_for_function('() => !document.querySelector("#msgPreview [data-msg-missing]") && document.querySelector("#msgPreview [data-msg-body]")')
                        text = page.locator('#msgPreview [data-msg-body]').inner_text()
                        self.assertTrue(text.startswith('Guten Tag Maria Beispiel,'), text[:60])
                        self.assertIn(p['number'], page.locator('#msgPreview [data-msg-subject]').inner_text())
                        self.assertFalse(page.locator('#msgCopy').is_disabled())
                        page.fill('#wsMailForm [name=contact_basis]', 'Angebot im Termin am 12.11. zugesagt')
                        page.locator('#msgSaveBtn').click()
                        page.wait_for_function('() => document.querySelector("#toast")?.textContent.includes("nicht versendet")')
                        drafts = api('/workspace/mail-drafts')
                        self.assertEqual(len(drafts), 1)
                        self.assertEqual(drafts[0]['missing_json'], '[]')
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
