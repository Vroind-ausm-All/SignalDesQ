import json
import sqlite3
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sales_tool.model import connect, discovery_summary, init_db
from sales_tool.server import import_leads, make_handler, validate_discovery


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'local.sqlite3'
        with connect(self.path) as conn:
            init_db(conn)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.path))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(f'http://127.0.0.1:{self.server.server_port}{path}', data=data,
                      headers={'Content-Type':'application/json'} if data else {}, method=method)
        with urlopen(req, timeout=3) as response:
            return response.status, json.load(response)

    def test_http_create_import_dedupe_and_discovery(self):
        status, result = self.call('POST','/api/leads', {'company': 'Testunternehmen', 'website': 'https://example.org', 'location': 'Stuttgart', 'contact_role':'Inhaber'})
        self.assertEqual(status, 201)
        id = result['id']
        status, empty = self.call('GET',f'/api/leads/{id}/discovery')
        self.assertEqual(empty['completeness']['answered'], 0)
        status, result = self.call('PUT',f'/api/leads/{id}/discovery',
          {'problem': 'Anfragen gehen im Postfach verloren', 'impact':'Zeitverlust',
           'desired_outcome':'Alle Anfragen nachhalten', 'timing':'Nächster Monat',
           'decision_process':'Geschäftsführung', 'budget_status':'freigabe_offen'})
        self.assertEqual(status, 200)
        self.assertEqual(result['completeness']['answered'],5)
        status, result = self.call('POST','/api/leads/import',{'rows':[
          {'company':'Zweite Firma', 'website':'https://andere.example', 'industry': 'Sonstige', 'employees': '', 'signal_type':'', 'permission':''},
          {'company':'Testunternehmen','website':'https://example.org'},
          {'company':'Dritte Firma','website':'javascript:invalid'},
        ]})
        self.assertEqual(result['imported'],1)
        self.assertEqual(result['duplicates'],1)
        self.assertEqual(len(result['errors']),1)
        status, rows = self.call('GET', '/api/leads')
        self.assertEqual(len(rows),2)
        status, result = self.call('DELETE',f'/api/leads/{id}')
        self.assertEqual(status,200)
        with connect(self.path) as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM discovery WHERE lead_id=?',(id,)).fetchone()[0],0)

    def test_rejects_unknown_discovery_fields(self):
        with self.assertRaises(ValueError):
            validate_discovery({'secret_data':'test'})
        with self.assertRaises(ValueError):
            validate_discovery({'budget_status':'garantiert'})

    def test_migrate_v01_database(self):
        legacy = Path(self.temp.name) / 'legacy.db'
        with sqlite3.connect(legacy) as con:
            con.execute('''CREATE TABLE leads (id INTEGER PRIMARY KEY, company TEXT, website TEXT, contact_name TEXT,
                 industry TEXT, employees INTEGER, signal_type TEXT, signal_date TEXT, signal_source TEXT, signal_note TEXT,
                 offer TEXT, estimated_budget INTEGER, stage TEXT, permission TEXT, permission_evidence TEXT, note TEXT,
                 next_step TEXT, next_date TEXT, created_at TEXT, updated_at TEXT)''')
            con.execute('INSERT INTO leads (company) VALUES (?)',('Altbestand',))
        with connect(legacy) as con:
            init_db(con)
            self.assertIn('location', {row[1] for row in con.execute('PRAGMA table_info(leads)')})
            self.assertEqual(con.execute('SELECT company FROM leads').fetchone()[0],'Altbestand')

if __name__=='__main__':
    unittest.main()
