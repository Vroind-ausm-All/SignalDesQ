"""R0.4 (2.0.0-dev67): Projekt-Skills haben das vorgeschriebene Format und stehen im Skills-Register."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = sorted(p for p in (ROOT / '.claude' / 'skills').iterdir() if p.is_dir())
REGISTRY = (ROOT / 'docs' / 'SKILLS_REGISTRY.md').read_text(encoding='utf-8')
SECTIONS = ('## Eingaben', '## Ausgabe', '## Sicherheitsregeln', '## Beispiel')


class SkillFormatTests(unittest.TestCase):
    def test_every_skill_has_frontmatter_and_sections(self):
        self.assertGreaterEqual(len(SKILLS), 3)
        for d in SKILLS:
            with self.subTest(d.name):
                text = (d / 'SKILL.md').read_text(encoding='utf-8')
                m = re.match(r'---\nname: (\S+)\ndescription: (.+)\n---\n', text)
                self.assertIsNotNone(m, 'Frontmatter mit name und description')
                self.assertEqual(m.group(1), d.name)
                self.assertGreater(len(m.group(2)), 60, 'Beschreibung nennt die Auslöser')
                for s in SECTIONS:
                    self.assertIn(s, text)
                self.assertTrue('## Prüfliste' in text or '## Ablauf' in text)

    def test_every_skill_is_registered(self):
        for d in SKILLS:
            with self.subTest(d.name):
                self.assertRegex(REGISTRY, rf'\| `{re.escape(d.name)}` \|[^\n]*\| vorhanden')

    def test_registry_lists_no_installed_skill_that_is_missing(self):
        listed = re.findall(r'\| `([a-z-]+)` \|[^\n]*\| vorhanden', REGISTRY)
        self.assertEqual(sorted(listed), sorted(d.name for d in SKILLS))

    def test_tools_in_use_are_pinned(self):
        block = REGISTRY.split('## Entwicklungswerkzeuge (in Gebrauch)', 1)[1].split('\n## ', 1)[0]
        rows = [r for r in block.splitlines() if r.startswith('| ') and not r.startswith('| Werkzeug') and not r.startswith('|---')]
        self.assertGreaterEqual(len(rows), 3)
        for r in rows:
            with self.subTest(r[:30]):
                self.assertRegex(r, r'Hashes|SHA-256', 'Version mit Prüfsumme gepinnt')


if __name__ == '__main__':
    unittest.main()
