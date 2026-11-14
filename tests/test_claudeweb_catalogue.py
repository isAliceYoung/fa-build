"""claudeweb.json: the prebuilt ClaudeWeb versions every VPS's root updater trusts.

The root updater (fa: webdesktop-deploy/scripts/claudeweb_release.py) rejects the whole file if any
field differs from this shape, so a malformed edit here would stop all ClaudeWeb installs and updates.
"""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r'(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})')
SHA1, SHA256 = re.compile('[0-9a-f]{40}'), re.compile('[0-9a-f]{64}')


def key(version):
    return tuple(map(int, VERSION.fullmatch(version).groups()))


class Catalogue(unittest.TestCase):
    def setUp(self):
        raw = (ROOT/'claudeweb.json').read_bytes()
        self.assertLessEqual(len(raw), 256 * 1024)
        self.value = json.loads(raw)

    def test_shape_matches_what_root_accepts(self):
        value = self.value
        self.assertEqual(set(value), {'schema', 'repository', 'latest', 'versions'})
        self.assertEqual(value['schema'], 1)
        self.assertEqual(value['repository'], 'git@github.com:isAliceYoung/fa.git')
        self.assertTrue(0 < len(value['versions']) <= 64)
        self.assertEqual(value['latest'], max(value['versions'], key=key))
        for version, entry in value['versions'].items():
            with self.subTest(version=version):
                self.assertTrue(VERSION.fullmatch(version))
                self.assertEqual(set(entry), {'tag', 'commit', 'source_commit', 'archive', 'parts', 'unpacked_bytes',
                                              'requires_webdesktop', 'notes'})
                self.assertEqual(entry['tag'], 'claudeweb-v' + version)
                self.assertTrue(SHA1.fullmatch(entry['commit']) and SHA1.fullmatch(entry['source_commit']))
                self.assertTrue(VERSION.fullmatch(entry['requires_webdesktop']))
                self.assertLessEqual(len(entry['notes']), 4000)
                name = 'claudeweb-%s-linux-x64.tar.xz' % version
                self.assertEqual(entry['archive']['name'], name)
                self.assertTrue(SHA256.fullmatch(entry['archive']['sha256']))
                self.assertTrue(0 < entry['unpacked_bytes'] <= 2 * 1024**3)
                self.assertEqual([p['name'] for p in entry['parts']], ['%s.part%02d' % (name, i) for i in range(len(entry['parts']))])
                for part in entry['parts']:
                    self.assertTrue(SHA256.fullmatch(part['sha256']) and 0 < part['bytes'] <= 100 * 1024**2)
                self.assertEqual(sum(p['bytes'] for p in entry['parts']), entry['archive']['bytes'])

    def test_every_version_runs_on_a_desktop_that_can_install_claudeweb(self):
        maintenance = json.loads((ROOT/'cloudcli-maintenance.json').read_text(encoding='utf-8'))
        oldest = min(maintenance['supported_versions'], key=key)
        newest = min(self.value['versions'].values(), key=lambda e: key(e['requires_webdesktop']))
        self.assertLessEqual(key(newest['requires_webdesktop']), key(oldest))


if __name__ == '__main__':
    unittest.main()
