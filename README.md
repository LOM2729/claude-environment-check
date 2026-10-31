# Claude 环境检测

让客户电脑上的 Codex 自动识别现状、准备具体方案，一次确认后完成配置与实际验证。支持 Mac / Windows，客户只看简短的已完成／未完成结果。

**[下载最新客户包](https://github.com/LOM2729/claude-environment-check/releases/latest/download/Claude-Setup-Kit.zip)** · [校验文件](https://github.com/LOM2729/claude-environment-check/releases/latest/download/Claude-Setup-Kit.zip.sha256) · [使用说明](START-HERE.md)

## 桌面端

[下载桌面端](https://github.com/LOM2729/claude-environment-check/releases/latest)：macOS 13+ Apple Silicon 与 Windows x64，独立应用内置五步向导和检查引擎，无需客户安装 Python。支持选配置／节点、只读检查、确认导出新文件、读回核对、已有报告导入及 Codex 续做。实际导入、系统网络配置和联网实测仍按本机具体方案完成，不能把文件导出当作配置已生效。详见 [桌面使用与构建说明](https://github.com/LOM2729/claude-environment-check/blob/main/desktop/README.md)。

## 给客户的一句话

请按 https://github.com/LOM2729/claude-environment-check 下载并校验最新版，按仓库五步自动配置：先准备完整方案并集中确认，网络核验后再打开 AI；保留系统语言，其他按现有用途处理，最后只给简短结果。

## 五步完成

1. **准备**：读取本机版本、软件、端口与现有配置，只补必要缺口；离线检查隐含请求、DIRECT、UDP 和依赖，备齐最终候选、差异与恢复材料。
2. **确认**：展示保留项、具体改动、影响、恢复和准确检测范围，集中确认一次。
3. **配置网络**：执行已批准项并读回，先核对 DNS、选定接口 IPv6 和非 AI 路径。
4. **使用 AI**：当前网络核验通过后，才启动／安装／登录实际需要的客户端并验证真实功能。
5. **交付**：简短结果、未完成原因和下一步，私有记录留本机；需要中断时保存进度，恢复后从核对点继续。

[五步细则](.agents/skills/claude-mac-readiness/references/five-step-setup.md) 是唯一执行顺序；长清单是内部核对表。客户不用填写技术参数或 JSON，已有配置和节点不重复问。系统语言保持，完整配置默认把时区对齐指定稳定出口纳入方案，目标不清先补问；浏览器语言无明确目标保留。

## 新增准备与排障模块

完整配置默认将系统时区对齐指定稳定出口的具体时区，原值、自动选项、影响与恢复列入方案，批准后执行并读回；明确保留项及局部任务按用户范围处理。系统语言、输入法和键盘继续保留。

按实际任务读取 [时区目标与验证](.agents/skills/claude-mac-readiness/references/timezone-policy.md)、[本机／VM／VPS 与出口规划](.agents/skills/claude-mac-readiness/references/deployment-routes.md)、[账号与订阅准备](.agents/skills/claude-mac-readiness/references/account-preparation.md)、[事故与清理规划](.agents/skills/claude-mac-readiness/references/incident-and-cleanup.md)。

[Claude-Guardian 固定版本审阅](.agents/skills/claude-mac-readiness/references/guardian-integration.md)记录参考方法和检测判据的局限；未接入其执行脚本，也不把固定养号天数、第三方全绿或免封保证设为要求。

## 默认网络目标

采用 `domestic-v4`，保留完整 AI、IPv6、UDP、国内视频／域名与教程扩展规则：Claude 专属组 `AI-ONLY-Claude` 和基础组 `AI-ONLY` 用同一指定节点，AI 保护优先且失败不回落 DIRECT；关闭选定联网接口及代理层 IPv6；国内视频直连位于其余 UDP 拒绝前，普通国内直连、普通国外统一代理。Mihomo 输出 YAML／JSON，小火箭输出原生 `.conf`。

[规则与视频](.agents/skills/claude-mac-readiness/references/domestic-video-udp.md) · [小火箭适配](.agents/skills/claude-mac-readiness/references/shadowrocket-domestic.md) · [教程覆盖与来源边界](.agents/skills/claude-mac-readiness/references/tutorial-coverage.md)

## 工具与交付

| 工具 | 用途 |
| --- | --- |
| collect / review-template / report | 只读采集、按模式记录保留项、生成二状态报告；自动模式保留系统语言 |
| contact-scan / direct-review / udp-check | 批准前离线检查隐含请求、直连例外和 UDP 限制层 |
| connection-check / connection-plan / ai-route / ai-audit / tutorial-check | 生成完整候选与私有差异，核对当前规则和连接设置，保留既有政策 |
| plan / verify / recovery-* | 文本快照、读回与可靠恢复，拒绝覆盖客户后续修改，不写应用数据库或自动重载 |
| network-plan / network-check / dns-ready / ipv6-check / action-check / preflight | 非 AI 前置核验、当前证据与服务动作门槛；外部请求必须在批准范围内 |
| lifecycle-template / lifecycle-accept | 默认仅正常使用为本次必需；其他七类后续复查未实测仍显示未完成，明确选择的事件严格验收 |
| workflow-save / workflow-resume | 私有进度与离线继续说明；恢复先查材料变化并重新核验网络，不恢复操作授权 |
| baseline / recheck | 更新后复查当前状态，不自动恢复旧值 |

[工具参数](.agents/skills/claude-mac-readiness/references/automation.md) · [进度与离线恢复](.agents/skills/claude-mac-readiness/references/workflow-progress.md) · [回滚与生命周期验收](.agents/skills/claude-mac-readiness/references/recovery-and-acceptance.md)

## 使用边界

Python 3.9+，YAML 需 PyYAML 6.0.3，优先复用已有运行时；确实缺依赖且无法准备候选时先单独确认明确的依赖安装，完成后再出最终配置方案，安装批准不覆盖未知配置改动。Mac、Windows 原生与 WSL／虚拟机／远端分别核验。缺少基础网络时先用可信材料或人工准备，在线 Codex 无法保证自身第一次联网前零 AI 请求。

需要重启客户端、核心、服务、机器，或操作可能中断控制通道时，只在确有需要后给客户明确动作、影响及本机离线恢复办法，再安排操作时机。客户手动完成、恢复连接后重新读回与核验，不能自行断开当前通道。

候选、文件匹配、应用载入、实际进程采用和端到端观察分别记录。生命周期工具只审阅供给证据，不自行制造事件；Mac／Windows 合成测试不等于客户网络实测。没有常驻监控、系统 Kill Switch 或账号防封保证。官方资料、源码参考和个人经验分开，见 [来源说明](.agents/skills/claude-mac-readiness/references/evidence-sources.md)。

完整配置、凭据、差异、IP 与证据只留客户本机；每位客户新解压一份。发布包按文件白名单生成，不含客户文件、运行报告或未完成教程草稿。

检查报告现使用 [离线面板](.agents/skills/claude-mac-readiness/references/report-dashboard.md)：显示检查时间，原因和下一步直接可见，详细记录与后续复查折叠。Mac／Windows 共用展示，不改变既有启动方式。
