import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DockerCoreServiceTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / 'docker/core-service').exists(), 'core lifecycle adapter missing')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.core = Path(self.temp.name)
        (self.core / 'bin').mkdir()
        self.binary = self.core / 'bin/v2ray'
        self.binary.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(120)\n')
        self.binary.chmod(0o755)
        (self.core / 'config.json').write_text('{}')
        self.env = dict(os.environ, V2RAY_ROOT=str(self.core), V2RAY_SCRIPT_DIR=str(ROOT),
                        V2RAY_LOG_DIR=str(self.core / 'logs'))
        self.addCleanup(lambda: self.ctl('stop'))

    def ctl(self, action, service='v2ray.service'):
        return subprocess.run(['bash', str(ROOT / 'docker/systemctl'), action, service],
                              env=self.env, capture_output=True, text=True, timeout=10)

    def test_start_is_idempotent_and_restart_stop_report_real_state(self):
        self.assertNotEqual(self.ctl('is-active').returncode, 0)
        self.assertEqual(self.ctl('start').returncode, 0)
        pid_file = self.core / 'run/core.pid'
        pid = pid_file.read_text()
        self.assertEqual(self.ctl('start').returncode, 0)
        self.assertEqual(pid_file.read_text(), pid)
        self.assertEqual(self.ctl('is-active').returncode, 0)
        self.assertNotEqual(self.ctl('stop', 'not-v2ray.service').returncode, 0)
        self.assertEqual(self.ctl('is-active').returncode, 0)
        self.assertEqual(self.ctl('restart').returncode, 0)
        self.assertNotEqual(pid_file.read_text(), pid)
        self.assertEqual(self.ctl('stop').returncode, 0)
        self.assertNotEqual(self.ctl('is-active').returncode, 0)
        self.assertNotEqual(self.ctl('status').returncode, 0)

    def test_failed_process_is_not_reported_as_started(self):
        self.binary.write_text('#!/bin/sh\nexit 1\n')
        self.assertNotEqual(self.ctl('start').returncode, 0)
        self.assertNotEqual(self.ctl('is-active').returncode, 0)


if __name__ == '__main__':
    unittest.main()
