"""GitHub data-only updates; no downloaded code, extraction, or client writes."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import threading
import time
import urllib.request
from urllib.parse import urlsplit
import uuid

import ai_routing as ai
import claude_setup as c
import community_routing as community
import config_recovery as recovery
import domestic_policy as domestic
import rule_data

REPO = 'LOM2729/claude-environment-check'
TAG = 'lite-rules'
ASSET = 'Clash-Lite-Rules.json.gz'
API = f'https://api.github.com/repos/{REPO}/releases/tags/{TAG}'
DOWNLOAD = f'https://github.com/{REPO}/releases/download/{TAG}/{ASSET}'
ABI = 'domestic-v4-hotdata/1'
MAX_PACK = 4 * 1024 * 1024
MAX_JSON = 8 * 1024 * 1024
INTERVAL = 30 * 60
REQUIRED_AI = frozenset(('claude.ai', 'claude.com', 'anthropic.com', 'openai.com', 'chatgpt.com'))


def decode_pack(raw):
    c.require(type(raw) is bytes and len(raw) <= MAX_PACK, 'RULE_PACK_TOO_LARGE')
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            data = stream.read(MAX_JSON + 1)
        c.require(len(data) <= MAX_JSON, 'RULE_PACK_TOO_LARGE')
        doc = c.load_json(data)
        c.require(isinstance(doc, dict) and set(doc) == {'schema', 'abi', 'revision', 'files', 'sha256'},
                  'RULE_PACK_SCHEMA_INVALID')
        c.require(doc['schema'] == 'clash-lite-rules/1' and doc['abi'] == ABI, 'RULE_PACK_APP_UPGRADE_REQUIRED')
        revision = doc['revision']
        c.require(type(revision) is int and 1 <= revision < 10**15, 'RULE_PACK_REVISION_INVALID')
        c.require(isinstance(doc['files'], dict) and set(doc['files']) == rule_data.FILES
                  and isinstance(doc['sha256'], dict) and set(doc['sha256']) == rule_data.FILES,
                  'RULE_PACK_FILES_INVALID')
        files = {}
        for name, value in doc['files'].items():
            c.require(isinstance(value, str), 'RULE_PACK_FILES_INVALID')
            content = value.encode('utf-8')
            c.require(hashlib.sha256(content).hexdigest() == doc['sha256'][name], 'RULE_PACK_HASH_INVALID')
            files[name] = content
        c.require(len(files['ai_domains.json']) <= 32768
                  and len(files['community_snapshot.json']) <= 256 * 1024
                  and len(files['domestic_sources.json']) <= 256 * 1024, 'RULE_PACK_TOO_LARGE')
        selected = rule_data.Snapshot(revision, files)
        with rule_data.using(selected):
            catalog = ai.catalog(c)
            c.require(REQUIRED_AI <= set(catalog['suffixes']), 'RULE_PACK_CORE_TARGET_REMOVED')
            sources = c.load_json(files['domestic_sources.json'])
            providers = domestic.snapshot()
            for key, name in ((domestic.CN, 'domestic_cn.list'), (domestic.VIDEO, 'domestic_video.list')):
                entries = providers[key]['payload']
                c.require(0 < len(entries) <= 250000 and sources['files'][name]['entries'] == len(entries),
                          'RULE_PACK_DOMAIN_COUNT_INVALID')
                c.require(not any(s.removeprefix('+.') in {'com', 'net', 'org', 'io', 'ai', 'app', 'dev', '*'}
                                  for s in entries), 'RULE_PACK_BROAD_DIRECT_FORBIDDEN')
            # Validate all includes, hashes, domain syntax and IPv4 networks
            # using the same parser that will generate the candidate rules.
            matches = community.matches()
            c.require(0 < len(matches) <= 5000, 'RULE_PACK_COMMUNITY_INVALID')
        return selected
    except c.SetupError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, OSError, EOFError, RecursionError):
        raise c.SetupError('RULE_PACK_INVALID') from None


def build_pack(source, revision):
    files = {name: c.read_bytes(Path(source) / name) for name in rule_data.FILES}
    doc = {'schema': 'clash-lite-rules/1', 'abi': ABI, 'revision': revision,
           'files': {name: data.decode('utf-8') for name, data in files.items()},
           'sha256': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    raw = gzip.compress(c.encode(doc), mtime=0)
    decode_pack(raw)
    return raw


class _Redirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 3
    def redirect_request(self, request, response, code, message, headers, newurl):
        parts = urlsplit(newurl)
        c.require(request.full_url != API and parts.scheme == 'https'
                  and parts.hostname in ('release-assets.githubusercontent.com', 'objects.githubusercontent.com')
                  and parts.port in (None, 443) and parts.username is None and parts.password is None,
                  'RULE_UPDATE_REDIRECT_REJECTED')
        return super().redirect_request(request, response, code, message, headers, newurl)


def _get(url, limit, timeout=5):
    c.require(url in (API, DOWNLOAD), 'RULE_UPDATE_URL_REJECTED')
    request = urllib.request.Request(url, headers={
        'Accept': 'application/vnd.github+json' if url == API else 'application/octet-stream',
        'User-Agent': 'Clash-Config-Lite-rules/1', 'X-GitHub-Api-Version': '2022-11-28'})
    # Use the current system/environment proxy. Never create a direct bypass.
    with urllib.request.build_opener(_Redirects()).open(request, timeout=timeout) as response:
        data = response.read(limit + 1)
    c.require(len(data) <= limit, 'RULE_UPDATE_RESPONSE_TOO_LARGE')
    return data


def release_asset(raw):
    doc = c.load_json(raw)
    c.require(isinstance(doc, dict) and doc.get('tag_name') == TAG and doc.get('draft') is False
              and doc.get('prerelease') is False and doc.get('published_at'), 'RULE_UPDATE_CHANNEL_INVALID')
    assets = doc.get('assets')
    c.require(isinstance(assets, list) and len(assets) <= 20, 'RULE_UPDATE_CHANNEL_INVALID')
    hits = [a for a in assets if isinstance(a, dict) and a.get('name') == ASSET]
    c.require(len(hits) == 1, 'RULE_UPDATE_ASSET_MISSING')
    asset = hits[0]
    digest = asset.get('digest')
    c.require(asset.get('state') == 'uploaded' and asset.get('browser_download_url') == DOWNLOAD
              and isinstance(digest, str) and re.fullmatch(r'sha256:[0-9a-f]{64}', digest)
              and type(asset.get('size')) is int and 0 < asset['size'] <= MAX_PACK,
              'RULE_UPDATE_ASSET_INVALID')
    return asset['size'], digest[7:]


class Client:
    def __init__(self, root, fetch=None):
        self.root = recovery._private_dir(c, Path(root), create=not Path(root).exists())
        self.fetch = _get if fetch is None else fetch
        self._snapshot = None
        self._digest = None
        self.last_check = 0
        self.lock = threading.Lock()
        self._load_cache()

    def current(self):
        # An immutable object reference is published only after validation.
        # Reading it must never wait for the updater's network request.
        return self._snapshot

    def _load_cache(self):
        # Immutable complete files only. Ignore partial writes and fall back to
        # the previous valid version if a cached file is corrupted.
        files = sorted(self.root.glob('rules-*.json.gz'), reverse=True)[:32]
        for path in files:
            match = re.fullmatch(r'rules-(\d{15})-([0-9a-f]{64})\.json\.gz', path.name)
            if not match:
                continue
            try:
                raw = c.read_bytes(path, MAX_PACK)
                c.require(hashlib.sha256(raw).hexdigest() == match[2], 'RULE_PACK_HASH_INVALID')
                selected = decode_pack(raw)
                c.require(selected.revision == int(match[1]), 'RULE_PACK_REVISION_INVALID')
            except (c.SetupError, OSError):
                continue
            self._snapshot, self._digest = selected, match[2]
            break

    def refresh(self, force=False):
        # Only this updater writes its data cache; GUI/export snapshots are
        # immutable and never change halfway through a generation operation.
        if not self.lock.acquire(blocking=False):
            return {'status': 'checking'}
        try:
            now = time.monotonic()
            if not force and self.last_check and now - self.last_check < INTERVAL:
                return {'status': 'cached', 'revision': self._snapshot.revision if self._snapshot else None}
            self.last_check = now
            try:
                size, digest = release_asset(self.fetch(API, 256 * 1024))
                if digest == self._digest:
                    return {'status': 'current', 'revision': self._snapshot.revision}
                raw = self.fetch(DOWNLOAD, MAX_PACK)
                c.require(len(raw) == size and hashlib.sha256(raw).hexdigest() == digest, 'RULE_PACK_HASH_INVALID')
                selected = decode_pack(raw)
                if self._snapshot:
                    c.require(selected.revision > self._snapshot.revision, 'RULE_UPDATE_ROLLBACK_REJECTED')
                final = self.root / f'rules-{selected.revision:015d}-{digest}.json.gz'
                stage = self.root / ('.part-' + uuid.uuid4().hex)
                c.write_new(stage, raw)
                try:
                    c.require(c.read_bytes(stage, MAX_PACK) == raw, 'RULE_UPDATE_READBACK_FAILED')
                    try:
                        os.link(stage, final)
                    except FileExistsError:
                        c.require(c.read_bytes(final, MAX_PACK) == raw, 'RULE_UPDATE_READBACK_FAILED')
                finally:
                    stage.unlink(missing_ok=True)
                c.require(c.read_bytes(final, MAX_PACK) == raw, 'RULE_UPDATE_READBACK_FAILED')
                self._snapshot, self._digest = selected, digest
                return {'status': 'updated', 'revision': selected.revision}
            except Exception as exc:
                code = str(exc) if isinstance(exc, c.SetupError) and re.fullmatch(r'[A-Z0-9_]{1,90}', str(exc)) else 'RULE_UPDATE_UNAVAILABLE'
                return {'status': 'kept_previous', 'revision': self._snapshot.revision if self._snapshot else None,
                        'code': code}
        finally:
            self.lock.release()
