import base64
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BASH = os.environ.get('V2RAY_TEST_BASH', 'bash')


class ShellTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / 'src/subscription.sh').exists(), 'subscription commands missing')
        version = subprocess.check_output([BASH, '-c', 'echo "${BASH_VERSINFO[0]}"'], text=True)
        if int(version) < 4:
            self.skipTest('Bash 4+ required; set V2RAY_TEST_BASH')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.core = Path(self.temp.name) / 'core'
        self.conf = self.core / 'conf'
        self.conf.mkdir(parents=True)
        self.state = self.core / 'subscription'
        self.python('setup', 'https://sub.example.com')
        self.node = self.conf / 'VMess-TCP-12345.json'
        self.node.write_text(json.dumps({'inbounds': [{
            'protocol': 'vmess', 'port': 12345,
            'settings': {'clients': [{'id': '11111111-2222-3333-4444-555555555555'}]},
            'streamSettings': {'network': 'tcp', 'tcpSettings': {'header': {'type': 'none'}}}
        }]}))

    def python(self, *args):
        result = subprocess.run([sys.executable, str(ROOT / 'src/subscription.py'),
                                 '--state-dir', str(self.state), *args],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def shell(self, *args, prefix=''):
        harness = r'''
is_sh_dir=$1
is_core_dir=$2
is_conf_dir=$is_core_dir/conf
is_caddy_conf=$is_core_dir/caddy
is_https_port=443
ip=203.0.113.8
shift 2
load() { . "$is_sh_dir/src/$1"; }
msg() { printf '%s\n' "$*"; }
warn() { printf '%s\n' "$*" >&2; }
err() { warn "$*"; [[ $is_dont_auto_exit ]] && return; exit 1; }
_green() { printf '%s' "$*"; }
# Use GNU base64 when available on macOS; Linux uses its native tool.
if command -v gbase64 >/dev/null; then base64() { gbase64 "$@"; }; fi
load protocol.sh
load config.sh
load cmd.sh
'''
        return subprocess.run([BASH, '-c', harness + prefix + '\nmain sub "$@"',
                               'test', str(ROOT), str(self.core), *args],
                              text=True, capture_output=True)

    def grants(self):
        with sqlite3.connect(self.state / 'tokens.sqlite3') as db:
            return db.execute('SELECT name, expires_at FROM grants').fetchall()

    def test_real_base64_generator_and_name_with_spaces(self):
        result = self.shell('base64', '--ttl', '2h', '--name', 'my phone')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('https://sub.example.com/sub?token=', result.stdout)
        content = base64.b64decode((self.state / 'sub.txt').read_bytes()).decode().strip()
        self.assertTrue(content.startswith('vmess://'))
        node = json.loads(base64.b64decode(content[len('vmess://'):]))
        self.assertEqual(node['add'], '203.0.113.8')
        self.assertEqual(node['port'], '12345')
        self.assertEqual(self.grants()[0][0], 'my phone')
        self.assertFalse((self.core / 'sub.txt').exists())
        self.assertEqual((self.state / 'sub.txt').stat().st_mode & 0o777, 0o600)

    def test_refresh_updates_content_without_changing_authorization(self):
        result = self.shell('clash')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        before = self.grants()
        node = json.loads(self.node.read_text())
        node['inbounds'][0]['port'] = 23456
        self.node.write_text(json.dumps(node))
        result = self.shell('refresh', 'clash')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('port: 23456', (self.state / 'sub-clash.yaml').read_text())
        self.assertEqual(self.grants(), before)
        self.assertNotIn('token=', result.stdout)

    def test_failed_generation_keeps_content_and_does_not_issue(self):
        self.assertEqual(self.shell('clash').returncode, 0)
        before = (self.state / 'sub-clash.yaml').read_bytes()
        grants = self.grants()
        self.node.write_text('{ invalid json')
        result = self.shell('clash')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.state / 'sub-clash.yaml').read_bytes(), before)
        self.assertEqual(self.grants(), grants)
        self.assertEqual(list(self.state.glob('.content-*')), [])

    def test_no_supported_nodes_does_not_publish_empty_clash(self):
        node = json.loads(self.node.read_text())
        node['inbounds'][0]['streamSettings']['network'] = 'kcp'
        self.node.write_text(json.dumps(node))
        result = self.shell('clash')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.state / 'sub-clash.yaml').exists())
        self.assertEqual(self.grants(), [])

    def test_structurally_invalid_json_preserves_existing_content(self):
        second = self.conf / 'VMess-TCP-23456.json'
        valid = json.loads(self.node.read_text())
        for mode, filename in [('base64', 'sub.txt'), ('clash', 'sub-clash.yaml')]:
            second.write_text(json.dumps(valid))
            self.assertEqual(self.shell(mode).returncode, 0)
            before = (self.state / filename).read_bytes()
            grants = self.grants()
            for invalid in ('bad', [], [{'id': None}]):
                data = json.loads(self.node.read_text())
                data['inbounds'][0]['settings']['clients'] = invalid
                second.write_text(json.dumps(data))
                with self.subTest(mode=mode, invalid=invalid):
                    self.assertNotEqual(self.shell(mode).returncode, 0)
                    self.assertEqual((self.state / filename).read_bytes(), before)
                    self.assertEqual(self.grants(), grants)

    def test_unknown_protocol_or_network_preserves_existing_content(self):
        second = self.conf / 'second.json'
        valid = json.loads(self.node.read_text())
        for mode, filename in [('base64', 'sub.txt'), ('clash', 'sub-clash.yaml')]:
            second.write_text(json.dumps(valid))
            self.assertEqual(self.shell(mode).returncode, 0)
            before = (self.state / filename).read_bytes()
            grants = self.grants()
            for field in ('network', 'protocol'):
                data = json.loads(self.node.read_text())
                if field == 'network':
                    data['inbounds'][0]['streamSettings']['network'] = 'broken'
                else:
                    data['inbounds'][0]['protocol'] = 'broken'
                second.write_text(json.dumps(data))
                with self.subTest(mode=mode, field=field):
                    self.assertNotEqual(self.shell(mode).returncode, 0)
                    self.assertEqual((self.state / filename).read_bytes(), before)
                    self.assertEqual(self.grants(), grants)

    def test_invalid_arguments_leave_content_unchanged(self):
        for args in [('clash', '--ttl', '0d'), ('clash', '--unknown'), ('refresh', 'bogus')]:
            with self.subTest(args=args):
                self.assertNotEqual(self.shell(*args).returncode, 0)
        self.assertFalse((self.state / 'sub-clash.yaml').exists())
        self.assertEqual(self.grants(), [])

    def test_missing_setup_and_empty_nodes_fail_closed(self):
        self.node.unlink()
        self.assertNotEqual(self.shell('base64').returncode, 0)
        shutil.rmtree(self.state)
        self.assertNotEqual(self.shell('base64').returncode, 0)
        self.assertFalse((self.core / 'sub.txt').exists())


if __name__ == '__main__':
    unittest.main()
