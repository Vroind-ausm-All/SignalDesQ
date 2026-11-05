"""Human-reviewed B2B contact identities. No commercial data provider."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

ROLE_SUGGESTIONS = {
    "pilot": ("Geschäftsführung", "Marketingleitung"),
    "conversion": ("Marketingleitung", "Geschäftsführung"),
    "brand": ("Marketingleitung / Brand Management", "Geschäftsführung"),
    "portal": ("IT- / Digitalisierungsleitung", "Operations-Leitung / Geschäftsführung"),
    "automation": ("Operations-Leitung / Fachbereich", "IT- / Digitalisierungsleitung"),
}
ROLES = ("fachlich", "budget", "entscheidung", "unbekannt")


def role_suggestions(lead):
    roles = ROLE_SUGGESTIONS.get(lead['offer'], ROLE_SUGGESTIONS['pilot'])
    if 0 < int(lead['employees'] or 0) < 50:
        return ("Geschäftsführung", roles[0] if roles[0] != "Geschäftsführung" else roles[1])
    return roles


def validate_contact(data):
    if not isinstance(data, dict):
        raise ValueError('Kontaktdaten müssen ein Objekt sein.')
    fields = ('full_name','job_title','decision_role','source_url','linkedin_url','note')
    if set(data) - set(fields):
        raise ValueError('Unbekannte Kontaktfelder.')
    out = {k: str(data.get(k, '') or '').strip() for k in fields}
    if not 3 <= len(out['full_name']) <= 160:
        raise ValueError('Bitte einen vollständigen Namen (3–160 Zeichen) angeben.')
    if out['decision_role'] not in ROLES:
        raise ValueError('Ungültige Entscheidungsrolle.')
    for f, limit in [('job_title',160),('note',1000)]:
        if len(out[f]) > limit: raise ValueError(f'{f} zu lang.')
    for f in ('source_url','linkedin_url'):
        if len(out[f]) > 500: raise ValueError('Quelle ist zu lang.')
        if out[f]:
            u = urlsplit(out[f])
            if u.scheme != 'https' or not u.hostname or u.username or u.password:
                raise ValueError('Nur HTTPS-Quellen ohne Zugangsdaten zulässig.')
    if not out['source_url'] and not out['linkedin_url']:
        raise ValueError('Bitte eine öffentliche berufliche Quelle angeben.')
    return out


def domain_of(website):
    parsed = urlsplit((website or '').strip())
    host = (parsed.hostname or '').lower()
    if parsed.scheme not in ('http','https') or not host or not re.fullmatch(r'[a-z0-9.-]+',host):
        return ''
    return host[4:] if host.startswith('www.') else host


