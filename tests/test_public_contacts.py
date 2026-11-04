"""Self-owned source-based contact research tests, without any internet or paid API."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from unittest.mock import patch
from sales_tool.model import connect,init_db
from sales_tool.server import make_handler
from sales_tool.public_contacts import extract_public_contacts,run_job
from sales_tool.website_analyzer import derive_links

PAGES={'source':'https://demo.example/','pages':[
  {'url':'https://demo.example/team', 'title':'Team',
   'raw_text':'Geschäftsführerin: Anna Mustermann\nMarketing Leitung\nPeter Schmidt\nZentrale: +49 711 3334440\ninfo@demo.example\nIT-Leitung: Carla Meyer\nDirekt: +49 711 333444 22'},
  {'url':'https://demo.example/kontakt','title':'Kontakt','raw_text':'Kontakt\nTel: +49 711 3334440\nE-Mail: info@demo.example'}
 ],'warnings':[]}

class PublicRulesTests(unittest.TestCase):
 def test_role_matches_and_office_phone_not_misattributed(self):
  r=extract_public_contacts(PAGES,offer='conversion')
  self.assertEqual([x['full_name'] for x in r['people']],['Peter Schmidt','Anna Mustermann','Carla Meyer'])
  self.assertTrue(all(not x['business_phone'] for x in r['people']))
  self.assertTrue(any(c['value']=='info@demo.example' for c in r['channels']))
  self.assertEqual(len([c for c in r['channels'] if c['type']=='email']),1)
 def test_explicit_person_line_direct_is_preserved(self):
  r=extract_public_contacts({'pages':[{'url':'https://demo.example/team',
    'raw_text':'Geschäftsführer: Max Muster, Direktwahl +49 711 333444 20'}]})
  self.assertEqual(len(r['people']),1)
  self.assertIn('20',r['people'][0]['business_phone'])
 def test_no_person_without_name_and_role(self):
  r=extract_public_contacts({'pages':[{'url':'https://demo.example/',
     'raw_text':'Marketing und Software!\nWählen Sie +49 711 3334440\ninfo@demo.example'}]})
  self.assertEqual(r['people'],[])
 def test_disallows_http_pii_storage(self):
  self.assertEqual(extract_public_contacts({'pages':[{'url':'http://demo.example/team',
       'raw_text':'Geschäftsführer: Max Muster'}]})['people'],[])
 def test_prioritises_team_in_crawler(self):
  links=[{'href':f'https://demo.example/{x}','text':x} for x in ['produkte','leistungen','impressum','team','kontakt']]
  r=derive_links('https://demo.example/',links,'contacts')
  self.assertIn('https://demo.example/team',r)
  self.assertNotIn('https://demo.example/produkte',r)

class PublicHTTPTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'crm.sqlite3'
  with connect(self.db) as db:init_db(db)
  self.http=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.db))
  self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):
  self.http.shutdown();self.http.server_close();self.thread.join(timeout=2);self.tmp.cleanup()
 def request(self,method,url,payload=None):
  data=json.dumps(payload).encode() if payload is not None else None
  req=Request(f'http://127.0.0.1:{self.http.server_port}{url}',data=data,method=method,headers={'Content-Type':'application/json'} if data else {})
  try:
   with urlopen(req,timeout=4) as r:return r.status,json.load(r)
  except HTTPError as e:return e.code,json.load(e)
 def create(self):
  status,lead=self.request('POST','/api/leads',{'company':'Demo AG','website':'https://demo.example','offer':'conversion'})
  self.assertEqual(status,201);return lead['id']
 def test_public_research_review_and_legacy_paid_api_disabled(self):
  lid=self.create()
  with patch('sales_tool.public_contacts.enqueue',return_value=None):
   # The server imported enqueue as alias; patch that call site.
   with patch('sales_tool.server.enqueue_contact_research') as enq:
    status,result=self.request('POST',f'/api/leads/{lid}/contact-research',{'confirm_public_research':True})
    self.assertEqual(status,202);enq.assert_called_once()
  with patch('sales_tool.public_contacts.crawl_site',return_value=PAGES):
   run_job(self.db,result['id'],lid,'https://demo.example','conversion')
  status,runs=self.request('GET',f'/api/leads/{lid}/contact-research')
  self.assertEqual(status,200);self.assertEqual(runs[0]['status'],'done')
  self.assertEqual(len(runs[0]['people']),3)
  cid=runs[0]['people'][0]['id']
  status,result=self.request('POST',f'/api/contact-candidates/{cid}/review',{'decision':'accept'})
  self.assertEqual(status,200)
  status,contacts=self.request('GET',f'/api/leads/{lid}/contacts')
  self.assertEqual(status,200);self.assertEqual(len(contacts['contacts']),1)
  self.assertEqual(contacts['contacts'][0]['data_provider'],'eigene_recherche')
  self.assertEqual(contacts['contacts'][0]['business_phone'],'')
  contact_id=contacts['contacts'][0]['id']
  status,result=self.request('POST',f'/api/contacts/{contact_id}/preview',{'confirm_search':True})
  self.assertEqual(status,410)
  status,result=self.request('POST',f'/api/contact-candidates/{cid}/review',{'decision':'accept'})
  self.assertEqual(status,400)
 def test_no_scan_without_website_confirmation_or_when_blocked(self):
  lid=self.create()
  code,_=self.request('POST',f'/api/leads/{lid}/contact-research',{})
  self.assertEqual(code,400)
  self.request('PATCH',f'/api/leads/{lid}',{'permission':'nicht_kontaktieren'})
  code,_=self.request('POST',f'/api/leads/{lid}/contact-research',{'confirm_public_research':True})
  self.assertEqual(code,403)
 def test_review_does_not_auto_contact(self):
  lid=self.create()
  with connect(self.db) as db:
   run=db.execute('INSERT INTO contact_research_runs(lead_id,status) VALUES (?,?)',(lid,'done')).lastrowid
   cand=db.execute('INSERT INTO contact_candidates (run_id,lead_id,full_name,job_title,source_url) VALUES (?,?,?,?,?)',
     (run,lid,'Anna Muster','Marketing','https://demo.example/team')).lastrowid
   db.commit()
  code,_=self.request('POST',f'/api/contact-candidates/{cand}/review',{'decision':'reject'})
  self.assertEqual(code,200)
  with connect(self.db) as db:
   self.assertEqual(db.execute('SELECT count(*) FROM decision_contacts WHERE lead_id=?',(lid,)).fetchone()[0],0)
