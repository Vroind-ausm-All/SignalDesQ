"""Firmenidentität und Dubletten (Masterplan 2.0, Sprint 4).

Grundsatz: Dubletten zuverlässig erkennen – aber fremde Firmen nie versehentlich zusammenführen.
Entscheidung je Paar: 'same' (sicher dieselbe Firma → automatisch zusammenführen), 'possible' (Prüfung nötig →
nicht doppelt auflisten, sondern beim Haupteintrag zur Entscheidung zeigen) oder 'different'.

Vertrauensstufen (Plan, Abschnitt 5): (1) LEI bzw. Registernummer + Gericht/Ort, (2) belegte eigene Domain,
(3) normalisierter Name + Rechtsform + Anschrift als Abgleich-Kandidat (RapidFuzz, falls installiert – sonst difflib).
Harte Gegenbelege (verschiedene LEI, verschiedene Registernummer, verschiedene Rechtsform, verschiedene Orte) schließen
ein Zusammenführen aus – Niederlassungen, Töchter, Verwaltungs-GmbH und KG bleiben getrennt.
"""
from __future__ import annotations

import difflib
import functools
import itertools
import re
import unicodedata

# Plattformen: gleiche Domain heißt hier NICHT gleiche Firma
PLATFORM_DOMAINS = {'facebook.com', 'instagram.com', 'linkedin.com', 'xing.com', 'twitter.com', 'x.com', 'youtube.com', 'linktr.ee',
                    'google.com', 'goo.gl', 'maps.google.com', 'business.site', 'sites.google.com', 'wixsite.com', 'jimdo.com',
                    'jimdosite.com', 'wordpress.com', 'blogspot.com', 'eventbrite.de', 'gelbeseiten.de', 'dasoertliche.de', 'branchenbuch.de',
                    'yelp.de', 'tripadvisor.de', 'stepstone.de', 'indeed.com', 'kununu.com', 'northdata.de', 'firmenwissen.de', 'onepage.me',
                    'beepworld.de', 'npage.de', 'page4.com', 'web.de', 'gmx.de', 't-online.de', 'icloud.com'}

_LEGAL = [  # Reihenfolge wichtig: Zusammengesetzte Formen zuerst
    (r'gmbh\s*(?:&|und)\s*co\.?\s*kgaa', 'gmbh_co_kgaa'), (r'gmbh\s*(?:&|und)\s*co\.?\s*(?:kg|kommanditgesellschaft)', 'gmbh_co_kg'),
    (r'ug\s*(?:\(haftungsbeschraenkt\))?\s*(?:&|und)\s*co\.?\s*kg', 'ug_co_kg'), (r'ag\s*(?:&|und)\s*co\.?\s*kg', 'ag_co_kg'),
    (r'se\s*(?:&|und)\s*co\.?\s*kg', 'se_co_kg'), (r'(?:&|und)\s*co\.?\s*kg', 'co_kg'),
    (r'gesellschaft mit beschraenkter haftung', 'gmbh'), (r'g\.?\s?m\.?\s?b\.?\s?h\.?', 'gmbh'), (r'ggmbh|gemeinnuetzige gmbh', 'ggmbh'),
    (r'mbh', 'gmbh'), (r'unternehmergesellschaft(?:\s*\(haftungsbeschraenkt\))?|ug\s*\(haftungsbeschraenkt\)|\bug\b', 'ug'),
    (r'aktiengesellschaft|\bag\b', 'ag'), (r'kommanditgesellschaft auf aktien|\bkgaa\b', 'kgaa'), (r'europaeische gesellschaft|\bse\b', 'se'),
    (r'kommanditgesellschaft|\bkg\b', 'kg'), (r'offene handelsgesellschaft|\bohg\b', 'ohg'),
    (r'gesellschaft buergerlichen rechts|\begbr\b|\bgbr\b', 'gbr'), (r'partg\s*mbb|partnerschaftsgesellschaft', 'partg'), (r'\bpartg\b', 'partg'),
    (r'eingetragene genossenschaft|\beg\b', 'eg'), (r'eingetragener verein|\be\.?\s?v\b\.?', 'ev'),
    (r'eingetragene[rs]? kauf(?:mann|frau)|\be\.?\s?k\b\.?|\be\.?\s?kfm\b\.?|\be\.?\s?kfr\b\.?', 'ek'),
    (r'\bltd\b\.?|\blimited\b', 'ltd'), (r'\binc\b\.?', 'inc'), (r'\bllc\b', 'llc'), (r'\bb\.?\s?v\b\.?', 'bv'),
]
_LEGAL_RX = [(re.compile(p), f) for p, f in _LEGAL]
# Gleichwertige Schreibweisen (keine Unterscheidung)
FAMILY_EQUIV = {'ggmbh': 'gmbh', 'co_kg': 'gmbh_co_kg'}
STOP = {'und', 'the', 'der', 'die', 'das', 'fuer', 'von', 'in', 'am', 'an', 'co', 'gesellschaft', 'firma', 'inh', 'inhaber', 'deutschland',
        'germany', 'gruppe', 'group', 'haftungsbeschraenkt'}


try:  # v1.19: einmal importieren – ein fehlgeschlagener Import je Vergleich kostete ein Drittel der Rechenzeit
    from rapidfuzz import fuzz as _FUZZ
except Exception:  # noqa: BLE001 – RapidFuzz ist optional
    _FUZZ = None


def translit(s):
    s = unicodedata.normalize('NFKC', str(s or '')).casefold()
    for a, b in (('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss'), ('&', ' & ')):
        s = s.replace(a, b)
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()


@functools.lru_cache(maxsize=50_000)
def legal_family(name):
    t = translit(name)
    for rx, fam in _LEGAL_RX:
        if rx.search(t):
            return FAMILY_EQUIV.get(fam, fam)
    return ''


def family_of(item):
    """Rechtsform-Familie aus Name UND Rechtsform-Feld – die spezifischere gewinnt (Name „… GmbH & Co. KG“ mit Feld „GmbH“ → GmbH & Co. KG)."""
    fn, ff = legal_family(item.get('name')), legal_family(item.get('legal_form') or '')
    if fn and ff and fn != ff:
        return fn if '_co_' in fn or fn.startswith('co_') else ff if '_co_' in ff else fn
    return fn or ff


def core_tokens(name):
    """Name ohne Rechtsform, Satzzeichen und Füllwörter – transliteriert (Müller = Mueller), sortierbar."""
    return list(_core_tokens(name or ''))


@functools.lru_cache(maxsize=50_000)
def _core_tokens(name):
    t = translit(name)
    t = re.sub(r'["\'„“”‚‘’`´]', ' ', t)
    for rx, _ in _LEGAL_RX:
        t = rx.sub(' ', t)
    return tuple(w for w in re.split(r'[^a-z0-9]+', t) if w and w not in STOP)


def core_name(name, cache=True):
    """cache=False für Massenimporte (Katalog): nichts zwischenspeichern, damit der Speicher begrenzt bleibt."""
    return ' '.join(_core_tokens(name or '') if cache else _core_tokens.__wrapped__(name or ''))


def _ratio(x, y, floor):
    """difflib-Ähnlichkeit; liegt schon die schnelle Obergrenze unter `floor`, wird diese zurückgegeben (Ergebnis < floor
    bleibt < floor – die Entscheidung ist identisch, nur ohne teure Vollberechnung)."""
    sm = difflib.SequenceMatcher(None, x, y)
    upper = sm.real_quick_ratio()
    if upper < floor:
        return upper
    upper = sm.quick_ratio()
    if upper < floor:
        return upper
    return sm.ratio()


def name_similarity(a, b, floor=0.0):
    ta, tb = _core_tokens(a or ''), _core_tokens(b or '')
    if not ta or not tb:
        return 0.0
    sa, sb = ' '.join(sorted(ta)), ' '.join(sorted(tb))
    if sa == sb or ''.join(ta) == ''.join(tb):  # gleiche Wörter bzw. „Reith-Spezialkabel“ = „Reith Spezialkabel“
        return 1.0
    if _FUZZ is not None:
        sort = _FUZZ.token_sort_ratio(sa, sb) / 100
        ratio = _FUZZ.ratio(' '.join(ta), ' '.join(tb)) / 100
    else:
        sort = _ratio(sa, sb, floor)
        ratio = _ratio(' '.join(ta), ' '.join(tb), floor)
    return round(max(sort, ratio), 3)


def engine():
    try:
        import rapidfuzz  # noqa: F401
        return 'rapidfuzz'
    except Exception:  # noqa: BLE001
        return 'difflib'


@functools.lru_cache(maxsize=50_000)
def norm_domain(url):
    url = (url or '').strip().lower()
    if not url:
        return ''
    host = re.sub(r'^[a-z]+://', '', url).split('/')[0].split(':')[0].rstrip('.')
    host = host[4:] if host.startswith('www.') else host
    if host in PLATFORM_DOMAINS or any(host.endswith('.' + p) for p in PLATFORM_DOMAINS):
        return ''
    return host


@functools.lru_cache(maxsize=50_000)
def norm_register(reg):
    m = re.search(r'\b(HRA|HRB|GNR|GSR|PR|VR)\s*[-.:]?\s*(\d{1,7})\s?([A-Z]{0,2})\b', (reg or '').upper())
    return f'{m.group(1)}{m.group(2)}{m.group(3)}' if m else ''


@functools.lru_cache(maxsize=50_000)
def norm_city(city):
    t = translit(city)
    t = re.sub(r'\s+(am|an der|an den|bei|im|in der|ob der)\s.*$|\s*\(.*$', '', t)
    return re.sub(r'[^a-z]+', ' ', t).strip().split(' ')[0] if t.strip() else ''


def _location(a, b):
    """'same' | 'compatible' (eine Seite ohne Ort) | 'different'"""
    za, zb = (a.get('zip') or '').strip(), (b.get('zip') or '').strip()
    ca, cb = norm_city(a.get('city')), norm_city(b.get('city'))
    if za and zb and za == zb:
        return 'same'
    if ca and cb:
        return 'same' if ca == cb else 'different'
    if za and zb:  # nur PLZ bekannt: gleiche Leitregion (erste 3 Ziffern) gilt als gleicher Ort
        return 'same' if za[:3] == zb[:3] else 'different'
    return 'compatible'


def decide(a, b):
    """Vergleicht zwei Firmen-Datensätze (dict mit name, lei, register_id, website, zip, city, legal_form).
    Gibt (verdict, score, reason) zurück."""
    la, lb = (a.get('lei') or '').upper(), (b.get('lei') or '').upper()
    if la and lb:
        return ('same', 1.0, 'gleiche LEI') if la == lb else ('different', 0.0, 'verschiedene LEI')
    ra, rb = norm_register(a.get('register_id')), norm_register(b.get('register_id'))
    loc = _location(a, b)
    if ra and rb:
        if ra != rb:
            return 'different', 0.0, 'verschiedene Registernummer'
        if loc != 'different':
            return 'same', 1.0, f'gleiche Registernummer {a.get("register_id")}'
    fa, fb = family_of(a), family_of(b)
    if fa and fb and fa != fb:
        return 'different', 0.0, f'verschiedene Rechtsform ({fa} / {fb})'
    da, db = norm_domain(a.get('website') or ''), norm_domain(b.get('website') or '')
    if da and db and da == db:
        if loc == 'same' or name_similarity(a.get('name'), b.get('name'), 0.6) >= 0.6:
            return 'same', 1.0, f'gleiche Website {da}'
        return 'possible', 0.8, f'gleiche Website {da}, aber andere Namen'
    if loc == 'different':
        return 'different', 0.0, 'verschiedene Orte'
    sim = name_similarity(a.get('name'), b.get('name'), 0.85)  # erst hier rechnen – vorher entscheiden harte Merkmale
    distinctive = len(''.join(core_tokens(a.get('name')))) >= 8 and len(core_tokens(a.get('name'))) >= 2
    if sim == 1.0:
        # Automatisch nur bei gleichem Kernnamen (Umlaute, Wortfolge, Bindestriche egal) UND gleichem Ort –
        # ohne Ort nur bei unverwechselbarem Namen und gleicher Rechtsform („Müller GmbH“ bleibt eine Prüffrage)
        if loc == 'same' or (fa and fb and fa == fb and distinctive):
            return 'same', sim, 'gleicher Name' + (' · gleicher Ort' if loc == 'same' else ' · gleiche Rechtsform')
        return 'possible', sim, 'gleicher Name, Ort fehlt auf einer Seite'
    if sim >= 0.95 and loc != 'same':
        return 'possible', sim, f'Name {int(sim * 100)} % gleich, Ort fehlt auf einer Seite'
    if sim >= 0.85:
        return 'possible', sim, f'Name {int(sim * 100)} % ähnlich' + (' · gleicher Ort' if loc == 'same' else '')
    return 'different', sim, 'Name zu verschieden'


def block_keys(item):
    """Blöcke für den schnellen Abgleich (nicht jedes Paar vergleichen): erstes und längstes Namenswort, Domain, Register, LEI."""
    keys = set()
    toks = core_tokens(item.get('name'))
    if toks:
        keys.add('f:' + ' '.join(sorted(toks)))  # exakter Kernname (Wortreihenfolge egal)
        keys.add('t:' + toks[0][:6])
        keys.add('t:' + max(toks, key=len)[:6])
        keys.add('g:' + ''.join(toks)[:8])
    if norm_domain(item.get('website')):
        keys.add('d:' + norm_domain(item.get('website')))
    if norm_register(item.get('register_id')):
        keys.add('r:' + norm_register(item.get('register_id')))
    if item.get('lei'):
        keys.add('l:' + item['lei'].upper())
    return keys


MAX_BLOCK = 400
MAX_SCAN = 3000  # Obergrenze je Block, falls nur riesige Blöcke passen
STRONG = ('gleiche LEI', 'gleiche Registernummer', 'gleiche Website')


class Index:
    """Blockierter Index für den Dubletten-Abgleich (Kandidaten oder Leads)."""

    def __init__(self):
        self.blocks, self.items = {}, {}

    def add(self, key, item):
        self.items[key] = item
        for b in block_keys(item):
            self.blocks.setdefault(b, set()).add(key)

    def best(self, item, exclude=()):
        """Bester Treffer: ('same'|'possible', key, score, reason) oder None. 'same' schlägt 'possible'.
        Passt ein Datensatz nur über den Namen zu mehreren verschiedenen Firmen (z. B. ohne Ort), ist er mehrdeutig → nur 'possible'."""
        seen, best, same_keys = set(), None, []
        blocks = [b for b in block_keys(item) if b in self.blocks]
        # Häufige Namensanfänge („Autohaus …“) ergeben riesige Blöcke – die überspringen, solange ein genauerer Block da ist
        small = [b for b in blocks if b[0] in 'fdrl' or len(self.blocks[b]) <= MAX_BLOCK]
        for b in small or sorted(blocks, key=lambda x: len(self.blocks[x]))[:1]:
            for key in itertools.islice(self.blocks.get(b, ()), MAX_SCAN):
                if key in seen or key in exclude:
                    continue
                seen.add(key)
                verdict, score, reason = decide(item, self.items[key])
                if verdict == 'different':
                    continue
                if verdict == 'same':
                    same_keys.append(key)
                rank = (verdict == 'same', score)
                if best is None or rank > (best[0] == 'same', best[2]):
                    best = (verdict, key, score, reason)
        if best and best[0] == 'same' and not best[3].startswith(STRONG) and len(same_keys) > 1:
            base = {str(k).split(':')[0] for k in same_keys}
            if len(base) > 1 and any(decide(self.items[k], self.items[best[1]])[0] == 'different' for k in same_keys if k != best[1]):
                best = ('possible', best[1], best[2], best[3] + ' · passt zu mehreren Firmen')
        return best
