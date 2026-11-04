"""Single-URL research flow: one crawl, independent website and contact findings.

Website text is untrusted. A scan is a research aid, never a contact permission.
Never generates unobserved personal contact information or auto-contacts people.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from urllib.parse import urlsplit

from .ai_provider import analyze
from .contacts import role_suggestions
from .decision_finder import research_plan
from .model import connect
from .public_contacts import extract_public_contacts
from .website_analyzer import crawl_site, public_url, same_company_host


def _canonical(value: str) -> str:
    parsed = urlsplit(value)
    host = (parsed.hostname or '').lower().removeprefix('www.')
    return host


def company_guess(url: str, pages: list[dict]) -> str:
    """A provisional label for the lead; never claim this is the registered company name."""
    title = str(pages[0].get('title', '') if pages else '').strip()
    name = re.split(r'\s+[|–—-]\s+', title)[0].strip()[:100]
    if len(name) < 3 or name.casefold() in ('startseite', 'home', 'willkommen', 'homepage'):
        name = _canonical(url)
    return name[:160]


def research(crawl: dict, provider: str = 'rules', model: str = 'qwen3:8b') -> dict:
    analysis = analyze(crawl, provider=provider, model=model)
    best_offer = (analysis['findings'][0]['offer'] if analysis['findings'] else 'pilot')
    public = extract_public_contacts(crawl, offer=best_offer)
    pages = [{'url': p['url'], 'title': p.get('title', '')} for p in crawl['pages']]
    questions = list(dict.fromkeys(f['question'] for f in analysis['findings']))
    # Ask honest discovery questions even if the website yields no explicit needs.
    if len(questions) < 3:
        for q in (
            'Welche Rolle spielt Ihre Website heute bei der Gewinnung neuer Kundenanfragen?',
            'Welche Prozesse rund um Kundenanfragen oder Angebote verursachen intern die meiste Arbeit?',
            'Wer wäre bei Ihnen fachlich und für die Freigabe eines solchen Projekts zuständig?',
        ):
            if q not in questions:
                questions.append(q)
            if len(questions) >= 3:
                break
    return {
        'site': {'url': crawl['source'], 'company_label': company_guess(crawl['source'], crawl['pages']),
                 'pages': pages},
        'audit': {'summary': analysis['summary'], 'findings': analysis['findings'], 'provider': provider,
                  'discarded': analysis.get('discarded', 0)},
        'decision_makers': {'people': public['people'], 'suggested_roles': role_suggestions({'offer':best_offer,'employees':0}),
                            'note': 'Recherchekandidaten – Funktion und Entscheidungsbefugnis bitte manuell verifizieren.',
                            'research_plan': research_plan(company_guess(crawl['source'],crawl['pages']), best_offer)},
        'contact_channels': public['channels'],
        'questions': questions[:5],
        'warnings': (crawl.get('warnings', []) + public['notes'] +
                     ([f"{analysis['discarded']} unbelegte KI-Befunde verworfen."] if analysis.get('discarded') else []))[:20],
    }


def run_job(db_path: str | Path, run_id: int, url: str, provider: str, model: str):
    with connect(db_path) as conn:
        conn.execute("UPDATE quick_scans SET status='running' WHERE id=? AND status='queued'", (run_id,))
        conn.commit()
    try:
        crawl = crawl_site(url, purpose='full')
        result = research(crawl, provider, model)
        with connect(db_path) as conn:
            conn.execute("UPDATE quick_scans SET status='done', result_json=?, finished_at=datetime('now') WHERE id=?",
                         (json.dumps(result, ensure_ascii=False),run_id))
            conn.commit()
    except Exception as exc:
        # No internal traceback or paths in the browser; leave actionable error for expected failures.
        message = str(exc)[:320] if isinstance(exc, ValueError) else 'Technischer Fehler beim Website-Abruf. Serverkonsole prüfen.'
        with connect(db_path) as conn:
            conn.execute("UPDATE quick_scans SET status='failed', error=?,finished_at=datetime('now') WHERE id=?",
                         (message,run_id))
            conn.commit()
        if not isinstance(exc, ValueError):
            print('Quick scan failed:', repr(exc))


def enqueue(db_path, run_id, url, provider, model):
    threading.Thread(target=run_job,args=(db_path,run_id,url,provider,model),daemon=True,
                     name=f'signaldesk-research-{run_id}').start()


def scan_row(row):
    r=dict(row)
    r['result'] = json.loads(r.pop('result_json') or '{}') if r['status']=='done' else None
    return r


def list_scans(conn, limit=25):
    return [dict(r) for r in conn.execute("SELECT id,url,provider,model,status,error,lead_id,created_at,finished_at FROM quick_scans ORDER BY id DESC LIMIT ?", (limit,))]


def import_scan(conn, scan_id: int) -> dict:
    """Bring scan into CRM for human review. No hypothesis is auto-approved.

    Commit belongs to HTTP caller for atomicity. Reuses existing domain lead and
    never alters its rights/stage/confirmed signals.
    """
    scan=conn.execute('SELECT * FROM quick_scans WHERE id=?',(scan_id,)).fetchone()
    if not scan or scan['status']!='done':
        raise ValueError('Keine abgeschlossene Recherche vorhanden.')
    if scan['lead_id']:
        return {'lead_id':scan['lead_id'],'existing':True,'already_imported':True}
    result=json.loads(scan['result_json'])
    url=scan['url']
    host=_canonical(url)
    found=None
    for row in conn.execute('SELECT id,website,permission,stage FROM leads'):
        if row['website'] and _canonical(row['website'])==host:
            found=row
            break
    if found and (found['permission']=='nicht_kontaktieren' or found['stage']=='gesperrt'):
        raise ValueError('Dieser Lead ist gesperrt. Recherche nicht übernehmen.')
    if found:
        lid=found['id']
    else:
        cur=conn.execute('INSERT INTO leads(company,website,stage,permission,offer,next_step) VALUES (?,?,?,?,?,?)',
                         (result['site']['company_label'],url,'recherche','unbekannt',
                          (result['audit']['findings'][0]['offer'] if result['audit']['findings'] else 'pilot'),
                          'Websitebefunde und Zuständigkeiten prüfen; zulässigen Kontaktweg klären'))
        lid=cur.lastrowid
    audit=result['audit']
    cur=conn.execute("INSERT INTO analysis_runs(lead_id,provider,model,status,summary,pages_json,warnings_json,finished_at) VALUES (?,?,?,?,?,?,?,datetime('now'))",
                     (lid,audit['provider'],scan['model'],'done',audit['summary'],
                      json.dumps(result['site']['pages'],ensure_ascii=False),json.dumps(result['warnings'],ensure_ascii=False)))
    aid=cur.lastrowid
    for f in audit['findings']:
        conn.execute('''INSERT INTO findings(run_id,lead_id,category,observation,hypothesis,evidence,source_url,offer,question)
                        VALUES (?,?,?,?,?,?,?,?,?)''', (aid,lid,*(f[k] for k in
                        ('category','observation','hypothesis','evidence','source_url','offer','question'))))
    cur=conn.execute("INSERT INTO contact_research_runs(lead_id,status,pages_json,channels_json,warnings_json,finished_at) VALUES (?,'done',?,?,?,datetime('now'))",
                     (lid,json.dumps(result['site']['pages'],ensure_ascii=False),
                      json.dumps(result['contact_channels'],ensure_ascii=False),json.dumps(result['warnings'],ensure_ascii=False)))
    cid=cur.lastrowid
    for p in result['decision_makers']['people']:
        conn.execute('''INSERT INTO contact_candidates(run_id,lead_id,full_name,job_title,role_hint,priority,business_email,
                        business_phone,phone_type,source_url,evidence) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                     (cid,lid,*(p[k] for k in ('full_name','job_title','role_hint','priority','business_email',
                                             'business_phone','phone_type','source_url','evidence'))))
    conn.execute('UPDATE quick_scans SET lead_id=? WHERE id=?',(lid,scan_id))
    return {'lead_id':lid,'existing':bool(found),'already_imported':False,
            'findings_pending_review':len(audit['findings']),
            'contacts_pending_review':len(result['decision_makers']['people'])}


def demo_report() -> dict:
    """Fictional, clearly labelled offline preview; never persisted or imported."""
    url='https://demo.invalid/'
    home='Unsere Produkte und Leistungen: Produktunterlagen als PDF zum Download. Nutzen Sie das Kontaktformular für Ihre Anfrage.'
    team='Geschäftsführung: Anna Beispiel\nMarketingleitung: Max Muster\nZentrale: 0711 1234567'
    crawl={'source':url, 'warnings':[], 'pages':[
        {'url':url,'title':'FIKTIVE Beispieltechnik GmbH | Produkte','text':home,'raw_text':home,'form_count':1},
        {'url':url+'team','title':'Team (fiktiv)','text':team,'raw_text':team,'form_count':0},
    ]}
    return research(crawl, provider='rules')
