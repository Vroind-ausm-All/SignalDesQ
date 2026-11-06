"""Impressum Intelligence (Phase 1): Pflichtangaben aus Impressumsseiten deterministisch extrahieren.

- Findet den Impressumslink über Linktext/Pfad (nicht nur `/impressum`), erlaubt HTML und PDF.
- Liest nur Seiten derselben Firmen-Domain, prüft robots.txt, DNS (keine internen Adressen),
  jede Weiterleitung und begrenzt die Antwortgröße.
- Jedes Feld bekommt den wörtlichen Textbeleg. Nicht gefundene Felder bleiben `None`.
- Personen werden nur als vertretungsberechtigte Funktion laut Impressum erfasst. Allgemeine
  Telefonnummern werden nie als persönliche Durchwahl ausgegeben.
"""
from __future__ import annotations

import datetime as dt
import html
import re
import time
import zlib
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .website_analyzer import CrawlError, public_url, robots_allowed, same_company_host

METHOD = 'regel:impressum-v1'
AGENT = 'SignalDeskResearch/1.15 (+public company data research; single pages, no bulk crawling)'  # nur ASCII; Abruf: research.policy.AGENT
MAX_HTML = 2_000_000
MAX_PDF = 5_000_000
REQUEST_DELAY = 1.0  # Sekunden zwischen zwei Abrufen derselben Domain
IMPRINT_WORDS = ('impressum', 'imprint', 'legal notice', 'legal-notice', 'site notice', 'anbieterkennzeichnung',
                 'rechtliche hinweise', 'rechtliches', 'legal', 'pflichtangaben', 'herausgeber')
NOT_IMPRINT = ('datenschutz', 'privacy', 'cookie', 'agb', 'terms', 'barrierefrei', 'widerruf')
FALLBACK_PATHS = ('/impressum', '/imprint', '/de/impressum')


# ---------------------------------------------------------------- Abruf (in Tests ersetzbar)

class _SafeRedirect(HTTPRedirectHandler):
    def __init__(self, origin):
        super().__init__()
        self.origin = origin
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > 4:
            raise CrawlError('Zu viele Weiterleitungen.')
        target = public_url(urljoin(req.full_url, newurl))
        if self.origin and not same_company_host(self.origin, target):
            raise CrawlError(f'Weiterleitung auf fremde Domain ({urlsplit(target).hostname}) – nicht gefolgt.')
        return super().redirect_request(req, fp, code, msg, headers, target)


def http_fetch(url, origin=None):
    """Gibt (finale_url, content_type, bytes) zurück. Wirft CrawlError bei jedem Sicherheitsproblem.
    Seit v1.15 über research.fetch: IP-Pinning, geprüfte Weiterleitungen, robots.txt nach RFC 9309, gzip mit Größenbremse."""
    from .research import fetch
    res = fetch(url, origin=origin)
    return res.final_url, res.content_type, res.body


FETCH = http_fetch
SLEEP = time.sleep


# ---------------------------------------------------------------- HTML → Text mit Zeilen

class _TextAndLinks(HTMLParser):
    BLOCK = {'p', 'div', 'br', 'li', 'tr', 'td', 'th', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'section', 'article',
             'header', 'footer', 'address', 'dd', 'dt', 'table', 'ul', 'ol', 'hr', 'blockquote', 'span'}
    SKIP = {'script', 'style', 'noscript', 'svg', 'template', 'iframe', 'title'}  # v1.15: Seitentitel ist kein Fließtext

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self._skip, self._href, self._atext = [], [], 0, None, []
        self.mailtos = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        if tag in self.BLOCK and tag != 'span':
            self.parts.append('\n')
        if tag == 'a':
            href = dict(attrs).get('href') or ''
            self._href, self._atext = href, []
            if href.lower().startswith('mailto:'):
                self.mailtos.append(href[7:].split('?')[0])

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag in self.BLOCK and tag != 'span':
            self.parts.append('\n')
        if tag == 'a' and self._href is not None:
            self.links.append({'href': self._href, 'text': ' '.join(self._atext).strip()})
            self._href = None

    def handle_data(self, data):
        if self._skip:
            return
        self.parts.append(data)
        if self._href is not None:
            self._atext.append(data.strip())


def html_to_text(raw: bytes):
    if isinstance(raw, bytes):
        from .research.fetchers.base import decode_html
        text = decode_html(raw)  # v1.15: BOM → meta charset → UTF-8 → Windows-1252
    else:
        text = raw
    parser = _TextAndLinks()
    parser.feed(text)
    joined = ''.join(parser.parts).replace('\xa0', ' ')
    lines = [re.sub(r'[ \t\r\f\v]+', ' ', l).strip() for l in joined.split('\n')]
    return '\n'.join(l for l in lines if l), parser.links, parser.mailtos


# ---------------------------------------------------------------- PDF (einfach, ohne Abhängigkeiten)

def _pdf_string(s: bytes) -> str:
    out, i = bytearray(), 0
    esc = {b'n': b'\n', b'r': b'\r', b't': b'\t', b'b': b'\b', b'f': b'\f', b'(': b'(', b')': b')', b'\\': b'\\'}
    while i < len(s):
        c = s[i:i + 1]
        if c == b'\\' and i + 1 < len(s):
            nxt = s[i + 1:i + 2]
            if nxt in esc:
                out += esc[nxt]
                i += 2
                continue
            m = re.match(rb'[0-7]{1,3}', s[i + 1:i + 4])
            if m:
                out.append(int(m.group(0), 8) & 0xFF)
                i += 1 + len(m.group(0))
                continue
            i += 1
            continue
        out += c
        i += 1
    try:
        return out.decode('utf-8')
    except UnicodeDecodeError:
        return out.decode('cp1252', 'replace')


def pdf_to_text(raw: bytes) -> str:
    """Best effort: liest Text aus unkomprimierten und Flate-komprimierten Inhaltsströmen.

    PDFs mit eingebetteten CID-Schriften/Subset-Kodierungen liefern oft keinen lesbaren Text –
    dann bleibt das Ergebnis leer und das Impressum muss manuell geprüft werden.
    """
    chunks = []
    for m in re.finditer(rb'<<(.*?)>>\s*stream\r?\n(.*?)\r?\nendstream', raw, re.S):
        head, body = m.group(1), m.group(2)
        if b'/FlateDecode' in head:
            try:
                body = zlib.decompress(body)
            except zlib.error:
                continue
        elif b'/Filter' in head:
            continue
        if b'BT' not in body:
            continue
        lines, current = [], []
        for tok in re.finditer(rb'\((?:\\.|[^\\)])*\)|\[(?:[^\]]*)\]\s*TJ|T\*|Td|TD|ET|\'|"', body, re.S):
            t = tok.group(0)
            if t.startswith(b'('):
                current.append(_pdf_string(t[1:-1]))
            elif t.startswith(b'['):
                current.append(''.join(_pdf_string(x[1:-1]) for x in re.findall(rb'\((?:\\.|[^\\)])*\)', t)))
            elif current:
                lines.append(''.join(current))
                current = []
        if current:
            lines.append(''.join(current))
        chunks.extend(l.strip() for l in lines if l.strip())
    text = '\n'.join(chunks)
    letters = sum(ch.isalpha() for ch in text)
    return text if text and letters / max(1, len(text)) > 0.5 else ''


# ---------------------------------------------------------------- Extraktion

LEGAL_FORMS = (r'GmbH\s*&\s*Co\.?\s*KGaA|GmbH\s*&\s*Co\.?\s*KG|UG\s*\(haftungsbeschränkt\)\s*&\s*Co\.?\s*KG|AG\s*&\s*Co\.?\s*KG|'
               r'gGmbH|GmbH|UG\s*\(haftungsbeschränkt\)|KGaA|AG|SE|KG|OHG|oHG|e\.\s?K\.|e\.\s?Kfm\.|e\.\s?Kfr\.|'
               r'PartG\s*mbB|PartG|eG|e\.\s?V\.|GbR|Ltd\.?|Limited|B\.V\.|S\.A\.|Inc\.')
COMPANY_RE = re.compile(r'([A-ZÄÖÜ0-9][\w&.,\'’+\-– ]{1,90}?\s(?:' + LEGAL_FORMS + r'))(?=$|[\s,;:)|/])')
LABEL_PREFIX = re.compile(r'^(anbieter|betreiber|herausgeber|verantwortlich|firma|unternehmen|name|inhaber der website|'
                          r'angaben gemäß § ?5 (tmg|ddg)|diensteanbieter|website|webseite)\s*[:\-–]\s*', re.I)
PLZ_RE = re.compile(r'(?<![\d-])(\d{5})\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöüß.\- ]{1,40}?)(?=$|\s*[,;|]|\s{2,}|\s+(?:Deutschland|Germany|DE)\b|\s+(?:Tel|Fon|Fax|E-Mail|Mail|www)\b|'
                    r'\s+(?:Amtsgericht|Registergericht|Handelsregister|HRB|HRA|USt|Umsatzsteuer|Geschäftsführ|Vertreten|Inhaber)\b)')
STREET_RE = re.compile(r'([A-ZÄÖÜ][A-Za-zÄÖÜäöüß.\-\' ]{2,50}?\s\d{1,4}\s?[a-zA-Z]?(?:\s?[-–/]\s?\d{1,4}[a-z]?)?)(?=$|\s*[,;|]|\s+\d{5}\s)')
REG_NUM_RE = re.compile(r'\b(HRB|HRA|GnR|PR|VR|GsR)\s*(?:Nr\.?|-Nr\.?|:)?\s*(\d{1,6}(?:\s?[A-Z]{1,2}\b)?)')
COURT_RE = re.compile(r'(?:Amtsgerichts?|Registergericht\s*:?\s*(?:Amtsgericht)?|Registergericht)\s*:?\s*'
                      r'([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+(?:\s(?:am|an der|im|in der|i\.)\s?[A-ZÄÖÜ]?[A-Za-zÄÖÜäöüß.()\-]+)?(?:\s\((?:Main|Oder|Breisgau)\))?)')
VAT_RE = re.compile(r'\b(DE)\s?(\d{3})\s?(\d{3})\s?(\d{3})\b')
PHONE_RE = re.compile(r'(?<![\w])(?:Tel(?:efon)?|Fon|Phone|T)\s*\.?\s*[:.]?\s*(\+?\(?\d[\d\s/().\-–]{5,22}\d)')
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}')
REP_RE = re.compile(r'(Geschäftsführer(?:in|innen)?|Geschäftsführung|Geschäftsleitung|Vorstandsvorsitzende[r]?|Vorstände|Vorstand|'
                    r'Inhaber(?:in)?|Vertretungsberechtigte[r]?(?:\s(?:Geschäftsführer(?:in)?|Gesellschafter(?:in)?))?|Vertreten durch|'
                    r'Managing Directors?|Persönlich haftende[r]? Gesellschafter(?:in)?)\s*[:\-–]?\s*(.*)', re.I)
TITLE_RE = re.compile(r'\b(Dr\.|Prof\.|Dipl\.-[A-Za-zäöü.]+|Dipl\.|M\.A\.|B\.A\.|MBA|LL\.M\.|Ing\.|rer\. nat\.|med\.)\s*', re.I)
NAME_TOKEN = re.compile(r"^(?:[A-ZÄÖÜ][a-zäöüßéèáàíóúç'’]+(?:-[A-ZÄÖÜ][a-zäöüßéèáàíóúç'’]+)?|von|van|de|der|den|zu|vom|di|da|le|la)$")
GENERIC_MAIL = ('info', 'kontakt', 'contact', 'office', 'mail', 'hello', 'hallo', 'service', 'post', 'zentrale', 'empfang', 'buero', 'team', 'anfrage', 'vertrieb', 'sales')
ROLE_LABELS = {'geschäftsführ': 'Geschäftsführung', 'geschäftsleitung': 'Geschäftsleitung', 'vorstand': 'Vorstand',
               'inhaber': 'Inhaber/in', 'managing': 'Geschäftsführung', 'persönlich haftend': 'Persönlich haftende/r Gesellschafter/in',
               'vertret': 'Vertretungsberechtigt'}
STOP_WORDS = {'Straße', 'Str', 'Strasse', 'Weg', 'Platz', 'Telefon', 'Tel', 'Fax', 'Mail', 'Amtsgericht', 'Handelsregister',
              'Registergericht', 'Deutschland', 'Germany', 'Umsatzsteuer', 'Impressum', 'Kontakt', 'Sitz', 'Gesellschaft'}


def vat_checksum_ok(vat: str) -> bool:
    """Prüfziffer deutscher USt-IdNr. (ISO 7064, MOD 11,10)."""
    if not re.fullmatch(r'DE\d{9}', vat or ''):
        return False
    digits = [int(c) for c in vat[2:]]
    product = 10
    for d in digits[:8]:
        total = (d + product) % 10 or 10
        product = (2 * total) % 11
    check = 11 - product
    return (0 if check == 10 else check) == digits[8]


def _field(value, excerpt, quality='mittel'):
    return {'value': value, 'excerpt': excerpt[:300], 'method': METHOD, 'quality': quality}


def _deobfuscate(text):
    text = re.sub(r'\s*[\[(\{]\s*(?:at|ät|@)\s*[\])\}]\s*', '@', text, flags=re.I)
    text = re.sub(r'\s*[\[(\{]\s*(?:dot|punkt|\.)\s*[\])\}]\s*', '.', text, flags=re.I)
    return text


def _clean_company(name):
    name = LABEL_PREFIX.sub('', name.strip(' :-–,'))
    name = re.sub(r'^(die|der|das|the)\s+', '', name, flags=re.I)
    return re.sub(r'\s{2,}', ' ', name).strip(' ,;:')


def _legal_form(name):
    m = re.search('(' + LEGAL_FORMS + r')\s*$', name)
    return re.sub(r'\s+', ' ', m.group(1)) if m else None


def _entities(lines):
    seen, out = set(), []
    for idx, line in enumerate(lines[:200]):
        if len(line) > 220:
            continue
        for m in COMPANY_RE.finditer(line):
            raw = _clean_company(m.group(1))
            words = raw.split()
            if not 2 <= len(words) <= 12 or re.match(r'^(Sitz|Registergericht|Amtsgericht|Umsatzsteuer|Copyright|©)', raw, re.I):
                continue
            key = re.sub(r'\W+', '', raw.lower())
            if key in seen:
                continue
            seen.add(key)
            context = (lines[idx - 1] + ' ' + line) if idx else line
            role = 'Komplementärin' if re.search(r'komplementär|persönlich haftende|vertreten durch die', context, re.I) and out else None
            out.append({'name': raw, 'legal_form': _legal_form(raw), 'role': role, 'line': idx, 'excerpt': line})
    return out


def _address(lines, start):
    for idx in range(start, min(len(lines), start + 12)):
        line = lines[idx]
        if re.search(r'postfach', line, re.I):
            continue
        m = PLZ_RE.search(line)
        if not m:
            continue
        zip_code, city = m.group(1), m.group(2).strip(' .-')
        before = line[:m.start()].strip(' ,;|')
        street = None
        sm = STREET_RE.search(before) if before else None
        if sm:
            street = sm.group(1).strip()
        elif idx > 0:
            sm = STREET_RE.search(lines[idx - 1])
            if sm and not COMPANY_RE.search(lines[idx - 1]):
                street = sm.group(1).strip()
        excerpt = (lines[idx - 1] + ' | ' + line) if idx > 0 and street and street not in line else line
        return {'street': _field(street, excerpt, 'hoch') if street else None,
                'zip': _field(zip_code, excerpt, 'hoch'), 'city': _field(city, excerpt, 'hoch')}
    return {'street': None, 'zip': None, 'city': None}


def _register_at(lines, idx, m):
    line = lines[idx]
    court, excerpt = None, line
    cm = COURT_RE.search(line)
    if not cm:  # Registergericht steht oft eine Zeile darüber oder darunter
        for near in (idx - 1, idx + 1, idx - 2):
            if 0 <= near < len(lines) and (cm := COURT_RE.search(lines[near])):
                excerpt = f'{lines[near]} | {line}' if near < idx else f'{line} | {lines[near]}'
                break
    if cm:
        court = 'Amtsgericht ' + re.sub(r'\s+', ' ', cm.group(1)).strip(' ,.;')
    number = f"{m.group(1)} {re.sub(r'\s+', ' ', m.group(2)).strip()}"
    return number, court, excerpt


def _register(lines, other_entities=()):
    """Registerangabe der Hauptgesellschaft. Zeilen, die eine weitere Gesellschaft nennen
    (z. B. Komplementär-GmbH), werden dieser zugeordnet statt der Hauptfirma."""
    fallback = None
    for idx, line in enumerate(lines):
        m = REG_NUM_RE.search(line)
        if not m:
            continue
        number, court, excerpt = _register_at(lines, idx, m)
        owner = next((e for e in other_entities if e['name'].lower() in line.lower()), None)
        if owner:
            owner.setdefault('register', f"{court + ' ' if court else ''}{number}")
            fallback = fallback or (number, court, excerpt)
            continue
        return {'register_number': _field(number, excerpt, 'hoch' if court else 'mittel'),
                'register_court': _field(court, excerpt, 'hoch') if court else None}
    if fallback and not other_entities:
        number, court, excerpt = fallback
        return {'register_number': _field(number, excerpt, 'mittel'), 'register_court': _field(court, excerpt, 'mittel') if court else None}
    return {'register_number': None, 'register_court': None}


def _vat(lines):
    for idx, line in enumerate(lines):
        m = VAT_RE.search(line)
        if not m:
            continue
        context = ' '.join(lines[max(0, idx - 1):idx + 1])
        if not re.search(r'USt|Umsatzsteuer|VAT|Steuer', context, re.I):
            continue
        vat = ''.join(m.groups())
        ok = vat_checksum_ok(vat)
        return _field(vat, line, 'hoch' if ok else 'niedrig') | {'checksum_ok': ok}
    return None


def _persons(lines, entity_names):
    people, seen = [], set()
    for idx, line in enumerate(lines):
        m = REP_RE.search(line)
        if not m:
            continue
        keyword, rest = m.group(1), m.group(2).strip()
        if not rest and idx + 1 < len(lines):
            rest = lines[idx + 1]
        if COMPANY_RE.search(rest) and not re.search(r'\b(diese|deren|sie)\b.*vertreten', rest, re.I):
            continue  # z. B. „vertreten durch die Muster Verwaltungs GmbH“ – Gesellschaft, keine Person
        role = next((label for key, label in ROLE_LABELS.items() if key in keyword.lower()), 'Vertretungsberechtigt')
        # „vertreten durch die Geschäftsführerin Lea Nordmann“ → Artikel/Rollenwörter vor dem Namen entfernen
        lead_in = re.compile(r'^(?:(?:die|den|der|das|ihre[n]?|seine[n]?|unsere[n]?)\s+|(?:Geschäftsführer(?:in|innen)?|Geschäftsführung|Vorstand|Vorstände|Inhaber(?:in)?|Gesellschafter(?:in)?|Partner(?:in)?)\s*:?\s+)', re.I)
        while True:
            stripped = lead_in.sub('', rest, count=1)
            if stripped == rest:
                break
            if re.match(r'geschäftsführ', rest, re.I):
                role = 'Geschäftsführung'
            rest = stripped
        rest = re.split(r'\s(?:Sitz|Registergericht|Amtsgericht|Handelsregister|USt|Umsatzsteuer|Tel|E-Mail)\b', rest)[0]
        for chunk in re.split(r',|;|\s+und\s+|\s+&\s+|\s/\s|\s\|\s', rest):
            name = TITLE_RE.sub('', chunk).strip(' .:()')
            name = re.sub(r'\s*\(.*?\)\s*', ' ', name).strip()
            tokens = name.split()
            if not 2 <= len(tokens) <= 4 or any(t.strip('.') in STOP_WORDS for t in tokens):
                continue
            if not all(NAME_TOKEN.match(t) for t in tokens) or not tokens[0][0].isupper() or not tokens[-1][0].isupper():
                continue
            if any(name.lower() in e.lower() for e in entity_names):
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            people.append({'name': name, 'role': role, 'excerpt': line[:300], 'method': METHOD, 'quality': 'mittel'})
        if len(people) >= 6:
            break
    return people


def _phone(lines):
    for line in lines:
        if re.match(r'^\s*(Fax|Telefax)\b', line, re.I):
            continue
        m = PHONE_RE.search(line)
        if m and not re.search(r'fax', line[:m.start()][-8:], re.I):
            number = re.sub(r'\s+', ' ', m.group(1)).strip(' -/')
            if sum(c.isdigit() for c in number) >= 6:
                return _field(number, line, 'mittel') | {'note': 'Allgemeine Geschäftsnummer laut Impressum – keine persönliche Durchwahl, keine Werbeeinwilligung.'}
    return None


def _email(lines, mailtos, site_domain):
    candidates = []
    for addr in mailtos:
        candidates.append((addr.strip(), f'mailto:{addr.strip()}'))
    for line in lines:
        for addr in EMAIL_RE.findall(_deobfuscate(line)):
            candidates.append((addr, line))
    best, best_score = None, -1
    for addr, excerpt in candidates:
        addr = addr.lower().strip('.')
        if not EMAIL_RE.fullmatch(addr):
            continue
        local, _, domain = addr.partition('@')
        score = (2 if site_domain and (domain == site_domain or domain.endswith('.' + site_domain)) else 0) + (2 if local in GENERIC_MAIL else 0)
        if score > best_score:
            best, best_score = (addr, excerpt, local in GENERIC_MAIL), score
    if not best:
        return None
    addr, excerpt, generic = best
    field = _field(addr, excerpt, 'hoch' if generic else 'mittel')
    field['note'] = 'Veröffentlicht zur Erreichbarkeit – keine Werbeeinwilligung (§ 7 UWG).'
    if not generic:
        field['note'] += ' Möglicherweise personenbezogen.'
    return field


def extract(text, mailtos=(), site_domain='', include_persons=True):
    """Deterministische Extraktion aus Impressumstext. Fehlende Felder bleiben None."""
    lines = [l.strip() for l in (text or '').splitlines() if l.strip()]
    entities = _entities(lines)
    primary = next((e for e in entities if not e['role']), entities[0] if entities else None)
    fields = {k: None for k in ('legal_name', 'legal_form', 'street', 'zip', 'city', 'register_court', 'register_number',
                                'vat_id', 'business_phone', 'business_email')}
    if primary:
        fields['legal_name'] = _field(primary['name'], primary['excerpt'], 'hoch')
        if primary['legal_form']:
            fields['legal_form'] = _field(primary['legal_form'], primary['excerpt'], 'hoch')
    fields.update(_address(lines, primary['line'] if primary else 0))
    if not fields['zip'] and primary:
        fields.update(_address(lines, 0))
    fields.update(_register(lines, [e for e in entities if e is not primary]))
    fields['vat_id'] = _vat(lines)
    fields['business_phone'] = _phone(lines)
    fields['business_email'] = _email(lines, mailtos, site_domain)
    persons = _persons(lines, [e['name'] for e in entities]) if include_persons else []
    warnings = []
    independent = [e for e in entities if not e['role']]
    if len(independent) > 1:
        warnings.append(f'{len(independent)} Gesellschaften im Impressum erkannt – richtige Firma prüfen.')
    if not primary:
        warnings.append('Kein Firmenname mit Rechtsform gefunden (Einzelunternehmen oder ungewöhnliches Format) – manuell prüfen.')
    if fields['vat_id'] and not fields['vat_id'].get('checksum_ok'):
        warnings.append('USt-IdNr. besteht die Prüfziffernprüfung nicht – Tippfehler im Impressum oder Fehlerkennung.')
    if fields['register_number'] and not fields['register_court']:
        warnings.append('Registernummer ohne erkennbares Registergericht.')
    found = sum(1 for v in fields.values() if v)
    return {'entities': [{k: e.get(k) for k in ('name', 'legal_form', 'role', 'excerpt', 'register')} for e in entities[:6]],
            'fields': fields, 'representatives': persons, 'warnings': warnings,
            'completeness': {'found': found, 'total': len(fields)}}


# ---------------------------------------------------------------- Impressum finden

def _score_link(origin, link):
    href = urljoin(origin, link.get('href', ''))
    p = urlsplit(href)
    if p.scheme not in ('http', 'https') or not same_company_host(origin, href):
        return None, href
    label = (link.get('text', '') + ' ' + p.path).lower()
    if any(w in label for w in NOT_IMPRINT) and 'impressum' not in label:
        return None, href
    if 'impressum' in label or 'imprint' in label:
        return 0, href
    if any(w in label for w in IMPRINT_WORDS):
        return 1, href
    return None, href


def find_imprint_links(origin, links):
    scored = []
    for link in links:
        rank, href = _score_link(origin, link)
        if rank is not None:
            clean = urlunsplit(urlsplit(href)._replace(fragment=''))
            if clean not in [h for _, h in scored]:
                scored.append((rank, clean))
    return [h for _, h in sorted(scored)][:3]


def _decode(url, ctype, data):
    if ctype == 'application/pdf' or data[:5] == b'%PDF-':
        return pdf_to_text(data), [], [], 'impressum_pdf'
    text, links, mailtos = html_to_text(data)
    return text, links, mailtos, 'impressum_html'


def research_domain(domain_or_url, include_persons=True):
    """Startseite laden → Impressum finden → extrahieren. Gibt ein Ergebnis-Dict zurück (wirft nur bei Totalausfall)."""
    url = domain_or_url.strip()
    if '://' not in url:
        url = 'https://' + url
    log = []
    try:
        home_url, ctype, data = FETCH(url, None)
    except CrawlError as exc:
        # v1.16: ohne angegebenes Schema erst https, bei reinem Verbindungsfehler http (kein Rückfall bei Zertifikatsfehlern)
        if '://' in domain_or_url.strip() or getattr(exc, 'kind', '') != 'network':
            raise
        url = 'http://' + url.split('://', 1)[1]
        home_url, ctype, data = FETCH(url, None)
        log.append('Website ohne funktionierendes HTTPS – unverschlüsselt (http) gelesen.')
    origin = home_url
    site_domain = (urlsplit(origin).hostname or '').lower()
    site_domain = site_domain[4:] if site_domain.startswith('www.') else site_domain
    text, links, mailtos, source_type = _decode(home_url, ctype, data)
    candidates = find_imprint_links(origin, links)
    if not candidates:
        root = f'{urlsplit(origin).scheme}://{urlsplit(origin).netloc}'
        candidates = [root + p for p in FALLBACK_PATHS]
        log.append('Kein Impressumslink auf der Startseite – Standardpfade geprüft.')
    best = None
    best_source = {home_url: _deobfuscate(text) + '\n' + text + '\n' + '\n'.join('mailto:' + m for m in mailtos)}
    for cand in candidates:
        SLEEP(REQUEST_DELAY)
        try:
            final, ctype2, data2 = FETCH(cand, origin)
        except CrawlError as exc:
            log.append(f'{cand}: {exc}')
            continue
        t2, links2, mailtos2, stype2 = _decode(final, ctype2, data2)
        if stype2 == 'impressum_html' and not re.search(r'impressum|imprint|legal notice|anbieterkennzeichnung|§ ?5 (tmg|ddg)|angaben gem', t2, re.I):
            # Seite ohne Impressumsmerkmale; evtl. verlinkt sie auf ein PDF-Impressum
            pdfs = [l for l in find_imprint_links(final, links2) if l.lower().endswith('.pdf')]
            if pdfs:
                candidates.extend(p for p in pdfs if p not in candidates)
            log.append(f'{final}: keine Impressumsmerkmale.')
            continue
        if stype2 == 'impressum_pdf' and not t2:
            log.append(f'{final}: PDF ohne auslesbaren Text – bitte manuell prüfen.')
            continue
        result = extract(t2, mailtos2, site_domain, include_persons)
        best = (final, stype2, result)
        best_source[final] = _deobfuscate(t2) + '\n' + t2 + '\n' + '\n'.join('mailto:' + m for m in mailtos2)
        break
    if not best:
        # Manche Seiten haben die Pflichtangaben direkt auf der Startseite (One-Pager)
        if re.search(r'angaben gem|§ ?5 (tmg|ddg)|registergericht|handelsregister|umsatzsteuer-id|ust-id', text, re.I):  # v1.16: nicht nur „Impressum“-Link
            best = (home_url, source_type, extract(text, mailtos, site_domain, include_persons))
            log.append('Impressumsangaben auf der Startseite gefunden.')
    if not best:
        return {'status': 'kein_impressum', 'home_url': home_url, 'imprint_url': None, 'source_type': None,
                'checked_at': _now(), 'log': log, 'entities': [], 'fields': {}, 'representatives': [],
                'warnings': ['Kein Impressum gefunden – Pflichtangabe fehlt oder ist nur per JavaScript/Grafik sichtbar.'],
                'completeness': {'found': 0, 'total': 10}, 'site_domain': site_domain}
    final, stype, result = best
    result.update({'status': 'ok', 'home_url': home_url, 'imprint_url': final, 'source_type': stype,
                   'checked_at': _now(), 'log': log, 'site_domain': site_domain})
    _attach_evidence(result, best_source.get(final, ''), final)
    result['structured'] = _structured(home_url, data)
    return result


def _attach_evidence(result, source_text, source_url):
    """Sprint 2: jeder Wert braucht einen Beleg im Originaltext, sonst wird er verworfen (bleibt leer)."""
    from .research.evidence import content_hash, validate_fields
    checked, rejected = validate_fields(result.get('fields') or {}, source_text, source_url, METHOD,
                                        chash=content_hash(source_text))
    result['fields'] = checked
    if rejected:
        result.setdefault('warnings', []).append('Nicht im Originaltext belegbar, daher verworfen: ' + ', '.join(rejected) + '.')
    result['completeness'] = {'found': sum(1 for v in checked.values() if v), 'total': len(checked)}


def _structured(home_url, data):
    """Strukturierte Angaben der Startseite (JSON-LD/Microdata) – mit Beleg im HTML-Quelltext."""
    from .research.evidence import structured_evidence
    from .research.extractors import structured
    from .research.fetchers.base import decode_html
    if not data or data[:5] == b'%PDF-':
        return {'organizations': [], 'jobpostings': [], 'evidence': []}
    page = decode_html(data) if isinstance(data, bytes) else data
    st = structured.extract(page, home_url)
    st['evidence'] = [e for org in st['organizations'][:3] for e in structured_evidence(org, home_url, page)]
    return st


def _now():
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
