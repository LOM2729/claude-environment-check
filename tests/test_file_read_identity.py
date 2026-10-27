"""Stable same-file reads across Windows stat/fstat timestamp semantics.

Only synthetic local files and fixed mocked stat fields are used. No collection,
application launch, network access, or raw user-file diagnostics are involved.
"""
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import claude_setup as c


class FileReadIdentity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / 'synthetic.bin'
        self.data = b'synthetic bytes'
        self.path.write_bytes(self.data)

    def tearDown(self):
        self.temp.cleanup()

    def info(self, **updates):
        value = dict(st_mode=stat.S_IFREG | 0o600, st_dev=1, st_ino=42,
                     st_size=len(self.data), st_mtime_ns=100, st_ctime_ns=1000)
        value.update(updates)
        return SimpleNamespace(**value)

    def read_with_stats(self, mutations=None, windows=True):
        # Deliberately model different stable creation/change times.
        records = {key: self.info(st_ctime_ns=2000 if windows and key in ('opened', 'after') else 1000)
                   for key in ('before', 'opened', 'after', 'final')}
        for phase, fields in (mutations or {}).items():
            records[phase] = SimpleNamespace(**(vars(records[phase]) | fields))
        # Returning the existing native Path avoids constructing WindowsPath on
        # a POSIX test host while os.name selects the Windows comparison branch.
        with mock.patch.object(c, 'Path', lambda value: self.path), \
             mock.patch.object(type(self.path), 'lstat', side_effect=[records['before'], records['final']]), \
             mock.patch.object(c.os, 'fstat', side_effect=[records['opened'], records['after']]), \
             mock.patch.object(c.os, 'name', 'nt' if windows else 'posix'):
            return c.read_bytes(self.path)

    def test_windows_stable_path_and_handle_ctime_domains_can_differ(self):
        self.assertEqual(self.read_with_stats(), self.data)

    def test_windows_path_ctime_change_is_rejected(self):
        with self.assertRaisesRegex(c.SetupError, '^INPUT_CHANGED$'):
            self.read_with_stats({'final': {'st_ctime_ns': 1001}})

    def test_windows_handle_ctime_change_is_rejected(self):
        with self.assertRaisesRegex(c.SetupError, '^INPUT_CHANGED$'):
            self.read_with_stats({'after': {'st_ctime_ns': 2001}})

    def test_windows_identity_size_and_mtime_must_match_every_phase(self):
        for phase in ('opened', 'after', 'final'):
            for field, value in (('st_dev', 2), ('st_ino', 99),
                                 ('st_size', len(self.data) + 1), ('st_mtime_ns', 101)):
                with self.subTest(phase=phase, field=field):
                    with self.assertRaisesRegex(c.SetupError, '^INPUT_CHANGED$'):
                        self.read_with_stats({phase: {field: value}})

    def test_posix_strict_ctime_comparison_is_preserved(self):
        self.assertEqual(self.read_with_stats(windows=False), self.data)
        with self.assertRaisesRegex(c.SetupError, '^INPUT_CHANGED$'):
            self.read_with_stats({'after': {'st_ctime_ns': 2000}}, windows=False)
        with self.assertRaisesRegex(c.SetupError, '^INPUT_CHANGED$'):
            self.read_with_stats({'final': {'st_ctime_ns': 2000}}, windows=False)

    def test_bounded_native_read_is_unchanged(self):
        self.assertEqual(c.read_bytes(self.path), self.data)
        with self.assertRaisesRegex(c.SetupError, '^INPUT_TOO_LARGE$'):
            c.read_bytes(self.path, maximum=2)

    @unittest.skipUnless(os.name == 'nt', 'native Windows rewritten and atomically replaced files')
    def test_windows_native_rewrite_and_atomic_save_are_readable(self):
        self.path.write_bytes(b'first contents')
        self.path.write_bytes(self.data)
        self.assertEqual(c.read_bytes(self.path), self.data)
        replacement = self.root / 'stage.bin'
        replacement.write_bytes(b'replacement contents')
        os.replace(replacement, self.path)
        self.assertEqual(c.read_bytes(self.path), b'replacement contents')


if __name__ == '__main__':
    unittest.main()
