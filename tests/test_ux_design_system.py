"""UX-Programm U2 (2.0.0-dev72): Designsystem „Professionell“ (Professional Light / Research Dark).

Geprüft wird, was sich ohne Browser prüfen lässt:
- Schriften liegen im Repository mit Lizenz und passender Prüfsumme und werden lokal ausgeliefert (kein CDN);
- die Farben der Vorgabe stehen in den Tokens des Themes, Radius 6 px, Tabellenzeilen 32/40/52 px;
- neue Regeln wirken nur im Theme „Professionell“ – die übrigen Themes bleiben unverändert;
- keine Verläufe, kein Glaseffekt, kein Tailwind/CDN.
Kontraste je Theme prüft tests/test_v2_appearance.py.
"""
import hashlib
import json
import re
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from sales_tool import appearance
from sales_tool.model import connect, init_db
from sales_tool.server import STATIC_FILES, make_handler

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / 'sales_tool' / 'public'
FONTS = PUBLIC / 'fonts'
CSS = (PUBLIC / 'style.css').read_text(encoding='utf-8')
MANIFEST = json.loads((FONTS / 'fonts.json').read_text(encoding='utf-8'))


def token_block(selector_start):
    """Erster Tokenblock, dessen Selektor mit selector_start beginnt."""
    i = CSS.index(selector_start)
    return CSS[i:CSS.index('}', i)]


class FontTests(unittest.TestCase):
    def test_fonts_match_manifest_and_have_license(self):
        files = {f['file'] for f in MANIFEST['files']}
        self.assertEqual(files, {p.name for p in FONTS.glob('*.woff2')}, 'jede Schriftdatei steht im Verzeichnis fonts.json')
        for f in MANIFEST['files']:
            with self.subTest(f['file']):
                data = (FONTS / f['file']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), f['sha256'])
                self.assertEqual(len(data), f['bytes'])
                self.assertEqual(data[:4], b'wOF2')
                self.assertEqual(f['license'], 'OFL-1.1')
                self.assertIn('SIL OPEN FONT LICENSE', (FONTS / f['license_file']).read_text(encoding='utf-8').upper())

    def test_css_loads_fonts_only_locally(self):
        urls = re.findall(r'url\(([^)]*)\)', CSS)
        font_urls = [u for u in urls if 'woff' in u]
        self.assertEqual(sorted(font_urls), sorted(f"/fonts/{f['file']}" for f in MANIFEST['files']))
        self.assertNotRegex(CSS, r'@import|fonts\.googleapis|https?://')
        for f in MANIFEST['files']:
            self.assertEqual(STATIC_FILES[f"/fonts/{f['file']}"], (f"fonts/{f['file']}", 'font/woff2'))

    def test_fonts_are_in_release_package(self):
        """Ohne die Dateien im ZIP fiele eine Installation still auf die Systemschrift zurück (404 auf /fonts/…)."""
        sys.path.insert(0, str(ROOT / 'tools'))
        import build_release
        shipped = set(build_release.release_files())
        for f in MANIFEST['files']:
            for name in (f['file'], f['license_file']):
                self.assertIn(f'sales_tool/public/fonts/{name}', shipped)

    def test_font_served_as_woff2_without_charset(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'a.sqlite3'
            with connect(db) as conn:
                init_db(conn)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                url = f'http://127.0.0.1:{server.server_port}/fonts/geist-400.woff2'
                with urllib.request.urlopen(url) as r:
                    self.assertEqual(r.headers['Content-Type'], 'font/woff2')
                    self.assertEqual(r.read(4), b'wOF2')
                with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/style.css') as r:
                    self.assertEqual(r.headers['Content-Type'], 'text/css; charset=utf-8')
            finally:
                server.shutdown()
                server.server_close()


class TokenTests(unittest.TestCase):
    SPEC = {'--accent': '#2447a8',  # Primär '--nav-bg': '#14161a', '--bg': '#fafaf8', '--line': '#e3e2dc',
            '--danger-fg': '#a32b2b', '--warn-strong': '#b4610e', '--radius': '6px', '--table-row': '40px',
            '--shadow': 'none', '--card-shadow': 'none'}

    def test_spec_colors_in_professional_light(self):
        block = token_block(':root[data-theme="professionell"],')
        for name, value in self.SPEC.items():
            with self.subTest(name):
                self.assertRegex(block, rf'{re.escape(name)}:{re.escape(value)}(?:;|$)', 'Wert laut Vorgabe Phase 2')
        self.assertRegex(block, r'--ok-fg:#1d7a4c;', 'Positiv')
        self.assertRegex(block, r'--faint:#6b7280;', 'Neutral')

    def test_positive_states_use_their_own_role(self):
        """Im klassischen Theme ist der Akzent grün – „positiv“ darf im blauen Theme nicht blau werden."""
        for sel in ('.ui-pill.is-done', ':is(.pill,.sw-web,.as-grade):is(.ok,.won)', '.q-status.ok'):
            with self.subTest(sel):
                body = CSS[CSS.index(sel + '{'):]
                body = body[:body.index('}')]
                self.assertIn('var(--ok-fg)', body)
                self.assertNotIn('accent', body)

    def test_research_dark_exists(self):
        block = token_block(':root[data-theme="professionell"][data-mode="dark"]')
        self.assertIn('--bg:', block)
        self.assertIn('--accent:', block)

    def test_densities_set_row_heights(self):
        self.assertRegex(CSS, r'\[data-theme="professionell"\]\[data-density="kompakt"\]\{--table-row:32px\}')
        self.assertRegex(CSS, r'\[data-theme="professionell"\]\[data-density="komfort"\]\{--table-row:52px\}')
        self.assertEqual([d['id'] for d in appearance.DENSITIES], ['normal', 'kompakt', 'komfort'])

    def test_default_for_new_installations(self):
        self.assertEqual(appearance.DEFAULT, {'theme': 'professionell', 'mode': 'system', 'density': 'normal'})
        js = (PUBLIC / 'theme.js').read_text(encoding='utf-8')
        self.assertIn("const DEFAULT={theme:'professionell',mode:'system',density:'normal'}", js)

    def test_new_rules_are_scoped_to_the_theme(self):
        """Typografie, Radius und Zeilenhöhe dürfen die übrigen vier Themes nicht verändern."""
        tail = CSS[CSS.index("@font-face{font-family:'Geist'"):]
        rules = [r.strip() for r in re.findall(r'(?:^|\})\s*([^{}@]+)\{', tail)]
        self.assertTrue(rules)
        for sel in rules:
            with self.subTest(sel):
                self.assertTrue(sel.startswith(':root[data-theme="professionell"]'), sel)


class NoDecorationTests(unittest.TestCase):
    def test_no_gradients_glass_or_cdn(self):
        self.assertNotRegex(CSS, r'gradient\(')
        self.assertNotIn('backdrop-filter', CSS)
        html = (PUBLIC / 'index.html').read_text(encoding='utf-8')
        for tag in re.findall(r'<(?:script|link)\b[^>]*>', html):
            with self.subTest(tag):
                self.assertNotRegex(tag, r'(?:src|href)="(?:https?:)?//', 'Skripte und Stylesheets nur lokal')
        self.assertNotIn('tailwind', html.lower())


if __name__ == '__main__':
    unittest.main()
