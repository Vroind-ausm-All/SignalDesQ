"""v0.8 automated evidence review and manual external search handoff."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sales_tool.decision_finder import research_plan, validate_verification, save_verification
from sales_tool.model import connect, init_db
from sales_tool.server import make_handler
from sales_tool.quickscan import research


class DecisionFinderV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name)/'db.sqlite3'
        with connect(self.db) as c:
            init_db(c)
            c.execute("INSERT INTO leads(company,website,offer,employees) VALUES ('Beispiel Firma','https://beispiel.de','portal',100)")
            self.lead_id=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute('''INSERT INTO decision_contacts(lead_id,full_name,job_title,source_url)
                VALUES (?,?,?,?)''',(self.lead_id,'Anna Muster','IT-Leiterin','https://beispiel.de/team'))
            self.contact_id=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_offer_aware_manual_links(self):
        plan=research_plan('Beispiel GmbH','portal',100)
        self.assertTrue(any('IT-' in r['role'] for r in plan['targets']))
        self.assertTrue(all(x['web_search_url'].startswith('https://www.google.com/search?') for x in plan['targets']))
        self.assertTrue(any('linkedin.com%2Fin' in x['linkedin_search_url'] for x in plan['targets']))
        self.assertNotIn('api.linkedin',str(plan))
        self.assertIn('nicht',plan['note'])

    def test_confirmation_requires_source_and_evidence(self):
        with self.assertRaisesRegex(ValueError,'Beleg'):
            validate_verification({'verification_status':'rolle_bestaetigt', 'decision_role':'entscheidung',
                                   'source_url':'https://beispiel.de/team'})
        with self.assertRaisesRegex(ValueError,'Entscheidungsbefugnis'):
            validate_verification({'verification_status':'ungeprueft','decision_role':'entscheidung'})
        with self.assertRaises(ValueError):
            validate_verification({'verification_status':'quelle_geprueft','source_url':'http://beispiel.de',
                                   'source_excerpt':'Anna Muster IT-Leiterin'})
        with self.assertRaises(ValueError):
            validate_verification({'verification_status':'quelle_geprueft','source_url':'https://u:p@beispiel.de',
                                   'source_excerpt':'Anna Muster IT-Leiterin'})
        d=validate_verification({'verification_status':'rolle_bestaetigt','decision_role':'fachlich',
                 'source_url':'https://beispiel.de/team','source_excerpt':'Anna Muster – IT-Leiterin bei Beispiel Firma'})
        self.assertEqual(d['verification_status'],'rolle_bestaetigt')

    def test_persists_verified_record_without_changing_consent(self):
        with connect(self.db) as c:
            r=save_verification(c,self.contact_id,{'verification_status':'rolle_bestaetigt',
                'decision_role':'fachlich','source_url':'https://beispiel.de/team',
                'source_excerpt':'Anna Muster leitet das IT-Team','note':'Aktuelle Rolle manuell geprüft'})
            c.commit()
            item=c.execute('SELECT * FROM decision_contacts WHERE id=?',(self.contact_id,)).fetchone()
            self.assertEqual(item['verification_status'],'rolle_bestaetigt')
            self.assertEqual(item['decision_role'],'fachlich')
            self.assertEqual(item['source_excerpt'],'Anna Muster leitet das IT-Team')
            self.assertTrue(item['verification_date'])
            self.assertEqual(c.execute('SELECT permission FROM leads WHERE id=?',(self.lead_id,)).fetchone()[0],'unbekannt')

    def test_migration_idempotent_and_legacy_untouched(self):
        with connect(self.db) as c:
            init_db(c)
            init_db(c)
            self.assertIn('verification_status',{r[1] for r in c.execute('PRAGMA table_info(decision_contacts)')})
            self.assertEqual(c.execute('SELECT COUNT(*) FROM decision_contacts').fetchone()[0],1)

    def test_blocked_lead_cannot_be_enriched(self):
        with connect(self.db) as c:
            c.execute("UPDATE leads SET permission='nicht_kontaktieren',stage='gesperrt' WHERE id=?",(self.lead_id,))
            with self.assertRaisesRegex(ValueError,'gesperrt'):
                save_verification(c,self.contact_id,{'verification_status':'ungeprueft'})

    def test_single_url_result_has_research_plan(self):
        crawl={'source':'https://beispiel.de/', 'pages':[{'url':'https://beispiel.de/',
               'title':'Beispiel GmbH | Kontakt','text':'Kontaktieren Sie uns über unser Kontaktformular.','raw_text':'Kontaktformular',
               'form_count':1}], 'warnings':[]}
        report=research(crawl)
        self.assertTrue(report['decision_makers']['research_plan']['targets'])

    def test_api_get_plan_and_patch_contact(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.db))
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        def req(path,method='GET',body=None):
            b=json.dumps(body).encode() if body is not None else None
            headers={'Content-Type':'application/json'} if b else {}
            with urlopen(Request(base+path,data=b,method=method,headers=headers),timeout=5) as resp:
                return resp.status,json.load(resp)
        try:
            _,leads=req(f'/api/leads/{self.lead_id}/contacts')
            self.assertIn('research_plan',leads)
            self.assertEqual(leads['contacts'][0]['verification_status'],'ungeprueft')
            with self.assertRaises(HTTPError) as err:
                req(f'/api/contacts/{self.contact_id}','PATCH',{'verification_status':'rolle_bestaetigt',
                                    'decision_role':'entscheidung'})
            self.assertEqual(err.exception.code,400)
            code,result=req(f'/api/contacts/{self.contact_id}','PATCH',{
               'verification_status':'quelle_geprueft','decision_role':'unbekannt',
               'source_url':'https://beispiel.de/team', 'source_excerpt':'Anna Muster ist IT-Leiterin.'})
            self.assertEqual(code,200)
            self.assertEqual(result['verification_status'],'quelle_geprueft')
            _,new=req(f'/api/leads/{self.lead_id}/contacts')
            self.assertEqual(new['contacts'][0]['verification_status'],'quelle_geprueft')
        finally:
            server.shutdown();server.server_close();thread.join(timeout=3)

if __name__=='__main__':unittest.main()
