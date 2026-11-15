"""2.0.0-dev45: Produktreview M21 – Recherchepilot: Stichprobe ziehen, von Hand prüfen, Quoten.

- Zufallsstichprobe in der gewünschten Größe, ohne Dubletten, wahlweise nur eine Quelle.
- Beim Ziehen wird der damalige Stand festgehalten; spätere Änderungen an der Firma ändern die Messung nicht.
- Quoten nur aus eindeutigen Angaben („unklar“ zählt nicht), mit Anzahl; kleine Basis wird gekennzeichnet.
- Ungültige Angaben werden abgelehnt; CSV-Export enthält Einträge und Quoten.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import pilot  # noqa: E402
from sales_tool import sweep as sw  # noqa: E402
from sales_tool.model import connect, init_db  # noqa: E402


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = c = connect(Path(self.tmp.name) / 'p.sqlite3')
        init_db(c)
        run = sw._run_record(c, 'osm', None, {})
        for i in range(60):
            src = 'osm' if i < 40 else 'gleif'
            c.execute("""INSERT INTO discovery_candidates(run_id, source, name, website, zip, city, industry, website_status)
                         VALUES (?,?,?,?, '70191', 'Stuttgart', 'Handwerk', ?)""",
                      (run, src, f'Betrieb {i:02d} Fiktiv', f'betrieb{i}.example' if i % 2 else '', 'wahrscheinlich' if i % 2 else ''))
        c.execute("INSERT INTO discovery_candidates(run_id, source, name, dup_of) VALUES (?, 'osm', 'Dublette', 1)", (run,))
        c.commit()

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def test_draw_snapshot_and_filter(self):
        v = pilot.draw(self.conn, {'size': 20, 'source': 'osm'}, rng=random.Random(1))
        self.assertEqual(len(v['items']), 20)
        self.assertTrue(all(i['snapshot']['source'] == 'osm' for i in v['items']))
        self.assertNotIn('Dublette', [i['snapshot']['name'] for i in v['items']])
        self.assertEqual(len({i['candidate_id'] for i in v['items']}), 20)
        first = v['items'][0]
        self.conn.execute("UPDATE discovery_candidates SET website='anders.example' WHERE id=?", (first['candidate_id'],))
        self.assertEqual(pilot.view(self.conn, v['id'])['items'][0]['snapshot']['website'], first['snapshot']['website'], 'Stand beim Ziehen')
        with self.assertRaisesRegex(ValueError, '20, 50, 75 oder 100'):
            pilot.draw(self.conn, {'size': 7})
        with self.assertRaisesRegex(ValueError, 'Zu wenige'):
            pilot.draw(self.conn, {'size': 20, 'source': 'ted'})

    def test_metrics_count_only_clear_answers(self):
        v = pilot.draw(self.conn, {'size': 50}, rng=random.Random(2))
        shown = [i for i in v['items'] if i['snapshot']['website']]
        hidden = [i for i in v['items'] if not i['snapshot']['website']]
        for n, i in enumerate(shown[:10]):
            pilot.mark(self.conn, i['id'], {'target': 'ja', 'website': 'richtig' if n < 8 else 'falsch', 'has_site': 'ja', 'industry': 'richtig'})
        for n, i in enumerate(hidden[:6]):
            pilot.mark(self.conn, i['id'], {'target': 'ja', 'website': 'fehlt', 'has_site': 'ja' if n < 3 else 'nein', 'industry': 'falsch'})
        pilot.mark(self.conn, hidden[6]['id'], {'target': 'nein'})
        pilot.mark(self.conn, hidden[7]['id'], {'target': 'unklar'})
        m = pilot.view(self.conn, v['id'])['metrics']
        self.assertEqual(m['target_share'], {'hit': 16, 'of': 17, 'pct': 94})
        self.assertEqual(m['website_precision'], {'hit': 8, 'of': 10, 'pct': 80})
        self.assertEqual(m['website_coverage'], {'hit': 8, 'of': 13, 'pct': 62})  # 10 + 3 mit Website, 8 richtig gefunden
        self.assertEqual(m['industry_correct'], {'hit': 10, 'of': 16, 'pct': 62})
        self.assertEqual(m['checked'], 17, '„unklar“ beim Zielbetrieb gilt nicht als geprüft')
        self.assertIn('Kleine Basis', m['notice'])

    def test_validation_export_delete(self):
        v = pilot.draw(self.conn, {'size': 20}, rng=random.Random(3))
        iid = v['items'][0]['id']
        with self.assertRaises(ValueError):
            pilot.mark(self.conn, iid, {'target': 'vielleicht'})
        with self.assertRaises(ValueError):
            pilot.mark(self.conn, iid, {'passwort': 'x'})
        pilot.mark(self.conn, iid, {'target': 'ja', 'true_url': 'https://richtig.example', 'note': 'Impressum geprüft'})
        csv_text = pilot.export_csv(self.conn, v['id']).decode('utf-8-sig')
        self.assertIn('https://richtig.example', csv_text)
        self.assertIn('Trefferquote Websites', csv_text)
        self.assertEqual(len(pilot.overview(self.conn)['samples']), 1)
        pilot.delete(self.conn, v['id'])
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM pilot_items').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
