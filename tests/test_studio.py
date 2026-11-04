"""Integration tests for v0.4 website-based KI Studio and sales follow-up workflow."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from sales_tool.ai_lab import demo_analysis, lead_brief, ollama_health
from sales_tool.model import connect, init_db, stats
from sales_tool.server import make_handler

TEST_TEXT = ('Fiktive Maschinenbau GmbH stellt Komponenten für die Industrie her. '
             'Die technische Produktübersicht steht als PDF bereit. '
             'Interessierte können über das Kontaktformular weitere Informationen anfragen. '
             'Die Bearbeitung von Projektanfragen geschieht aktuell zentral über das Vertriebsteam.')


class PreviewTests(unittest.TestCase):
    def test_rules_demo_does_not_touch_database(self):
        result = demo_analysis({'text': TEST_TEXT, 'provider':'rules'})
        self.assertEqual(result['saved'], False)
        self.assertEqual(result['mode'], 'preview_only')
        self.assertEqual(result['findings'][0]['source_url'],'urn:signaldesk:manual-input')
        self.assertIn('Regelmodus', result['summary'])

    def test_rejects_short_text_and_unknown_parameters(self):
        for body in ({'text':'kurz','provider':'rules'},
                     {'text':TEST_TEXT,'provider':'unknown'},
                     {'text':TEST_TEXT,'provider':'rules','secret':'key'}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                demo_analysis(body)

    def test_ollama_health_offline_is_not_false_success(self):
        with patch('sales_tool.ai_lab.urlopen',side_effect=OSError('refused')):
            result=ollama_health()
            self.assertFalse(result['online'])
            self.assertEqual(result['models'],[])


class StudioHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Path(self.temp.name)/'studio.sqlite3'
        with connect(self.db) as con:
            init_db(con)
        self.server=ThreadingHTTPServer(('127.0.0.1', 0),make_handler(self.db))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2); self.temp.cleanup()

    def call(self,method,path,body=None,origin=None):
        data=json.dumps(body).encode() if body is not None else None
        headers={'Content-Type':'application/json'} if data is not None else {}
        if origin:headers['Origin']=origin
        req=Request(f'http://127.0.0.1:{self.server.server_port}{path}',data=data,method=method,headers=headers)
        try:
            with urlopen(req, timeout=5) as response:
                return response.status, json.load(response)
        except HTTPError as e:
            return e.code,json.load(e)

    def test_preview_api_and_archive_are_separate(self):
        status,result=self.call('POST','/api/ai/preview',{'text':TEST_TEXT,'provider':'rules'})
        self.assertEqual(status,200)
        self.assertFalse(result['saved'])
        _,archive=self.call('GET','/api/analyses')
        self.assertEqual(archive,[])
        with connect(self.db) as con:
            self.assertEqual(con.execute('select count(*) from leads').fetchone()[0],0)
            self.assertEqual(con.execute('select count(*) from analysis_runs').fetchone()[0],0)

    def test_manual_briefing_and_reviewed_findings(self):
        status,lead=self.call('POST','/api/leads',{'company':'Kundenfirma','website':'https://example.org/',
            'next_step':'Intro über gemeinsame Bekannte','permission':'unbekannt'})
        self.assertEqual(status,201)
        lid=lead['id']
        with connect(self.db) as con:
            con.execute('INSERT INTO discovery(lead_id,problem,desired_outcome) VALUES (?,?,?)',
                        (lid,'Der Kunde bestätigt Verzögerungen','Bessere Bearbeitung'))
            cur=con.execute('INSERT INTO analysis_runs(lead_id,status,summary) VALUES (?,?,?)',
                            (lid,'done','Recherche durchgeführt'))
            rid=cur.lastrowid
            con.execute('''INSERT INTO findings(run_id,lead_id,category,observation,hypothesis,evidence,
              source_url,offer,question,review_status) VALUES (?,?,?,?,?,?,?,?,?,?)''',
              (rid,lid,'webentwicklung','Kontaktformular sichtbar','Besserer Prozess denkbar',
               'Fragen Sie uns über das Kontaktformular','https://example.org/','conversion',
               'Wie funktioniert Ihr Anfrageprozess?','ungeprueft'))
            con.commit()
        status,brief=self.call('GET',f'/api/leads/{lid}/brief')
        self.assertEqual(status,200)
        self.assertIn('Der Kunde bestätigt Verzögerungen',brief['markdown'])
        self.assertNotIn('Besserer Prozess denkbar',brief['markdown'])
        status,runs=self.call('GET','/api/analyses')
        self.assertEqual(status,200)
        self.assertEqual(runs[0]['company'],'Kundenfirma')
        self.assertEqual(len(runs[0]['findings']),1)
        fid=runs[0]['findings'][0]['id']
        self.call('PATCH',f'/api/findings/{fid}',{'review_status':'freigegeben'})
        _,brief=self.call('GET',f'/api/leads/{lid}/brief')
        self.assertIn('Besserer Prozess denkbar',brief['markdown'])
        self.assertIn('kein bestätigter Bedarf',brief['markdown'])

    def test_lead_next_step_increases_due_count(self):
        with connect(self.db) as con:
            con.execute('''INSERT INTO leads(company,next_step,next_date) VALUES (?,?,?)''',
                        ('Erstkunde GmbH','Bedarf klären','2020-01-01'))
            self.assertEqual(stats(con)['tasks_due'],1)
            con.execute("UPDATE leads SET stage='gesperrt' WHERE company='Erstkunde GmbH'")
            self.assertEqual(stats(con)['tasks_due'],0)

    def test_invalid_preview_and_cross_origin_rejected(self):
        code,error=self.call('POST','/api/ai/preview',{'text':'Zu kurz','provider':'rules'})
        self.assertEqual(code,400)
        self.assertIn('80',error['error'])
        code,_=self.call('POST','/api/ai/preview',{'text':TEST_TEXT,'provider':'rules'},origin='http://evil.example')
        self.assertEqual(code,403)
        code,_=self.call('GET','/api/leads/9999/brief')
        self.assertEqual(code,404)

if __name__=='__main__': unittest.main()
