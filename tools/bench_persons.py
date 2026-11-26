"""R2-Messung: Personen und Rollen – Regeln (vorher) gegen R2.1-Extraktion und optional das NLP-Profil (R2.5).

python tools/bench_persons.py [--split test|abstimmung|alle] [--out docs/bench/r2-persons.json]

Testmenge: erfundene Team-Seiten in ``tests/fixtures/persons_bench/pages.json`` (erzeugt von ``tools/make_persons_bench.py``),
getrennt in Abstimm- und Testmenge. Das ist KEINE Messung an echten Firmen; die Abnahme „Präzision ≥ 95 %, Recall ≥ 70 %“
braucht die Referenzliste (R1.6). Gezählt wird je Seite: gefunden (Name), richtig (Name in der Sollliste UND normalisierte
Rolle gleich), Soll. Präzision = richtig / gefunden, Recall = richtig / Soll, je mit 95-%-Wilson-Bereich.

Varianten:
- ``regeln``: Zeilenregeln wie vor R2 (keine strukturierten Personen, kein NLP).
- ``r2``: strukturierte Personen (JSON-LD, Microdata, Tabellen, Karten) + Zeilenregeln.
- ``r2_nlp``: wie ``r2`` plus spaCy-Vorschläge – nur, wenn spaCy und de_core_news_sm installiert sind.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sales_tool import __version__  # noqa: E402
from sales_tool.public_contacts import extract_public_contacts  # noqa: E402
from sales_tool.research.benchmark import wilson  # noqa: E402
from sales_tool.research.evidence import content_hash  # noqa: E402
from sales_tool.research.extractors import nlp, persons  # noqa: E402
from sales_tool.research.parse import parse_html  # noqa: E402

FIXTURE = ROOT / 'tests' / 'fixtures' / 'persons_bench' / 'pages.json'


def _crawl(p, structured):
    html = p['html']
    return {'pages': [{'url': p['url'], 'raw_text': parse_html(html, p['url'], use='stdlib')['text'], 'content_hash': content_hash(html),
                       'persons': persons.extract(html, p['url'])['persons'] if structured else []}]}


def _run(pages, variant):
    use_nlp = variant == 'r2_nlp'
    rows, t0 = [], time.perf_counter()
    with mock.patch.object(nlp, 'enabled', lambda: use_nlp):
        for p in pages:
            found = extract_public_contacts(_crawl(p, variant != 'regeln'))['people']
            gold = {n.casefold(): r for n, r in p['gold']}
            got = {x['full_name'].casefold(): x['role_key'] for x in found}
            correct = sum(1 for n, r in got.items() if gold.get(n) == r)
            wrong = sorted(f'{n} ({r})' for n, r in got.items() if gold.get(n) != r)
            missed = sorted(n for n in gold if got.get(n) != gold[n])
            rows.append({'page': p['id'], 'found': len(got), 'correct': correct, 'gold': len(gold), 'false': wrong, 'missed': missed,
                         'methods': sorted({x['method'] for x in found})})
    found, correct, gold = (sum(r[k] for r in rows) for k in ('found', 'correct', 'gold'))
    return {'found': found, 'correct': correct, 'gold': gold,
            'precision': round(correct / found, 3) if found else None, 'precision_ci95': wilson(correct, found),
            'recall': round(correct / gold, 3) if gold else None, 'recall_ci95': wilson(correct, gold),
            'seconds': round(time.perf_counter() - t0, 3), 'pages': rows}


def run(split='test'):
    pages = [p for p in json.loads(FIXTURE.read_text(encoding='utf-8')) if split == 'alle' or p['split'] == split]
    out = {'version': __version__, 'note': 'erfundene Seiten, keine Messung an echten Firmen (Referenzliste R1.6 fehlt)',
           'split': split, 'pages': len(pages), 'variants': {}}
    for v in ('regeln', 'r2', 'r2_nlp'):
        if v == 'r2_nlp' and not nlp.available():
            out['variants'][v] = {'skipped': 'spaCy/de_core_news_sm nicht installiert (requirements-nlp.txt)'}
            continue
        out['variants'][v] = _run(pages, v)
    if nlp.available():
        import spacy
        out['nlp_model'] = {'spacy': spacy.__version__, 'model': nlp.MODEL, 'model_version': nlp._model().meta.get('version')}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--split', default='test', choices=('test', 'abstimmung', 'alle'))
    ap.add_argument('--out')
    a = ap.parse_args(argv)
    res = run(a.split)
    text = json.dumps(res, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).write_text(text + '\n', encoding='utf-8')
    for v, r in res['variants'].items():
        if 'skipped' in r:
            print(f'{v:8} übersprungen: {r["skipped"]}')
        else:
            print(f'{v:8} Präzision {r["correct"]}/{r["found"]} {r["precision_ci95"]}  Recall {r["correct"]}/{r["gold"]} {r["recall_ci95"]}  {r["seconds"]} s')
    return 0


if __name__ == '__main__':
    sys.exit(main())
