"""Minimal dependency-free local HTTP+JSON server. Not a public multi-user deployment."""
from __future__ import annotations

import contextlib
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
    CALL_OUTCOMES, MEETING_STATUSES, QUOTE_STATUSES, DRAFT_TYPES,
    daily_view, call_permission, create_call, create_meeting, quote_preview,
    make_proposal, proposal_rows, proposal_detail, customer_markdown, create_mail_draft,
)
from .accounting_api import route_accounting, route_print
from .lead_finder import route_lead_finder
from .offer_flow import route_offer_flow
from .imprint_batch import route_imprint, route_company_data, recover_batches
from .company_data import check_suppressed, suppress_lead
from .website_scorer import route_scoring, recover_audits
from .buying_signals import route_signals, recover_scans
from .research_center import route_center
from .sales_integration import route_sales_integration, can_complete_task
from .quality import route_quality, start_scheduler
from .today import route_today
from .source_check import route_source_check
from .research.settings import route_research, load as load_research_settings
from .research import jobs as research_jobs
from .sweep import route_sweep, recover_sweeps, dedupe_candidates
from .duplicates import route_duplicates
from .research.catalog import route_catalog
from .profiles import route_profiles
from . import lead_imprint
from . import __version__
from . import qualification
from . import reach
from . import postcalc
from . import appearance
from . import focus as focus_mod
from .research import osm_local
from . import netpolicy
from .backup_restore import route_restore
from .workday import route_workday, ContactLocked, check_stage_change, assert_contact_allowed, after_meeting_done
from .report import route_report, recover_reports
from .pricing import route_pricing
from . import auth
from .backup_crypto import create_encrypted_backup, available as crypto_available
from .model import STAGES, INDUSTRIES, SIGNALS, OFFERS, PERMISSIONS, CONTACT_ROUTES, as_lead, connect, init_db, stats, discovery_summary

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
FIELDS = ("company", "website", "location", "contact_name", "contact_role", "contact_route", "industry", "employees", "signal_type", "signal_date", "signal_source",
          "signal_note", "offer", "estimated_budget", "stage", "permission", "permission_evidence", "note", "next_step", "next_date")
INT_FIELDS = {"employees", "estimated_budget"}
DATE_FIELDS = {"signal_date", "next_date"}
ENUMS = {"stage": STAGES, "industry": INDUSTRIES, "signal_type": tuple(SIGNALS), "offer": tuple(OFFERS), "permission": PERMISSIONS, "contact_route": CONTACT_ROUTES}
URL_FIELDS = {"website", "signal_source"}
OPTIONAL_ENUMS = {"industry", "offer"}
TEXT_LIMITS = {"company": 200, "location": 160, "contact_role": 120, "contact_name": 160, "permission_evidence": 500, "signal_note": 2000, "note": 4000, "next_step": 500}


DISCOVERY_FIELDS = ("problem", "impact", "current_solution", "desired_outcome", "timing",
                    "decision_process", "budget_status", "budget_note")
BUDGET_STATUSES = ("offen", "budget_vorhanden", "freigabe_offen", "kein_budget")
IMPORT_FIELDS = ("company", "website", "location", "industry", "employees", "signal_type", "signal_date",
                 "signal_source", "signal_note", "offer", "contact_name", "contact_role", "contact_route", "permission",
                 "permission_evidence", "next_step", "next_date")


class _CountingReader:
    """Reicht alles an den Eingabestrom durch und zählt die gelesenen Bytes."""

    def __init__(self, raw):
        self._raw, self.count = raw, 0

    def read(self, *a):
        data = self._raw.read(*a)
        self.count += len(data)
        return data

    def readline(self, *a):
        data = self._raw.readline(*a)
        self.count += len(data)
        return data

    def readinto(self, b):
        n = self._raw.readinto(b)
        self.count += n or 0
        return n

    def __getattr__(self, name):
        return getattr(self._raw, name)


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
            d.setdefault("industry", "")  # 2.0.0-dev13: ohne Angabe unbekannt statt „Sonstige“
            d.setdefault("offer", "")  # und keine vorgewählte Leistung
            identity = d["company"].casefold()
            url_identity = (d.get("website") or "").lower().rstrip('/')
            if identity in known or url_identity and url_identity in known:
                results["duplicates"] += 1
                continue
            if check_suppressed(conn, website=d.get("website", ""), name=d["company"]):
                results["suppressed"] = results.get("suppressed", 0) + 1
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
        # 2.0.0-dev13: Branche und Leistung dürfen leer bleiben („unbekannt“ / „noch keine gewählt“) – keine erfundenen Vorgaben.
        if key in ENUMS and value not in ENUMS[key] and not (key in OPTIONAL_ENUMS and value == ""):
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


STATIC_FILES = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
    "/style.css": ("style.css", "text/css"), "/theme.js": ("theme.js", "text/javascript"), "/workspace.js": ("workspace.js", "text/javascript"), "/favicon.svg": ("favicon.svg", "image/svg+xml"),
    "/accounting.js": ("accounting.js", "text/javascript"), "/assessment.js": ("assessment.js", "text/javascript"), "/reach.js": ("reach.js", "text/javascript"), "/postcalc.js": ("postcalc.js", "text/javascript"), "/osmlocal.js": ("osmlocal.js", "text/javascript"), "/leadfinder.js": ("leadfinder.js", "text/javascript"), "/datacheck.js": ("datacheck.js", "text/javascript"), "/scoring.js": ("scoring.js", "text/javascript"), "/signals.js": ("signals.js", "text/javascript"), "/center.js": ("center.js", "text/javascript"), "/salesint.js": ("salesint.js", "text/javascript"), "/quality.js": ("quality.js", "text/javascript"), "/today.js": ("today.js", "text/javascript"), "/sweep.js": ("sweep.js", "text/javascript"), "/report.js": ("report.js", "text/javascript"), "/quotes.js": ("quotes.js", "text/javascript"), "/offerflow.js": ("offerflow.js", "text/javascript"), "/chances.js": ("chances.js", "text/javascript"), "/tasks.js": ("tasks.js", "text/javascript"), "/pipeline.js": ("pipeline.js", "text/javascript"), "/jobs.js": ("jobs.js", "text/javascript"), "/catalog.js": ("catalog.js", "text/javascript"), "/akte.js": ("akte.js", "text/javascript"), "/formguard.js": ("formguard.js", "text/javascript"), "/nav.js": ("nav.js", "text/javascript"), "/leadlist.js": ("leadlist.js", "text/javascript"), "/workday.js": ("workday.js", "text/javascript"), "/invoice.css": ("invoice.css", "text/css"), "/print.js": ("print.js", "text/javascript")}

LOOPBACK_HOSTS = frozenset({'127.0.0.1', 'localhost', '::1'})
CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"


def _host_name(host_header):
    host = (host_header or '').strip().lower()
    if host.startswith('['):
        return host[1:host.find(']')] if ']' in host else ''
    return host.rsplit(':', 1)[0] if host.count(':') == 1 else host


def make_handler(db_path, allowed_hosts=None):
    hosts = LOOPBACK_HOSTS | {h.lower() for h in (allowed_hosts or ())}

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.rfile = _CountingReader(self.rfile)  # 2.0.0-dev10: mitzählen, wie viel vom Anfragekörper gelesen wurde

        def _drain(self, limit=1024 * 1024):
            """Ungelesenen Rest des Anfragekörpers einlesen (bis 1 MB), bevor die Verbindung endet. Wird eine Anfrage abgelehnt,
            ohne dass ihr Körper gelesen wurde, bricht Windows die Verbindung sonst hart ab – der Aufrufer sieht dann einen
            Verbindungsfehler statt der Fehlermeldung."""
            try:
                total = int(self.headers.get("Content-Length", "0") or 0)
            except (ValueError, AttributeError):
                return
            left = total - (self.rfile.count - getattr(self, "_body_from", self.rfile.count))
            if left <= 0:
                return
            if left > limit:
                self.close_connection = True  # zu groß zum Nachlesen: Verbindung nicht weiterverwenden
                return
            try:
                while left > 0:
                    chunk = self.rfile.read(min(65536, left))
                    if not chunk:
                        break
                    left -= len(chunk)
            except OSError:
                self.close_connection = True

        server_version = "SignalDesk/" + __version__.rsplit(".", 1)[0]  # v1.19: aus der Paketversion statt fest eingetragen
        user = None

        def _security_headers(self):
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")

        def _conn(self):
            return connect(db_path)

        def _offers(self):
            # 2.0.0-dev16 (M12): Vorlagen mit Preis aus dem zentralen Katalog (eigene Werte inbegriffen)
            from .catalog import offers_for_client
            with self._conn() as conn:
                return offers_for_client(conn)

        def _send(self, status, payload, extra_headers=None):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self._security_headers()
            for key, value in (extra_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def _error(self, msg, status=400):
            self._send(status, {"error": msg})

        def _send_raw(self, status, data, mime, filename=None, extra_headers=None):
            self.send_response(status)
            self.send_header("Content-Type", mime if mime.startswith("image/") else mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self._security_headers()
            if filename:
                safe = re.sub(r'[^A-Za-z0-9._-]+', '_', filename)[:150]
                self.send_header("Content-Disposition", f'attachment; filename="{safe}"')
            for key, value in (extra_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def _body(self, max_len=65536):
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise ValueError("Nur application/json erlaubt.")
            raw_len = self.headers.get("Content-Length", "0")
            if not raw_len.isdigit():
                raise ValueError("Ungültige Anfragegröße.")
            length = int(raw_len)
            if length <= 0 or length > max_len:
                raise ValueError("Ungültige Anfragegröße.")
            try:
                data = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
                raise ValueError("Ungültiges JSON.") from exc
            if not isinstance(data, dict):
                raise ValueError("Erwartet wird ein JSON-Objekt.")
            return data

        def _same_origin(self):
            origin = self.headers.get("Origin")
            if origin:
                expected = f"http://{self.headers.get('Host', '')}"
                if origin != expected:
                    self._error("Anfragen von fremden Webseiten sind gesperrt.", 403)
                    return False
            return True

        def _host_ok(self):
            # Schutz vor DNS-Rebinding: nur bekannte Hostnamen beantworten.
            if _host_name(self.headers.get("Host", "")) not in hosts:
                self._error("Unbekannter Host – SignalDesk antwortet nur unter 127.0.0.1/localhost bzw. freigegebenen Namen.", 421)
                return False
            return True

        def _guard(self, method, route):
            """Login-Pflicht und Rollenrechte (nur wenn der Login eingeschaltet ist)."""
            static = route in STATIC_FILES
            with self._conn() as conn:
                self.user = auth.session_user(conn, self.headers.get("Cookie", ""))
                required = auth.auth_required(conn)
            if not required or static or (method, route) in auth.PUBLIC_API:
                return True
            if not self.user:
                self._send(401, {"error": "Bitte anmelden.", "auth_required": True})
                return False
            if not auth.allowed(self.user["role"], method, route):
                self._error("Für deine Rolle nicht freigegeben.", 403)
                return False
            return True

        def _routes(self, method):
            if not self._host_ok():
                return
            if method != "GET" and not self._same_origin():
                return
            route = urlparse(self.path).path
            query = parse_qs(urlparse(self.path).query)
            if not self._guard(method, route):
                return
            if route.startswith("/api/auth/"):
                with self._conn() as conn:
                    if auth.route_auth(self, conn, method, route, self.user):
                        return
                return self._error("Endpunkt nicht gefunden", 404)
            if route == "/api/backup/encrypted" and method == "POST":
                return self._send(201, create_encrypted_backup(db_path, self._body()))
            if route == "/api/system/security" and method == "GET":
                with self._conn() as conn:
                    return self._send(200, security_status(conn, hosts, self.headers.get("Host", "")))
            if not route.startswith("/api/"):
                if method == "GET" and route_print(self, route, db_path, connect):
                    return
                return self._static(route, method)
            if route == "/api/config" and method == "GET":
                return self._send(200, {"stages": STAGES, "industries": INDUSTRIES, "signals": SIGNALS,
                                        "offers": self._offers(), "permissions": PERMISSIONS, "contact_routes": CONTACT_ROUTES, "budget_statuses": BUDGET_STATUSES})
            if route == "/api/ai/health" and method == "GET":
                return self._send(200, ollama_health())
            if route == "/api/ai/preview" and method == "POST":
                return self._send(200, demo_analysis(self._body()))
            if route == '/api/research/demo' and method == 'GET':
                return self._send(200,{'id':0,'status':'done','lead_id':None,'demo':True,'result':demo_report()})
            with self._conn() as conn:
                if route_accounting(self, conn, method, route, query, db_path):
                    return
                if route_lead_finder(self, conn, method, route, query):
                    return
                if route_imprint(self, conn, method, route, query, db_path) or route_company_data(self, conn, method, route, query):
                    return
                if route_scoring(self, conn, method, route, query, db_path):
                    return
                if route_signals(self, conn, method, route, query, db_path):
                    return
                if route_today(self, conn, method, route, query):
                    return
                if route_source_check(self, conn, method, route, query):
                    return
                if route_research(self, conn, method, route, query):
                    return
                if research_jobs.route_jobs(self, conn, method, route, query, db_path):
                    return
                if route_sweep(self, conn, method, route, query, db_path):
                    return
                if route_duplicates(self, conn, method, route, query):
                    return
                if route_catalog(self, conn, method, route, query, db_path):
                    return
                if route_workday(self, conn, method, route, query, db_path):
                    return
                if qualification.route(self, conn, method, route):  # 2.0.0-dev2: Zielkundenprofil, Bewertung, Erreichbarkeit
                    return
                if reach.route(self, conn, method, route):  # 2.0.0-dev3: eigene Erreichbarkeit, Eingang, Auslastung
                    return
                if postcalc.route(self, conn, method, route):  # 2.0.0-dev5: Nachkalkulation
                    return
                if appearance.route(self, conn, method, route):  # 2.0.0-dev11: Theme, Hell/Dunkel, Dichte
                    return
                if focus_mod.route(self, conn, method, route):  # 2.0.0-dev15: Fokusliste, Einstieg, Arbeitsansichten
                    return
                if osm_local.route(self, conn, method, route, query, db_path):  # 2.0.0-dev7: OpenStreetMap aus lokalem Auszug
                    return
                if route_profiles(self, conn, method, route, query, db_path):
                    return
                if lead_imprint.route_lead_imprint(self, conn, method, route, query, db_path):
                    return
                if netpolicy.route_netpolicy(self, conn, method, route):
                    return
                if route_restore(self, conn, method, route, query, db_path):
                    return
                if route_report(self, conn, method, route, query, db_path):
                    return
                if route_pricing(self, conn, method, route, query):
                    return
                if route_center(self, conn, method, route, query):
                    return
                if route_sales_integration(self, conn, method, route, query):
                    return
                if route_quality(self, conn, method, route, query, db_path):
                    return
                if route == '/api/workspace/catalog' and method == 'GET':
                    from .catalog import offers_for_client
                    return self._send(200, {'packages':offers_for_client(conn),'addons':{},'call_outcomes':CALL_OUTCOMES,
                                             'meeting_statuses':MEETING_STATUSES,'quote_statuses':QUOTE_STATUSES,
                                             'draft_types':DRAFT_TYPES})
                if route == '/api/workspace' and method == 'GET':
                    view=daily_view(conn)
                    view['call_permissions']={str(r['id']):call_permission(r) for r in conn.execute('SELECT * FROM leads')}
                    return self._send(200,view)
                if route == '/api/workspace/quote-preview' and method == 'POST':
                    return self._send(200,quote_preview(conn,self._body()))
                if route == '/api/workspace/proposals':
                    if method == 'GET': return self._send(200,proposal_rows(conn))
                    if method == 'POST': return self._send(201,make_proposal(conn,self._body()))
                if route_offer_flow(self, conn, method, route):  # 2.0.0-dev17: Versandfassung, Projektstart
                    return
                from .chances import route_chances
                if route_chances(self, conn, method, route):  # 2.0.0-dev18: Verkaufschancen je Firma
                    return
                proposal_match=re.fullmatch(r'/api/workspace/proposals/(\d+)(/customer)?',route)
                if proposal_match:
                    ident=int(proposal_match.group(1))
                    if method=='GET':
                        try: detail=proposal_detail(conn,ident,customer_only=bool(proposal_match.group(2)))
                        except ValueError as exc: return self._error(str(exc),404)
                        if proposal_match.group(2):
                            from .offer_flow import release_info, state as offer_state
                            rel=release_info(conn.execute('SELECT * FROM proposals WHERE id=?',(ident,)).fetchone())
                            detail['markdown']=customer_markdown(detail['customer'],rel)
                            detail['release']=rel
                            detail['filename']=offer_state(conn,ident)['filename']
                        return self._send(200,detail)
                    if method=='PATCH' and not proposal_match.group(2):
                        from .offer_flow import set_status
                        try: return self._send(200,set_status(conn,ident,self._body()))
                        except LookupError as exc: return self._error(str(exc),404)
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
                        after_meeting_done(conn,meeting['lead_id'])
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
                        last = focus_mod.last_contacts(conn)  # 2.0.0-dev15: Spalte „letzter Kontakt“
                        for l in all_leads:
                            l["last_contact"] = last.get(l["id"], "")
                        return self._send(200, all_leads)
                    if method == "POST":
                        data = validate(self._body())
                        data.setdefault("industry", "")  # 2.0.0-dev13: keine erfundenen Vorgaben
                        data.setdefault("offer", "")
                        if data.get("permission") == "nicht_kontaktieren":
                            data["stage"] = "gesperrt"
                        elif data.get("stage") == "gesperrt":
                            data["permission"] = "nicht_kontaktieren"
                        hits = check_suppressed(conn, website=data.get("website", ""), name=data["company"])
                        if hits and data.get("stage") != "gesperrt":
                            return self._error("Diese Firma steht auf der Sperrliste (" + ", ".join(h["kind"] + " „" + h["display"] + "“" for h in hits) + "). Widerspruch bleibt bestehen – kein neuer Lead.", 409)
                        cols = ", ".join(data)
                        placeholders = ", ".join("?" for _ in data)
                        cursor = conn.execute(f"INSERT INTO leads ({cols}) VALUES ({placeholders})", tuple(data.values()))
                        if data.get("stage") == "gesperrt":
                            suppress_lead(conn, cursor.lastrowid)
                        row = conn.execute("SELECT * FROM leads WHERE id = ?", (cursor.lastrowid,)).fetchone()
                        conn.commit()
                        if row["website"]:  # v1.19: Firmendaten automatisch aus dem Impressum (nur leere Felder)
                            lead_imprint.queue(conn, db_path, row["id"], "neuer Lead mit Website")
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
                        if conn.execute("SELECT 1 FROM invoices WHERE lead_id=? LIMIT 1", (ident,)).fetchone():
                            return self._error("Lead hat Rechnungen. Wegen Aufbewahrungspflichten (GoBD/AO, 8–10 Jahre) nicht löschbar – stattdessen auf 'verloren' setzen bzw. sperren.", 409)
                        if row["stage"] == "gesperrt" or row["permission"] == "nicht_kontaktieren":
                            suppress_lead(conn, ident, "Gesperrter Lead gelöscht – Sperre bleibt")
                        conn.execute("DELETE FROM leads WHERE id = ?", (ident,))
                        conn.commit()
                        return self._send(200, {"deleted": True})
                    if method == "PATCH":
                        body = self._body()
                        lost = {k: body.pop(k) for k in ("lost_reason", "lost_note") if isinstance(body, dict) and k in body}
                        data = validate(body, partial=True)
                        if not data:
                            return self._error("Keine Änderung")
                        check_stage_change(conn, row, data)  # v1.18: keine Kontaktphase bei Sperre
                        data.update(qualification.check_lost(row, data, lost.get("lost_reason", ""), lost.get("lost_note", "")))  # 2.0.0-dev2
                        if data.get("permission") == "nicht_kontaktieren":
                            data["stage"] = "gesperrt"
                        elif data.get("stage") == "gesperrt":
                            data["permission"] = "nicht_kontaktieren"
                        set_clause = ", ".join(f"{key} = ?" for key in data)
                        conn.execute(f"UPDATE leads SET {set_clause}, updated_at=datetime('now') WHERE id = ?", (*data.values(), ident))
                        if data.get("stage") == "gesperrt":
                            suppress_lead(conn, ident)
                        if data.get("stage") == "verloren" and row["stage"] != "verloren":
                            from .chances import close_open
                            close_open(conn, ident, data.get("lost_reason"), data.get("lost_note"))  # 2.0.0-dev18: keine offene Chance bei verlorener Firma
                        conn.commit()
                        if data.get("website") and data["website"] != row["website"]:  # v1.19: neue Website → Impressum lesen
                            conn.execute("UPDATE leads SET imprint_checked_at='' WHERE id=? AND (legal_name='' OR legal_name IS NULL)", (ident,))
                            conn.commit()
                            lead_imprint.queue(conn, db_path, ident, "Website eingetragen")
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
                        if data["done"]:
                            allowed, why = can_complete_task(conn, ident)
                            if not allowed:
                                return self._error(why, 409)
                        cursor = conn.execute("UPDATE tasks SET done = ?, done_at = CASE WHEN ? THEN datetime('now') ELSE '' END WHERE id = ?",
                                              (int(data["done"]), int(data["done"]), ident))
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
            mapping = STATIC_FILES
            if route not in mapping:
                return self._error("Datei nicht gefunden", 404)
            path, mime = mapping[route]
            payload = (PUBLIC / path).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self._security_headers()
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
            self._body_from = self.rfile.count
            try:
                self._routes(method)
            except auth.NotLoggedIn as exc:
                self._send(401, {"error": str(exc), "auth_required": True})
            except auth.Throttled as exc:
                self._error(str(exc), 429)
            except PermissionError as exc:
                self._error(str(exc), 403)
            except KeyError as exc:
                self._error("Pflichtfeld fehlt: " + str(exc), 400)
            except ContactLocked as exc:  # v1.18: Kontaktsperre / fehlende Freigabe
                self._error(str(exc), 409)
            except LookupError as exc:
                self._error(str(exc).strip("'\"") or "Nicht gefunden", 404)
            except (ValueError, TypeError, OverflowError) as exc:
                self._error(str(exc), 400)
            except sqlite3.IntegrityError as exc:
                self._error(str(exc) or "Ungültiger Datensatz", 400)
            except BrokenPipeError:
                pass
            except Exception as exc:
                print("Serverfehler:", repr(exc))
                self._error("Interner Serverfehler", 500)
            finally:
                self._drain()

        def log_message(self, fmt, *args):
            if os.environ.get("AKQUISE_LOG_REQUESTS") == "1":
                super().log_message(fmt, *args)

    return Handler


SCHEMA_VERSION = 31  # 2.0.0-dev18 – bei Schemaänderungen erhöhen (Verkaufschancen je Firma)


def backup_before_migration(db):
    """Sichert eine bestehende Datenbank automatisch, bevor ein neueres Schema ergänzt wird."""
    if not Path(db).exists() or Path(db).stat().st_size == 0:
        return None
    with contextlib.closing(sqlite3.connect(str(db))) as raw, raw:
        version = raw.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return None
    from .accounting_api import create_backup
    return create_backup(db)["path"]


def prepare_database(db):
    """Sicherung vor Schema-Update, Migration aller Module, Wiederaufnahme unterbrochener Aufträge. Gibt den Sicherungspfad zurück."""
    backup = backup_before_migration(db)
    with connect(db) as conn:
        old_version = conn.execute("PRAGMA user_version").fetchone()[0]
        init_db(conn)
        if 0 < old_version < 23:
            dedupe_candidates(conn)  # v1.17: Bestand einmalig bereinigen (sichere Dubletten zusammenführen, mögliche markieren)
        if 0 < old_version < 29:
            from .company_data import backfill_sole_records
            backfill_sole_records(conn)  # 2.0.0-dev10: Nachweise für bereits übernommene Betriebe ohne Rechtsform nachziehen
        if 0 < old_version < 31:
            from .chances import ensure_first_chances
            ensure_first_chances(conn)  # 2.0.0-dev18: eine erste Chance je Firma mit Verkaufsbezug, Angebote und Termine zugeordnet
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.execute("""UPDATE analysis_runs SET status='failed',error='Analyse durch Neustart unterbrochen.',
                        finished_at=datetime('now') WHERE status IN ('queued','running')""")
        conn.execute("""UPDATE quick_scans SET status='failed',error='Recherche durch Neustart unterbrochen.',
                        finished_at=datetime('now') WHERE status IN ('queued','running')""")
        research_jobs.recover(conn)  # v1.16: unterbrochene Auftragsschritte wieder einreihen (vor den fachlichen Wiederaufnahmen)
        recover_batches(conn)
        recover_audits(conn)
        recover_scans(conn)
        recover_sweeps(conn)
        recover_reports(conn)
        load_research_settings(conn)  # v1.15: Schalter für Abruf/Auswertung
        netpolicy.load(conn)  # v1.19: Offline-Modus
        conn.commit()
    return backup


def security_status(conn, hosts, host_header=''):
    """Selbstauskunft für die Oberfläche: welche Schutzmaßnahmen aktiv sind und was für Team-Betrieb fehlt."""
    required = auth.auth_required(conn)
    team_host = sorted(h for h in hosts if h not in LOOPBACK_HOSTS)
    checks = [
        {'key': 'host', 'ok': True, 'label': 'Host-Prüfung gegen DNS-Rebinding', 'detail': 'Erlaubt: ' + ', '.join(sorted(hosts))},
        {'key': 'origin', 'ok': True, 'label': 'Schreibende Anfragen nur von SignalDesk selbst (Origin-Prüfung, nur JSON)', 'detail': ''},
        {'key': 'headers', 'ok': True, 'label': 'Sicherheits-Header (CSP ohne Inline-Skripte, kein Einbetten, kein Referrer)', 'detail': ''},
        {'key': 'auth', 'ok': required or not team_host, 'label': 'Login-Pflicht' if required else 'Ohne Login (lokaler Einzelplatz)',
         'detail': 'Rollen: ' + ', '.join(auth.ROLES) if required else 'Für Team-Betrieb Login einschalten.'},
        {'key': 'crypto', 'ok': crypto_available(), 'label': 'Verschlüsselte Sicherung verfügbar' if crypto_available() else 'Verschlüsselte Sicherung nicht verfügbar',
         'detail': '' if crypto_available() else 'Optional: pip install -r requirements-team.txt'},
        {'key': 'tls', 'ok': not team_host, 'label': 'Transportverschlüsselung', 'detail': 'Lokal nicht nötig (127.0.0.1).' if not team_host else
         'Im Netzwerk nur hinter einem TLS-Proxy (HTTPS) betreiben – SignalDesk selbst spricht nur HTTP.'},
    ]
    return {'checks': checks, 'auth_required': required, 'users': conn.execute('SELECT COUNT(*) FROM users WHERE active=1').fetchone()[0],
            'schema_version': SCHEMA_VERSION, 'server_version': 'SignalDesk/' + __version__.rsplit('.', 1)[0]}


def reset_login(conn):
    """Notfallzugang für den lokalen Rechner: schaltet die Login-Pflicht aus und beendet alle Sitzungen."""
    from .quality import put_setting
    from .company_data import _audit
    put_setting(conn, 'auth_required', False)
    conn.execute('DELETE FROM sessions')
    _audit(conn, 'auth', 0, 'login_pflicht_notfall_aus', 'Kommandozeile --reset-login')
    conn.commit()


def running_instance(port, timeout=1.5):
    """True, wenn auf dem Port bereits SignalDesk antwortet."""
    from urllib.request import urlopen
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/config", timeout=timeout) as resp:
            return resp.headers.get("Server", "").startswith("SignalDesk/")
    except (OSError, ValueError):
        return False


def bind_server(handler, port, attempts=20, host="127.0.0.1"):
    """Bindet host:port oder den nächsten freien Port. Gibt (server, port) zurück."""
    last_error = None
    for candidate in range(port, port + attempts):
        try:
            return ThreadingHTTPServer((host, candidate), handler), candidate
        except OSError as exc:
            last_error = exc
    raise OSError(f"Kein freier Port zwischen {port} und {port + attempts - 1}: {last_error}")


def open_browser_later(url, delay=0.8):
    import threading
    import webbrowser

    def _open():
        try:
            webbrowser.open(url, new=2)
        except Exception:  # Browser-Start ist Komfort, kein Muss
            pass
    timer = threading.Timer(delay, _open)
    timer.daemon = True
    timer.start()
    return timer


def main():
    parser = argparse.ArgumentParser(description="Lokales Akquise-Tool (nur localhost, nicht öffentlich hosten)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default=str(Path.home() / ".akquise-tool" / "akquise.sqlite3"))
    parser.add_argument("--open-browser", action="store_true", help="Benutzeroberfläche nach dem Start im Standardbrowser öffnen")
    parser.add_argument("--host", default="127.0.0.1", help="Bind-Adresse. Andere als 127.0.0.1 nur mit eingeschaltetem Login (Team-Betrieb hinter TLS-Proxy)")
    parser.add_argument("--allowed-host", action="append", default=[], help="Zusätzlich erlaubter Hostname (z. B. signaldesk.firma.intern)")
    parser.add_argument("--no-scheduler", action="store_true", help="Wiederkehrende Rechercheaufträge nicht automatisch ausführen")
    parser.add_argument("--offline", action="store_true", help="Offline-Modus für diese Sitzung: keine Abrufe aus dem Internet")
    parser.add_argument("--reset-login", action="store_true", help="Notfall: Login-Pflicht ausschalten (z. B. wenn die Administration ausgesperrt ist) und beenden")
    args = parser.parse_args()
    if args.reset_login:
        db = Path(args.db).expanduser().resolve()
        prepare_database(db)
        with connect(db) as conn:
            reset_login(conn)
        print("Login-Pflicht ausgeschaltet. SignalDesk normal starten und unter „Einstellungen → Daten & Zugang“ Passwörter neu setzen.")
        return
    if running_instance(args.port):
        url = f"http://127.0.0.1:{args.port}"
        print(f"SignalDesk läuft bereits: {url}")
        if args.open_browser:
            open_browser_later(url, delay=0).join()
        return
    db = Path(args.db).expanduser().resolve()
    db.parent.mkdir(parents=True, exist_ok=True)
    netpolicy.STATE['forced'] = bool(args.offline)
    lead_imprint.ENABLED = True  # v1.19: im laufenden Programm Firmendaten automatisch aus dem Impressum übertragen
    backup = prepare_database(db)
    if backup:
        print(f"Datenbank-Update erkannt – Sicherung angelegt: {backup}")
    allowed_hosts = set(args.allowed_host)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        with connect(db) as conn:
            if not (auth.auth_required(conn) and auth.has_users(conn)):
                raise SystemExit("Abbruch: Betrieb im Netzwerk nur mit eingeschaltetem Login. Zuerst lokal starten, Administration anlegen und Login einschalten.")
        print("Hinweis: SignalDesk spricht nur HTTP. Im Netzwerk unbedingt hinter einem TLS-Proxy (HTTPS) betreiben.")
        if args.host not in ("0.0.0.0", "::"):
            allowed_hosts.add(args.host)
    server, port = bind_server(make_handler(db, allowed_hosts), args.port, host=args.host)
    if not args.no_scheduler:
        start_scheduler(db)
    with connect(db) as conn:
        if research_jobs.pending(conn)[0]:
            research_jobs.ensure_workers(db)  # nach Neustart offene Recherche-Aufträge fortsetzen
            print("Offene Recherche-Aufträge werden fortgesetzt.")
    url = f"http://127.0.0.1:{port}"
    if port != args.port:
        print(f"Port {args.port} ist belegt – weiche auf {port} aus.")
    print(f"SignalDesk läuft: {url}  |  Daten: {db}")
    print("Dieses Fenster offen lassen, solange du SignalDesk nutzt. Beenden: Fenster schließen oder Strg+C.")
    if args.open_browser:
        open_browser_later(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
