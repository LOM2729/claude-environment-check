"""Explicit, temporary browser-Profile ICE observations; never a whole-machine proof."""
import datetime as dt
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import socket
import sys
import threading
import time

COMMANDS = ('webrtc-plan', 'webrtc-serve', 'webrtc-report')
PLAN_SCHEMA = 'claude-browser-webrtc-plan/1'
RESULT_SCHEMA = 'claude-browser-webrtc-observation/1'
MAX_BODY = 16384
COUNTS = ('host', 'mdns', 'srflx_ipv4', 'srflx_ipv6', 'relay', 'prflx', 'unknown')
FINISH = ('completed', 'timeout', 'cancelled', 'pagehide', 'error', 'expired')
SHA = re.compile(r'[0-9a-f]{64}')


def register_commands(subparsers):
    p = subparsers.add_parser('webrtc-plan', help='Prepare a browser ICE/STUN proposal; no network or browser launch')
    p.add_argument('--config', required=True)
    p.add_argument('--target-alias', required=True)
    p.add_argument('--profile-alias', required=True)
    p.add_argument('--platform', choices=('macos', 'windows', 'linux'), required=True)
    p.add_argument('--stun-url', action='append', required=True, help='Exact approved stun:hostname:port, no credentials')
    p.add_argument('--measurement-seconds', type=int, default=12)
    p.add_argument('--output', required=True)
    p = subparsers.add_parser('webrtc-serve', help='Serve a random-token loopback page; STUN starts only after browser approval')
    p.add_argument('--plan', required=True)
    p.add_argument('--config', required=True)
    p.add_argument('--allow-network', action='store_true')
    p.add_argument('--session-seconds', type=int, default=180)
    p.add_argument('--session-output', required=True, help='New private file with temporary local URL; no automatic launch')
    p.add_argument('--output', required=True, help='New private redacted browser observation')
    p = subparsers.add_parser('webrtc-report', help='Validate a browser-exported redacted observation against its plan/config')
    p.add_argument('--plan', required=True)
    p.add_argument('--config', required=True)
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)


def _need(condition, code):
    if not condition:
        raise ValueError(code)


def _alias(value):
    _need(type(value) is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}', value), 'WEBRTC_ALIAS_REQUIRED')
    return value


def _stamp(value):
    _need(type(value) is str and len(value) <= 40, 'WEBRTC_TIMESTAMP_INVALID')
    try:
        stamp = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('WEBRTC_TIMESTAMP_INVALID') from None
    _need(stamp.tzinfo is not None, 'WEBRTC_TIMESTAMP_INVALID')
    return stamp


def _stun(value):
    # No TURN credentials, DNS query options, URL user-info, paths or implicit ports.
    _need(type(value) is str and len(value) <= 270, 'WEBRTC_STUN_URL_INVALID')
    match = re.fullmatch(r'stun:([A-Za-z0-9.-]+):([0-9]{1,5})', value)
    _need(match is not None, 'WEBRTC_STUN_URL_INVALID')
    hostname, port = match.groups()
    _need(1 <= int(port) <= 65535 and len(hostname) <= 253 and
          all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', x) for x in hostname.split('.')),
          'WEBRTC_STUN_URL_INVALID')
    return value


def validate_plan(value):
    _need(type(value) is dict and set(value) == {'schema', 'created_at', 'target_alias', 'profile_alias',
          'platform', 'config_sha256', 'stun_urls', 'measurement_seconds'}, 'WEBRTC_PLAN_INVALID')
    _need(value['schema'] == PLAN_SCHEMA and type(value['config_sha256']) is str
          and SHA.fullmatch(value['config_sha256']), 'WEBRTC_PLAN_INVALID')
    _stamp(value['created_at'])
    _alias(value['target_alias']); _alias(value['profile_alias'])
    _need(value['platform'] in ('macos', 'windows', 'linux'), 'WEBRTC_PLAN_INVALID')
    _need(type(value['measurement_seconds']) is int and 3 <= value['measurement_seconds'] <= 30,
          'WEBRTC_MEASUREMENT_BUDGET_INVALID')
    urls = value['stun_urls']
    _need(type(urls) is list and 1 <= len(urls) <= 3 and all(type(url) is str for url in urls)
          and len(set(urls)) == len(urls), 'WEBRTC_STUN_URL_INVALID')
    for url in urls:
        _stun(url)
    return value


def _json(raw):
    _need(type(raw) is bytes and len(raw) <= MAX_BODY, 'WEBRTC_BODY_TOO_LARGE')
    def pairs(values):
        result = {}
        for key, value in values:
            _need(key not in result, 'WEBRTC_INVALID_JSON')
            result[key] = value
        return result
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('WEBRTC_INVALID_JSON')))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValueError('WEBRTC_INVALID_JSON') from None


def plan_digest(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def validate_observation(value, plan, expected_session=None):
    """Only finite enums/counts/booleans cross loopback; raw candidates/IPs are rejected."""
    fields = {'schema', 'plan_sha256', 'session_id', 'started_at', 'ended_at', 'finish',
              'counts', 'reference_provided', 'reference_matches', 'mismatch_observed',
              'ipv6_observed', 'gathering_complete', 'truncated', 'error_codes'}
    _need(type(value) is dict and set(value) == fields and value['schema'] == RESULT_SCHEMA,
          'WEBRTC_OBSERVATION_INVALID')
    _need(value['plan_sha256'] == plan_digest(plan), 'WEBRTC_PLAN_BINDING_MISMATCH')
    _need(type(value['session_id']) is str and re.fullmatch(r'[0-9a-f]{32}', value['session_id']), 'WEBRTC_SESSION_INVALID')
    if expected_session is not None:
        _need(value['session_id'] == expected_session, 'WEBRTC_SESSION_MISMATCH')
    start, end = _stamp(value['started_at']), _stamp(value['ended_at'])
    _need(start >= _stamp(plan['created_at']) and 0 <= (end - start).total_seconds() <= 45,
          'WEBRTC_OBSERVATION_TIME_INVALID')
    _need(value['finish'] in FINISH, 'WEBRTC_OBSERVATION_INVALID')
    counts = value['counts']
    _need(type(counts) is dict and set(counts) == set(COUNTS) and
          all(type(n) is int and 0 <= n <= 65535 for n in counts.values()), 'WEBRTC_COUNTS_INVALID')
    for name in ('reference_provided', 'reference_matches', 'mismatch_observed', 'ipv6_observed',
                 'gathering_complete', 'truncated'):
        _need(type(value[name]) is bool, 'WEBRTC_OBSERVATION_INVALID')
    _need(type(value['error_codes']) is list and len(value['error_codes']) <= 32 and
          all(type(n) is int and 0 <= n <= 65535 for n in value['error_codes']), 'WEBRTC_OBSERVATION_INVALID')
    _need(not value['reference_matches'] or (value['reference_provided'] and counts['srflx_ipv4'] > 0),
          'WEBRTC_OBSERVATION_INCONSISTENT')
    _need(not value['mismatch_observed'] or (value['reference_provided'] and counts['srflx_ipv4'] > 0),
          'WEBRTC_OBSERVATION_INCONSISTENT')
    _need(value['ipv6_observed'] == (counts['srflx_ipv6'] > 0), 'WEBRTC_OBSERVATION_INCONSISTENT')
    return value


def project(plan, observation, source, observed_at):
    value = validate_observation(observation, plan)
    age = (_stamp(observed_at) - _stamp(value['ended_at'])).total_seconds()
    _need(-5 <= age <= 3600, 'WEBRTC_OBSERVATION_STALE_OR_FUTURE')
    complete = (value['finish'] == 'completed' and value['gathering_complete'] and
                value['reference_provided'] and value['counts']['srflx_ipv4'] > 0 and
                not value['truncated'] and not value['error_codes'])
    status = ('ipv6_observed' if value['ipv6_observed'] else 'mismatch_observed' if value['mismatch_observed']
              else 'sample_matches' if complete and value['reference_matches'] else 'incomplete')
    return {'schema': 'claude-browser-webrtc-report/1', 'checked_at': observed_at,
        'target_alias': plan['target_alias'], 'profile_alias': plan['profile_alias'], 'platform': plan['platform'],
        'config_sha256': plan['config_sha256'], 'plan_sha256': plan_digest(plan), 'session_id': value['session_id'],
        'status': status, 'required_checks_completed': status == 'sample_matches',
        'evidence_source': source, 'observation': value, 'network_protection_verified': False,
        'scope': 'one_browser_profile_ice_sample_not_actual_media_path_or_whole_machine',
        'same_ip_is_not_same_path': True, 'host_mdns_relay_not_public_leak_proof': True,
        'system_changes_performed': False}


class ProbeSession:
    def __init__(self, plan, duration, asset=None, monotonic=time.monotonic, wall=time.time):
        validate_plan(plan)
        _need(type(duration) is int and 30 <= duration <= 600, 'WEBRTC_SESSION_BUDGET_INVALID')
        self.plan, self.duration = json.loads(json.dumps(plan)), duration
        self.clock, self.wall = monotonic, wall
        self.created = monotonic()
        self.expires = self.created + duration
        self.expires_ms = int((wall() + duration) * 1000)
        self.token, self.csrf, self.nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        self.session_id = secrets.token_hex(16)
        self.asset = asset if asset is not None else Path(__file__).with_name('browser_webrtc.html').read_text(encoding='utf-8')
        self.result, self.cancelled, self.lock = None, False, threading.Lock()
        self.started_at = None

    def active(self):
        return self.clock() < self.expires and self.result is None and not self.cancelled

    def page(self, origin):
        payload = {'plan': self.plan, 'plan_sha256': plan_digest(self.plan), 'session_id': self.session_id,
                   'csrf': self.csrf, 'base': '/' + self.token + '/', 'expires_ms': self.expires_ms}
        encoded = json.dumps(payload, ensure_ascii=True).replace('<', '\\u003c')
        return self.asset.replace('__NONCE__', self.nonce).replace('__SESSION_JSON__', encoded).encode('utf-8')


def handler_for(session):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, *args):
            pass  # Random URL, aliases and private session payloads never enter logs.

        def _send(self, code, body=b'', content='application/json; charset=utf-8'):
            self.send_response(code)
            for name, value in [('Content-Type', content), ('Content-Length', str(len(body))),
                ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
                ('Referrer-Policy', 'no-referrer'), ('X-Frame-Options', 'DENY'),
                ('Cross-Origin-Opener-Policy', 'same-origin'),
                ('Content-Security-Policy', "default-src 'none'; script-src 'nonce-%s'; style-src 'nonce-%s'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'" % (session.nonce, session.nonce)),
                ('Connection', 'close')]:
                self.send_header(name, value)
            self.end_headers()
            self.close_connection = True
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _scope(self):
            origin = 'http://127.0.0.1:' + str(self.server.server_address[1])
            if self.client_address[0] != '127.0.0.1' or self.headers.get_all('Host') != [origin[7:]]:
                self._send(403); return None
            if not session.active():
                self._send(410); return None
            return origin

        def do_GET(self):
            origin = self._scope()
            if origin is None:
                return
            if self.path not in ('/' + session.token + '/', '/' + session.token + '/heartbeat'):
                self._send(404); return
            if self.headers.get('Sec-Fetch-Site') not in (None, 'none', 'same-origin'):
                self._send(403); return
            if self.path.endswith('/heartbeat'):
                self._send(200, b'{"active":true}')
            else:
                self._send(200, session.page(origin), 'text/html; charset=utf-8')

        def do_POST(self):
            origin = self._scope()
            if origin is None:
                return
            if self.path not in ('/' + session.token + '/start', '/' + session.token + '/result', '/' + session.token + '/cancel'):
                self._send(404); return
            tokens = self.headers.get_all('X-CSRF-Token')
            if (self.headers.get_all('Origin') != [origin] or not tokens or len(tokens) != 1
                    or not secrets.compare_digest(tokens[0], session.csrf)
                    or self.headers.get('Sec-Fetch-Site') not in (None, 'same-origin')):
                self._send(403); return
            sizes = self.headers.get_all('Content-Length')
            if (self.headers.get('Transfer-Encoding') is not None or not sizes or len(sizes) != 1
                    or len(sizes[0]) > 6 or not sizes[0].isdigit() or not 0 < int(sizes[0]) <= MAX_BODY
                    or self.headers.get('Content-Type') != 'application/json'):
                self._send(400); return
            try:
                raw = self.rfile.read(int(sizes[0]))
                _need(len(raw) == int(sizes[0]), 'WEBRTC_BODY_INCOMPLETE')
                value = _json(raw)
                if self.path.endswith('/start'):
                    _need(value == {'session_id': session.session_id}, 'WEBRTC_SESSION_MISMATCH')
                    with session.lock:
                        _need(session.active() and session.started_at is None, 'WEBRTC_SESSION_ALREADY_STARTED')
                        session.started_at = session.wall()
                elif self.path.endswith('/cancel'):
                    _need(value == {'session_id': session.session_id}, 'WEBRTC_SESSION_MISMATCH')
                    with session.lock:
                        _need(session.active(), 'WEBRTC_SESSION_ENDED')
                        session.cancelled = True
                else:
                    _need(session.started_at is not None, 'WEBRTC_START_REQUIRED')
                    validate_observation(value, session.plan, session.session_id)
                    received = dt.datetime.fromtimestamp(session.wall(), dt.timezone.utc)
                    _need(_stamp(value['started_at']) >= dt.datetime.fromtimestamp(session.started_at, dt.timezone.utc) - dt.timedelta(seconds=5)
                          and _stamp(value['ended_at']) <= received + dt.timedelta(seconds=5),
                          'WEBRTC_OBSERVATION_TIME_INVALID')
                    with session.lock:
                        _need(session.active(), 'WEBRTC_SESSION_ENDED')
                        session.result = value
                self._send(200, b'{"accepted":true}')
            except (ValueError, OSError, socket.timeout):
                self._send(400)

        def do_OPTIONS(self):
            self._send(405)

        do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS
    return Handler


class BoundedServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def __init__(self, *args, **kwargs):
        self._slots = threading.BoundedSemaphore(8)
        super().__init__(*args, **kwargs)

    def process_request(self, request, address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self._slots.release()


def serve(c, plan, duration, session_output, output, server_factory=BoundedServer, config_check=None):
    session = ProbeSession(plan, duration)
    with server_factory(('127.0.0.1', 0), handler_for(session)) as server:
        server.daemon_threads = True
        server.timeout = .25
        origin = 'http://127.0.0.1:' + str(server.server_address[1])
        c.write_new(session_output, c.encode({'schema': 'claude-browser-webrtc-session/1',
            'url': origin + '/' + session.token + '/', 'expires_at': dt.datetime.fromtimestamp(session.wall() + duration,
                dt.timezone.utc).isoformat(), 'target_alias': plan['target_alias'], 'profile_alias': plan['profile_alias'],
            'plan_sha256': plan_digest(plan), 'browser_launched': False,
            'instruction': 'Open this URL in the selected existing browser Profile; review exact STUN targets before clicking.'}))
        try:
            while session.active():
                server.handle_request()
        except KeyboardInterrupt:
            session.cancelled = True
        if session.result is None:
            result = {'schema': 'claude-browser-webrtc-report/1', 'status': 'cancelled' if session.cancelled else 'expired',
                'target_alias': plan['target_alias'], 'profile_alias': plan['profile_alias'],
                'platform': plan['platform'], 'config_sha256': plan['config_sha256'], 'plan_sha256': plan_digest(plan),
                'session_id': session.session_id, 'checked_at': c.now(), 'required_checks_completed': False,
                'network_protection_verified': False, 'system_changes_performed': False}
        else:
            result = project(plan, session.result, 'loopback_browser_supplied_not_independently_verified', c.now())
        if config_check is not None:
            _need(config_check(), 'WEBRTC_CONFIG_CHANGED')
        c.write_new(output, c.encode(result))
        # No raw candidate, reference address or browser credential is ever stored by Python.
        return {k: result[k] for k in ('schema', 'status', 'required_checks_completed',
            'network_protection_verified', 'system_changes_performed')}


def run(c, args):
    try:
        if args.command == 'webrtc-plan':
            plan = validate_plan({'schema': PLAN_SCHEMA, 'created_at': c.now(), 'target_alias': args.target_alias,
                'profile_alias': args.profile_alias, 'platform': args.platform, 'config_sha256': c.sha(c.read_bytes(args.config)),
                'stun_urls': args.stun_url, 'measurement_seconds': args.measurement_seconds})
            c.write_new(args.output, c.encode(plan))
            return {'status': 'webrtc_plan_written', 'required_checks_completed': True, 'network_requests': 0,
                    'browser_launched': False, 'system_changes_performed': False}
        plan = validate_plan(_json(c.read_bytes(args.plan, MAX_BODY)))
        c.require(c.sha(c.read_bytes(args.config)) == plan['config_sha256'], 'WEBRTC_CONFIG_CHANGED')
        if args.command == 'webrtc-report':
            observation = _json(c.read_bytes(args.input, MAX_BODY))
            result = project(plan, observation, 'imported_browser_observation_not_independently_verified', c.now())
            c.write_new(args.output, c.encode(result))
            return {k: result[k] for k in ('schema', 'status', 'required_checks_completed',
                'network_protection_verified', 'system_changes_performed')}
        c.require(args.allow_network, 'EXPLICIT_NETWORK_OPT_IN_REQUIRED')
        actual = 'macos' if sys.platform == 'darwin' else 'windows' if sys.platform == 'win32' else 'linux' if sys.platform.startswith('linux') else 'unsupported'
        c.require(plan['platform'] == actual, 'WEBRTC_TARGET_PLATFORM_MISMATCH')
        age = (dt.datetime.now(dt.timezone.utc) - _stamp(plan['created_at'])).total_seconds()
        c.require(0 <= age <= 3600, 'WEBRTC_PLAN_STALE')
        return serve(c, plan, args.session_seconds, args.session_output, args.output,
                     config_check=lambda: c.sha(c.read_bytes(args.config)) == plan['config_sha256'])
    except ValueError as exc:
        code = str(exc)
        raise c.SetupError(code if code.startswith('WEBRTC_') else 'WEBRTC_OPERATION_FAILED') from None
    except (OSError, TypeError, KeyError, RecursionError):
        raise c.SetupError('WEBRTC_OPERATION_FAILED') from None
