"""Entwicklungswerkzeug Graphify (tools/code_graph.py): nur Code, kein KI-Backend, keine Hooks, nicht im Release."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))

import code_graph  # noqa: E402


class CodeGraphToolTests(unittest.TestCase):
    def run_tool(self, args):
        calls = []

        class Done:
            returncode = 0

        def fake_run(cmd, **kw):
            calls.append((cmd, kw))
            return Done()

        old = code_graph.graphify_exe
        code_graph.graphify_exe = lambda: 'graphify'
        try:
            self.assertEqual(code_graph.main(args, run=fake_run), 0)
        finally:
            code_graph.graphify_exe = old
        return calls[0]

    def test_build_is_code_only_without_backend(self):
        cmd, kw = self.run_tool(['bauen'])
        self.assertEqual(cmd, ['graphify', 'extract', '.', '--code-only'])
        self.assertEqual(kw['cwd'], ROOT)
        self.assertEqual(kw['env']['GRAPHIFY_BACKEND'], 'none')

    def test_api_keys_never_reach_graphify(self):
        env = code_graph.safe_env({'PATH': '/bin', 'ANTHROPIC_API_KEY': 'x', 'OPENAI_API_KEY': 'x', 'GEMINI_API_KEY': 'x',
                                   'MOONSHOT_API_KEY': 'x', 'AWS_SECRET_ACCESS_KEY': 'x', 'GITHUB_TOKEN': 'x',
                                   'GRAPHIFY_BACKEND': 'claude'})
        self.assertEqual(env['PATH'], '/bin')
        self.assertEqual(env['GRAPHIFY_BACKEND'], 'none')
        self.assertFalse([k for k in env if re.search('KEY|TOKEN|SECRET', k)])

    def test_install_hooks_and_watch_are_refused(self):
        for sub in ('install', 'hook', 'watch', 'clone', 'global', 'extract', 'claude'):
            with self.subTest(sub), self.assertRaises(SystemExit):
                code_graph.command([sub])

    def test_read_only_queries_pass_through(self):
        cmd, _ = self.run_tool(['explain', 'assert_contact_allowed'])
        self.assertEqual(cmd, ['graphify', 'explain', 'assert_contact_allowed'])

    def test_lock_pinned_with_hashes_and_output_ignored(self):
        text = (ROOT / 'tools' / 'requirements-lock-graphify.txt').read_text(encoding='utf-8')
        self.assertRegex(text, r'(?m)^graphifyy==\S+ \\\n    --hash=sha256:[0-9a-f]{64}')
        pins = re.findall(r'(?m)^([A-Za-z0-9_.-]+)==', text)
        hashed = re.findall(r'(?m)^[A-Za-z0-9_.-]+==[^\n]*\\\n    --hash=sha256:', text)
        self.assertEqual(len(pins), len(hashed), 'jede Abhängigkeit mit Prüfsumme')
        self.assertIn('graphify-out/', (ROOT / '.gitignore').read_text(encoding='utf-8').splitlines())
        import build_release
        self.assertFalse([f for f in build_release.release_files() if 'graphify' in f])


if __name__ == '__main__':
    unittest.main()
