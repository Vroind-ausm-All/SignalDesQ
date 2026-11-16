"""2.0.0-dev49: UI-Baukasten und Hauptnavigation bei schmaler Breite (Schritt 1 der visuellen Konsolidierung).

Abnahme:
- style.css stellt die Abstands- und Maßvariablen und alle Bausteinklassen mit Präfix ui- bereit.
- Die neuen Regeln (Baukasten, Schublade) färben nur über Theme-Variablen – keine festen Farbwerte.
- docs/UI_BAUKASTEN.md nennt alle sieben Bausteine, die Regeln und die Messwerte des Zielbilds.
- Kopfzeile hat den beschrifteten Menü-Knopf mit aria-controls/aria-expanded; die Seitenleiste ist dessen Ziel.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / 'sales_tool' / 'public'
CSS = (PUBLIC / 'style.css').read_text(encoding='utf-8')
HTML = (PUBLIC / 'index.html').read_text(encoding='utf-8')
NAV = (PUBLIC / 'nav.js').read_text(encoding='utf-8')
DOC = (ROOT / 'docs' / 'UI_BAUKASTEN.md').read_text(encoding='utf-8')

LAYOUT = {'--s1': '4px', '--s2': '8px', '--s3': '12px', '--s4': '16px', '--s5': '24px', '--s6': '32px',
          '--row': '56px', '--ctl': '36px', '--side': '320px'}
CLASSES = ('ui-page', 'ui-head', 'ui-meta', 'ui-back', 'ui-tool', 'ui-search', 'ui-tabs', 'ui-tab', 'ui-list', 'ui-row', 'ui-row-head',
           'ui-main', 'ui-num', 'ui-chev', 'ui-fold', 'ui-fold-body', 'ui-pill', 'is-overdue', 'is-attention', 'is-done', 'is-underway',
           'ui-txt', 'ui-with-side', 'ui-side')
BLOCKS = ('Seitenkopf', 'Werkzeugzeile', 'Liste', 'Klappzeile', 'Status', 'Knöpfe', 'Abstände und Schrift')
HEX = re.compile(r'#[0-9a-fA-F]{3,8}\b')


def _strip(css):
    return re.sub(r'/\*.*?\*/', '', css, flags=re.S)


def _section(marker):
    start = CSS.index(marker)
    nxt = CSS.find('/* =====', start + len(marker))
    return CSS[start:nxt if nxt > 0 else len(CSS)]


class UiBaukastenTests(unittest.TestCase):
    def test_layout_tokens_in_base_block(self):
        base = re.search(r':root,\[data-swatch="klassisch"\]\{([^}]*)\}', _strip(CSS)).group(1)
        for name, value in LAYOUT.items():
            self.assertIn(f'{name}:{value}', base, name)
        # nur einmal definiert, damit kein Theme sie unbemerkt überschreibt
        for name in LAYOUT:
            self.assertEqual(len(re.findall(re.escape(name) + r':', _strip(CSS))), 1, name)

    def test_building_block_classes_exist(self):
        css = _strip(CSS)
        for cls in CLASSES:
            self.assertRegex(css, r'\.' + re.escape(cls) + r'(?![\w-])', cls)
        section = _strip(_section('/* ===== 2.0.0-dev49: UI-Baukasten'))
        self.assertIn('min-height:var(--row)', section)  # Zeile 56 px
        self.assertIn('min-height:var(--ctl)', section)  # Werkzeugzeile 36 px
        self.assertIn('var(--side)', section)            # Kontextspalte 320 px
        self.assertIn('min-height:40px', section)        # Seitenkopf
        # alle Selektoren des Baukastens tragen das Präfix ui- (Ausnahme: Zustände is-… an ui-Elementen)
        for sel in re.findall(r'([^{}@]+)\{', section):
            for part in sel.split(','):
                part = part.strip()
                if not part or part.startswith('media'):
                    continue
                self.assertTrue(part.startswith('.ui-'), part)

    def test_new_rules_use_theme_variables_only(self):
        for marker in ('/* ===== 2.0.0-dev49: UI-Baukasten', '/* ===== 2.0.0-dev49: Hauptnavigation'):
            section = _strip(_section(marker))
            self.assertIsNone(HEX.search(section), marker)
            self.assertIsNone(re.search(r':\s*(white|black)\b|rgba?\(', section), marker)
            used = set(re.findall(r'var\((--[\w-]+)', section))
            self.assertTrue(used, marker)
            for name in used:
                self.assertRegex(CSS, re.escape(name) + r':', name)

    def test_document_names_all_seven_blocks_rules_and_measures(self):
        for i, block in enumerate(BLOCKS, 1):
            self.assertRegex(DOC, rf'\| {i} \| {re.escape(block)} \|', block)
        for cls in ('.ui-head', '.ui-tool', '.ui-list', '.ui-row', '.ui-fold', '.ui-pill', '.ui-tab', '.ui-with-side', '.ui-txt'):
            self.assertIn(cls, DOC)
        for value in ('76 px', '132 px', '184 px', '1280 × 720', '4/8/12/16/24/32', 'Titel 26', 'Zusatz 12'):
            self.assertIn(value, DOC)
        self.assertIn('noch nicht', DOC)  # ehrlich: Ansichten sind noch nicht umgestellt

    def test_menu_button_and_drawer_markup(self):
        btn = re.search(r'<button[^>]*id="navMenuBtn"[^>]*>([^<]*)</button>', HTML)
        self.assertIsNotNone(btn)
        self.assertIn('Menü', btn.group(1))
        self.assertIn('aria-controls="sideNav"', btn.group(0))
        self.assertIn('aria-expanded="false"', btn.group(0))
        self.assertRegex(HTML, r'<aside class="sidebar" id="sideNav">')
        self.assertIn('id="navClose"', HTML)
        self.assertIn('id="navScrim"', HTML)
        self.assertNotRegex(HTML, r'<[^>]+\son[a-z]+=')  # CSP: keine Inline-Event-Handler
        for needle in ("'aria-expanded'", "'Escape'", 'navScrim', 'navClose', 'btn.focus()'):
            self.assertIn(needle, NAV)
        # breit: Knopf, Schließen und Hintergrund unsichtbar; die Schublade gilt nur bis 520 px
        css = _strip(CSS)
        self.assertIn('.nav-menu,.nav-close,.nav-scrim{display:none}', css)
        drawer = _strip(_section('/* ===== 2.0.0-dev49: Hauptnavigation'))
        self.assertIn('@media(max-width:520px)', drawer)

    def test_doc_in_release(self):
        build = (ROOT / 'tools' / 'build_release.py').read_text(encoding='utf-8')
        self.assertIn("'docs/UI_BAUKASTEN.md'", build)


if __name__ == '__main__':
    unittest.main()
