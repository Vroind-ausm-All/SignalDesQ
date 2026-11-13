"""Tests for the offline CRM sales workspace and productized proposals."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
from s5_helpers import confirm_need  # noqa: E402
from sales_tool.model import connect, init_db
from sales_tool.server import make_handler
from sales_tool.sales_workspace import quote_preview, customer_markdown, daily_view, create_call, create_mail_draft

import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from tmpclean import cleanup_tmp  # noqa: E402 – Worker beenden, dann löschen (Windows)


class PricingUnitTests(unittest.TestCase):
    """2.0.0-dev16 (Produktreview M12): Aufrufe mit Paket und Zusatzleistungen rechnen über den zentralen Katalog."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.conn = connect(Path(self.tmp.name) / 'p.sqlite3')
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def test_package_scope_and_addons_are_explicit(self):
        p=quote_preview(self.conn,{'package':'conversion','addons':['copy','analytics'],'tax_mode':'regel_19'})
        c=p['customer']
        self.assertEqual([x['service'] for x in c['positions']],['webdesign','texte','seo_geo','texte','aufwand'])
        self.assertEqual(c['positions'][4]['title'],'Messkonzept & Dashboard')
        self.assertTrue(any('Garantie' in v for v in c['excluded']))
        self.assertNotIn('Texte (separate Position)',c['excluded'],'Texte stehen als eigene Position im Angebot – kein Widerspruch')
        self.assertIn('Fotografie (separate Position)',c['excluded'])
        self.assertEqual(round(c['net_eur']*1.19,2),c['total_eur'])
        self.assertEqual(p['internal']['mode'],'baukasten')

    def test_customer_export_contains_no_internal_rate_or_hours(self):
        p=quote_preview(self.conn,{'package':'portal','addons':['integration'],'tax_mode':'regel_19'})
        md=customer_markdown(p['customer'])
        self.assertIn('Festpreis',md)
        self.assertIn('Nicht enthalten',md)
        self.assertIn('Eine Schnittstellen-Integration',md)
        for secret in ('Stundensatz','Kalkulation','estimated_hours','€/h','catalog_version'):
            self.assertNotIn(secret,md)

    def test_monthly_care_offer_is_explicit_recurring(self):
        p=quote_preview(self.conn,{'package':'care','tax_mode':'regel_19'})
        self.assertEqual(p['customer']['billing'],'monatlich')
        self.assertIn('pro Monat',customer_markdown(p['customer']))
        self.assertIn('Kündigungsfrist',customer_markdown(p['customer']))

    def test_unknown_tax_mode_marks_draft_as_incomplete(self):
        p=quote_preview(self.conn,{'package':'pilot','tax_mode':'offen'})
        self.assertIn('offen',customer_markdown(p['customer']))
        self.assertNotIn('Gesamtbetrag:',customer_markdown(p['customer']))

    def test_impossible_price_and_malicious_fields_rejected(self):
        for data in (
            {'package':'pilot','custom_price_eur':100},
            {'package':'pilot','addons':['foo']},
            {'package':'brand','addons':['seo','seo']},
            {'package':'brand','tax_mode':'unknown'},
            {'package':'brand','margin_pct':100},
            {'package':'pilot','cost_rate_eur':float('nan')},
            {'package':'raumfahrt'},
        ):
            with self.subTest(data=data),self.assertRaises(ValueError): quote_preview(self.conn,data)
        with self.assertRaisesRegex(ValueError,'zentralen Leistungskatalog'):
            quote_preview(self.conn,{'package':'pilot','target_margin_pct':35})


class WorkspaceApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'leads.sqlite3'
        with connect(self.path) as con: init_db(con)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.path))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2);cleanup_tmp(self.tmp)

    def call(self,method,path,body=None):
        data=json.dumps(body).encode() if body is not None else None
        req=Request('http://127.0.0.1:'+str(self.server.server_port)+path,method=method,data=data,
                    headers={'Content-Type':'application/json'} if data is not None else {})
        try:
            with urlopen(req,timeout=5) as resp:
                return resp.status,json.load(resp)
        except HTTPError as ex:
            return ex.code,json.load(ex)

    def lead(self,permission='unbekannt'):
        return self.call('POST','/api/leads',{'company':'Beispieltechnik GmbH','permission':permission})[1]['id']

    def test_new_static_and_catalog(self):
        req=Request('http://127.0.0.1:'+str(self.server.server_port)+'/workspace.js')
        with urlopen(req,timeout=5) as resp:
            self.assertEqual(resp.status,200)
            self.assertIn(b'wsInit',resp.read())
        code,catalog=self.call('GET','/api/workspace/catalog')
        self.assertEqual(code,200)
        self.assertIn('portal',catalog['packages'])

    def test_full_quote_and_public_export_hides_internal(self):
        lead_id=self.lead()
        payload={'lead_id':lead_id,'package':'brand','addons':['training'],
                 'tax_mode':'regel_19','customer_goal':'Mehr Wiedererkennung'}
        code,offer=self.call('POST','/api/workspace/proposals',payload)
        self.assertEqual(code,201)
        self.assertIn('internal',offer)
        code,cust=self.call('GET','/api/workspace/proposals/'+str(offer['id'])+'/customer')
        self.assertEqual(code,200)
        self.assertNotIn('internal',cust)
        self.assertNotIn('cost_rate_eur',cust['markdown'])
        self.assertIn('Mehr Wiedererkennung',cust['markdown'])
        code,err=self.call('PATCH','/api/workspace/proposals/'+str(offer['id']),{'status':'gesendet_manuell'})
        self.assertEqual(code,409)  # v1.18: erst nach bestätigtem Bedarf
        self.assertIn('Bedarf',err['error'])
        confirm_need(self.path,lead_id)
        code,status=self.call('PATCH','/api/workspace/proposals/'+str(offer['id']),{'status':'gesendet_manuell'})
        self.assertEqual(code,200)
        code,history=self.call('GET','/api/workspace/proposals')
        self.assertEqual(history[0]['status'],'gesendet_manuell')

    def test_quote_sent_creates_review_task_only_once(self):
        lid=self.lead()
        _,offer=self.call('POST','/api/workspace/proposals',{'lead_id':lid,'package':'pilot','tax_mode':'regel_19'})
        ident=str(offer['id'])
        confirm_need(self.path,lid)
        self.call('PATCH','/api/workspace/proposals/'+ident,{'status':'gesendet_manuell'})
        self.call('PATCH','/api/workspace/proposals/'+ident,{'status':'gesendet_manuell'})
        _,view=self.call('GET','/api/workspace')
        self.assertEqual(len([t for t in view['tasks'] if ident in t['title']]),1)
        self.assertTrue(any('zulässige' in t['title'] for t in view['tasks']))

    def test_incomplete_quote_cannot_be_marked_sent(self):
        lid=self.lead()
        _,offer=self.call('POST','/api/workspace/proposals',{'lead_id':lid,'package':'pilot'})
        code,error=self.call('PATCH','/api/workspace/proposals/'+str(offer['id']),{'status':'gesendet_manuell'})
        self.assertEqual(code,400)
        self.assertIn('Steuerstatus',error['error'])

    def test_meeting_and_ics_data(self):
        lid=self.lead()
        code,created=self.call('POST','/api/workspace/meetings',{'lead_id':lid,'title':'Discovery','starts_at':'2026-11-03T10:30','duration_min':45})
        self.assertEqual(code,201)
        _,view=self.call('GET','/api/workspace')
        self.assertEqual(view['meetings'][0]['title'],'Discovery')
        code,updated=self.call('PATCH','/api/workspace/meetings/'+str(created['id']),{'status':'bestaetigt'})
        self.assertEqual(code,200)
        code,rows=self.call('GET','/api/workspace/meetings')
        self.assertEqual(rows[0]['status'],'bestaetigt')

    def test_completed_meeting_creates_internal_followup_once(self):
        lid=self.lead()
        _,meeting=self.call('POST','/api/workspace/meetings',{'lead_id':lid,'title':'Bedarfsanalyse','starts_at':'2026-11-03T10:30'})
        ident=str(meeting['id'])
        self.call('PATCH','/api/workspace/meetings/'+ident,{'status':'erledigt'})
        self.call('PATCH','/api/workspace/meetings/'+ident,{'status':'erledigt'})
        _,view=self.call('GET','/api/workspace')
        titles=[t['title'] for t in view['tasks']]
        self.assertEqual(len([t for t in titles if t.startswith('Gespräch dokumentieren')]),1)
        # v1.18: Folgeaufgaben je einmal – Termin vorbereiten, danach Bedarf bestätigen
        self.assertEqual(len([t for t in titles if 'vorbereiten' in t]),1)
        self.assertEqual(len([t for t in titles if t.startswith('Bedarf aus dem Termin')]),1)

    def test_callback_requires_agreement_and_creates_task(self):
        lid=self.lead()
        code,_=self.call('POST','/api/workspace/calls',{'lead_id':lid,'outcome':'rueckruf_vereinbart','notes':'Bitte zurückrufen'})
        self.assertEqual(code,400)
        code,_=self.call('POST','/api/workspace/calls',{'lead_id':lid,'outcome':'rueckruf_vereinbart','notes':'Rückruf für ein Projekt gewünscht','callback_date':'2026-11-02'})
        self.assertEqual(code,201)
        _,view=self.call('GET','/api/workspace')
        self.assertEqual(len(view['tasks']),1)
        self.assertIn('Rückruf',view['tasks'][0]['title'])

    def test_optout_blocks_drafts_and_removes_contact_tasks_from_agenda(self):
        lid=self.lead()
        self.call('POST','/api/tasks',{'lead_id':lid,'title':'Kontaktieren','due_date':'2026-10-19'})
        code,_=self.call('POST','/api/workspace/calls',{'lead_id':lid,'outcome':'widerspruch','notes':'Keine Kontakte mehr gewünscht'})
        self.assertEqual(code,201)
        _,lead=self.call('GET','/api/leads/'+str(lid))
        self.assertEqual(lead['permission'],'nicht_kontaktieren')
        _,v=self.call('GET','/api/workspace')
        self.assertEqual(v['tasks'],[])
        code,_=self.call('POST','/api/workspace/mail-drafts',{'lead_id':lid,'draft_type':'nach_gespraech','contact_basis':'gesprochen'})
        self.assertEqual(code,409)  # v1.18: Kontaktsperre

    def test_mail_draft_never_sends(self):
        lid=self.lead()
        code,mail=self.call('POST','/api/workspace/mail-drafts',{'lead_id':lid,'draft_type':'nach_gespraech','contact_basis':'Kunde bittet um Zusammenfassung'})
        self.assertEqual(code,201)
        self.assertIn('nicht versendet',mail['notice'])
        _,drafts=self.call('GET','/api/workspace/mail-drafts')
        self.assertEqual(len(drafts),1)

    def test_invalid_meeting_and_unknown_lead(self):
        lid=self.lead()
        code,_=self.call('POST','/api/workspace/meetings',{'lead_id':lid,'title':'Falsch','starts_at':'morgen'})
        self.assertEqual(code,400)
        code,_=self.call('POST','/api/workspace/proposals',{'lead_id':999,'package':'pilot'})
        self.assertEqual(code,400)

    def test_migration_idempotent(self):
        with connect(self.path) as con:
            init_db(con);init_db(con)
            names={r[0] for r in con.execute('SELECT name FROM sqlite_master WHERE type="table"')}
            self.assertTrue({'calls','meetings','proposals','mail_drafts'}.issubset(names))


if __name__=='__main__': unittest.main()
