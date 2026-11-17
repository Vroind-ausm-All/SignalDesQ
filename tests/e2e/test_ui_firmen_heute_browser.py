"""Browserprüfung 2.0.0-dev50 (visuelle Konsolidierung, Schritt 2): Rahmen, Firmenliste und Heute aus dem UI-Baukasten.

Abnahme (1280 × 720, 9 fiktive Firmen):
- Firmen: erste Firmenzeile beginnt bei höchstens 280 px, mindestens 7 Zeilen ganz sichtbar, Zeilen 56 px, Inhaltsschrift
  nicht kleiner als vorher (12 px).
- Heute: die Liste „Als Nächstes“ beginnt bei höchstens 200 px.
- Kopfzeile ohne Hauptaktion, ohne Datum und ohne Hell/Dunkel; im Seitenkopf von Firmen und Heute genau eine sichtbare Hauptaktion.
- „Neue Firma“ über den Knopf und über Strg+K; „Filter“ enthält Phase, Zurücksetzen, CSV-Import; „Spalten“ schaltet eine Spalte;
  „Weitere“ enthält die übrigen Ansichten und „Ansicht speichern“.
- Klick auf eine Zeile öffnet die Akte, „Zurück“ führt zur gefilterten Liste; Enter auf der Zeile öffnet ebenfalls.
- Heute: Klappzeilen mit Kurzstand, die ihren Inhalt öffnen; „Erledigt“ hakt ab, ohne die Akte zu öffnen.
- 390 × 844: kein waagerechtes Scrollen, Menü erreichbar. Keine Seitenfehler, keine Abrufe nach außen.
Nur fiktive Firmen."""
import datetime as dt
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
FOLDS = ('erreichbarkeit', 'wiedervorlage', 'tdPotBox', 'tagesabschluss', 'tdStatusBox')
ROWS = 'document.querySelectorAll("#leadRows tr.ui-row").length'


def visible_primaries(page, scope):
    return page.evaluate(f'() => [...document.querySelectorAll("{scope} .btn-primary")].filter(b => b.offsetParent !== null).map(b => b.textContent.trim())')


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class UiFirmenHeuteBrowserTests(unittest.TestCase):
    def test_frame_company_list_and_today(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'u.sqlite3'
            with connect(db) as conn:
                init_db(conn)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, body=None, method=None):
                req = urllib.request.Request(base + '/api' + path, method=method or ('POST' if body is not None else 'GET'),
                                             headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read())

            day = lambda n: (dt.date.today() + dt.timedelta(days=n)).isoformat()
            firms = [('Musterwerk Studio GmbH', 'angebot', 'Angebot besprechen', day(-1)), ('Beispiel Metall GmbH', 'termin', 'Rückruf durchführen', day(0)),
                     ('Demo Architektur GmbH', 'recherche', 'Website prüfen', day(1)), ('Fiktiv Software GmbH', 'termin', 'Bedarf klären', day(-1)),
                     ('Musterpraxis Beispiel', 'qualifiziert', 'Kontaktweg prüfen', day(0)), ('Beispiel Druck KG', 'qualifiziert', 'Gespräch vorbereiten', day(2)),
                     ('Demo Garten GmbH', 'kontakt', 'Unterlagen schicken', day(-2)), ('Fiktiv Handel GmbH', 'angebot', 'Umfang abstimmen', day(4)),
                     ('Beispiel Bau GmbH', 'antwort', 'Nachfassen', day(5))]
            ids = {}
            for name, stage, step, date in firms:
                ids[name] = api('/leads', {'company': name, 'location': 'Stuttgart', 'stage': stage, 'industry': 'Sonstige', 'employees': 12,
                                           'next_step': step, 'next_date': date})['id']
            task = api('/tasks', {'title': 'Muster an Fiktiv Software senden', 'due_date': day(-5), 'lead_id': ids['Fiktiv Software GmbH']})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1280, 'height': 720})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base + '/#/firmen')
                        page.wait_for_load_state('networkidle')
                        page.wait_for_function(f'() => {ROWS} === 9')

                        # Rahmen: eine Kopfzeile mit den Reitern des Bereichs und der Suche – ohne Hauptaktion, Datum, Hell/Dunkel
                        top = page.locator('.topbar').bounding_box()
                        self.assertLessEqual(round(top['height']), 53)
                        self.assertTrue(page.locator('.topbar [data-area-view="pipeline"]').is_visible())
                        self.assertTrue(page.locator('#gsOpen').is_visible())
                        self.assertEqual(visible_primaries(page, '.topbar'), [])
                        for gone in ('#modeToggle', '.date-chip', '#newLeadBtn2'):
                            self.assertEqual(page.locator(gone).count(), 0, gone)
                        self.assertFalse(page.locator('.breadcrumb').is_visible())
                        page.locator('.sidebar [data-area="abrechnen"]').click()  # Bereich mit nur einer Ansicht: keine Reiter (dev52: Angebote hat drei)
                        self.assertFalse(page.locator('#areaBar .area-tabs[data-area="abrechnen"]').is_visible())
                        page.locator('.sidebar [data-area="firmen"]').click()
                        page.wait_for_function(f'() => {ROWS} === 9')

                        # Abnahmemaß Firmen
                        m = page.evaluate('''() => { const r = [...document.querySelectorAll("#leadRows tr.ui-row")];
                            return {top: r[0].getBoundingClientRect().top, full: r.filter(x => x.getBoundingClientRect().bottom <= innerHeight).length,
                                    h: r[0].getBoundingClientRect().height, font: parseFloat(getComputedStyle(r[0].querySelector("td b")).fontSize)}; }''')
                        self.assertLessEqual(m['top'], 280, m)
                        self.assertGreaterEqual(m['full'], 7, m)
                        self.assertEqual(round(m['h']), 56, m)
                        self.assertGreaterEqual(m['font'], 12, m)
                        heads = page.evaluate('() => [...document.querySelectorAll("#leadHead th")].map(t => t.textContent.trim())')
                        self.assertEqual(heads[:5], ['FIRMA', 'NÄCHSTER SCHRITT', 'FÄLLIG', 'PHASE', 'PASSUNG'])
                        overdue = page.locator('#leadRows tr', has_text='Demo Garten GmbH').locator('.ui-pill.is-overdue')
                        self.assertEqual(overdue.inner_text(), 'überfällig')  # Fälligkeit als Status-Pille
                        self.assertEqual(page.locator('#leadRows tr', has_text='Beispiel Metall GmbH').locator('.ui-pill.is-attention').inner_text(), 'heute')
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'firmen_1280.png'))

                        # genau eine Hauptaktion: „+ Neue Firma“ im Seitenkopf
                        self.assertEqual(visible_primaries(page, '#viewLeads'), ['＋ Neue Firma'])
                        self.assertEqual(visible_primaries(page, '#viewLeads .ui-head'), ['＋ Neue Firma'])
                        page.locator('#newLeadBtn').click()
                        page.locator('#leadForm').wait_for(state='visible')
                        page.wait_for_function('() => document.activeElement && document.activeElement.name === "company"')
                        page.keyboard.press('Escape')  # nichts eingegeben: schließt ohne Rückfrage
                        page.locator('#modal').wait_for(state='hidden')
                        # … und als Befehl in der globalen Suche
                        page.keyboard.press('Control+k')
                        page.locator('#gsInput').wait_for(state='visible')
                        self.assertEqual(page.locator('#gsResults [data-gs-kind="befehl"]').inner_text().split('\n')[0], 'Neue Firma anlegen')
                        page.locator('#gsInput').fill('neue fi')
                        page.locator('#gsResults [data-gs-kind="befehl"]', has_text='Neue Firma anlegen').wait_for()
                        page.locator('#gsResults [data-gs-kind="befehl"]').click()
                        page.locator('#leadForm').wait_for(state='visible')
                        self.assertTrue(page.locator('#gsBackdrop').is_hidden())
                        page.keyboard.press('Escape')
                        page.locator('#modal').wait_for(state='hidden')

                        # Werkzeugzeile: Reihenfolge Suche · Ansichten · Weitere · Filter · Spalten
                        order = page.evaluate('() => [...document.querySelector("#viewLeads .ui-tool").children].map(e => e.id)')
                        self.assertEqual(order, ['leadSearch', 'leadViews', 'leadMore', 'leadFilterMenu', 'leadColsMenu'])
                        # Filter ▾: Phase, Zurücksetzen, CSV importieren
                        self.assertFalse(page.locator('#stageFilter').is_visible())
                        page.locator('#leadFilterMenu > summary').click()
                        for sel in ('#stageFilter', '#resetFilter', '#leadFilterMenu .import-label'):
                            self.assertTrue(page.locator(sel).is_visible(), sel)
                        self.assertEqual(page.locator('#leadFilterMenu #csvImport').count(), 1)
                        page.select_option('#stageFilter', 'angebot')
                        page.wait_for_function(f'() => {ROWS} === 2')
                        self.assertIn('phase=angebot', page.url)
                        self.assertIn('2 von 9 Firmen', page.text_content('#leadFilterInfo'))
                        page.locator('#resetFilter').click()
                        page.wait_for_function(f'() => {ROWS} === 9')
                        page.wait_for_function('() => !document.getElementById("leadFilterMenu").open')  # Knopf im Menü schließt es
                        # Spalten ▾ schaltet eine Spalte
                        page.locator('#leadColsMenu > summary').click()
                        self.assertTrue(page.locator('#leadFilterMenu').evaluate('d => !d.open'), 'nur ein Menü offen')
                        page.check('[data-ll-col="last"]')
                        self.assertIn('LETZTER KONTAKT', page.text_content('#leadHead'))
                        self.assertEqual(page.locator('#leadRows tr.ui-row').first.locator('td').count(), 7)
                        page.uncheck('[data-ll-col="last"]')
                        self.assertNotIn('LETZTER KONTAKT', page.text_content('#leadHead'))
                        page.keyboard.press('Escape')
                        page.wait_for_function('() => !document.getElementById("leadColsMenu").open')
                        # Ansichten: häufige als Reiter, die übrigen und „Ansicht speichern“ unter „Weitere ▾“
                        tabs = page.evaluate('() => [...document.querySelectorAll("#leadViews [data-ll-preset]")].map(b => b.dataset.llPreset)')
                        self.assertEqual(tabs, ['alle', 'heute', 'ohne_schritt'])
                        page.locator('#leadMore > summary').click()
                        more = page.evaluate('() => [...document.querySelectorAll("#leadMoreBody [data-ll-preset]")].map(b => b.dataset.llPreset)')
                        self.assertEqual(more, ['angebote', 'recherche', 'passung_ab', 'kunden'])
                        self.assertTrue(page.locator('#leadMoreBody [data-ll-save]').is_visible())
                        page.locator('#leadMoreBody [data-ll-preset="recherche"]').click()
                        page.wait_for_function(f'() => {ROWS} === 1')
                        self.assertIn('ansicht=recherche', page.url)
                        self.assertEqual(page.text_content('#leadMoreBtn'), 'Recherche prüfen ▾')  # die gewählte Ansicht bleibt sichtbar
                        page.locator('#leadViews [data-ll-preset="alle"]').click()
                        page.wait_for_function(f'() => {ROWS} === 9')

                        # Zeile öffnet die Akte; „← Zurück“ führt zur gefilterten Liste
                        page.fill('#leadSearch', 'Fiktiv')
                        page.wait_for_function(f'() => {ROWS} === 2')
                        page.locator('#leadRows tr', has_text='Fiktiv Handel GmbH').click()
                        page.locator('#leadTabs').wait_for(state='visible')
                        self.assertIn(f"#/firmen/akte/{ids['Fiktiv Handel GmbH']}?suche=Fiktiv", page.url)
                        page.locator('#closeModal').click()
                        page.locator('#modal').wait_for(state='hidden')
                        page.wait_for_function(f'() => {ROWS} === 2')
                        self.assertEqual(page.input_value('#leadSearch'), 'Fiktiv')
                        self.assertIn('suche=Fiktiv', page.url)
                        # Tastatur: Enter auf der Zeile öffnet ebenfalls, Zurück im Browser schließt
                        page.locator('#leadRows tr', has_text='Fiktiv Software GmbH').focus()
                        page.keyboard.press('Enter')
                        page.locator('#leadTabs').wait_for(state='visible')
                        page.go_back()
                        page.locator('#modal').wait_for(state='hidden')
                        self.assertEqual(page.input_value('#leadSearch'), 'Fiktiv')
                        page.fill('#leadSearch', '')

                        # Heute: Abnahmemaß, Hauptaktion, Statuszeile
                        page.locator('.sidebar [data-area="heute"]').click()
                        first = page.locator('#tdFocusList .td-focus-item').first
                        first.wait_for()
                        self.assertLessEqual(page.locator('#tdFocus').bounding_box()['y'], 200)
                        self.assertEqual(visible_primaries(page, '#viewDashboard'), ['＋ Neuer Eingang'])
                        self.assertEqual(visible_primaries(page, '#viewDashboard .ui-head'), ['＋ Neuer Eingang'])
                        self.assertTrue(page.locator('#viewDashboard .ui-head .ui-meta').inner_text().strip())  # Datum als Zusatz
                        page.wait_for_function('() => /als Nächstes/.test(document.getElementById("tdStrip").textContent) && /Kapazität/.test(document.getElementById("tdStrip").textContent)')
                        self.assertIn('in der Wiedervorlage', page.text_content('#tdStrip'))
                        self.assertIn('Einrichtung', page.text_content('#tdStrip'))  # noch nicht eingerichtet → ein Hinweis
                        heads = page.evaluate('() => [...document.querySelectorAll("#tdFocus .ui-row-head > span")].map(s => s.textContent.trim()).filter(Boolean)')
                        self.assertEqual(heads, ['Als Nächstes', 'Warum jetzt', 'Fällig', 'Phase'])
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'heute_1280.png'))

                        # Klappzeilen: Kurzstand im geschlossenen Zustand, Öffnen zeigt den Inhalt
                        for fold in FOLDS:
                            d = page.locator(f'#{fold}')
                            self.assertFalse(d.evaluate('d => d.open'), fold)
                            page.wait_for_function(f'() => document.querySelector("#{fold} > summary > span").textContent.trim() !== ""')
                            self.assertFalse(d.locator('.ui-fold-body').is_visible(), fold)
                            d.locator('summary').click()
                            d.locator('.ui-fold-body').wait_for(state='visible')
                            d.locator('summary').click()
                            d.locator('.ui-fold-body').wait_for(state='hidden')
                        page.locator('#tdPotBox > summary').click()
                        page.locator('#rcCap .sw-web').wait_for()  # Inhalte unverändert in der Klappzeile
                        page.locator('#tdStages .td-stage').first.wait_for()
                        page.locator('#tdPotBox > summary').click()
                        # „+ Neuer Eingang“ öffnet das Erfassen eines Eingangs
                        page.locator('#tdNewInbound').click()
                        page.wait_for_function('() => document.activeElement && document.activeElement.name === "who" && document.getElementById("erreichbarkeit").open')
                        page.locator('#erreichbarkeit > summary').click()

                        # „Erledigt“ hakt die Aufgabe ab und öffnet nicht die Akte
                        row = page.locator('#tdFocusList .td-focus-item', has_text='Muster an Fiktiv Software senden')
                        self.assertEqual(row.locator('[data-td-done]').inner_text(), 'Erledigt')
                        before = page.url
                        row.locator('[data-td-done]').click()
                        row.wait_for(state='detached')
                        self.assertTrue(page.locator('#modal').is_hidden(), 'Erledigt öffnet keine Akte')
                        self.assertEqual(page.url, before)
                        self.assertTrue(next(t for t in api('/tasks') if t['id'] == task['id'])['done'])
                        # … und die Zeile selbst öffnet die Akte
                        first = page.locator('#tdFocusList .td-focus-item').first
                        self.assertEqual(first.locator('[data-td-done]').count(), 0)
                        name = first.locator('.ui-main small').inner_text()
                        first.click()
                        page.locator('#leadTabs').wait_for(state='visible')
                        self.assertEqual(page.text_content('#modalTitle'), name)
                        page.locator('#closeModal').click()
                        page.locator('#modal').wait_for(state='hidden')
                        self.assertNotIn('Lead', page.locator('#viewDashboard').inner_text())  # Begriff: „Firma“, nicht „Lead“

                        # Darstellung: Hell/Dunkel/System weiter unter Einstellungen → Darstellung
                        page.locator('.sidebar [data-area="einstellungen"]').click()
                        page.locator('[data-ap-mode]').first.wait_for()
                        self.assertEqual(page.evaluate('() => [...document.querySelectorAll("[data-ap-mode]")].map(b => b.dataset.apMode)'), ['system', 'hell', 'dunkel'])

                        # schmal: kein waagerechtes Scrollen, Menü erreichbar
                        page.set_viewport_size({'width': 390, 'height': 844})
                        for address in ('/#/firmen', '/#/heute'):
                            page.goto(base + address)
                            page.wait_for_load_state('networkidle')
                            page.wait_for_timeout(300)
                            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 390, address)
                            self.assertTrue(page.locator('#navMenuBtn').is_visible())
                            if SHOTS:
                                page.screenshot(path=str(Path(SHOTS) / f'{address[3:]}_390.png'))
                        page.goto(base + '/#/firmen')
                        page.wait_for_load_state('networkidle')
                        for menu in ('#leadMore', '#leadFilterMenu', '#leadColsMenu'):
                            page.locator(f'{menu} > summary').click()
                            body = page.locator(f'{menu} .ui-menu-body').bounding_box()
                            self.assertGreaterEqual(body['x'], 0, menu)
                            self.assertLessEqual(body['x'] + body['width'], 390, menu)
                            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 390, menu)
                        page.keyboard.press('Escape')
                        page.locator('#navMenuBtn').click()
                        page.locator('#sideNav').wait_for(state='visible')
                        page.keyboard.press('Escape')
                        page.locator('#sideNav').wait_for(state='hidden')

                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
