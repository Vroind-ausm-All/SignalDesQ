"""Strukturierte Firmenangaben (Sprint 2): JSON-LD, Microdata, OpenGraph – nur Standardbibliothek.

extruct (Plan: P0) wurde geprüft: ``pip install extruct`` scheitert unter Python 3.13 an der Abhängigkeit jstyleson
(kein Wheel, Build-Fehler). Deshalb eine eigene, kleine Implementierung für die Typen, die SignalDesk braucht:
Organization/LocalBusiness (Name, Telefon, E-Mail, USt-IdNr., Adresse, Website, Profile) und JobPosting.
Website-Inhalte sind nicht vertrauenswürdig: nur json.loads mit Größenbremse, nichts wird ausgeführt.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from html.parser import HTMLParser

MAX_JSONLD = 200_000
MAX_ITEMS = 50
ORG_TYPES = {'organization', 'corporation', 'localbusiness', 'professionalservice', 'store', 'onlinebusiness', 'ngo',
             'educationalorganization', 'medicalorganization', 'governmentorganization', 'sportsorganization', 'newsmediaorganization',
             'homeandconstructionbusiness', 'automotivebusiness', 'foodestablishment', 'lodgingbusiness', 'legalservice',
             'accountingservice', 'financialservice', 'itcompany', 'organisation'}
LD_RE = re.compile(r'<script[^>]+type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)


def _types(obj):
    t = obj.get('@type') or obj.get('type') or ''
    t = t if isinstance(t, list) else [t]
    return {str(x).rsplit('/', 1)[-1].lower() for x in t if x}


def _walk(obj, out, depth=0):
    if depth > 6 or len(out) >= MAX_ITEMS:
        return
    if isinstance(obj, list):
        for x in obj:
            _walk(x, out, depth + 1)
    elif isinstance(obj, dict):
        if '@graph' in obj:
            _walk(obj['@graph'], out, depth + 1)
        if _types(obj):
            out.append(obj)
        for k, v in obj.items():
            if k not in ('@graph',) and isinstance(v, (dict, list)) and k in ('mainEntity', 'publisher', 'author', 'hiringOrganization', 'itemListElement', 'about'):
                _walk(v, out, depth + 1)


def jsonld_blocks(page_html):
    items, warnings = [], []
    for raw in LD_RE.findall(page_html or '')[:20]:
        raw = raw.strip()
        if len(raw) > MAX_JSONLD:
            warnings.append('JSON-LD-Block zu groß – ausgelassen.')
            continue
        raw = re.sub(r'^\s*(<!--|<!\[CDATA\[)|(-->|\]\]>)\s*$', '', raw).strip()
        try:
            data = json.loads(raw)
        except ValueError:
            try:  # häufig: HTML-Entities oder abschließende Kommata
                data = json.loads(re.sub(r',\s*([}\]])', r'\1', html_lib.unescape(raw)))
            except ValueError:
                warnings.append('Ungültiges JSON-LD – ausgelassen.')
                continue
        _walk(data, items)
    return items, warnings


class _Microdata(HTMLParser):
    """Einfache Microdata-Auswertung: itemscope/itemtype/itemprop (Text, content, href)."""
    VOID = {'meta', 'link', 'img', 'br', 'hr', 'input', 'source'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.items, self.prop_stack, self.og = [], [], [], {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'meta' and (a.get('property') or '').startswith('og:') and a.get('content'):
            self.og[a['property'][3:]] = a['content'][:500]
        prop = a.get('itemprop')
        if 'itemscope' in a:
            item = {'@type': (a.get('itemtype') or '').rsplit('/', 1)[-1], '_tag': tag}
            if prop and self.stack:
                self.stack[-1][0].setdefault(prop, item)
            self.stack.append((item, tag))
            if not prop and len(self.items) < MAX_ITEMS:
                self.items.append(item)
            return
        if prop and self.stack:
            value = a.get('content') or a.get('href') or a.get('src') or a.get('datetime')
            if value is not None:
                self.stack[-1][0].setdefault(prop, value[:500])
            elif tag not in self.VOID:
                self.prop_stack.append([prop, tag, [], self.stack[-1][0]])

    def handle_endtag(self, tag):
        if self.prop_stack and self.prop_stack[-1][1] == tag:
            prop, _, parts, owner = self.prop_stack.pop()
            owner.setdefault(prop, re.sub(r'\s+', ' ', ''.join(parts)).strip()[:500])
        if self.stack and self.stack[-1][1] == tag:
            self.stack.pop()

    def handle_data(self, data):
        for entry in self.prop_stack:
            entry[2].append(data)


def _text(v):
    if isinstance(v, list):
        v = next((x for x in v if x), '')
    if isinstance(v, dict):
        v = v.get('name') or v.get('@id') or ''
    return re.sub(r'\s+', ' ', html_lib.unescape(str(v or ''))).strip()[:300]


def _address(a):
    if isinstance(a, list):
        a = next((x for x in a if isinstance(x, dict)), a[0] if a else '')
    if isinstance(a, str):
        return {'street': '', 'zip': '', 'city': '', 'country': '', 'raw': _text(a)}
    if not isinstance(a, dict):
        return {}
    country = a.get('addressCountry')
    return {'street': _text(a.get('streetAddress')), 'zip': _text(a.get('postalCode')), 'city': _text(a.get('addressLocality')),
            'country': _text(country.get('name') if isinstance(country, dict) else country)}


def organization(obj, method):
    addr = _address(obj.get('address'))
    same = obj.get('sameAs') or []
    same = same if isinstance(same, list) else [same]
    email = _text(obj.get('email')).replace('mailto:', '')
    return {'type': next(iter(_types(obj)), 'organization'), 'name': _text(obj.get('legalName') or obj.get('name')),
            'telephone': _text(obj.get('telephone')), 'email': email, 'vat_id': re.sub(r'\s+', '', _text(obj.get('vatID') or obj.get('taxID'))),
            'url': _text(obj.get('url')), 'street': addr.get('street', ''), 'zip': addr.get('zip', ''), 'city': addr.get('city', ''),
            'country': addr.get('country', ''), 'same_as': [str(x)[:200] for x in same if x][:10], 'method': method}


def jobposting(obj, method):
    loc = obj.get('jobLocation')
    loc = loc[0] if isinstance(loc, list) and loc else loc
    addr = _address(loc.get('address')) if isinstance(loc, dict) else {}
    org = obj.get('hiringOrganization')
    return {'title': _text(obj.get('title')), 'date_posted': _text(obj.get('datePosted'))[:10], 'valid_through': _text(obj.get('validThrough'))[:10],
            'employment_type': _text(obj.get('employmentType')), 'organization': _text(org.get('name') if isinstance(org, dict) else org),
            'city': addr.get('city', ''), 'zip': addr.get('zip', ''), 'remote': 'TELECOMMUTE' in _text(obj.get('jobLocationType')).upper(),
            'description': re.sub(r'<[^>]+>', ' ', _text(obj.get('description'))), 'method': method}


def extract(page_html, url=''):
    """→ {'organizations': [...], 'jobpostings': [...], 'opengraph': {...}, 'counts': {...}, 'warnings': [...], 'engine': 'stdlib'}"""
    items, warnings = jsonld_blocks(page_html)
    md = _Microdata()
    try:
        md.feed(page_html or '')
    except Exception:  # noqa: BLE001 – kaputtes HTML darf nichts stoppen
        warnings.append('Microdata nicht auswertbar.')
    orgs, jobs = [], []
    for method, pool in (('jsonld', items), ('microdata', md.items)):
        for obj in pool:
            t = _types(obj)
            if t & ORG_TYPES or any(x.endswith('business') for x in t):
                o = organization(obj, method)
                if o['name'] or o['telephone'] or o['email']:
                    orgs.append(o)
            if 'jobposting' in t:
                j = jobposting(obj, method)
                if j['title']:
                    jobs.append(j)
    return {'organizations': orgs[:10], 'jobpostings': jobs[:40], 'opengraph': md.og,
            'counts': {'jsonld': len(items), 'microdata': len(md.items)}, 'warnings': warnings, 'engine': 'stdlib'}
