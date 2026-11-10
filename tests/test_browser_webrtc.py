"""ICE result contracts and HTTP protocol boundaries; no real browser/STUN traffic."""
import argparse
import copy
import datetime as dt
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import claude_setup as c
import browser_webrtc as web


def plan():
    return {'schema': web.PLAN_SCHEMA, 'created_at': c.now(), 'target_alias': 'device', 'profile_alias': 'profile',
        'platform': 'macos', 'config_sha256': 'a' * 64, 'stun_urls': ['stun:stun.example.com:3478'],
        'measurement_seconds': 12}


def observation(p, session_id='a' * 32):
    return {'schema': web.RESULT_SCHEMA, 'plan_sha256': web.plan_digest(p), 'session_id': session_id,
        'started_at': p['created_at'], 'ended_at': p['created_at'], 'finish': 'completed',
        'counts': {'host': 1, 'mdns': 1, 'srflx_ipv4': 1, 'srflx_ipv6': 0, 'relay': 0, 'prflx': 0, 'unknown': 0},
        'reference_provided': True, 'reference_matches': True, 'mismatch_observed': False,
        'ipv6_observed': False, 'gathering_complete': True, 'truncated': False, 'error_codes': []}


class FakeSocket:
    def __init__(self, request):
        self.incoming = io.BytesIO(request)
        self.outgoing = io.BytesIO()
    def makefile(self, mode, *args):
        return self.incoming
    def sendall(self, data):
        self.outgoing.write(data)
    def settimeout(self, value):
        pass


def request(session, method='GET', suffix='', body=b'', host='127.0.0.1:19485', origin=None, csrf=None, extra=None):
    headers = [('Host', host)]
    if method == 'POST':
        headers += [('Content-Type', 'application/json'), ('Content-Length', str(len(body))),
                    ('Origin', origin or 'http://127.0.0.1:19485'), ('X-CSRF-Token', csrf or session.csrf)]
    headers += extra or []
    raw = (method + ' /' + session.token + '/' + suffix + ' HTTP/1.1\r\n' +
           ''.join(k + ': ' + v + '\r\n' for k, v in headers) + '\r\n').encode() + body
    sock = FakeSocket(raw)
    web.handler_for(session)(sock, ('127.0.0.1', 12345), SimpleNamespace(server_address=('127.0.0.1', 19485)))
    return sock.outgoing.getvalue()


class BrowserWebRTC(unittest.TestCase):
    def test_plan_is_offline_and_exact_binding_changes_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve();config = root / 'config.json';config.write_bytes(b'{}')
            parser = argparse.ArgumentParser();web.register_commands(parser.add_subparsers(dest='command'))
            args = parser.parse_args(['webrtc-plan', '--config', str(config), '--target-alias', 'device',
                '--profile-alias', 'profile', '--platform', 'macos', '--stun-url', 'stun:stun.example.com:3478',
                '--output', str(root / 'plan.json')])
            with patch.object(web, 'serve', side_effect=AssertionError('must not open a server')):
                result = web.run(c, args)
            self.assertEqual(result['network_requests'], 0)
            self.assertFalse(result['browser_launched'])
            saved = c.load_json(c.read_bytes(args.output))
            config.write_bytes(b'{"changed":true}')
            serve_args = parser.parse_args(['webrtc-serve', '--plan', args.output, '--config', str(config),
                '--session-output', str(root / 'session.json'), '--output', str(root / 'result.json')])
            with self.assertRaisesRegex(c.SetupError, 'CONFIG_CHANGED'):
                web.run(c, serve_args)
            for url in ('turn:user:pass@host:3478', 'stun:evil/path:3478', 'stun:host:70000', 'stun:host:3478?x=1'):
                bad = copy.deepcopy(saved);bad['stun_urls'] = [url]
                with self.subTest(url=url), self.assertRaises(ValueError):
                    web.validate_plan(bad)

    def test_matching_sample_does_not_claim_whole_machine_or_actual_media_path(self):
        p = plan();value = observation(p)
        result = web.project(p, value, 'synthetic', c.now())
        self.assertEqual(result['status'], 'sample_matches')
        self.assertFalse(result['network_protection_verified'])
        self.assertTrue(result['same_ip_is_not_same_path'])
        for name, change in [('timeout', {'finish': 'timeout'}), ('error701', {'error_codes': [701]}),
                             ('truncated', {'truncated': True}), ('notcomplete', {'gathering_complete': False})]:
            changed = copy.deepcopy(value);changed.update(change)
            with self.subTest(name=name):
                self.assertEqual(web.project(p, changed, 'synthetic', c.now())['status'], 'incomplete')
        changed = copy.deepcopy(value);changed['counts']['srflx_ipv4'] = 0;changed['reference_matches'] = False
        self.assertEqual(web.project(p, changed, 'synthetic', c.now())['status'], 'incomplete')
        changed = copy.deepcopy(value);changed['mismatch_observed'] = True
        self.assertEqual(web.project(p, changed, 'synthetic', c.now())['status'], 'mismatch_observed')
        changed['counts']['srflx_ipv6'] = 1;changed['ipv6_observed'] = True
        self.assertEqual(web.project(p, changed, 'synthetic', c.now())['status'], 'ipv6_observed')

    def test_untrusted_report_rejects_raw_addresses_unbounded_counts_forged_bindings_and_times(self):
        p = plan();value = observation(p)
        for mutate in [lambda x: x.update(raw_ip='203.0.113.2'), lambda x: x.update(plan_sha256='b' * 64),
                       lambda x: x['counts'].update(host=-1), lambda x: x['counts'].update(host=True),
                       lambda x: x.update(ipv6_observed=True), lambda x: x.update(error_codes=['secret']),
                       lambda x: x.update(ended_at='2100-01-01T00:00:00Z')]:
            bad = copy.deepcopy(value);mutate(bad)
            with self.assertRaises(ValueError):
                web.project(p, bad, 'synthetic', c.now())
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).isoformat()
        p['created_at'] = old;value = observation(p)
        with self.assertRaisesRegex(ValueError, 'STALE_OR_FUTURE'):
            web.project(p, value, 'synthetic', c.now())

    def test_real_http_handler_rejects_cross_origin_host_and_csrf_and_accepts_one_redacted_result(self):
        p = plan();session = web.ProbeSession(p, 180)
        page = request(session)
        self.assertIn(b'HTTP/1.1 200', page)
        self.assertIn(b"frame-ancestors 'none'", page)
        self.assertIn(b'Cache-Control: no-store', page)
        self.assertIn(b'RTCPeerConnection', page)
        self.assertNotIn(b'__SESSION_JSON__', page)
        self.assertIn(b'HTTP/1.1 403', request(session, host='attacker.example:19485'))
        body = c.encode(observation(p, session.session_id))
        self.assertIn(b'HTTP/1.1 403', request(session, 'POST', 'result', body, origin='https://attacker.example'))
        self.assertIn(b'HTTP/1.1 403', request(session, 'POST', 'result', body, csrf='wrong'))
        self.assertIn(b'HTTP/1.1 400', request(session, 'POST', 'result', body, extra=[('Content-Length', '1')]))
        secret = c.load_json(body);secret['address'] = '203.0.113.2'
        self.assertIn(b'HTTP/1.1 400', request(session, 'POST', 'result', c.encode(secret)))
        self.assertTrue(session.active())
        self.assertIn(b'HTTP/1.1 400', request(session, 'POST', 'result', body))
        self.assertIn(b'HTTP/1.1 200', request(session, 'POST', 'start', c.encode({'session_id': session.session_id})))
        self.assertIn(b'HTTP/1.1 400', request(session, 'POST', 'start', c.encode({'session_id': session.session_id})))
        self.assertIn(b'HTTP/1.1 200', request(session, 'POST', 'result', body))
        self.assertFalse(session.active())
        self.assertEqual(session.result['session_id'], session.session_id)
        self.assertIn(b'HTTP/1.1 410', request(session, 'POST', 'result', body))

    def test_session_cancellation_expiry_and_bad_request_budget(self):
        p = plan();clock = [0.0]
        session = web.ProbeSession(p, 30, monotonic=lambda: clock[0])
        self.assertIn(b'HTTP/1.1 405', request(session, 'OPTIONS'))
        body = b'x' * (web.MAX_BODY + 1)
        self.assertIn(b'HTTP/1.1 400', request(session, 'POST', 'result', body))
        self.assertIn(b'HTTP/1.1 200', request(session, 'POST', 'cancel', c.encode({'session_id': session.session_id})))
        self.assertTrue(session.cancelled)
        other = web.ProbeSession(p, 30, monotonic=lambda: clock[0]);clock[0] = 31
        self.assertIn(b'HTTP/1.1 410', request(other))

    @unittest.skipUnless(shutil.which('node'), 'Node is required for the offline browser lifecycle harness')
    def test_javascript_gates_stun_classifies_candidates_cleans_up_and_exports_no_addresses(self):
        session = web.ProbeSession(plan(), 180)
        page = session.page('http://127.0.0.1:19485').decode()
        script = page.split('<script nonce=', 1)[1].split('>', 1)[1].split('</script>', 1)[0]
        harness = r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
const script=JSON.parse(process.argv[1]);const elements={},events={},calls=[],timers=new Map();let number=0,peer,closed=0,channelClosed=0;
for(const name of ['binding','targets','reference','start','cancel','download','status'])elements[name]={value:'',textContent:'',disabled:false,addEventListener:(type,fn)=>events[name+':'+type]=fn};
const context=vm.createContext({document:{getElementById:id=>elements[id]},window:{addEventListener:(type,fn)=>events['window:'+type]=fn},Date,JSON,Object,Number,Error,console,AbortController,
 setTimeout:(fn)=>{timers.set(++number,fn);return number;},clearTimeout:id=>timers.delete(id),fetch:(url,options)=>{calls.push({url,options});return Promise.resolve({ok:true});},
 RTCPeerConnection:class {constructor(config){peer=this;calls.push({pc:config});}createDataChannel(){return {close(){channelClosed++;}};}createOffer(){return Promise.resolve({});}setLocalDescription(){return Promise.resolve();}close(){closed++;}}});
vm.runInContext(script,context);assert.equal(calls.length,0);elements.reference.value='203.0.113.8';events['start:click']();
setImmediate(()=>{assert.equal(calls.length,2);assert(calls[0].url.endsWith('/start'));assert.equal(elements.reference.value,'');peer.onicecandidate({candidate:{type:'host',address:'hidden.local'}});peer.onicecandidate({candidate:{type:'srflx',address:'203.0.113.8'}});peer.onicecandidate({candidate:{type:'srflx',address:'2001:db8::8'}});peer.onicecandidate({candidate:null});
 assert.equal(closed,1);assert.equal(channelClosed,1);assert.equal(timers.size,0);const submitted=JSON.parse(calls[2].options.body);assert.equal(submitted.counts.mdns,1);assert.equal(submitted.counts.srflx_ipv4,1);assert.equal(submitted.counts.srflx_ipv6,1);assert.equal(submitted.reference_matches,true);assert.equal(submitted.ipv6_observed,true);assert.equal(submitted.finish,'completed');assert(!calls[2].options.body.includes('203.0.113'));assert(!calls[2].options.body.includes('2001:db8'));assert.equal(vm.runInContext('referenceIP',context),'');events['window:pagehide']();assert.equal(calls.length,3);console.log('offline ICE lifecycle passed');});
'''
        result = subprocess.run([shutil.which('node'), '-e', harness, json.dumps(script)], capture_output=True,
                                text=True, encoding='utf-8', timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('offline ICE lifecycle passed', result.stdout)

    @unittest.skipUnless(shutil.which('node'), 'Node is required for the offline browser lifecycle harness')
    def test_javascript_requires_live_start_and_stops_ice_when_service_disappears(self):
        session = web.ProbeSession(plan(), 180)
        page = session.page('http://127.0.0.1:19485').decode()
        script = page.split('<script nonce=', 1)[1].split('>', 1)[1].split('</script>', 1)[0]
        harness = r'''
const vm=require('node:vm'),assert=require('node:assert/strict');const script=JSON.parse(process.argv[1]);
function scenario(startWorks){const elements={},events={},timers=new Map();let number=0,created=0,closed=0,channelClosed=0;
 for(const name of ['binding','targets','reference','start','cancel','download','status'])elements[name]={value:'',textContent:'',disabled:false,addEventListener:(type,fn)=>events[name+':'+type]=fn};
 const context=vm.createContext({document:{getElementById:id=>elements[id]},window:{addEventListener:(type,fn)=>events['window:'+type]=fn},Date,JSON,Object,Number,Error,AbortController,
 setTimeout:(fn,ms)=>{timers.set(++number,{fn,ms});return number;},clearTimeout:id=>timers.delete(id),
 fetch:(url)=>url.endsWith('/start')?Promise.resolve({ok:startWorks}):url.endsWith('/heartbeat')?Promise.reject(new Error('server stopped')):Promise.resolve({ok:true}),
 RTCPeerConnection:class {constructor(){created++;}createDataChannel(){return {close(){channelClosed++;}};}createOffer(){return Promise.resolve({});}setLocalDescription(){return Promise.resolve();}close(){closed++;}}});
 vm.runInContext(script,context);elements.reference.value='203.0.113.8';events['start:click']();return {context,timers,get created(){return created;},get closed(){return closed;},get channelClosed(){return channelClosed;}};
}
(async()=>{const failed=scenario(false);await new Promise(setImmediate);assert.equal(failed.created,0);assert.equal(failed.closed,0);assert.equal(vm.runInContext('referenceIP',failed.context),'');
 const live=scenario(true);await new Promise(setImmediate);assert.equal(live.created,1);const heartbeat=Array.from(live.timers).find(([,v])=>v.ms===750);assert(heartbeat);live.timers.delete(heartbeat[0]);heartbeat[1].fn();await new Promise(setImmediate);assert.equal(live.closed,1);assert.equal(live.channelClosed,1);assert.equal(vm.runInContext('latest.finish',live.context),'cancelled');assert.equal(vm.runInContext('referenceIP',live.context),'');assert.equal(live.timers.size,0);console.log('offline session death passed');})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result = subprocess.run([shutil.which('node'), '-e', harness, json.dumps(script)], capture_output=True,
                                text=True, encoding='utf-8', timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('offline session death passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
