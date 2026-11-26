"""Browserprüfung 2.0.0-dev54 (visuelle Konsolidierung, Schritt 6): Firmenakte als Detailseite aus dem UI-Baukasten.

Abnahme (1280 × 720, fiktive Firmen):
- Seitenkopf: „← Firmen“, Firmenname, Phase als Pille, Zusatz Ort · Branche, genau eine Hauptaktion; darunter fünf Reiter,
  beim Öffnen hat der Reiter „Überblick“ den Fokus.
- Überblick: „Vereinbart“ beginnt bei höchstens 200 px und ist von der Empfehlung des Programms getrennt; Chancenliste;
  Kontextspalte und die erste Chance liegen im ersten Bildschirm; Kontaktstatus in der Kontextspalte.
- Gesperrte Firma: Sperre im Kopf und in der Kontextspalte sichtbar, ohne etwas aufzuklappen; keine Aktion in der Empfehlung.
- „← Firmen“ führt zur gefilterten Liste; „＋ Neue Firma“ (Knopf und Strg+K) zeigt „Neue Firma“.
- Kein sichtbares „Lead“ auf Akte (alle Reiter, alle Klappzeilen offen), Firmenliste, Heute, Angebote, Abrechnen, Einstellungen.
- 390 × 844: kein waagerechtes Scrollen. Keine Seitenfehler, keine Abrufe nach außen. Nur fiktive Firmen."""
import datetime as dt
import json
import os
import re
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
TABS = ['ueberblick', 'kontakt', 'bedarf', 'recherche', 'stammdaten']
# Sichtbarer Text der gerade gezeigten Ansicht bzw. der Akte – mit allen Klappzeilen geöffnet, inklusive Platzhalter und Auswahltexte
VISIBLE_TEXT = '''sel => {
  const root = document.querySelector(sel);
  root.querySelectorAll('details').forEach(d => { d.open = true; });
  const extra = [...root.querySelectorAll('[placeholder],option,[title],[aria-label]')].filter(e => e.closest('.hidden') === null)
    .map(e => [e.placeholder, e.tagName === 'OPTION' ? e.textContent : '', e.title, e.getAttribute('aria-label')].filter(Boolean).join(' '));
  return root.innerText + '\\n' + extra.join('\\n');
}'''
VIEW = '() => "#" + [...document.querySelectorAll(".content")].find(e => !e.classList.contains("hidden")).id'


def visible_primaries(page, scope):
    return page.evaluate(f'() => [...document.querySelectorAll("{scope} .btn-primary")].filter(b => b.offsetParent !== null).map(b => b.textContent.trim())')


def lead_lines(text):
    return [line.strip() for line in text.split('\n') if re.search(r'\bleads?\b', line, re.I)]


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class UiAkteBrowserTests(unittest.TestCase):
    def test_company_file_page(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'a.sqlite3'
            with connect(db) as conn:
                init_db(conn)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'{}')

            today = dt.date.today()
            metal = api('/leads', 'POST', {'company': 'Beispiel Metall GmbH', 'location': 'Stuttgart', 'industry': 'Industrie & B2B-Technik',
                                           'stage': 'termin', 'contact_name': 'Herr Muster', 'contact_role': 'Geschäftsführung',
                                           'contact_route': 'inbound', 'next_step': 'Rückruf durchführen', 'next_date': today.isoformat(),
                                           'estimated_budget': 4000})
            api('/activities', 'POST', {'lead_id': metal['id'], 'activity_type': 'gespraech', 'detail': 'Relaunch besprochen'})
            api(f"/leads/{metal['id']}/chances", 'POST', {'title': 'Website-Relaunch', 'next_step': 'Angebot erstellen',
                                                          'next_date': (today + dt.timedelta(days=1)).isoformat()})
            locked = api('/leads', 'POST', {'company': 'Sperre Fiktiv GmbH', 'location': 'Ulm', 'industry': 'Sonstige', 'stage': 'qualifiziert',
                                            'permission': 'nicht_kontaktieren', 'permission_evidence': 'Widerspruch am Telefon'})
            for name in ('Fiktiv Handel GmbH', 'Fiktiv Software GmbH', 'Muster Bau KG'):
                api('/leads', 'POST', {'company': name, 'location': 'Hamburg', 'industry': 'Sonstige', 'stage': 'qualifiziert'})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1280, 'height': 720})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if not r.url.startswith(base) and not r.url.startswith('data:') else None)
                        page.goto(base + '/#/firmen')
                        page.wait_for_load_state('networkidle')
                        page.locator('#leadRows tr', has_text='Beispiel Metall GmbH').click()
                        page.locator('#lfAgreed').wait_for()
                        page.locator('#lfChances .ui-row').first.wait_for()

                        # Seitenkopf
                        self.assertEqual(page.text_content('#closeModal'), '← Firmen')
                        self.assertEqual(page.text_content('#modalTitle'), 'Beispiel Metall GmbH')
                        self.assertEqual(page.text_content('#modalPhase'), 'Termin')
                        self.assertEqual(page.text_content('#modalMeta'), 'Stuttgart · Industrie & B2B-Technik')
                        self.assertTrue(page.locator('#modalLock').is_hidden())
                        self.assertEqual(visible_primaries(page, '#modal'), ['Gespräch notieren'])
                        self.assertEqual(visible_primaries(page, '#modal .ui-head'), ['Gespräch notieren'])
                        # Reiter: fünf, Fokus auf „Überblick“
                        self.assertEqual(page.evaluate('() => [...document.querySelectorAll("#leadTabs [data-lf-tab]")].map(t => t.dataset.lfTab)'), TABS)
                        self.assertEqual(page.evaluate('() => document.activeElement.dataset.lfTab'), 'ueberblick')

                        # Abnahmemaß 1280 × 720
                        box = lambda sel: page.locator(sel).first.bounding_box()
                        self.assertLessEqual(box('#lfAgreed')['y'], 200)
                        side, first = box('#lfSide'), box('#lfChances .ui-row')
                        self.assertLess(side['y'], 720)
                        self.assertAlmostEqual(side['width'], 320, delta=1)
                        self.assertLessEqual(first['y'] + first['height'], 720, 'erste Chance im ersten Bildschirm')
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'akte_1280.png'))

                        # „Vereinbart“ (mit dem Kunden) getrennt von der Empfehlung des Programms
                        agreed = page.locator('#lfAgreed').inner_text()
                        self.assertIn('Vereinbart', agreed)
                        self.assertIn('Rückruf durchführen', agreed)
                        self.assertIn('fällig heute', agreed)
                        self.assertNotIn('Empfehlung', agreed)
                        rec = page.locator('#lfNext')
                        self.assertEqual(rec.locator('summary b').inner_text(), 'Empfehlung')
                        self.assertEqual(page.evaluate('() => document.getElementById("lfAgreed").contains(document.getElementById("lfNext"))'), False)
                        self.assertNotIn('Rückruf durchführen', rec.locator('summary').inner_text())
                        self.assertFalse(rec.evaluate('d => d.open'))

                        # Chancenliste
                        heads = page.evaluate('() => [...document.querySelectorAll("#lfChances .ui-row-head > span:not(.ui-sr)")].map(s => s.textContent.trim())')
                        self.assertEqual(heads, ['Chance', 'Nächster Schritt', 'Fällig', 'Status', 'Wert'])
                        row = page.locator('#lfChances .ui-row').first
                        self.assertIn('Website-Relaunch', row.inner_text())
                        self.assertIn('Angebot erstellen', row.inner_text())
                        self.assertIn('4.000', row.inner_text())

                        # Kontextspalte
                        ctx = page.locator('#lfSide').inner_text()
                        for expected in ('Ansprechpartner', 'Herr Muster', 'Letzter Kontakt', 'Kontaktstatus', 'Website', 'Telefon', 'Verlauf'):
                            self.assertIn(expected, ctx)
                        self.assertEqual(page.locator('#lfSide .qt-phase.is-current .ui-txt').inner_text().strip(), 'Termin')
                        self.assertEqual(page.locator('#lfSide .qt-phase').count(), 5)

                        # Zeile der Chance öffnet die Chance im Reiter „Bedarf & Angebot“
                        row.click()
                        page.wait_for_function('() => document.querySelector("[data-lf-tab=bedarf]").getAttribute("aria-selected") === "true"')
                        self.assertTrue(page.locator('#chList .ch-item[open]').is_visible())

                        # Hauptaktion: „Gespräch notieren“ führt ins Protokoll (Kontakt & Verlauf)
                        page.locator('#lfHeadNext').click()
                        page.wait_for_function('() => document.activeElement && document.activeElement.name === "detail"')
                        self.assertEqual(page.input_value('#activityForm [name=activity_type]'), 'gespraech')
                        self.assertTrue(page.locator('#lfTimeline .lf-tl li').first.is_visible())

                        # Kein sichtbares „Lead“ in der Akte (alle Reiter, Klappzeilen offen)
                        for tab in TABS:
                            page.locator(f'[data-lf-tab="{tab}"]').click()
                            self.assertEqual(lead_lines(page.evaluate(VISIBLE_TEXT, '#modal')), [], tab)
                            if SHOTS:
                                page.screenshot(path=str(Path(SHOTS) / f'akte_{tab}.png'), full_page=True)

                        # Gesperrte Firma: Sperre sichtbar ohne Aufklappen, keine Aktion in der Empfehlung
                        page.evaluate(f'() => showModal({locked["id"]})')
                        page.locator('#lfSide .lf-lock').wait_for()
                        self.assertTrue(page.locator('#modalLock').is_visible())
                        self.assertIn('Kontaktsperre', page.locator('#lfSide .lf-lock').inner_text())
                        self.assertIn('gesperrt', page.locator('#lfSide .lf-perm').inner_text())
                        self.assertEqual(page.locator('#lfNext summary button').count(), 0)
                        self.assertEqual(visible_primaries(page, '#modal'), ['Notiz erfassen'])
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'akte_gesperrt.png'))
                        page.locator('#closeModal').click()
                        page.locator('#modal').wait_for(state='hidden')

                        # „← Firmen“ führt zur gefilterten Liste
                        page.goto(base + '/#/firmen')
                        page.wait_for_load_state('networkidle')
                        page.fill('#leadSearch', 'Fiktiv')
                        page.wait_for_function('() => document.querySelectorAll("#leadRows tr.ui-row").length === 3')
                        page.locator('#leadRows tr', has_text='Fiktiv Software GmbH').click()
                        page.locator('#lfAgreed').wait_for()
                        self.assertIn('suche=Fiktiv', page.url)
                        page.locator('#closeModal').click()
                        try:
                            page.locator('#viewLeads').wait_for(state='visible')
                        except Exception as exc:  # selten (Baseline dev67): Zustand mitgeben, damit die Ursache sichtbar wird
                            state = page.evaluate('''() => JSON.stringify({hash: location.hash, view: typeof currentView !== 'undefined' ? currentView : null,
                                leads: document.getElementById('viewLeads').className, body: document.body.className,
                                modalHidden: document.getElementById('modal').classList.contains('hidden'), history: history.length})''')
                            raise AssertionError(f'Firmenliste nach „← Firmen“ nicht sichtbar: {state}') from exc
                        page.wait_for_function('() => document.querySelectorAll("#leadRows tr.ui-row").length === 3')
                        self.assertEqual(page.input_value('#leadSearch'), 'Fiktiv')
                        self.assertIn('suche=Fiktiv', page.url)
                        page.fill('#leadSearch', '')

                        # „＋ Neue Firma“: Überschrift „Neue Firma“, keine Reiter, Fokus im Namensfeld – über den Knopf und über Strg+K
                        page.locator('#newLeadBtn').click()
                        page.locator('#leadForm').wait_for(state='visible')
                        self.assertEqual(page.text_content('#modalTitle'), 'Neue Firma')
                        self.assertTrue(page.locator('#leadTabs').is_hidden())
                        self.assertEqual(visible_primaries(page, '#modal'), ['Firma speichern'])
                        self.assertEqual(lead_lines(page.evaluate(VISIBLE_TEXT, '#modal')), [])
                        page.wait_for_function('() => document.activeElement && document.activeElement.name === "company"')
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'neue_firma.png'))
                        page.keyboard.press('Escape')
                        page.locator('#modal').wait_for(state='hidden')
                        page.keyboard.press('Control+k')
                        page.locator('#gsInput').wait_for(state='visible')
                        page.locator('#gsInput').fill('neue fi')
                        page.locator('#gsResults [data-gs-kind="befehl"]', has_text='Neue Firma anlegen').click()
                        page.locator('#leadForm').wait_for(state='visible')
                        self.assertEqual(page.text_content('#modalTitle'), 'Neue Firma')
                        page.keyboard.press('Escape')
                        page.locator('#modal').wait_for(state='hidden')

                        # Kein sichtbares „Lead“ in den Bereichen
                        for address in ('#/firmen', '#/heute', '#/angebote', '#/abrechnen', '#/einstellungen'):
                            page.goto(base + '/' + address)
                            page.wait_for_load_state('networkidle')
                            view = page.evaluate(VIEW)
                            self.assertEqual(lead_lines(page.evaluate(VISIBLE_TEXT, view)), [], address)

                        # 390 × 844: kein waagerechtes Scrollen in der Akte
                        page.set_viewport_size({'width': 390, 'height': 844})
                        page.goto(base + f'/#/firmen/akte/{metal["id"]}')
                        page.wait_for_load_state('networkidle')
                        page.locator('#lfAgreed').wait_for()
                        for tab in TABS:
                            page.locator(f'[data-lf-tab="{tab}"]').click()
                            self.assertFalse(page.evaluate('() => document.documentElement.scrollWidth > window.innerWidth + 1'), tab)
                        if SHOTS:
                            page.locator('[data-lf-tab="ueberblick"]').click()
                            page.screenshot(path=str(Path(SHOTS) / 'akte_390.png'))

                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
