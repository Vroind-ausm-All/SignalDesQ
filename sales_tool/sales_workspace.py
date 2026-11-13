"""Local-first daily sales workflow & productized fixed-scope proposals.

Never sends email, places calls or syncs external calendars. All pricing inputs are
internal, while the customer-facing proposal always displays a complete fixed price.
"""
from __future__ import annotations

import datetime as dt
import json
import re

# 2.0.0-dev16 (Produktreview M12): Pakete (PACKAGES, PACKAGE_DETAILS) und Zusatzleistungen (ADDONS) des früheren
# Paket-Rechners sind im zentralen Katalog (catalog.py) aufgegangen. Preise kommen ausschließlich von dort;
# gespeicherte Angebote behalten ihren Text- und Preisstand.
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
    from .offer_flow import init_offer_flow
    init_offer_flow(conn)  # 2.0.0-dev17: Freigabe, Versand und Entscheidung mit Zeitpunkt, Weg und Stand
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
    if not isinstance(data,dict) or set(data)-{'lead_id','outcome','notes','legal_note','callback_date','slot'}:
        raise ValueError('Ungültige Anrufdaten.')
    lead=_lead(conn,data.get('lead_id'))
    outcome=data.get('outcome')
    if outcome not in CALL_OUTCOMES: raise ValueError('Ungültiges Gesprächsergebnis.')
    notes=_optional_text(data,'notes')
    legal=_optional_text(data,'legal_note',1000)
    callback=_valid_date(_optional_text(data,'callback_date',10))
    follow=None
    from .workday import assert_contact_allowed, after_call
    if outcome!='widerspruch':  # v1.18: Widerspruch lässt sich immer dokumentieren, alles andere nicht bei Sperre
        assert_contact_allowed(conn,lead,'Gespräch dokumentieren')
    if outcome=='rueckruf_vereinbart' and (not callback or not notes):
        raise ValueError('Vereinbarten Rückruf mit Datum und Gesprächsnotiz belegen.')
    from .qualification import SLOTS, MISSED, slot_of, after_missed_call
    slot=data.get('slot') or slot_of()  # 2.0.0-dev2: Zeitfenster des Versuchs (für den nächsten Versuch zu anderer Tageszeit)
    if slot not in SLOTS: raise ValueError('Ungültiges Zeitfenster.')
    cur=conn.execute('INSERT INTO calls(lead_id,outcome,notes,legal_note,callback_date,slot) VALUES (?,?,?,?,?,?)',(lead['id'],outcome,notes,legal,callback,slot))
    if outcome=='widerspruch':
        conn.execute("UPDATE leads SET permission='nicht_kontaktieren',stage='gesperrt',next_step='',next_date='',updated_at=datetime('now') WHERE id=?",(lead['id'],))
        from .company_data import suppress_lead
        suppress_lead(conn,lead['id'],'Widerspruch im Gespräch')
    elif outcome=='rueckruf_vereinbart':
        conn.execute('INSERT INTO tasks (lead_id,title,due_date) VALUES (?,?,?)',(lead['id'],'Vereinbarten Rückruf prüfen: '+notes[:100],callback))
    elif outcome in MISSED:
        follow=after_missed_call(conn,lead['id'])  # nicht erreicht: neuer Versuch bzw. Kanalwechsel statt Sackgasse
    else:
        after_call(conn,lead['id'],outcome)
    conn.commit()
    return {'id':cur.lastrowid,'saved':True,'blocked':outcome=='widerspruch','follow_up':follow}


def create_meeting(conn,data):
    if not isinstance(data,dict) or set(data)-{'lead_id','title','starts_at','duration_min','location','notes','opportunity_id'}:
        raise ValueError('Ungültige Termindaten.')
    lead=_lead(conn,data.get('lead_id'))
    from .workday import assert_contact_allowed, after_meeting_created
    assert_contact_allowed(conn,lead,'Termin eintragen')
    title=_required_text(data,'title',180)
    when=_required_text(data,'starts_at',16)
    try: dt.datetime.strptime(when,'%Y-%m-%dT%H:%M')
    except ValueError as exc: raise ValueError('Termin als YYYY-MM-DDTHH:MM angeben.') from exc
    if type(data.get('duration_min',30)) is not int or not 15<=data.get('duration_min',30)<=180:
        raise ValueError('Termindauer 15–180 Minuten.')
    from .chances import open_chances, for_new_offer, advance
    # 2.0.0-dev18: Termin gehört zur gewählten Chance, sonst zur einzigen offenen; ohne offene Chance ist er ein Firmentermin
    opened=open_chances(conn,lead['id'])
    chance=for_new_offer(conn,lead['id'],data.get('opportunity_id')) if data.get('opportunity_id') not in (None,'') else (opened[0]['id'] if len(opened)==1 else None)
    if chance is None and len(opened)>1:
        raise ValueError('Diese Firma hat mehrere offene Chancen – bitte auswählen, zu welcher der Termin gehört.')
    cur=conn.execute('INSERT INTO meetings(lead_id,title,starts_at,duration_min,location,notes,opportunity_id) VALUES (?,?,?,?,?,?,?)',(
        lead['id'],title,when,data.get('duration_min',30),_optional_text(data,'location',300),_optional_text(data,'notes',2000),chance))
    after_meeting_created(conn,lead['id'],when)
    advance(conn,chance,'termin')
    conn.commit()
    return {'id':cur.lastrowid,'saved':True,'opportunity_id':chance}


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


def quote_preview(conn, data):
    """Früherer Paket-Rechner ({package, addons}) – rechnet seit 2.0.0-dev16 mit dem zentralen Katalog."""
    from .catalog import legacy_payload
    from .pricing import build_quote
    return build_quote(conn, legacy_payload(data))


def make_proposal(conn,data):
    if not isinstance(data,dict) or 'lead_id' not in data: raise ValueError('Lead-ID fehlt.')
    lead=_lead(conn,data['lead_id'])
    from .workday import assert_contact_allowed, after_proposal, need_status
    assert_contact_allowed(conn,lead,'Angebot erstellen')
    payload={k:v for k,v in data.items() if k not in ('lead_id','opportunity_id')}
    from .pricing import build_quote
    # Sprint D: Baukasten mit Positionen; ältere Aufrufe mit Paket werden über den zentralen Katalog übersetzt (dev16)
    proposal=build_quote(conn,payload) if 'positions' in payload else quote_preview(conn,payload)
    from .chances import for_new_offer
    # 2.0.0-dev18: jedes Angebot gehört zu einer Chance (gewählt, die einzige offene oder eine neue)
    chance=for_new_offer(conn,lead['id'],data.get('opportunity_id'),proposal['customer']['project_label'])
    if proposal['customer'].get('package') not in (None,'','baukasten'):
        conn.execute("UPDATE opportunities SET offer=? WHERE id=? AND offer=''",(proposal['customer']['package'],chance))
    from .accounting import _next_number
    issued=dt.date.today()
    number=_next_number(conn,'AN',issued.year)
    valid_until=(issued+dt.timedelta(days=OFFER_VALID_DAYS)).isoformat()
    proposal['customer'].update({'customer_company':lead['company'],'offer_number':number,
                                 'offer_date':issued.isoformat(),'valid_until':valid_until})
    ns=need_status(conn,lead['id'],chance)
    proposal['internal']['need_confirmed_at']=ns['confirmed_at']  # intern: Freigabegrundlage, nie im Kundendokument
    from .briefing import snapshot
    proposal['internal']['briefing']=snapshot(conn,chance)  # 2.0.0-dev20: Angaben, auf denen das Angebot beruht (intern)
    cur=conn.execute('INSERT INTO proposals(lead_id,internal_json,customer_json,number,valid_until,opportunity_id) VALUES (?,?,?,?,?,?)',(
        lead['id'],json.dumps(proposal['internal'],ensure_ascii=False),json.dumps(proposal['customer'],ensure_ascii=False),number,valid_until,chance))
    after_proposal(conn,lead['id'],number)
    conn.commit()
    return {'id':cur.lastrowid,'status':'entwurf','number':number,'need_confirmed':bool(ns['confirmed']),'opportunity_id':chance,**proposal}


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


def customer_markdown(customer,release=None):
    """Kundendokument. Ohne Freigabe (2.0.0-dev17, M35) trägt es sichtbar „Entwurf“; die Versandfassung nennt ihren Stand."""
    def safe(s): return re.sub(r'[\r\n]+',' ',str(s)).strip()
    lines=[f"# Angebot: {safe(customer['project_label'])}"]
    if release and not release.get('changed'):
        lines.append(f"*Versandfassung · Stand {safe(release['stand'])} · freigegeben am {safe(release['released_at'])}*")
    else:
        lines.append('**ENTWURF – nicht zum Versand freigegeben.**')
    lines.append(f"**An:** {safe(customer.get('customer_company',''))}")
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
              *([f"- Korrekturschleifen: {customer['revision_rounds']}"] if customer.get('revision_rounds') is not None else
                [f"- Korrekturschleifen: {safe(customer['revision_note'])}"] if customer.get('revision_note') else []),
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
              '', '## Hinweise',safe(customer['guarantee'])]
    if release and not release.get('changed'):
        lines.append(f"Dieses Angebot ist bis {safe(customer.get('valid_until') or 'zum genannten Datum')} gültig. Stand {safe(release['stand'])}.")
    else:
        lines.append('Dieses Dokument ist ein Angebotsentwurf. Kundendaten, Fristen, Vertrags- und Steuerangaben vor Versand prüfen.')
    return '\n'.join(lines)+'\n'


def create_mail_draft(conn,data):
    if not isinstance(data,dict) or set(data)-{'lead_id','draft_type','contact_basis'}:
        raise ValueError('Ungültige Entwurfsdaten.')
    lead=_lead(conn,data.get('lead_id'))
    kind=data.get('draft_type')
    if kind not in DRAFT_TYPES: raise ValueError('Ungültige Vorlage.')
    from .workday import assert_contact_allowed
    assert_contact_allowed(conn,lead,'Kontaktvorlage erstellen')  # v1.18: auch Sperrliste (Domain/Name/E-Mail)
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
