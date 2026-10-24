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
        {'title': 'DNS 与代理路径', 'status': '未完成', 'required': True,
         'reason': '合成示例：尚未取得本轮 DNS 路径证据。',
         'next_step': '在已批准范围完成非 AI 验证，再继续启动检查。',
         'observation': '仅为界面测试材料，没有读取本机设置。'},
        {'title': '指定代理规则', 'status': '已完成', 'required': True,
         'reason': '合成示例：本项记录与本次指定范围一致。',
         'next_step': '实际配置变化后重新核验。', 'verified_at': '2026-10-24T10:00:00+08:00'},
        {'title': 'IPv6 关闭范围', 'status': '已完成', 'required': True,
         'reason': '合成示例：选定接口与代理层的记录齐全。', 'next_step': '更换网络后重新核对。'},
        {'title': '客户保留业务', 'status': '已完成', 'required': True,
         'reason': '合成示例：视频与远控均有对应观察记录。', 'next_step': '按本次确认的范围使用。'},
        {'title': '代理故障与恢复', 'status': '未完成', 'required': False,
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
