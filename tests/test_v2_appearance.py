"""2.0.0-dev11: Darstellung – Themes, Hell/Dunkel, Dichte.

Abnahme:
- Alle Farben der Oberfläche kommen aus Rollen-Variablen; außerhalb der Theme-Blöcke steht keine feste Farbe mehr.
- Jede verwendete Variable ist definiert, und der Dunkelmodus überschreibt jede Farbrolle.
- Jedes Theme erfüllt in Hell und Dunkel die WCAG-Kontraste der wichtigsten Paare (AA; Theme „Kontrast“ AAA).
- Die Wahl wird gespeichert, ungültige Werte werden abgewiesen, unbekannte gespeicherte Werte fallen auf die Vorgabe zurück.
- theme.js wird ausgeliefert, steht im <head> vor dem Stylesheet und gehört zum Release.
"""
import json
import re
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sales_tool import appearance  # noqa: E402
from sales_tool.model import connect, init_db  # noqa: E402
from sales_tool.quality import put_setting  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / 'sales_tool' / 'public'
CSS = (PUBLIC / 'style.css').read_text(encoding='utf-8')
THEMES = ('klassisch', 'schiefer', 'sand', 'kontrast')
HEX = re.compile(r'#[0-9a-fA-F]{3,8}\b')


def _strip(css):
    return re.sub(r'/\*.*?\*/', '', css, flags=re.S)


def _rules(css):
    return [(sel.strip(), body) for sel, body in re.findall(r'([^{}]*)\{([^{}]*)\}', _strip(css))]


def _is_token_rule(sel, body):
    parts = [p.strip() for p in sel.split(',')]
    return all(p.startswith((':root', '[data-swatch')) for p in parts) and re.search(r'--[\w-]+:', body)


def _token_rules():
    """Regeln aus Theme-/Modus-Wurzeln mit Variablen: hier – und nur hier – stehen Farbwerte."""
    return {sel.split(',')[0].strip(): {k: v.strip() for k, v in re.findall(r'(--[\w-]+):([^;]+)', body)}
            for sel, body in _rules(CSS) if _is_token_rule(sel, body)}


TOKENS = _token_rules()


def palette(theme, mode):
    t = dict(TOKENS[':root'])
    if theme != 'klassisch':
        t.update(TOKENS[f':root[data-theme="{theme}"]'])
    if mode == 'dunkel':
        t.update(TOKENS[':root[data-mode="dark"]'])
        if theme != 'klassisch':
            t.update(TOKENS[f':root[data-theme="{theme}"][data-mode="dark"]'])
    return t


def _lum(hexcolor):
    h = hexcolor.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    rgb = [c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4 for c in rgb]
    return .2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2]


def contrast(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + .05) / (lo + .05)


# Vordergrund, Hintergrund, Mindestkontrast (AA). Theme „Kontrast“ verlangt bei Text 7:1 (AAA).
PAIRS = (('ink', 'surface', 7), ('ink', 'bg', 7), ('ink-2', 'surface', 4.5), ('muted', 'surface', 4.5), ('muted', 'bg', 4.5),
         ('faint', 'surface', 3), ('accent-ink', 'surface', 4.5), ('accent-ink', 'accent-soft', 4.5), ('on-dark', 'accent', 4.5),
         ('on-dark', 'accent-hover', 4.5), ('accent-strong', 'surface', 3), ('warn-fg', 'warn-bg', 4.5), ('danger-fg', 'danger-bg', 4.5),
         ('info-fg', 'info-bg', 4.5), ('warn-fg', 'surface', 4.5), ('danger-fg', 'surface', 4.5), ('info-fg', 'surface', 4.5),
         ('violet-fg', 'surface', 4.5), ('on-dark', 'nav-bg', 7), ('on-dark-muted', 'nav-bg', 4.5), ('on-dark-faint', 'nav-bg', 4.5),
         ('on-dark-accent', 'nav-bg', 4.5), ('on-dark', 'nav-bg-2', 4.5), ('on-dark', 'toast-error', 4.5))


class StylesheetTests(unittest.TestCase):
    def test_no_fixed_colours_outside_token_blocks(self):
        offenders = []
        for sel, body in _rules(CSS):
            if _is_token_rule(sel, body):
                continue
            for decl in body.split(';'):
                if HEX.search(decl) or re.search(r':\s*(white|black)\b', decl):
                    offenders.append(f'{sel[-60:]} → {decl.strip()}')
        self.assertEqual(offenders, [], 'Feste Farben gehören in die Theme-Blöcke oben in style.css')
        quoted = re.compile(r'[\'"`]#[0-9a-fA-F]{3,8}[\'"`]')
        for name in ('app.js', 'theme.js'):
            self.assertIsNone(quoted.search((PUBLIC / name).read_text(encoding='utf-8')), name)
        html = (PUBLIC / 'index.html').read_text(encoding='utf-8')
        self.assertIsNone(re.search(r'style="[^"]*#[0-9a-fA-F]{3,8}', html))

    def test_every_used_variable_is_defined_and_dark_mode_is_complete(self):
        used = set(re.findall(r'var\((--[\w-]+)', CSS))
        base = TOKENS[':root']
        self.assertEqual(sorted(used - set(base)), [])
        dark = TOKENS[':root[data-mode="dark"]']
        missing = sorted(k for k in base if k not in dark and k != '--toast-error')
        self.assertEqual(missing, [], 'Dunkelmodus muss jede Farbrolle setzen')
        for theme in THEMES[1:]:
            self.assertIn(f':root[data-theme="{theme}"]', TOKENS)
            self.assertIn(f':root[data-theme="{theme}"][data-mode="dark"]', TOKENS)

    def test_theme_ids_match_backend(self):
        self.assertEqual(tuple(t['id'] for t in appearance.THEMES), THEMES)

    def test_contrast_in_every_theme_and_mode(self):
        failures = []
        for theme in THEMES:
            for mode in ('hell', 'dunkel'):
                pal = palette(theme, mode)
                for fg, bg, need in PAIRS:
                    if theme == 'kontrast' and need >= 4.5:
                        need = 7
                    ratio = contrast(pal['--' + fg], pal['--' + bg])
                    if ratio < need:
                        failures.append(f'{theme}/{mode}: {fg} auf {bg} = {ratio:.2f} < {need}')
        self.assertEqual(failures, [])

    def test_brand_colours_of_klassisch_unchanged(self):
        pal = palette('klassisch', 'hell')
        self.assertEqual((pal['--nav-bg'], pal['--bg'], pal['--ink'], pal['--accent-strong'], pal['--on-dark-accent']),
                         ('#0d2026', '#f6f7f4', '#183137', '#14a178', '#51dfb0'))


class PageTests(unittest.TestCase):
    def test_theme_script_runs_before_stylesheet(self):
        html = (PUBLIC / 'index.html').read_text(encoding='utf-8')
        head = html[:html.index('</head>')]
        self.assertIn('<script src="/theme.js"></script>', head)
        self.assertLess(head.index('/theme.js'), head.index('/style.css'))
        self.assertNotIn('defer', head[head.index('/theme.js') - 20:head.index('/theme.js') + 20])
        self.assertIn('id="modeToggle"', html)
        self.assertIn('id="apPanel"', html)

    def test_release_contains_new_files(self):
        from tools.build_release import RELEASE_ADDITIONS
        for f in ('sales_tool/appearance.py', 'sales_tool/public/theme.js', 'docs/UI_UX_VORSCHLAEGE.md'):
            self.assertIn(f, RELEASE_ADDITIONS)


class SettingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = connect(str(Path(self.tmp.name) / 't.sqlite3'))
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def test_defaults_save_and_validation(self):
        self.assertEqual(appearance.load(self.conn), {'theme': 'klassisch', 'mode': 'system', 'density': 'normal'})
        self.assertEqual(appearance.save(self.conn, {'theme': 'Sand', 'mode': 'dunkel'}),
                         {'theme': 'sand', 'mode': 'dunkel', 'density': 'normal'})
        self.assertEqual(appearance.save(self.conn, {'density': 'kompakt'})['theme'], 'sand')  # Teiländerung behält den Rest
        for bad in ({'theme': 'neon'}, {'mode': 'nacht'}, {'density': ''}, ['sand']):
            with self.assertRaises(ValueError):
                appearance.save(self.conn, bad)
        self.assertEqual(appearance.load(self.conn), {'theme': 'sand', 'mode': 'dunkel', 'density': 'kompakt'})

    def test_unknown_stored_values_fall_back(self):
        put_setting(self.conn, appearance.KEY, {'theme': 'aus-zukunft', 'mode': 'hell', 'density': 7})
        self.assertEqual(appearance.load(self.conn), {'theme': 'klassisch', 'mode': 'hell', 'density': 'normal'})
        put_setting(self.conn, appearance.KEY, 'kaputt')
        self.assertEqual(appearance.load(self.conn), appearance.DEFAULT)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'api.sqlite3')
        prepare_database(self.db)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        cleanup_tmp(self.tmp)

    def call(self, method, path, body=None):
        c = HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=10)
        c.request(method, path, json.dumps(body) if body is not None else None, {'Content-Type': 'application/json'} if body is not None else {})
        r = c.getresponse()
        data = r.read()
        ctype = r.getheader('Content-Type', '')
        c.close()
        return r.status, (json.loads(data) if data and 'json' in ctype else data), ctype

    def test_roundtrip_and_static_file(self):
        st, d, _ = self.call('GET', '/api/ui/appearance')
        self.assertEqual((st, d['appearance']['theme'], len(d['themes']), len(d['modes'])), (200, 'klassisch', 4, 3))
        st, d, _ = self.call('PUT', '/api/ui/appearance', {'theme': 'kontrast', 'mode': 'hell'})
        self.assertEqual((st, d['appearance']['theme'], d['appearance']['mode']), (200, 'kontrast', 'hell'))
        self.assertEqual(self.call('PUT', '/api/ui/appearance', {'theme': '<script>'})[0], 400)
        self.assertEqual(self.call('GET', '/api/ui/appearance')[1]['appearance']['theme'], 'kontrast')
        st, body, ctype = self.call('GET', '/theme.js')
        self.assertEqual(st, 200)
        self.assertTrue(ctype.startswith('text/javascript'))
        self.assertIn(b'signaldesk.appearance', body)


if __name__ == '__main__':
    unittest.main()
