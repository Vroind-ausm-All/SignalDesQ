"""2.0.0-dev46: Produktreview M29 (Fachreview erfassen) und M33 (Bewertung kalibrieren).

- Review zu einer abgeschlossenen Bewertung: Rubriken übernommen, Auswahl, Urteil, Beleg, Begründung, Prüfer, Version.
- Jede Eingabe sofort gespeichert („Abbruch“ = neue Verbindung, nichts verloren); „offen“ bleibt sichtbar.
- Abschließen nur vollständig (Urteil + Begründung, bei „auffällig“ ein Beleg); danach unveränderlich und nicht löschbar.
- Kalibrierung je Version und Rubrik nur aus abgeschlossenen Reviews und eindeutigen Urteilen; Gewichte bleiben unverändert.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import expert_review as er  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402

FINDINGS = [('A1', 'design', 'Kontrast', 'auffaellig'), ('A3', 'design', 'Überschriften', 'hinweis'),
            ('B1', 'web', 'Kontaktweg', 'ok'), ('B2', 'web', 'Ladezeit', 'unbekannt')]


def make_audit(conn, lead, status='done'):
    vid = conn.execute('SELECT id FROM score_versions WHERE active=1').fetchone()[0]
    aid = conn.execute("INSERT INTO website_audits(lead_id, url, status, version_id) VALUES (?, 'https://fiktiv.example', ?, ?)", (lead, status, vid)).lastrowid
    for rub, area, label, res in FINDINGS:
        conn.execute('''INSERT INTO website_findings(audit_id, lead_id, rubric, area, label, result, weight, evidence, method, certainty)
                        VALUES (?,?,?,?,?,?,1,'Messwert','messung','gemessen')''', (aid, lead, rub, area, label, res))
    conn.commit()
    return aid


class ExpertReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'e.sqlite3')
        prepare_database(self.db)
        self.conn = connect(self.db)
        self.lead = self.conn.execute("INSERT INTO leads(company) VALUES ('Review Fiktiv GmbH')").lastrowid
        self.aid = make_audit(self.conn, self.lead)

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def fill(self, v, verdicts):
        for i in v['items']:
            verdict = verdicts.get(i['rubric'])
            if verdict is None:
                v = er.update_item(self.conn, i['id'], {'included': False})
            else:
                v = er.update_item(self.conn, i['id'], {'verdict': verdict, 'reason': 'geprüft am Bildschirm', 'evidence': 'Screenshot Startseite'})
        return v

    def test_capture_save_and_complete(self):
        v = er.create(self.conn, {'audit_id': self.aid, 'reviewer': '  AB  '})
        self.assertEqual(v['reviewer'], 'AB')
        self.assertTrue(v['version_hash'])
        self.assertEqual([i['auto_result'] for i in v['items']], ['auffaellig', 'hinweis', 'ok', 'unbekannt'])
        self.assertTrue(all(i['verdict'] == 'offen' for i in v['items']))
        a1 = v['items'][0]['id']
        er.update_item(self.conn, a1, {'verdict': 'auffaellig', 'reason': 'Text kaum lesbar'})
        # „Abbruch“: neue Verbindung – nichts verloren
        other = connect(self.db)
        try:
            item = other.execute('SELECT verdict, reason FROM expert_review_items WHERE id=?', (a1,)).fetchone()
            self.assertEqual(tuple(item), ('auffaellig', 'Text kaum lesbar'))
        finally:
            other.close()
        v = er.view(self.conn, v['id'])
        self.assertIn('Kontrast: Beleg fehlt', v['missing'])
        self.assertIn('Überschriften: noch offen', v['missing'])
        with self.assertRaisesRegex(ValueError, 'Noch nicht vollständig'):
            er.complete(self.conn, v['id'], {})
        v = self.fill(v, {'A1': 'auffaellig', 'A3': 'ok', 'B1': 'ok'})
        self.assertEqual(v['progress'], {'chosen': 3, 'decided': 3, 'agree': 2})
        done = er.complete(self.conn, v['id'], {'note': 'Erstes Review'})
        self.assertEqual(done['status'], 'abgeschlossen')
        with self.assertRaisesRegex(ValueError, 'unveränderlich'):
            er.update_item(self.conn, a1, {'verdict': 'ok'})
        with self.assertRaisesRegex(ValueError, 'bleiben'):
            er.delete(self.conn, v['id'])

    def test_validation(self):
        with self.assertRaisesRegex(ValueError, 'Prüfer'):
            er.create(self.conn, {'audit_id': self.aid, 'reviewer': ' '})
        running = make_audit(self.conn, self.lead, status='running')
        with self.assertRaisesRegex(ValueError, 'abgeschlossene'):
            er.create(self.conn, {'audit_id': running, 'reviewer': 'AB'})
        v = er.create(self.conn, {'audit_id': self.aid, 'reviewer': 'AB'})
        with self.assertRaises(ValueError):
            er.update_item(self.conn, v['items'][0]['id'], {'verdict': 'super'})
        with self.assertRaises(ValueError):
            er.update_item(self.conn, v['items'][0]['id'], {'weight': 3})
        for i in v['items']:
            er.update_item(self.conn, i['id'], {'included': False})
        with self.assertRaisesRegex(ValueError, 'Mindestens eine Rubrik'):
            er.complete(self.conn, v['id'], {})
        self.assertEqual(er.delete(self.conn, v['id']), {'deleted': True})

    def test_calibration_only_completed_and_clear(self):
        weights = self.conn.execute('SELECT config_json FROM score_versions WHERE active=1').fetchone()[0]
        for n in range(5):  # A1: 4× einig, 1× „auffällig → ok“; B1: 5× uneinig
            aid = make_audit(self.conn, self.lead)
            v = er.create(self.conn, {'audit_id': aid, 'reviewer': f'P{n}'})
            v = self.fill(v, {'A1': 'auffaellig' if n else 'ok', 'B1': 'auffaellig', 'B2': 'ok'})
            er.complete(self.conn, v['id'], {})
        draft = er.create(self.conn, {'audit_id': self.aid, 'reviewer': 'Entwurf'})
        self.fill(draft, {'A1': 'ok', 'B1': 'ok'})  # Entwurf zählt nicht
        c = er.calibration(self.conn)
        rows = {r['rubric']: r for r in c['rows']}
        self.assertEqual((rows['A1']['agree'], rows['A1']['n'], rows['A1']['pct']), (4, 5, 80))
        self.assertEqual(rows['A1']['directions'], {'auffällig → ok': 1})
        self.assertFalse(rows['A1']['flag'])
        self.assertEqual((rows['B1']['agree'], rows['B1']['n']), (0, 5))
        self.assertTrue(rows['B1']['flag'])
        self.assertEqual(rows['B2']['n'], 5, 'automatisch „unbekannt“, dein Urteil eindeutig – zählt als Abweichung')
        self.assertEqual(c['completed_reviews'], 5)
        self.assertIn('ändert keine Gewichte', c['notice'])
        self.assertEqual(self.conn.execute('SELECT config_json FROM score_versions WHERE active=1').fetchone()[0], weights)


if __name__ == '__main__':
    unittest.main()
