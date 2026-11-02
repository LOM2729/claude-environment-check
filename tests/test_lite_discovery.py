import contextlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))
from lite import discovery


CONFIG = {'proxies': [{'name': 'private-node', 'type': 'socks5', 'server': '192.0.2.1',
                       'port': 1080, 'password': 'SECRET_DO_NOT_PRINT'}],
          'rules': ['MATCH,private-node']}


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relative, value=CONFIG):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def discover(self, **kwargs):
        return discovery.discover(home=self.home, platform='darwin', environ={}, **kwargs)

    def selected(self, root='.config/clash-verge', name='selected.yaml'):
        self.write(f'{root}/profiles.yaml', {'current': 'uuid-one', 'items': [
            {'uid': 'uuid-one', 'file': name, 'name': 'SECRET_METADATA',
             'url': 'https://example.invalid/SECRET_SUBSCRIPTION'}]})
        return self.write(f'{root}/profiles/{name}')

    def test_empty_home_returns_fixed_warning(self):
        self.assertEqual(self.discover(), {'candidates': [], 'limited': False,
                                         'warnings': ['ACTIVE_PROFILE_NOT_CONFIRMED']})

    def test_verge_selection_maps_current_uid_to_profile(self):
        selected = self.selected()
        other = self.write('.config/clash-verge/profiles/newer.yaml')
        os.utime(other, (2000000000, 2000000000))
        result = self.discover()
        by_path = {item['path']: item for item in result['candidates']}
        self.assertTrue(by_path[str(selected)]['active'])
        self.assertFalse(by_path[str(other)]['active'])
        self.assertEqual(by_path[str(selected)]['selection_evidence'],
                         'clash_verge_profiles_current')
        self.assertNotIn('SECRET', json.dumps(result))

    def test_multiple_configs_without_metadata_do_not_use_mtime(self):
        first = self.write('.config/clash/config.yaml')
        second = self.write('.config/mihomo/config.json')
        os.utime(first, (100, 100))
        os.utime(second, (2000000000, 2000000000))
        result = self.discover()
        self.assertEqual(len(result['candidates']), 2)
        self.assertFalse(any(item['active'] for item in result['candidates']))

    def test_complete_verge_runtime_candidate_is_not_claimed_active(self):
        runtime = self.write('.config/clash-verge/clash-verge.yaml')
        result = self.discover()
        self.assertEqual(len(result['candidates']), 1)
        row = result['candidates'][0]
        self.assertEqual(row['path'], str(runtime))
        self.assertIn('运行配置候选', row['label'])
        self.assertFalse(row['active'])
        self.assertIsNone(row['selection_evidence'])

    def test_directory_enumeration_without_fd_support(self):
        selected = self.selected()
        original = discovery._open_local
        def open_file_only(path, directory=False):
            self.assertFalse(directory, 'Windows os.open cannot open directories')
            return original(path, directory=False)
        with patch.object(os, 'supports_fd', set()), patch.object(discovery, '_open_local', open_file_only):
            result = self.discover()
        self.assertEqual(result['candidates'][0]['path'], str(selected))
        self.assertTrue(result['candidates'][0]['active'])

    def test_two_clients_selected_require_user_choice(self):
        self.selected()
        self.selected('Library/Application Support/io.github.clash-verge-rev.clash-verge-rev')
        result = self.discover()
        self.assertFalse(any(item['active'] for item in result['candidates']))
        self.assertTrue(all(item['selection_evidence'] for item in result['candidates']))
        self.assertIn('MULTIPLE_SELECTED_PROFILES', result['warnings'])

    def test_unsafe_metadata_path_cannot_select_or_open_outside_profile_dir(self):
        self.write('.config/clash-verge/profiles.yaml', {'current': 'x', 'items': [
            {'uid': 'x', 'file': '../../SECRET.yaml'}]})
        self.write('.config/clash-verge/profiles/fallback.yaml')
        result = self.discover()
        self.assertEqual(len(result['candidates']), 1)
        self.assertFalse(result['candidates'][0]['active'])
        self.assertIn('SELECTION_METADATA_UNAVAILABLE', result['warnings'])

    def test_duplicate_uid_metadata_is_ambiguous(self):
        self.write('.config/clash-verge/profiles.yaml', {'current': 'x', 'items': [
            {'uid': 'x', 'file': 'a.yaml'}, {'uid': 'x', 'file': 'b.yaml'}]})
        self.write('.config/clash-verge/profiles/a.yaml')
        self.assertFalse(self.discover()['candidates'][0]['active'])

    def test_settings_fragments_invalid_and_duplicate_keys_are_excluded(self):
        self.write('.config/clash/settings.json')
        self.write('.config/clash/fragment.json', {'proxies': CONFIG['proxies']})
        self.write('.config/clash/config.json', {'rules': ['MATCH,DIRECT']})
        path = self.write('.config/clash/duplicate.yaml')
        path.write_text('rules: [MATCH,DIRECT]\nrules: [MATCH,DIRECT]\n')
        self.assertEqual(self.discover()['candidates'], [])

    def test_provider_profile_without_inline_nodes_is_supported(self):
        self.write('.config/mihomo/config.yaml', {
            'proxy-providers': {'provider': {'type': 'file', 'path': './nodes.yaml'}},
            'proxy-groups': [{'name': 'chain', 'type': 'select', 'use': ['provider']}],
            'rules': ['MATCH,chain']})
        self.assertEqual(len(self.discover()['candidates']), 1)

    @unittest.skipUnless(hasattr(os, 'symlink'), 'symlinks unavailable')
    def test_symlink_file_and_symlink_ancestor_are_not_followed(self):
        original = self.write('private/config.yaml')
        directory = self.home / '.config/clash'
        directory.mkdir(parents=True)
        (directory / 'link.yaml').symlink_to(original)
        (self.home / '.config/mihomo').symlink_to(original.parent, target_is_directory=True)
        result = self.discover()
        self.assertEqual(result['candidates'], [])
        self.assertIn('UNSAFE_LOCATION_SKIPPED', result['warnings'])

    @unittest.skipUnless(hasattr(os, 'link'), 'hardlinks unavailable')
    def test_hardlink_is_not_read(self):
        original = self.write('private/config.yaml')
        directory = self.home / '.config/clash'
        directory.mkdir(parents=True)
        os.link(original, directory / 'shared.yaml')
        self.assertEqual(self.discover()['candidates'], [])

    def test_windows_reparse_attribute_is_rejected(self):
        path = self.write('.config/clash/config.json')
        original_lstat = Path.lstat

        def lstat(value):
            info = original_lstat(value)
            if value == path:
                return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
            return info

        with patch.object(Path, 'lstat', lstat):
            self.assertEqual(self.discover()['candidates'], [])

    def test_windows_stat_and_fstat_ctime_domains_can_differ(self):
        path = self.write('.config/clash/config.json')
        original_fstat = os.fstat

        def fstat(fd):
            info = original_fstat(fd)
            fields = {key: getattr(info, key) for key in (
                'st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')}
            fields['st_ctime_ns'] += 1000000000
            return SimpleNamespace(**fields)

        with patch.object(os, 'fstat', side_effect=fstat):
            self.assertEqual(discovery._read(path, 4096), path.read_bytes())

    def test_windows_fstat_ctime_change_during_read_is_still_rejected(self):
        path = self.write('.config/clash/config.json')
        original_fstat = os.fstat
        calls = []

        def fstat(fd):
            info = original_fstat(fd)
            fields = {key: getattr(info, key) for key in (
                'st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')}
            calls.append(True)
            fields['st_ctime_ns'] += 1000000000 + len(calls)
            return SimpleNamespace(**fields)

        with patch.object(os, 'fstat', side_effect=fstat), self.assertRaises(discovery._Unsafe):
            discovery._read(path, 4096)

    def test_no_recursion_into_cache_history_or_unknown_subdir(self):
        for relative in ('cache', 'history', 'backup', 'profiles/nested'):
            self.write(f'.config/clash/{relative}/config.yaml')
        self.assertEqual(self.discover()['candidates'], [])

    def test_file_and_entry_limits_are_explicit(self):
        self.write('.config/clash/large.yaml')
        with patch.object(discovery, 'MAX_FILE_BYTES', 16):
            result = self.discover()
        self.assertTrue(result['limited'])
        self.assertEqual(result['candidates'], [])
        self.assertIn('DISCOVERY_LIMIT_REACHED', result['warnings'])
        with patch.object(discovery, 'MAX_ENTRIES', 0):
            self.assertTrue(self.discover()['limited'])

    def test_windows_appdata_selection_and_unc_rejection(self):
        base = self.home / 'AppData/Roaming'
        self.selected('AppData/Roaming/clash-verge')
        result = discovery.discover(self.home, 'win32', {'APPDATA': str(base)})
        self.assertTrue(result['candidates'][0]['active'])
        original_read = discovery._read

        def local_read(path, limit):
            self.assertFalse(str(path).startswith(('//', '\\\\')))
            return original_read(path, limit)

        with patch.object(discovery, '_read', side_effect=local_read):
            result = discovery.discover(self.home, 'win32', {'APPDATA': '//server/share'})
        self.assertEqual(result['candidates'], [])
        self.assertIn('UNSAFE_LOCATION_SKIPPED', result['warnings'])

    def test_missing_yaml_dependency_keeps_json_candidates(self):
        self.selected()
        self.write('.config/clash/config.json')
        original_parse = discovery.config.parse_config

        def parse(data, fmt):
            if fmt == 'yaml':
                raise discovery.config.SetupError('YAML_DEPENDENCY_MISSING')
            return original_parse(data, fmt)

        with patch.object(discovery.config, 'parse_config', side_effect=parse):
            result = self.discover()
        self.assertEqual(len(result['candidates']), 1)
        self.assertIn('DEPENDENCY_REQUIRED', result['warnings'])

    def test_oversized_selection_metadata_is_explicitly_limited(self):
        self.selected()
        with patch.object(discovery, 'MAX_METADATA_BYTES', 8):
            result = self.discover()
        self.assertTrue(result['limited'])
        self.assertFalse(result['candidates'][0]['active'])
        self.assertIn('DISCOVERY_LIMIT_REACHED', result['warnings'])

    def test_limited_scan_cannot_claim_unique_active_profile(self):
        self.selected()
        self.write('.config/clash-verge/profiles/another.yaml')
        with patch.object(discovery, 'MAX_FILES', 1):
            result = self.discover()
        self.assertTrue(result['limited'])
        self.assertFalse(any(item['active'] for item in result['candidates']))

    def test_discovery_does_not_write_network_launch_or_print(self):
        self.selected()
        before = {p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        output = io.StringIO()
        original_open = os.open

        def readonly_open(path, flags, *args, **kwargs):
            self.assertFalse(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
            return original_open(path, flags, *args, **kwargs)

        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output), \
                patch.object(os, 'open', side_effect=readonly_open), \
                patch.object(socket, 'socket', side_effect=AssertionError('network')), \
                patch.object(socket, 'getaddrinfo', side_effect=AssertionError('DNS')), \
                patch.object(subprocess, 'Popen', side_effect=AssertionError('launch')), \
                patch.object(os, 'system', side_effect=AssertionError('shell')):
            result = self.discover()
        self.assertTrue(result['candidates'][0]['active'])
        self.assertEqual(output.getvalue(), '')
        after = {p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
