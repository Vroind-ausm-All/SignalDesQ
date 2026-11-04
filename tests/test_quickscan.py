"""v0.7 URL-first flow: source-grounded report, CRM consent gates, persistence and API."""
import json
import sqlite3
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from sales_tool.model import connect, init_db
from sales_tool.quickscan import research, company_guess, run_job, import_scan, list_scans
from sales_tool.server import make_handler


CRAWL = {
    'source':'https://beispiel-firma.de/',
    'warnings': [],
    'pages': [
        {'url':'https://beispiel-firma.de/', 'title':'Beispiel Firma GmbH | Lösungen',
         'text':'Unsere Produkte und Leistungen: Produktblätter als PDF. Nutzen Sie das Kontaktformular für Ihre Anfrage.',
         'raw_text':'Unsere Produkte und Leistungen: Produktblätter als PDF. Nutzen Sie das Kontaktformular für Ihre Anfrage.',
         'headings':['Lösungen'], 'form_count':1},
        {'url':'https://beispiel-firma.de/team', 'title':'Team – Beispiel Firma',
         'text':'Team\nGeschäftsführung: Anna Musterfrau\nTelefon: 0711 1234567\nMarketingleitung: Max Mustermann\nDurchwahl: 0711 555123',
         'raw_text':'Team\nGeschäftsführung: Anna Musterfrau\nTelefon: 0711 1234567\nMarketingleitung: Max Mustermann\nDurchwahl: 0711 555123', 'headings':['Team'], 'form_count':0},
        {'url':'https://beispiel-firma.de/kontakt', 'title':'Kontakt',
         'text':'Kontakt: office@beispiel-firma.de Telefon: 0711 1234567',
         'raw_text':'Kontakt: office@beispiel-firma.de Telefon: 0711 1234567',
         'headings':['Kontakt'], 'form_count':0}
    ]
}


class QuickScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/'test.sqlite3'
        with connect(self.db) as c:init_db(c)

    def tearDown(self):self.tmp.cleanup()

    def _completed_scan(self):
        with connect(self.db) as c:
            c.execute("INSERT INTO quick_scans(url,provider,model) VALUES ('https://beispiel-firma.de/','rules','regelmodus')")
            rid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.commit()
        with patch('sales_tool.quickscan.crawl_site', return_value=CRAWL):
            run_job(self.db,rid,'https://beispiel-firma.de/','rules','qwen3:8b')
        return rid

    def test_result_has_grounded_findings_contacts_questions(self):
        d=research(CRAWL)
        self.assertEqual(d['site']['company_label'],'Beispiel Firma GmbH')
        self.assertEqual(len(d['questions']),3)
        self.assertTrue(d['audit']['findings'])
        for f in d['audit']['findings']:
            page=next(p for p in CRAWL['pages'] if p['url']==f['source_url'])
            self.assertIn(f['evidence'],page['text'])
        self.assertIn('office@beispiel-firma.de', [c['value'] for c in d['contact_channels']])
        for p in d['decision_makers']['people']:
            self.assertEqual(p['business_phone'],'') # footer/other line never attributed

    def test_crm_import_requires_human_review(self):
        rid=self._completed_scan()
        with connect(self.db) as c:
            r=import_scan(c,rid)
            c.commit()
            self.assertGreater(r['findings_pending_review'],0)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM findings WHERE lead_id=? AND review_status='ungeprueft'",(r['lead_id'],)).fetchone()[0],r['findings_pending_review'])
            self.assertEqual(c.execute("SELECT permission FROM leads WHERE id=?",(r['lead_id'],)).fetchone()[0],'unbekannt')
            self.assertEqual(c.execute("SELECT COUNT(*) FROM decision_contacts WHERE lead_id=?",(r['lead_id'],)).fetchone()[0],0)
            again=import_scan(c,rid)
            self.assertTrue(again['already_imported'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM leads').fetchone()[0],1)

    def test_reuses_existing_domain_without_overwriting(self):
        rid=self._completed_scan()
        with connect(self.db) as c:
            c.execute("INSERT INTO leads(company,website,permission,signal_note,stage) VALUES ('Original','https://www.beispiel-firma.de/angebot','opt_in','Bestätigtes Signal','kontakt')")
            c.commit()
            r=import_scan(c,rid)
            c.commit()
            self.assertTrue(r['existing'])
            lead=c.execute('SELECT * FROM leads WHERE id=?',(r['lead_id'],)).fetchone()
            self.assertEqual(lead['company'],'Original')
            self.assertEqual(lead['signal_note'],'Bestätigtes Signal')
            self.assertEqual(lead['permission'],'opt_in')
            self.assertEqual(lead['stage'],'kontakt')

    def test_blocked_lead_cannot_import(self):
        rid=self._completed_scan()
        with connect(self.db) as c:
            c.execute("INSERT INTO leads(company,website,permission,stage) VALUES ('Block','https://beispiel-firma.de/','nicht_kontaktieren','gesperrt')")
            c.commit()
            with self.assertRaisesRegex(ValueError,'gesperrt'):import_scan(c,rid)

    def test_failures_persist_and_never_import(self):
        with connect(self.db) as c:
            c.execute("INSERT INTO quick_scans(url,provider) VALUES ('https://beispiel-firma.de/','rules')")
            rid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.commit()
        with patch('sales_tool.quickscan.crawl_site',side_effect=ValueError('Abruf blockiert')):
            run_job(self.db,rid,'https://beispiel-firma.de/','rules','qwen3:8b')
        with connect(self.db) as c:
            rows=list_scans(c)
            self.assertEqual(rows[0]['status'],'failed')
            self.assertIn('Abruf blockiert',rows[0]['error'])
            with self.assertRaises(ValueError):import_scan(c,rid)

    def test_api_responds_and_requires_explicit_import(self):
        rid=self._completed_scan()
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.db))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{server.server_port}'
        def req(path,method='GET',data=None):
            buf=json.dumps(data).encode() if data is not None else None
            headers={'Content-Type':'application/json'} if buf else {}
            with urlopen(Request(base+path,data=buf,method=method,headers=headers),timeout=6) as r:
                return r.status,json.load(r)
        try:
            status,d=req('/api/research/'+str(rid))
            self.assertEqual(status,200)
            self.assertEqual(d['result']['site']['company_label'],'Beispiel Firma GmbH')
            with self.assertRaises(HTTPError) as e:req('/api/research/'+str(rid)+'/import','POST',{'confirm':False})
            self.assertEqual(e.exception.code,400)
            status,result=req('/api/research/'+str(rid)+'/import','POST',{'confirm':True})
            self.assertEqual(status,200)
            self.assertTrue(result['lead_id']>0)
            status,html=req('/api/research')
            self.assertEqual(status,200)
            self.assertEqual(html[0]['lead_id'],result['lead_id'])
            status,demo=req('/api/research/demo')
            self.assertEqual(status,200)
            self.assertTrue(demo['demo'])
            self.assertIsNone(demo['lead_id'])
            self.assertTrue(demo['result']['questions'])
            with patch('sales_tool.server.enqueue_quickscan') as enqueue:
                status,started=req('/api/research','POST',{'url':'https://andere-firma.de/', 'provider':'rules'})
                self.assertEqual(status,202)
                self.assertTrue(started['id']>rid)
                enqueue.assert_called_once()
            with self.assertRaises(HTTPError) as ex:
                req('/api/research','POST',{'url':'http://127.0.0.1/test'})
            # Unsafe IPs must be rejected by public_url in background; the API only validates syntax.
            self.assertEqual(ex.exception.code,400) # direct IP blocked before enqueue
        finally:
            server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
