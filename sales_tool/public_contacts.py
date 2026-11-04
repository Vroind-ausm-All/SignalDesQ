"""Source-led, low-volume research of public business contacts.

No purchased datasets, no email permutation, no private phone inference, no
social-network scraping, no outreach. Results require human review.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from urllib.parse import urlsplit
from .model import connect
from .website_analyzer import crawl_site

NAME = r"[A-ZÄÖÜ][a-zäöüßà-ÿ]+(?:[-'][A-ZÄÖÜ][a-zäöüßà-ÿ]+)?"
NAME_RE = re.compile(rf"\b({NAME}(?:\s+{NAME}){{1,2}})\b")
EMAIL_RE = re.compile(r"(?<![\w.+-])([\w.+-]+@[\w.-]+\.[A-Za-z]{2,})(?![\w.-])")
PHONE_RE = re.compile(r"(?<!\w)((?:\+49|0049|0)(?:[\s./()-]*\d){7,15})(?!\d)")
ROLE_RE = re.compile(r"\b(geschäftsführ\w*|geschäftsleitung|inhaber\w*|gründer\w*|marketing(?:[ -]?leitung|leiter\w*| manager\w*| director|chef\w*)|leitung marketing|head of marketing|cmo|chief marketing officer|it[ -]?leitung|leiter\w* it|cto|chief technology officer|digitalisierungsleitung|head of (?:digital|it)|operations[ -]?(?:leitung|manager)|brand[ -]?(?:manager|leitung|director)|vertriebsleitung)\b", re.I)


def _role(title: str, offer: str) -> tuple[str, int]:
    t = title.casefold()
    if any(x in t for x in ('geschäftsführ', 'geschäftsleitung', 'inhaber', 'gründer')):
        return ('Geschaeftsfuehrung', 85)
    if any(x in t for x in ('marketing','brand','cmo')):
        return ('Marketing / Marke', 90 if offer in ('pilot','conversion','brand') else 60)
    if any(x in t for x in ('it-', 'it ', 'digital','cto','technolog')):
        return ('IT / Digitalisierung', 90 if offer=='portal' else 65)
    if any(x in t for x in ('operations','vertrieb')):
        return ('Betrieb / Vertrieb', 75 if offer=='portal' else 55)
    return ('Rolle unklar', 30)


def _lines(page):
    raw = page.get('raw_text') or page.get('text') or ''
    # Website text is untrusted. Preserve line associations only, never treat as instructions.
    return [re.sub(r'\s+', ' ', line).strip(' \u2022\t|') for line in raw.splitlines() if line.strip()][:700]


def _personal_phone(line: str) -> str:
    # A number must be explicitly marked as a person-specific business line.
    if not re.search(r'\b(?:durchwahl|direkt(?:wahl|nummer)?|telefon\s*direkt)\b',line,re.I):
        return ''
    m = PHONE_RE.search(line)
    return m.group(1).strip() if m else ''


def extract_public_contacts(crawl: dict, offer='pilot') -> dict:
    """Rules produce *candidates*, never verified decision makers.

    A candidate needs an explicit role and a full name in a short adjoining
    segment. Office contact points are separate from a person's direct number.
    """
    people, channels = [], []
    seen_people, seen_channels = set(), set()
    for page in crawl.get('pages', [])[:5]:
        src = page.get('url','')
        if urlsplit(src).scheme != 'https':
            # HTTP pages can be read, but only HTTPS page citations are accepted for storing PII.
            continue
        lines = _lines(page)
        for i,line in enumerate(lines):
            for kind,rx in (('email',EMAIL_RE),('telefon_veroeffentlicht',PHONE_RE)):
                for m in rx.finditer(line):
                    value = m.group(1).strip()
                    if kind=='email' and len(value)>160: continue
                    if kind=='telefon_veroeffentlicht' and not (7<=len(re.sub(r'\D','',value))<=17):continue
                    key = (kind, value.casefold())
                    if key not in seen_channels:
                        seen_channels.add(key)
                        channels.append({'type':kind,'value':value,'source_url':src,
                                         'evidence':line[:350]})
            role_match = ROLE_RE.search(line)
            if not role_match:
                continue
            # Same line and neighboring line only; headers/long paragraphs are too ambiguous.
            options = [(line,0)]
            # Prefer role + name together, else a *name-only* adjacent line;
            # never steal a name from a different person's preceding role line.
            if i+1<len(lines) and len(lines[i+1]) < 90 and not ROLE_RE.search(lines[i+1]):
                options.append((lines[i+1],1))
            if i and len(lines[i-1]) < 90 and not ROLE_RE.search(lines[i-1]):
                options.append((lines[i-1],1))
            matched = None
            for candidate,offset in options:
                if len(candidate)>170:continue
                # Ignore names whose exact span is the role label itself.
                for m in NAME_RE.finditer(candidate):
                    name=m.group(1)
                    if ROLE_RE.search(name):continue
                    if offset and name != candidate.strip():continue
                    if any(q.casefold() in name.casefold() for q in ('Unsere Leistungen','Unsere Kunden','Unser Team','Mehr Erfahren','Kontakt Telefon','Telefon Email')):continue
                    matched=(name,offset)
                    break
                if matched:break
            if not matched:continue
            name, offset=matched
            key=name.casefold()
            if key in seen_people:continue
            seen_people.add(key)
            role_label=role_match.group(1)
            responsibility, priority=_role(role_label,offer)
            # Do not assign general footer address to a named person. Same-line only.
            exact_line = line if name in line else next((x for x,_ in options if name in x), '')
            p_mail = (EMAIL_RE.search(exact_line).group(1) if EMAIL_RE.search(exact_line) else '')
            phone = _personal_phone(exact_line)
            people.append({'full_name':name,'job_title':role_label,'role_hint':responsibility,
                           'priority':priority,'business_email':p_mail,'business_phone':phone,
                           'phone_type':'ausdruecklich_publizierte_durchwahl' if phone else '',
                           'source_url':src,'evidence':line[:350],
                           'status':'ungeprueft'})
    people.sort(key=lambda x:-x['priority'])
    return {'people':people[:30], 'channels':channels[:40],
            'notes':['Personen sind unbestätigte Recherchekandidaten; eine genannte Rolle belegt keine Budgethoheit.',
                     'Zentrale Telefonnummern sind keine persönlichen Durchwahlen.',
                     'Keine Kontaktdaten wurden geraten oder bei einem Datenhändler abgefragt.']}


def run_job(db_path: str | Path, run_id: int, lead_id: int, website: str, offer: str):
    with connect(db_path) as conn:
        conn.execute("UPDATE contact_research_runs SET status='running' WHERE id=?", (run_id,))
        conn.commit()
    try:
        crawl = crawl_site(website, purpose='contacts')
        output = extract_public_contacts(crawl, offer)
        with connect(db_path) as conn:
            conn.execute("""UPDATE contact_research_runs SET status='done', pages_json=?, channels_json=?, warnings_json=?,
                       finished_at=datetime('now') WHERE id=?""",
                       (json.dumps([{'url':p['url'],'title':p.get('title','')} for p in crawl['pages']],ensure_ascii=False),
                        json.dumps(output['channels'],ensure_ascii=False),json.dumps(crawl.get('warnings',[])+output['notes'],ensure_ascii=False),run_id))
            for p in output['people']:
                conn.execute("""INSERT INTO contact_candidates (run_id,lead_id,full_name,job_title,role_hint,priority,
                 business_email,business_phone,phone_type,source_url,evidence) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                 (run_id,lead_id, *(p[k] for k in ('full_name','job_title','role_hint','priority','business_email','business_phone','phone_type','source_url','evidence'))))
            conn.commit()
    except Exception as exc:
        msg=str(exc)[:280] if isinstance(exc,ValueError) else 'Technischer Recherchefehler; Serverkonsole prüfen.'
        with connect(db_path) as conn:
            conn.execute("UPDATE contact_research_runs SET status='failed', error=?, finished_at=datetime('now') WHERE id=?",(msg,run_id))
            conn.commit()
        if not isinstance(exc,ValueError): print('Contact research error:',repr(exc))


def enqueue(db_path,run_id,lead_id,website,offer):
    threading.Thread(target=run_job,args=(db_path,run_id,lead_id,website,offer),daemon=True,
                     name=f'public-contact-research-{run_id}').start()


def list_runs(conn,lead_id):
    rows=[dict(r) for r in conn.execute('SELECT * FROM contact_research_runs WHERE lead_id=? ORDER BY id DESC LIMIT 10',(lead_id,))]
    for r in rows:
        for k in ('pages','channels','warnings'):
            r[k]=json.loads(r.pop(k+'_json') or '[]')
        r['people']=[dict(p) for p in conn.execute('SELECT * FROM contact_candidates WHERE run_id=? ORDER BY priority DESC,id',(r['id'],))]
    return rows


def review_candidate(conn, candidate_id, decision):
    if decision not in ('accept','reject'):
        raise ValueError('Entscheidung muss accept oder reject sein.')
    r=conn.execute('SELECT * FROM contact_candidates WHERE id=?',(candidate_id,)).fetchone()
    if not r:raise ValueError('Recherchekandidat nicht gefunden.')
    if r['status']!='ungeprueft':raise ValueError('Dieser Recherchekandidat wurde bereits bearbeitet.')
    lead=conn.execute('SELECT permission,stage FROM leads WHERE id=?',(r['lead_id'],)).fetchone()
    if not lead or lead['permission']=='nicht_kontaktieren' or lead['stage']=='gesperrt':
        raise ValueError('Dieser Lead ist gesperrt. Keine Übernahme möglich.')
    status='abgelehnt' if decision=='reject' else 'freigegeben'
    if decision=='accept':
        exists=conn.execute('SELECT id FROM decision_contacts WHERE lead_id=? AND lower(full_name)=lower(?)',(r['lead_id'],r['full_name'])).fetchone()
        if exists:raise ValueError('Diese Person ist bereits im CRM vorhanden. Keine Dublette angelegt.')
        conn.execute('''INSERT INTO decision_contacts (lead_id,full_name,job_title,decision_role,source_url,
                  note,business_phone,phone_type,data_provider,business_email)
                  VALUES (?,?,?,?,?,?,?,?,?,?)''', (r['lead_id'],r['full_name'],r['job_title'],'unbekannt',r['source_url'],
                  'Quelle manuell freigegeben; Entscheidungsbefugnis noch nicht bestätigt. '+r['evidence'][:300],
                  r['business_phone'],r['phone_type'],'eigene_recherche',r['business_email']))
    conn.execute("UPDATE contact_candidates SET status=? WHERE id=?",(status,candidate_id))
    return {'status':status}
