"""Personalisiertes Themenprofil für die regelbasierte Inhaltsrecherche.

Je Datenbank gespeichert; keine globalen Laufzeitvariablen. Ein Profil ändert
weder die technische Website-Bewertung noch die Stellenklassifikation.
"""
from __future__ import annotations

import hashlib
import json

THEMES = {
    'campaign': 'Kampagnen und Anlässe',
    'media': 'Foto und Video',
    'print': 'Print und Produktunterlagen',
    'forms': 'Website und Anfragewege',
    'automation': 'Abläufe und Automatisierung',
    'recruiting': 'Recruiting und Bewerbungen',
    'products': 'Produkt- und Leistungsdarstellung',
}
KEY = 'content_service_profile_v1'


def default_profile():
    return {'name': 'Medien & Digital', 'themes': {k: {'enabled': True, 'keywords': []} for k in THEMES}}


def validate(data):
    if not isinstance(data, dict) or set(data) != {'name', 'themes'}:
        raise ValueError('Profil benötigt name und themes.')
    name, themes = data['name'], data['themes']
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise ValueError('Profilname muss 1–80 Zeichen enthalten.')
    if not isinstance(themes, dict) or set(themes) != set(THEMES):
        raise ValueError('Das Profil muss alle bekannten Themen enthalten.')
    out = {}
    for key in THEMES:
        val = themes[key]
        if not isinstance(val, dict) or set(val) != {'enabled', 'keywords'} or not isinstance(val['enabled'], bool):
            raise ValueError(f'{THEMES[key]}: Aktivierung und Suchbegriffe angeben.')
        words = val['keywords']
        if not isinstance(words, list) or len(words) > 15:
            raise ValueError(f'{THEMES[key]}: höchstens 15 Suchbegriffe angeben.')
        clean = []
        for word in words:
            if not isinstance(word, str) or not 2 <= len(word.strip()) <= 60 or '\n' in word or '\r' in word:
                raise ValueError(f'{THEMES[key]}: Suchbegriffe müssen 2–60 Zeichen lang sein.')
            term = word.strip()
            if term.casefold() not in {w.casefold() for w in clean}:
                clean.append(term)
        out[key] = {'enabled': val['enabled'], 'keywords': clean}
    return {'name': name.strip(), 'themes': out}


def load(conn):
    from ..quality import get_setting
    return validate(get_setting(conn, KEY, default_profile()))


def save(conn, data):
    from ..quality import put_setting
    profile = validate(data)
    put_setting(conn, KEY, profile)
    conn.commit()
    return profile


def fingerprint(profile):
    raw = json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]


def route(h, conn, method, path):
    if path != '/api/research/service-profile':
        return False
    if method == 'GET':
        profile = load(conn)
    elif method == 'POST':
        profile = save(conn, h._body())
    else:
        return False
    h._send(200, {'profile': profile, 'themes': THEMES, 'version': fingerprint(profile)})
    return True
