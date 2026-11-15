"""Browserprüfung 2.0.0-dev30 (Produktreview M25): Kurzbericht – nur geprüfte Befunde wählbar, Vorschau ohne interne Werte,
Download. Fiktive Firma, keine Abrufe nach außen."""
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

from sales_tool.model import connect
from sales_tool.server import make_handler, prepare_database


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class KurzberichtBrowserTests(unittest.TestCase):
    def test_select_reviewed_findings_and_download(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'kr.sqlite3'
            prepare_database(db)
            c = connect(str(db))
            lead = c.execute("INSERT INTO leads(company, website) VALUES ('Bericht Fiktiv GmbH', 'https://bericht.example')").lastrowid
            a = c.execute("INSERT INTO website_audits(lead_id, url, status, finished_at) VALUES (?, 'https://bericht.example', 'done', '2026-11-10 10:00:00')", (lead,)).lastrowid
            ins = """INSERT INTO website_findings(audit_id, lead_id, rubric, area, label, result, weight, evidence, source_url, method, certainty, offer, question, review_status)
                     VALUES (?, ?, ?, 'web', ?, 'auffaellig', 3, ?, 'https://bericht.example/', 'dom', 'beobachtet', 'conversion', 'Wie erreichen Kunden Sie heute?', ?)"""
            c.execute(ins, (a, lead, 'B3', 'Sichtbarer Anfrageaufruf', 'Ohne Scrollen ist kein Anfrageweg sichtbar.', 'bestaetigt'))
            c.execute(ins, (a, lead, 'B4', 'Ungeprüfter Punkt', 'Vermutung', 'ungeprueft'))
            c.commit()
            c.close()
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900}, accept_downloads=True)
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base + '/#/finden/website-scoring')
                        page.wait_for_load_state('networkidle')
                        page.locator(f'#krLead option[value="{lead}"]').wait_for(state='attached')
                        page.select_option('#krLead', str(lead))
                        page.locator('[data-kr-item]').first.wait_for(state='attached')
                        self.assertEqual(page.locator('[data-kr-item]').count(), 1, 'nur der geprüfte Befund')
                        self.assertIn('1 ungeprüfte', page.locator('[data-kr-hidden]').inner_text())
                        page.locator('[data-kr-item]').check()
                        page.locator('#krForm button[type=submit]').click()
                        md = page.locator('#krPreview [data-kr-md]')
                        md.wait_for()
                        text = md.inner_text()
                        self.assertIn('Sichtbarer Anfrageaufruf', text)
                        for internal in ('conversion', 'Vermutung', 'auffaellig'):
                            self.assertNotIn(internal, text)
                        with page.expect_download() as dl:
                            page.locator('#krDownload').click()
                        self.assertTrue(dl.value.suggested_filename.startswith('Kurzbericht-Bericht-Fiktiv-GmbH-'))
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
