"""R1.5 (2.0.0-dev69): Firmenidentität – Konfliktfälle bleiben getrennt (Regressionstests).

Grundsatz: Identität über LEI, Registergericht + Nummer, Domain + Name/Anschrift; Marke und Rechtsträger getrennt; bei
einem Konflikt nie automatisch zusammenführen. Alle Firmen sind erfunden.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sales_tool import duplicates  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.research import identity  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402

# (Fall, a, b, erlaubte Urteile) – keiner dieser Fälle darf 'same' ergeben
CONFLICTS = [
    ('gleiche Nummer, anderes Registergericht (Text)',
     {'name': 'Muster Bau GmbH', 'register_id': 'HRB 12345 Amtsgericht Stuttgart'},
     {'name': 'Muster Bau GmbH', 'register_id': 'HRB 12345 Amtsgericht München'}, ('different',)),
    ('gleiche Nummer, anderes Registergericht (Feld)',
     {'name': 'Muster Bau GmbH', 'register_id': 'HRB 12345', 'register_court': 'Amtsgericht Stuttgart'},
     {'name': 'Muster Bau GmbH', 'register_id': 'HRB 12345', 'register_court': 'Amtsgericht Ulm'}, ('different',)),
    ('Marke und Träger unter derselben Website',
     {'name': 'Sonnenschein Kita', 'website': 'https://sonnenschein-fiktiv.de', 'city': 'Ulm'},
     {'name': 'Kinderhaus Träger gGmbH', 'website': 'https://www.sonnenschein-fiktiv.de', 'city': 'Ulm'}, ('possible',)),
    ('KG und Verwaltungs-GmbH', {'name': 'Muster Bau GmbH & Co. KG', 'city': 'Ulm'},
     {'name': 'Muster Bau Verwaltungs GmbH', 'city': 'Ulm'}, ('different',)),
    ('GmbH und e.K.', {'name': 'Müller Elektro GmbH', 'city': 'Ulm'}, {'name': 'Müller Elektro e.K.', 'city': 'Ulm'}, ('different',)),
    ('Niederlassung in anderer Stadt', {'name': 'Muster Logistik GmbH', 'city': 'Hamburg'},
     {'name': 'Muster Logistik GmbH', 'city': 'Berlin'}, ('different',)),
    ('verschiedene LEI', {'name': 'Muster AG', 'lei': '529900AAAAAAAAAAAA01'}, {'name': 'Muster AG', 'lei': '529900BBBBBBBBBBBB02'},
     ('different',)),
    ('gleiche Domain, verschiedene Registernummer', {'name': 'Muster GmbH', 'website': 'muster-fiktiv.de', 'register_id': 'HRB 1'},
     {'name': 'Muster GmbH', 'website': 'muster-fiktiv.de', 'register_id': 'HRB 2'}, ('different',)),
    ('Plattform-Seite ist keine eigene Domain', {'name': 'Bäckerei Sonne', 'website': 'https://facebook.com/sonne', 'city': 'Ulm'},
     {'name': 'Bäckerei Mond', 'website': 'https://facebook.com/mond', 'city': 'Ulm'}, ('different', 'possible')),
    ('Holding und Betriebsgesellschaft', {'name': 'Muster Holding GmbH', 'city': 'Ulm'}, {'name': 'Muster GmbH', 'city': 'Ulm'},
     ('different', 'possible')),
    ('häufiger Name ohne Ort', {'name': 'Müller GmbH'}, {'name': 'Müller GmbH'}, ('possible',)),
]

# Diese Paare SIND dieselbe Firma – die Korrekturen dürfen sie nicht trennen
SAME = [
    ('gleiche Nummer, Gericht einmal als Feld, einmal im Text',
     {'name': 'Muster Bau GmbH', 'register_id': 'HRB 12345', 'register_court': 'Amtsgericht Stuttgart'},
     {'name': 'Muster Bau GmbH', 'register_id': 'HRB 12345 AG Stuttgart'}),
    ('gleiche Nummer, Gericht nur auf einer Seite', {'name': 'Muster Bau GmbH', 'register_id': 'HRB 12345 Amtsgericht Stuttgart'},
     {'name': 'Muster Bau GmbH', 'register_id': 'HRB 12345'}),
    ('gleiche Website, ähnlicher Name', {'name': 'Muster Elektrotechnik GmbH', 'website': 'muster-fiktiv.de'},
     {'name': 'Muster Elektrotechnik', 'website': 'https://www.muster-fiktiv.de/kontakt'}),
    ('gleiche LEI', {'name': 'Muster AG', 'lei': '529900AAAAAAAAAAAA01'}, {'name': 'Muster Aktiengesellschaft', 'lei': '529900aaaaaaaaaaaa01'}),
]


class IdentityConflictTests(unittest.TestCase):
    def test_conflicts_are_never_merged(self):
        for case, a, b, allowed in CONFLICTS:
            for x, y in ((a, b), (b, a)):  # Reihenfolge egal
                with self.subTest(case):
                    verdict, _, reason = identity.decide(x, y)
                    self.assertIn(verdict, allowed, f'{case}: {verdict} ({reason})')

    def test_true_duplicates_stay_same(self):
        for case, a, b in SAME:
            with self.subTest(case):
                self.assertEqual(identity.decide(a, b)[0], 'same', case)

    def test_register_number_keeps_city_suffix_but_not_court(self):
        self.assertEqual(identity.norm_register('HRB 12345 AG Stuttgart'), 'HRB12345')
        self.assertEqual(identity.norm_register('HRB 12345 B'), 'HRB12345B')
        self.assertEqual(identity.norm_court('Registergericht: Amtsgericht Frankfurt am Main, HRB 7'), 'frankfurt')
        self.assertEqual(identity.norm_court('HRB 12345'), '')


class LeadDuplicateTests(unittest.TestCase):
    """Dublettenprüfung der Firmenliste: gleiche Nummer bei anderem Gericht ist kein Duplikat."""

    def test_same_number_other_court_is_not_a_duplicate(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'd.sqlite3'
            prepare_database(db)
            with connect(db) as conn:
                a = conn.execute("""INSERT INTO leads(company, register_court, register_number, city)
                                    VALUES ('Muster Bau GmbH', 'Amtsgericht Stuttgart', 'HRB 12345', '')""").lastrowid
                b = conn.execute("""INSERT INTO leads(company, register_court, register_number, city)
                                    VALUES ('Muster Bau GmbH', 'Amtsgericht München', 'HRB 12345', '')""").lastrowid
                conn.commit()
                ra = conn.execute('SELECT * FROM leads WHERE id=?', (a,)).fetchone()
                rb = conn.execute('SELECT * FROM leads WHERE id=?', (b,)).fetchone()
                self.assertEqual(identity.decide(duplicates.lead_item(ra), duplicates.lead_item(rb))[0], 'different')


if __name__ == '__main__':
    unittest.main()
