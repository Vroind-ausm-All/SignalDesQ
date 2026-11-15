"""2.0.0-dev29: Produktreview M37 – eigene Nachrichtenvorlagen mit Platzhaltern.

Abnahme: Anrede und Felder nur aus bestätigten Daten; fehlende Werte sichtbar; Endfassung vor Versand prüfbar.
Leitplanken: Sperre der Firma und Einschränkungen der Person gelten für Vorschau und Entwurf; Anrede nie aus dem Vornamen;
kein Versand. Alle Firmen und Personen sind fiktiv; keine Netzabfragen.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5_helpers import confirm_need, release_offer  # noqa: E402
from test_accounting import SELLER  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import accounting as acc  # noqa: E402
from sales_tool import messages as ms  # noqa: E402
from sales_tool import offer_flow as of  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.sales_integration import update_contact_roles  # noqa: E402
from sales_tool.sales_workspace import create_mail_draft, make_proposal  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402
from sales_tool.workday import ContactLocked  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'm.sqlite3')
        prepare_database(self.db)
        self.conn = connect(self.db)
        self.lead = self.conn.execute("INSERT INTO leads(company, stage) VALUES ('Vorlage Fiktiv GmbH', 'termin')").lastrowid
        self.contact = self.conn.execute("INSERT INTO decision_contacts(lead_id, full_name) VALUES (?, 'Maria Beispiel')", (self.lead,)).lastrowid
        self.conn.commit()
        self.tpl = {t['key']: t['id'] for t in ms.list_templates(self.conn)['templates'] if t['key']}

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def render(self, key='angebot_versand', **kw):
        return ms.render(self.conn, self.tpl[key], {'lead_id': self.lead, **kw})


class MessageTests(Base):
    def test_missing_values_visible_until_confirmed_data_exists(self):
        r = self.render()
        self.assertFalse(r['complete'])
        self.assertTrue(r['body'].startswith('Guten Tag,'), 'ohne Person neutral')
        for label in ('Angebotsnummer', 'Festpreis netto des Angebots', 'Dein Name', 'Nächste Nachfassfrist zum Angebot'):
            self.assertIn(label, r['missing'])
        self.assertIn('[FEHLT: Angebotsnummer]', r['subject'])
        acc.save_settings(self.conn, SELLER)
        confirm_need(self.conn, self.lead)
        p = make_proposal(self.conn, {'lead_id': self.lead, 'tax_mode': 'regel_19', 'project_label': 'Neue Website', 'positions': [{'service': 'webdesign', 'size': 'S'}]})
        r = self.render(proposal_id=p['id'], contact_id=self.contact)
        self.assertIn('Stand der freigegebenen Versandfassung', r['missing'], 'Stand erst nach Freigabe')
        release_offer(self.conn, p['id'])
        of.set_status(self.conn, p['id'], {'status': 'gesendet_manuell'})
        r = self.render(proposal_id=p['id'], contact_id=self.contact)
        self.assertEqual(r['missing'], [])
        self.assertTrue(r['complete'])
        self.assertEqual(r['subject'], f"Angebot {p['number']}: Neue Website")
        self.assertTrue(r['body'].startswith('Guten Tag Maria Beispiel,'), 'Anrede nicht aus dem Vornamen geraten')
        self.assertEqual(r['used']['anrede']['source'], 'neutral')
        update_contact_roles(self.conn, self.contact, {'salutation': 'frau'})
        r = self.render(proposal_id=p['id'], contact_id=self.contact)
        self.assertTrue(r['body'].startswith('Sehr geehrte Frau Beispiel,'))
        self.assertEqual(r['used']['anrede']['source'], 'Anrede an der Person hinterlegt')
        d = create_mail_draft(self.conn, {'lead_id': self.lead, 'template_id': self.tpl['angebot_versand'], 'proposal_id': p['id'],
                                          'contact_id': self.contact, 'contact_basis': 'Angebot im Termin am 12.11. zugesagt'})
        self.assertTrue(d['complete'])
        self.assertIn('nicht versendet', d['notice'])
        with self.assertRaisesRegex(ValueError, 'Anlass'):
            create_mail_draft(self.conn, {'lead_id': self.lead, 'template_id': self.tpl['angebot_versand']})

    def test_own_templates_and_unknown_placeholders(self):
        with self.assertRaisesRegex(ValueError, 'Unbekannte Platzhalter: \\{\\{vorname\\}\\}'):
            ms.save_template(self.conn, None, {'title': 'Eigene', 'subject': 'Hallo {{vorname}}', 'body': 'x'})
        t = ms.save_template(self.conn, None, {'title': 'Eigene', 'subject': 'Kurz zu {{ firma }}', 'body': '{{anrede}}\n\nText.'})
        r = ms.render(self.conn, t['id'], {'lead_id': self.lead})
        self.assertEqual(r['subject'], 'Kurz zu Vorlage Fiktiv GmbH')
        ms.save_template(self.conn, self.tpl['nachfassen'], {'title': 'Nachfassen', 'subject': 'Angepasst', 'body': 'Text'})
        with self.assertRaisesRegex(ValueError, 'nicht löschen'):
            ms.delete_template(self.conn, self.tpl['nachfassen'])
        self.assertTrue(ms.delete_template(self.conn, t['id'])['deleted'])
        with self.assertRaisesRegex(ValueError, 'Anrede'):
            update_contact_roles(self.conn, self.contact, {'salutation': 'Dr.'})

    def test_blocked_firm_and_restricted_person(self):
        self.conn.execute("UPDATE decision_contacts SET contact_restrictions='[\"keine_email\"]' WHERE id=?", (self.contact,))
        self.conn.commit()
        with self.assertRaisesRegex(ContactLocked, 'keine E-Mails'):
            self.render(contact_id=self.contact)
        other_lead = self.conn.execute("INSERT INTO leads(company) VALUES ('Andere Fiktiv KG')").lastrowid
        other = self.conn.execute("INSERT INTO decision_contacts(lead_id, full_name) VALUES (?, 'Fremd')", (other_lead,)).lastrowid
        self.conn.commit()
        with self.assertRaisesRegex(ValueError, 'gehört nicht'):
            self.render(contact_id=other)
        self.conn.execute("UPDATE leads SET permission='nicht_kontaktieren' WHERE id=?", (self.lead,))
        self.conn.commit()
        with self.assertRaises(ContactLocked):
            self.render()
        with self.assertRaises(ContactLocked):
            create_mail_draft(self.conn, {'lead_id': self.lead, 'template_id': self.tpl['nach_gespraech'], 'contact_basis': 'Gespräch am 12.11.'})
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM mail_drafts').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
