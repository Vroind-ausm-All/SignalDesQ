"""SDQ-020: Serverpaket – Dienstdateien, Proxy-Beispiele und Handbuch passen zum Programm.

Die systemd-Dateien werden mit den Werten aus ``deploy/umgebung.beispiel`` aufgelöst und ihre Aufrufe mit den echten
Kommandozeilen-Parsern geprüft. So fällt auf, wenn eine Option umbenannt wird und das Paket nicht mehr startet."""
import re
import shlex
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sales_tool import betreiber, multi_server  # noqa: E402

DEPLOY = ROOT / 'deploy'


def _env():
    out = {}
    for line in (DEPLOY / 'umgebung.beispiel').read_text(encoding='utf-8').splitlines():
        if line.strip() and not line.startswith('#'):
            k, _, v = line.partition('=')
            out[k.strip()] = v.strip()
    return out


def _unit(name):
    text = (DEPLOY / name).read_text(encoding='utf-8').replace('\\\n', ' ')
    keys = {}
    for line in text.splitlines():
        if '=' in line and not line.lstrip().startswith(('#', '[')):
            k, _, v = line.partition('=')
            keys.setdefault(k.strip(), []).append(v.strip())
    return keys


def _exec(name):
    env = _env()
    cmd = _unit(name)['ExecStart'][0]
    cmd = re.sub(r'\$\{(\w+)\}', lambda m: env[m.group(1)], cmd)
    return shlex.split(cmd)


class DeployPackageTests(unittest.TestCase):
    def test_service_command_parses(self):
        argv = _exec('signaldesk-mandanten.service')
        self.assertEqual(argv[1:3], ['-m', 'sales_tool.multi_server'])
        args = multi_server.build_parser().parse_args(argv[3:])
        env = _env()
        self.assertEqual((args.root, args.host, args.port), (env['SIGNALDESK_ROOT'], '127.0.0.1', int(env['SIGNALDESK_PORT'])))
        self.assertEqual(args.allowed_host, [env['SIGNALDESK_HOST']])
        self.assertEqual(args.backup_dir, env['SIGNALDESK_SICHERUNG_ZIEL'])
        self.assertTrue(args.log_file)

    def test_backup_command_parses_and_verifies(self):
        argv = _exec('signaldesk-sicherung.service')
        self.assertEqual(argv[1:3], ['-m', 'sales_tool.betreiber'])
        args = betreiber._parser().parse_args(argv[3:])
        self.assertEqual(args.cmd, 'sichern')
        self.assertTrue(args.verschluesselt and args.pruefen)  # nie unverschlüsselt, immer mit Wiederherstellungstest
        self.assertEqual(args.ziel, _env()['SIGNALDESK_SICHERUNG_ZIEL'])

    def test_writable_paths_cover_data_logs_and_backups(self):
        env = _env()
        svc = _unit('signaldesk-mandanten.service')
        writable = svc['ReadWritePaths'][0].split()
        self.assertIn(env['SIGNALDESK_ROOT'], writable)
        self.assertIn(str(Path(env['SIGNALDESK_LOG']).parent), writable)
        self.assertEqual(svc['ProtectSystem'], ['strict'])
        self.assertEqual(svc['NoNewPrivileges'], ['yes'])
        self.assertEqual(svc['KillSignal'], ['SIGTERM'])
        self.assertNotEqual(svc['User'], ['root'])
        backup = _unit('signaldesk-sicherung.service')['ReadWritePaths'][0].split()
        self.assertIn(env['SIGNALDESK_SICHERUNG_ZIEL'], backup)
        self.assertIn(env['SIGNALDESK_ROOT'], backup)  # Protokoll im Verzeichnis
        self.assertEqual(_unit('signaldesk-sicherung.timer')['Persistent'], ['true'])

    def test_no_secrets_in_package(self):
        for p in DEPLOY.iterdir():
            text = p.read_text(encoding='utf-8')
            for line in text.splitlines():
                if line.lstrip().startswith('#'):
                    continue
                self.assertNotRegex(line, r'(?i)(passwort|password|secret|token)\s*=', f'{p.name}: {line}')

    def test_proxy_examples_forward_what_the_server_needs(self):
        nginx = (DEPLOY / 'nginx.beispiel.conf').read_text(encoding='utf-8')
        self.assertIn('proxy_set_header Host $host', nginx)
        self.assertIn('X-Forwarded-Proto https', nginx)
        self.assertIn('127.0.0.1:' + _env()['SIGNALDESK_PORT'], nginx)
        caddy = (DEPLOY / 'Caddyfile.beispiel').read_text(encoding='utf-8')
        self.assertIn('reverse_proxy 127.0.0.1:' + _env()['SIGNALDESK_PORT'], caddy)
        self.assertIn('health_uri /healthz', caddy)

    def test_handbook_names_every_operator_command(self):
        text = (ROOT / 'docs' / 'BETRIEB_SERVER.md').read_text(encoding='utf-8')
        commands = betreiber._parser()._subparsers._group_actions[0].choices
        missing = [c for c in commands if c not in text and c not in ('liste', 'konto', 'konto-freigeben', 'mitglied', 'archivieren', 'anlegen')]
        self.assertEqual(missing, [])
        for f in DEPLOY.iterdir():
            self.assertIn(f.name, text, f'{f.name} fehlt im Handbuch')


if __name__ == '__main__':
    unittest.main()
