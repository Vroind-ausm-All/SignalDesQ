"""Code-Graph von SignalDesk mit Graphify – lokal, nur Quelltext, ohne KI-Backend, ohne Hooks (Entwicklungswerkzeug).

python tools/code_graph.py bauen                      # Graph aus dem Quelltext erzeugen (graphify-out/, nicht eingecheckt)
python tools/code_graph.py explain assert_contact_allowed
python tools/code_graph.py affected sales_tool/workday.py
python tools/code_graph.py path create_call contact_lock
python tools/code_graph.py query "Wo wird die Sperrliste geprüft?"

Installation (einmalig, eigene Umgebung): pip install --require-hashes -r tools/requirements-lock-graphify.txt
Original: github.com/Graphify-Labs/graphify (Apache-2.0), Pin und Rechte in docs/SKILLS_REGISTRY.md.

Warum ein eigener Aufruf statt `graphify` direkt:
- `graphify install` und `graphify hook …` schreiben Hooks und einen Block in CLAUDE.md (Regel 3 des Skill-Registers) – gesperrt.
- `graphify extract` wählt sonst selbst ein KI-Backend nach vorhandenen API-Keys und schickt Doku-Inhalte dorthin.
  Hier gilt immer `--code-only` und `GRAPHIFY_BACKEND=none`; API-Keys werden dem Prozess gar nicht erst mitgegeben.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Nur lesende Abfragen auf einem fertigen Graphen; alles andere (install, hook, watch, clone, global, prs …) bleibt gesperrt.
QUERIES = ('explain', 'affected', 'path', 'query')
# Umgebungsvariablen, über die Graphify ein KI-Backend finden könnte – werden entfernt.
SECRET_MARKERS = ('API_KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL')
SECRET_PREFIXES = ('ANTHROPIC_', 'OPENAI_', 'AZURE_OPENAI_', 'GEMINI_', 'GOOGLE_', 'MOONSHOT_', 'DEEPSEEK_', 'AWS_',
                   'OLLAMA_', 'GRAPHIFY_')


def safe_env(base=None):
    env = {k: v for k, v in (os.environ if base is None else base).items()
           if not k.startswith(SECRET_PREFIXES) and not any(m in k.upper() for m in SECRET_MARKERS)}
    env.update({'GRAPHIFY_BACKEND': 'none', 'GRAPHIFY_NO_TIPS': '1', 'GRAPHIFY_NO_CTA': '1', 'DO_NOT_TRACK': '1'})
    return env


def graphify_exe():
    exe = os.environ.get('SIGNALDESK_GRAPHIFY') or shutil.which('graphify') \
        or shutil.which('graphify', path=str(Path(sys.executable).parent))
    if not exe:
        raise SystemExit('Graphify fehlt: pip install --require-hashes -r tools/requirements-lock-graphify.txt')
    return exe


def command(args):
    if not args:
        raise SystemExit(__doc__)
    if args[0] == 'bauen':
        return ['extract', '.', '--code-only'] + args[1:]
    if args[0] in QUERIES:
        return list(args)
    raise SystemExit(f'„{args[0]}“ ist hier nicht erlaubt. Erlaubt: bauen, {", ".join(QUERIES)}.')


def main(argv=None, run=subprocess.run):
    cmd = command(list(sys.argv[1:] if argv is None else argv))
    return run([graphify_exe(), *cmd], cwd=ROOT, env=safe_env(), check=False).returncode


if __name__ == '__main__':
    sys.exit(main())
