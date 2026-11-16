"""Browserprüfung 2.0.0-dev49 (visuelle Konsolidierung, Schritt 1): Hauptnavigation bei schmaler Breite.
- Bei 390 × 844 steht „☰ Menü“ in der Kopfzeile; die Seitenleiste ist zu, kein waagerechtes Scrollen.
- Öffnen zeigt alle sechs Bereiche, der aktuelle ist markiert, der Fokus liegt in der Schublade, aria-expanded folgt.
- Wahl von „Angebote“ wechselt Ansicht und Adresse und schließt; Escape schließt und gibt den Fokus an den Knopf zurück;
  Klick auf den abgedunkelten Hintergrund und „Schließen“ schließen ebenfalls.
- Bei 1280 px ist der Knopf unsichtbar und die Seitenleiste normal da.
Fiktive Firma, keine Abrufe nach außen."""
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
AREAS = ['Heute', 'Finden', 'Firmen', 'Angebote', 'Abrechnen', 'Einstellungen']
LABELS_JS = ('() => [...document.querySelectorAll("#sideNav .nav[data-area]")].filter(b => b.offsetParent !== null)'
             '.map(b => [...b.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join("").trim())')


def visible_view(page):
    return page.evaluate('() => [...document.querySelectorAll(".content")].filter(e => !e.classList.contains("hidden")).map(e => e.id).join(",")')


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class MobileNavigationBrowserTests(unittest.TestCase):
    def test_menu_drawer_on_narrow_screens(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'm.sqlite3'
            with connect(db) as conn:
                init_db(conn)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            req = urllib.request.Request(base + '/api/leads', method='POST', headers={'Content-Type': 'application/json', 'Origin': base},
                                         data=json.dumps({'company': 'Beispielbau Fiktiv GmbH', 'stage': 'qualifiziert'}).encode())
            urllib.request.urlopen(req).read()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 390, 'height': 844})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base + '/#/firmen')
                        page.wait_for_load_state('networkidle')
                        page.wait_for_function('() => document.getElementById("viewLeads") && !document.getElementById("viewLeads").classList.contains("hidden")')

                        menu = page.locator('#navMenuBtn')
                        self.assertTrue(menu.is_visible())
                        self.assertIn('Menü', menu.inner_text())
                        self.assertEqual(menu.get_attribute('aria-controls'), 'sideNav')
                        self.assertEqual(menu.get_attribute('aria-expanded'), 'false')
                        self.assertFalse(page.locator('#sideNav').is_visible())
                        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 391)
                        # die Kopfzeile passt in die Breite (nichts ragt rechts heraus)
                        self.assertLessEqual(page.evaluate('Math.max(...[...document.querySelectorAll(".topbar *")].map(e => e.getBoundingClientRect().right))'), 390.5)
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'mobile_nav_zu.png'))

                        # Öffnen: alle sechs Bereiche, aktueller markiert, Fokus in der Schublade
                        menu.click()
                        page.locator('#sideNav').wait_for(state='visible')
                        self.assertEqual(menu.get_attribute('aria-expanded'), 'true')
                        self.assertEqual(page.evaluate(LABELS_JS), AREAS)
                        self.assertEqual(page.get_attribute('#sideNav .nav[aria-current="page"]', 'data-area'), 'firmen')
                        self.assertTrue(page.evaluate('document.getElementById("sideNav").contains(document.activeElement)'))
                        self.assertTrue(page.locator('#navClose').is_visible())
                        self.assertTrue(page.locator('#navScrim').is_visible())
                        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 391)
                        box = page.locator('#sideNav').bounding_box()
                        self.assertEqual(round(box['x']), 0)
                        self.assertLess(box['width'], 390)
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'mobile_nav_offen.png'))

                        # Bereich wählen: Ansicht und Adresse wechseln, Schublade schließt
                        page.locator('#sideNav .nav[data-area="angebote"]').click()
                        page.wait_for_function('() => location.hash.startsWith("#/angebote")')
                        page.locator('#sideNav').wait_for(state='hidden')
                        self.assertEqual(visible_view(page), 'viewQuotes')
                        self.assertEqual(menu.get_attribute('aria-expanded'), 'false')
                        self.assertEqual(page.text_content('#areaCrumb'), 'Angebote')

                        # Escape schließt und gibt den Fokus an den Knopf zurück
                        menu.click()
                        page.locator('#sideNav').wait_for(state='visible')
                        self.assertEqual(page.get_attribute('#sideNav .nav[aria-current="page"]', 'data-area'), 'angebote')
                        page.keyboard.press('Escape')
                        page.locator('#sideNav').wait_for(state='hidden')
                        self.assertEqual(page.evaluate('document.activeElement.id'), 'navMenuBtn')
                        self.assertEqual(menu.get_attribute('aria-expanded'), 'false')
                        self.assertTrue(page.url.endswith('#/angebote'), 'Escape ändert die Adresse nicht')

                        # Klick auf den Hintergrund und „Schließen“ schließen ebenfalls; Inhalt dahinter wieder bedienbar
                        menu.click()
                        page.locator('#sideNav').wait_for(state='visible')
                        page.mouse.click(380, 600)
                        page.locator('#sideNav').wait_for(state='hidden')
                        self.assertFalse(page.evaluate('document.querySelector(".main").inert'))
                        menu.click()
                        page.locator('#navClose').click()
                        page.locator('#sideNav').wait_for(state='hidden')
                        self.assertEqual(page.evaluate('document.activeElement.id'), 'navMenuBtn')

                        # Zurück im Browser bleibt unverändert: von Angebote zurück zu Firmen
                        page.go_back()
                        page.wait_for_function('() => location.hash.startsWith("#/firmen")')
                        page.wait_for_function('() => !document.getElementById("viewLeads").classList.contains("hidden")')

                        # breit: Knopf unsichtbar, Seitenleiste wie bisher
                        page.set_viewport_size({'width': 1280, 'height': 720})
                        page.wait_for_function('() => getComputedStyle(document.getElementById("navMenuBtn")).display === "none"')
                        self.assertFalse(menu.is_visible())
                        self.assertTrue(page.locator('#sideNav').is_visible())
                        self.assertFalse(page.locator('#navClose').is_visible())
                        self.assertEqual(page.evaluate(LABELS_JS), AREAS)
                        self.assertEqual(round(page.locator('#sideNav').bounding_box()['width']), 238)
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'mobile_nav_breit.png'))

                        # offen gelassen und dann breit: Schublade schließt von selbst
                        page.set_viewport_size({'width': 390, 'height': 844})
                        page.wait_for_function('() => getComputedStyle(document.getElementById("navMenuBtn")).display !== "none"')
                        menu.click()
                        page.locator('#sideNav').wait_for(state='visible')
                        page.set_viewport_size({'width': 1280, 'height': 720})
                        page.wait_for_function('() => !document.body.classList.contains("nav-open")')
                        self.assertFalse(page.evaluate('document.querySelector(".main").inert'))

                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
