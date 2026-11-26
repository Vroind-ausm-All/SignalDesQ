"""Personen und Rollen aus strukturierten Seitenteilen (Plan R2.1) – nur Standardbibliothek.

Quellen in dieser Reihenfolge: JSON-LD (schema.org Person, auch als employee/founder/member einer Organization),
Microdata (itemtype …/Person), HTML-Karten (Team-/Mitarbeiter-Kacheln) und Tabellen (Zeile mit Name und Funktion).
Die zeilenbasierten Regeln in ``public_contacts`` bleiben der Rückfall.

Belegvertrag v2 (``research.evidence``): Jede Person trägt für Name UND Funktion einen Beleg mit Fundstelle –
JSON-Pfad im JSON-LD-Block bzw. Textspanne im sichtbaren Seitentext (``visible_text``). Name und Funktion müssen aus
demselben Objekt bzw. derselben Karte/Tabellenzeile stammen; eine Person ohne Funktion ist kein Kandidat.
Keine abgeleiteten E-Mail-Muster: eine E-Mail wird nur übernommen, wenn sie wörtlich beim Objekt steht und zur Domain der
Website gehört; Mobilnummern werden nie übernommen (mögliche Privatnummer). Website-Inhalte sind Daten, keine Befehle.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

from .. import evidence as ev
from .. import roles

VERSION = 'personen-v1'
MAX_HTML = 2_000_000
MAX_PERSONS = 40
MAX_CARD_TEXT = 400
SKIP = {'script', 'style', 'noscript', 'template', 'svg', 'head', 'title', 'iframe'}
BLOCK = {'p', 'div', 'br', 'li', 'tr', 'td', 'th', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'section', 'article', 'header', 'footer',
         'address', 'dd', 'dt', 'table', 'ul', 'ol', 'hr', 'blockquote', 'main', 'nav', 'form', 'figcaption', 'figure', 'caption'}
VOID = {'br', 'hr', 'img', 'input', 'meta', 'link', 'source', 'wbr', 'area', 'col', 'embed', 'param', 'track'}
CARD_RX = re.compile(r'team|member|mitarbeit|person|employee|staff|vcard|profil|ansprechpartner|kontaktperson|management|vorstand|people', re.I)
LD_RE = re.compile(r'<script[^>]+type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)
NAME_TOKEN = re.compile(r"^[A-ZÄÖÜ][a-zäöüßà-ÿ]+(?:[-'][A-ZÄÖÜ][a-zäöüßà-ÿ]+)?$")
PARTICLES = {'von', 'van', 'de', 'der', 'den', 'zu', 'di', 'da', 'del', 'le'}
HONORIFICS = re.compile(r"^(?:(?:Prof\.|Dr\.(?:-Ing\.)?(?:\s?h\.\s?c\.)?|Dipl\.-[A-Za-zäöü]+\.?|Mag\.|Herr|Frau)\s+)+")
STOP = {'unser', 'unsere', 'unseren', 'kontakt', 'team', 'telefon', 'email', 'mehr', 'über', 'uns', 'startseite', 'impressum',
        'datenschutz', 'leistungen', 'kunden', 'service', 'karriere', 'news', 'presse', 'home', 'willkommen', 'jetzt', 'anfrage',
        'standort', 'ansprechpartner', 'management', 'geschäftsführung', 'vorstand', 'gmbh', 'ag', 'kg', 'mitarbeiter',
        'leitung', 'abteilung', 'vertrieb', 'marketing', 'technik', 'büro', 'zentrale', 'fax', 'mobil', 'termin', 'online',
        'produkte', 'lösungen', 'referenzen', 'downloads', 'aktuelles', 'jobs', 'die', 'der', 'das', 'und', 'für', 'mit'}
EMAIL_RE = re.compile(r'^[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}$')
MOBILE_RE = re.compile(r'^(?:\+49|0049|0)\s*\(?0?\)?\s*1[5-7]')


def person_name(text):
    """Vollständiger Personenname (ohne Anrede/Titel) oder ''. Mindestens Vor- und Nachname, keine Rollen- oder Menüwörter."""
    t = re.sub(r'\s+', ' ', str(text or '')).strip(' ,;:–-|')
    if not t or len(t) > 80:
        return ''
    t = HONORIFICS.sub('', t).strip()
    tokens = t.split(' ')
    if not 2 <= len(tokens) <= 5:
        return ''
    if not (NAME_TOKEN.match(tokens[0]) and NAME_TOKEN.match(tokens[-1])):
        return ''
    for tok in tokens:
        if tok.casefold() in STOP:
            return ''
        if not (NAME_TOKEN.match(tok) or tok in PARTICLES):
            return ''
    if roles.is_title(t):
        return ''
    return t


def _host(url):
    h = (urlsplit(url or '').hostname or '').lower()
    return h[4:] if h.startswith('www.') else h


def business_email(value, page_url):
    v = str(value or '').strip()
    v = v[7:] if v.lower().startswith('mailto:') else v
    if not EMAIL_RE.match(v) or len(v) > 160:
        return ''
    dom, host = v.rsplit('@', 1)[1].lower(), _host(page_url)
    return v if host and (dom == host or host.endswith('.' + dom) or dom.endswith('.' + host)) else ''


def business_phone(value):
    v = re.sub(r'\s+', ' ', str(value or '')).strip()
    digits = re.sub(r'\D', '', v)
    if not 7 <= len(digits) <= 17 or MOBILE_RE.match(v):
        return ''
    return v


# ---------------------------------------------------------------- sichtbarer Text mit Knotenbaum

class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.pos, self.skip = [], 0, 0
        self.root = {'tag': '#root', 'attrs': {}, 'start': 0, 'end': 0, 'children': [], 'parent': None}
        self.cur = self.root

    def _emit(self, s):
        if self.skip or not s:
            return
        self.parts.append(s)
        self.pos += len(s)

    def handle_starttag(self, tag, attrs):
        if tag in BLOCK:
            self._emit('\n')
        if tag in VOID:
            return
        node = {'tag': tag, 'attrs': {k: (v or '') for k, v in attrs}, 'start': self.pos, 'end': self.pos, 'children': [], 'parent': self.cur}
        self.cur['children'].append(node)
        self.cur = node
        if tag in SKIP:
            self.skip += 1

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n['tag'] != tag:
            n = n['parent']
        if n is self.root:
            return
        c = self.cur
        while True:  # alle offenen Knoten bis einschließlich n schließen
            c['end'] = self.pos
            if c['tag'] in SKIP:
                self.skip -= 1
            if c is n:
                break
            c = c['parent']
        self.cur = n['parent']
        if tag in BLOCK:
            self._emit('\n')

    def handle_data(self, data):
        self._emit(re.sub(r'[ \t\r\f\v\xa0]+', ' ', data.replace('\n', ' ')))

    def close(self):
        super().close()
        c = self.cur
        while c is not self.root:
            c['end'] = self.pos
            c = c['parent']
        self.root['end'] = self.pos


def parse_tree(page_html):
    t = _Tree()
    try:
        t.feed(page_html or '')
        t.close()
    except Exception:  # noqa: BLE001 – kaputtes HTML liefert, was bis dahin lesbar war
        pass
    return ''.join(t.parts), t.root


def visible_text(page_html):
    """Basis der Textspannen (``basis='visible_text'``) – deterministisch aus dem HTML."""
    return parse_tree(str(page_html or '')[:MAX_HTML])[0]


def _walk(node):
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n['children']))


def _lines(text, a, b):
    """Nicht leere Zeilen im Bereich [a, b) mit Lage im Gesamttext: [(start, end, zeile)]."""
    out, pos = [], a
    for raw in text[a:b].split('\n'):
        s = raw.strip()
        if s:
            off = pos + raw.index(s)
            out.append((off, off + len(s), s))
        pos += len(raw) + 1
    return out


# ---------------------------------------------------------------- JSON-LD

PERSON_KEYS = ('employee', 'employees', 'founder', 'founders', 'member', 'members', 'contactPoint', 'alumni', 'mainEntity', 'author',
               'itemListElement', 'item', 'about', 'subjectOf')


def ld_blocks(page_html):
    """Alle JSON-LD-Blöcke in Seitenreihenfolge (ungültige als None, damit die Blocknummer stabil bleibt)."""
    blocks = []
    for raw in LD_RE.findall(page_html or '')[:20]:
        raw = re.sub(r'^\s*(<!--|<!\[CDATA\[)|(-->|\]\]>)\s*$', '', raw.strip()).strip()
        if len(raw) > 200_000:
            blocks.append(None)
            continue
        try:
            blocks.append(json.loads(raw))
        except ValueError:
            try:
                blocks.append(json.loads(re.sub(r',\s*([}\]])', r'\1', html_lib.unescape(raw))))
            except ValueError:
                blocks.append(None)
    return blocks


def _types(obj):
    t = obj.get('@type') or ''
    t = t if isinstance(t, list) else [t]
    return {str(x).rsplit('/', 1)[-1].lower() for x in t if x}


def _str_at(obj, key, path):
    """Textwert unter key (direkt, erster Listeneintrag oder .name) → (wert, pfad) oder ('', None)."""
    v = obj.get(key)
    if isinstance(v, list) and v:
        v, path = v[0], path + [key, 0]
    else:
        path = path + [key]
    if isinstance(v, dict):
        if isinstance(v.get('name'), str):
            return v['name'].strip(), path + ['name']
        return '', None
    if isinstance(v, str):
        return v.strip(), path
    return '', None


def _ld_persons(blocks, url, meta):
    found = []

    def visit(obj, path, org_name, org_path, block, depth):
        if depth > 8 or len(found) >= MAX_PERSONS:
            return
        if isinstance(obj, list):
            for i, x in enumerate(obj[:200]):
                visit(x, path + [i], org_name, org_path, block, depth + 1)
            return
        if not isinstance(obj, dict):
            return
        types = _types(obj)
        if 'person' in types:
            found.append((obj, path, org_name, org_path, block))
        name, npath = _str_at(obj, 'legalName', path) if 'person' not in types else ('', None)
        if not name and 'person' not in types:
            name, npath = _str_at(obj, 'name', path)
        is_org = bool(types) and 'person' not in types and not types <= {'webpage', 'website', 'breadcrumblist', 'listitem', 'itemlist',
                                                                          'aboutpage', 'contactpage', 'imageobject', 'searchaction'}
        for key in PERSON_KEYS + ('@graph',):
            if key in obj and isinstance(obj[key], (dict, list)):
                visit(obj[key], path + [key], name if is_org and name else org_name, npath if is_org and name else org_path,
                      block, depth + 1)

    for b, data in enumerate(blocks):
        if data is not None:
            visit(data, [], '', None, b, 0)
    out = []
    for obj, path, org_name, org_path, block in found:
        data = blocks[block]
        name, npath = _str_at(obj, 'name', path)
        name = person_name(name) and name
        title, tpath = _str_at(obj, 'jobTitle', path)
        if not title:
            title, tpath = _str_at(obj, 'roleName', path)
        if not (name and title and roles.normalize(title)):
            continue
        refs = {'full_name': ev.json_ref('full_name', name, data, block, npath, url, VERSION + ':jsonld', **meta),
                'job_title': ev.json_ref('job_title', title, data, block, tpath, url, VERSION + ':jsonld', **meta)}
        works, wpath = _str_at(obj, 'worksFor', path)
        if not works and org_name:
            works, wpath = org_name, org_path
        if works and wpath:
            refs['employer'] = ev.json_ref('employer', works, data, block, wpath, url, VERSION + ':jsonld', **meta)
        mail, mpath = _str_at(obj, 'email', path)
        mail_ok = business_email(mail, url)
        if mail_ok:
            refs['business_email'] = ev.json_ref('business_email', mail, data, block, mpath, url, VERSION + ':jsonld', **meta)
        tel, ppath = _str_at(obj, 'telephone', path)
        tel_ok = business_phone(tel)
        if tel_ok:
            refs['business_phone'] = ev.json_ref('business_phone', tel, data, block, ppath, url, VERSION + ':jsonld', **meta)
        out.append({'full_name': name, 'job_title': title, 'employer': works if refs.get('employer') else '',
                    'business_email': mail_ok.removeprefix('mailto:') if refs.get('business_email') else '',
                    'business_phone': tel_ok if refs.get('business_phone') else '', 'method': 'jsonld',
                    'evidence': f'JSON-LD Person: name = {name}; jobTitle = {title}' + (f'; worksFor = {works}' if works else ''),
                    'locator_group': {'kind': 'json', 'block': block, 'path': path}, 'evidence_refs': {k: v for k, v in refs.items() if v}})
    return out


# ---------------------------------------------------------------- Microdata, Karten, Tabellen

def _text_person(text, node, url, meta, method, name_span, title_span, extra=None):
    a, b = node['start'], node['end']
    name, title = text[name_span[0]:name_span[1]], text[title_span[0]:title_span[1]]
    ext = VERSION + ':' + method
    refs = {'full_name': ev.text_ref('full_name', name, text, url, ext, basis='visible_text', start_hint=name_span[0], end_hint=name_span[1], **meta),
            'job_title': ev.text_ref('job_title', title, text, url, ext, basis='visible_text', start_hint=title_span[0], end_hint=title_span[1], **meta)}
    person = {'full_name': name, 'job_title': title, 'employer': '', 'business_email': '', 'business_phone': '', 'method': method,
              'evidence': re.sub(r'\s+', ' ', text[a:b]).strip()[:350],
              'locator_group': {'kind': 'text', 'basis': 'visible_text', 'start': a, 'end': b}}
    for field, (value, span) in (extra or {}).items():
        r = ev.text_ref(field, value, text, url, ext, basis='visible_text', start_hint=span[0], end_hint=span[1], **meta)
        if r:
            refs[field] = r
            person[field] = value
    person['evidence_refs'] = {k: v for k, v in refs.items() if v}
    return person


def _name_in_line(line_start, line):
    """Name am Zeilenanfang oder hinter „Rolle:“ / vor „, Rolle“ → (start, end) im Gesamttext oder None."""
    full = person_name(line)
    if full:
        off = line.find(full)
        return (line_start + off, line_start + off + len(full))
    for part in re.split(r'\s*[:,|–—]\s*|\s+-\s+', line):
        n = person_name(part)
        if n and len(re.split(r'\s*[:,|–—]\s*|\s+-\s+', line)) > 1:
            off = line.find(n)
            return (line_start + off, line_start + off + len(n))
    return None


def _title_in_line(line_start, line, name_span=None):
    rel = None
    for part in re.split(r'\s*[:,|–—]\s*|\s+-\s+', line):
        if part and roles.is_title(part) and not person_name(part):
            off = line.find(part)
            rel = (off, off + len(part))
            break
    if rel is None:
        return None
    span = (line_start + rel[0], line_start + rel[1])
    if name_span and not (span[1] <= name_span[0] or span[0] >= name_span[1]):
        return None
    return span


def _card_person(text, node, url, meta, method):
    lines = _lines(text, node['start'], node['end'])
    if not lines or len(text[node['start']:node['end']]) > MAX_CARD_TEXT:
        return None
    names = [(i, s) for i, (a, _b, line) in enumerate(lines) if (s := _name_in_line(a, line))]
    if len({text[s[0]:s[1]] for _, s in names}) != 1:
        return None  # keine oder mehrere Personen in der Karte – zu unsicher
    i, nspan = names[0]
    tspan = _title_in_line(lines[i][0], lines[i][2], nspan)
    for j in (i + 1, i - 1, i + 2):  # Funktion direkt unter/über dem Namen
        if tspan or not 0 <= j < len(lines):
            continue
        if not _name_in_line(lines[j][0], lines[j][2]):
            tspan = _title_in_line(lines[j][0], lines[j][2])
    if not tspan:
        return None
    extra = {}
    for a, _b, line in lines:
        m = re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', line)
        if m and business_email(m.group(0), url):
            extra['business_email'] = (m.group(0), (a + m.start(), a + m.end()))
        d = re.search(r'\b(?:durchwahl|direkt(?:wahl)?|tel(?:efon)?\.?\s*direkt)\b\s*:?\s*((?:\+49|0049|0)(?:[\s./()-]*\d){6,15})', line, re.I)
        if d and business_phone(d.group(1)):
            extra['business_phone'] = (d.group(1), (a + d.start(1), a + d.end(1)))
    return _text_person(text, node, url, meta, method, nspan, tspan, extra)


def _microdata_person(text, node, url, meta):
    props = {}
    for n in _walk(node):
        if n is node:
            continue
        p = n['attrs'].get('itemprop')
        if p and p not in props and n['end'] > n['start']:
            s = text[n['start']:n['end']]
            lead = len(s) - len(s.lstrip())
            core = s.strip()
            if core:
                props[p] = (n['start'] + lead, n['start'] + lead + len(core))
    if 'name' not in props or 'jobTitle' not in props:
        return None
    nspan, tspan = props['name'], props['jobTitle']
    name, title = text[nspan[0]:nspan[1]], text[tspan[0]:tspan[1]]
    if not person_name(name) or person_name(name) != HONORIFICS.sub('', name).strip() or not roles.normalize(title):
        return None
    off = name.find(person_name(name))
    nspan = (nspan[0] + off, nspan[0] + off + len(person_name(name)))
    extra = {}
    if 'email' in props and business_email(text[props['email'][0]:props['email'][1]], url):
        extra['business_email'] = (text[props['email'][0]:props['email'][1]], props['email'])
    if 'worksFor' in props:
        extra['employer'] = (text[props['worksFor'][0]:props['worksFor'][1]], props['worksFor'])
    return _text_person(text, node, url, meta, 'microdata', nspan, tspan, extra)


def _table_persons(text, table, url, meta):
    out, col_name, col_title = [], None, None
    for tr in (n for n in _walk(table) if n['tag'] == 'tr'):
        cells = [c for c in tr['children'] if c['tag'] in ('td', 'th')]
        texts = [text[c['start']:c['end']].strip() for c in cells]
        if all(c['tag'] == 'th' for c in cells) and texts:
            low = [t.casefold() for t in texts]
            col_name = next((i for i, t in enumerate(low) if t in ('name', 'ansprechpartner', 'person', 'mitarbeiter/in', 'mitarbeiter')), None)
            col_title = next((i for i, t in enumerate(low) if t in ('funktion', 'position', 'rolle', 'aufgabe', 'bereich', 'titel', 'zuständigkeit')), None)
            continue
        name_cells = [i for i, t in enumerate(texts) if person_name(t)]
        title_cells = [i for i, t in enumerate(texts) if roles.is_title(t) and not person_name(t)]
        ni = col_name if col_name is not None and col_name in name_cells else (name_cells[0] if len(name_cells) == 1 else None)
        ti = col_title if col_title is not None and col_title in title_cells else (title_cells[0] if len(title_cells) == 1 else None)
        if ni is None or ti is None or ni == ti:
            continue
        nc, tc = cells[ni], cells[ti]
        nraw, traw = text[nc['start']:nc['end']], text[tc['start']:tc['end']]
        n = person_name(nraw)
        noff, toff = nraw.find(n), len(traw) - len(traw.lstrip())
        out.append(_text_person(text, tr, url, meta, 'tabelle', (nc['start'] + noff, nc['start'] + noff + len(n)),
                                (tc['start'] + toff, tc['start'] + toff + len(traw.strip()))))
    return out


def _html_persons(text, root, url, meta):
    out, used = [], []

    def inside(node):
        return any(u['start'] <= node['start'] and node['end'] <= u['end'] for u in used)

    nodes = list(_walk(root))
    for n in nodes:  # Microdata zuerst (ausdrücklich ausgezeichnet)
        if 'itemscope' in n['attrs'] and n['attrs'].get('itemtype', '').rstrip('/').rsplit('/', 1)[-1].lower() == 'person':
            p = _microdata_person(text, n, url, meta)
            if p:
                out.append(p)
                used.append(n)
    for n in nodes:
        if n['tag'] == 'table' and not inside(n):
            rows = _table_persons(text, n, url, meta)
            if rows:
                out.extend(rows)
                used.append(n)
    # Karten: innerste passende Knoten zuerst (kleinste Spanne), damit eine Teamliste nicht als eine Karte gilt
    cards = [n for n in nodes if n['tag'] not in ('table', 'tr', 'td', 'html', 'body', '#root')
             and CARD_RX.search(' '.join((n['attrs'].get('class', ''), n['attrs'].get('id', ''))))]
    for n in sorted(cards, key=lambda x: x['end'] - x['start']):
        if inside(n) or any(n['start'] <= u['start'] and u['end'] <= n['end'] for u in used):
            continue
        p = _card_person(text, n, url, meta, 'karte')
        if p:
            out.append(p)
            used.append(n)
    return out


def extract(page_html, url, chash='', fetched_at='', published_at=''):
    """→ {'persons': [...], 'visible_text_hash': 'sha256:…', 'counts': {...}, 'version': VERSION}

    Jede Person: full_name, job_title, employer, business_email, business_phone, method (jsonld/microdata/tabelle/karte),
    evidence (Wortlaut), locator_group (gemeinsame Fundstelle von Name und Funktion), evidence_refs (Belege v2 je Feld)."""
    page_html = str(page_html or '')[:MAX_HTML]
    meta = {'chash': chash or ev.content_hash(page_html), 'fetched_at': fetched_at or ev.now(), 'published_at': published_at}
    blocks = ld_blocks(page_html)
    persons = _ld_persons(blocks, url, meta)
    text, root = parse_tree(page_html)
    persons += _html_persons(text, root, url, meta)
    seen, out = set(), []
    for p in persons:
        key = p['full_name'].casefold()
        if key in seen:
            continue
        if not (p['evidence_refs'].get('full_name') and p['evidence_refs'].get('job_title')):
            continue  # ohne Beleg für Name UND Funktion kein Kandidat
        seen.add(key)
        out.append(p)
    counts = {}
    for p in out:
        counts[p['method']] = counts.get(p['method'], 0) + 1
    return {'persons': out[:MAX_PERSONS], 'visible_text_hash': ev.text_hash(text), 'counts': counts, 'version': VERSION}


def verify(person, page_html):
    """Gegenprüfung aller Belege einer Person am HTML (z. B. nach erneutem Abruf)."""
    page_html = str(page_html or '')[:MAX_HTML]
    text, blocks = visible_text(page_html), ld_blocks(page_html)
    refs = person.get('evidence_refs') or {}
    return bool(refs) and all(ev.verify_ref(r, text=text, blocks=blocks) for r in refs.values())
