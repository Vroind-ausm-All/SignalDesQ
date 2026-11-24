"""Browserprüfung SDQ-001: Nach einer Abschlagsrechnung über 40 % bleiben 60 % als noch abzurechnen sichtbar.

- Abrechnen → „Aus Angeboten berechnen“: Kurzstand nennt den offenen Restbetrag, der Eintrag zeigt „teilweise abgerechnet“ und
  bietet die Schlussrechnung über den Rest an (statt erneut „Abschlag 40 %“).
- Angebote: nächster Schritt „Schlussrechnung: … netto offen“ statt „–“.
- Heute → Potenzial: „Angenommen, noch nicht abgerechnet“ zeigt den Rest (6.000 €), nicht 0 €.
- Schlussrechnung festgeschrieben → das Angebot verschwindet aus der Liste.
Fiktive Firma, keine Abrufe nach außen."""
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from test_accounting import SELLER, buyer  # noqa: E402

from sales_tool import accounting as acc  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.sales_workspace import make_proposal  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402


def issue(conn, inv):
    lines = [{k: x[k] for k in ('description', 'quantity', 'unit', 'unit_price_cents', 'vat_rate')} for x in inv['lines']]
    return acc.finalize_invoice(conn, acc.update_invoice(conn, inv['id'], {**buyer(), 'lead_id': inv['lead_id'], 'lines': lines})['id'])


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class BillingStateBrowserTests(unittest.TestCase):
    def test_deposit_keeps_rest_visible(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'bs.sqlite3'
            prepare_database(db)
            with connect(db) as conn:
                acc.save_settings(conn, SELLER)
                lead = conn.execute("INSERT INTO leads(company, permission, stage) VALUES ('Beispiel Maschinenbau GmbH', 'opt_in', 'gewonnen')").lastrowid
                from sales_tool.pricing import save_override
                save_override(conn, {'service': 'logo', 'size': 'L', 'fixed_price': 10000})
                prop = make_proposal(conn, {'lead_id': lead, 'positions': [{'service': 'logo', 'size': 'L'}], 'tax_mode': 'regel_19'})
                conn.execute("UPDATE proposals SET status='angenommen' WHERE id=?", (prop['id'],))
                conn.commit()
                issue(conn, acc.invoice_from_proposal(conn, {'proposal_id': prop['id'], 'mode': 'abschlag', 'percent': 40}))
                # Projekt gestartet und abgenommen: erst dann ist die Schlussrechnung der nächste Schritt in der Angebotsliste
                # (vorher heißt er „Kick-off …“ bzw. „Übergabe & Abnahme …“ – der Rest bleibt unter Abrechnen und Heute sichtbar)
                from sales_tool import handover, kickoff
                kickoff.act(conn, prop['id'], {'action': 'start', 'trotz_offener_punkte': True})
                for it in handover.state(conn, prop['id'])['items']:
                    if it['kind'] == 'liefer':
                        handover.act(conn, prop['id'], {'action': 'item', 'item_id': it['id'], 'state': 'erledigt'})
                handover.act(conn, prop['id'], {'action': 'uebergabe'})
                handover.act(conn, prop['id'], {'action': 'abnahme', 'result': 'abgenommen'})
                conn.commit()
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
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

                        # ---- Abrechnen
                        go('#/abrechnen')
                        page.wait_for_function('() => document.querySelector("#accUnbilledState").textContent.length > 0')
                        state = page.text_content('#accUnbilledState')
                        self.assertIn('noch nicht vollständig abgerechnet', state)
                        self.assertIn('6.000,00', state)
                        item = page.locator('#accUnbilled [data-billing-state="teilweise"]')
                        self.assertEqual(item.count(), 1)
                        text = item.text_content()
                        self.assertIn('teilweise abgerechnet', text)
                        self.assertIn('4.000,00', text)
                        self.assertIn('10.000,00', text)
                        self.assertIn('6.000,00', text)
                        self.assertEqual(item.locator('[data-mode="schluss"]').count(), 1)
                        self.assertEqual(item.locator('[data-mode="abschlag"]').count(), 0, 'kein zweiter Abschlag als Vorschlag')

                        # ---- Angebote: nächster Schritt nennt den Rest
                        go('#/angebote')
                        # Die Liste zeichnet zuerst ohne Projektstand und danach mit – geprüft wird der Endstand
                        page.wait_for_function('() => document.body.innerText.includes("Schlussrechnung:")')
                        page.wait_for_load_state('networkidle')
                        page.wait_for_timeout(300)
                        quotes = page.inner_text('#viewQuotes')
                        self.assertIn('Schlussrechnung: 6.000', quotes)
                        self.assertIn('netto offen', quotes)
                        self.assertNotIn('Kick-off:', quotes)

                        # ---- Heute: Potenzial zeigt den Rest
                        go('#/heute')
                        page.wait_for_function('() => (document.querySelector("#tdPotKpis")?.textContent || "").includes("Angenommen")')
                        kpi = page.locator('#tdPotKpis > div', has_text='Angenommen, noch nicht abgerechnet').text_content()
                        self.assertIn('6.000', kpi)
                        self.assertIn('teilweise abgerechnet', page.text_content('#tdPot'))

                        # ---- Schlussrechnung festschreiben → nichts mehr offen
                        with connect(db) as conn:
                            issue(conn, acc.invoice_from_proposal(conn, {'proposal_id': prop['id'], 'mode': 'schluss'}))
                        go('#/abrechnen')
                        page.wait_for_function('() => document.querySelector("#accUnbilledState").textContent === "alle angenommenen Angebote sind vollständig abgerechnet"')
                        self.assertEqual(page.locator('#accUnbilled [data-billing-state]').count(), 0)
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
