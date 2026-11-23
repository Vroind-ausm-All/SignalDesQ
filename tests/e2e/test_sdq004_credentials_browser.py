"""Browserprüfung SDQ-004 (Audit B3): Einstellungen → Kalender & Postfach sagt ehrlich, wo ein Passwort gemerkt wird.

- Ohne sicheren Passwortspeicher: kein „merken“-Häkchen, sondern der Hinweis „gilt bis zum Neustart“.
- Klartext-Altbestand (zugangsdaten.json aus früheren Versionen): gelber Hinweis mit der Bitte, das Passwort neu einzugeben.
- Mit Passwortspeicher: Häkchen „im … merken“; der Altbestand wird beim Anzeigen übernommen, der Hinweis verschwindet,
  die Datei ist danach weg. Das Passwort erscheint nie in der Seite.
Fiktive Zugangsdaten, keine Abrufe nach außen."""
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cred_fake import FakeStore  # noqa: E402

from sales_tool import credentials  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402

PW = 'Alt-Klartext-Passwort-55'


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class CredentialsBrowserTests(unittest.TestCase):
    def tearDown(self):
        credentials._MEMORY.clear()
        credentials.set_backend('auto')

    def test_store_and_legacy_hints(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'cr.sqlite3'
            prepare_database(db)
            legacy = Path(tmp) / 'zugangsdaten.json'
            legacy.write_text(json.dumps({'caldav': PW}), encoding='utf-8')
            credentials.set_backend(None)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1280, 'height': 800})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)

                        def open_section():
                            page.goto(base + '/#/einstellungen?abschnitt=kalender')
                            page.reload()  # gleiche Adresse: neu laden, damit der Abschnitt frisch vom Server kommt
                            page.wait_for_load_state('networkidle')
                            page.locator('#cdForm').wait_for(state='visible')

                        # ---- ohne sicheren Speicher, mit Klartext-Altbestand
                        open_section()
                        self.assertEqual(page.locator('#cdForm label.check #cdRemember').count(), 0, 'kein Häkchen ohne sicheren Speicher')
                        self.assertIn('bis zum Neustart', page.text_content('[data-cred-nostore="cd"]'))
                        self.assertIn('neu eingeben', page.text_content('[data-cred-legacy="cd"]'))
                        self.assertEqual(page.locator('[data-cred-legacy="im"]').count(), 0, 'Hinweis nur beim betroffenen Zugang')
                        self.assertNotIn(PW, page.content())
                        self.assertTrue(legacy.exists(), 'ohne Neu-Eingabe bleibt die Altdatei unverändert')

                        # ---- mit Passwortspeicher: Übernahme, Hinweis weg, Datei weg
                        store = FakeStore()
                        credentials.set_backend(store)
                        credentials._MEMORY.clear()
                        open_section()
                        label = page.locator('#cdForm label.check', has=page.locator('#cdRemember'))
                        self.assertIn('Test-Passwortspeicher merken', label.text_content())
                        self.assertTrue(page.is_checked('#cdRemember'))
                        self.assertEqual(page.locator('[data-cred-legacy="cd"]').count(), 0)
                        self.assertFalse(legacy.exists())
                        self.assertEqual(list(store.data.values()), [PW])
                        self.assertNotIn(PW, page.content())
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
