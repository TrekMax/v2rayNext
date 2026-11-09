import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BASH = os.environ.get('V2RAY_TEST_BASH', 'bash')


class ServiceTest(unittest.TestCase):
    def test_systemd_setup_generates_unit_and_removes_old_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            core = Path(directory) / 'core'
            core.mkdir()
            (core / 'sub.txt').write_text('old base64')
            (core / 'sub-clash.yaml').write_text('old clash')
            harness = r'''
is_sh_dir=$1
is_core_dir=$2
is_systemd_dir=$3
mkdir -p "$is_systemd_dir"
load() { . "$is_sh_dir/src/$1"; }
msg() { :; }
warn() { printf '%s\n' "$*" >&2; }
# The host service manager is the only unavailable boundary in this test.
systemctl() { printf '%s\n' "$*" >> "$is_core_dir/service-commands"; }
load subscription.sh
subscription_command setup https://sub.example.com
'''
            result = subprocess.run([BASH, '-c', harness, 'test', str(ROOT), str(core),
                                     str(Path(directory) / 'units')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            unit = Path(directory) / 'units/v2ray-subscription.service'
            self.assertTrue(unit.exists())
            self.assertFalse((core / 'sub.txt').exists())
            self.assertFalse((core / 'sub-clash.yaml').exists())
            self.assertTrue((core / 'subscription/tokens.sqlite3').exists())

    def test_docker_manager_real_start_stop_restart_and_enable_state(self):
        with tempfile.TemporaryDirectory() as directory:
            core = Path(directory)
            state = core / 'subscription'
            result = subprocess.run([sys.executable, str(ROOT / 'src/subscription.py'),
                                     '--state-dir', str(state), 'setup', 'https://sub.example.com'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            env = dict(os.environ, V2RAY_ROOT=str(core), V2RAY_SCRIPT_DIR=str(ROOT))

            def ctl(action, *extra):
                return subprocess.run([BASH, str(ROOT / 'docker/systemctl'), action,
                                       *extra, 'v2ray-subscription.service'], env=env,
                                      capture_output=True, text=True, timeout=10)
            self.addCleanup(lambda: ctl('stop'))
            self.assertNotEqual(ctl('is-active', '--quiet').returncode, 0)
            self.assertEqual(ctl('enable').returncode, 0)
            self.assertEqual(ctl('is-enabled', '--quiet').returncode, 0)
            self.assertEqual(ctl('start').returncode, 0)
            self.assertEqual(ctl('is-active', '--quiet').returncode, 0)
            first_pid = (state / 'service.pid').read_text()
            self.assertEqual(ctl('start').returncode, 0)
            self.assertEqual((state / 'service.pid').read_text(), first_pid)
            self.assertEqual(ctl('restart').returncode, 0)
            self.assertNotEqual((state / 'service.pid').read_text(), first_pid)
            self.assertEqual(ctl('stop').returncode, 0)
            self.assertNotEqual(ctl('is-active', '--quiet').returncode, 0)
            self.assertEqual(ctl('is-enabled', '--quiet').returncode, 0)
            self.assertEqual(ctl('disable').returncode, 0)
            self.assertNotEqual(ctl('is-enabled', '--quiet').returncode, 0)


if __name__ == '__main__':
    unittest.main()
