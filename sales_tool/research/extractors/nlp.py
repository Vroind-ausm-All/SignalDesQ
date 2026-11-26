"""Optionales Profil „nlp“ (Plan R2.5): Personennamen mit spaCy (de_core_news_sm) im Vergleich zu den Regeln.

Standardmäßig AUS (Einstellung ``nlp`` in ``research.settings``) und nur aktiv, wenn spaCy und das Modell installiert sind
(``pip install -r requirements-nlp.txt``). Das Modell läuft lokal auf bereits abgerufenem Text, ohne Netz-, Schreib- oder
Shell-Rechte; beim Programmstart wird nichts heruntergeladen.

Was das Modell darf: einen Personennamen (Entität PER) in einer Zeile vorschlagen, in der – oder direkt neben der – eine
bekannte Funktion steht (``research.roles``). Was es nicht darf: eine Person oder einen Arbeitgeber bestätigen. Jeder Fund
braucht wie jeder Regel-Fund eine wörtliche Fundstelle (Beleg v2) und bleibt ein Kandidat bis zur menschlichen Prüfung.

Lizenzen (getrennt geprüft, siehe docs/BESTANDTEILE.md): spaCy MIT; Modellgewichte de_core_news_sm laut Metadaten MIT,
trainiert u. a. auf TIGER (eigene Korpuslizenz) und WikiNER – die rechtliche Bewertung der Trainingsdaten steht aus (E8).
"""
from __future__ import annotations

import functools
import re

from .. import evidence as ev
from .. import roles
from .persons import person_name

VERSION = 'nlp-spacy-v1'
MODEL = 'de_core_news_sm'
MAX_LINE = 600
MAX_LINES = 700


def available():
    try:
        import spacy  # noqa: F401
        import importlib.util
        return importlib.util.find_spec(MODEL) is not None
    except Exception:  # noqa: BLE001 – optionaler Zusatz
        return False


def enabled():
    from .. import settings
    return bool(settings.get().get('nlp')) and available()


@functools.lru_cache(maxsize=1)
def _model():
    import spacy
    return spacy.load(MODEL, disable=['parser', 'lemmatizer', 'attribute_ruler', 'morphologizer', 'tagger'])


def _lines(raw):
    out, pos = [], 0
    for line in raw.splitlines(keepends=True):
        s = line.strip()
        if s:
            off = pos + line.index(s)
            out.append((off, off + len(s), s))
        pos += len(line)
        if len(out) >= MAX_LINES:
            break
    return out


def persons(raw, url, chash='', nlp=None):
    """Kandidaten aus einem Seitentext → Liste wie ``extractors.persons`` (method 'nlp'), jeweils mit Beleg v2 auf ``raw``."""
    raw = str(raw or '')
    lines = _lines(raw)
    if not lines:
        return []
    nlp = nlp or _model()
    docs = list(nlp.pipe([s[:MAX_LINE] for _, _, s in lines]))
    titles = [roles.find_titles(s) for _, _, s in lines]
    out, seen = [], set()
    for i, ((a, b, line), doc) in enumerate(zip(lines, docs)):
        if roles.is_quote(line):
            continue  # Zitat/Kundenstimme: Person einer anderen Firma
        for ent in doc.ents:
            if ent.label_ != 'PER':
                continue
            name = person_name(ent.text)
            if not name or name.casefold() in seen:
                continue
            n_off = line.find(name, ent.start_char)
            if n_off < 0:
                continue
            title_span, ta, tb = None, None, None
            free = [t for t in titles[i] if t[1] <= n_off or t[0] >= n_off + len(name)]
            if free:  # nächstgelegene Funktion in derselben Zeile
                t = min(free, key=lambda t: min(abs(t[0] - (n_off + len(name))), abs(n_off - t[1])))
                title_span, ta, tb = t, a, b
            else:  # Funktion als eigene Zeile direkt darüber/darunter, Name allein in seiner Zeile
                if name == person_name(line):
                    for j in (i - 1, i + 1):
                        if 0 <= j < len(lines) and titles[j] and not any(e.label_ == 'PER' for e in docs[j].ents):
                            title_span, ta, tb = titles[j][0], lines[j][0], lines[j][1]
                            break
            if not title_span:
                continue
            title_line = raw[ta:tb]
            title = _title_text(title_line, title_span, name)
            refs = {'full_name': ev.text_ref('full_name', name, raw, url, VERSION, start_hint=a + n_off, end_hint=b, chash=chash),
                    'job_title': ev.text_ref('job_title', title, raw, url, VERSION, start_hint=ta, end_hint=tb, chash=chash)}
            if not (refs['full_name'] and refs['job_title']):
                continue
            seen.add(name.casefold())
            lo, hi = min(a, ta), max(b, tb)
            out.append({'full_name': name, 'job_title': title, 'employer': '', 'business_email': '', 'business_phone': '',
                        'method': 'nlp', 'evidence': re.sub(r'\s+', ' ', raw[lo:hi])[:350], 'evidence_refs': refs,
                        'locator_group': {'kind': 'text', 'basis': 'raw_text', 'start': lo, 'end': hi}})
    return out


def _title_text(line, span, name=''):
    """Die Funktionsangabe um die gefundene Titelstelle: bis zum nächsten Trenner (Doppelpunkt, Komma, Gedankenstrich)."""
    a, b = span
    left = max([line.rfind(sep, 0, a) for sep in (':', ',', '–', '|', ' - ')] + [-1])
    right = [x for x in (line.find(sep, b) for sep in (':', ',', '–', '|', ' - ', '.')) if x >= 0]
    seg = line[left + 1:min(right) if right else len(line)].strip()
    if not seg or len(seg) > 80 or person_name(seg) or (name and name in seg):
        return line[a:b]
    return seg
