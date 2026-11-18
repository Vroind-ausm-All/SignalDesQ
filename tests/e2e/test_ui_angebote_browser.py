"""Browserprüfung 2.0.0-dev52 (UX Schritt 4): Bereich „Angebote“ auf dem UI-Baukasten.

- Drei Reiter mit Adressen: Angebote (#/angebote) · Aufträge & Betreuung (#/angebote/auftraege) · Auswertung (#/angebote/auswertung).
- Liste: Seitenkopf mit Anzahl und genau einer Hauptaktion, Werkzeugzeile (Suche, Ansichten, Filter), Spalten Angebot · Nächster Schritt ·
  Fällig · Status · Betrag netto; nächster Schritt aus vorhandenen Daten (Freigabe, Nachfassen, Kick-off).
- „＋ Neues Angebot“ öffnet den Editor (#/angebote?neu=1); Speichern führt in das geöffnete Angebot.
- Geöffnetes Angebot: Kopf mit „← Angebote“, Titel, Status und genau einer Hauptaktion je Phase (Entwurf → freigegeben → gesendet →
  angenommen durchgespielt), vier Reiter, Kontextspalte mit „Prüfung vor Freigabe“ und „Ablauf“; Adresse übersteht Neuladen und Zurück.
- Abnahmemaße bei 1280 × 720 mit 5 Angeboten: erste Angebotszeile ≤ 280 px, Positionen im geöffneten Angebot ab ≤ 260 px.
- 390 × 844 ohne waagerechtes Scrollen; keine Fehler im Browser, keine Abrufe nach außen. Fiktive Firmen.
Mit SIGNALDESK_E2E_SHOTS=<Ordner> entstehen Bildschirmfotos (hell und im dunklen Theme)."""
import datetime as dt
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from s5_helpers import confirm_need, release_offer  # noqa: E402

from sales_tool.model import connect  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402

SHOTS = os.environ.get('SIGNALDESK_E2E_SHOTS')
VIEWS = {'#/angebote': 'viewQuotes', '#/angebote/auftraege': 'viewOrders', '#/angebote/auswertung': 'viewInsights'}


def visible_view(page):
    return page.evaluate('() => [...document.querySelectorAll(".content")].find(e => !e.classList.contains("hidden"))?.id')


def primaries(page, scope='#viewQuotes'):
    return page.evaluate(f'() => [...document.querySelectorAll("{scope} .btn-primary")].filter(b => b.offsetParent !== null).map(b => b.textContent.trim())')


def top(page, selector):
    return page.evaluate(f'() => Math.round(document.querySelector({json.dumps(selector)}).getBoundingClientRect().top)')


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class UiAngeboteBrowserTests(unittest.TestCase):
    def test_list_editor_workplace_and_tabs(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'ang.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            def lead(name):
                return api('/leads', 'POST', {'company': name, 'stage': 'termin'})['id']

            ids = {k: lead(f'{k} Fiktiv GmbH') for k in ('Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon')}
            with connect(db) as conn:
                for k in ('Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon'):
                    confirm_need(conn, ids[k])
            mk = lambda k, label, pos: api('/workspace/proposals', 'POST', {'lead_id': ids[k], 'tax_mode': 'regel_19', 'project_label': label, 'positions': pos})
            draft = mk('Alpha', 'Logo & Geschäftsausstattung', [{'service': 'logo', 'size': 'S'}, {'service': 'texte', 'qty': 2, 'optional': True}])
            sent = mk('Beta', 'Website-Relaunch', [{'service': 'logo', 'size': 'M'}])
            won = mk('Gamma', 'Landingpage', [{'service': 'texte', 'qty': 3}])
            lost = mk('Epsilon', 'Broschüre', [{'service': 'logo', 'size': 'S'}])
            open_draft = mk('Alpha', 'Visitenkarten', [{'service': 'logo', 'size': 'S'}])
            with connect(db) as conn:
                for p in (sent, won, lost):
                    release_offer(conn, p['id'])
            api(f"/workspace/proposals/{sent['id']}", 'PATCH', {'status': 'gesendet_manuell', 'channel': 'email', 'follow_up': (dt.date.today() + dt.timedelta(days=3)).isoformat(), 'follow_reason': 'Entscheidung abwarten'})
            api(f"/workspace/proposals/{won['id']}", 'PATCH', {'status': 'gesendet_manuell', 'channel': 'email'})
            api(f"/workspace/proposals/{won['id']}", 'PATCH', {'status': 'angenommen', 'channel': 'email', 'person': 'Frau Beispiel'})
            api(f"/workspace/proposals/{lost['id']}", 'PATCH', {'status': 'gesendet_manuell', 'channel': 'post'})
            api(f"/workspace/proposals/{lost['id']}", 'PATCH', {'status': 'abgelehnt', 'channel': 'email'})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1280, 'height': 720})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)

                        # ---- Liste
                        page.goto(base + '/#/angebote')
                        page.wait_for_load_state('networkidle')
                        rows = page.locator('#quoteHistory .qt-row')
                        page.wait_for_function('() => document.querySelectorAll("#quoteHistory .qt-row").length === 5')
                        page.locator(f'.qt-row[data-quote-open="{sent["id"]}"] [data-qt-step]', has_text='Nachfassen').wait_for()
                        self.assertEqual(page.text_content('#qtList h1'), 'Angebote')
                        self.assertEqual(page.text_content('#qtCount'), '5 Angebote')
                        self.assertEqual(primaries(page), ['＋ Neues Angebot'])
                        first_row = top(page, '#quoteHistory .qt-row')
                        self.assertLessEqual(first_row, 280, 'erste Angebotszeile im ersten Bildschirm')
                        self.assertEqual(round(rows.first.bounding_box()['height']), 56)
                        heads = page.locator('#qtList .ui-row-head > span').all_inner_texts()
                        self.assertEqual([h.strip().lower() for h in heads[:5]], ['angebot', 'nächster schritt', 'fällig', 'status', 'betrag netto'])
                        row = lambda p: page.locator(f'.qt-row[data-quote-open="{p["id"]}"]')
                        self.assertIn('Nachfassen: Entscheidung abwarten', row(sent).inner_text())
                        self.assertIn('gesendet', row(sent).inner_text())
                        self.assertIn('Kick-off:', row(won).inner_text())
                        self.assertIn('angenommen', row(won).inner_text())
                        self.assertIn('abgelehnt', row(lost).inner_text())
                        self.assertIn('Entwurf', row(draft).inner_text())
                        self.assertRegex(row(draft).locator('[data-qt-step]').inner_text(), r'Zur Freigabe prüfen|Prüfpunkte klären')
                        self.assertRegex(row(open_draft).locator('[data-qt-step]').inner_text(), r'Zur Freigabe prüfen|Prüfpunkte klären: \d+ offen')
                        self.assertIn('Beta Fiktiv GmbH · ' + sent['number'], row(sent).inner_text())
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'angebote_liste.png'))
                        # Ansichten, Suche, Filter
                        page.locator('[data-qt-view="offen"]').click()
                        self.assertEqual(rows.count(), 3)
                        page.locator('[data-qt-view="angenommen"]').click()
                        self.assertEqual(rows.count(), 1)
                        page.locator('[data-qt-view="alle"]').click()
                        page.fill('#qtQ', 'gamma')
                        self.assertEqual(rows.count(), 1)
                        page.fill('#qtQ', sent['number'])
                        self.assertEqual(rows.count(), 1)
                        page.fill('#qtQ', '')
                        page.locator('#qtFilterBtn').click()
                        page.select_option('#qtStatus', 'abgelehnt')
                        self.assertEqual(rows.count(), 1)
                        self.assertIn('1 von 5', page.text_content('#qtCount'))
                        page.locator('#qtReset').click()
                        self.assertEqual(rows.count(), 5)

                        # ---- Reiter des Bereichs mit Adressen
                        tabs = page.locator('#areaBar .area-tabs[data-area="angebote"] [data-area-view]')
                        self.assertEqual(tabs.all_inner_texts(), ['Angebote', 'Aufträge & Betreuung', 'Auswertung'])
                        page.locator('#areaBar [data-area-view="orders"]').click()
                        page.wait_for_function('() => location.hash === "#/angebote/auftraege"')
                        self.assertEqual(visible_view(page), 'viewOrders')
                        od = page.locator(f'#odRows [data-od="{won["id"]}"]')
                        od.wait_for()
                        self.assertIn('Projektkompass', od.locator('[data-od-kickoff]').inner_text())  # Stand des Kick-offs aus /bestand
                        page.locator(f'.pk-card[data-pk="{won["id"]}"]').wait_for()
                        page.locator(f'[data-cr-firm="{ids["Gamma"]}"]').wait_for()
                        self.assertEqual(primaries(page, '#viewOrders'), [])
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'angebote_auftraege.png'))
                        page.locator('#areaBar [data-area-view="insights"]').click()
                        page.wait_for_function('() => location.hash === "#/angebote/auswertung"')
                        self.assertEqual(visible_view(page), 'viewInsights')
                        for box in ('#lessonBox', '#stBox', '#lnBox'):
                            self.assertTrue(page.locator(box).is_visible(), box)
                        page.locator('#lnBox > summary').click()
                        page.locator('#lnLimits li').first.wait_for()
                        page.locator('#stBox > summary').click()
                        page.locator('#stCreate').wait_for()
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'angebote_auswertung.png'))
                        for address, view in VIEWS.items():  # Adressen direkt aufrufen
                            page.goto(base + '/' + address)
                            page.wait_for_function(f'() => !document.getElementById("{view}").classList.contains("hidden")')
                        # Aus „Aufträge & Betreuung“ öffnet die Zeile den Auftrag
                        page.goto(base + '/#/angebote/auftraege')
                        page.locator(f'#odRows [data-od="{won["id"]}"]').click()
                        page.wait_for_function(f'() => location.hash === "#/angebote?angebot={won["id"]}"')
                        page.locator('#ofKickoff').wait_for()
                        self.assertEqual(page.text_content('#qtMain'), 'Projektstart festlegen')

                        # ---- Neues Angebot: Editor als eigene Ansicht, Speichern führt ins Angebot
                        page.locator('#qtOffer [data-qt-back]').click()
                        page.wait_for_function('() => location.hash === "#/angebote"')
                        page.locator('#qtNew').click()
                        page.wait_for_function('() => location.hash === "#/angebote?neu=1"')
                        self.assertTrue(page.locator('#qtEdit').is_visible())
                        self.assertTrue(page.locator('#qtList').is_hidden())
                        self.assertEqual(page.text_content('#qtEditTitle'), 'Neues Angebot')
                        self.assertEqual(primaries(page), ['Angebot als Entwurf speichern'])
                        page.select_option('#quoteForm [name=lead_id]', str(ids['Delta']))
                        page.select_option('#qbService', 'logo')
                        page.locator('#qbAdd').click()
                        page.fill('#quoteForm [name=project_label]', 'Logo für Delta')
                        page.select_option('#quoteForm [name=tax_mode]', 'regel_19')
                        page.locator('#quoteCustomer .qb-table').wait_for()
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'angebote_neu.png'))
                        page.locator('#quoteForm button[type=submit]').click()
                        page.wait_for_function('() => /^#\\/angebote\\?angebot=\\d+$/.test(location.hash)')
                        new_id = int(page.evaluate('location.hash.split("=")[1]'))
                        page.locator('#qtOffer').wait_for()
                        self.assertTrue(page.locator('#qtEdit').is_hidden())

                        # ---- Arbeitsplatz: Entwurf
                        page.locator('#qtTitle', has_text='Logo für Delta').wait_for()
                        page.locator('#qtMain', has_text='Zur Freigabe prüfen').wait_for()
                        self.assertEqual(page.text_content('#qtPill'), 'Entwurf')
                        self.assertIn('Delta Fiktiv GmbH', page.text_content('#qtMeta'))
                        self.assertEqual(primaries(page), ['Zur Freigabe prüfen'])
                        self.assertEqual(page.locator('#qtTabs [data-qt-tab]').all_inner_texts(), ['Positionen', 'Kundenvorschau', 'Interne Kalkulation', 'Verlauf'])
                        self.assertTrue(page.locator('#qtChecks').is_visible())
                        self.assertIn('Bedarf ist im Gespräch bestätigt', page.text_content('#qtCheckList'))
                        self.assertIn('Bedarf', page.locator('#qtPhases .qt-phase.is-done').first.inner_text())
                        self.assertRegex(page.locator('#qtPhases .qt-phase.is-current').inner_text(), r'Entwurf|Freigabe')
                        self.assertEqual(round(page.locator('#qtChecks').bounding_box()['width']), 320)
                        self.assertLessEqual(top(page, '#qtTitle'), 100)
                        self.assertLessEqual(top(page, '#qtTabs'), 160)
                        self.assertLessEqual(top(page, '#qtPositions .qt-pos-row'), 260, 'Positionen beginnen im ersten Bildschirm')
                        self.assertLessEqual(top(page, '#qtMain') + 36, 720)
                        # spätere Phasen als Vorschau: Versand und Entscheidung eingeklappt
                        self.assertIsNone(page.locator('#ofSend details.of-later').get_attribute('open'))
                        self.assertTrue(page.locator('#ofSend [data-of-sent]').is_hidden())
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'angebot_entwurf.png'))
                        # Reiter
                        page.locator('[data-qt-tab="kunde"]').click()
                        self.assertTrue(page.locator('#qtSlotCustomer #quoteCustomer').is_visible())
                        self.assertTrue(page.locator('#qtPositions').is_hidden())
                        page.locator('[data-qt-tab="intern"]').click()
                        self.assertTrue(page.locator('#qtSlotInternal #quoteInternal').is_visible())
                        page.locator('[data-qt-tab="verlauf"]').click()
                        self.assertIn('Angebot erstellt', page.locator('#qtHistory').inner_text())
                        page.locator('[data-qt-tab="positionen"]').click()
                        # Hauptaktion springt zur Freigabe (gibt nichts frei)
                        page.locator('#qtMain').click()
                        page.wait_for_function('() => document.activeElement?.closest("#ofRelease") !== null')
                        self.assertEqual(api(f'/workspace/proposals/{new_id}/versand')['released'], False)
                        for box in page.locator('#ofRelease [data-of-confirm]').all():
                            box.check()
                        page.locator('#ofRelease [data-of-release]').click()
                        page.locator('#qtMain', has_text='Als gesendet markieren').wait_for()
                        self.assertEqual(page.text_content('#qtPill'), 'freigegeben')
                        self.assertIn('Freigegeben am', page.text_content('#qtCheckList'))
                        self.assertTrue(page.locator('#qtPhases .qt-phase.is-current', has_text='Versand').is_visible())
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'angebot_freigegeben.png'))
                        page.locator('#qtMain').click()
                        page.wait_for_function('() => document.activeElement?.closest("#ofSend") !== null')
                        page.locator('#ofSend [data-of-sent]').click()
                        page.locator('#qtMain', has_text='Annahme dokumentieren').wait_for()
                        self.assertEqual(page.text_content('#qtPill'), 'gesendet')
                        self.assertEqual(primaries(page), ['Annahme dokumentieren'])
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'angebot_gesendet.png'))
                        page.locator('#qtMain').click()
                        page.fill('#ofDecision [data-of-person]', 'Herr Beispiel')
                        page.locator('#ofDecision [data-of-decide="angenommen"]').click()
                        page.locator('#qtMain', has_text='Projektstart festlegen').wait_for()
                        self.assertEqual(page.text_content('#qtPill'), 'angenommen')
                        page.locator('#ofStart [data-of-start]').click()
                        page.locator('#qtMain', has_text='Kick-off vorbereiten').wait_for()
                        self.assertTrue(page.locator('#ofKickoff').is_visible())
                        self.assertTrue(page.locator('#ofHandover').is_visible())
                        self.assertTrue(page.locator(f'[data-of-addendum="{new_id}"]').is_visible(), 'Nachtrag nach Annahme erreichbar')
                        self.assertEqual(page.locator('#qtPhases .qt-phase.is-done').count(), 5)
                        page.locator('[data-qt-tab="verlauf"]').click()
                        hist = page.locator('#qtHistory').inner_text()
                        for event in ('Versandfassung freigegeben', 'Als versendet dokumentiert', 'Zusage dokumentiert', 'Nachgefasst'):
                            self.assertIn(event, hist)
                        page.locator('[data-qt-tab="positionen"]').click()
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'angebot_angenommen.png'))

                        # ---- Adresse: Neuladen und Zurück
                        page.reload()
                        page.wait_for_load_state('networkidle')
                        page.locator('#qtTitle', has_text='Logo für Delta').wait_for()
                        page.locator('#qtOffer [data-qt-back]').click()
                        page.wait_for_function('() => location.hash === "#/angebote"')
                        page.locator(f'.qt-row[data-quote-open="{draft["id"]}"]').focus()
                        page.keyboard.press('Enter')  # Tastatur öffnet die Zeile
                        page.wait_for_function(f'() => location.hash === "#/angebote?angebot={draft["id"]}"')
                        page.locator('#qtTitle', has_text='Logo & Geschäftsausstattung').wait_for()
                        page.go_back()
                        page.locator('#qtList').wait_for()
                        page.go_back()
                        page.locator('#qtTitle', has_text='Logo für Delta').wait_for()
                        self.assertTrue(page.locator('#qtList').is_hidden())

                        # ---- Schmal: keine waagerechte Rolle
                        page.set_viewport_size({'width': 390, 'height': 844})
                        page.wait_for_timeout(100)
                        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 391)
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'angebot_mobil.png'))
                        page.locator('#qtOffer [data-qt-back]').click()
                        page.locator('#qtList').wait_for()
                        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 391)
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'angebote_liste_mobil.png'))

                        # ---- Dunkles Theme (nur Bildschirmfotos)
                        if SHOTS:
                            api('/ui/appearance', 'PUT', {'theme': 'schiefer', 'mode': 'dunkel', 'density': 'normal'})
                            page.set_viewport_size({'width': 1280, 'height': 720})
                            page.goto(base + '/#/angebote')
                            page.reload()
                            page.wait_for_load_state('networkidle')
                            page.screenshot(path=str(Path(SHOTS) / 'angebote_liste_dunkel.png'))
                            page.goto(base + f'/#/angebote?angebot={draft["id"]}')
                            page.locator('#qtTitle', has_text='Logo & Geschäftsausstattung').wait_for()
                            page.wait_for_load_state('networkidle')
                            page.screenshot(path=str(Path(SHOTS) / 'angebot_entwurf_dunkel.png'))
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
