"""Browserprüfung 2.0.0-dev12: Firmenakte mit Reitern – Kopf mit Name und nächster Aktion, Reiter per Maus und Tastatur,
Sprung aus „Als Nächstes“ in den richtigen Reiter, neuer Lead ohne Reiter. Fiktive Firma, keine Abrufe nach außen."""
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

from sales_tool.model import connect, init_db
from sales_tool.server import make_handler

SHOTS = os.environ.get('SIGNALDESK_E2E_SHOTS')
TABS = ('ueberblick', 'kontakt', 'bedarf', 'recherche', 'stammdaten')


def _active(page):
    return page.locator('[data-lf-tab][aria-selected="true"]').get_attribute('data-lf-tab')


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class AkteTabsBrowserTests(unittest.TestCase):
    def test_tabs_header_and_jumps(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'k.sqlite3'
            with connect(db) as conn:
                init_db(conn)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            req = urllib.request.Request(base + '/api/leads', method='POST', headers={'Content-Type': 'application/json', 'Origin': base},
                                         data=json.dumps({'company': 'Beispiel Malerbetrieb', 'location': 'Stuttgart 70191', 'stage': 'qualifiziert',
                                                          'industry': 'Sonstige', 'next_step': 'Anrufen'}).encode())
            urllib.request.urlopen(req).read()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 768})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base)
                        page.wait_for_load_state('networkidle')  # erst nach dem Start klicken (sonst ist die Firmenliste ggf. noch verborgen)
                        page.locator('.sidebar [data-view="leads"]').click()
                        page.locator('#leadRows tr', has_text='Beispiel Malerbetrieb').first.click()
                        page.locator('#leadTabs').wait_for(state='visible', timeout=15000)

                        # Kopf: Firmenname, Kennzahlen, nächste Aktion; Start im Überblick
                        self.assertEqual(page.text_content('#modalTitle'), 'Beispiel Malerbetrieb')
                        self.assertIn('Phase Qualifiziert', page.text_content('#modalMeta'))  # 2.0.0-dev13: Name statt interner Schlüssel
                        self.assertTrue(page.locator('#lfHeadNext').is_visible())
                        self.assertEqual(_active(page), 'ueberblick')
                        self.assertTrue(page.locator('#leadFile').is_visible())
                        self.assertFalse(page.locator('#leadForm').is_visible())

                        # Jeder Reiter zeigt genau seinen Bereich
                        heights = {}
                        for tab, probe in zip(TABS, ('#leadFile', '#activityForm', '#discoveryForm', '#leadImprintBtn', '#leadForm')):
                            page.locator(f'[data-lf-tab="{tab}"]').click()
                            self.assertEqual(_active(page), tab)
                            self.assertTrue(page.locator(probe).is_visible(), tab)
                            self.assertEqual(page.locator('[data-lf-panel]:not(.lf-panel-off)').count(), 1)
                            heights[tab] = page.evaluate('() => document.querySelector("#modal .modal").scrollHeight')
                            if SHOTS:
                                page.screenshot(path=str(Path(SHOTS) / f'akte-{tab}.png'))
                        # Längster Reiter deutlich kürzer als der Dialog vor dev12 (rund 7.800 px)
                        self.assertLess(max(heights.values()), 4000, heights)

                        # Tastatur: Pfeile und Pos1/Ende wechseln den Reiter
                        page.locator('[data-lf-tab="stammdaten"]').focus()
                        page.keyboard.press('ArrowRight')
                        self.assertEqual(_active(page), 'ueberblick')
                        page.keyboard.press('End')
                        self.assertEqual(_active(page), 'stammdaten')
                        page.keyboard.press('ArrowLeft')
                        self.assertEqual(_active(page), 'recherche')

                        # Ein Element in einem verdeckten Reiter wird sichtbar gemacht
                        page.evaluate('() => window.leadTabs.reveal(document.querySelector("#discoveryForm"))')
                        self.assertEqual(_active(page), 'bedarf')

                        # Neuer Lead: keine Reiter, nur das Formular
                        page.locator('#closeModal').click()
                        page.locator('#newLeadBtn').click()
                        page.locator('#leadForm').wait_for(state='visible')
                        self.assertFalse(page.locator('#leadTabs').is_visible())
                        self.assertFalse(page.locator('#lfHeadNext').is_visible())
                        self.assertEqual(page.text_content('#modalTitle'), 'Neuer Lead')

                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
