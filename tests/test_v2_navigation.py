"""2.0.0-dev14: Produktreview M06/M07 – sechs Bereiche, eigener Bereich Einstellungen, direkte Adressen (ohne Browser).

Abnahme:
- Die Seitenleiste hat genau sechs Bereiche; jede Ansicht gehört zu genau einem Bereich und hat eine Adresse.
- Jedes bisherige Ziel ist als Reiter oder Hilfe-Verweis erreichbar (Zuordnungstabelle des Reviews); nichts ist nur versteckt.
- Kein Abschnitt steht außerhalb einer Ansicht (sonst erschiene er auf jeder Seite).
- Einstellungen liegen in einer Ansicht; Datenpflege bleibt unter Firmen, wiederkehrende Recherche unter Finden,
  Preise werden aus den Angeboten verlinkt.
- Zähler-Elemente, die andere Module beschreiben, existieren genau einmal.
"""
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / 'sales_tool' / 'public'
HTML = (PUBLIC / 'index.html').read_text(encoding='utf-8')
NAV = (PUBLIC / 'nav.js').read_text(encoding='utf-8')
VOID = {'input', 'br', 'img', 'meta', 'link', 'hr', 'source', 'col', 'area', 'base', 'wbr', 'track', 'embed', 'param'}
VIEWS = re.findall(r'class="content[^"]*" id="view([A-Za-z]+)"', HTML)
VIEW_KEYS = [v[0].lower() + v[1:] for v in VIEWS]


class Where(HTMLParser):
    """Merkt sich für jede id und jeden Abschnitt die umgebende Ansicht."""

    def __init__(self):
        super().__init__()
        self.stack, self.view_of, self.orphans, self.in_main = [], {}, [], False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'main':
            self.in_main = True
        views = [x for _, x in self.stack if x and x.startswith('view')]
        view = views[-1] if views else None
        if a.get('id'):
            self.view_of[a['id']] = view
        cls = a.get('class') or ''
        if self.in_main and not view and tag in ('section', 'details') and 'panel' in cls:
            self.orphans.append(a.get('id') or cls)
        if tag not in VOID:
            self.stack.append((tag, a.get('id')))

    def handle_endtag(self, tag):
        if tag == 'main':
            self.in_main = False
        if tag in VOID:
            return
        while self.stack:
            if self.stack.pop()[0] == tag:
                break


W = Where()
W.feed(HTML)


def nav_table(name):
    body = NAV[NAV.index(f'const {name} = '):]
    return body[:body.index('};') + 2] if name == 'SLUG' else body[:body.index('];') + 2]


class NavigationStructureTests(unittest.TestCase):
    def test_six_areas_in_sidebar(self):
        areas = re.findall(r'<button class="nav[^"]*" data-view="([a-z]+)" data-area="([a-z]+)">', HTML)
        self.assertEqual([a for _, a in areas], ['heute', 'finden', 'firmen', 'angebote', 'abrechnen', 'einstellungen'])
        self.assertEqual([v for v, _ in areas], ['dashboard', 'finder', 'leads', 'quotes', 'accounting', 'settings'])
        self.assertNotIn('nav-more', HTML)  # kein verstecktes Sammelmenü „Erweitert“ mehr

    def test_every_view_has_area_address_and_tab(self):
        slug = nav_table('SLUG')
        areas = nav_table('AREAS')
        for view in VIEW_KEYS:
            self.assertRegex(slug, rf"\b{view}: '[a-z/-]+'", view)
            self.assertIn(f"'{view}'", areas, view)
        tabs = set(re.findall(r'data-area-view="([a-z]+)"', HTML))
        self.assertEqual(sorted(set(VIEW_KEYS) - tabs), ['report'])  # Bericht öffnet man aus einer Firma
        # Zuordnung der bisherigen 16 Menüziele (Review, Seite 13)
        old = ['dashboard', 'tasks', 'finder', 'datacheck', 'center', 'leads', 'pipeline', 'workspace', 'quotes', 'accounting',
               'research', 'scoring', 'signals', 'quality', 'studio', 'playbook']
        self.assertEqual([v for v in old if v not in tabs], [])
        self.assertIn('data-view-link="playbook"', HTML)  # Hilfe als festes kleines Ziel

    def test_no_section_outside_a_view(self):
        self.assertEqual(W.orphans, [])

    def test_settings_moved_into_one_view(self):
        for el in ('darstellung', 'apPanel', 'qSettingsForm', 'rtForm', 'targetProfileForm', 'availabilityForm', 'serviceProfileForm',
                   'qSecurity', 'qAuth', 'qBackup', 'qOffline', 'qbSettingsBox', 'qbSettings', 'preise', 'zugang', 'offline', 'gewichte'):
            self.assertEqual(W.view_of.get(el), 'viewSettings', el)
        for el in ('qChanges', 'qStale', 'qPrivacy', 'qDups', 'qMetrics'):
            self.assertEqual(W.view_of.get(el), 'viewQuality', el)
        self.assertEqual(W.view_of.get('qJobForm'), 'viewCenter')
        self.assertIn('data-settings-link="preise"', HTML[HTML.index('id="viewQuotes"'):HTML.index('id="viewFinder"')])
        jumps = re.findall(r'data-settings-jump="([A-Za-z]+)"', HTML)
        self.assertTrue(jumps)
        for j in jumps:
            self.assertEqual(W.view_of.get(j), 'viewSettings', j)

    def test_counters_exist_once(self):
        for badge in ('tdNavBadge', 'dueBadge', 'rcNavBadge', 'sgNavBadge', 'qNavBadge', 'aiNavBadge'):
            self.assertEqual(HTML.count(f'id="{badge}"'), 1, badge)

    def test_script_hooks(self):
        app = (PUBLIC / 'app.js').read_text(encoding='utf-8')
        self.assertIn("window.appReady=(async()=>{if(document.readyState!=='complete')await new Promise(r=>{document.addEventListener('DOMContentLoaded'", app)
        self.assertIn("['quality','settings','center'].includes(view)&&window.refreshQuality", app)
        self.assertIn('window.loadPricingSettings', (PUBLIC / 'quotes.js').read_text(encoding='utf-8'))
        self.assertLess(HTML.index('<script src="/workday.js"'), HTML.index('<script src="/nav.js" defer></script>'))
        from sales_tool.server import STATIC_FILES
        from tools.build_release import RELEASE_ADDITIONS
        self.assertIn('/nav.js', STATIC_FILES)
        self.assertIn('sales_tool/public/nav.js', RELEASE_ADDITIONS)
        for mod in ('osmlocal.js', 'postcalc.js'):  # laden beim Ansichtswechsel, nicht mehr beim Klick auf alte Menüpunkte
            self.assertIn("signaldesk:view", (PUBLIC / mod).read_text(encoding='utf-8'), mod)


if __name__ == '__main__':
    unittest.main()
