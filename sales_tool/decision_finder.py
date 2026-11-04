"""Human-led decision maker research planning and evidence verification.

This does not crawl search engines or social networks. Search hyperlinks are
opened only by the user and never constitute proof of a person's job or rights.
"""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import quote, urlsplit

from .contacts import ROLE_SUGGESTIONS

VERIFICATION_STATES = ('ungeprueft', 'quelle_geprueft', 'rolle_bestaetigt', 'veraltet')
DECISION_ROLES = ('unbekannt', 'fachlich', 'budget', 'entscheidung')


def research_plan(company: str, offer: str = 'pilot', employees: int = 0) -> dict:
    """Offer-specific search prompts and explicit verification criteria."""
    title = str(company or '').strip()[:160]
    if len(title) < 2:
        title = 'Unternehmen'
    roles = ROLE_SUGGESTIONS.get(offer, ROLE_SUGGESTIONS['pilot'])
    if 0 < int(employees or 0) < 50:
        roles = ('Geschäftsführung', roles[0])
    seen = set()
    targets = []
    for r in roles:
        if r in seen:
            continue
        seen.add(r)
        lookup = f'"{title}" "{r}"'
        search = 'https://www.google.com/search?q=' + quote(lookup, safe='')
        li_query = f'site:linkedin.com/in/ "{title}" "{r}"'
        linkedin_via_search = 'https://www.google.com/search?q=' + quote(li_query, safe='')
        targets.append({'role': r, 'web_search_url': search,
                        'linkedin_search_url': linkedin_via_search,
                        'query': lookup})
    return {
        'targets': targets,
        'checklist': [
            'Aktuellen Arbeitgeber und berufliche Funktion anhand einer konkreten Quelle prüfen.',
            'Fachliche Zuständigkeit nicht mit Budget- oder Entscheidungsvollmacht verwechseln.',
            'Fundstelle, Prüfdatum und wörtlichen Beleg beim Kontakt dokumentieren.',
            'Firmennummer und persönliche Durchwahl getrennt behandeln; keine Kontaktdaten erraten.',
            'Kontaktweg und datenschutzrechtliche Grundlage vor einer Ansprache separat prüfen.',
        ],
        'note': 'Suchlinks öffnen externe Dienste nur manuell. SignalDesk liest LinkedIn nicht aus.'
    }


def validate_verification(data: dict) -> dict:
    """Allow manual evidence review, not automated validation or contact permissions."""
    if not isinstance(data, dict) or set(data) - {
        'verification_status','decision_role','source_url','source_excerpt','linkedin_url','note'
    }:
        raise ValueError('Ungültige Prüfdaten.')
    status = data.get('verification_status', 'ungeprueft')
    role = data.get('decision_role', 'unbekannt')
    if status not in VERIFICATION_STATES or role not in DECISION_ROLES:
        raise ValueError('Ungültige Prüfung oder Entscheiderrolle.')
    out = {'verification_status': status, 'decision_role': role}
    for key, limit in (('source_url',500),('linkedin_url',500),('source_excerpt',500),('note',1000)):
        value=data.get(key,'')
        if not isinstance(value,str) or len(value.strip())>limit:
            raise ValueError('Ungültige Länge oder Typ für '+key)
        out[key]=value.strip()
    for key in ('source_url','linkedin_url'):
        if out[key]:
            u=urlsplit(out[key])
            if u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443):
                raise ValueError('Nur überprüfbare HTTPS-Quellen ohne Zugangsdaten zulässig.')
    if status in ('quelle_geprueft','rolle_bestaetigt'):
        if not out['source_url'] or len(out['source_excerpt']) < 10:
            raise ValueError('Für diese Bestätigung sind Quellen-URL und konkreter Beleg erforderlich.')
    if role=='entscheidung' and status!='rolle_bestaetigt':
        raise ValueError('Entscheidungsbefugnis nur nach bestätigter Rolle kennzeichnen.')
    if status=='veraltet' and role=='entscheidung':
        raise ValueError('Veraltete Quellen bestätigen keine Entscheidungsbefugnis.')
    return out


def save_verification(conn, contact_id: int, values: dict) -> dict:
    contact=conn.execute('''SELECT d.*, l.permission, l.stage FROM decision_contacts d
        JOIN leads l ON l.id=d.lead_id WHERE d.id=?''',(contact_id,)).fetchone()
    if contact is None:
        raise ValueError('Kontakt nicht gefunden.')
    if contact['permission']=='nicht_kontaktieren' or contact['stage']=='gesperrt':
        raise ValueError('Kontakt ist gesperrt. Keine weitere Anreicherung.')
    d=validate_verification(values)
    conn.execute('''UPDATE decision_contacts SET verification_status=?, decision_role=?, source_url=?,
        source_excerpt=?, linkedin_url=?,note=?, verification_date=?,updated_at=datetime('now') WHERE id=?''',
        (d['verification_status'],d['decision_role'],d['source_url'],d['source_excerpt'],
         d['linkedin_url'],d['note'],date.today().isoformat(),contact_id))
    return {'id':contact_id,'verification_status':d['verification_status'],
            'decision_role':d['decision_role'], 'verification_date':date.today().isoformat()}
