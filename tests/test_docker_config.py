import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DockerConfigTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / 'docker/prepare-config').exists(), 'persistent config setup missing')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.volume = self.base / 'volume'
        self.volume.mkdir()
        self.core = self.new_container('first')

    def new_container(self, name):
        core = self.base / name
        core.mkdir()
        (core / 'state').symlink_to(self.volume, target_is_directory=True)
        return core

    def prepare(self, core=None):
        return subprocess.run(['bash', str(ROOT / 'docker/prepare-config'), str(core or self.core)],
                              capture_output=True, text=True)

    def test_writes_through_standard_path_survive_a_new_container(self):
        self.assertEqual(self.prepare().returncode, 0)
        expected = {'dns': {'servers': ['1.1.1.1']}, 'inbounds': []}
        (self.core / 'config.json').write_text(json.dumps(expected))
        second = self.new_container('second')
        self.assertEqual(self.prepare(second).returncode, 0)
        self.assertEqual(json.loads((second / 'config.json').read_text()), expected)
        self.assertEqual((self.volume / 'config.json').stat().st_mode & 0o777, 0o600)

    def test_corrupt_or_empty_persistent_config_is_not_reinitialized(self):
        for content in ('', '{broken', '[]', '{}\n{}', '[]\n{}'):
            with self.subTest(content=content):
                (self.volume / 'config.json').write_text(content)
                self.assertNotEqual(self.prepare().returncode, 0)
                self.assertEqual((self.volume / 'config.json').read_text(), content)


if __name__ == '__main__':
    unittest.main()
