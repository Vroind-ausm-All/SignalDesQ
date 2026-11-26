"""Berufliche Titel → normalisierte Rolle und Abteilung (Plan R2.2).

Nur Titel, die auf der Quelle stehen, werden eingeordnet; nichts wird geraten. Eine Rolle sagt nichts über Budget- oder
Entscheidungsbefugnis und ist nie eine Kontakterlaubnis. Unbekannte Titel bleiben „unklar“ statt in eine Schublade gedrückt.
Reihenfolge der Regeln: spezifisch vor allgemein (z. B. „Leitung Marketing“ vor „Leitung“).
"""
from __future__ import annotations

import re

VERSION = 'rollen-v1'

# (Schlüssel, Bezeichnung, Abteilung, Ebene, Muster)
RULES = (
    ('vorstand', 'Vorstand', 'Geschäftsleitung', 'leitung',
     r'\bvorstand\w*|\bvorstandsvorsitz\w*|\bchief executive officer\b|\bceo\b'),
    ('geschaeftsfuehrung', 'Geschäftsführung', 'Geschäftsleitung', 'leitung',
     r'geschäftsführ\w*|geschaeftsfuehr\w*|geschäftsleitung|\bmanaging director\b|\bgeneral manager\b'),
    ('inhaber', 'Inhaber/in', 'Geschäftsleitung', 'leitung', r'\binhaber\w*|\beigentümer\w*|\bowner\b'),
    ('gruender', 'Gründer/in', 'Geschäftsleitung', 'leitung', r'\bgründer\w*|\bmitgründer\w*|\bco-?founder\b|\bfounder\b'),
    ('prokura', 'Prokurist/in', 'Geschäftsleitung', 'leitung', r'\bprokurist\w*|\bprokura\b'),
    ('finanzen_leitung', 'Leitung Finanzen', 'Finanzen', 'leitung',
     r'\bcfo\b|\bchief financial officer\b|kaufmännische\w* leit\w*|\b(?:leit\w*|head of)\s+(?:finanz\w*|finance|controlling|buchhaltung|rechnungswesen)|finanzleit\w*'),
    ('it_leitung', 'Leitung IT / Digitalisierung', 'IT / Digitalisierung', 'leitung',
     r'\bcto\b|\bcio\b|\bcdo\b|\bchief (?:technology|information|digital) officer\b|\bit[ -]?leit\w*|\bleit\w* (?:der )?it\b|'
     r'digitalisierungsleit\w*|\bhead of (?:it|digital\w*|technology|engineering)\b|\bleit\w* digital\w*'),
    ('marketing_leitung', 'Leitung Marketing', 'Marketing', 'leitung',
     r'\bcmo\b|\bchief marketing officer\b|marketing[ -]?leit\w*|\bleit\w* (?:des )?marketing\b|\bhead of marketing\b|'
     r'\bmarketing director\b|\bbrand[ -]?(?:director|leit\w*)\b'),
    ('vertrieb_leitung', 'Leitung Vertrieb', 'Vertrieb', 'leitung',
     r'\bcso\b|\bchief sales officer\b|vertriebsleit\w*|\bleit\w* (?:des )?vertrieb\w*|\bhead of sales\b|\bsales director\b|verkaufsleit\w*'),
    ('personal_leitung', 'Leitung Personal', 'Personal', 'leitung',
     r'\bchro\b|personalleit\w*|\bleit\w* personal\b|\bhead of (?:hr|people|human resources)\b|\bhr[ -]?(?:leit\w*|director)\b'),
    ('einkauf_leitung', 'Leitung Einkauf', 'Einkauf', 'leitung',
     r'einkaufsleit\w*|\bleit\w* (?:des )?einkauf\w*|\bhead of (?:procurement|purchasing)\b'),
    ('betrieb_leitung', 'Leitung Betrieb / Operations', 'Betrieb / Operations', 'leitung',
     r'\bcoo\b|\bchief operating officer\b|betriebsleit\w*|\boperations[ -]?(?:leit\w*|director|manager\w*)\b|\bhead of operations\b|'
     r'produktionsleit\w*|werksleit\w*|technische\w* leit\w*'),
    ('marketing', 'Marketing', 'Marketing', 'fach', r'\bmarketing\w*|\bbrand[ -]?manager\w*|\bonline[ -]?marketing\b'),
    ('vertrieb', 'Vertrieb', 'Vertrieb', 'fach', r'\bvertrieb\w*|\bkey[ -]?account\w*|\baccount manager\w*|\bsales\b|außendienst\w*'),
    ('it', 'IT / Digitalisierung', 'IT / Digitalisierung', 'fach', r'\bit[ -]?(?:administrator\w*|manager\w*|referent\w*)|\bsystemadministrat\w*|\bdigital\w* manager\w*'),
    ('personal', 'Personal', 'Personal', 'fach', r'\bpersonalreferent\w*|\bhr[ -]?(?:manager\w*|business partner)\b|\brecruit\w*'),
    ('einkauf', 'Einkauf', 'Einkauf', 'fach', r'\beinkäufer\w*|\beinkauf\b|\bprocurement\b'),
    ('finanzen', 'Finanzen', 'Finanzen', 'fach', r'\bbuchhalt\w*|\bcontroller\w*|\bcontrolling\b'),
    ('bereichsleitung', 'Bereichs-/Abteilungsleitung', 'unklar', 'leitung',
     r'\bbereichsleit\w*|\babteilungsleit\w*|\bteamleit\w*|\bniederlassungsleit\w*|\bstandortleit\w*'),
)
_COMPILED = tuple((k, label, dept, level, re.compile(rx, re.I)) for k, label, dept, level, rx in RULES)
MAX_TITLE = 160


def normalize(title):
    """→ {'role', 'label', 'department', 'level', 'version'} oder None, wenn kein bekannter Titel."""
    t = re.sub(r'\s+', ' ', str(title or '')).strip()
    if not t or len(t) > MAX_TITLE:
        return None
    for key, label, dept, level, rx in _COMPILED:
        if rx.search(t):
            return {'role': key, 'label': label, 'department': dept, 'level': level, 'version': VERSION}
    return None


def is_title(text):
    return normalize(text) is not None


def find_title(text):
    """Erste Titelstelle in einem kurzen Text → (start, end) oder None (für Belegspannen)."""
    t = str(text or '')
    best = None
    for _k, _l, _d, _lv, rx in _COMPILED:
        m = rx.search(t)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), m.end())
    return best


def find_titles(text):
    """Alle Titelstellen in einem Text → [(start, end)], sortiert, ohne Überlappung (für die Zuordnung zum nächsten Namen)."""
    t = str(text or '')
    spans = []
    for _k, _l, _d, _lv, rx in _COMPILED:
        spans += [(m.start(), m.end()) for m in rx.finditer(t)]
    out = []
    for a, b in sorted(spans, key=lambda s: (s[0], -(s[1] - s[0]))):
        if not out or a >= out[-1][1]:
            out.append((a, b))
    return out


QUOTE_RE = re.compile(r'[„“”«»]|\bkundenstimme|\breferenz(?:en)?\b|\btestimonial', re.I)


def is_quote(line):
    """Zitat oder Kundenstimme: genannte Personen gehören meist zu einer anderen Firma – kein Kandidat."""
    return bool(QUOTE_RE.search(str(line or '')))
