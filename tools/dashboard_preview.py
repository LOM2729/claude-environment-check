#!/usr/bin/env python3
"""Create a synthetic offline UI fixture; never collects or probes a device."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import claude_setup as c
import report_dashboard


def preview(output):
    rows = [
        {'id': 'system_dns', 'title': '系统与代理 DNS', 'status': '未完成', 'required': True,
         'reason': '尚未核实 DNS 查询是否绕过指定线路。',
         'next_step': '由 Codex 补做 DNS 路径检查。',
         'observation': '仅为界面测试材料，没有读取本机设置。'},
        {'id': 'system_proxy', 'title': '代理与接管', 'status': '已完成', 'required': True,
         'reason': '示例结果：代理已开启，本次代理连接正常。',
         'next_step': '更换节点或网络后再检查。', 'verified_at': '2026-10-24T10:00:00+08:00'},
        {'id': 'public_egress', 'title': '公网出口', 'status': '已完成', 'required': True,
         'reason': '示例结果：本次已测线路的出口一致。', 'next_step': '其他软件的出口需要分别核对。'},
        {'id': 'ip_families', 'title': 'IPv4／IPv6', 'status': '已完成', 'required': True,
         'reason': '示例结果：选定网络和代理层已关闭 IPv6。', 'next_step': '换网后重新检查。'},
        {'id': 'ai_failure', 'title': 'AI 代理失败不回落直连', 'status': '未完成', 'required': False,
         'reason': '尚未安排本轮演练。', 'next_step': '客户选择演练后，先准备恢复路径。'},
    ]
    page = report_dashboard.render(title='启动前检查', checked_at='2026-10-24T10:00:00+08:00',
        generated_at='2026-10-24T10:02:00+08:00', rows=rows, current_label='启动必需检查',
        followup_label='后续复查', metadata=(('来源', '合成示例（非设备实测）'),),
        notes=('本页面只验证界面，不表示真实设备已完成任何检查。',))
    c.write_new(output, page.encode('utf-8'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    preview(parser.parse_args().output)
