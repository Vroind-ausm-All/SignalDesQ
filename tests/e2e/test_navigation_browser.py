"""Browserprüfung 2.0.0-dev14 (Produktreview M06/M07, U01–U03, Abnahmefall T05):
- Sechs Bereiche in der Seitenleiste; jeder Bereich öffnet seine Standardansicht, die übrigen Ansichten stehen als Reiter oben.
- Jede Ansicht hat eine Adresse; Neuladen bleibt in der Ansicht; Zurück und Vor wechseln zwischen den Ansichten.
- Eine Firma hat eine Adresse (?firma=ID): Neuladen öffnet sie wieder, Zurück schließt sie und zeigt die gefilterte Liste.
- Die Filter der Firmenliste stehen in der Adresse und überstehen das Neuladen.
- Einstellungen sind ein eigener Bereich; „Leistungen & Preise“ ist aus den Angeboten erreichbar.
Fiktive Firmen, keine Abrufe nach außen."""
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
OLD_VIEWS = ('dashboard', 'tasks', 'workspace', 'finder', 'datacheck', 'center', 'research', 'scoring', 'signals',
             'leads', 'pipeline', 'quality', 'quotes', 'accounting', 'studio', 'playbook')


def visible_view(page):
    return page.evaluate('() => [...document.querySelectorAll(".content")].filter(e => !e.classList.contains("hidden")).map(e => e.id).join(",")')


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class NavigationBrowserTests(unittest.TestCase):
    def test_areas_addresses_history_and_settings(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'n.sqlite3'
            with connect(db) as conn:
                init_db(conn)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, body):
                req = urllib.request.Request(base + '/api' + path, method='POST', headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode())
                return json.loads(urllib.request.urlopen(req).read())

            api('/leads', {'company': 'Beispiel Malerbetrieb', 'stage': 'qualifiziert'})
            lead = api('/leads', {'company': 'Muster Steuerkanzlei', 'stage': 'kontakt'})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 768})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base)
                        page.wait_for_load_state('networkidle')
                        self.assertTrue(page.url.endswith('#/heute'))

                        # U01: sechs Bereiche, jedes alte Ziel als Reiter erreichbar
                        areas = page.locator('.sidebar .nav[data-area]')
                        self.assertEqual(areas.count(), 6)
                        labels = page.evaluate('() => [...document.querySelectorAll(".sidebar .nav[data-area]")].map(b => [...b.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join("").trim())')
                        self.assertEqual(labels, ['Heute', 'Finden', 'Firmen', 'Angebote', 'Abrechnen', 'Einstellungen'])
                        self.assertEqual(page.text_content('.sidebar [data-area="einstellungen"] .nav-dot'), '')  # KI-Status ist kein Zähler
                        tabs = page.evaluate('() => [...document.querySelectorAll("#areaBar [data-area-view]")].map(b => b.dataset.areaView)')
                        self.assertEqual(sorted(set(tabs) & set(OLD_VIEWS)), sorted(OLD_VIEWS))

                        # Bereich → Standardansicht, Reiter → weitere Ansicht; Adresse folgt
                        page.locator('.sidebar [data-area="firmen"]').click()
                        self.assertEqual(visible_view(page), 'viewLeads')
                        self.assertTrue(page.url.endswith('#/firmen'))
                        page.locator('[data-area-view="pipeline"]').click()
                        self.assertEqual(visible_view(page), 'viewPipeline')
                        self.assertTrue(page.url.endswith('#/firmen/pipeline'))
                        self.assertEqual(page.text_content('#areaCrumb'), 'Firmen')
                        self.assertEqual(page.locator('.sidebar .nav[data-area="firmen"]').get_attribute('aria-current'), 'page')

                        # U03: Neuladen bleibt in der Ansicht
                        page.reload()
                        page.wait_for_load_state('networkidle')
                        self.assertEqual(visible_view(page), 'viewPipeline')

                        # Zurück / Vor
                        page.locator('.sidebar [data-area="finden"]').click()
                        self.assertEqual(visible_view(page), 'viewFinder')
                        page.go_back()
                        page.wait_for_function('() => !document.getElementById("viewPipeline").classList.contains("hidden")')
                        page.go_forward()
                        page.wait_for_function('() => !document.getElementById("viewFinder").classList.contains("hidden")')

                        # T05: gefilterte Liste → Firma → Zurück: Filter bleiben, Firma hat eine Adresse
                        page.locator('.sidebar [data-area="firmen"]').click()
                        page.fill('#leadSearch', 'Kanzlei')
                        page.wait_for_function('() => location.hash.includes("suche=Kanzlei")')
                        page.locator('#leadRows tr', has_text='Muster Steuerkanzlei').click()
                        page.locator('#leadTabs').wait_for(state='visible')
                        self.assertIn(f"firma={lead['id']}", page.url)
                        page.reload()  # Firma per Adresse wieder öffnen
                        page.locator('#leadTabs').wait_for(state='visible', timeout=15000)
                        self.assertEqual(page.text_content('#modalTitle'), 'Muster Steuerkanzlei')
                        self.assertEqual(page.input_value('#leadSearch'), 'Kanzlei')
                        page.locator('#closeModal').click()
                        page.locator('#modal').wait_for(state='hidden')
                        page.wait_for_function('() => !location.hash.includes("firma=")')
                        self.assertEqual(page.locator('#leadRows tr').count(), 1)  # Filter gilt weiter
                        page.locator('#leadRows tr', has_text='Muster Steuerkanzlei').click()
                        page.locator('#leadTabs').wait_for(state='visible')
                        page.go_back()  # Zurück schließt die Firma, die Liste bleibt gefiltert
                        page.locator('#modal').wait_for(state='hidden')
                        self.assertEqual(visible_view(page), 'viewLeads')
                        self.assertEqual(page.input_value('#leadSearch'), 'Kanzlei')

                        # M06: Einstellungen als eigener Bereich; Preise aus den Angeboten verlinkt
                        page.locator('.sidebar [data-area="einstellungen"]').click()
                        self.assertEqual(visible_view(page), 'viewSettings')
                        for section in ('darstellung', 'ownTimes', 'leistungsprofil', 'targetProfile', 'qbSettingsBox', 'gewichte', 'rtPanel', 'zugang', 'offline'):
                            self.assertEqual(page.evaluate(f'() => document.getElementById("{section}").closest(".content").id'), 'viewSettings', section)
                        page.locator('#qbSettings input[name="hourly_rate"]').wait_for(timeout=15000)
                        page.locator('.sidebar [data-area="angebote"]').click()
                        page.locator('[data-settings-link="preise"]').click()
                        self.assertEqual(visible_view(page), 'viewSettings')
                        self.assertIn('abschnitt=preise', page.url)
                        page.wait_for_function('() => Math.abs(document.getElementById("preise").getBoundingClientRect().top) < 120', timeout=5000)
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'einstellungen.png'))
                        # Datenpflege bleibt unter Firmen, wiederkehrende Recherche steht unter Finden
                        self.assertEqual(page.evaluate('() => document.getElementById("qChanges").closest(".content").id'), 'viewQuality')
                        self.assertEqual(page.evaluate('() => document.getElementById("qJobForm").closest(".content").id'), 'viewCenter')

                        # Hilfe ist ein kleines festes Ziel
                        page.locator('.nav-help').click()
                        self.assertEqual(visible_view(page), 'viewPlaybook')
                        self.assertTrue(page.url.endswith('#/einstellungen/hilfe'))

                        # Schmaler Bildschirm: keine waagerechte Scrollleiste der Seite
                        page.set_viewport_size({'width': 390, 'height': 844})
                        for area in ('heute', 'finden', 'firmen', 'einstellungen'):
                            page.evaluate(f'() => document.querySelector(\'.sidebar [data-area="{area}"]\').click()')
                            self.assertFalse(page.evaluate('() => document.documentElement.scrollWidth > window.innerWidth + 1'), area)

                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
