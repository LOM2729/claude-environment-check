"""Update comparisons use synthetic Skill files and injected GitHub responses only."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import claude_setup as c
import skill_updates as updates


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def snapshot(entries):
    prefix = '.agents/skills/claude-mac-readiness/'
    return {'schema': updates.SNAPSHOT_SCHEMA, 'repository': updates.REPOSITORY,
        'commit': 'b' * 40, 'tree_sha': 'a' * 40,
        'tree': {'sha': 'a' * 40, 'truncated': False, 'tree': [
            {'path': prefix + name, 'sha': blob(data), 'type': 'blob', 'mode': '100644'}
            for name, data in entries.items()]}}


class SkillUpdates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-skill-update-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'claude-mac-readiness'
        self.root.mkdir()
        self.skill = b'---\nname: claude-mac-readiness\ndescription: synthetic\n---\n'
        (self.root / 'SKILL.md').write_bytes(self.skill)

    def test_diff_distinguishes_local_changes_missing_upstream_and_custom_files_without_writes(self):
        (self.root / 'changed.py').write_bytes(b'local-custom-change\n')
        (self.root / 'custom.txt').write_bytes(b'preserve this\n')
        value = snapshot({'SKILL.md': self.skill, 'changed.py': b'upstream\n', 'new.py': b'new\n'})
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        result = updates.compare(c, self.root, 'mac', value, 'offline_supplied_snapshot')
        self.assertEqual(result['changed'], ['changed.py'])
        self.assertEqual(result['upstream_only'], ['new.py'])
        self.assertEqual(result['local_only'], ['custom.txt'])
        self.assertFalse(result['latest_version_checked'])
        self.assertFalse(result['installed_files_modified'])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_local_only_is_preserved_and_not_called_update_available(self):
        (self.root / 'custom.txt').write_bytes(b'custom')
        result = updates.compare(c, self.root, 'mac', snapshot({'SKILL.md': self.skill}), 'github_pinned_main')
        self.assertEqual(result['status'], 'local_customizations_only')
        self.assertEqual(result['local_only_action'], 'preserve_and_review_not_automatic_deletion')

    def test_online_pins_commit_then_requests_exact_tree(self):
        value = snapshot({'SKILL.md': self.skill})
        called = []
        def fetch(url):
            called.append(url)
            if url.endswith('/commits/main'):
                return json.dumps({'sha': 'b' * 40, 'commit': {'tree': {'sha': 'a' * 40}}}).encode()
            self.assertEqual(url, updates.API + '/git/trees/' + 'a' * 40 + '?recursive=1')
            return json.dumps(value['tree']).encode()
        self.assertEqual(updates.upstream_snapshot(fetch), value)
        self.assertEqual(len(called), 2)
        self.assertNotIn('/git/trees/main', called[1])

    def test_truncated_foreign_duplicate_and_unsafe_tree_entries_fail(self):
        original = snapshot({'SKILL.md': self.skill})
        for mutate in [lambda x: x.update(repository='attacker/repo'),
                       lambda x: x['tree'].update(truncated=True),
                       lambda x: x['tree'].update(sha='c' * 40),
                       lambda x: x['tree']['tree'].append(copy.deepcopy(x['tree']['tree'][0]))]:
            value = copy.deepcopy(original); mutate(value)
            with self.assertRaises(ValueError):
                updates.validate_snapshot(value)
        for path in ('../SKILL.md', '/absolute', 'x\\y', 'C:drive', 'x//y', 'x/./y'):
            value = copy.deepcopy(original);value['tree']['tree'][0]['path'] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                updates.validate_snapshot(value)
        value = copy.deepcopy(original);value['tree']['tree'][0]['mode'] = '120000'
        with self.assertRaisesRegex(ValueError, 'UPSTREAM_LINK_REJECTED'):
            updates.compare(c, self.root, 'mac', value, 'offline_supplied_snapshot')

    def test_local_links_special_files_and_case_collisions_are_not_hashed(self):
        value = snapshot({'SKILL.md': self.skill})
        outside = self.root.parent / 'outside';outside.write_bytes(b'secret')
        try:
            (self.root / 'linked').symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest('symlink unavailable for current test user')
        with self.assertRaisesRegex(ValueError, 'LINK_REJECTED'):
            updates.compare(c, self.root, 'mac', value, 'offline_supplied_snapshot')
        (self.root / 'linked').unlink()
        (self.root / 'A').write_bytes(b'a')
        (self.root / 'a').write_bytes(b'b')
        if len([p for p in self.root.iterdir() if p.name.lower() == 'a']) == 2:
            with self.assertRaisesRegex(ValueError, 'COLLISION'):
                updates.compare(c, self.root, 'mac', value, 'offline_supplied_snapshot')

    def test_cli_offline_and_failed_online_never_claim_latest_or_install(self):
        parser = argparse.ArgumentParser();updates.register_commands(parser.add_subparsers(dest='command'))
        saved = self.root.parent / 'snapshot.json';saved.write_bytes(c.encode(snapshot({'SKILL.md': self.skill})))
        args = parser.parse_args(['skill-update-check', '--platform', 'mac', '--skill-root', str(self.root),
            '--snapshot', str(saved), '--output', str(self.root.parent / 'result.json')])
        with patch.object(updates, 'upstream_snapshot', side_effect=AssertionError('no network permitted')):
            result = updates.run(c, args)
        self.assertFalse(result['latest_version_checked'])
        self.assertEqual(result['network_requests'], 0)
        args.snapshot = None; args.output = str(self.root.parent / 'failed.json')
        with self.assertRaisesRegex(c.SetupError, 'OPT_IN'):
            updates.run(c, args)
        args.allow_network = True
        with patch.object(updates, 'upstream_snapshot', side_effect=ValueError('SKILL_UPDATE_UNAVAILABLE')):
            with self.assertRaisesRegex(c.SetupError, 'SKILL_UPDATE_UNAVAILABLE'):
                updates.run(c, args)
        self.assertFalse(Path(args.output).exists())

    def test_default_fetcher_rejects_redirects_and_non_fixed_hosts_without_requests(self):
        with self.assertRaisesRegex(ValueError, 'URL_REJECTED'):
            updates.fetch_bytes('https://example.com/anything')
        with self.assertRaisesRegex(ValueError, 'REDIRECT_REJECTED'):
            updates._NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com/')
        with self.assertRaisesRegex(ValueError, 'RESPONSE_INVALID'):
            updates._json(b'{"sha":"a","sha":"b"}')


if __name__ == '__main__':
    unittest.main()
