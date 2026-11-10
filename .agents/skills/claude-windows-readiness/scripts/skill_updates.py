"""Pinned, read-only update comparison for the public Clearpath Skill repository."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import urllib.error
import urllib.request

COMMANDS = ('skill-update-check',)
REPOSITORY = 'LOM2729/claude-environment-check'
API = 'https://api.github.com/repos/' + REPOSITORY
SNAPSHOT_SCHEMA = 'claude-skill-upstream-snapshot/1'
MAX_RESPONSE = 3 * 1024 * 1024
MAX_FILES = 5000
MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
SKIP = frozenset({'.git', '__pycache__', '.DS_Store'})


def register_commands(subparsers):
    p = subparsers.add_parser('skill-update-check', help='Compare installed Skill bytes against a pinned GitHub tree; never install')
    p.add_argument('--skill-root', required=True)
    p.add_argument('--platform', choices=('mac', 'windows'), required=True)
    p.add_argument('--snapshot', help='Previously saved upstream snapshot; offline comparison, not a latest-version claim')
    p.add_argument('--allow-network', action='store_true')
    p.add_argument('--snapshot-output', help='New private pinned upstream snapshot file')
    p.add_argument('--output', required=True, help='New private comparison report')


def _need(condition, code):
    if not condition:
        raise ValueError(code)


def _sha(value):
    return type(value) is str and re.fullmatch(r'[0-9a-f]{40}', value) is not None


def _path(value):
    _need(type(value) is str and 0 < len(value) <= 1024, 'SKILL_UPDATE_PATH_INVALID')
    _need(not any(ord(x) < 32 or ord(x) == 127 for x in value) and '\\' not in value and ':' not in value,
          'SKILL_UPDATE_PATH_INVALID')
    parts = value.split('/')
    _need(not value.startswith('/') and all(x not in ('', '.', '..') for x in parts), 'SKILL_UPDATE_PATH_INVALID')
    _need(str(PurePosixPath(value)) == value, 'SKILL_UPDATE_PATH_INVALID')
    return value


def _json(raw):
    _need(type(raw) is bytes and len(raw) <= MAX_RESPONSE, 'SKILL_UPDATE_RESPONSE_INVALID')
    def pairs(values):
        result = {}
        for key, value in values:
            _need(key not in result, 'SKILL_UPDATE_RESPONSE_INVALID')
            result[key] = value
        return result
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('SKILL_UPDATE_RESPONSE_INVALID')))
    except (UnicodeError, TypeError, json.JSONDecodeError, RecursionError):
        raise ValueError('SKILL_UPDATE_RESPONSE_INVALID') from None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise ValueError('SKILL_UPDATE_REDIRECT_REJECTED')


def fetch_bytes(url):
    """Only two fixed GitHub API routes; normal certificate verification stays on."""
    allowed = url == API + '/commits/main' or re.fullmatch(re.escape(API) + r'/git/trees/[0-9a-f]{40}\?recursive=1', url)
    _need(allowed, 'SKILL_UPDATE_URL_REJECTED')
    request = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'Claude-Environment-Check'})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=8) as response:
            _need(response.geturl() == url and response.status == 200, 'SKILL_UPDATE_RESPONSE_INVALID')
            length = response.headers.get('Content-Length')
            _need(length is None or (length.isdigit() and int(length) <= MAX_RESPONSE), 'SKILL_UPDATE_RESPONSE_TOO_LARGE')
            raw = response.read(MAX_RESPONSE + 1)
            _need(len(raw) <= MAX_RESPONSE, 'SKILL_UPDATE_RESPONSE_TOO_LARGE')
            return raw
    except (urllib.error.URLError, OSError, TimeoutError):
        raise ValueError('SKILL_UPDATE_UNAVAILABLE') from None


def validate_snapshot(value):
    _need(type(value) is dict and set(value) == {'schema', 'repository', 'commit', 'tree_sha', 'tree'},
          'SKILL_UPDATE_SNAPSHOT_INVALID')
    _need(value['schema'] == SNAPSHOT_SCHEMA and value['repository'] == REPOSITORY
          and _sha(value['commit']) and _sha(value['tree_sha']), 'SKILL_UPDATE_SNAPSHOT_INVALID')
    tree = value['tree']
    _need(type(tree) is dict and tree.get('sha') == value['tree_sha'] and tree.get('truncated') is False,
          'SKILL_UPDATE_TREE_INCOMPLETE')
    entries = tree.get('tree')
    _need(type(entries) is list and 0 < len(entries) <= 10000, 'SKILL_UPDATE_TREE_INVALID')
    paths = set()
    for item in entries:
        _need(type(item) is dict, 'SKILL_UPDATE_TREE_INVALID')
        name = _path(item.get('path'))
        _need(name not in paths and _sha(item.get('sha')), 'SKILL_UPDATE_TREE_INVALID')
        paths.add(name)
        _need((item.get('type'), item.get('mode')) in {
            ('blob', '100644'), ('blob', '100755'), ('blob', '120000'),
            ('tree', '040000'), ('commit', '160000')}, 'SKILL_UPDATE_TREE_INVALID')
    return value


def upstream_snapshot(fetcher=None):
    """Pin main's commit/tree first; a moving branch cannot mix two snapshots."""
    fetcher = fetcher or fetch_bytes
    commit = _json(fetcher(API + '/commits/main'))
    _need(type(commit) is dict and _sha(commit.get('sha')), 'SKILL_UPDATE_COMMIT_INVALID')
    metadata = commit.get('commit')
    _need(type(metadata) is dict and type(metadata.get('tree')) is dict and _sha(metadata['tree'].get('sha')),
          'SKILL_UPDATE_COMMIT_INVALID')
    tree_sha = metadata['tree']['sha']
    tree = _json(fetcher(API + '/git/trees/' + tree_sha + '?recursive=1'))
    return validate_snapshot({'schema': SNAPSHOT_SCHEMA, 'repository': REPOSITORY,
        'commit': commit['sha'], 'tree_sha': tree_sha, 'tree': tree})


def _regular_root(root):
    root = Path(root).absolute()
    _need(root.is_absolute(), 'SKILL_UPDATE_ROOT_INVALID')
    for p in [root, *root.parents]:
        info = p.lstat()
        _need(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
              'SKILL_UPDATE_LINK_REJECTED')
    _need(root.is_dir(), 'SKILL_UPDATE_ROOT_INVALID')
    return root


def local_inventory(c, root, platform):
    root = _regular_root(root)
    expected_name = 'claude-' + platform + '-readiness'
    header = c.read_bytes(root / 'SKILL.md', 65536).decode('utf-8')
    _need(re.search(r'(?m)^name:\s*' + re.escape(expected_name) + r'\s*$', header) is not None,
          'SKILL_UPDATE_ROOT_IDENTITY_MISMATCH')
    entries, folded, total = {}, set(), 0
    for directory, folders, files in os.walk(root, followlinks=False):
        for name in folders + files:
            path = Path(directory) / name
            info = path.lstat()
            _need(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                  'SKILL_UPDATE_LINK_REJECTED')
        folders[:] = sorted(n for n in folders if n not in SKIP)
        for name in sorted(files):
            if name in SKIP or name.endswith(('.pyc', '.pyo')):
                continue
            path = Path(directory) / name
            rel = _path(path.relative_to(root).as_posix())
            _need(len(entries) < MAX_FILES and rel.casefold() not in folded, 'SKILL_UPDATE_LOCAL_LIMIT_OR_COLLISION')
            info = path.lstat()
            _need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= MAX_FILE,
                  'SKILL_UPDATE_REGULAR_FILE_REQUIRED')
            total += info.st_size
            _need(total <= MAX_TOTAL, 'SKILL_UPDATE_LOCAL_BUDGET_EXCEEDED')
            data = c.read_bytes(path, MAX_FILE)
            entries[rel] = hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()
            folded.add(rel.casefold())
    return entries


def compare(c, root, platform, snapshot, source):
    value = validate_snapshot(snapshot)
    _need(platform in ('mac', 'windows'), 'SKILL_UPDATE_PLATFORM_INVALID')
    prefix = '.agents/skills/claude-' + platform + '-readiness/'
    upstream, folded = {}, set()
    for item in value['tree']['tree']:
        if not item['path'].startswith(prefix) or item['type'] == 'tree':
            continue
        _need(item['type'] == 'blob' and item['mode'] in ('100644', '100755'), 'SKILL_UPDATE_UPSTREAM_LINK_REJECTED')
        name = item['path'][len(prefix):]
        _need(name.casefold() not in folded, 'SKILL_UPDATE_UPSTREAM_PATH_COLLISION')
        folded.add(name.casefold())
        upstream[name] = item['sha']
    _need('SKILL.md' in upstream, 'SKILL_UPDATE_UPSTREAM_SKILL_MISSING')
    local = local_inventory(c, root, platform)
    changed = sorted(n for n in upstream.keys() & local.keys() if upstream[n] != local[n])
    added, extra = sorted(upstream.keys() - local.keys()), sorted(local.keys() - upstream.keys())
    return {'schema': 'claude-skill-update-comparison/1', 'checked_at': c.now(),
        'repository': REPOSITORY, 'platform': platform, 'upstream_commit': value['commit'],
        'source': source, 'latest_version_checked': source == 'github_pinned_main',
        'status': 'update_available' if changed or added else 'local_customizations_only' if extra else 'upstream_matches',
        'changed': changed, 'upstream_only': added, 'local_only': extra,
        'installed_files_modified': False, 'release_package_identity_verified': False,
        'local_only_action': 'preserve_and_review_not_automatic_deletion', 'required_checks_completed': True}


def run(c, args):
    try:
        if args.snapshot:
            c.require(not args.snapshot_output, 'SKILL_UPDATE_SNAPSHOT_COPY_NOT_NEEDED')
            snapshot = validate_snapshot(_json(c.read_bytes(args.snapshot, MAX_RESPONSE)))
            source, requests = 'offline_supplied_snapshot', 0
        else:
            c.require(args.allow_network, 'EXPLICIT_NETWORK_OPT_IN_REQUIRED')
            snapshot = upstream_snapshot()
            source, requests = 'github_pinned_main', 2
        result = compare(c, args.skill_root, args.platform, snapshot, source)
        result['network_requests'] = requests
        if args.snapshot_output:
            c.write_new(args.snapshot_output, c.encode(snapshot))
        c.write_new(args.output, c.encode(result))
        return {k: result[k] for k in ('schema', 'status', 'source', 'latest_version_checked', 'upstream_commit',
            'installed_files_modified', 'release_package_identity_verified', 'required_checks_completed', 'network_requests')} | {
            'changed_count': len(result['changed']), 'upstream_only_count': len(result['upstream_only']),
            'local_only_count': len(result['local_only'])}
    except ValueError as exc:
        code = str(exc)
        raise c.SetupError(code if code.startswith('SKILL_UPDATE_') else 'SKILL_UPDATE_FAILED') from None
    except (OSError, UnicodeError, RecursionError):
        raise c.SetupError('SKILL_UPDATE_FAILED') from None
