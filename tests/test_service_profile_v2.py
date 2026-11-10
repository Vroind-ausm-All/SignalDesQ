"""Profilsteuerung: gespeicherte Werte gelten nur für neue regelbasierte Analysen."""
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sales_tool.model import connect, init_db
from sales_tool.quickscan import research
from sales_tool.research.service_profile import default_profile, fingerprint, load, save
from sales_tool.server import make_handler

CRAWL = {'source': 'https://firma.example/', 'pages': [{'url': 'https://firma.example/',
    'title': 'Firma', 'text': 'Unser Kundentag findet dieses Jahr statt. Karriere und Bewerbung sind möglich.'}], 'warnings': []}


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / 'profile.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def test_profile_controls_new_research_and_retains_snapshot(self):
        p = default_profile()
        p['name'] = 'Mein Profil'
        p['themes']['campaign']['keywords'] = ['Kundentag']
        p['themes']['recruiting']['enabled'] = False
        save(self.conn, p)
        result = research(CRAWL, profile=load(self.conn))
        self.assertEqual(result['audit']['service_profile']['version'], fingerprint(p))
        self.assertTrue(any('Kundentag' in f['evidence'] for f in result['audit']['findings']))
        self.assertFalse(any('Recruiting' in f['observation'] for f in result['audit']['findings']))
        snapshot = result['audit']['service_profile']['snapshot']
        p['themes']['campaign']['enabled'] = False
        save(self.conn, p)
        self.assertTrue(snapshot['themes']['campaign']['enabled'])
        self.assertNotEqual(fingerprint(p), result['audit']['service_profile']['version'])

    def test_rejects_invalid_profile_and_preserves_previous(self):
        p = default_profile()
        p['themes']['media']['keywords'] = ['x']
        with self.assertRaises(ValueError):
            save(self.conn, p)
        self.assertEqual(load(self.conn), default_profile())

    def test_http_save_and_reload(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{server.server_port}/api/research/service-profile'
        try:
            with urlopen(url) as response:
                profile = json.load(response)['profile']
            profile['themes']['campaign']['keywords'] = ['Kundentag']
            body = json.dumps(profile).encode()
            with urlopen(Request(url, data=body, method='POST', headers={'Content-Type': 'application/json'})) as response:
                self.assertEqual(json.load(response)['profile'], profile)
            with urlopen(url) as response:
                self.assertEqual(json.load(response)['profile'], profile)
            with self.assertRaises(HTTPError) as err:
                urlopen(Request(url, data=b'{}', method='POST', headers={'Content-Type': 'application/json'}))
            self.assertEqual(err.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
