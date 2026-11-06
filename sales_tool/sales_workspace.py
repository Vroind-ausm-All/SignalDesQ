"""Local-first daily sales workflow & productized fixed-scope proposals.

Never sends email, places calls or syncs external calendars. All pricing inputs are
internal, while the customer-facing proposal always displays a complete fixed price.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from decimal import Decimal, ROUND_CEILING

# Catalogue is deliberately editable and has explicit inclusions/exclusions.
PACKAGES = {
    'pilot': {
        'title': 'Website- & Anfrage-Pilot', 'outcome': 'Ein konkreter Anfrageweg ist einfacher und überprüfbar nutzbar.',
        'weeks': '1–2 Wochen', 'minimum_eur': 1450,
        'included': ['Kick-off und Zieldefinition', 'Kurzaudit eines Anfragewegs', 'Umsetzung einer klar abgegrenzten Verbesserung', 'Funktionsprüfung und Übergabe'],
        'excluded': ['Vollständiger Website-Relaunch', 'Texterstellung für die gesamte Website', 'Laufendes Marketing / Werbebudget'],
        'hours': 19, 'external_cost_eur': 90, 'revision_rounds': 1,
    },
    'conversion': {
        'title': 'B2B Website- & Conversion-Sprint', 'outcome': 'Eine messbare Produkt-/Leistungsstrecke für qualifizierte Anfragen.',
        'weeks': '3–5 Wochen', 'minimum_eur': 5900,
        'included': ['Zielgruppen- & Conversion-Workshop', 'Konzept und UX für bis zu 4 Kernseiten', 'Responsive Umsetzung', 'Kontakt- oder Anfrageformular', 'Basis-Tracking und Qualitätsprüfung', 'Übergabe und Einweisung'],
        'excluded': ['Media-Budget', 'Komplette Contentproduktion', 'Externe Lizenz- und Hostinggebühren'],
        'hours': 78, 'external_cost_eur': 240, 'revision_rounds': 2,
    },
    'brand': {
        'title': 'Brand- & Design-System', 'outcome': 'Ein konsistenter Markenauftritt mit wiederverwendbaren Vorlagen.',
        'weeks': '2–4 Wochen', 'minimum_eur': 4200,
        'included': ['Marken-Workshop', 'Visuelle Leitidee', 'Logo-/Identitätsüberarbeitung im definierten Umfang', 'Farben und Typografie', 'Digitales Styleguide-Paket und 3 Vorlagen'],
        'excluded': ['Markenrechtliche Prüfung', 'Fotoshootings und Printproduktion', 'Unbegrenzte Varianten'],
        'hours': 58, 'external_cost_eur': 180, 'revision_rounds': 2,
    },
    'care': {
        'title': 'Growth Care – Website & Optimierung', 'outcome': 'Kontinuierliche Verbesserung eines bestehenden digitalen Anfragewegs.',
        'weeks': 'fortlaufend / monatlich', 'billing': 'monatlich', 'minimum_eur': 790,
        'included': ['Monatliche Funktions- und Tracking-Kontrolle', 'Eine klar definierte kleine Conversion-Optimierung pro Monat', 'Monatsreport mit 30-Minuten-Review', 'Dokumentierte Übergabe der Änderungen'],
        'excluded': ['Hosting und Drittanbieter-Lizenzen', '24/7 Support oder garantierte Reaktionszeiten', 'Kompletter Website-Relaunch', 'Größere neue Funktionen'],
        'hours': 8, 'external_cost_eur': 55, 'revision_rounds': 1,
    },
    'portal': {
        'title': 'Kundenportal-MVP', 'outcome': 'Ein klar definierter digitaler Kundenprozess als benutzbares MVP.',
        'weeks': '8–12 Wochen', 'minimum_eur': 18500,
        'included': ['Prozess-Workshop', 'UX-Prototyp', 'Benutzeranmeldung und Rollen (Basis)', 'Ein Kernprozess mit Datenansicht und Eingabe', 'Tests und Deployment-Vorbereitung', 'Dokumentation und Übergabe'],
        'excluded': ['Komplexe ERP-Integration', 'Native iOS-/Android-Apps', '24/7 Betrieb und SLA', 'Unbegrenzte Funktionswünsche'],
        'hours': 238, 'external_cost_eur': 850, 'revision_rounds': 2,
    },
}
PACKAGES['automation'] = {
    'title': 'Automatisierungsprojekt – ein Prozess digital', 'outcome': 'Ein klar abgegrenzter manueller Ablauf läuft automatisiert, nachvollziehbar und mit weniger Doppelerfassung.',
    'weeks': '4–6 Wochen', 'minimum_eur': 6900,
    'included': ['Prozessaufnahme-Workshop mit den beteiligten Personen', 'Ist-/Soll-Ablauf mit Datenfluss und Zuständigkeiten',
                 'Umsetzung der Automatisierung für einen definierten Prozess (z. B. Formular → System, Excel → Datenbank, Benachrichtigungen)',
                 'Fehler- und Ausnahmebehandlung', 'Test mit echten, freigegebenen Beispieldaten', 'Dokumentation und Übergabe'],
    'excluded': ['Weitere Prozesse oder Abteilungen', 'Anpassungen am ERP/CRM durch dessen Hersteller', 'Lizenzkosten von Drittsystemen', '24/7-Betrieb und SLA'],
    'hours': 96, 'external_cost_eur': 300, 'revision_rounds': 2,
}
# Kundenseitige Angebotsstruktur (Master-Prompt Modul 8): Liefergegenstände, Abnahmekriterien, Drittanbieter-/Folgekosten
PACKAGE_DETAILS = {
    'pilot': {'deliverables': ['Kurzaudit des Anfragewegs (PDF)', 'Umgesetzte Verbesserung auf der bestehenden Website', 'Übergabeprotokoll'],
              'acceptance': ['Der verbesserte Anfrageweg funktioniert auf Desktop und Smartphone', 'Testanfrage kommt beim vereinbarten Empfänger an'],
              'third_party': ['Keine, sofern bestehende Systeme (Website, Formular-Tool) genutzt werden.']},
    'conversion': {'deliverables': ['Konzept und UX-Entwürfe für bis zu 4 Kernseiten', 'Umgesetzte, responsive Seiten', 'Anfrageformular inkl. Bestätigung', 'Tracking-Plan und eingerichtetes Basis-Tracking', 'Einweisung (60 Min.)'],
                   'acceptance': ['Seiten entsprechen den freigegebenen Entwürfen', 'Formular und Tracking sind getestet', 'Darstellung auf aktuellen Browsern und Smartphones geprüft'],
                   'third_party': ['Hosting/CMS-Lizenz, falls neu erforderlich: ca. 10–40 € pro Monat, Vertrag direkt mit dem Anbieter.', 'Bildlizenzen nach Bedarf.']},
    'brand': {'deliverables': ['Visuelle Leitidee', 'Überarbeitetes Logo/Identität im vereinbarten Umfang', 'Farb- und Typografie-Definition', 'Digitales Styleguide-Paket', '3 Vorlagen'],
              'acceptance': ['Freigabe der Leitidee', 'Styleguide und Vorlagen vollständig in den vereinbarten Formaten geliefert'],
              'third_party': ['Schriftlizenzen und Bildrechte nach Bedarf, direkt beim Rechteinhaber.', 'Markenrechtliche Prüfung durch eine Kanzlei (nicht enthalten).']},
    'care': {'deliverables': ['Monatlicher Kurzreport', 'Eine dokumentierte Optimierung pro Monat', '30-Minuten-Review'],
             'acceptance': ['Report und Änderungsprotokoll liegen bis zum vereinbarten Termin vor'],
             'third_party': ['Hosting, Domains und Lizenzen bleiben beim Kunden bzw. dessen Anbietern.']},
    'portal': {'deliverables': ['UX-Prototyp', 'Lauffähiges MVP mit Anmeldung, Rollen und einem Kernprozess', 'Testprotokoll', 'Technische Dokumentation', 'Übergabe-Workshop'],
               'acceptance': ['Der vereinbarte Kernprozess ist mit Testdaten vollständig durchführbar', 'Rollen und Rechte entsprechen dem Konzept', 'Abnahmetest gemeinsam bestanden'],
               'third_party': ['Hosting/Server: ca. 30–150 € pro Monat je nach Nutzung, Vertrag direkt mit dem Anbieter.', 'Optional: Wartungsvertrag nach dem Go-live (separates Angebot).']},
    'automation': {'deliverables': ['Prozessdokumentation Ist/Soll', 'Eingerichtete Automatisierung für einen Prozess', 'Testprotokoll mit Beispieldaten', 'Betriebsdokumentation'],
                   'acceptance': ['Der vereinbarte Prozess läuft mit Testdaten ohne manuellen Zwischenschritt', 'Ausnahmen werden wie vereinbart gemeldet'],
                   'third_party': ['Automatisierungsplattform oder Schnittstellen-Lizenzen: je nach Volumen ca. 0–100 € pro Monat, direkt beim Anbieter.']},
}

ADDONS = {
    'copy': {'title':'Texte für bis zu 3 Kernseiten', 'included':'Redaktion/Überarbeitung von maximal drei Webseitentexten', 'hours':12, 'external_cost_eur':0, 'price_floor':700},
    'analytics': {'title':'Messkonzept & Dashboard', 'included':'Ereignismessung und ein einfaches Reporting-Dashboard', 'hours':15, 'external_cost_eur':50, 'price_floor':950},
    'seo': {'title':'Technisches SEO-Basispaket', 'included':'Meta-Struktur, Indexierungsprüfung und technische SEO-Grundlagen', 'hours':12, 'external_cost_eur':40, 'price_floor':750},
    'integration': {'title':'Eine Schnittstellen-Integration', 'included':'Eine definierte Datenübergabe über vorhandene API', 'hours':28, 'external_cost_eur':150, 'price_floor':2200},
    'training': {'title':'Zusätzlicher Übergabe-Workshop', 'included':'Ein zusätzlicher zweistündiger Workshop mit Dokumentation', 'hours':5, 'external_cost_eur':0, 'price_floor':350},
}
CALL_OUTCOMES = ('erreicht','rueckruf_vereinbart','mailbox','nicht_erreicht','kein_bedarf','termin_vereinbart','widerspruch')
MEETING_STATUSES = ('geplant','bestaetigt','erledigt','abgesagt')
QUOTE_STATUSES = ('entwurf','gesendet_manuell','angenommen','abgelehnt')
DRAFT_TYPES = ('nach_gespraech','terminbestaetigung','angebot_begleiten','rueckfrage')
OFFER_VALID_DAYS = 30


def init_workspace(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS calls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        outcome TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
        legal_note TEXT NOT NULL DEFAULT '', callback_date TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS meetings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        title TEXT NOT NULL, starts_at TEXT NOT NULL, duration_min INTEGER NOT NULL DEFAULT 30,
        location TEXT DEFAULT '', status TEXT DEFAULT 'geplant', notes TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'entwurf', internal_json TEXT NOT NULL,
        customer_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS mail_drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        draft_type TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
        contact_basis TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_calls_lead ON calls(lead_id);
      CREATE INDEX IF NOT EXISTS idx_meetings_time ON meetings(starts_at);
      CREATE INDEX IF NOT EXISTS idx_proposals_lead ON proposals(lead_id);
      CREATE INDEX IF NOT EXISTS idx_mail_lead ON mail_drafts(lead_id);
    ''')
    # v1.0: Angebotsnummer und Bindefrist (schonende Migration).
    cols={r[1] for r in conn.execute('PRAGMA table_info(proposals)')}
    for name in ('number','valid_until'):
        if name not in cols:
            conn.execute(f"ALTER TABLE proposals ADD COLUMN {name} TEXT DEFAULT ''")
    conn.commit()


def _required_text(data, key, max_len=300):
    val=data.get(key, '')
    if not isinstance(val,str) or not val.strip() or len(val.strip())>max_len:
        raise ValueError(f'{key}: Text (1–{max_len} Zeichen) erforderlich.')
    return val.strip()


def _optional_text(data,key,max_len=2000):
    val=data.get(key,'')
    if not isinstance(val,str) or len(val)>max_len:
        raise ValueError(f'{key}: Ungültiger Text.')
    return val.strip()


def _valid_date(value):
    if value:
        dt.date.fromisoformat(value)
    return value


def _lead(conn, lead_id):
    if isinstance(lead_id,bool) or not str(lead_id).isdigit():
        raise ValueError('Ungültige Lead-ID.')
    row=conn.execute('SELECT * FROM leads WHERE id=?',(int(lead_id),)).fetchone()
    if not row:
        raise ValueError('Lead existiert nicht.')
    return row


def call_permission(lead):
    if lead['permission']=='nicht_kontaktieren' or lead['stage']=='gesperrt':
        return {'allowed':False,'reason':'Widerspruch/Sperre – keine Ansprache.'}
    if lead['permission']=='opt_in' and lead['permission_evidence']:
        return {'allowed':True,'reason':'Opt-in ist dokumentiert; Umfang und Kanal vor Kontakt erneut prüfen.'}
    if lead['permission']=='telefon_einzelfall' and lead['permission_evidence']:
        return {'allowed':False,'reason':'Einzelfallprüfung dokumentiert; vor einem B2B-Werbeanruf manuell konkret bewerten. Keine pauschale Freigabe.'}
    return {'allowed':False,'reason':'Keine hinreichend dokumentierte Telefonberechtigung. Keine automatische Anwahl.'}


def create_call(conn, data):
    if not isinstance(data,dict) or set(data)-{'lead_id','outcome','notes','legal_note','callback_date'}:
        raise ValueError('Ungültige Anrufdaten.')
    lead=_lead(conn,data.get('lead_id'))
    outcome=data.get('outcome')
    if outcome not in CALL_OUTCOMES: raise ValueError('Ungültiges Gesprächsergebnis.')
    notes=_optional_text(data,'notes')
    legal=_optional_text(data,'legal_note',1000)
    callback=_valid_date(_optional_text(data,'callback_date',10))
    if outcome=='rueckruf_vereinbart' and (not callback or not notes):
        raise ValueError('Vereinbarten Rückruf mit Datum und Gesprächsnotiz belegen.')
    cur=conn.execute('INSERT INTO calls(lead_id,outcome,notes,legal_note,callback_date) VALUES (?,?,?,?,?)',(lead['id'],outcome,notes,legal,callback))
    if outcome=='widerspruch':
        conn.execute("UPDATE leads SET permission='nicht_kontaktieren',stage='gesperrt',next_step='',next_date='',updated_at=datetime('now') WHERE id=?",(lead['id'],))
        from .company_data import suppress_lead
        suppress_lead(conn,lead['id'],'Widerspruch im Gespräch')
    elif outcome=='rueckruf_vereinbart':
        conn.execute('INSERT INTO tasks (lead_id,title,due_date) VALUES (?,?,?)',(lead['id'],'Vereinbarten Rückruf prüfen: '+notes[:100],callback))
    conn.commit()
    return {'id':cur.lastrowid,'saved':True,'blocked':outcome=='widerspruch'}


def create_meeting(conn,data):
    if not isinstance(data,dict) or set(data)-{'lead_id','title','starts_at','duration_min','location','notes'}:
        raise ValueError('Ungültige Termindaten.')
    lead=_lead(conn,data.get('lead_id'))
    title=_required_text(data,'title',180)
    when=_required_text(data,'starts_at',16)
    try: dt.datetime.strptime(when,'%Y-%m-%dT%H:%M')
    except ValueError as exc: raise ValueError('Termin als YYYY-MM-DDTHH:MM angeben.') from exc
    if type(data.get('duration_min',30)) is not int or not 15<=data.get('duration_min',30)<=180:
        raise ValueError('Termindauer 15–180 Minuten.')
    cur=conn.execute('INSERT INTO meetings(lead_id,title,starts_at,duration_min,location,notes) VALUES (?,?,?,?,?,?)',(
        lead['id'],title,when,data.get('duration_min',30),_optional_text(data,'location',300),_optional_text(data,'notes',2000)))
    conn.commit()
    return {'id':cur.lastrowid,'saved':True}


def daily_view(conn):
    today=dt.date.today().isoformat()
    leads=conn.execute("SELECT id,company,stage,permission,permission_evidence,offer,next_step,next_date FROM leads WHERE stage NOT IN ('gewonnen','verloren','gesperrt') ORDER BY next_date='' ,next_date,id LIMIT 100").fetchall()
    todos=[dict(r) for r in conn.execute('''SELECT t.id,t.title,t.due_date,t.lead_id,t.action_type,t.permission_status,t.channel,t.permission_basis,l.company FROM tasks t LEFT JOIN leads l ON l.id=t.lead_id WHERE t.done=0 AND (l.id IS NULL OR l.stage!='gesperrt') ORDER BY (t.due_date=''),t.due_date,t.id LIMIT 80''')]
    meetings=[dict(r) for r in conn.execute('''SELECT m.*,l.company FROM meetings m JOIN leads l ON l.id=m.lead_id WHERE m.status IN ('geplant','bestaetigt') ORDER BY m.starts_at LIMIT 80''')]
    lead_steps=[{'id':r['id'],'company':r['company'],'next_step':r['next_step'],'next_date':r['next_date']} for r in leads if r['next_step']]
    proposals=[dict(r) for r in conn.execute("SELECT p.id,p.lead_id,p.status,l.company,p.created_at FROM proposals p JOIN leads l ON l.id=p.lead_id ORDER BY p.id DESC LIMIT 50")]
    return {'today':today,'tasks':todos,'meetings':meetings,'lead_steps':lead_steps,'proposals':proposals,
            'due_count':sum(1 for t in todos if t['due_date'] and t['due_date']<=today)+sum(1 for l in lead_steps if l['next_date'] and l['next_date']<=today),
            'calls_logged':conn.execute('SELECT COUNT(*) FROM calls').fetchone()[0]}


def _amount(val,key,lo,hi):
    if isinstance(val,bool) or type(val) not in (int,float) or not math.isfinite(val) or not lo<=val<=hi:
        raise ValueError(f'{key}: Wert außerhalb des erlaubten Bereichs.')
    return Decimal(str(val))


def quote_preview(data):
    if not isinstance(data,dict) or set(data)-{'package','addons','cost_rate_eur','risk_pct','target_margin_pct','custom_price_eur','tax_mode','project_label','customer_goal','assumptions'}:
        raise ValueError('Ungültige Kalkulation.')
    key=data.get('package')
    if key not in PACKAGES: raise ValueError('Bitte Leistungspaket auswählen.')
    plan=PACKAGES[key]
    raw=data.get('addons',[])
    if not isinstance(raw,list) or len(raw)>len(ADDONS) or any(not isinstance(x,str) or x not in ADDONS for x in raw) or len(set(raw))!=len(raw):
        raise ValueError('Ungültige Zusatzleistungen.')
    cost_rate=_amount(data.get('cost_rate_eur',55),'cost_rate_eur',15,250)
    risk=_amount(data.get('risk_pct',15),'risk_pct',0,60)
    margin=_amount(data.get('target_margin_pct',35),'target_margin_pct',10,75)
    custom=data.get('custom_price_eur')
    custom_val=None if custom in (None,'') else _amount(custom,'custom_price_eur',100,1000000)
    mode=data.get('tax_mode','offen')
    if mode not in ('offen','regel_19','kleinunternehmer'): raise ValueError('Steuerstatus ungültig.')
    label=_optional_text(data,'project_label',140) or plan['title']
    goal=_optional_text(data,'customer_goal',500) or plan['outcome']
    assumptions=_optional_text(data,'assumptions',1000)
    hours=Decimal(plan['hours'])+sum(Decimal(ADDONS[x]['hours']) for x in raw)
    external=Decimal(plan['external_cost_eur'])+sum(Decimal(ADDONS[x]['external_cost_eur']) for x in raw)
    cost=(hours*cost_rate+external)*(1+risk/100)
    min_approved=Decimal(plan['minimum_eur'])+sum(Decimal(ADDONS[x]['price_floor']) for x in raw)
    suggested=(max(min_approved,cost/(1-margin/100))/50).to_integral_value(rounding=ROUND_CEILING)*50
    final=custom_val if custom_val is not None else suggested
    # Below-cost override is never disguised as healthy margin.
    if final<cost:
        raise ValueError('Festpreis unterschreitet bereits die internen kalkulierten Kosten inklusive Puffer.')
    final=final.quantize(Decimal('0.01'))
    if mode=='regel_19':
        tax=(final*Decimal('.19')).quantize(Decimal('0.01'))
        tax_note='Zuzüglich 19 % Umsatzsteuer'
    elif mode=='kleinunternehmer':
        tax=Decimal(0)
        tax_note='Keine Umsatzsteuer ausgewiesen (Anwendung § 19 UStG vor Verwendung prüfen)'
    else:
        tax=Decimal(0)
        tax_note='Umsatzsteuerstatus offen – Angebot vor Versand steuerlich vervollständigen'
    included=plan['included']+[ADDONS[x]['included'] for x in raw]
    details=PACKAGE_DETAILS.get(key,{})
    customer={
        'project_label':label,'package':key,'package_title':plan['title'],'goal':goal,
        'included':included,'excluded':list(plan['excluded']),'assumptions':assumptions,
        'deliverables':list(details.get('deliverables',[]))+[ADDONS[x]['title'] for x in raw],
        'acceptance_criteria':list(details.get('acceptance',[])),'third_party_costs':list(details.get('third_party',[])),
        'weeks':plan['weeks'],'billing':plan.get('billing','einmalig'),'revision_rounds':plan['revision_rounds'],
        'net_eur':float(final),'vat_eur':float(tax),'total_eur':float(final+tax),'tax_mode':mode,'tax_note':tax_note,
        'payment_plan':('Monatliche Zahlung im Voraus; Vertragslaufzeit und Kündigungsfristen ausdrücklich vereinbaren.' if plan.get('billing')=='monatlich' else '40 % bei Beauftragung, 60 % nach vereinbarter Abnahme (Vorschlag, anpassen)'),
        'change_requests':'Zusätzliche Leistungen nur nach gesondertem transparentem Angebot und Freigabe.',
        'guarantee':'Keine Umsatz-, Lead- oder Rankinggarantie; Abnahme nach vereinbarten Liefergegenständen.'
    }
    internal={'estimated_hours':float(hours),'cost_rate_eur':float(cost_rate),'external_cost_eur':float(external),
              'risk_pct':float(risk),'target_margin_pct':float(margin),
              'cost_with_buffer_eur':float(cost.quantize(Decimal('.01'))), 'suggested_eur':float(suggested),
              'contribution_eur':float((final-cost).quantize(Decimal('.01'))),
              'contribution_pct':float(((final-cost)/final*100).quantize(Decimal('.1'))),
              'price_overridden':custom_val is not None}
    return {'customer':customer,'internal':internal}


def make_proposal(conn,data):
    if not isinstance(data,dict) or 'lead_id' not in data: raise ValueError('Lead-ID fehlt.')
    lead=_lead(conn,data['lead_id'])
    payload={k:v for k,v in data.items() if k!='lead_id'}
    if 'positions' in payload:  # Sprint D: Baukasten mit einzelnen Positionen
        from .pricing import build_quote
        proposal=build_quote(conn,payload)
    else:
        proposal=quote_preview(payload)
    from .accounting import _next_number
    issued=dt.date.today()
    number=_next_number(conn,'AN',issued.year)
    valid_until=(issued+dt.timedelta(days=OFFER_VALID_DAYS)).isoformat()
    proposal['customer'].update({'customer_company':lead['company'],'offer_number':number,
                                 'offer_date':issued.isoformat(),'valid_until':valid_until})
    cur=conn.execute('INSERT INTO proposals(lead_id,internal_json,customer_json,number,valid_until) VALUES (?,?,?,?,?)',(
        lead['id'],json.dumps(proposal['internal'],ensure_ascii=False),json.dumps(proposal['customer'],ensure_ascii=False),number,valid_until))
    conn.commit()
    return {'id':cur.lastrowid,'status':'entwurf','number':number,**proposal}


def proposal_rows(conn):
    return [{'id':r['id'],'lead_id':r['lead_id'],'company':r['company'],'status':r['status'],
             'number':r['number'] or f"#{r['id']}",'valid_until':r['valid_until'] or '',
             'expired':bool(r['valid_until'] and r['status'] in ('entwurf','gesendet_manuell') and r['valid_until']<dt.date.today().isoformat()),
             'project_label':json.loads(r['customer_json'])['project_label'],
             'net_eur':json.loads(r['customer_json'])['net_eur'],'created_at':r['created_at'],
             'invoiced':bool(conn.execute("SELECT 1 FROM invoices WHERE proposal_id=? AND kind<>'storno' AND status<>'storniert' LIMIT 1",(r['id'],)).fetchone())}
            for r in conn.execute('SELECT p.*,l.company FROM proposals p JOIN leads l ON l.id=p.lead_id ORDER BY p.id DESC LIMIT 100')]


def proposal_detail(conn,ident,customer_only=False):
    row=conn.execute('SELECT * FROM proposals WHERE id=?',(ident,)).fetchone()
    if not row: raise ValueError('Angebot nicht gefunden.')
    result={'id':row['id'],'status':row['status'],'number':row['number'] or f"#{row['id']}",'lead_id':row['lead_id'],
            'customer':json.loads(row['customer_json'])}
    if not customer_only: result['internal']=json.loads(row['internal_json'])
    return result


def customer_markdown(customer):
    def safe(s): return re.sub(r'[\r\n]+',' ',str(s)).strip()
    lines=[f"# Angebot: {safe(customer['project_label'])}",f"**An:** {safe(customer.get('customer_company',''))}"]
    if customer.get('offer_number'):
        lines.append(f"**Angebotsnummer:** {safe(customer['offer_number'])} · **Datum:** {safe(customer.get('offer_date',''))} · **Gültig bis:** {safe(customer.get('valid_until',''))}")
    lines+=['',
           '## Ziel und Ergebnis',safe(customer['goal'])]
    if customer.get('positions'):
        money=lambda v: f"{v:,.2f} €".replace(',','X').replace('.',',').replace('X','.')
        lines+=['','## Leistungen und Festpreise','','| Pos. | Leistung | Umfang | Festpreis netto |','|---|---|---|---|']
        for n,pos in enumerate(customer['positions'],1):
            lines.append(f"| {n} | {safe(pos['title'])} | {safe(pos['scope'])}{' · '+safe(pos['note']) if pos.get('note') else ''} | {money(pos['price_eur'])}{' / Monat' if pos['billing']=='monatlich' else ''} |")
        if customer.get('once_net_eur'): lines.append(f"| | **Summe einmalig** | | **{money(customer['once_net_eur'])}** |")
        if customer.get('monthly_net_eur'): lines.append(f"| | **Summe monatlich** | | **{money(customer['monthly_net_eur'])} / Monat** |")
        lines+=['','## Was enthalten ist']
        for n,pos in enumerate(customer['positions'],1):
            details=[x for x in pos.get('included',[])]
            lines.append(f"- **Pos. {n} {safe(pos['title'])}:** {safe(pos['description'])}" + (' Enthalten: '+'; '.join(safe(x) for x in details)+'.' if details else ''))
    else:
        lines+=['','## Enthaltene Leistungen']
        lines += ['- '+safe(x) for x in customer['included']]
    if customer.get('deliverables'): lines += ['','## Liefergegenstände']+['- '+safe(x) for x in customer['deliverables']]
    lines += ['','## Nicht enthalten']+['- '+safe(x) for x in customer['excluded']]
    if customer.get('assumptions'): lines+=['','## Voraussetzungen',safe(customer['assumptions'])]
    lines += ['','## Umfang und Abnahme',f"- Geplanter Zeitraum: {safe(customer['weeks'])}",
              f"- Korrekturschleifen: {customer['revision_rounds']}",
              '- Abnahme anhand der genannten Liefergegenstände nach gemeinsamer Prüfung.']
    if customer.get('acceptance_criteria'): lines += ['','## Abnahmekriterien']+['- '+safe(x) for x in customer['acceptance_criteria']]
    if customer.get('third_party_costs'): lines += ['','## Mögliche Drittanbieter- und Folgekosten (nicht im Festpreis)']+['- '+safe(x) for x in customer['third_party_costs']]
    if customer.get('billing')=='gemischt':
        lines += ['','## Festpreis',f"**{customer['once_net_eur']:.2f} EUR netto einmalig** und **{customer['monthly_net_eur']:.2f} EUR netto pro Monat**",safe(customer['tax_note'])]
        if customer['tax_mode']=='regel_19':
            lines.append(f"**Gesamtbetrag einmalig: {customer['once_net_eur']*1.19:.2f} EUR · monatlich: {customer['monthly_net_eur']*1.19:.2f} EUR**")
    else:
        lines += ['',
                  '## Festpreis',f"**{customer['net_eur']:.2f} EUR netto{' pro Monat' if customer.get('billing')=='monatlich' else ''}**",safe(customer['tax_note'])]
        if customer['tax_mode']!='offen': lines.append(f"**Gesamtbetrag: {customer['total_eur']:.2f} EUR{' pro Monat' if customer.get('billing')=='monatlich' else ''}**")
    lines += ['', '## Zahlung und Änderungen',safe(customer['payment_plan']),safe(customer['change_requests']),
              '', '## Hinweise',safe(customer['guarantee']),
              'Dieses Dokument ist ein Angebotsentwurf. Kundendaten, Fristen, Vertrags- und Steuerangaben vor Versand prüfen.']
    return '\n'.join(lines)+'\n'


def create_mail_draft(conn,data):
    if not isinstance(data,dict) or set(data)-{'lead_id','draft_type','contact_basis'}:
        raise ValueError('Ungültige Entwurfsdaten.')
    lead=_lead(conn,data.get('lead_id'))
    kind=data.get('draft_type')
    if kind not in DRAFT_TYPES: raise ValueError('Ungültige Vorlage.')
    if lead['permission']=='nicht_kontaktieren' or lead['stage']=='gesperrt':
        raise ValueError('Widerspruch/Sperre: keine Kontaktvorlage generieren.')
    basis=_optional_text(data,'contact_basis',500)
    if not basis: raise ValueError('Dokumentiere zuerst den vereinbarten Anlass bzw. Kontaktstatus.')
    template={
      'nach_gespraech':('Unser Gespräch – nächste Schritte','vielen Dank für das Gespräch. Hier die von uns besprochenen nächsten Schritte:\n\n[Konkrete Vereinbarung eintragen]'),
      'terminbestaetigung':('Bestätigung unseres Termins','wie besprochen bestätige ich unseren Termin:\n\n[Datum, Uhrzeit, Ort/Link ergänzen]'),
      'angebot_begleiten':('Unser Lösungsvorschlag','anbei der besprochene Lösungsvorschlag. Er fasst Ziele, Leistungsumfang, Festpreis und nächste Schritte zusammen.\n\n[Angebot manuell hinzufügen]'),
      'rueckfrage':('Rückfrage zu unserem Projektgespräch','zu unserem letzten Gespräch habe ich noch eine kurze Rückfrage:\n\n[Konkrete offene Frage ergänzen]'),
    }
    subject,content=template[kind]
    body=f'Guten Tag,\n\n{content}\n\nFreundliche Grüße\n[Dein Name / Medienagentur]'
    cur=conn.execute('INSERT INTO mail_drafts(lead_id,draft_type,subject,body,contact_basis) VALUES (?,?,?,?,?)',(
        lead['id'],kind,subject,body,basis))
    conn.commit()
    return {'id':cur.lastrowid,'subject':subject,'body':body,'contact_basis':basis,
            'notice':'Entwurf, nicht versendet. Vor jeder werblichen E-Mail Berechtigung prüfen.'}
