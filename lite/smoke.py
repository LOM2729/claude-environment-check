"""Disposable synthetic fixture for testing a frozen bundle, without native UI."""
import json
from pathlib import Path
import tempfile
import tkinter
import claude_setup as c
from .service import Service


def run():
    with tempfile.TemporaryDirectory(prefix='clash-lite-smoke-') as td:
        root = Path(td).resolve()
        source = root / 'input.json'
        obj = {'mode': 'rule', 'proxies': [
            {'name': 'Demo Transit', 'type': 'http', 'server': '192.0.2.10', 'port': 8080},
            {'name': 'Demo Exit', 'type': 'socks5', 'server': '203.0.113.10', 'port': 1080,
             'dialer-proxy': 'Demo Transit'}], 'rules': ['DOMAIN,example.cn,DIRECT', 'MATCH,Demo Exit']}
        original = c.encode(obj); source.write_bytes(original)
        service = Service(root / 'private')
        service.load(source, probe_runtime=False)
        result = service.prepare('Demo Exit', preserve=True)
        exported = root / 'new-copy.yaml'
        receipt = service.export(exported)
        after = c.parse_config(exported.read_bytes(), 'yaml')
        assert source.read_bytes() == original and after['proxies'] == obj['proxies']
        assert result['export_ready'] and not receipt['runtime_verified']
        assert not receipt['proxy_or_system_changes']
        tcl = tkinter.Tcl()
        return {'ok': True, 'engine_version': c.VERSION, 'tcl_version': tcl.eval('info patchlevel'),
                'chain_preserved': True, 'source_unchanged': True, 'yaml_generated': True,
                'runtime_verified': False, 'proxy_or_system_changes': False}
