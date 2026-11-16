"""Browserprüfung 2.0.0-dev51 (UX Schritt 3): Bereich „Finden“ aus dem UI-Baukasten.

Abnahme:
- Vier Reiter: Sichten · Neue Suche · Import · Analysen; Recherche, URL-Recherche, Website-Scoring, Kaufsignale und Bericht als
  Unteransichten von „Analysen“. Alle bisherigen Adressen öffnen die richtige Ansicht, dazu #/finden/sichten und #/finden/neue-suche;
  #/finden (und die Seitenleiste) führt zu „Sichten“, solange offene Treffer warten, sonst zu „Neue Suche“.
- Neue Suche bei 1280 × 720: „Suche starten“ ohne Scrollen (Oberkante ≤ 140 px); Ort, Umkreis, Branchen und „Wen suchst du?“
  liegen vollständig im ersten Bildschirm.
- „Wen suchst du?“: jede Voreinstellung setzt genau die erwarteten Felder (Formular und an den Server gesendete Parameter);
  eine Handänderung bleibt, die Auswahl zeigt dann „Eigene Auswahl“; die Voreinstellung wird mit den Suchparametern gemerkt.
- Klappzeilen „Quellen & Budget“, „Optionen“, „Suchprofile“ zeigen ihren Kurzstand und enthalten die Felder.
- Sichten bei 1280 × 720 mit 11 Treffern: erste Trefferzeile ≤ 280 px, mindestens 7 Zeilen ganz sichtbar; Übernehmen, Verwerfen und
  Website bestätigen sind in der Zeile bzw. der aufgeklappten Zeile erreichbar.
- Datenquellen unter Einstellungen (OpenStreetMap-Auszug einlesen, danach offline suchen), Stichprobe unter Firmen → Datenpflege.
- Genau eine Hauptaktion je Seitenkopf; 390 × 844 ohne waagerechtes Scrollen; keine Skriptfehler, keine Abrufe nach außen.
Fiktive Firmen; es wird kein öffentlicher Server abgefragt."""
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

from sales_tool import sweep as sw
from sales_tool.model import connect, init_db
from sales_tool.research import jobs
from sales_tool.server import make_handler

PBF = Path(__file__).resolve().parent.parent / 'fixtures' / 'osm' / 'beispiel.osm.pbf'
SHOTS = os.environ.get('SIGNALDESK_E2E_SHOTS')
# Name, Branche, Rechtsform, Website-Status, Website, Entfernung (alles fiktiv)
CANDS = [('Elektro Muster', 'elektro', '', 'belegt', 'https://elektro-muster.example', 2.1),
         ('Sanitär Beispiel GmbH', 'shk', 'GmbH', 'wahrscheinlich', 'https://sanitaer-beispiel.example', 3.4),
         ('Malerbetrieb Fiktiv', 'maler', '', 'belegt', 'https://maler-fiktiv.example', 4.0),
         ('Demo Holding GmbH', 'beratung', 'GmbH', 'nicht_gefunden', '', 5.2),
         ('Beispiel Dach GmbH', 'dach', 'GmbH', '', '', 6.8),
         ('Fiktiv Fliesen', 'fliesen', '', 'belegt', 'https://fiktiv-fliesen.example', 7.3),
         ('Beispiel Schreinerei KG', 'schreiner', 'KG', 'belegt', 'https://schreinerei-beispiel.example', 8.0),
         ('Demo Metallbau GmbH', 'metallbau', 'GmbH', 'wahrscheinlich', 'https://demo-metallbau.example', 9.6),
         ('Fiktiv Garten', 'garten', '', '', '', 11.0),
         ('Muster Elektrotechnik GmbH', 'elektro', 'GmbH', 'belegt', 'https://muster-et.example', 12.5),
         ('Beispiel Bau AG', 'bau', 'AG', '', '', 14.1)]
ADDRESSES = {'#/finden/sichten': 'viewSichten', '#/finden/neue-suche': 'viewFinder', '#/finden/import': 'viewDatacheck',
             '#/finden/recherche': 'viewCenter', '#/finden/url-recherche': 'viewResearch', '#/finden/website-scoring': 'viewScoring',
             '#/finden/kaufsignale': 'viewSignals', '#/finden/bericht': 'viewCenter'}
ANALYSEN = {'viewCenter': 'center', 'viewResearch': 'research', 'viewScoring': 'scoring', 'viewSignals': 'signals'}


def visible_view(page):
    return page.evaluate('() => [...document.querySelectorAll(".content")].filter(e => !e.classList.contains("hidden")).map(e => e.id).join(",")')


def seed(db):
    with connect(db) as conn:
        init_db(conn)
        sid = conn.execute("""INSERT INTO sweeps(label, kind, params_json, status) VALUES ('70173 · 30 km · Handwerk', 'suche',
                              '{"place": "70173", "radius_km": 30, "sources": ["osm"]}', 'fertig')""").lastrowid
        run = sw._run_record(conn, 'osm', sid, {})
        for name, ind, legal, status, web, km in CANDS:
            src = 'gleif' if legal == 'AG' else 'osm'
            conn.execute("""INSERT INTO discovery_candidates(run_id, sweep_id, source, name, website, zip, city, status, sources_json,
                            website_status, website_evidence, distance_km, industry_key, legal_form) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (run, sid, src, name, web, '70173', 'Stuttgart', 'neu', json.dumps([{'source': src, 'url': ''}]), status,
                          'Vorschlag: Name und PLZ im Impressum – bitte prüfen' if status == 'wahrscheinlich' else '', km, ind, legal))
        conn.commit()


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class FindenBrowserTests(unittest.TestCase):
    def test_finden_tabs_search_review_and_moves(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'f.sqlite3'
            seed(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1280, 'height': 720})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        api = lambda path, method='GET', body=None: page.evaluate(
                            """async ([p, m, b]) => { const r = await fetch('/api' + p, {method: m, headers: b ? {'Content-Type': 'application/json'} : {},
                                 body: b ? JSON.stringify(b) : undefined}); return r.json(); }""", [path, method, body])

                        def go(hash_, view):
                            page.goto(base + '/' + hash_)
                            page.wait_for_function('v => !document.getElementById(v).classList.contains("hidden")', arg=view)
                            page.wait_for_load_state('networkidle')

                        # ---- Einstieg: offene Treffer → Sichten; Adresse wird konkret
                        go('#/finden', 'viewSichten')
                        self.assertEqual(visible_view(page), 'viewSichten')
                        page.wait_for_function('() => location.hash === "#/finden/sichten"')
                        tabs = page.evaluate('() => [...document.querySelectorAll(\'#areaBar .area-tabs[data-area="finden"] [data-area-view]\')].map(b => b.firstChild.textContent.trim())')
                        self.assertEqual(tabs, ['Sichten', 'Neue Suche', 'Import', 'Analysen'])

                        # ---- alle bisherigen und neuen Adressen
                        for hash_, view in ADDRESSES.items():
                            go(hash_, view)
                            self.assertEqual(visible_view(page), view, hash_)
                            active = page.evaluate('() => [...document.querySelectorAll("#areaBar .area-tab.active")].map(b => b.firstChild.textContent.trim())')
                            expect = 'Analysen' if view in ANALYSEN else {'viewSichten': 'Sichten', 'viewFinder': 'Neue Suche', 'viewDatacheck': 'Import'}[view]
                            self.assertEqual(active, [expect], hash_)
                            if view in ANALYSEN:  # Reiterzeile „Analysen“ steht in der sichtbaren Ansicht, der richtige Reiter ist aktiv
                                self.assertEqual(page.evaluate('() => document.getElementById("fdAnBar").closest(".content").id'), view)
                                self.assertEqual(page.get_attribute('#fdAnBar .ui-tab.is-active', 'data-area-view'), ANALYSEN[view])
                                self.assertEqual(page.locator('#fdAnBar [data-area-view]').count(), 4)
                        page.locator('#fdAnBar [data-area-view="signals"]').click()
                        page.wait_for_function('() => location.hash === "#/finden/kaufsignale"')
                        self.assertEqual(visible_view(page), 'viewSignals')

                        # ---- Sichten: Abnahmemaß 1280 × 720, Spalten, eine Hauptaktion
                        go('#/finden/sichten', 'viewSichten')
                        page.locator('.sw-item').nth(8).wait_for()
                        m = page.evaluate('''() => { const r = [...document.querySelectorAll("#swList .fd-row")];
                          return {top: r[0].getBoundingClientRect().top, full: r.filter(x => x.getBoundingClientRect().bottom <= innerHeight).length,
                                  h: r[0].getBoundingClientRect().height, n: r.length}; }''')
                        self.assertEqual(m['n'], 11)
                        self.assertLessEqual(m['top'], 280, m)
                        self.assertGreaterEqual(m['full'], 7, m)
                        self.assertEqual(round(m['h']), 56)
                        heads = page.evaluate('() => [...document.querySelectorAll("#swReview .ui-row-head > span")].map(s => s.textContent.trim())')
                        self.assertEqual(heads[:4], ['Firma', 'Website', 'Entfernung', 'Quelle'])
                        self.assertIn('11', page.text_content('#swCounts'))
                        self.assertEqual(page.locator('#viewSichten .ui-head .btn-primary').count(), 1)
                        self.assertEqual(page.locator('#viewSichten .btn-primary:visible').count(), 1)
                        self.assertEqual(page.text_content('#viewSichten .ui-head .btn-primary').strip(), '＋ Neue Suche')
                        sani = page.locator('.sw-item', has_text='Sanitär Beispiel GmbH')
                        self.assertEqual(sani.locator('.ui-pill').first.inner_text(), 'Vorschlag prüfen')
                        self.assertIn('ohne Rechtsform', page.locator('.sw-item', has_text='Elektro Muster').locator('.sw-main').inner_text())
                        self.assertEqual(page.locator('#swViews .ui-tab.is-active').get_attribute('data-sw-view'), 'offen')
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'finden_sichten.png'))

                        # Zeilenaktion „Übernehmen“ (Text in der Zeile)
                        page.locator('.sw-item', has_text='Demo Holding GmbH').locator('[data-sw-do="uebernehmen"]').click()
                        page.wait_for_function("async () => (await (await fetch('/api/leads')).json()).some(l => l.company === 'Demo Holding GmbH')")
                        page.wait_for_function('() => ![...document.querySelectorAll(".sw-item")].some(e => e.textContent.includes("Demo Holding GmbH"))')
                        # Aufklappen: Verwerfen, Website bestätigen, Website eintragen/suchen, Dubletten-Hinweise in der Zeile
                        garten = page.locator('.sw-item', has_text='Fiktiv Garten')
                        self.assertTrue(garten.locator('[data-sw-do="verwerfen"]').is_hidden())
                        garten.locator('.sw-main').click()
                        garten.locator('[data-sw-do="verwerfen"]').wait_for(state='visible')
                        self.assertTrue(garten.locator('[data-sw-do="website-eintragen"]').is_visible())
                        self.assertTrue(garten.locator('[data-sw-do="website"]').is_visible())
                        self.assertEqual(garten.locator('.fd-row').get_attribute('aria-expanded'), 'true')
                        garten.locator('[data-sw-do="verwerfen"]').click()
                        page.wait_for_function('() => ![...document.querySelectorAll(".sw-item")].some(e => e.textContent.includes("Fiktiv Garten"))')
                        sani = page.locator('.sw-item', has_text='Sanitär Beispiel GmbH')
                        sani.locator('.fd-row').press('Enter')  # Tastatur: Enter klappt auf
                        sani.locator('[data-sw-web="bestaetigen"]').click()
                        page.wait_for_function("""async () => (await (await fetch('/api/sweep-candidates?status=neu&limit=50')).json()).items
                          .some(c => c.name === 'Sanitär Beispiel GmbH' && c.website_status === 'bestaetigt')""")
                        # Ansicht „Mit Website“, Filter im Menü, Massenaktionen unter „Auswahl ▾“
                        page.locator('#swViews [data-sw-view="website"]').click()
                        page.wait_for_function('() => document.querySelector("#swViews .ui-tab.is-active")?.dataset.swView === "website"')
                        page.wait_for_function('() => document.querySelectorAll(".sw-item").length === 7')
                        page.locator('#swFilterMenu > summary').click()
                        for sel in ('#swStatus', '#swSweep', '#swWeb', '#swCity', '#swKm', '#swSort', '#swNoTed', '#swDedupe'):
                            self.assertTrue(page.locator(sel).is_visible(), sel)
                        page.keyboard.press('Escape')
                        page.locator('#swBulkMenu > summary').click()
                        for sel in ('[data-sw-bulk="uebernehmen"]', '[data-sw-bulk="bericht"]', '[data-sw-bulk="verwerfen"]', '[data-sw-bulk="websites"]', '#swTakeAll'):
                            self.assertTrue(page.locator(sel).is_visible(), sel)
                        page.keyboard.press('Escape')
                        page.locator('#swViews [data-sw-view="offen"]').click()
                        page.wait_for_function('() => document.querySelectorAll(".sw-item").length === 9')

                        # ---- Neue Suche: Abnahmemaß 1280 × 720, eine Hauptaktion, Statuszeile
                        page.locator('#fdNewSearch').click()
                        page.wait_for_function('() => location.hash === "#/finden/neue-suche"')
                        page.wait_for_function('() => document.getElementById("fdSources").textContent.includes("GLEIF-Katalog")')
                        page.wait_for_function('() => document.querySelectorAll("#swIndustries [data-ind]").length > 20')
                        geo = page.evaluate('''() => Object.fromEntries([["go", "#swGo"], ["ort", "#swForm [name=place]"], ["umkreis", "#swForm [name=radius_km]"],
                            ["branchen", "#swIndMenu > summary"], ["wen", "#fdPresets"]].map(([k, s]) => { const r = document.querySelector(s).getBoundingClientRect();
                            return [k, {top: r.top, bottom: r.bottom}]; }))''')
                        self.assertLessEqual(geo['go']['top'], 140, geo)
                        for k in ('ort', 'umkreis', 'branchen', 'wen'):
                            self.assertGreaterEqual(geo[k]['top'], 0, k)
                            self.assertLessEqual(geo[k]['bottom'], 720, (k, geo))
                        self.assertEqual(page.locator('#viewFinder .ui-head .btn-primary').count(), 1)
                        self.assertEqual(page.locator('#viewFinder .btn-primary:visible').count(), 1)
                        self.assertEqual(page.text_content('#swGo').strip(), 'Suche starten')
                        self.assertIn('Einstellungen → Datenquellen', page.text_content('#fdSources'))
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'finden_neue_suche.png'))
                        # Branchen: Auswahl einklappbar, gewählte als Marken (alle bisherigen Branchen wählbar)
                        page.locator('#swIndMenu > summary').click()
                        page.fill('#swIndSearch', 'Maler')
                        page.locator('#swIndustries [data-ind="maler"]').check()
                        page.keyboard.press('Escape')
                        page.locator('#swIndChips .ui-chip', has_text='Maler').wait_for()
                        page.locator('#swIndChips [data-ind-remove="maler"]').click()
                        page.wait_for_function('() => !document.querySelector("#swIndChips .ui-chip")')
                        self.assertFalse(page.evaluate('() => document.getElementById("swIndMenu").open'), 'Entfernen klappt die Auswahl nicht auf')

                        # ---- „Wen suchst du?“: Voreinstellungen setzen nur die vorgesehenen Felder
                        def state():
                            return page.evaluate('''() => { const p = window.swFormParams();
                              return {sources: [...p.sources].sort(), sole: p.include_sole, web: p.find_websites, budget: p.budget, operative: p.operative,
                                      org: p.org_kinds, active: document.querySelector("#fdPresets .is-active")?.dataset.fdPreset || "",
                                      own: document.getElementById("fdPresetState").textContent}; }''')
                        s0 = state()
                        self.assertEqual(s0['active'], 'alles')  # bisherige Voreinstellung des Formulars
                        page.locator('[data-fd-preset="handwerk"]').click()
                        s = state()
                        self.assertEqual((s['sources'], s['sole'], s['web'], s['active']), (['gleif', 'osm', 'wikidata'], True, True, 'handwerk'))
                        self.assertEqual((s['operative'], s['org'], s['budget']), (s0['operative'], s0['org'], s0['budget']))
                        page.locator('[data-fd-preset="gross"]').click()
                        s = state()
                        self.assertEqual((s['sources'], s['sole'], s['web'], s['active']), (['gleif', 'wikidata'], False, True, 'gross'))
                        page.locator('[data-fd-preset="oeffentlich"]').click()
                        s = state()
                        self.assertEqual((s['sources'], s['sole'], s['active']), (['ted'], False, 'oeffentlich'))
                        # Handänderung im Budget, dann „Alles“: Budget wie die bisherige Voreinstellung
                        page.locator('#fdSrcFold > summary').click()
                        page.fill('#swForm [name=max_companies]', '120')
                        page.locator('[data-fd-preset="alles"]').click()
                        s = state()
                        self.assertEqual((s['sources'], s['sole'], s['web'], s['active']), (['gleif', 'osm', 'ted', 'wikidata'], True, True, 'alles'))
                        self.assertEqual(s['budget'], {'max_companies': 300, 'max_websites': 100, 'max_minutes': 30})
                        # Handänderung bleibt; keine Voreinstellung aktiv, Hinweis „Eigene Auswahl“
                        page.locator('[data-fd-preset="handwerk"]').click()
                        page.locator('#fdOptFold > summary').click()
                        page.locator('#swForm [name=find_websites]').uncheck()
                        s = state()
                        self.assertEqual((s['sources'], s['web'], s['active'], s['own']), (['gleif', 'osm', 'wikidata'], False, '', 'Eigene Auswahl'))
                        self.assertIn('Websites automatisch suchen: nein', page.text_content('#fdOptState'))
                        # Klappzeilen: Kurzstand nennt die aktuellen Werte und enthält die Felder
                        self.assertIn('GLEIF', page.text_content('#fdSrcState'))
                        self.assertIn('300 neue Firmen', page.text_content('#fdSrcState'))
                        self.assertNotIn('TED', page.text_content('#fdSrcState'))
                        self.assertIn('ohne Rechtsform: ja', page.text_content('#fdOptState'))
                        fold = lambda sel: page.evaluate('s => document.querySelector(s).closest("details")?.id || ""', sel)
                        for sel in ('#swForm [name=src][value=gleif]', '#swForm [name=osm_online]', '#swForm [name=max_companies]',
                                    '#swForm [name=max_websites]', '#swForm [name=max_minutes]'):
                            self.assertEqual(fold(sel), 'fdSrcFold', sel)
                        for sel in ('#swForm [name=operative]', '#swForm [name=include_sole]', '#swForm [name=find_websites]',
                                    '#swForm [name=org][value=verein]', '#swForm [name=ted_nationwide]', '#swForm [name=keywords]'):
                            self.assertEqual(fold(sel), 'fdOptFold', sel)
                        self.assertEqual(fold('#swProfile'), 'fdProfFold')
                        self.assertIn('noch keins gespeichert', page.text_content('#fdProfState'))
                        # Voreinstellung wird mit dem Suchprofil gemerkt
                        page.fill('#swForm [name=place]', '70173')
                        page.locator('[data-fd-preset="gross"]').click()
                        page.locator('#fdProfFold > summary').click()
                        page.once('dialog', lambda d: d.accept('Größere Firmen Stuttgart'))
                        page.locator('#swProfileSave').click()
                        page.wait_for_function('() => document.getElementById("fdProfState").textContent.includes("aktiv: Größere Firmen Stuttgart")')
                        page.locator('[data-fd-preset="oeffentlich"]').click()
                        page.select_option('#swProfile', '')
                        page.select_option('#swProfile', label='Größere Firmen Stuttgart')
                        page.wait_for_function('() => document.querySelector("#fdPresets .is-active")?.dataset.fdPreset === "gross"')
                        # … und mit der zuletzt gestarteten Suche (Speicher des Browsers, wie die übrigen Suchparameter)
                        page.evaluate('''() => localStorage.setItem("sw_last", JSON.stringify({...window.swFormParams(), sources: ["ted"], place: "70173"}))''')
                        page.reload()
                        page.wait_for_function('() => !document.getElementById("viewFinder").classList.contains("hidden")')
                        page.wait_for_function('() => document.querySelector("#fdPresets .is-active")?.dataset.fdPreset === "oeffentlich"')
                        self.assertEqual(page.input_value('#swForm [name=place]'), '70173')

                        # ---- Einstellungen → Datenquellen: OpenStreetMap-Auszug einlesen, danach offline suchen
                        page.fill('#swForm [name=place]', '70191')
                        page.select_option('#swForm [name=radius_km]', '0')
                        page.locator('#fdSources [data-settings-link="datenquellen"]').click()
                        page.wait_for_function('() => location.hash.includes("abschnitt=datenquellen")')
                        self.assertEqual(visible_view(page), 'viewSettings')
                        for box in ('osmBox', 'osmFile', 'catBox', 'catFile', 'swCheckBox', 'swCheck', 'datenquellen'):
                            self.assertEqual(page.evaluate(f'() => document.getElementById("{box}").closest(".content").id'), 'viewSettings', box)
                        page.locator('#osmBox > summary').click()
                        page.locator('#osmState', has_text='noch kein lokaler Bestand').wait_for(timeout=15000)
                        self.assertEqual(page.input_value('#osmPlace'), '70191')
                        page.locator('#osmTurbo').wait_for(state='visible', timeout=15000)
                        self.assertIn('70191', page.get_attribute('#osmTurbo', 'href'))
                        page.locator('#osmFile').set_input_files(str(PBF))
                        page.locator('#osmState', has_text='6 Betriebe').wait_for(timeout=30000)
                        page.wait_for_function('() => document.getElementById("osmSummary").textContent.includes("6 Betriebe")')
                        page.locator('#catBox > summary').click()
                        self.assertTrue(page.locator('#catSearch').is_visible())
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'einstellungen_datenquellen.png'))
                        page.locator('.sidebar [data-area="finden"]').click()
                        self.assertEqual(visible_view(page), 'viewSichten')  # offene Treffer warten
                        page.locator('#areaBar [data-area-view="finder"]').click()
                        page.wait_for_function('() => document.getElementById("fdSources").textContent.includes("6 Betriebe")')
                        page.locator('[data-fd-preset="handwerk"]').click()
                        page.locator('#fdSrcFold > summary').click()
                        page.locator('#fdOptFold > summary').click()
                        for src in ('gleif', 'wikidata'):
                            page.locator(f'#swForm input[name="src"][value="{src}"]').uncheck()
                        page.locator('#swForm input[name="find_websites"]').uncheck()
                        page.locator('#swGo').click()
                        page.wait_for_function("""async () => { const s = await (await fetch('/api/sweeps')).json();
                          return s[0] && s[0].params.place === '70191' && s[0].status === 'fertig'; }""", timeout=30000)
                        page.locator('#swProgress [data-sw-show]').click()
                        page.wait_for_function('() => location.hash === "#/finden/sichten"')
                        page.locator('.sw-main', has_text='Malerbetrieb Beispiel').wait_for(timeout=15000)

                        # ---- Firmen → Datenpflege: Stichprobe von Hand prüfen
                        go('#/firmen/datenpflege', 'viewQuality')
                        self.assertEqual(page.evaluate('() => document.getElementById("plBox").closest(".content").id'), 'viewQuality')
                        page.locator('#plBox > summary').click()
                        page.locator('#plSource option[value="osm"]').wait_for(state='attached')
                        page.select_option('#plSize', '20')
                        page.locator('#plDraw button[type=submit]').click()
                        page.locator('[data-pl-row]').first.wait_for()

                        # ---- Import: Firmenliste (bisher bei „Suche & Sichtung“)
                        go('#/finden/import', 'viewDatacheck')
                        self.assertTrue(page.locator('#fdImport .sw-import').is_visible())
                        self.assertEqual(page.evaluate('() => document.getElementById("swFile").closest(".content").id'), 'viewDatacheck')

                        # ---- schmal: kein waagerechtes Scrollen
                        page.set_viewport_size({'width': 390, 'height': 844})
                        for hash_, view in (('#/finden/sichten', 'viewSichten'), ('#/finden/neue-suche', 'viewFinder'),
                                            ('#/einstellungen?abschnitt=datenquellen', 'viewSettings'), ('#/finden/kaufsignale', 'viewSignals')):
                            go(hash_, view)
                            self.assertFalse(page.evaluate('() => document.documentElement.scrollWidth > window.innerWidth + 1'), hash_)

                        # ---- keine offenen Treffer mehr: #/finden führt zur neuen Suche
                        page.set_viewport_size({'width': 1280, 'height': 720})
                        api('/sweep-candidates/bulk-all', 'POST', {'filter': {}, 'decision': 'verwerfen', 'max': 1000})
                        go('#/finden', 'viewFinder')
                        page.wait_for_function('() => location.hash === "#/finden/neue-suche"')
                        self.assertEqual(visible_view(page), 'viewFinder')

                        self.assertEqual(outside, [], 'kein Abruf außerhalb des eigenen Rechners')
                        self.assertEqual(errors, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                jobs.stop_all_workers()


if __name__ == '__main__':
    unittest.main()
