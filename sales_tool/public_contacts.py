"""Source-led, low-volume research of public business contacts.

No purchased datasets, no email permutation, no private phone inference, no
social-network scraping, no outreach. Results require human review.
"""
from __future__ import annotations

import json
import re
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
    """Nicht leere Zeilen mit Lage im Originaltext: [(bereinigte Zeile, Anfang, Ende)] – für Belege mit Textspanne (R2.3)."""
    raw = page.get('raw_text') or page.get('text') or ''
    # Website text is untrusted. Preserve line associations only, never treat as instructions.
    out, pos = [], 0
    for line in raw.splitlines(keepends=True):
        clean = re.sub(r'\s+', ' ', line).strip(' \u2022\t|')
        if clean:
            out.append((clean, pos, pos + len(line)))
        pos += len(line)
        if len(out) >= 700:
            break
    return out


def _personal_phone(line: str) -> str:
    # A number must be explicitly marked as a person-specific business line.
    if not re.search(r'\b(?:durchwahl|direkt(?:wahl|nummer)?|telefon\s*direkt)\b',line,re.I):
        return ''
    m = PHONE_RE.search(line)
    return m.group(1).strip() if m else ''


RULES_VERSION = 'regeln-personen-v2'


def _rule_refs(raw, src, chash, name, role_label, mail, phone, a, b):
    """Belege v2 für einen Regel-Fund: wörtlich im Originaltext zwischen a und b (Rollenzeile ± Nachbarzeile)."""
    from .research import evidence as ev
    meta = {'chash': chash}
    refs = {'full_name': ev.text_ref('full_name', name, raw, src, RULES_VERSION, start_hint=a, end_hint=b, **meta),
            'job_title': ev.text_ref('job_title', role_label, raw, src, RULES_VERSION, start_hint=a, end_hint=b, **meta)}
    if mail:
        refs['business_email'] = ev.text_ref('business_email', mail, raw, src, RULES_VERSION, start_hint=a, end_hint=b, **meta)
    if phone:
        refs['business_phone'] = ev.text_ref('business_phone', phone, raw, src, RULES_VERSION, start_hint=a, end_hint=b, **meta)
    return {k: v for k, v in refs.items() if v}


def _with_role(person, offer):
    from .research import roles
    norm = roles.normalize(person['job_title'])
    responsibility, priority = _role(person['job_title'], offer)
    if norm and responsibility == 'Rolle unklar':
        responsibility, priority = norm['label'], 40 if norm['level'] == 'fach' else 55
    person.update({'role_hint': responsibility, 'priority': priority, 'role_key': norm['role'] if norm else 'unklar',
                   'department': norm['department'] if norm else 'unklar', 'role_level': norm['level'] if norm else ''})
    return person


def extract_public_contacts(crawl: dict, offer='pilot') -> dict:
    """Rules produce *candidates*, never verified decision makers.

    R2.1: strukturierte Personen (JSON-LD, Microdata, Tabellen, Karten – ``page['persons']`` aus dem Abruf) zuerst,
    die Zeilenregeln als Rückfall. A candidate needs an explicit role and a full name in a short adjoining
    segment, both with evidence v2 (Fundstelle). Office contact points are separate from a person's direct number.
    """
    from .research import evidence as ev
    from .research import roles
    from .research.extractors.persons import business_email
    people, channels = [], []
    seen_people, seen_channels = set(), set()
    dropped = 0
    for page in crawl.get('pages', [])[:5]:
        src = page.get('url','')
        if urlsplit(src).scheme != 'https':
            # HTTP pages can be read, but only HTTPS page citations are accepted for storing PII.
            continue
        chash = page.get('content_hash') or ''
        for sp in page.get('persons') or []:
            key = sp['full_name'].casefold()
            if key in seen_people or not (sp.get('evidence_refs', {}).get('full_name') and sp['evidence_refs'].get('job_title')):
                continue
            seen_people.add(key)
            phone = sp.get('business_phone', '')
            people.append(_with_role({'full_name': sp['full_name'], 'job_title': sp['job_title'], 'business_email': sp.get('business_email', ''),
                                      'business_phone': phone, 'phone_type': 'ausdruecklich_publizierte_durchwahl' if phone else '',
                                      'employer': sp.get('employer', ''), 'method': sp['method'], 'source_url': src,
                                      'evidence': sp['evidence'][:350], 'evidence_refs': sp['evidence_refs'],
                                      'locator_group': sp.get('locator_group', {}), 'status': 'kandidat'}, offer))
        raw = page.get('raw_text') or page.get('text') or ''
        if not chash:
            chash = ev.content_hash(raw)
        lines = _lines(page)
        for i,(line,l_start,l_end) in enumerate(lines):
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
            if not role_match or roles.is_quote(line):  # R2.2: Zitate/Kundenstimmen nennen meist Personen anderer Firmen
                continue
            # Same line and neighboring line only; headers/long paragraphs are too ambiguous.
            options = [(line,0,l_start,l_end)]
            # Prefer role + name together, else a *name-only* adjacent line;
            # never steal a name from a different person's preceding role line.
            if i+1<len(lines) and len(lines[i+1][0]) < 90 and not ROLE_RE.search(lines[i+1][0]):
                options.append((lines[i+1][0],1,lines[i+1][1],lines[i+1][2]))
            if i and len(lines[i-1][0]) < 90 and not ROLE_RE.search(lines[i-1][0]):
                options.append((lines[i-1][0],1,lines[i-1][1],lines[i-1][2]))
            matched = None
            for candidate,offset,_a,_b in options:
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
            role_label=role_match.group(1)
            # Do not assign general footer address to a named person. Same-line only.
            exact_line = line if name in line else next((x for x,*_ in options if name in x), '')
            p_mail = (EMAIL_RE.search(exact_line).group(1) if EMAIL_RE.search(exact_line) else '')
            if p_mail and not business_email(p_mail, src):
                p_mail = ''  # fremde Domain (z. B. Freemail) – mögliche Privatadresse, nicht übernehmen
            phone = _personal_phone(exact_line)
            a = min(o[2] for o in options); b = max(o[3] for o in options)
            refs = _rule_refs(raw, src, chash, name, role_label, p_mail, phone, a, b)
            if not (refs.get('full_name') and refs.get('job_title')):
                dropped += 1  # nicht wörtlich im Originaltext auffindbar – kein Beleg, kein Kandidat
                continue
            seen_people.add(key)
            people.append(_with_role({'full_name':name,'job_title':role_label,
                           'business_email':p_mail if refs.get('business_email') else '','business_phone':phone if refs.get('business_phone') else '',
                           'phone_type':'ausdruecklich_publizierte_durchwahl' if phone and refs.get('business_phone') else '',
                           'employer':'','method':'regel','source_url':src,'evidence':line[:350],'evidence_refs':refs,
                           'locator_group':{'kind':'text','basis':'raw_text','start':a,'end':b},
                           'status':'kandidat'}, offer))
    from .research.extractors import nlp
    if nlp.enabled():  # R2.5: optional, Standard aus – nur zusätzliche Vorschläge mit Beleg, nie bestätigt
        for page in crawl.get('pages', [])[:5]:
            src = page.get('url', '')
            if urlsplit(src).scheme != 'https':
                continue
            raw = page.get('raw_text') or page.get('text') or ''
            for sp in nlp.persons(raw, src, page.get('content_hash') or ev.content_hash(raw)):
                if sp['full_name'].casefold() in seen_people:
                    continue
                seen_people.add(sp['full_name'].casefold())
                people.append(_with_role({**sp, 'phone_type': '', 'source_url': src, 'status': 'kandidat'}, offer))
    people.sort(key=lambda x:-x['priority'])
    notes = ['Personen sind unbestätigte Recherchekandidaten; eine genannte Rolle belegt keine Budgethoheit.',
             'Zentrale Telefonnummern sind keine persönlichen Durchwahlen.',
             'Keine Kontaktdaten wurden geraten oder bei einem Datenhändler abgefragt.']
    if dropped:
        notes.append(f'{dropped} Fund(e) ohne wörtliche Fundstelle verworfen.')
    return {'people':people[:30], 'channels':channels[:40], 'notes':notes}


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
            from .candidates import store_all
            store_all(conn, run_id, lead_id, output['people'])  # R2.4: Sperre, Beleg, Frist – nie direkt ins CRM
            conn.commit()
    except Exception as exc:
        msg=str(exc)[:280] if isinstance(exc,ValueError) else 'Technischer Recherchefehler; Serverkonsole prüfen.'
        with connect(db_path) as conn:
            conn.execute("UPDATE contact_research_runs SET status='failed', error=?, finished_at=datetime('now') WHERE id=?",(msg,run_id))
            conn.commit()
        if not isinstance(exc,ValueError): print('Contact research error:',repr(exc))


def enqueue(db_path,run_id,lead_id,website,offer):
    """2.0.0-dev36 (M23): als Auftrag im gemeinsamen System statt eigenem Thread – setzt nach einem Neustart fort."""
    from . import bg_jobs
    bg_jobs.submit(db_path, 'ansprechpartner', run_id, f'Öffentliche Ansprechpartner: {website}', website,
                   {'lead_id': lead_id, 'website': website, 'offer': offer})


def _job_contacts(db_path, payload, ctx):
    from . import bg_jobs
    bg_jobs.still_open(db_path, 'ansprechpartner', payload['run_id'])
    run_job(db_path, payload['run_id'], payload['lead_id'], payload['website'], payload['offer'])
    return bg_jobs.finished(db_path, 'ansprechpartner', payload['run_id'])


def _register():
    from .research import jobs
    jobs.handler('ansprechpartner')(_job_contacts)


_register()


def list_runs(conn,lead_id):
    from .candidates import view_row
    rows=[dict(r) for r in conn.execute('SELECT * FROM contact_research_runs WHERE lead_id=? ORDER BY id DESC LIMIT 10',(lead_id,))]
    for r in rows:
        for k in ('pages','channels','warnings'):
            r[k]=json.loads(r.pop(k+'_json') or '[]')
        r['people']=[view_row(p) for p in conn.execute('SELECT * FROM contact_candidates WHERE run_id=? ORDER BY priority DESC,id',(r['id'],))]
    return rows


def review_candidate(conn, candidate_id, decision, confirm_conflict=False):
    """R2.4: Sichtung über ``candidates.review`` (Sperre, Beleg v2, kein Kontakt ohne Freigabe)."""
    from .candidates import review
    return review(conn, candidate_id, decision, confirm_conflict)
