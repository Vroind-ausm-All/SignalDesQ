"""Contact identity tests; no paid API nor social-network scraping."""
import unittest
from sales_tool.contacts import validate_contact, role_suggestions

class ContactDomainTests(unittest.TestCase):
    def test_roles_depend_on_offer_and_size(self):
        self.assertIn('IT-',role_suggestions({'offer':'portal','employees':120})[0])
        self.assertEqual('Geschäftsführung',role_suggestions({'offer':'pilot','employees':20})[0])
    def test_source_mandatory_and_https_only(self):
        for val in [
          {'full_name':'Anna Beispiel','decision_role':'unbekannt'},
          {'full_name':'Anna Beispiel','decision_role':'fachlich','source_url':'javascript:alert(1)'},
          {'full_name':'Anna Beispiel','decision_role':'fachlich','source_url':'https://user:pw@site.example/'}]:
            with self.assertRaises(ValueError):validate_contact(val)
        r=validate_contact({'full_name':'Anna Beispiel','decision_role':'fachlich','source_url':'https://demo.example/team'})
        self.assertEqual(r['full_name'],'Anna Beispiel')
