"""Opt-in real-container tests: V2RAY_DOCKER_IMAGE=v2raynext:test python3 -m unittest discover -s tests -v."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import unittest
from urllib.parse import urlsplit
import uuid


ROOT = Path(__file__).resolve().parents[1]
IMAGE = os.environ.get('V2RAY_DOCKER_IMAGE')


@unittest.skipUnless(IMAGE, 'set V2RAY_DOCKER_IMAGE to run real Docker tests')
class DockerIntegrationTest(unittest.TestCase):
    def command(self, *args, check=True, input=None, timeout=360):
        result = subprocess.run(args, input=input, capture_output=True, text=True, timeout=timeout)
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def compose(self, *args, **kwargs):
        return self.command('docker', 'compose', '-p', self.name, '-f', str(self.compose_file),
                            *args, **kwargs)

    def execute(self, *args, **kwargs):
        return self.command('docker', 'exec', '-e', 'ip=203.0.113.8', self.name, *args, **kwargs)

    def setUp(self):
        self.name = 'v2raynext-test-' + uuid.uuid4().hex[:10]
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        config = json.loads(self.command('docker', 'compose', 'config', '--format', 'json').stdout)
        config['name'] = self.name
        service = config['services']['v2ray']
        service.pop('build')
        service.pop('network_mode')  # Isolated bridge; no host ports or external services touched.
        service.update(image=IMAGE, container_name=self.name, restart='no')
        service['healthcheck'] = {'interval': '1s', 'timeout': '5s', 'start_period': '5m', 'retries': 3}
        for key, volume in config['volumes'].items():
            volume['name'] = self.name + '-' + key
        self.compose_file = Path(self.temp.name) / 'compose.json'
        self.compose_file.write_text(json.dumps(config))
        self.addCleanup(lambda: self.compose('down', '--volumes', '--remove-orphans', check=False))

    def ready(self):
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            status = self.command('docker', 'inspect', self.name, '--format',
                                  '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}').stdout.strip()
            if status == 'running healthy':
                return
            if status.startswith('exited'):
                break
            time.sleep(1)
        self.fail('Container did not become healthy: ' + self.compose('logs').stdout)

    def issue(self, ttl='1d'):
        output = self.execute('v2ray', 'sub', '--ttl', ttl).stdout
        url = re.search(r'https://sub\.example\.com/sub\?token=[A-Za-z0-9_-]+', output).group()
        grant_id = re.search(r'授权 ID: (\S+)', output).group(1)
        return urlsplit(url).path + '?' + urlsplit(url).query, grant_id

    def request(self, path):
        result = self.execute('curl', '-sS', '-w', '\n%{http_code}', 'http://127.0.0.1:8787' + path)
        body, status = result.stdout.rsplit('\n', 1)
        return int(status), body

    def test_detached_cli_and_recreation_preserve_config_nodes_and_authorization(self):
        self.compose('up', '-d')
        self.ready()
        self.assertEqual(self.command('docker', 'inspect', self.name, '--format', '{{.Config.Tty}}').stdout.strip(), 'false')
        self.execute('v2ray', 'add', 'tcp', 'auto')
        self.execute('v2ray', 'dns', '11')
        self.execute('v2ray', 'sub', 'setup', 'https://sub.example.com')
        valid, _ = self.issue()
        revoked, grant_id = self.issue()
        expired, _ = self.issue('1s')
        self.execute('v2ray', 'sub', 'revoke', grant_id)
        config = self.execute('cat', '/etc/v2ray/config.json').stdout
        self.assertEqual(json.loads(config)['dns']['servers'], ['1.1.1.1'])
        nodes = self.execute('sh', '-c', 'cat /etc/v2ray/conf/*.json').stdout
        node_port = str(json.loads(nodes)['inbounds'][0]['port'])
        self.execute('python3', '-c', 'import socket,sys; socket.create_connection(("127.0.0.1", int(sys.argv[1])), 2).close()', node_port)
        status, payload = self.request(valid)
        self.assertEqual(status, 200)
        self.assertTrue(base64.b64decode(payload).startswith(b'vmess://'))
        # A core stop must not affect the subscription service; health must detect it.
        self.execute('systemctl', 'stop', 'v2ray.service')
        self.execute('systemctl', 'is-active', 'v2ray-subscription.service')
        self.assertNotEqual(self.execute('bash', '/etc/v2ray/sh/docker/healthcheck', check=False).returncode, 0)
        self.execute('systemctl', 'start', 'v2ray.service')
        self.execute('bash', '/etc/v2ray/sh/docker/healthcheck')
        # Down (without -v) removes the writable layer and preserves only Compose volumes.
        self.compose('stop')
        self.assertEqual(self.command('docker', 'inspect', self.name, '--format', '{{.State.ExitCode}}').stdout.strip(), '0')
        self.compose('down')
        self.compose('up', '-d')
        self.ready()
        self.assertEqual(self.execute('cat', '/etc/v2ray/config.json').stdout, config)
        self.assertEqual(self.execute('sh', '-c', 'cat /etc/v2ray/conf/*.json').stdout, nodes)
        self.execute('python3', '-c', 'import socket,sys; socket.create_connection(("127.0.0.1", int(sys.argv[1])), 2).close()', node_port)
        self.assertEqual(self.request(valid), (200, payload))
        self.assertEqual(self.request(revoked)[0], 403)
        self.assertEqual(self.request(expired)[0], 403)
        self.assertEqual(self.request('/sub')[0], 403)
        self.execute('v2ray', 'sub', 'stop')
        self.execute('systemctl', 'is-active', 'v2ray.service')
        self.assertNotEqual(self.execute('bash', '/etc/v2ray/sh/docker/healthcheck', check=False).returncode, 0)
        self.execute('systemctl', 'disable', 'v2ray-subscription.service')
        self.execute('bash', '/etc/v2ray/sh/docker/healthcheck')
        self.compose('down')
        self.compose('up', '-d')
        self.ready()
        self.assertNotEqual(self.execute('systemctl', 'is-active', 'v2ray-subscription.service', check=False).returncode, 0)
        self.assertNotEqual(self.execute('systemctl', 'is-enabled', 'v2ray-subscription.service', check=False).returncode, 0)
        self.execute('systemctl', 'enable', 'v2ray-subscription.service')
        self.execute('v2ray', 'sub', 'restart')
        self.execute('bash', '/etc/v2ray/sh/docker/healthcheck')
        # Corrupt persisted data must stop startup rather than silently reset user settings.
        self.compose('down')
        self.compose('run', '--rm', '-T', '--no-deps', '--entrypoint', 'sh', 'v2ray', '-c',
                     'printf broken > /etc/v2ray/state/config.json')
        result = self.compose('run', '--rm', '-T', '--no-deps', 'v2ray', check=False)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('Invalid main config', result.stderr)


if __name__ == '__main__':
    unittest.main()
