"""Local, new-file-only operations used by the native window."""
from pathlib import Path
import datetime as dt
import json
import os
import re
import sys
import uuid
import rule_data

import claude_setup as c
import config_recovery as recovery
from . import discovery, config_engine, runtime_probe

SITES = {'IP': 'https://ip.net.coffee/', 'DNS': 'https://ip.net.coffee/dns/',
         'WebRTC': 'https://ip.net.coffee/webrtc/'}
ERRORS = {
    'CHAIN_RELAY_UNSUPPORTED': '检测到旧式 relay 代理链，暂不自动转换。请联系交付人员处理，原配置未改动。',
    'CHAIN_EXTERNAL_DEPENDENCY_UNRESOLVED': '该节点依赖尚未读取的订阅节点，无法完整保留代理链。请导出包含节点的完整配置。',
    'CHAIN_DEPENDENCY_CYCLE': '配置存在循环代理依赖，已停止生成，原配置未改动。',
    'CHAIN_REFERENCE_MISSING': '代理链引用了缺失节点，无法生成完整副本。',
    'LITE_EXISTING_DIRECT_REVIEW_REQUIRED': '存在自定义直连例外。若要保留原有业务，请勾选“保留原有直连例外”后重试。',
    'LITE_DEPENDENCIES_UNRESOLVED': '配置引用了未能一并保存的本地资源，请联系交付人员处理。',
    'LITE_SOURCE_CHANGED': '原配置在处理中发生变化，请重新读取后再生成。',
    'OUTPUT_EXISTS_OR_UNAVAILABLE': '保存位置已存在文件或无法写入，请选择一个新的本机文件名。',
    'LITE_EXPORT_EXISTS': '所选文件已存在。请使用新文件名，原文件不会被覆盖。',
    'LITE_SAME_DISK_REQUIRED': '请先保存到本机同一磁盘的普通目录，例如“下载”。',
    'YAML_ANCHORS_UNSUPPORTED': '此配置使用了暂未支持的 YAML 引用语法，请导出展开后的完整配置。',
    'YAML_DEPENDENCY_MISSING': '检查引擎缺少 YAML 组件，请完整解压程序或联系交付人员。',
    'LITE_MIHOMO_FULL_CONFIG_REQUIRED': '请选择 Clash/Mihomo 导出的完整 YAML 或 JSON 配置，不能只选择一个节点名称。',
    'LITE_RULE_MODE_REVIEW_REQUIRED': '原配置不是规则模式，暂不能直接生成分流副本。请联系交付人员核对；工具不会切换当前客户端模式。',
    'CHAIN_NODE_ENDPOINT_INCOMPLETE': '链路上的节点地址或端口不完整，请导出包含完整节点参数的配置。',
    'CHAIN_NODE_ENDPOINT_INVALID': '节点地址包含不能直接使用的格式，请由交付人员核对，工具不会猜测修正。',
}


def error_message(exc):
    code = str(exc) if isinstance(exc, c.SetupError) else 'LITE_OPERATION_FAILED'
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{1,90}', code):
        code = 'LITE_OPERATION_FAILED'
    return ERRORS.get(code, '配置暂不能安全处理，请联系交付人员。原配置与当前代理均未改动。') + f' [{code}]'


def default_workspace():
    if sys.platform == 'darwin':
        parent = Path.home() / 'Library/Application Support'
    elif os.name == 'nt':
        parent = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local')))
    else:
        parent = Path.home() / '.local/share'
    parent = parent.resolve()
    # The platform's existing application-data parent must already exist.
    c.require(parent.is_dir(), 'RECOVERY_PATH_UNAVAILABLE')
    base = parent / 'ClashKitLite'
    recovery._private_dir(c, base, create=not base.exists())
    path = base / ('task-' + uuid.uuid4().hex)
    recovery._private_dir(c, path, create=True)
    return path


class Service:
    def __init__(self, workspace=None):
        self.root = default_workspace() if workspace is None else recovery._private_dir(
            c, Path(workspace).resolve(), create=not Path(workspace).exists())
        self.source = None
        self.source_hash = None
        self.inspection = None
        self.runtime = None
        self.selection = None
        self.prepared = None
        self.rule_client = None

    def discover(self):
        return discovery.discover()

    def load(self, path, probe_runtime=True):
        self.prepared = None
        self.source = self.source_hash = self.inspection = self.runtime = self.selection = None
        path = Path(path).absolute()
        c.require(path.suffix.lower() in ('.yaml', '.yml', '.json'), 'LITE_MIHOMO_FULL_CONFIG_REQUIRED')
        try:
            raw = discovery._read(path, c.MAX_FILE)
        except Exception:
            raise c.SetupError('INPUT_UNAVAILABLE') from None
        with rule_data.using(self.rule_client.current() if self.rule_client else None):
            info = config_engine.inspect_config(path)
        c.require(c.sha(raw) == info['source_sha256'], 'LITE_SOURCE_CHANGED')
        obj = c.parse_config(raw, c.config_format(path, 'auto'))
        runtime = runtime_probe.inspect_selection(obj) if probe_runtime else {
            'available': False, 'selected_node': None, 'selection_origin': None,
            'selections': {}, 'warning': 'RUNTIME_NOT_QUERIED'}
        self.source, self.source_hash, self.inspection = path, c.sha(raw), info
        self.runtime = runtime
        all_names = {n['name'] for n in info['nodes']}
        selectable = {n['name'] for n in info['nodes'] if n['selectable']}
        self.selection = runtime.get('selected_node') if runtime.get('selected_node') in all_names else None
        # An unresolved exit must never be silently replaced by its one readable
        # transit node. A lone-node convenience applies only to a lone-node file.
        if self.selection is None and len(all_names) == len(selectable) == 1:
            self.selection = next(iter(selectable))
        return {'inspection': info, 'runtime': runtime, 'selected_node': self.selection,
                'file_label': path.name}

    def _check_source(self):
        c.require(self.source is not None, 'LITE_CONFIG_REQUIRED')
        try:
            raw = discovery._read(self.source, c.MAX_FILE)
        except Exception:
            raise c.SetupError('LITE_SOURCE_CHANGED') from None
        c.require(c.sha(raw) == self.source_hash, 'LITE_SOURCE_CHANGED')

    def prepare(self, node, preserve=True):
        self.prepared = None
        self._check_source()
        names = {n['name'] for n in self.inspection['nodes'] if n['selectable']}
        c.require(node in names, 'AI_CONCRETE_NODE_NOT_FOUND')
        output = self.root / ('candidate-' + uuid.uuid4().hex)
        with rule_data.using(self.rule_client.current() if self.rule_client else None):
            result = config_engine.prepare_candidate(self.source, node, output,
                                                      preserve_existing_direct=preserve)
        self._check_source()
        self.selection, self.prepared = node, result
        return result

    def export(self, destination, manual_checks=None):
        c.require(self.prepared is not None and self.prepared.get('export_ready'), 'LITE_CANDIDATE_REQUIRED')
        checks = {key: (manual_checks or {}).get(key, '未记录') for key in SITES}
        c.require(all(v in ('未记录', '人工核对未见异常', '人工发现问题', '人工请求协助') for v in checks.values()),
                  'LITE_MANUAL_RESULT_INVALID')
        self._check_source()
        path, chain = recovery._safe_path(c, destination, missing=True)
        c.require(path.suffix.lower() in ('.yaml', '.yml'), 'LITE_YAML_EXTENSION_REQUIRED')
        c.require(not path.exists(), 'LITE_EXPORT_EXISTS')
        c.require(path.resolve() != self.source.resolve(), 'LITE_EXPORT_EXISTS')
        candidate = Path(self.prepared['candidate_path'])
        data = c.read_bytes(candidate)
        c.require(c.sha(data) == self.prepared['private_summary']['candidate_sha256'], 'LITE_CANDIDATE_CHANGED')
        # This is a NEW output only. No import/reload/controller writes exist.
        if os.name == 'nt':
            from desktop.backend import windows_export_new
            windows_export_new(path, chain, data)
        else:
            stage = self.root / ('export-' + uuid.uuid4().hex + '.yaml')
            recovery._write(c, stage, data)
            parent_fd = None
            try:
                _, current_chain = recovery._safe_path(c, path, missing=True)
                c.require(current_chain == chain and not path.exists(), 'LITE_EXPORT_EXISTS')
                parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                parent = os.fstat(parent_fd)
                c.require((parent.st_dev, parent.st_ino) == tuple(chain[-1][1:]), 'LITE_EXPORT_EXISTS')
                try:
                    os.link(stage, path.name, dst_dir_fd=parent_fd, follow_symlinks=False)
                except FileExistsError:
                    raise c.SetupError('LITE_EXPORT_EXISTS') from None
                except OSError:
                    raise c.SetupError('LITE_SAME_DISK_REQUIRED') from None
            finally:
                if parent_fd is not None:
                    os.close(parent_fd)
                stage.unlink(missing_ok=True)
        _, final_chain = recovery._safe_path(c, path)
        c.require(final_chain == chain and c.sha(c.read_bytes(path)) == c.sha(data), 'LITE_EXPORT_READBACK_FAILED')
        receipt = {'schema': 'lite-export/1', 'created_at': c.now(), 'output': str(path),
                   'rules_revision': self.prepared['private_summary']['rules_revision'],
                   'candidate_sha256': c.sha(data), 'source_unchanged': True,
                   'manual_checks': checks, 'manual_results_independently_verified': False,
                   'runtime_verified': False, 'proxy_or_system_changes': False}
        c.write_new(self.root / ('export-receipt-' + uuid.uuid4().hex + '.json'), c.encode(receipt))
        return receipt

    def support_summary(self, error_code=None):
        code = error_code if isinstance(error_code, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{1,90}', error_code) else None
        info = self.inspection or {}
        return {'engine_version': c.VERSION, 'platform': sys.platform, 'error_code': code,
                'rules_revision': self.rule_client.current().revision if self.rule_client and self.rule_client.current() else 'bundled',
                'candidate_rules_revision': (self.prepared or {}).get('private_summary', {}).get('rules_revision'),
                'config_loaded': self.source is not None, 'node_count': len(info.get('nodes', [])),
                'chain_count': len(info.get('chains', [])),
                'pending_direct_count': info.get('pending_direct_count'),
                'candidate_prepared': self.prepared is not None,
                'runtime_verified': False, 'proxy_or_system_changes': False,
                'private_configuration_included': False}
