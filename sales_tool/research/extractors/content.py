"""Haupttext einer Seite (Sprint 2) – ohne Navigation, Kopf-/Fußbereich, Cookie-Hinweise.

Standard: eingebauter Leser (bevorzugt <main>/<article>, entfernt nav/header/footer/aside und typische Banner).
Optional: Trafilatura (Apache-2.0), per Schalter – nur die Auswertung ``trafilatura.extract``; Trafilatura ruft
dabei nichts aus dem Netz ab (das macht immer der sichere SignalDesk-Abruf).
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

DROP_TAGS = {'nav', 'header', 'footer', 'aside', 'script', 'style', 'noscript', 'template', 'svg', 'iframe', 'form', 'title', 'head', 'button'}
BOILER_RX = re.compile(r'cookie|consent|banner|navbar|navigation|menu|breadcrumb|footer|header|sidebar|newsletter|social|share', re.I)
BLOCK = {'p', 'div', 'br', 'li', 'tr', 'td', 'th', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'section', 'article', 'main', 'address', 'dd', 'dt',
         'table', 'ul', 'ol', 'hr', 'blockquote'}
VOID = {'br', 'hr', 'img', 'input', 'meta', 'link', 'source', 'wbr', 'area', 'col', 'embed', 'param', 'track'}


def trafilatura_available():
    try:
        import trafilatura  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


class _Main(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth_skip, self.stack = 0, []
        self.all, self.main = [], []
        self.in_main = 0

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            if tag in BLOCK:
                self._emit('\n')
            return
        a = dict(attrs)
        marker = ' '.join(filter(None, (a.get('class'), a.get('id'), a.get('role'))))
        skip = tag in DROP_TAGS or bool(marker and BOILER_RX.search(marker)) or a.get('aria-hidden') == 'true' or 'hidden' in a
        is_main = tag in ('main', 'article') or a.get('role') == 'main'
        self.stack.append((tag, skip, is_main))
        if skip:
            self.depth_skip += 1
        if is_main:
            self.in_main += 1
        if tag in BLOCK:
            self._emit('\n')

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for t, skip, is_main in self.stack[i:]:
                    if skip:
                        self.depth_skip -= 1
                    if is_main:
                        self.in_main -= 1
                del self.stack[i:]
                break
        if tag in BLOCK:
            self._emit('\n')

    def _emit(self, s):
        if self.depth_skip:
            return
        self.all.append(s)
        if self.in_main:
            self.main.append(s)

    def handle_data(self, data):
        self._emit(data)


def _clean(parts):
    lines = [re.sub(r'[ \t\r\f\v\xa0]+', ' ', l).strip() for l in ''.join(parts).split('\n')]
    return '\n'.join(l for l in lines if l)


def main_text(page_html, url='', use=None):
    from .. import settings
    which = use or settings.get().get('content', 'stdlib')
    if which == 'trafilatura' and trafilatura_available():
        try:
            import trafilatura
            text = trafilatura.extract(page_html, url=url or None, include_comments=False, include_tables=True, favor_precision=True,
                                       with_metadata=False, deduplicate=True) or ''
            return {'text': text.strip(), 'engine': 'trafilatura'}
        except Exception as exc:  # noqa: BLE001
            out = main_text(page_html, url, use='stdlib')
            out['warning'] = f'Trafilatura fehlgeschlagen ({exc.__class__.__name__}) – eingebauter Leser genutzt.'
            return out
    p = _Main()
    try:
        p.feed(page_html or '')
    except Exception:  # noqa: BLE001
        pass
    main = _clean(p.main)
    return {'text': main if len(main) >= 80 else _clean(p.all), 'engine': 'stdlib'}
