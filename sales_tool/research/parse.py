"""HTML-Auswertung (Sprint 1): Scrapling-Selector (lxml), wenn installiert und eingeschaltet – sonst eingebauter Parser.

Ergebnis je Seite: title, text (Fließtext ohne <title>/<script>/<style>/<noscript>/<template>), headings, links,
forms, mailtos. Seiteninhalte sind nicht vertrauenswürdige Daten – hier wird nichts ausgeführt, nichts nachgeladen.
"""
from __future__ import annotations

import re

from . import settings

SKIP_TAGS = ('script', 'style', 'noscript', 'template', 'svg', 'iframe', 'title', 'head')
BLOCK_TAGS = {'p', 'div', 'br', 'li', 'tr', 'td', 'th', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'section', 'article', 'header',
              'footer', 'address', 'dd', 'dt', 'table', 'ul', 'ol', 'hr', 'blockquote', 'main', 'nav', 'form'}


def scrapling_available():
    try:
        import scrapling.parser  # noqa: F401
        return True
    except Exception:  # noqa: BLE001 – optionaler Zusatz
        return False


def engine():
    choice = settings.get()['parser']
    if choice == 'stdlib':
        return 'stdlib'
    if choice in ('auto', 'scrapling') and scrapling_available():
        return 'scrapling'
    return 'stdlib'


def _clean_lines(text):
    lines = [re.sub(r'[ \t\r\f\v\xa0]+', ' ', l).strip() for l in text.split('\n')]
    return '\n'.join(l for l in lines if l)


def _parse_stdlib(html, url):
    from ..imprint import html_to_text
    text, links, mailtos = html_to_text(html)
    title = re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S)
    headings = [re.sub(r'<[^>]+>|\s+', ' ', h).strip() for h in re.findall(r'<h[1-3][^>]*>(.*?)</h[1-3]>', html, re.I | re.S)]
    return {'title': re.sub(r'\s+', ' ', title.group(1)).strip()[:220] if title else '', 'text': text,
            'headings': [h for h in headings if h][:25], 'links': links[:300], 'forms': len(re.findall(r'<form\b', html, re.I)),
            'mailtos': mailtos, 'engine': 'stdlib'}


def _parse_scrapling(html, url):
    from scrapling.parser import Selector
    sel = Selector(content=html, url=url, huge_tree=False, keep_comments=False, adaptive=False)
    root = sel._root
    title = ' '.join(str(t).strip() for t in sel.css('title::text') if str(t).strip())
    for bad in list(root.iter(*SKIP_TAGS)):
        if bad.tag != 'head':
            bad.drop_tree()
    for el in root.iter(*BLOCK_TAGS):
        el.tail = '\n' + (el.tail or '')
        if el.tag == 'br':
            continue
        el.text = '\n' + (el.text or '')
    body = root.find('body')
    raw_text = (body if body is not None else root).text_content()
    links, mailtos = [], []
    for a in sel.css('a[href]'):
        href = str(a.attrib.get('href', '')).strip()
        if href.lower().startswith('mailto:'):
            mailtos.append(href[7:].split('?')[0])
        links.append({'href': href, 'text': re.sub(r'\s+', ' ', a.get_all_text(separator=' ')).strip()[:80]})
    headings = [re.sub(r'\s+', ' ', h.get_all_text(separator=' ')).strip() for h in sel.css('h1, h2, h3')]
    return {'title': re.sub(r'\s+', ' ', title).strip()[:220], 'text': _clean_lines(raw_text), 'headings': [h for h in headings if h][:25],
            'links': links[:300], 'forms': len(sel.css('form')), 'mailtos': mailtos, 'engine': 'scrapling'}


def parse_html(html, url='', use=None):
    """``html`` als bereits dekodierter Text. ``use`` erzwingt 'stdlib' oder 'scrapling' (z. B. im Benchmark)."""
    which = use or engine()
    if which == 'scrapling':
        try:
            return _parse_scrapling(html, url)
        except Exception as exc:  # noqa: BLE001 – Zusatz darf den Ablauf nie stoppen
            out = _parse_stdlib(html, url)
            out['warning'] = f'Scrapling-Auswertung fehlgeschlagen ({exc.__class__.__name__}) – eingebauter Parser genutzt.'
            return out
    return _parse_stdlib(html, url)
