"""Website-Zuordnung mit mehreren Merkmalen (2.0.0-dev66).

Bisher wurde die Firmen-Website nur aus dem Firmennamen geraten und allein über Name/Registernummer im Impressum
zugeordnet. Kleine Betriebe treten aber oft unter einer Marke auf („Elektro Huber“ ↔ „Huber Elektrotechnik e.K.“),
haben keine Registernummer und eine Domain, die sich nicht aus dem Namen ergibt. Dieses Modul ergänzt:

1. **Kandidaten-Domains** aus der E-Mail-Domain der Quelle (z. B. OpenStreetMap `contact:email` → nur die Domain wird
   gemerkt, Freemail-Anbieter zählen nicht) und weiteren Schreibweisen des Namens (Rechtsform angehängt, umgekehrte
   Wortfolge, „muller“ statt „mueller“, Umlaut-Domain).
2. **Abgleichsmerkmale** ohne Klartext-Kontaktdaten: E-Mail-Domain und ein Prüfwert der Telefonnummer
   (`phone_key`, gekürzter SHA-256 der Ziffern). Der Prüfwert ist eine Pseudonymisierung, keine Anonymisierung –
   er wird nur zum Vergleich mit dem Impressum genutzt, nie angezeigt oder exportiert.
3. **Mehr-Merkmal-Abgleich** (`assess`): Name, Anschrift (Straße + PLZ), Telefon, E-Mail-Domain, Registernummer.
   Harte Gegenbelege (andere Registernummer/-gericht, Rechtsform, PLZ, Ort) schließen weiterhin jede Zuordnung aus.
   Ein abweichender Name ist kein harter Gegenbeleg mehr, wenn Anschrift UND Telefon bzw. E-Mail-Domain übereinstimmen
   (Marke ↔ Firmenname) – das bleibt aber immer ein Vorschlag („wahrscheinlich“), den ein Mensch bestätigt.

Belegt (automatisch übernommen, Empfehlung A) ist eine Website nur mit
- Registernummer + Registergericht + Name (wie bisher) oder
- Name + vollständiger Anschrift + Telefon oder E-Mail-Domain – drei unabhängige Merkmale (für Betriebe ohne Register).
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

FREEMAIL = frozenset('''gmail.com googlemail.com web.de gmx.de gmx.net gmx.at gmx.ch gmx.com t-online.de outlook.com outlook.de hotmail.com
hotmail.de live.de live.com msn.com yahoo.com yahoo.de ymail.com icloud.com me.com mac.com aol.com aol.de freenet.de posteo.de posteo.net
mailbox.org arcor.de online.de mail.de email.de 1und1.de ionos.de kabelmail.de vodafone.de vodafonemail.de protonmail.com proton.me
tutanota.com tutanota.de tuta.io gmx.org netcologne.de ewe.net htp-tel.de unitybox.de mail.com'''.split())
# Gängige Gewerkebegriffe am Namensanfang: „Elektro Huber“ heißt im Netz oft „huber-elektro.de“
TRADE_WORDS = frozenset('''elektro maler malerbetrieb sanitaer heizung bau dach dachdecker auto kfz metall metallbau holz tischlerei schreinerei
zimmerei friseur salon physio physiotherapie praxis kanzlei steuerberatung garten gartenbau fliesen boden raumausstattung glas glaserei
schlosserei stahlbau druck druckerei foto optik baeckerei metzgerei fleischerei catering reinigung transport umzug spedition'''.split())
LEGAL_TAILS = (('gmbh', re.compile(r'\bgmbh\b', re.I)), ('ug', re.compile(r'\bug\b', re.I)), ('ag', re.compile(r'\bag\b', re.I)),
               ('kg', re.compile(r'\bkg\b', re.I)))
MAX_DOMAINS = 12


def _translit(s):
    s = (s or '').casefold().replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()


def _plain(s):
    """„müller“ → „muller“ (manche Betriebe lassen das e weg)."""
    s = (s or '').casefold().replace('ß', 'ss')
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()


# ---------------------------------------------------------------- Abgleichsmerkmale (keine Klartext-Kontaktdaten)

def email_domain(addr):
    """Domain einer E-Mail-Adresse, wenn sie zu einer Firma gehören kann (keine Freemail-Anbieter). Sonst ''."""
    m = re.fullmatch(r'\s*(?:mailto:)?[^@\s<>]+@([a-z0-9.-]+\.[a-z]{2,})\s*', (addr or '').casefold())
    if not m:
        return ''
    dom = m.group(1).strip('.')
    dom = dom[4:] if dom.startswith('www.') else dom
    return '' if dom in FREEMAIL or len(dom) > 80 else dom


def phone_digits(raw):
    """Telefonnummer → Ziffern mit Ländervorwahl (49…). Sonst ''."""
    s = (raw or '').split(';')[0].split(',')[0]
    s = re.sub(r'\(0\)', '', s)
    d = re.sub(r'\D', '', s)
    if s.strip().startswith('+'):
        pass
    elif d.startswith('00'):
        d = d[2:]
    elif d.startswith('0'):
        d = '49' + d[1:]
    return d if 9 <= len(d) <= 15 else ''


def phone_key(raw):
    d = phone_digits(raw)
    return hashlib.sha256(('signaldesk-tel:' + d).encode()).hexdigest()[:16] if d else ''


def hints_from(phone='', email='', domain=''):
    """Abgleichsmerkmale einer Quelle. Gespeichert werden nur E-Mail-Domain und Telefon-Prüfwert."""
    out = {}
    ed = email_domain(email) or (email_domain('x@' + domain) if domain else '')
    if ed:
        out['email_domains'] = [ed]
    pk = phone_key(phone)
    if pk:
        out['phone_keys'] = [pk]
    return out


def merge_hints(old, new):
    out = {k: list(v) for k, v in (old or {}).items() if isinstance(v, list)}
    for k, vals in (new or {}).items():
        cur = out.setdefault(k, [])
        cur.extend(v for v in vals if v not in cur)
        out[k] = cur[:5]
    return out


# ---------------------------------------------------------------- Kandidaten-Domains

def _words(name, city=''):
    from ..sweep import STOP_WORDS
    town = set(_translit(city).split())
    return [w for w in re.split(r'[^a-z0-9]+', _translit(name)) if w and w not in STOP_WORDS and w not in town]


def extra_guesses(name, city=''):
    """Weitere Schreibweisen zusätzlich zu ``sweep.domain_guesses``."""
    words = _words(name, city)
    if not words:
        return []
    out = []
    core = words[:3]
    if len(core) <= 2:
        for tail, rx in LEGAL_TAILS:
            if rx.search(name or ''):
                out += [f"{'-'.join(core)}-{tail}.de", f"{''.join(core)}{tail}.de"]
                break
    if len(words) == 2:
        out.append(f'{words[1]}-{words[0]}.de')  # „Elektro Huber“ → huber-elektro.de
    stop, town = _words_stop(), set(_translit(city).split())
    plain = [w for w in re.split(r'[^a-z0-9]+', _plain(name)) if w and w not in stop and w not in town]
    if plain and plain[:3] != core:
        out += [f"{'-'.join(plain[:3])}.de", f"{''.join(plain[:3])}.de"]
    uml = [w for w in re.split(r'[^\wäöü]+', (name or '').casefold()) if w and _translit(w) in words]
    if any(ch in ''.join(uml) for ch in 'äöü'):
        for base in dict.fromkeys(['-'.join(uml[:3]), ''.join(uml[:3])]):
            try:
                out.append(f"{base.encode('idna').decode('ascii')}.de")
            except UnicodeError:
                pass
    return [d for d in dict.fromkeys(out) if 4 <= len(d) <= 63]


def _words_stop():
    from ..sweep import STOP_WORDS
    return STOP_WORDS


def candidate_domains(name, city='', hints=None, rejected=()):
    """Geordnete Liste (domain, herkunft). E-Mail-Domain der Quelle zuerst, dann Namensvarianten. Höchstens MAX_DOMAINS."""
    from ..sweep import domain_guesses
    rejected = set(rejected)
    out = []
    for d in (hints or {}).get('email_domains', []):
        out.append((d, 'E-Mail-Domain laut Quelle'))
    guesses = domain_guesses(name, city)
    out += [(d, 'aus dem Namen') for d in guesses if not d.endswith('.com')]
    out += [(d, 'Namensvariante') for d in extra_guesses(name, city)]
    out += [(d, 'aus dem Namen') for d in guesses if d.endswith('.com')]
    seen, result = set(), []
    for d, why in out:
        if d in seen or d in rejected or d.split('.')[0] in TRADE_WORDS:  # „elektro.de“ gehört sicher nicht diesem Betrieb
            continue
        seen.add(d)
        result.append((d, why))
    return result[:MAX_DOMAINS]


# ---------------------------------------------------------------- Abgleich

def norm_street(street):
    t = _translit(street)
    t = re.sub(r'stra(ss)?e\b|str\b\.?', 'str', t)
    return re.sub(r'[^a-z0-9]', '', t)


def _street_match(a, b):
    na, nb = norm_street(a), norm_street(b)
    return bool(na and nb and re.search(r'\d', na) and na == nb)


def signals(cand, fields, hints, site_domain=''):
    """Welche Merkmale stimmen zwischen Treffer und Impressum überein? Gibt eine Liste von Kürzeln zurück."""
    from ..sweep import _cget, _names_match
    val = lambda k: ((fields.get(k) or {}).get('value') or '')
    hints = hints or {}
    out = []
    if _names_match(cand['name'], val('legal_name')):
        out.append('name')
    if cand['zip'] and val('zip') == cand['zip']:
        out.append('plz')
    if _street_match(_cget(cand, 'street'), val('street')):
        out.append('strasse')
    if hints.get('phone_keys') and phone_key(val('business_phone')) in hints['phone_keys']:
        out.append('telefon')
    eds = set(hints.get('email_domains') or [])
    if eds and (email_domain(val('business_email')) in eds or (site_domain and site_domain in eds)):
        out.append('email_domain')
    return out


LABELS = {'name': 'Firmenname', 'plz': 'PLZ', 'strasse': 'Straße', 'telefon': 'Telefon', 'email_domain': 'E-Mail-Domain'}


def _label(sig):
    return ', '.join(LABELS[s] for s in sig if s in LABELS)


def assess(cand, fields, hints=None, site_domain=''):
    """Stufe und Begründung: ('belegt' | 'wahrscheinlich' | None, Begründung, Merkmale)."""
    from ..company_data import normalize_register
    from ..sweep import _cget, counter_evidence
    val = lambda k: ((fields.get(k) or {}).get('value') or '')
    sig = signals(cand, fields, hints, site_domain)
    contact = {'telefon', 'email_domain'} & set(sig)
    address = {'plz', 'strasse'} <= set(sig)
    why_not = counter_evidence(cand, fields)
    if why_not.startswith('anderer Firmenname') and address and contact and not counter_evidence(cand, fields, ignore_name=True):
        # Marke ↔ Firmenname: Anschrift und Kontaktweg stimmen, sonst kein Gegenbeleg – nur als Vorschlag
        return 'wahrscheinlich', f"{why_not}, aber {_label(sig)} stimmen überein (Marke oder Inhabername?)", sig
    if why_not:
        return None, why_not, sig
    reg = re.sub(r'\s+', '', val('register_number').upper())
    wanted_reg = re.sub(r'\s+', '', (cand['register_id'] or '').upper())
    if reg and wanted_reg == reg:
        expected = normalize_register(_cget(cand, 'register_court'), wanted_reg)
        observed = normalize_register(val('register_court'), reg)
        if expected and observed and 'name' in sig:
            return 'belegt', f"Registernummer und Registergericht stimmen überein: {val('register_number')} · {val('register_court')}", sig
        return 'wahrscheinlich', f"Registernummer {val('register_number')} stimmt überein; Registergericht oder Firmenname nicht sicher verglichen", sig
    if 'name' in sig and address and contact:
        return 'belegt', f'{_label(sig)} stimmen mit dem Impressum überein', sig
    if 'name' in sig and (not cand['zip'] or 'plz' in sig):
        return 'wahrscheinlich', f"Firmenname{' und PLZ' if cand['zip'] else ''} im Impressum stimmen überein" + (
            f" (außerdem {_label([s for s in sig if s not in ('name', 'plz')])})" if len(sig) > 2 or (not cand['zip'] and len(sig) > 1) else ''), sig
    if contact and ('plz' in sig or address):
        return 'wahrscheinlich', f'{_label(sig)} stimmen mit dem Impressum überein', sig
    return None, 'Impressum ohne passenden Firmennamen oder Registernummer', sig


# ---------------------------------------------------------------- Suche (gemeinsam für Treffer-Sichtung und Firmen-Bericht)

def search(cand, targets, hints=None, research=None, on_missing=None):
    """Prüft die Domains nacheinander über das Impressum, bis eine zugeordnet werden kann.
    targets: Liste (domain, herkunft) – darf während der Suche wachsen (on_missing(index, domain) kann ergänzen).
    Gibt ein Dict zurück: status ('belegt' | 'wahrscheinlich' | None), domain, origin, why, res, tried, missing, errors, inspected, against.
    Eine Domain ohne DNS-Eintrag ist kein Abruffehler. Fehlt die Namensauflösung ganz, zählt sie doch als Fehler (dns_down)."""
    from .. import imprint
    from .safe_urls import DomainMissing, dns_available
    research = research or imprint.research_domain
    out = {'status': None, 'domain': '', 'origin': '', 'why': '', 'res': None, 'tried': [], 'missing': [], 'errors': 0,
           'inspected': 0, 'against': [], 'dns_down': False}
    i = 0
    while i < len(targets):
        dom, origin = targets[i]
        i += 1
        out['tried'].append(dom)
        try:
            res = research(dom, include_persons=False)
        except DomainMissing:
            out['missing'].append(dom)
            if on_missing:
                on_missing(i - 1, dom)
            continue
        except Exception:  # Fehler bedeutet nicht, dass die Website nicht existiert.
            out['errors'] += 1
            continue
        out['inspected'] += 1
        if res.get('status') != 'ok':
            continue
        status, why, _ = assess(cand, res.get('fields') or {}, hints, res.get('site_domain') or '')
        if not status:
            if why:
                out['against'].append(f'{dom}: {why}')
            continue
        if origin == 'E-Mail-Domain laut Quelle':
            why += ' · Domain aus der E-Mail-Adresse der Quelle'
        out.update(status=status, domain=dom, origin=origin, why=why, res=res)
        return out
    if not out['errors'] and out['missing'] and not out['inspected'] and not dns_available():
        out['errors'], out['dns_down'] = len(out['missing']), True  # ohne Namensauflösung ist „gibt es nicht“ keine Aussage
    return out


def lead_profile(conn, lead):
    """Treffer-ähnliche Sicht auf eine Firma (für ``assess``) samt Abgleichsmerkmalen und abgelehnten Domains."""
    cand = {'name': lead['company'], 'zip': lead['zip'] or '', 'city': lead['city'] or '', 'street': lead['street'] or '',
            'register_id': lead['register_number'] or '', 'register_court': lead['register_court'] or '', 'legal_form': lead['legal_form'] or ''}
    hints = hints_from(lead['business_phone'], lead['business_email'])
    rejected = set()
    import json
    for r in conn.execute('SELECT match_hints_json, imprint_json FROM discovery_candidates WHERE lead_id=?', (lead['id'],)):
        try:
            hints = merge_hints(hints, json.loads(r['match_hints_json'] or '{}'))
            rejected |= set(json.loads(r['imprint_json'] or '{}').get('rejected_domains', []))
        except ValueError:
            continue
    for r in conn.execute('SELECT refs_json FROM company_reports WHERE lead_id=?', (lead['id'],)):
        try:
            rejected |= set(json.loads(r['refs_json'] or '{}').get('rejected_domains', []))
        except ValueError:
            continue
    return cand, hints, rejected
