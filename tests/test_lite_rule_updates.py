"""Data-update trust boundaries, rollback, isolation and actual YAML behavior."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lite import rule_updates as update
from lite import config_engine
from lite.service import Service
import ai_routing as ai
import claude_setup as c
import community_routing as community
import rule_data
import unified_policy as unified


def changed_pack(revision=101, host='fresh-ai.example.test'):
    raw = update.build_pack(ROOT / 'src', revision)
    doc = json.loads(gzip.decompress(raw))
    catalog = json.loads(doc['files']['ai_domains.json'])
    catalog['suffixes'].append(host)
    doc['files']['ai_domains.json'] = json.dumps(catalog)
    community_data = json.loads(doc['files']['community_snapshot.json'])
    source = community_data['files']['anthropic']
    source['text'] += '\nfull:fresh-community.example.test\n'
    source['sha256'] = hashlib.sha256(source['text'].encode()).hexdigest()
    doc['files']['community_snapshot.json'] = json.dumps(community_data)
    doc['files']['domestic_cn.list'] = doc['files']['domestic_cn.list'].rstrip('\n') + '\n+.fresh-domestic.example.test\n'
    meta = json.loads(doc['files']['domestic_sources.json'])
    meta['files']['domestic_cn.list']['entries'] += 1
    meta['files']['domestic_cn.list']['sha256'] = hashlib.sha256(doc['files']['domestic_cn.list'].encode()).hexdigest()
    doc['files']['domestic_sources.json'] = json.dumps(meta)
    return encode(doc)


def encode(doc):
    doc['sha256'] = {name: hashlib.sha256(value.encode()).hexdigest() for name,value in doc['files'].items()}
    return gzip.compress(c.encode(doc), mtime=0)


def feed(raw):
    return c.encode({'tag_name': update.TAG, 'draft': False, 'prerelease': False,
        'published_at': '2026-11-02T00:00:00Z', 'assets': [
            {'name': update.ASSET, 'state': 'uploaded', 'size': len(raw),
             'digest': 'sha256:' + hashlib.sha256(raw).hexdigest(), 'browser_download_url': update.DOWNLOAD}]})


class RuleUpdates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = changed_pack()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.requests = []
        self.remote = self.raw

    def tearDown(self):
        self.tmp.cleanup()

    def fetch(self, url, limit):
        self.requests.append(url)
        return feed(self.remote) if url == update.API else self.remote

    def test_new_data_changes_actual_yaml_and_does_not_leak_to_legacy_context(self):
        snapshot = update.decode_pack(self.raw)
        self.assertNotIn('fresh-ai.example.test', ai.catalog(c)['suffixes'])
        self.assertEqual(unified.classify_direct_rule('DOMAIN,fresh-domestic.example.test,DIRECT')['decision'], 'pending')
        with rule_data.using(snapshot):
            self.assertIn('fresh-ai.example.test', ai.catalog(c)['suffixes'])
            self.assertIn(('DOMAIN','fresh-community.example.test'), community.matches())
            self.assertEqual(unified.classify_direct_rule('DOMAIN,fresh-domestic.example.test,DIRECT')['decision'], 'keep')
        self.assertNotIn('fresh-ai.example.test', ai.catalog(c)['suffixes'])
        source = self.root / 'source.json'
        source.write_bytes(c.encode({'proxies': [{'name':'Exit','type':'socks5','server':'192.0.2.1','port':1080}],
                                     'rules':['DOMAIN,fresh-domestic.example.test,DIRECT','MATCH,Exit']}))
        service = Service(self.root / 'private')
        active = [snapshot]
        service.rule_client = type('Rules', (), {'current': lambda _:active[0]})()
        service.load(source, probe_runtime=False)
        other = update.decode_pack(changed_pack(102, 'other-ai.example.test'))
        original = config_engine.prepare_candidate
        def prepare(*args, **kwargs):
            active[0] = other
            self.assertIs(rule_data.current(), snapshot)
            return original(*args, **kwargs)
        with patch.object(config_engine, 'prepare_candidate', side_effect=prepare):
            result = service.prepare('Exit', preserve=False)
        obj = c.parse_config(Path(result['candidate_path']).read_bytes(), 'yaml')
        self.assertIn('DOMAIN-SUFFIX,fresh-ai.example.test,AI-ONLY', obj['rules'])
        self.assertNotIn('DOMAIN-SUFFIX,other-ai.example.test,AI-ONLY', obj['rules'])
        self.assertEqual(result['private_summary']['rules_revision'], 101)
        receipt = service.export(self.root/'new.yaml')
        self.assertEqual(receipt['rules_revision'],101)
        self.assertFalse(receipt['proxy_or_system_changes'])

    def test_download_cache_readback_and_offline_restart(self):
        client = update.Client(self.root/'cache',self.fetch)
        self.assertEqual(client.refresh()['status'],'updated')
        self.assertEqual(self.requests,[update.API,update.DOWNLOAD])
        self.assertEqual(client.current().revision,101)
        self.assertEqual(client.refresh()['status'],'cached')
        cached = update.Client(self.root/'cache',lambda *_:(_ for _ in ()).throw(OSError()))
        self.assertEqual(cached.current().revision,101)
        self.assertEqual(cached.refresh(True)['status'],'kept_previous')
        self.assertEqual(cached.current().revision,101)

    def test_bad_digest_and_replayed_versions_keep_valid_snapshot(self):
        client = update.Client(self.root/'cache',self.fetch)
        self.assertEqual(client.refresh()['status'],'updated')
        self.remote = changed_pack(100)
        self.assertEqual(client.refresh(True)['code'],'RULE_UPDATE_ROLLBACK_REJECTED')
        self.remote = changed_pack(101,'different.example.test')
        self.assertEqual(client.refresh(True)['code'],'RULE_UPDATE_ROLLBACK_REJECTED')
        client.fetch = lambda url,limit:feed(self.remote) if url==update.API else b'tampered'
        self.assertEqual(client.refresh(True)['code'],'RULE_PACK_HASH_INVALID')
        self.assertEqual(client.current().revision,101)

    def test_corrupt_latest_cache_falls_back_to_previous(self):
        client = update.Client(self.root/'cache',self.fetch)
        client.refresh()
        self.remote = changed_pack(102)
        self.assertEqual(client.refresh(True)['status'],'updated')
        newest=sorted((self.root/'cache').glob('rules-*'))[-1]
        newest.write_bytes(b'corrupt')
        self.assertEqual(update.Client(self.root/'cache').current().revision,101)

    def test_current_snapshot_does_not_wait_for_network(self):
        client=update.Client(self.root/'cache',self.fetch);client.refresh()
        started,finish=threading.Event(),threading.Event()
        def fetch(*_):
            started.set();finish.wait(3);raise OSError()
        client.fetch=fetch
        thread=threading.Thread(target=lambda:client.refresh(True));thread.start()
        try:
            self.assertTrue(started.wait(1))
            before = time.monotonic()
            self.assertEqual(client.current().revision,101)
            self.assertLess(time.monotonic()-before, 1)
        finally:
            finish.set();thread.join(3)

    def test_snapshot_is_immutable_and_thread_context_isolated(self):
        selected=update.decode_pack(self.raw)
        with self.assertRaises((AttributeError,TypeError)):
            selected.revision=0
        with self.assertRaises(TypeError):selected.files['ai_domains.json']=b'{}'
        observed=[]
        with rule_data.using(selected):
            thread=threading.Thread(target=lambda:observed.append(rule_data.current()))
            thread.start();thread.join()
            self.assertIs(rule_data.current(),selected)
        self.assertEqual(observed,[None]);self.assertIsNone(rule_data.current())

    def test_extra_files_incompatible_schema_and_missing_core_are_rejected(self):
        doc=json.loads(gzip.decompress(self.raw))
        variants=[]
        bad=copy.deepcopy(doc);bad['files']['script.py']='print(1)';variants.append(bad)
        bad=copy.deepcopy(doc);bad['abi']='future/99';variants.append(bad)
        bad=copy.deepcopy(doc);catalog=json.loads(bad['files']['ai_domains.json']);catalog['suffixes'].remove('claude.ai')
        bad['files']['ai_domains.json']=json.dumps(catalog);variants.append(bad)
        bad=copy.deepcopy(doc);bad['files']['domestic_video.list']='+.com\n';variants.append(bad)
        for value in variants:
            with self.subTest(abi=value['abi']),self.assertRaises(c.SetupError):update.decode_pack(encode(value))

    def test_channel_url_digest_and_status_are_validated(self):
        doc=json.loads(feed(self.raw))
        for key,value in (('draft',True),('prerelease',True),('tag_name','other')):
            bad=copy.deepcopy(doc);bad[key]=value
            with self.assertRaises(c.SetupError):update.release_asset(c.encode(bad))
        for key,value in (('digest',None),('browser_download_url','https://example.test/evil'),('size',True)):
            bad=copy.deepcopy(doc);bad['assets'][0][key]=value
            with self.assertRaises(c.SetupError):update.release_asset(c.encode(bad))
        bad=copy.deepcopy(doc);bad['assets']*=2
        with self.assertRaises(c.SetupError):update.release_asset(c.encode(bad))
        for url in ('http://release-assets.githubusercontent.com/a','https://example.test/a','https://user@release-assets.githubusercontent.com/a'):
            with self.assertRaises(c.SetupError):
                update._Redirects().redirect_request(Request(update.DOWNLOAD),None,302,'',{},url)

    def test_oversized_decompression_is_bounded(self):
        raw=gzip.compress(b'x'*(update.MAX_JSON+1))
        with self.assertRaisesRegex(c.SetupError,'RULE_PACK_TOO_LARGE'):update.decode_pack(raw)

    def test_excessive_community_include_expansion_is_bounded(self):
        data = {'files': {'a': {'text': 'include:b\n'*200}, 'b': {'text': 'full:example.test\n'*200}}}
        with self.assertRaisesRegex(ValueError, 'expansion limit'):
            community.expand(data, 'a')


if __name__=='__main__':unittest.main()
