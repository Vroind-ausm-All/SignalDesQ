"""Einheitliche Belege (Sprint 2) und Belegvalidator.

Regel aus dem Masterplan: Ein Fakt gilt nur, wenn er im abrufbaren Originaltext nachweisbar ist. Der Validator gilt für
jede Herkunft – Regeln, strukturierte Daten oder ein Sprachmodell: Wert UND Auszug müssen im Originaltext stehen,
sonst wird der Wert verworfen (bleibt leer/None). Es werden keine Werte erdacht oder „verbessert“.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass


@dataclass
class Evidence:
    field: str
    value: str
    source_url: str
    evidence: str          # Auszug aus dem Originaltext
    method: str            # z. B. regel:impressum-v1, jsonld, microdata, manuell, ki
    confidence: str = 'source_observed'
    review_status: str = 'unverified'
    checked_at: str = ''
    content_hash: str = ''

    def as_dict(self):
        return asdict(self)


def now():
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def content_hash(data):
    if isinstance(data, str):
        data = data.encode('utf-8', 'replace')
    return 'sha256:' + hashlib.sha256(data or b'').hexdigest()


def _norm(text):
    t = unicodedata.normalize('NFKC', str(text or '')).casefold()
    t = t.replace('ß', 'ss').replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', t).strip()


def _digits(text):
    return re.sub(r'\D', '', str(text or ''))


def found_in(value, source_text, kind=''):
    """Steht der Wert im Originaltext? Telefonnummern ziffernweise (+49/0-Vorwahl gleichwertig), Rest normalisiert."""
    if value is None or str(value).strip() == '':
        return False
    src = _norm(source_text)
    v = _norm(value)
    if v and v in src:
        return True
    if kind in ('business_phone', 'telephone', 'phone'):
        d = _digits(value)
        d_alt = '0' + d[2:] if d.startswith('49') else ('49' + d[1:] if d.startswith('0') else d)
        sd = _digits(source_text)
        return len(d) >= 6 and (d in sd or d_alt in sd)
    if kind in ('vat_id', 'register_number'):
        return re.sub(r'\s+', '', v) in re.sub(r'\s+', '', src)
    if kind == 'register_court':  # „Amtsgericht“ wird bei „Registergericht: Stuttgart“ ergänzt
        core = re.sub(r'^amtsgericht\s+', '', v)
        return bool(core) and core in src
    return False


def validate_fields(fields, source_text, source_url, method='', checked_at='', chash=''):
    """Prüft extrahierte Felder {name: {'value', 'excerpt', ...}} gegen den Originaltext.
    Gibt (geprüfte Felder, verworfene Feldnamen) zurück; jedes behaltene Feld trägt einen Beleg-Block ``evidence``."""
    checked, rejected = {}, []
    ts = checked_at or now()
    for name, f in (fields or {}).items():
        if not f or not isinstance(f, dict) or f.get('value') in (None, ''):
            checked[name] = None
            continue
        value, excerpt = str(f['value']), str(f.get('excerpt') or '')
        excerpt_ok = not excerpt or all(found_in(part, source_text) for part in excerpt.split(' | ') if part.strip())
        if not (found_in(value, source_text, name) and excerpt_ok):
            checked[name] = None
            rejected.append(name)
            continue
        checked[name] = {**f, 'evidence': Evidence(name, value, source_url, excerpt or value, f.get('method') or method,
                                                   checked_at=ts, content_hash=chash).as_dict()}
    return checked, rejected


def structured_evidence(org, source_url, source_html, checked_at=''):
    """Belege für strukturierte Angaben (JSON-LD/Microdata): Wert muss im HTML-Quelltext stehen (dort steht der Block)."""
    out = []
    for key, field in (('name', 'legal_name'), ('telephone', 'business_phone'), ('email', 'business_email'), ('vat_id', 'vat_id'),
                       ('street', 'street'), ('zip', 'zip'), ('city', 'city')):
        value = org.get(key)
        if value and found_in(value, source_html, field):
            out.append(Evidence(field, value, source_url, f'{org.get("method")}: {key} = {value}', org.get('method') or 'jsonld',
                                checked_at=checked_at or now(), content_hash=content_hash(source_html)).as_dict())
    return out


# ---------------------------------------------------------------- Evidence-Vertrag v2 (Plan R2.3)
#
# Ein Beleg v2 sagt nicht nur „steht irgendwo im Text“, sondern WO: eine Fundstelle (Textspanne, JSON-Pfad oder PDF-Seite),
# dazu URL, SHA-256 der Abrufbytes, Abruf- und Publikationsdatum, Extraktor mit Version, Rechtsträger und Prüfstatus.
# Originalwert und normalisierter Wert bleiben getrennt. Ein Beleg ohne Fundstelle ist kein Beleg (check_ref → Fehler).
# Wörtliche Belege werden deterministisch gegen den Quellinhalt geprüft (verify_ref): dieselbe Spanne muss denselben
# Wortlaut ergeben bzw. derselbe JSON-Pfad denselben Wert.

EVIDENCE_VERSION = 2
LOCATOR_KINDS = ('text', 'json', 'pdf', 'xml', 'csv', 'doc_text')  # R3.2: XML-Pfad, CSV-Zeile/Spalte, Textzeile eines Dokuments
REVIEW_STATES = ('ungeprueft', 'bestaetigt', 'verworfen')


def text_hash(text):
    return content_hash(text or '')


def _span(text, value, start_hint=0, end_hint=None):
    """Erste wörtliche Fundstelle von ``value`` in ``text`` (ab start_hint, optional bis end_hint) – exakt, nicht normalisiert."""
    if not value or not text:
        return None
    pos = text.find(value, max(0, start_hint), end_hint if end_hint is not None else len(text))
    if pos < 0:
        return None
    return pos, pos + len(value)


def make_ref(field, value, source_url, extractor, locator, *, normalized='', chash='', fetched_at='', published_at='',
             legal_entity='', review_status='ungeprueft'):
    """Beleg v2 als dict. ``locator`` z. B. {'kind': 'text', 'basis': 'raw_text', 'start': 10, 'end': 22, 'quote': '…',
    'text_hash': 'sha256:…'} oder {'kind': 'json', 'block': 0, 'path': ['employee', 1, 'name']}."""
    return {'v': EVIDENCE_VERSION, 'field': field, 'value': str(value), 'normalized': str(normalized or ''), 'source_url': source_url,
            'locator': dict(locator or {}), 'content_hash': chash or '', 'fetched_at': fetched_at or now(),
            'published_at': published_at or '', 'extractor': extractor, 'legal_entity': str(legal_entity or ''),
            'review_status': review_status}


def text_ref(field, value, text, source_url, extractor, *, basis='raw_text', start_hint=0, end_hint=None, **kw):
    """Beleg mit Textspanne – None, wenn der Wert nicht wörtlich im Text steht (dann gibt es keinen Beleg)."""
    span = _span(text, str(value or ''), start_hint, end_hint)
    if not span:
        return None
    a, b = span
    return make_ref(field, value, source_url, extractor,
                    {'kind': 'text', 'basis': basis, 'start': a, 'end': b, 'quote': text[a:b], 'text_hash': text_hash(text)}, **kw)


def resolve_path(data, path):
    cur = data
    for step in path or []:
        if isinstance(step, int) and isinstance(cur, list) and -len(cur) <= step < len(cur):
            cur = cur[step]
        elif isinstance(step, str) and isinstance(cur, dict) and step in cur:
            cur = cur[step]
        else:
            raise KeyError(step)
    return cur


def json_ref(field, value, data, block, path, source_url, extractor, **kw):
    """Beleg mit JSON-Pfad – None, wenn der Pfad nicht genau diesen Wert ergibt."""
    try:
        found = resolve_path(data, path)
    except KeyError:
        return None
    if not isinstance(found, (str, int, float)) or str(found).strip() != str(value).strip():
        return None
    return make_ref(field, value, source_url, extractor, {'kind': 'json', 'block': int(block), 'path': list(path)}, **kw)


def check_ref(ref):
    """Vollständigkeit eines Belegs v2 (ohne Quellinhalt). Gibt eine Fehlerliste zurück – leer heißt vollständig."""
    errors = []
    if not isinstance(ref, dict) or ref.get('v') != EVIDENCE_VERSION:
        return ['kein Beleg v2']
    for key in ('field', 'value', 'source_url', 'extractor', 'fetched_at'):
        if not str(ref.get(key) or '').strip():
            errors.append(f'{key} fehlt')
    loc = ref.get('locator') or {}
    kind = loc.get('kind')
    if kind not in LOCATOR_KINDS:
        errors.append('Fundstelle fehlt')
    elif kind == 'text':
        if not (isinstance(loc.get('start'), int) and isinstance(loc.get('end'), int) and 0 <= loc['start'] < loc['end']):
            errors.append('Textspanne ungültig')
        if not loc.get('quote') or str(ref.get('value', '')) not in loc.get('quote', ''):
            errors.append('Wortlaut passt nicht zum Wert')
        if not str(loc.get('text_hash', '')).startswith('sha256:'):
            errors.append('Prüfsumme des Textes fehlt')
    elif kind == 'json':
        if not isinstance(loc.get('path'), list) or not loc['path'] or not isinstance(loc.get('block'), int):
            errors.append('JSON-Pfad ungültig')
    elif kind == 'pdf':
        if not (isinstance(loc.get('page'), int) and loc['page'] >= 1 and loc.get('quote')):
            errors.append('PDF-Seite oder Wortlaut fehlt')
    elif kind == 'xml':
        if not (str(loc.get('path') or '').startswith('/') and loc.get('quote')):
            errors.append('XML-Pfad oder Wortlaut fehlt')
    elif kind == 'csv':
        if not (isinstance(loc.get('row'), int) and loc['row'] >= 1 and str(loc.get('column') or '').strip() and loc.get('quote')):
            errors.append('CSV-Zeile, Spalte oder Wortlaut fehlt')
    elif kind == 'doc_text':
        if not (isinstance(loc.get('line'), int) and loc['line'] >= 1 and loc.get('quote')):
            errors.append('Zeile oder Wortlaut fehlt')
    if kind in ('pdf', 'xml', 'csv', 'doc_text') and loc.get('quote') and str(ref.get('value', '')) not in loc['quote']:
        errors.append('Wortlaut passt nicht zum Wert')
    if ref.get('review_status', 'ungeprueft') not in REVIEW_STATES:
        errors.append('Prüfstatus ungültig')
    return errors


def verify_ref(ref, text=None, blocks=None):
    """Deterministische Gegenprüfung am Quellinhalt: ``text`` für Textspannen (dieselbe Basis wie beim Erzeugen),
    ``blocks`` (Liste geparster JSON-LD-Blöcke) für JSON-Pfade. True nur, wenn Fundstelle und Wert übereinstimmen."""
    if check_ref(ref):
        return False
    loc = ref['locator']
    if loc['kind'] == 'text':
        if text is None or text_hash(text) != loc['text_hash']:
            return False
        return text[loc['start']:loc['end']] == loc['quote'] and str(ref['value']) in loc['quote']
    if loc['kind'] == 'json':
        if blocks is None or not 0 <= loc['block'] < len(blocks):
            return False
        try:
            found = resolve_path(blocks[loc['block']], loc['path'])
        except KeyError:
            return False
        return str(found).strip() == str(ref['value']).strip()
    if loc['kind'] == 'pdf':  # Seitentext: ``text`` ist der Text genau dieser Seite
        return text is not None and loc['quote'] in text and str(ref['value']) in loc['quote']
    return False


def keep_with_refs(claim, required):
    """Behält einen Claim nur, wenn jedes Pflichtfeld einen vollständigen Beleg v2 hat. → (claim | None, Fehler)."""
    refs = claim.get('evidence_refs') or {}
    problems = []
    for name in required:
        errs = check_ref(refs.get(name))
        if errs:
            problems.append(f'{name}: {", ".join(errs)}')
    return (None, problems) if problems else (claim, [])
