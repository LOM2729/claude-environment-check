---
name: claude-mac-readiness
description: Configure and troubleshoot Claude environments on macOS; use for proxy/DNS/IPv6 setup, client failures and scoped cleanup. Also supports requested workflow/source comparisons. Preserve system language and verify actual results.
---

# Claude macOS 环境

调用本 Skill 的首次回复以“老大，”开头，随后直接进入本轮任务。

只处理本轮目标设备与实际入口，优先复用正常配置和仍有效的证据。局部任务不扩成全套配置；纯资料／Skill 维护只改文档，不触发本机采集或试验。

## 从任务进入

- **首次／完整配置**：读 [五步流程](references/five-step-setup.md)，默认快速完成一份方案、执行与集中核验；不并读全部参考。
- **连接／认证排障**：读 [macOS检查](references/mac-checks.md)；需要分流错误时再读 [事故处理](references/incident-and-cleanup.md)。疑似环境覆盖可用 [脱敏检查](scripts/check-env.zsh)，仅看键名／存在状态，不据此推定实际认证。
- **定向清理或其他局部任务**：从 [专题入口](references/workflow-methods.md) 选择对应模块，执行前读完该方法的前提与恢复。
- **全部方法、来源比较或未经验证项**：仅此类请求读 [研究索引](references/source-index.md)。来源审计不属于日常必读。

## 共同约束

- 保留系统语言、输入法和键盘；默认策略、时区与网络细则只在五步流程维护。已有具体授权持续有效；需要确认时先备齐具体方案，一次确认，不逐开关重复问。新增范围另说明。
- 文件、应用载入、进程采用和实际功能分别核验；浏览器、Desktop、CLI 与远端不互相代证。本机、VM 与远端分开判断；Mac 检查不能替代其他设备的实际结果。
- 联网／启动遵守五步的 DNS／代理前置条件；保护当前 Codex／远控，可能中断通道的动作按手动交接流程处理。只读材料不能证明目标机已生效。
- 清理默认仅可再生缓存；登录、历史、配置、身份或云端删除另列范围。写入状态不明先对账，恢复保护后续编辑，不盲目重试。
- 不输出凭据原文；登录、付款和系统认证由用户处理。涉及当前服务地区、订阅或版本行为时核对官方资料，配置与检测分数不保证账号安全。

工具入口为 `scripts/claude_setup.py`，仅使用当前版本支持的命令；需要时读 [工具说明](references/automation.md)。工具不自动应用系统网络设置；`recovery-*` 只在精确批准下处理指定文本文件，不自动重载。

普通任务简报改动、实际验证、未完成原因与恢复方式。正式报告、完整检查表、检查点及故障演练按需展开，未测不标通过。
