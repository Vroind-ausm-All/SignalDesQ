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
