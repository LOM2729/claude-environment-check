"""Read-back of explicitly selected outbound interfaces. No system mutations."""
import json
import platform
import re
from pathlib import Path

import readiness_lifecycle as life


def check(c, names):
    c.require(isinstance(names, list) and 1 <= len(names) <= 12, 'IPV6_EXPLICIT_INTERFACES_REQUIRED')
    c.require(len(names) == len(set(names)), 'IPV6_DUPLICATE_INTERFACE')
    rows, private = [], []
    for index, name in enumerate(names):
        c.require(isinstance(name, str) and 0 < len(name) <= 120 and not name.startswith('-')
                  and not any(ord(ch) < 32 or ch in '*?[]' for ch in name), 'IPV6_EXACT_INTERFACE_REQUIRED')
        off = False
        evidence = None
        if platform.system() == 'Darwin':
            raw = c.run_fixed(['/usr/sbin/networksetup', '-getinfo', name])
            if raw is not None:
                match = re.search(r'^IPv6:\s*(.+)$', raw, re.M)
                evidence = match.group(1).strip() if match else None
                off = evidence is not None and evidence.lower() == 'off'
        elif platform.system() == 'Windows':
            raw = c.run_fixed(['powershell.exe', '-NoProfile', '-NonInteractive', '-File',
                               str(Path(__file__).with_name('check_ipv6_binding.ps1')), '-AdapterName', name], timeout=20)
            try:
                value = c.load_json(raw.encode()) if raw else None
                if isinstance(value, dict) and value.get('name') == name:
                    off = value.get('enabled') is False
                    evidence = value
            except c.SetupError:
                pass
        rows.append(life.item('ipv6_interface_' + str(index + 1), '指定联网接口 IPv6 · ' + str(index + 1), off,
            '该明确指定的接口已读回为关闭；不包括 loopback 或未选接口。' if off else '该接口 IPv6 未读回为关闭，或未能取得可靠状态。',
            '核对所有实际出站接口及代理路径，再保存本轮网络记录。' if off else '核对服务/适配器身份与依赖，在批准范围内关闭并读回；不要用 IPv4 优先替代。'))
        private.append({'name': name, 'observed': evidence})
    return rows, private
