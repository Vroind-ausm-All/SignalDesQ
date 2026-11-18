"""Browserprüfung 2.0.0-dev52 (Fehlerbehebung): Erlebnisstudie, Fachreview und Stichprobe speichern jede Eingabe sofort und zeichnen
danach neu. Tippt man währenddessen in einem anderen Feld, darf das Neuzeichnen den getippten Text nicht ersetzen.

Nachweis: Die Speicher-Antwort wird über page.route festgehalten, bis im anderen Feld getippt ist; erst dann antwortet der Server und
die Ansicht zeichnet neu. Ohne die Korrektur (uiKeep in uikit.js) stand danach das leere Feld da – der Text war verloren.
Fiktive Firmen, nur 127.0.0.1."""
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
from test_v2_expert_review import make_audit  # noqa: E402

from sales_tool import sweep as sw  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402

TYPED = 'Kontakt war im Fußbereich versteckt'


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class KeepInputBrowserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Path(self.tmp.name) / 'keep.sqlite3'
        prepare_database(self.db)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def api(self, path, method='GET', body=None):
        req = urllib.request.Request(self.base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': self.base},
                                     data=json.dumps(body).encode() if body is not None else None)
        return json.loads(urllib.request.urlopen(req).read() or b'null')

    def run_case(self, address, prepare, save_glob, change_first, typed_field, verify, text=TYPED):
        """prepare(page) öffnet die Ansicht; change_first(page) ändert ein Feld (löst das Speichern aus); typed_field ist das andere Feld;
        verify(page) prüft danach den gespeicherten Stand."""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
            try:
                page = browser.new_page(viewport={'width': 1366, 'height': 900})
                errors, outside = [], []
                page.on('pageerror', lambda exc: errors.append(str(exc)))
                page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                page.on('dialog', lambda d: d.accept())
                page.goto(self.base + address)
                page.wait_for_load_state('networkidle')
                prepare(page)
                held, done = [], []

                def hold(route):  # jede Speicher-Anfrage festhalten, bis der Test sie freigibt
                    if route.request.method == 'POST':
                        held.append(route)
                    else:
                        route.continue_()

                def release_all():
                    quiet = 0
                    while quiet < 6:  # so lange freigeben, bis 300 ms lang keine neue Anfrage kommt
                        page.wait_for_timeout(50)
                        fresh = [r for r in held if r not in done]
                        quiet = 0 if fresh else quiet + 1
                        for r in fresh:
                            done.append(r)
                            r.continue_()
                page.route(save_glob, hold)
                old = change_first(page)  # Element, das beim Neuzeichnen ersetzt wird
                for _ in range(100):
                    if held:
                        break
                    page.wait_for_timeout(50)
                self.assertEqual(len(held), 1, 'Speichern wurde ausgelöst und festgehalten')
                first, rest = text[:len(text) // 2], text[len(text) // 2:]
                field = page.locator(typed_field)
                field.click()
                field.press_sequentially(first)  # Feld B ist bearbeitet, aber noch nicht verlassen
                done.append(held[0])
                held[0].continue_()  # jetzt antwortet der Server auf das Speichern von Feld A, die Ansicht zeichnet neu
                page.wait_for_function('el => !el.isConnected', arg=old)
                page.keyboard.type(rest)  # weitertippen, als wäre nichts gewesen
                release_all()
                page.unroute(save_glob)
                page.wait_for_load_state('networkidle')
                self.assertEqual(page.input_value(typed_field), text, 'getippter Text bleibt nach dem Neuzeichnen vollständig stehen')
                self.assertTrue(page.evaluate(f'() => document.activeElement === document.querySelector({json.dumps(typed_field)})'), 'Fokus bleibt im Feld')
                page.keyboard.press('Tab')  # Verlassen speichert den Text
                verify(page)
                self.assertEqual(errors, [])
                self.assertEqual(outside, [])
            finally:
                browser.close()

    def test_study_keeps_typed_answer(self):
        conn = connect(str(self.db))
        lead = conn.execute("INSERT INTO leads(company, stage) VALUES ('Studie Fiktiv GmbH', 'termin')").lastrowid
        conn.commit()
        conn.close()
        st = self.api('/studien', 'POST', {'lead_id': lead, 'title': 'Website vor dem Relaunch', 'phase': 'vorher', 'method': 'moderiert',
                                           'tasks': ['Telefonnummer finden'], 'questions': ['Was hat gestört?']})
        v = self.api(f"/studien/{st['id']}/sitzungen", 'POST', {'device': 'desktop', 'target_group': 'ja'})
        sid = v['sessions'][0]['id']
        task = next(t['id'] for t in v['tasks'] if t['kind'] == 'aufgabe')
        question = next(t['id'] for t in v['tasks'] if t['kind'] == 'frage')

        def prepare(page):
            page.locator('#stBox > summary').click()
            page.locator(f'[data-st-open="{st["id"]}"]').click()
            page.locator(f'details[data-st-session="{sid}"]').wait_for()

        def change_first(page):
            sel = page.locator(f'select[data-st-s="{sid}"][data-st-k="outcome"]')
            old = sel.element_handle()
            sel.select_option('geschafft')
            return old
        def verify(page):
            for _ in range(100):
                res = self.api(f"/studien/{st['id']}")['sessions'][0]['results']
                if (res.get(str(question)) or {}).get('answer') == TYPED:
                    break
                page.wait_for_timeout(50)
            self.assertEqual(res[str(task)]['outcome'], 'geschafft')
            self.assertEqual(res[str(question)]['answer'], TYPED, 'Antwort gespeichert')
        self.run_case('/#/angebote/auswertung', prepare, '**/api/studien/sitzung/*', change_first,
                      f'textarea[data-st-s="{sid}"][data-st-t="{question}"][data-st-k="answer"]', verify)

    def test_review_keeps_typed_evidence(self):
        conn = connect(str(self.db))
        lead = conn.execute("INSERT INTO leads(company) VALUES ('Review Fiktiv GmbH')").lastrowid
        conn.commit()
        make_audit(conn, lead)
        audit = conn.execute('SELECT id FROM website_audits WHERE lead_id=?', (lead,)).fetchone()[0]
        conn.close()
        rv = self.api('/fachreview', 'POST', {'audit_id': audit, 'reviewer': 'AB'})
        first, second = rv['items'][0]['id'], rv['items'][1]['id']

        def prepare(page):
            page.locator('#frBox > summary').click()
            page.locator(f'[data-fr-open="{rv["id"]}"]').click()
            page.locator(f'[data-fr-row="{first}"]').wait_for()

        def change_first(page):
            sel = page.locator(f'select[data-fr-item="{first}"][data-fr-key="verdict"]')
            old = sel.element_handle()
            values = sel.locator('option').evaluate_all('os => os.map(o => o.value)')
            sel.select_option(next(v for v in values if v != sel.input_value()))
            return old
        def verify(page):
            for _ in range(100):
                item = next(i for i in self.api(f"/fachreview/{rv['id']}")['items'] if i['id'] == second)
                if item['evidence'] == TYPED:
                    break
                page.wait_for_timeout(50)
            self.assertEqual(item['evidence'], TYPED, 'Beleg gespeichert')
        self.run_case('/#/finden/website-scoring', prepare, '**/api/fachreview/rubrik/*', change_first,
                      f'input[data-fr-item="{second}"][data-fr-key="evidence"]', verify)

    def test_pilot_keeps_typed_url(self):
        conn = connect(str(self.db))
        run = sw._run_record(conn, 'osm', None, {})
        for i in range(25):
            conn.execute("""INSERT INTO discovery_candidates(run_id, source, name, website, zip, city, industry)
                            VALUES (?, 'osm', ?, ?, '70191', 'Stuttgart', 'Maler')""", (run, f'Malerbetrieb {i:02d} Fiktiv', f'maler{i}.example'))
        conn.commit()
        conn.close()
        sample = self.api('/pilot', 'POST', {'size': 20})
        first, second = sample['items'][0]['id'], sample['items'][1]['id']

        def prepare(page):
            page.locator('#plBox > summary').click()
            page.locator(f'[data-pl-open="{sample["id"]}"]').click()
            page.locator(f'[data-pl-row="{first}"]').wait_for()

        def change_first(page):
            radio = page.locator(f'input[data-pl-item="{first}"][data-pl-key="target"][value="ja"]')
            old = radio.element_handle()
            radio.check()
            return old
        url = 'https://maler-fiktiv.example'

        def verify(page):
            for _ in range(100):
                item = next(i for i in self.api(f"/pilot/{sample['id']}")['items'] if i['id'] == second)
                if item['true_url'] == url:
                    break
                page.wait_for_timeout(50)
            self.assertEqual(item['true_url'], url, 'Echte Website gespeichert')
        self.run_case('/#/firmen/datenpflege', prepare, '**/api/pilot/eintrag/*', change_first,
                      f'input[data-pl-item="{second}"][data-pl-key="true_url"]', verify, text=url)


if __name__ == '__main__':
    unittest.main()
