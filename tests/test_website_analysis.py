import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sales_tool.ai_provider import validate_analysis, rules_analysis, AnalysisError
from sales_tool.model import connect, init_db
from sales_tool.server import make_handler
from sales_tool.website_analyzer import public_url, derive_links, CrawlError

CRAWL = {'source':'https://example.org/', 'pages':[{ 'url':'https://example.org/',
         'title':'B2B Produkte','text':'Wir entwickeln technische Produkte für Unternehmen und bieten eine Produktübersicht an.',
         'headings':['Technische Produkte'], 'form_count':0}], 'warnings':[]}
ANALYSIS = {'summary':'Sichtbare Inhalte, Kundenbedarf noch unbestätigt.', 'findings':[{
  'source_url':'https://example.org/', 'evidence':'technische Produkte für Unternehmen',
  'observation':'Die Website beschreibt technische Produkte.',
  'hypothesis':'Vielleicht lässt sich die Produktpräsentation verbessern.',
  'category':'webentwicklung','offer':'conversion',
  'question':'Wie stellen Sie heute den Nutzen Ihrer Produkte dar?'
}]}

class SourceEvidenceTests(unittest.TestCase):
    def test_accepts_literal_cited_evidence_and_discards_inventions(self):
        fake=json.loads(json.dumps(ANALYSIS))
        fake['findings'].append({**fake['findings'][0], 'evidence':'Erfundener Text aus einer anderen Seite'})
        fake['findings'].append({**fake['findings'][0], 'source_url':'https://other.example/'})
        result=validate_analysis(fake,CRAWL)
        self.assertEqual(len(result['findings']),1)
        self.assertEqual(result['discarded'],2)

    def test_wrong_shape_throws(self):
        with self.assertRaises(AnalysisError):
            validate_analysis({'findings':'falscher Typ'},CRAWL)

    def test_rule_mode_is_clearly_labeled(self):
        result=rules_analysis(CRAWL)
        self.assertIn('Regelmodus ohne KI', result['summary'])
        self.assertEqual(len(result['findings']),1)

class PublicUrlTests(unittest.TestCase):
    def test_blocks_private_hosts(self):
        for url in ['http://localhost/', 'http://127.0.0.1/', 'http://192.168.0.2/',
                    'http://[::1]/', 'http://printer.local/', 'file:///etc/passwd',
                    'https://example.org:8080/','https://user:pass@example.org/']:
            with self.subTest(url=url), self.assertRaises(CrawlError):
                public_url(url)

    def test_rejects_public_named_domain_resolving_to_private_address(self):
        with patch('sales_tool.website_analyzer.socket.getaddrinfo', return_value=[
            (socket.AF_INET, socket.SOCK_STREAM,6,'', ('10.10.0.1',443))]):
            with self.assertRaises(CrawlError):
                public_url('https://example.org/')

    def test_allows_public_dns_and_only_finds_same_host_links(self):
        with patch('sales_tool.website_analyzer.socket.getaddrinfo', return_value=[
            (socket.AF_INET, socket.SOCK_STREAM,6,'', ('93.184.215.14',443))]):
            self.assertEqual(public_url('https://example.org'), 'https://example.org/')
        found=derive_links('https://example.org/',[
            {'href':'/kontakt','text':'Kontakt'},
            {'href':'https://other.test/produkte','text':'Produkte'},
            {'href':'/leistungen','text':'Leistungen'},
        ])
        self.assertEqual(found,['https://example.org/leistungen','https://example.org/kontakt'])

class AnalysisHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Path(self.temp.name)/'test.sqlite3'
        with connect(self.db) as conn:
            init_db(conn)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.db))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
        self.temp.cleanup()

    def call(self, method,path,body=None):
        data=None if body is None else json.dumps(body).encode()
        r=Request('http://127.0.0.1:'+str(self.server.server_port)+path, data=data,
                 headers={'Content-Type':'application/json'} if data is not None else {}, method=method)
        try:
            with urlopen(r,timeout=5) as resp:
                return resp.status,json.load(resp)
        except HTTPError as exc:
            return exc.code,json.load(exc)

    def test_analysis_review_and_promotion_do_not_overwrite_existing_signal(self):
        status,lead=self.call('POST','/api/leads',{'company':'Fiktive GmbH','website':'https://example.org/'})
        self.assertEqual(status,201)
        ident=lead['id']
        with patch('sales_tool.analysis_jobs.crawl_site',return_value=CRAWL), \
             patch('sales_tool.analysis_jobs.analyze',return_value=validate_analysis(ANALYSIS,CRAWL)):
            status,result=self.call('POST',f'/api/leads/{ident}/analysis',{'provider':'rules','model':'qwen3:8b'})
            self.assertEqual(status,202)
            run_id=result['id']
            for _ in range(50):
                _,runs=self.call('GET',f'/api/leads/{ident}/analysis')
                if runs[0]['status']=='done':break
                time.sleep(.05)
            self.assertEqual(runs[0]['status'],'done')
            self.assertEqual(len(runs[0]['findings']),1)
            fid=runs[0]['findings'][0]['id']
            status,_=self.call('POST',f'/api/findings/{fid}/promote',{})
            self.assertEqual(status,409)
            status,_=self.call('PATCH',f'/api/findings/{fid}',{'review_status':'freigegeben'})
            self.assertEqual(status,200)
            status,result=self.call('POST',f'/api/findings/{fid}/promote',{})
            self.assertEqual(status,200)
            self.assertIn('technische Produkte',result['lead']['signal_note'])
            status,_=self.call('POST',f'/api/findings/{fid}/promote',{})
            self.assertEqual(status,409)
            with connect(self.db) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM findings').fetchone()[0],1)
            status,_=self.call('DELETE',f'/api/leads/{ident}')
            self.assertEqual(status,200)
            with connect(self.db) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM analysis_runs').fetchone()[0],0)
                self.assertEqual(conn.execute('SELECT count(*) FROM findings').fetchone()[0],0)

    def test_invalid_provider_and_missing_website(self):
        _,lead=self.call('POST','/api/leads',{'company':'Ohne URL'})
        status,_=self.call('POST',f'/api/leads/{lead["id"]}/analysis',{'provider':'ollama'})
        self.assertEqual(status,400)
        _,lead2=self.call('POST','/api/leads',{'company':'Mit URL','website':'https://example.org/'})
        status,_=self.call('POST',f'/api/leads/{lead2["id"]}/analysis',{'provider':'other'})
        self.assertEqual(status,400)

    def test_job_failure_is_visible_to_user(self):
        _,lead=self.call('POST','/api/leads',{'company':'Test','website':'https://example.org/'})
        with patch('sales_tool.analysis_jobs.crawl_site',side_effect=CrawlError('robots.txt sperrt den Abruf')):
            status,_=self.call('POST',f'/api/leads/{lead["id"]}/analysis',{'provider':'rules'})
            self.assertEqual(status,202)
            for _ in range(50):
                _,runs=self.call('GET',f'/api/leads/{lead["id"]}/analysis')
                if runs[0]['status']=='failed':break
                time.sleep(.05)
            self.assertEqual(runs[0]['status'],'failed')
            self.assertIn('robots.txt',runs[0]['error'])

if __name__ == '__main__':unittest.main()
