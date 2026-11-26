"""R0.3 (2.0.0-dev67): CLAUDE.md – jede Regel verweist auf Code und Test, die es wirklich gibt.

Die Regeln selbst setzt das Programm durch; dieser Test verhindert nur, dass CLAUDE.md auf umbenannte oder gelöschte Stellen zeigt.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import plan_status  # noqa: E402

TEXT = (ROOT / 'CLAUDE.md').read_text(encoding='utf-8')
REFS = re.findall(r'`([^`\s]+::[^`\s]+)`', TEXT)


def rules():
    """Nummerierte Regeln (Block bis zur nächsten Nummer oder Überschrift)."""
    body = TEXT.split('## Unverhandelbare Regeln', 1)[1].split('\n## ', 1)[0]
    return [b.strip() for b in re.split(r'\n(?=\d+\. )', body) if re.match(r'\d+\. ', b.strip())]


class RuleReferenceTests(unittest.TestCase):
    def test_every_rule_names_enforcement_or_test(self):
        found = rules()
        self.assertGreaterEqual(len(found), 10)
        for r in found:
            with self.subTest(r[:40]):
                self.assertTrue(re.search(r'`tests/[^`]+::', r), 'jede Regel nennt mindestens einen Test')

    def test_code_references_exist(self):
        code = [r for r in REFS if not r.startswith('tests/')]
        self.assertGreater(len(code), 10)
        for ref in code:
            with self.subTest(ref):
                path, symbol = ref.split('::')
                text = (ROOT / path).read_text(encoding='utf-8')
                self.assertRegex(text, rf'(?m)^(def|class) {re.escape(symbol)}\b')

    def test_test_references_exist(self):
        tests = [r for r in REFS if r.startswith('tests/')]
        self.assertGreater(len(tests), 10)
        for ref in tests:
            with self.subTest(ref):
                self.assertEqual(plan_status._test_ref_problem(ref), '')

    def test_no_mail_sending_library(self):
        """Regel 4: kein Versand – weder SMTP noch fremde Versandbibliotheken im Programmcode."""
        bad = []
        for path in (ROOT / 'sales_tool').rglob('*.py'):
            src = path.read_text(encoding='utf-8')
            if re.search(r'^\s*(import smtplib|from smtplib|import sendgrid|import yagmail)|\.sendmail\(|\.send_message\(', src, re.M):
                bad.append(str(path.relative_to(ROOT)))
        self.assertEqual(bad, [])


if __name__ == '__main__':
    unittest.main()
