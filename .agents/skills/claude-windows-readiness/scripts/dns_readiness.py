"""Fresh operator DNS/path verification record, bound to this machine's network settings.

A record captures checks performed by the operator; it is not autonomous proof of
routing correctness or permission for network traffic. No active probes here.
"""
import datetime as dt
from pathlib import Path
import readiness_lifecycle as lifecycle
from urllib.parse import urlsplit

MAX_AGE_SECONDS = 1800
NETWORK_KEYS = ('http_proxy_enabled', 'https_proxy_enabled', 'socks_proxy_enabled', 'pac_present',
                'ipv4_interface_count', 'ipv6_interface_count', 'tunnel_interface_count')


def fingerprint(c, config, browser=None):
    c.require(bool(config), 'DNS_READY_CURRENT_CONFIG_REQUIRED')
    state = lifecycle.native_state(c)
    c.require(state.get('dns_identity_sha256') is not None, 'DNS_READY_DNS_UNAVAILABLE')
    browser_digest = None
    if browser:
        data = c.load_json(c.read_bytes(browser))
        c.require(isinstance(data, dict), 'BROWSER_PREFERENCES_OBJECT_REQUIRED')
        browser_digest = c.sha(c.encode({key: data.get(key) for key in ('dns_over_https', 'webrtc', 'proxy')}))
    return c.sha(c.encode({'machine': lifecycle.machine_id(c), 'config': c.sha(c.read_bytes(config)),
                          'dns': state['dns_identity_sha256'], 'browser_network': browser_digest,
                          'network_settings': {key: state['values'].get(key) for key in NETWORK_KEYS}}))


def proxy_identity(c, value):
    c.require(isinstance(value, str), 'DNS_READY_PROXY_REQUIRED')
    parsed = urlsplit(value)
    c.require(parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', '::1') and parsed.port
              and not parsed.username and not parsed.password and parsed.path in ('', '/')
              and not parsed.query and not parsed.fragment, 'DNS_READY_PROXY_INVALID')
    return [parsed.scheme, parsed.hostname, parsed.port]


def record(c, config, browser, output, readback, dns_path, proxy_path, evidence, proxy=None):
    c.require(readback and dns_path and proxy_path, 'DNS_READY_VERIFICATIONS_REQUIRED')
    endpoint = proxy_identity(c, proxy)
    note = c.safe_review_text(evidence)
    data = {'schema': 'claude-dns-readiness/1', 'verified_at': c.now(),
            'fingerprint': fingerprint(c, config, browser), 'evidence': note, 'proxy': endpoint,
            'readback_verified': True, 'dns_path_verified': True, 'proxy_path_verified': True,
            'evidence_kind': 'operator_record_not_automatic_path_proof', 'network_authorization': False}
    c.write_new(output, c.encode(data))
    return {'status': 'dns_readiness_recorded', 'network_requests': 0, 'system_settings_changed': False}


def check(c, receipt, config, browser=None, proxy=None):
    if not receipt:
        return False, 'DNS_READY_RECORD_REQUIRED'
    try:
        data = c.load_json(c.read_bytes(receipt))
        c.require(isinstance(data, dict) and data.get('schema') == 'claude-dns-readiness/1', 'DNS_READY_RECORD_INVALID')
        c.require(all(data.get(k) is True for k in ('readback_verified', 'dns_path_verified', 'proxy_path_verified')), 'DNS_READY_RECORD_INVALID')
        c.require(isinstance(data.get('proxy'), list) and len(data['proxy']) == 3, 'DNS_READY_RECORD_INVALID')
        c.require(data['proxy'][0] == 'http' and data['proxy'][1] in ('127.0.0.1', '::1')
                  and type(data['proxy'][2]) is int and 1 <= data['proxy'][2] <= 65535, 'DNS_READY_RECORD_INVALID')
        if proxy is not None:
            c.require(data['proxy'] == proxy_identity(c, proxy), 'DNS_READY_PROXY_CHANGED')
        c.safe_review_text(data.get('evidence'))
        verified = dt.datetime.fromisoformat(data['verified_at'])
        c.require(verified.tzinfo is not None, 'DNS_READY_RECORD_INVALID')
        age = (dt.datetime.fromisoformat(c.now()) - verified).total_seconds()
        c.require(-30 <= age <= MAX_AGE_SECONDS, 'DNS_READY_RECORD_EXPIRED')
        c.require(data.get('fingerprint') == fingerprint(c, config, browser), 'DNS_READY_NETWORK_CHANGED')
        return True, 'DNS_READY_CURRENT'
    except c.SetupError as error:
        return False, str(error)
    except (ValueError, TypeError, KeyError, OSError):
        return False, 'DNS_READY_RECORD_INVALID'
