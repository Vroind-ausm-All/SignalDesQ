"""Browserprüfung 2.0.0-dev53 (UX Schritt 5): Einstellungen und Abrechnen auf dem UI-Baukasten.

Einstellungen
- Abschnittsliste links (240 px) mit Kurzstand, Inhalt rechts; Seitenkopf „Einstellungen“ mit dem Abschnitt als Zusatz und ohne Hauptaktion.
- Jeder der neun Abschnitte ist über seine Adresse (#/einstellungen?abschnitt=…) und über die Liste erreichbar; KI-Werkzeuge und
  Hilfe & Playbook sind eigene Ansichten mit derselben Liste, ihre bisherigen Adressen gelten weiter.
- Alle bisherigen Sprungziele (Element-IDs wie kalender, targetProfile, ownTimes, zugang, Verweise aus Angeboten, Finden, Abrechnen und
  „Heute“) öffnen den Abschnitt, der sie enthält. #/einstellungen öffnet den zuletzt benutzten Abschnitt (sonst „Meine Firma“).
- Kurzstand mit gelber Warnung (Pflichtangaben für Rechnungen fehlen, noch keine Sicherung).
- Eingabeschutz beim Abschnittswechsel: Weiter bearbeiten · Verwerfen · Speichern.
- Suche über die Einstellungen filtert die Liste, Enter öffnet den ersten passenden Abschnitt.
Abrechnen
- Vier Reiter mit Adressen; Rechnungen mit Seitenkopf, Anzahl und genau einer Hauptaktion „＋ Neue Rechnung“, Werkzeugzeile (Suche, Ansichten,
  Filter), Liste Rechnung · Nächster Schritt · Fällig · Status · Betrag brutto; nächster Schritt nur aus vorhandenen Daten.
- „＋ Neue Rechnung“ öffnet den Editor; die Stammdaten-Warnung springt nach Einstellungen → Meine Firma.
Abnahmemaße bei 1280 × 720: Inhalt der Einstellungen ab ≤ 200 px; mit 4 Rechnungen erste Rechnungszeile ≤ 280 px. 390 × 844 ohne
waagerechtes Scrollen; keine Fehler im Browser, keine Abrufe nach außen. Fiktive Firmen.
Mit SIGNALDESK_E2E_SHOTS=<Ordner> entstehen Bildschirmfotos."""
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

from sales_tool import accounting as acc
from sales_tool.model import connect
from sales_tool.server import make_handler, prepare_database

SHOTS = os.environ.get('SIGNALDESK_E2E_SHOTS')
SELLER = {'company_name': 'Beispiel Studio', 'owner_name': 'Alex Muster', 'street': 'Musterweg 1', 'zip': '20457', 'city': 'Hamburg',
          'tax_number': '22/123/45678', 'email': 'rechnung@studio.example', 'iban': 'DE89 3704 0044 0532 0130 00'}
SECTIONS = ['firma', 'preise', 'zielkunden', 'darstellung', 'kalender', 'datenquellen', 'sicherung', 'ki-werkzeuge', 'hilfe']
LABELS = {'firma': 'Meine Firma', 'preise': 'Leistungen & Preise', 'zielkunden': 'Zielkunden', 'darstellung': 'Darstellung',
          'kalender': 'Kalender & Postfach', 'datenquellen': 'Datenquellen', 'sicherung': 'Sicherung & Zugang', 'ki-werkzeuge': 'KI-Werkzeuge',
          'hilfe': 'Hilfe & Playbook'}
# bisherige Sprungziele (Element-IDs aus der langen Seite, Verweise anderer Seiten) → Abschnitt
OLD_TARGETS = {'kalender': 'kalender', 'datenquellen': 'datenquellen', 'preise': 'preise', 'darstellung': 'darstellung',
               'targetProfile': 'zielkunden', 'ownTimes': 'kalender', 'leistungsprofil': 'preise', 'gewichte': 'zielkunden',
               'zugang': 'sicherung', 'offline': 'sicherung', 'rtPanel': 'datenquellen', 'qbSettingsBox': 'preise', 'osmBox': 'datenquellen',
               'catBox': 'datenquellen', 'swCheckBox': 'datenquellen', 'accBackupBox': 'sicherung', 'firma': 'firma'}
ACC_TABS = [('accounting', 'Rechnungen', '#/abrechnen', 'viewAccounting'), ('expenses', 'Ausgaben', '#/abrechnen/ausgaben', 'viewExpenses'),
            ('revenue', 'Auswertung', '#/abrechnen/auswertung', 'viewRevenue'), ('tax', 'Steuer & Export', '#/abrechnen/steuer', 'viewTax')]


def visible_view(page):
    return page.evaluate('() => [...document.querySelectorAll(".content")].find(e => !e.classList.contains("hidden"))?.id')


def head_primaries(page):
    return page.evaluate('''() => { const v = [...document.querySelectorAll(".content")].find(e => !e.classList.contains("hidden"));
      return [...v.querySelectorAll(".ui-head .btn-primary")].filter(b => b.offsetParent !== null).map(b => b.textContent.trim()); }''')


def top(page, selector):
    return page.evaluate(f'() => Math.round(document.querySelector({json.dumps(selector)}).getBoundingClientRect().top)')


def shown_section(page):
    return page.evaluate('() => [...document.querySelectorAll("#viewSettings .es-sec")].filter(s => !s.classList.contains("hidden")).map(s => s.dataset.es).join(",")')


def no_hscroll(page):
    return page.evaluate('() => document.documentElement.scrollWidth <= window.innerWidth + 1')


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class UiEinstellungenAbrechnenBrowserTests(unittest.TestCase):
    def test_settings_sections_and_billing_tabs(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'ea.sqlite3'
            prepare_database(db)
            today = dt.date.today()
            ago = lambda n: (today - dt.timedelta(days=n)).isoformat()
            with connect(db) as conn:
                acc.save_settings(conn, SELLER)
                ids = []
                for who, what, issue, price, kind in (('Beispiel Bau GmbH', 'Landingpage', ago(40), '1150', 'abschlag'),
                                                      ('Demo Garten GmbH', 'Pflege Oktober', ago(35), '89', 'rechnung'),
                                                      ('Demo Garten GmbH', 'Pflege November', ago(5), '89', 'rechnung'),
                                                      ('Beispiel Druck KG', 'Flyer', '', '600', 'rechnung')):
                    inv = acc.create_invoice(conn, {'buyer_name': who, 'buyer_street': 'Werkstraße 5', 'buyer_zip': '70173', 'buyer_city': 'Stuttgart',
                                                    'buyer_email': 'buchhaltung@beispiel.example', 'service_from': issue or today.isoformat(),
                                                    'issue_date': issue, 'kind': kind, 'payment_days': 14,
                                                    'lines': [{'description': what, 'quantity': 1, 'unit': 'pauschal', 'unit_price_eur': price, 'vat_rate': 19}]})
                    if issue:
                        inv = acc.finalize_invoice(conn, inv['id'])
                    ids.append(inv)
                acc.add_payment(conn, ids[1]['id'], {'paid_on': ago(20)})
                acc.save_settings(conn, {'tax_number': ''})  # Pflichtangabe fehlt: Steuernummer oder USt-IdNr.
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            api('/leads', 'POST', {'company': 'Beispiel Bau GmbH', 'stage': 'angebot'})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1280, 'height': 720})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)

                        def go(hash_):
                            page.goto(base + '/' + hash_)
                            page.wait_for_load_state('networkidle')

                        def state(key):
                            return page.locator(f'[data-es-state="{key}"]')

                        # ---- Einstellungen: erster Abschnitt, Seitenkopf ohne Hauptaktion, Abnahmemaß
                        go('#/einstellungen')
                        self.assertEqual(visible_view(page), 'viewSettings')
                        page.wait_for_function('() => location.hash.includes("abschnitt=firma")')
                        self.assertEqual(shown_section(page), 'firma')
                        self.assertEqual(page.text_content('#esTitle'), 'Einstellungen')
                        self.assertEqual(page.text_content('#esMeta'), 'Meine Firma')
                        self.assertEqual(head_primaries(page), [])
                        self.assertLessEqual(top(page, '#esNav'), 200, 'Abschnittsliste im ersten Bildschirm')
                        self.assertLessEqual(top(page, '#viewSettings .es-sec:not(.hidden)'), 200, 'Inhalt ab höchstens 200 px')
                        self.assertEqual(round(page.locator('#esNav').bounding_box()['width']), 240)
                        self.assertEqual(page.locator('#esNav .es-item').count(), 9)
                        self.assertTrue(no_hscroll(page))
                        page.locator('#accSettingsForm [name="company_name"]').wait_for()
                        page.wait_for_function('() => document.querySelector("#accSettingsForm [name=company_name]").value === "Beispiel Studio"')
                        # Kurzstand mit Warnungen aus vorhandenen Daten
                        state('firma').locator('.ui-pill.is-attention').wait_for()
                        self.assertIn('fehlt', state('firma').inner_text())
                        self.assertIn('Steuernummer oder USt-IdNr.', page.text_content('#esFirmaMissing'))
                        self.assertIn('noch keine Sicherung', state('sicherung').inner_text())
                        self.assertTrue(page.locator('#esNav [data-es-key="sicherung"]').evaluate('b => b.classList.contains("is-warn")'))
                        self.assertIn('€/h', state('preise').inner_text())
                        self.assertFalse(page.locator('#esNav [data-es-key="darstellung"] .ui-pill').count(), 'keine Warnung ohne Grund')
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'einstellungen_firma.png'))

                        # ---- jeder Abschnitt über seine Adresse
                        for key in SECTIONS:
                            go(f'#/einstellungen?abschnitt={key}')
                            if key == 'ki-werkzeuge':
                                self.assertEqual(visible_view(page), 'viewStudio', key)
                            elif key == 'hilfe':
                                self.assertEqual(visible_view(page), 'viewPlaybook', key)
                            else:
                                self.assertEqual(visible_view(page), 'viewSettings', key)
                                self.assertEqual(shown_section(page), key)
                            self.assertEqual(page.text_content('#esMeta'), LABELS[key], key)
                            self.assertEqual(page.locator('#esNav .es-item.is-active').get_attribute('data-es-key'), key)
                            self.assertTrue(page.locator('#esNav').is_visible(), key)
                            self.assertEqual(head_primaries(page), [], key)

                        # ---- jeder Abschnitt über die Liste (Adresse folgt)
                        go('#/einstellungen?abschnitt=firma')
                        for key in SECTIONS:
                            page.locator(f'#esNav [data-es-key="{key}"]').click()
                            if key == 'ki-werkzeuge':
                                page.wait_for_function('() => location.hash === "#/einstellungen/ki-studio"')
                                self.assertEqual(visible_view(page), 'viewStudio')
                            elif key == 'hilfe':
                                page.wait_for_function('() => location.hash === "#/einstellungen/hilfe"')
                                self.assertEqual(visible_view(page), 'viewPlaybook')
                            else:
                                page.wait_for_function(f'() => location.hash === "#/einstellungen?abschnitt={key}"')
                                self.assertEqual(shown_section(page), key)
                            self.assertEqual(page.text_content('#esMeta'), LABELS[key])
                        page.go_back()  # Zurück führt in den vorigen Abschnitt
                        page.wait_for_function('() => location.hash === "#/einstellungen/ki-studio"')
                        self.assertEqual(visible_view(page), 'viewStudio')
                        page.go_back()
                        page.wait_for_function('() => location.hash === "#/einstellungen?abschnitt=sicherung"')
                        page.wait_for_function('() => !document.querySelector("#viewSettings .es-sec[data-es=sicherung]").classList.contains("hidden")')

                        # ---- bisherige Adressen und Sprungziele
                        go('#/einstellungen/ki-studio')
                        self.assertEqual(visible_view(page), 'viewStudio')
                        go('#/einstellungen/hilfe')
                        self.assertEqual(visible_view(page), 'viewPlaybook')
                        page.locator('.nav-help').click()
                        self.assertEqual(visible_view(page), 'viewPlaybook')
                        for target, key in OLD_TARGETS.items():
                            go(f'#/einstellungen?abschnitt={target}')
                            self.assertEqual(visible_view(page), 'viewSettings', target)
                            self.assertEqual(shown_section(page), key, target)
                            self.assertTrue(page.locator(f'#{target}').is_visible(), target)
                        go('#/einstellungen?abschnitt=ownTimes')
                        page.wait_for_function('() => document.getElementById("ownTimes").getBoundingClientRect().top < 300', timeout=5000)
                        # Verweise aus anderen Seiten
                        go('#/angebote')
                        page.locator('#viewQuotes [data-settings-link="preise"]').click()
                        page.wait_for_function('() => location.hash === "#/einstellungen?abschnitt=preise"')
                        self.assertEqual(shown_section(page), 'preise')
                        page.locator('#qbSettings input[name="hourly_rate"]').wait_for()
                        go('#/finden/neue-suche')
                        page.locator('#fdSources [data-settings-link="datenquellen"]').click()
                        page.wait_for_function('() => location.hash === "#/einstellungen?abschnitt=datenquellen"')
                        self.assertEqual(shown_section(page), 'datenquellen')
                        go('#/heute')
                        page.evaluate("() => goAction({view: 'settings', anchor: 'targetProfile'})")  # Sprung aus „Heute“ (Erste Schritte)
                        page.wait_for_function('() => location.hash === "#/einstellungen?abschnitt=zielkunden"')
                        self.assertTrue(page.locator('#targetProfileForm').is_visible())
                        # zuletzt benutzter Abschnitt
                        go('#/einstellungen?abschnitt=darstellung')
                        go('#/heute')
                        page.locator('.sidebar [data-area="einstellungen"]').click()
                        page.wait_for_function('() => location.hash === "#/einstellungen?abschnitt=darstellung"')
                        self.assertEqual(shown_section(page), 'darstellung')
                        page.goto(base + '/#/einstellungen')
                        page.reload()
                        page.wait_for_load_state('networkidle')
                        page.wait_for_function('() => location.hash === "#/einstellungen?abschnitt=darstellung"')
                        self.assertEqual(shown_section(page), 'darstellung')

                        # ---- Eingabeschutz beim Abschnittswechsel
                        go('#/einstellungen?abschnitt=zielkunden')
                        name = page.locator('#targetProfileForm [name="name"]')
                        page.wait_for_function('() => document.querySelector("#targetProfileForm [name=name]").value !== ""')
                        before = name.input_value()
                        name.fill('Handwerk Nord (Test)')
                        page.locator('#esNav [data-es-key="darstellung"]').click()
                        page.locator('#lfGuard').wait_for(state='visible')
                        self.assertIn('Zielkundenprofil', page.text_content('#lfGuardText'))
                        page.locator('#lfGuard [data-guard="edit"]').click()
                        page.locator('#lfGuard').wait_for(state='hidden')
                        self.assertEqual(shown_section(page), 'zielkunden')
                        self.assertEqual(name.input_value(), 'Handwerk Nord (Test)')
                        self.assertIn('abschnitt=zielkunden', page.url)
                        page.locator('#esNav [data-es-key="darstellung"]').click()
                        page.locator('#lfGuard').wait_for(state='visible')
                        page.locator('#lfGuard [data-guard="discard"]').click()
                        page.wait_for_function('() => location.hash === "#/einstellungen?abschnitt=darstellung"')
                        page.locator('#esNav [data-es-key="zielkunden"]').click()
                        self.assertEqual(name.input_value(), before, 'verworfen')
                        name.fill('Handwerk Nord')
                        page.locator('#esNav [data-es-key="preise"]').click()
                        page.locator('#lfGuard').wait_for(state='visible')
                        page.locator('#lfGuard [data-guard="save"]').click()
                        page.wait_for_function('() => location.hash === "#/einstellungen?abschnitt=preise"')
                        self.assertEqual(api('/profile/target')['profile']['name'], 'Handwerk Nord')
                        # Zurück mit ungespeicherter Eingabe fragt ebenfalls; „Weiter bearbeiten“ lässt Abschnitt und Adresse stehen
                        page.locator('#esNav [data-es-key="zielkunden"]').click()
                        name.fill('Handwerk Süd')
                        page.go_back()
                        page.locator('#lfGuard').wait_for(state='visible')
                        page.locator('#lfGuard [data-guard="edit"]').click()
                        page.wait_for_function('() => location.hash === "#/einstellungen?abschnitt=zielkunden"')
                        self.assertEqual(shown_section(page), 'zielkunden')
                        page.locator('#esNav [data-es-key="darstellung"]').click()
                        page.locator('#lfGuard [data-guard="discard"]').click()
                        page.wait_for_function('() => location.hash === "#/einstellungen?abschnitt=darstellung"')

                        # ---- Suche über die Einstellungen
                        page.fill('#esQ', 'IBAN')
                        self.assertTrue(page.locator('#esNav [data-es-key="firma"]').is_visible())
                        self.assertFalse(page.locator('#esNav [data-es-key="darstellung"]').is_visible())
                        self.assertIn('Abschnitt', page.text_content('#esHits'))
                        page.fill('#esQ', 'Overpass')
                        self.assertEqual(page.locator('#esNav .es-item:visible').count(), 1)
                        page.press('#esQ', 'Enter')
                        page.wait_for_function('() => location.hash === "#/einstellungen?abschnitt=datenquellen"')
                        self.assertEqual(shown_section(page), 'datenquellen')
                        page.fill('#esQ', 'gibt es nicht xyz')
                        self.assertEqual(page.locator('#esNav .es-item:visible').count(), 0)
                        self.assertEqual(page.text_content('#esHits'), 'Keine Einstellung gefunden')
                        page.fill('#esQ', '')
                        self.assertEqual(page.locator('#esNav .es-item:visible').count(), 9)

                        # ---- Abrechnen: Reiter mit Adressen
                        go('#/abrechnen')
                        self.assertEqual(visible_view(page), 'viewAccounting')
                        tabs = page.locator('#areaBar .area-tabs[data-area="abrechnen"] [data-area-view]')
                        self.assertTrue(page.locator('#areaBar .area-tabs[data-area="abrechnen"]').is_visible())
                        self.assertEqual([t.strip() for t in tabs.all_inner_texts()], [t[1] for t in ACC_TABS])
                        for view, label, hash_, el in ACC_TABS[1:] + ACC_TABS[:1]:
                            page.locator(f'#areaBar [data-area-view="{view}"]').click()
                            page.wait_for_function(f'() => location.hash === "{hash_}"')
                            self.assertEqual(visible_view(page), el)
                        go('#/abrechnen/steuer')
                        self.assertEqual(visible_view(page), 'viewTax')
                        page.locator('#accUstva table').wait_for()
                        page.locator('#accExports a').first.wait_for()
                        go('#/abrechnen/ausgaben')
                        self.assertTrue(page.locator('#accExpenseForm').is_visible())
                        self.assertTrue(page.locator('#accEinvoiceFile').count())
                        go('#/abrechnen/auswertung')
                        page.wait_for_function('() => document.getElementById("accOpen").textContent !== "–"')

                        # ---- Rechnungen: Seitenkopf, Liste, Abnahmemaß
                        go('#/abrechnen')
                        rows = page.locator('#accInvoiceRows .ui-row')
                        page.wait_for_function('() => document.querySelectorAll("#accInvoiceRows .ui-row").length === 4')
                        self.assertEqual(page.text_content('#accListTitle'), 'Abrechnen')
                        self.assertEqual(page.text_content('#accCount'), '4 Rechnungen')
                        self.assertEqual(head_primaries(page), ['＋ Neue Rechnung'])
                        self.assertLessEqual(top(page, '#accInvoiceRows .ui-row'), 280, 'erste Rechnungszeile im ersten Bildschirm')
                        # Höhe im Browser messen: die Liste zeichnet nach dem Laden neu, ein Locator kann dazwischen ins Leere greifen
                        self.assertEqual(page.evaluate('() => Math.round(document.querySelector("#accInvoiceRows .ui-row").getBoundingClientRect().height)'), 56)
                        heads = page.locator('#accList .ui-row-head > span').all_inner_texts()
                        self.assertEqual([h.strip().lower() for h in heads[:5]], ['rechnung', 'nächster schritt', 'fällig', 'status', 'betrag brutto'])
                        row = lambda inv: page.locator(f'#accInvoiceRows [data-acc-open="{inv["id"]}"]')
                        self.assertIn('Zahlung erinnern', row(ids[0]).inner_text())
                        self.assertIn('überfällig', row(ids[0]).locator('.ui-pill.is-overdue').inner_text())
                        self.assertIn('Beispiel Bau GmbH · Abschlag', row(ids[0]).inner_text())
                        self.assertIn('Zahlungseingang abwarten', row(ids[2]).inner_text())
                        self.assertIn('Bezahlt', row(ids[1]).inner_text())
                        self.assertIn('Stammdaten ergänzen', row(ids[3]).inner_text())  # Entwurf, aber Pflichtangabe fehlt
                        self.assertTrue(no_hscroll(page))
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'abrechnen_rechnungen.png'))
                        # Ansichten, Suche, Filter
                        page.locator('[data-acc-view="offen"]').click()
                        self.assertEqual(rows.count(), 2)
                        page.locator('[data-acc-view="ueberfaellig"]').click()
                        self.assertEqual(rows.count(), 1)
                        page.locator('[data-acc-view="bezahlt"]').click()
                        self.assertEqual(rows.count(), 1)
                        page.locator('[data-acc-view="alle"]').click()
                        page.fill('#accQ', ids[2]['number'])
                        self.assertEqual(rows.count(), 1)
                        self.assertIn('1 von 4', page.text_content('#accCount'))
                        page.fill('#accQ', '')
                        page.locator('#accFilterBtn').click()
                        page.select_option('#accInvoiceFilter', 'entwurf')
                        self.assertEqual(rows.count(), 1)
                        page.locator('#accFilterReset').click()
                        self.assertEqual(rows.count(), 4)

                        # Geöffnete Rechnung: ← Rechnungen, genau eine Hauptaktion (Drucken / PDF), Storno und E-Rechnung erreichbar
                        row(ids[0]).click()
                        page.locator('#accDetail .ui-head h1').wait_for()
                        self.assertEqual(page.text_content('#accDetail .ui-head h1'), ids[0]['number'])
                        self.assertEqual(head_primaries(page), ['Drucken / PDF ↗'])
                        self.assertEqual(page.evaluate('() => [...document.querySelectorAll("#viewAccounting .btn-primary")].filter(b => b.offsetParent !== null).length'), 1)
                        self.assertTrue(page.locator('#accDetail [data-acc-cancel]').is_visible())
                        self.assertTrue(page.locator('#accDetail a[href$="/xrechnung"]').is_visible())
                        self.assertTrue(page.locator('#accDunningForm').is_visible())
                        page.locator('#accDetail [data-acc-close-detail]').click()
                        rows.first.wait_for()
                        # Tastatur: Enter öffnet den Entwurf im Editor
                        row(ids[3]).focus()
                        page.keyboard.press('Enter')
                        page.locator('#accEditor').wait_for(state='visible')
                        self.assertIn('Entwurf', page.text_content('#accEditorTitle'))
                        page.locator('#accEditorClose').click()
                        rows.first.wait_for()

                        # „＋ Neue Rechnung“ öffnet den Editor
                        page.locator('#accNewInvoice').click()
                        page.locator('#accEditor').wait_for(state='visible')
                        self.assertTrue(page.locator('#accList').is_hidden())
                        self.assertEqual(page.text_content('#accEditorTitle'), 'Neue Rechnung')
                        self.assertTrue(page.locator('#accInvoiceForm [name="buyer_name"]').is_visible())
                        self.assertEqual(head_primaries(page), [])
                        self.assertLessEqual(top(page, '#accEditor .ui-card'), 200)
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'abrechnen_editor.png'))
                        page.locator('#accEditorClose').click()
                        page.locator('#accList').wait_for(state='visible')

                        # Stammdaten-Warnung als Klappzeile → Einstellungen → Meine Firma
                        fold = page.locator('#accMasterFold')
                        fold.wait_for()
                        self.assertIn('fehlt', page.text_content('#accMasterState'))
                        page.locator('#accMasterLink').click()
                        page.wait_for_function('() => location.hash === "#/einstellungen?abschnitt=firma"')
                        self.assertEqual(visible_view(page), 'viewSettings')
                        self.assertEqual(shown_section(page), 'firma')
                        self.assertTrue(page.locator('#accSettingsForm [name="tax_number"]').is_visible())
                        # ergänzen → Warnung verschwindet
                        page.fill('#accSettingsForm [name="tax_number"]', '22/123/45678')
                        page.locator('#accSettingsForm button[type="submit"]').click()
                        page.wait_for_function('() => !document.querySelector("[data-es-state=firma] .ui-pill")', timeout=10000)
                        self.assertTrue(page.locator('#esFirmaMissing').is_hidden())
                        go('#/abrechnen')
                        page.wait_for_function('() => document.querySelectorAll("#accInvoiceRows .ui-row").length === 4')
                        page.wait_for_function('() => document.getElementById("accMasterFold").classList.contains("hidden")')
                        self.assertIn('Prüfen und festschreiben', row(ids[3]).inner_text())

                        # ---- 390 × 844: Liste als eigene Ansicht, Abschnitt mit „← Einstellungen“
                        page.set_viewport_size({'width': 390, 'height': 844})
                        go('#/heute')
                        go('#/einstellungen')
                        page.wait_for_function('() => document.getElementById("viewSettings").dataset.esMode === "list"')
                        self.assertTrue(page.locator('#esNav').is_visible())
                        self.assertTrue(page.locator('#viewSettings .es-body').is_hidden())
                        self.assertTrue(page.locator('#esBack').is_hidden())
                        self.assertTrue(no_hscroll(page))
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'einstellungen_mobil.png'))
                        page.locator('#esNav [data-es-key="kalender"]').click()
                        page.wait_for_function('() => location.hash === "#/einstellungen?abschnitt=kalender"')
                        self.assertTrue(page.locator('#esNav').is_hidden())
                        self.assertTrue(page.locator('#calEnabled').is_visible())
                        self.assertTrue(page.locator('#esBack').is_visible())
                        self.assertTrue(no_hscroll(page))
                        page.locator('#esBack').click()
                        page.wait_for_function('() => location.hash === "#/einstellungen"')
                        self.assertTrue(page.locator('#esNav').is_visible())
                        page.locator('#esNav [data-es-key="ki-werkzeuge"]').click()
                        self.assertEqual(visible_view(page), 'viewStudio')
                        self.assertTrue(page.locator('#esBack').is_visible())
                        self.assertTrue(no_hscroll(page))
                        for sec in SECTIONS[:7]:
                            go(f'#/einstellungen?abschnitt={sec}')
                            self.assertTrue(no_hscroll(page), sec)
                        for _view, _label, hash_, _el in ACC_TABS:
                            go(hash_)
                            self.assertTrue(no_hscroll(page), hash_)
                        go('#/abrechnen')
                        rows.first.wait_for()
                        self.assertLess(top(page, '#accInvoiceRows .ui-row'), 844)

                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
