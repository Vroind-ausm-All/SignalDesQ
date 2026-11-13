"""2.0.0-dev12: Firmenakte mit Reitern (V2) und einheitliche Statusmarken (V6).

Abnahme:
- Fünf Reiter, jeder mit Tabpanel; jedes Bedienelement liegt im fachlich richtigen Reiter.
- Kein Element des Dialogs ist verloren gegangen: alle IDs aus dem Stand vor dev12 sind noch da.
- Statusmarken: fünf Tonstufen, jede mit Symbol; negative Zustände heißen überall „bad“, nicht „off“.
"""
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

PUBLIC = Path(__file__).resolve().parent.parent / 'sales_tool' / 'public'
HTML = (PUBLIC / 'index.html').read_text(encoding='utf-8')
CSS = (PUBLIC / 'style.css').read_text(encoding='utf-8')
VOID = {'input', 'br', 'img', 'meta', 'link', 'hr', 'source', 'col', 'area', 'base', 'wbr', 'track', 'embed', 'param'}

# Alle IDs, die der Dialog vor dev12 enthielt (Stand 2.0.0-dev11).
DIALOG_IDS = ('leadFile', 'leadForm', 'leadExtras', 'leadReportBtn', 'leadImprintBtn', 'leadCompanyData', 'leadFacts', 'leadScoreBtn',
              'leadScoreStatus', 'leadScoreResult', 'leadCorrelateBtn', 'leadSignals', 'startContactResearch', 'contactResearchStatus',
              'discoveryForm', 'siMatchBtn', 'draftText', 'copyDraft', 'exportBrief', 'activityForm', 'activityRows', 'modalScore',
              'scoreReasons', 'deleteLeadBtn', 'cancelLead', 'closeModal', 'modalTitle')


class Panels(HTMLParser):
    """Ordnet jedem Element mit id den nächstäußeren Reiter (data-lf-panel) zu."""

    def __init__(self):
        super().__init__()
        self.stack, self.where, self.tabs = [], {}, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get('role') == 'tab' and 'data-lf-tab' in a:
            self.tabs.append(a)
        panel = a.get('data-lf-panel') or next((p for _, p in reversed(self.stack) if p), None)
        if 'id' in a:
            self.where[a['id']] = panel
        if tag not in VOID:
            self.stack.append((tag, a.get('data-lf-panel')))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        while self.stack:
            if self.stack.pop()[0] == tag:
                break


PARSED = Panels()
PARSED.feed(HTML)


class TabTests(unittest.TestCase):
    def test_five_tabs_point_to_panels(self):
        tabs = PARSED.tabs
        self.assertEqual([t['data-lf-tab'] for t in tabs], ['ueberblick', 'kontakt', 'bedarf', 'recherche', 'stammdaten'])
        for t in tabs:
            target = t['aria-controls']
            self.assertIn(f'id="{target}"', HTML)
            self.assertEqual(PARSED.where[target], t['data-lf-tab'])
            self.assertRegex(HTML, rf'id="{target}"[^>]*role="tabpanel"[^>]*aria-labelledby="{t["id"]}"')
        self.assertEqual(sum(1 for t in tabs if t.get('aria-selected') == 'true'), 1)

    def test_controls_sit_in_the_right_tab(self):
        expected = {'activityForm': 'kontakt', 'draftText': 'kontakt', 'startContactResearch': 'kontakt',
                    'discoveryForm': 'bedarf', 'siMatchBtn': 'bedarf',
                    'leadReportBtn': 'recherche', 'leadImprintBtn': 'recherche', 'leadScoreBtn': 'recherche', 'leadSignals': 'recherche',
                    'modalScore': 'stammdaten', 'deleteLeadBtn': 'stammdaten'}
        self.assertEqual({k: PARSED.where.get(k) for k in expected}, expected)
        # Im Kontakt-Reiter steht das Protokoll vor der Recherche nach Entscheidern (häufigste Handlung zuerst).
        k = HTML[HTML.index('id="lfPanelKontakt"'):HTML.index('id="lfPanelBedarf"')]
        self.assertLess(k.index('id="activityForm"'), k.index('id="startContactResearch"'))

    def test_no_dialog_element_lost(self):
        missing = [i for i in DIALOG_IDS if f'id="{i}"' not in HTML]
        self.assertEqual(missing, [])
        self.assertEqual(len(re.findall(r'id="(leadForm|discoveryForm|activityForm)"', HTML)), 3)

    def test_header_and_script_hooks(self):
        for needle in ('id="leadTabs"', 'id="lfHeadNext"', 'id="modalMeta"', 'id="modalEyebrow"'):
            self.assertIn(needle, HTML)
        akte = (PUBLIC / 'akte.js').read_text(encoding='utf-8')
        app = (PUBLIC / 'app.js').read_text(encoding='utf-8')
        self.assertIn('window.leadTabs = ', akte)
        self.assertIn('window.leadTabs?.reset(!!id)', app)
        # Sprünge aus „Als Nächstes“ öffnen vorher den passenden Reiter.
        self.assertIn("setTab('stammdaten'); $('#leadForm [name=permission]')", akte)
        self.assertIn("setTab('bedarf'); $('#discoveryForm')", akte)
        self.assertIn('.lf-panel-off{display:none!important}', CSS)


class StatusMarkTests(unittest.TestCase):
    def test_every_tone_has_a_symbol(self):
        for tone, symbol in (('ok', '✓'), ('mid', '!'), ('bad', '✕'), ('wait', '○'), ('off', '–')):
            self.assertRegex(CSS, rf':is\(\.pill,\.sw-web\)(:is\([^)]*\b{tone}\b[^)]*\)|\.{tone})::before{{content:"{re.escape(symbol)}"')
        for tone in ('ok', 'mid', 'bad', 'wait', 'off'):
            self.assertIn(tone, re.search(r':is\(\.pill,\.sw-web\):is\(([^)]*)\)::before\{font-size', CSS).group(1))

    def test_negative_states_are_bad_not_off(self):
        checks = {'assessment.js': ("passt_nicht: 'bad'", "X: ['✕', 'bad'", "gesperrt: ['gesperrt', 'bad']", "nicht_qualifiziert: 'bad'"),
                  'jobs.js': ("failed: ['fehlgeschlagen', 'bad']",), 'postcalc.js': ("ueberzogen: ['über Kalkulation', 'bad']",),
                  'reach.js': ("voll: 'bad'",), 'akte.js': ("fehler: ['nicht gelesen', 'bad']",)}
        for name, needles in checks.items():
            text = (PUBLIC / name).read_text(encoding='utf-8')
            for n in needles:
                self.assertIn(n, text, name)
        # Die alten Einzelregeln sind entfernt – es gibt nur noch eine Stelle für die Tonfarben.
        for old in ('.sw-web.ok{', '.as-grade.off{', '.pill.won{'):
            self.assertNotIn(old, CSS)


if __name__ == '__main__':
    unittest.main()
