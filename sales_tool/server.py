"""Minimal dependency-free local HTTP+JSON server. Not a public multi-user deployment."""
from __future__ import annotations

import argparse
import json
import ipaddress
import os
import re
import sqlite3
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .analysis_jobs import enqueue, list_analyses
from .quickscan import enqueue as enqueue_quickscan, list_scans, scan_row, import_scan, demo_report
from .contacts import validate_contact, role_suggestions
from .decision_finder import research_plan, save_verification
from .public_contacts import enqueue as enqueue_contact_research, list_runs as list_contact_research, review_candidate
from .ai_lab import ollama_health, demo_analysis, lead_brief
from .sales_workspace import (
    PACKAGES, ADDONS, CALL_OUTCOMES, MEETING_STATUSES, QUOTE_STATUSES, DRAFT_TYPES,
    daily_view, call_permission, create_call, create_meeting, quote_preview,
    make_proposal, proposal_rows, proposal_detail, customer_markdown, create_mail_draft,
)
from .model import STAGES, INDUSTRIES, SIGNALS, OFFERS, PERMISSIONS, CONTACT_ROUTES, as_lead, connect, init_db, stats, discovery_summary

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
FIELDS = ("company", "website", "location", "contact_name", "contact_role", "contact_route", "industry", "employees", "signal_type", "signal_date", "signal_source",
          "signal_note", "offer", "estimated_budget", "stage", "permission", "permission_evidence", "note", "next_step", "next_date")
INT_FIELDS = {"employees", "estimated_budget"}
DATE_FIELDS = {"signal_date", "next_date"}
ENUMS = {"stage": STAGES, "industry": INDUSTRIES, "signal_type": tuple(SIGNALS), "offer": tuple(OFFERS), "permission": PERMISSIONS, "contact_route": CONTACT_ROUTES}
URL_FIELDS = {"website", "signal_source"}
TEXT_LIMITS = {"company": 200, "location": 160, "contact_role": 120, "contact_name": 160, "permission_evidence": 500, "signal_note": 2000, "note": 4000, "next_step": 500}


DISCOVERY_FIELDS = ("problem", "impact", "current_solution", "desired_outcome", "timing",
                    "decision_process", "budget_status", "budget_note")
BUDGET_STATUSES = ("offen", "budget_vorhanden", "freigabe_offen", "kein_budget")
IMPORT_FIELDS = ("company", "website", "location", "industry", "employees", "signal_type", "signal_date",
                 "signal_source", "signal_note", "offer", "contact_name", "contact_role", "contact_route", "permission",
                 "permission_evidence", "next_step", "next_date")


def validate_discovery(fields):
    if not isinstance(fields, dict) or set(fields) - set(DISCOVERY_FIELDS):
        raise ValueError("Ungültige Bedarfsanalyse-Felder.")
    out = {}
    for key, value in fields.items():
        if not isinstance(value, str):
            raise ValueError(f"{key} muss Text sein.")
        value = value.strip()
        if len(value) > 2000:
            raise ValueError(f"{key} ist zu lang.")
        if key == "budget_status" and value not in BUDGET_STATUSES:
            raise ValueError("Ungültiger Budgetstatus.")
        out[key] = value
    return out


def import_leads(conn, payload):
    if not isinstance(payload, dict) or set(payload) != {"rows"} or not isinstance(payload["rows"], list):
        raise ValueError("Erwartet: {'rows': [...]}.")
    rows = payload["rows"]
    if not rows or len(rows) > 50:
        raise ValueError("Bitte 1 bis 50 Zeilen gleichzeitig importieren.")
    results = {"imported": 0, "duplicates": 0, "errors": []}
    known = set()
    for r in conn.execute("SELECT company,website FROM leads"):
        known.add((r["company"] or "").strip().casefold())
        if r["website"]:
            known.add(r["website"].lower().rstrip('/'))
    for index, raw in enumerate(rows, 2):
        try:
            if not isinstance(raw, dict) or set(raw) - set(IMPORT_FIELDS):
                raise ValueError("Ungültige Spalten. Vorlage verwenden.")
            d = validate({k: v for k, v in raw.items() if v is not None and str(v).strip()})
            d.setdefault("permission", "unbekannt")
            d.setdefault("stage", "recherche")
            identity = d["company"].casefold()
            url_identity = (d.get("website") or "").lower().rstrip('/')
            if identity in known or url_identity and url_identity in known:
                results["duplicates"] += 1
                continue
            cols = ",".join(d)
            vals = ",".join("?" for _ in d)
            conn.execute(f"INSERT INTO leads ({cols}) VALUES ({vals})", tuple(d.values()))
            results["imported"] += 1
            known.add(identity)
            if url_identity:
                known.add(url_identity)
        except (ValueError, KeyError) as exc:
            results["errors"].append(f"Zeile {index}: {exc}")
    return results


def validate(fields: dict, partial=False):
    if not isinstance(fields, dict):
        raise ValueError("Ein JSON-Objekt ist erforderlich.")
    unknown = set(fields) - set(FIELDS)
    if unknown:
        raise ValueError("Unbekannte Felder: " + ", ".join(sorted(unknown)))
    if not partial and not str(fields.get("company", "")).strip():
        raise ValueError("Firmenname fehlt.")
    out = {}
    for key, value in fields.items():
        if key in INT_FIELDS:
            if value in (None, ""):
                value = 0
            if isinstance(value, bool) or not str(value).isdigit():
                raise ValueError(key + " muss eine nichtnegative Ganzzahl sein.")
            value = int(value)
            if value > 100000000:
                raise ValueError(key + " ist zu groß.")
        elif not isinstance(value, str):
            raise ValueError(key + " muss Text sein.")
        else:
            value = value.strip()
            if len(value) > TEXT_LIMITS.get(key, 500):
                raise ValueError(key + " ist zu lang.")
        if key in ENUMS and value not in ENUMS[key]:
            raise ValueError("Ungültiger Wert für " + key)
        if key in DATE_FIELDS and value:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("Datum bitte als JJJJ-MM-TT angeben.") from exc
        if key in URL_FIELDS and value:
            parsed = urlparse(value)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError(key + " muss eine http(s)-URL sein.")
        if key == "company" and not value:
            raise ValueError("Firmenname fehlt.")
        out[key] = value
    return out


def make_handler(db_path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SignalDesk/0.9"

        def _conn(self):
            return connect(db_path)

        def _send(self, status, payload):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def _error(self, msg, status=400):
            self._send(status, {"error": msg})

        def _body(self):
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise ValueError("Nur application/json erlaubt.")
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 65536:
                raise ValueError("Ungültige Anfragegröße.")
            try:
                return json.loads(self.rfile.read(length))
            except json.JSONDecodeError as exc:
                raise ValueError("Ungültiges JSON.") from exc

        def _same_origin(self):
            origin = self.headers.get("Origin")
            if origin:
                expected = f"http://{self.headers.get('Host', '')}"
                if origin != expected:
                    self._error("Anfragen von fremden Webseiten sind gesperrt.", 403)
                    return False
            return True

        def _routes(self, method):
            if method != "GET" and not self._same_origin():
                return
            route = urlparse(self.path).path
            query = parse_qs(urlparse(self.path).query)
            if not route.startswith("/api/"):
                return self._static(route, method)
            if route == "/api/config" and method == "GET":
                return self._send(200, {"stages": STAGES, "industries": INDUSTRIES, "signals": SIGNALS,
                                        "offers": OFFERS, "permissions": PERMISSIONS, "contact_routes": CONTACT_ROUTES, "budget_statuses": BUDGET_STATUSES})
            if route == "/api/ai/health" and method == "GET":
                return self._send(200, ollama_health())
            if route == "/api/ai/preview" and method == "POST":
                return self._send(200, demo_analysis(self._body()))
            if route == '/api/research/demo' and method == 'GET':
                return self._send(200,{'id':0,'status':'done','lead_id':None,'demo':True,'result':demo_report()})
            with self._conn() as conn:
                if route == '/api/workspace/catalog' and method == 'GET':
                    return self._send(200, {'packages':PACKAGES,'addons':ADDONS,'call_outcomes':CALL_OUTCOMES,
                                             'meeting_statuses':MEETING_STATUSES,'quote_statuses':QUOTE_STATUSES,
                                             'draft_types':DRAFT_TYPES})
                if route == '/api/workspace' and method == 'GET':
                    view=daily_view(conn)
                    view['call_permissions']={str(r['id']):call_permission(r) for r in conn.execute('SELECT * FROM leads')}
                    return self._send(200,view)
                if route == '/api/workspace/quote-preview' and method == 'POST':
                    return self._send(200,quote_preview(self._body()))
                if route == '/api/workspace/proposals':
                    if method == 'GET': return self._send(200,proposal_rows(conn))
                    if method == 'POST': return self._send(201,make_proposal(conn,self._body()))
                proposal_match=re.fullmatch(r'/api/workspace/proposals/(\d+)(/customer)?',route)
                if proposal_match:
                    ident=int(proposal_match.group(1))
                    if method=='GET':
                        try: detail=proposal_detail(conn,ident,customer_only=bool(proposal_match.group(2)))
                        except ValueError as exc: return self._error(str(exc),404)
                        if proposal_match.group(2): detail['markdown']=customer_markdown(detail['customer'])
                        return self._send(200,detail)
                    if method=='PATCH' and not proposal_match.group(2):
                        body=self._body()
                        if not isinstance(body,dict) or set(body)!={'status'} or body['status'] not in QUOTE_STATUSES:
                            return self._error('Ungültiger Angebotsstatus.')
                        row=conn.execute('SELECT id FROM proposals WHERE id=?',(ident,)).fetchone()
                        if not row: return self._error('Angebot nicht gefunden.',404)
                        if body['status'] in ('gesendet_manuell','angenommen'):
                            current=proposal_detail(conn,ident,customer_only=True)
                            if current['customer']['tax_mode']=='offen':
                                return self._error('Steuerstatus noch offen: Angebot nicht als gesendet/angenommen markieren.')
                        prev=conn.execute('SELECT status,lead_id FROM proposals WHERE id=?',(ident,)).fetchone()
                        conn.execute("UPDATE proposals SET status=?,updated_at=datetime('now') WHERE id=?",(body['status'],ident))
                        if body['status']=='gesendet_manuell' and prev['status']!='gesendet_manuell':
                            from datetime import timedelta
                            followup=(date.today()+timedelta(days=7)).isoformat()
                            conn.execute('INSERT INTO tasks(lead_id,title,due_date) VALUES (?,?,?)',
                                         (prev['lead_id'],'Angebotsstatus und zulässige Rückfrage prüfen (#'+str(ident)+')',followup))
                        conn.commit()
                        return self._send(200,{'saved':True,'status':body['status'],
                                               'notice':'Der Status wird nur dokumentiert. Keine Nachricht wurde gesendet.'})
                if route == '/api/workspace/calls':
                    if method=='GET':
                        lid=query.get('lead_id',[''])[0]
                        if lid and not lid.isdigit(): return self._error('Ungültige Lead-ID.')
                        sql='SELECT c.*,l.company FROM calls c JOIN leads l ON l.id=c.lead_id'
                        if lid: sql+=' WHERE c.lead_id=?'
                        sql+=' ORDER BY c.id DESC LIMIT 100'
                        return self._send(200,[dict(r) for r in conn.execute(sql,(int(lid),) if lid else ())])
                    if method=='POST': return self._send(201,create_call(conn,self._body()))
                if route == '/api/workspace/meetings':
                    if method=='GET':
                        return self._send(200,[dict(r) for r in conn.execute('SELECT m.*,l.company FROM meetings m JOIN leads l ON l.id=m.lead_id ORDER BY m.starts_at DESC LIMIT 100')])
                    if method=='POST': return self._send(201,create_meeting(conn,self._body()))
                meeting_match=re.fullmatch(r'/api/workspace/meetings/(\d+)',route)
                if meeting_match and method=='PATCH':
                    body=self._body()
                    if not isinstance(body,dict) or set(body)!={'status'} or body['status'] not in MEETING_STATUSES:
                        return self._error('Ungültiger Terminstatus.')
                    meeting=conn.execute('SELECT status,lead_id FROM meetings WHERE id=?',(int(meeting_match.group(1)),)).fetchone()
                    if not meeting: return self._error('Termin nicht gefunden.',404)
                    conn.execute('UPDATE meetings SET status=? WHERE id=?',(body['status'],int(meeting_match.group(1))))
                    if body['status']=='erledigt' and meeting['status']!='erledigt':
                        from datetime import timedelta
                        conn.execute('INSERT INTO tasks(lead_id,title,due_date) VALUES (?,?,?)',
                                     (meeting['lead_id'],'Gespräch dokumentieren und vereinbarten nächsten Schritt prüfen', (date.today()+timedelta(days=1)).isoformat()))
                    conn.commit()
                    return self._send(200,{'saved':True})
                if route == '/api/workspace/mail-drafts':
                    if method=='GET':
                        return self._send(200,[dict(r) for r in conn.execute('SELECT d.*,l.company FROM mail_drafts d JOIN leads l ON l.id=d.lead_id ORDER BY d.id DESC LIMIT 100')])
                    if method=='POST': return self._send(201,create_mail_draft(conn,self._body()))
                if route == "/api/research":
                    if method == 'GET':
                        return self._send(200, list_scans(conn))
                    if method == 'POST':
                        payload = self._body()
                        if not isinstance(payload, dict) or set(payload) - {'url','provider','model'}:
                            return self._error('Ungültige Recherche-Optionen.')
                        url = payload.get('url','')
                        provider = payload.get('provider','rules')
                        model = payload.get('model','qwen3:8b')
                        if not isinstance(url,str) or len(url)>1800:
                            return self._error('Bitte eine gültige Website-URL angeben.')
                        parsed=urlparse(url.strip())
                        if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.port not in (None,80,443):
                            return self._error('Bitte eine öffentliche HTTP(S)-Website ohne Login/Sonderport eingeben.')
                        host=parsed.hostname.rstrip('.').lower()
                        try:
                            ipaddress.ip_address(host)
                            return self._error('Direkte IP-Adressen sind keine erlaubten Analyseziele.')
                        except ValueError:
                            pass
                        if host=='localhost' or host.endswith(('.localhost','.local','.internal','.test','.invalid')) or '.' not in host:
                            return self._error('Bitte einen öffentlichen Firmendomainnamen verwenden.')
                        if provider not in ('rules','ollama') or not isinstance(model,str) or not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,80}', model):
                            return self._error('Ungültiger KI-Modus bzw. Modellname.')
                        if conn.execute("SELECT 1 FROM quick_scans WHERE status IN ('queued','running') LIMIT 1").fetchone():
                            return self._error('Es läuft bereits eine Schnellrecherche.',409)
                        cur=conn.execute('INSERT INTO quick_scans(url,provider,model) VALUES (?,?,?)',
                                         (url.strip(),provider,model))
                        conn.commit()
                        enqueue_quickscan(db_path,cur.lastrowid,url.strip(),provider,model)
                        return self._send(202,{'id':cur.lastrowid,'status':'queued'})
                research_match=re.fullmatch(r'/api/research/(\d+)(/import)?',route)
                if research_match:
                    rid=int(research_match.group(1))
                    row=conn.execute('SELECT * FROM quick_scans WHERE id=?',(rid,)).fetchone()
                    if not row: return self._error('Recherche nicht gefunden.',404)
                    if method=='GET' and not research_match.group(2):
                        return self._send(200,scan_row(row))
                    if method=='POST' and research_match.group(2)=='/import':
                        if self._body()!={'confirm':True}:
                            return self._error('CRM-Übernahme explizit bestätigen.')
                        try:
                            imported=import_scan(conn,rid)
                        except ValueError as exc:
                            return self._error(str(exc),409)
                        conn.commit()
                        return self._send(200,imported)
                if route == "/api/analyses" and method == "GET":
                    records = [dict(r) for r in conn.execute("""SELECT a.id, a.lead_id, l.company, a.provider, a.model, a.status,
                        a.summary, a.error, a.created_at, a.finished_at FROM analysis_runs a
                        JOIN leads l ON l.id=a.lead_id ORDER BY a.id DESC LIMIT 40""").fetchall()]
                    for record in records:
                        record['findings'] = [dict(f) for f in conn.execute(
                            'SELECT * FROM findings WHERE run_id=? ORDER BY id', (record['id'],)).fetchall()]
                    return self._send(200, records)
                if route == "/api/leads/import" and method == "POST":
                    result = import_leads(conn, self._body())
                    conn.commit()
                    return self._send(200, result)
                if route == "/api/stats" and method == "GET":
                    return self._send(200, stats(conn))
                if route == "/api/leads":
                    if method == "GET":
                        all_leads = [as_lead(x) for x in conn.execute("SELECT * FROM leads ORDER BY updated_at DESC, id DESC").fetchall()]
                        q = query.get("q", [""])[0].lower()[:120]
                        stage = query.get("stage", [""])[0]
                        if q:
                            all_leads = [l for l in all_leads if q in (l["company"] + " " + l["signal_note"] + " " + l["note"]).lower()]
                        if stage:
                            all_leads = [l for l in all_leads if l["stage"] == stage]
                        all_leads.sort(key=lambda x: (-x["score"], -x["id"]))
                        return self._send(200, all_leads)
                    if method == "POST":
                        data = validate(self._body())
                        if data.get("permission") == "nicht_kontaktieren":
                            data["stage"] = "gesperrt"
                        elif data.get("stage") == "gesperrt":
                            data["permission"] = "nicht_kontaktieren"
                        cols = ", ".join(data)
                        placeholders = ", ".join("?" for _ in data)
                        cursor = conn.execute(f"INSERT INTO leads ({cols}) VALUES ({placeholders})", tuple(data.values()))
                        row = conn.execute("SELECT * FROM leads WHERE id = ?", (cursor.lastrowid,)).fetchone()
                        conn.commit()
                        return self._send(201, as_lead(row))
                contact_list_match = re.fullmatch(r"/api/leads/(\d+)/contacts", route)
                if contact_list_match:
                    lid = int(contact_list_match.group(1))
                    lead = conn.execute('SELECT * FROM leads WHERE id=?',(lid,)).fetchone()
                    if not lead: return self._error('Lead nicht gefunden',404)
                    if method == 'GET':
                        records = [dict(r) for r in conn.execute('SELECT * FROM decision_contacts WHERE lead_id=? ORDER BY id DESC',(lid,)).fetchall()]
                        for record in records:
                            record['preview'] = json.loads(record.pop('preview_json') or '{}')
                        return self._send(200,{'contacts':records,'role_suggestions':role_suggestions(lead),
                                               'research_plan':research_plan(lead['company'],lead['offer'],lead['employees']),
                                               'provider':'eigene_quellenrecherche'})
                    if method == 'POST':
                        data = validate_contact(self._body())
                        cur = conn.execute('INSERT INTO decision_contacts (lead_id,full_name,job_title,decision_role,source_url,linkedin_url,note) VALUES (?,?,?,?,?,?,?)',
                            (lid,*(data[k] for k in ('full_name','job_title','decision_role','source_url','linkedin_url','note'))))
                        conn.commit()
                        return self._send(201,{'id':cur.lastrowid,'saved':True})
                contact_match = re.fullmatch(r"/api/contacts/(\d+)(/preview|/reveal)?",route)
                if contact_match:
                    ident = int(contact_match.group(1))
                    person = conn.execute('SELECT * FROM decision_contacts WHERE id=?',(ident,)).fetchone()
                    if not person: return self._error('Kontakt nicht gefunden',404)
                    lead = conn.execute('SELECT * FROM leads WHERE id=?',(person['lead_id'],)).fetchone()
                    if method == 'PATCH' and not contact_match.group(2):
                        try:
                            result=save_verification(conn,ident,self._body())
                        except ValueError as exc:
                            return self._error(str(exc))
                        conn.commit()
                        return self._send(200,result)
                    if method == 'DELETE' and not contact_match.group(2):
                        conn.execute('DELETE FROM decision_contacts WHERE id=?',(ident,));conn.commit()
                        return self._send(200,{'deleted':True})
                    if method == 'POST' and contact_match.group(2) in ('/preview','/reveal'):
                        return self._error('Externe Kontaktdatenanbieter sind in v0.6 deaktiviert. Eigene Quellenrecherche verwenden.',410)
                public_contact_match = re.fullmatch(r"/api/leads/(\d+)/contact-research",route)
                if public_contact_match:
                    lid = int(public_contact_match.group(1))
                    lead = conn.execute('SELECT * FROM leads WHERE id=?',(lid,)).fetchone()
                    if not lead: return self._error('Lead nicht gefunden',404)
                    if method == 'GET':
                        return self._send(200,list_contact_research(conn,lid))
                    if method == 'POST':
                        if self._body() != {'confirm_public_research':True}:
                            return self._error('Öffentliche Quellenrecherche ausdrücklich bestätigen.')
                        if not lead['website']:
                            return self._error('Zuerst die Unternehmenswebsite im Lead speichern.')
                        if lead['permission']=='nicht_kontaktieren' or lead['stage']=='gesperrt':
                            return self._error('Dieser Lead ist für Kontaktrecherche gesperrt.',403)
                        if conn.execute("SELECT id FROM contact_research_runs WHERE status IN ('queued','running') LIMIT 1").fetchone():
                            return self._error('Eine Kontaktrecherche läuft bereits.',409)
                        cur=conn.execute('INSERT INTO contact_research_runs (lead_id) VALUES (?)',(lid,))
                        conn.commit()
                        enqueue_contact_research(db_path,cur.lastrowid,lid,lead['website'],lead['offer'])
                        return self._send(202,{'id':cur.lastrowid,'status':'queued'})
                candidate_match = re.fullmatch(r"/api/contact-candidates/(\d+)/review",route)
                if candidate_match and method == 'POST':
                    data=self._body()
                    if not isinstance(data,dict) or set(data)!={'decision'}:
                        return self._error('Entscheidung fehlt.')
                    result=review_candidate(conn,int(candidate_match.group(1)),data['decision'])
                    conn.commit()
                    return self._send(200,result)
                analysis_match = re.fullmatch(r"/api/leads/(\d+)/analysis", route)
                if analysis_match:
                    ident = int(analysis_match.group(1))
                    lead = conn.execute("SELECT * FROM leads WHERE id=?", (ident,)).fetchone()
                    if not lead:
                        return self._error("Lead nicht gefunden", 404)
                    if method == "GET":
                        return self._send(200, list_analyses(conn, ident))
                    if method == "POST":
                        data = self._body()
                        if not isinstance(data, dict) or set(data) - {"provider", "model"}:
                            return self._error("Ungültige Analyse-Optionen")
                        provider = data.get("provider", "ollama")
                        model = data.get("model", "qwen3:8b")
                        if provider not in ("ollama", "rules") or not isinstance(model, str) or not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,80}", model):
                            return self._error("Ungültiger KI-Anbieter oder Modellname.")
                        if not lead["website"]:
                            return self._error("Zuerst eine Website beim Lead speichern.")
                        if conn.execute("SELECT 1 FROM analysis_runs WHERE status IN ('queued','running') LIMIT 1").fetchone():
                            return self._error("Es läuft bereits eine Analyse. Bitte anschließend erneut starten.", 409)
                        cursor = conn.execute("INSERT INTO analysis_runs(lead_id,provider,model) VALUES (?,?,?)",
                                              (ident,provider,model if provider=='ollama' else 'regelmodus'))
                        conn.commit()
                        enqueue(db_path, cursor.lastrowid, ident, lead['website'], provider, model)
                        return self._send(202, {"id": cursor.lastrowid, "status": "queued"})
                finding_match = re.fullmatch(r"/api/findings/(\d+)(/promote)?", route)
                if finding_match:
                    fid = int(finding_match.group(1))
                    f = conn.execute("SELECT * FROM findings WHERE id=?", (fid,)).fetchone()
                    if not f:
                        return self._error("Befund nicht gefunden", 404)
                    if not finding_match.group(2) and method == "PATCH":
                        data = self._body()
                        if not isinstance(data, dict) or set(data) != {'review_status'} or data['review_status'] not in ('freigegeben', 'verworfen'):
                            return self._error("Nur 'freigegeben' oder 'verworfen' erlaubt.")
                        conn.execute("UPDATE findings SET review_status=?,reviewed_at=datetime('now') WHERE id=?",
                                     (data['review_status'], fid))
                        conn.commit()
                        return self._send(200, {"saved": True})
                    if finding_match.group(2) and method == "POST":
                        if f['review_status'] != 'freigegeben':
                            return self._error("Befund muss zuerst freigegeben werden.", 409)
                        lead = conn.execute("SELECT * FROM leads WHERE id=?", (f['lead_id'],)).fetchone()
                        if lead['signal_note'] or lead['signal_source']:
                            return self._error("Lead hat bereits ein Signal. Vorhandene Daten nicht überschrieben; bitte bei Bedarf manuell übernehmen.", 409)
                        conn.execute("""UPDATE leads SET signal_note=?,signal_source=?,offer=?,updated_at=datetime('now') WHERE id=?""",
                                     (f['observation']+' (Hypothese: '+f['hypothesis']+')',f['source_url'],f['offer'],f['lead_id']))
                        conn.commit()
                        return self._send(200, {"saved": True, "lead": as_lead(conn.execute('SELECT * FROM leads WHERE id=?', (f['lead_id'],)).fetchone())})
                match = re.fullmatch(r"/api/leads/(\d+)", route)
                if match:
                    ident = int(match.group(1))
                    row = conn.execute("SELECT * FROM leads WHERE id = ?", (ident,)).fetchone()
                    if not row:
                        return self._error("Lead nicht gefunden", 404)
                    if method == "GET":
                        return self._send(200, as_lead(row))
                    if method == "DELETE":
                        conn.execute("DELETE FROM leads WHERE id = ?", (ident,))
                        conn.commit()
                        return self._send(200, {"deleted": True})
                    if method == "PATCH":
                        data = validate(self._body(), partial=True)
                        if not data:
                            return self._error("Keine Änderung")
                        if data.get("permission") == "nicht_kontaktieren":
                            data["stage"] = "gesperrt"
                        elif data.get("stage") == "gesperrt":
                            data["permission"] = "nicht_kontaktieren"
                        set_clause = ", ".join(f"{key} = ?" for key in data)
                        conn.execute(f"UPDATE leads SET {set_clause}, updated_at=datetime('now') WHERE id = ?", (*data.values(), ident))
                        conn.commit()
                        return self._send(200, as_lead(conn.execute("SELECT * FROM leads WHERE id = ?", (ident,)).fetchone()))
                brief_match = re.fullmatch(r"/api/leads/(\d+)/brief", route)
                if brief_match and method == "GET":
                    brief = lead_brief(conn, int(brief_match.group(1)))
                    if brief is None:
                        return self._error("Lead nicht gefunden", 404)
                    return self._send(200, brief)
                discovery_match = re.fullmatch(r"/api/leads/(\d+)/discovery", route)
                if discovery_match:
                    ident = int(discovery_match.group(1))
                    if not conn.execute("SELECT id FROM leads WHERE id=?", (ident,)).fetchone():
                        return self._error("Lead nicht gefunden", 404)
                    if method == "GET":
                        row = conn.execute("SELECT * FROM discovery WHERE lead_id=?", (ident,)).fetchone()
                        item = dict(row) if row else {"lead_id": ident, **{k: "offen" if k == "budget_status" else "" for k in DISCOVERY_FIELDS}}
                        return self._send(200, {**item, "completeness": discovery_summary(item)})
                    if method == "PUT":
                        data = validate_discovery(self._body())
                        if not data:
                            return self._error("Keine Änderungen")
                        exists = conn.execute("SELECT lead_id FROM discovery WHERE lead_id=?", (ident,)).fetchone()
                        if not exists:
                            conn.execute("INSERT INTO discovery(lead_id) VALUES (?)", (ident,))
                        pairs = ", ".join(f"{k}=?" for k in data)
                        conn.execute(f"UPDATE discovery SET {pairs}, updated_at=datetime('now') WHERE lead_id=?", (*data.values(), ident))
                        row = dict(conn.execute("SELECT * FROM discovery WHERE lead_id=?", (ident,)).fetchone())
                        conn.commit()
                        return self._send(200, {**row, "completeness": discovery_summary(row)})
                if route == "/api/activities":
                    if method == "GET":
                        lead_id = int(query.get("lead_id", ["0"])[0])
                        rows = conn.execute("SELECT * FROM activities WHERE lead_id = ? ORDER BY id DESC LIMIT 80", (lead_id,)).fetchall()
                        return self._send(200, [dict(r) for r in rows])
                    if method == "POST":
                        data = self._body()
                        lid = int(data.get("lead_id", 0))
                        a_type = str(data.get("activity_type", "notiz"))[:80]
                        detail = str(data.get("detail", ""))[:2000]
                        if not lid or not conn.execute("SELECT id FROM leads WHERE id=?", (lid,)).fetchone():
                            return self._error("Lead nicht gefunden", 404)
                        if a_type not in ("notiz", "anfrage", "gespraech", "angebot", "einwand", "abschluss", "widerspruch"):
                            return self._error("Ungültiger Aktivitätstyp")
                        conn.execute("INSERT INTO activities (lead_id, activity_type, detail) VALUES (?, ?, ?)", (lid, a_type, detail))
                        conn.commit()
                        return self._send(201, {"saved": True})
                if route == "/api/tasks":
                    if method == "GET":
                        rows = conn.execute("""SELECT t.*, l.company FROM tasks t LEFT JOIN leads l ON t.lead_id=l.id
                                               ORDER BY t.done, (t.due_date=''), t.due_date, t.id DESC""").fetchall()
                        return self._send(200, [dict(x) for x in rows])
                    if method == "POST":
                        data = self._body()
                        title = str(data.get("title", "")).strip()[:250]
                        due = str(data.get("due_date", "")).strip()
                        lead_id = data.get("lead_id") or None
                        if not title:
                            return self._error("Aufgabe benötigt einen Titel")
                        if due:
                            date.fromisoformat(due)
                        if lead_id is not None and not conn.execute("SELECT id FROM leads WHERE id = ?", (int(lead_id),)).fetchone():
                            return self._error("Lead existiert nicht", 404)
                        cursor = conn.execute("INSERT INTO tasks (lead_id, title, due_date) VALUES (?, ?, ?)", (lead_id, title, due))
                        conn.commit()
                        return self._send(201, {"id": cursor.lastrowid})
                match = re.fullmatch(r"/api/tasks/(\d+)", route)
                if match:
                    ident = int(match.group(1))
                    if method == "PATCH":
                        data = self._body()
                        if set(data) != {"done"} or not isinstance(data["done"], bool):
                            return self._error("Nur done: true/false erlaubt")
                        cursor = conn.execute("UPDATE tasks SET done = ? WHERE id = ?", (int(data["done"]), ident))
                        if not cursor.rowcount:
                            return self._error("Aufgabe nicht gefunden", 404)
                        conn.commit()
                        return self._send(200, {"saved": True})
                    if method == "DELETE":
                        conn.execute("DELETE FROM tasks WHERE id = ?", (ident,))
                        conn.commit()
                        return self._send(200, {"deleted": True})
            return self._error("Endpunkt nicht gefunden", 404)

        def _static(self, route, method):
            if method != "GET":
                return self._error("Nur Lesezugriff", 405)
            mapping = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                       "/style.css": ("style.css", "text/css"), "/workspace.js": ("workspace.js", "text/javascript"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}
            if route not in mapping:
                return self._error("Datei nicht gefunden", 404)
            path, mime = mapping[route]
            payload = (PUBLIC / path).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            self._run("GET")
        def do_POST(self):
            self._run("POST")
        def do_PATCH(self):
            self._run("PATCH")
        def do_PUT(self):
            self._run("PUT")
        def do_DELETE(self):
            self._run("DELETE")

        def _run(self, method):
            try:
                self._routes(method)
            except (ValueError, TypeError, OverflowError) as exc:
                self._error(str(exc), 400)
            except sqlite3.IntegrityError:
                self._error("Ungültiger Datensatz", 400)
            except BrokenPipeError:
                pass
            except Exception as exc:
                print("Serverfehler:", repr(exc))
                self._error("Interner Serverfehler", 500)

        def log_message(self, fmt, *args):
            if os.environ.get("AKQUISE_LOG_REQUESTS") == "1":
                super().log_message(fmt, *args)

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Lokales Akquise-Tool (nur localhost, nicht öffentlich hosten)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default=str(Path.home() / ".akquise-tool" / "akquise.sqlite3"))
    args = parser.parse_args()
    db = Path(args.db).expanduser().resolve()
    db.parent.mkdir(parents=True, exist_ok=True)
    with connect(db) as conn:
        init_db(conn)
        conn.execute("""UPDATE analysis_runs SET status='failed',error='Analyse durch Neustart unterbrochen.',
                        finished_at=datetime('now') WHERE status IN ('queued','running')""")
        conn.execute("""UPDATE quick_scans SET status='failed',error='Recherche durch Neustart unterbrochen.',
                        finished_at=datetime('now') WHERE status IN ('queued','running')""")
        conn.commit()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(db))
    print(f"Akquise-Tool: http://127.0.0.1:{args.port}  |  SQLite: {db}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
