"""R1.3-Messung: findet die Discovery mehr relevante Seiten bei gleichem Seitenbudget?

python tools/bench_discovery.py [--out docs/bench/r1.3-discovery.json]

Erfundene Websites ohne Netz: Jede hat eine Startseite, die nur einen Teil der Seiten verlinkt, und eine Sitemap.
Verglichen wird ``website_analyzer.light_crawl(..., 'contacts')`` mit und ohne Discovery bei gleichem Seitenbudget
(``MAX_PAGES``). Relevant heißt: Impressum, Management, Team, Presse oder Kontakt. Das ist eine Messung an erfundenen
Fällen, keine Messung an echten Firmen-Websites.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sales_tool import __version__, imprint, website_analyzer as wa  # noqa: E402
from sales_tool.research import discovery as dc  # noqa: E402

RELEVANT = {'impressum', 'management', 'team', 'presse', 'kontakt'}
TEXT = b'<p>' + b'Beispieltext einer erfundenen Firma. ' * 20 + b'</p>'

# (Name, auf der Startseite verlinkt, nur in der Sitemap)
SITES = [
    ('handwerk', ['leistungen', 'referenzen', 'kontakt'], ['ueber-uns/team', 'impressum', 'aktuelles/neubau']),
    ('kanzlei', ['rechtsgebiete', 'impressum'], ['anwaelte/team', 'kontakt', 'presse/urteil']),
    ('industrie', ['produkte/a', 'produkte/b', 'produkte/c', 'karriere'], ['unternehmen/vorstand', 'presse', 'impressum']),
    ('dienstleister', ['team', 'kontakt', 'impressum', 'leistungen'], ['presse/meldung']),
    ('agentur', ['projekte', 'leistungen'], []),  # keine Sitemap-Vorteile: darf nicht schlechter werden
    ('mittelstand', ['loesungen', 'branchen'], ['geschaeftsfuehrung', 'team', 'kontakt', 'impressum', 'news']),
]


def _site(name, linked, hidden):
    origin = f'https://{name}-fiktiv.example/'
    links = ''.join(f'<a href="/{p}">{p}</a>' for p in linked).encode()
    pages = {origin: b'<html><body><h1>' + name.encode() + b'</h1>' + TEXT + links + b'</body></html>'}
    for p in linked + hidden:
        pages[origin + p] = b'<html><body><h1>' + p.encode() + b'</h1>' + TEXT + b'</body></html>'
    if hidden:
        locs = ''.join(f'<url><loc>{origin}{p}</loc></url>' for p in linked + hidden).encode()
        pages[origin + 'sitemap.xml'] = b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + locs + b'</urlset>'
    return origin, pages


def _crawl(origin, pages, discovery_on):
    def fetch(url, origin_=None):
        if url not in pages:
            raise wa.CrawlError('HTTP 404')
        return url, 'application/xml' if url.endswith('.xml') else 'text/html', pages[url]
    patches = [mock.patch.object(imprint, 'FETCH', fetch), mock.patch.object(wa, 'public_url', lambda u: u),
               mock.patch('sales_tool.netpolicy.offline', lambda *a: False)]
    if not discovery_on:
        patches.append(mock.patch.object(dc, 'discover', lambda *a, **k: ([], [])))
    for p in patches:
        p.start()
    try:
        res = wa.light_crawl(origin, 'contacts')
    finally:
        for p in reversed(patches):
            p.stop()
    urls = [p['url'] for p in res['pages']][1:]  # ohne Startseite
    return {'pages': len(urls), 'relevant': sum(dc.category(u) in RELEVANT for u in urls)}


def run():
    out = {'version': __version__, 'note': 'erfundene Websites, keine Messung an echten Firmen', 'max_pages': wa.MAX_PAGES, 'sites': []}
    tot = {'links_only': {'pages': 0, 'relevant': 0}, 'with_discovery': {'pages': 0, 'relevant': 0}}
    same_budget = True
    for name, linked, hidden in SITES:
        origin, pages = _site(name, linked, hidden)
        a, b = _crawl(origin, pages, False), _crawl(origin, pages, True)
        same_budget &= a['pages'] <= wa.MAX_PAGES - 1 and b['pages'] <= wa.MAX_PAGES - 1
        out['sites'].append({'site': name, 'links_only': a, 'with_discovery': b})
        for k, v in (('links_only', a), ('with_discovery', b)):
            for f in v:
                tot[k][f] += v[f]
    out.update(tot)
    out['pages_budget_same'] = same_budget
    out['not_worse_anywhere'] = all(s['with_discovery']['relevant'] >= s['links_only']['relevant'] for s in out['sites'])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out')
    args = ap.parse_args(argv)
    res = run()
    text = json.dumps(res, ensure_ascii=False, indent=2) + '\n'
    if args.out:
        Path(args.out).write_text(text, encoding='utf-8')
    print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
