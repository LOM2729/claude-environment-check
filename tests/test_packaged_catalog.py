"""Trusted frozen assets may link within an app; user config readers stay strict."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import claude_setup as c
import ai_routing as ai


class PackagedCatalog(unittest.TestCase):
    def test_regular_frozen_asset_and_legacy_frozen_flag(self):
        with patch.object(sys, 'frozen', True, create=True):
            expected = c.load_json((ROOT / 'src/ai_domains.json').read_bytes())
            self.assertEqual(ai.catalog(c), expected)

    def test_app_internal_data_link_and_external_escape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve(); framework = root / 'Contents/Frameworks'; resources = root / 'Contents/Resources'
            framework.mkdir(parents=True); resources.mkdir()
            data = (ROOT / 'src/ai_domains.json').read_bytes()
            (resources / 'ai_domains.json').write_bytes(data)
            asset = framework / 'ai_domains.json'
            try:asset.symlink_to(resources / 'ai_domains.json')
            except OSError:self.skipTest('symlink unavailable')
            with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', str(framework), create=True), patch.object(ai, '__file__', str(framework / 'ai_routing.py')):
                self.assertTrue(ai.catalog(c)['suffixes'])
                asset.unlink(); outside = root / 'outside.json'; outside.write_bytes(data); asset.symlink_to(outside)
                with self.assertRaisesRegex(c.SetupError, 'AI_CATALOG_OUTSIDE_BUNDLE'):
                    ai.catalog(c)


if __name__ == '__main__':unittest.main()
