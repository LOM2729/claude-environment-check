# Claude 私人向导 Skill

把本仓库地址和一段提示词发给 Codex，让它成为你的 Claude 私人向导，从了解现状开始，按需要带你完成环境配置、订阅准备、开通／升级、排障、清理，或申诉退款。

提供 macOS 与 Windows 两套 Skill。Codex 先复用已有信息，了解你的账号／订阅阶段、实际系统、目标和现有网络，再衔接当前需要的步骤。已有账号可以直接配置，需要开通或升级就按当前官方条件选择渠道，遇到账号或付款问题则进入对应处理流程。

技术方案、参数、备份、随包工具调用和核验由 Codex 准备，你可以随时选择、跳过、暂停或更改目标。登录、身份核验、接受条款及付款由你本人在官方流程完成，已知事实与同项有效批准继续复用。

完整配置按五步流程进行，局部任务直接进入相应专题。结果报告写清已完成、未完成原因和下一步，详细配置、备份及证据保存在本机私有目录。具体分支见 [单入口向导](.agents/skills/claude-mac-readiness/references/workflow-methods.md#单入口向导)。

[下载当前 main 源码](https://github.com/LOM2729/claude-environment-check/archive/refs/heads/main.zip) · [macOS Skill](.agents/skills/claude-mac-readiness/SKILL.md) · [Windows Skill](.agents/skills/claude-windows-readiness/SKILL.md) · [当前执行能力](.agents/skills/claude-mac-readiness/references/execution-capabilities.md)

## 快速开始

在目标电脑上打开 Codex，发送下面这段提示词，后面可以补一句自己的情况，例如“已有账号和节点，只需要配置”或“我想申请退款”。

```text
请用 https://github.com/LOM2729/claude-environment-check 的 Skill 当我的 Claude 私人向导，按需配置、开通升级或申诉退款，按授权执行核验。
```

也可以先下载并解压当前 main 源码，在 Codex 中打开该目录，保留隐藏的 `.agents` 文件夹，再发送同一段提示词。Codex 按实际系统读取对应的 `SKILL.md` 和本轮需要的专题。

已经安装对应 Skill 时，可以直接调用。

| 系统 | 调用示例 |
| --- | --- |
| macOS | `$claude-mac-readiness 帮我检查现有配置，保留当前节点、系统语言和工作资料。` |
| Windows | `$claude-windows-readiness 帮我检查现有配置，先核对 Windows 原生与 WSL 各自使用的入口。` |

当前流程与修正以 main 为准，Release 保存各标签发布时的快照。更新已有 Skill 时，先比较文件差异并备份，本地自行修改过的内容需要合并保留。随包更新工具可以固定 GitHub 提交、逐文件比较并生成报告，实际替换由本轮具体更新方案决定。

## 可以让它做什么

| 任务 | 可以直接这样说 |
| --- | --- |
| 首次或完整配置 | 我用 Mac／Windows，已经有代理和指定节点。帮我准备完整方案，保留系统语言、局域网和会议功能。 |
| 已有账号，准备订阅 | 我已有账号和节点，先核对需要的环境准备，再带我比较当前可用渠道、开通并核对权益。 |
| 升级或续费 | 我已有订阅，请按原购买渠道核对升级、续费、当前费用和生效规则。 |
| 申诉或退款 | 根据我实际收到的通知和原购买渠道，带我准备真实申诉材料，或申请退款与人工复议。 |
| 现有连接故障 | Claude Code／Desktop／网页在某一步报错。先定位实际入口和原因，再准备最小修复方案。 |
| 只清缓存 | 只处理 Claude 的可再生缓存，保留登录、MCP、历史、配置和项目资料。 |
| 清网页登录数据 | 只清我平时使用的 Chrome／Edge 资料中，指定站点的登录数据，先说明会退出哪些登录。 |
| 中断后继续 | 复用上次的私有进度、计划和回执，先核对当前状态，再继续未完成项。 |
| 更新后复查 | 刚更新了客户端／代理，帮我核对受影响的配置、规则和实际功能。 |
| 比较本机、VM 与 VPS | 按我的用途、预算和维护能力比较路线，先给建议和所需条件。 |
| 阅读来源和未验证方法 | 对照 Guardian／CCBaga 的固定版本，列出已实现、方法已收录和仍待验证的部分。 |

已有信息直接复用，只追问影响下一步的缺口。普通任务按实际客户端和目标设备处理，正式报告、完整来源研究、系统防护和故障演练按需展开。

## 完整配置的五步流程

1. **准备方案**。确认目标系统、实际客户端、活动配置、指定节点、接口与必保业务。核对隐含请求、直连例外和 UDP 依赖，准备最终候选、具体差异、原值、备份与恢复材料。
2. **集中确认**。展示本轮会改什么、保留什么、影响哪些业务、如何恢复，以及需要访问哪些检测目标。复用已有的有效授权，新增范围另行说明。
3. **应用并读回**。按目标软件支持的入口应用已批准项，核对活动配置、规则、节点、系统代理／TUN、DNS 与精确接口的 IPv6 状态。写入结果不明时先检查现状。
4. **验证实际功能**。先完成获准的非 AI 网络核验，再启动、安装、登录或测试实际需要的客户端。网页、Desktop、CLI、后台和远端分别记录结果。
5. **简短交付**。给出已完成项、未完成原因和下一步。备份、差异、回执和恢复说明留在本机，中断后依材料继续。

需要重启代理、核心、服务或机器，或操作可能中断当前 Codex／远控时，先准备准确动作和离线恢复说明，由使用者在合适时机完成，再读回与复核。

详细顺序见 [五步流程](.agents/skills/claude-mac-readiness/references/five-step-setup.md)，局部任务见 [专题入口](.agents/skills/claude-mac-readiness/references/workflow-methods.md)。

## 当前默认方案

以下是本项目完整配置的默认选择。具体任务中的明确保留项和业务依赖会进入本轮方案，局部任务只处理相关范围。

| 项目 | 默认处理 |
| --- | --- |
| 系统语言 | 保留系统语言、输入法和键盘 |
| 节点与分组 | 使用指定稳定节点，`AI-ONLY-Claude` 与 `AI-ONLY` 绑定同一节点，AI 失败时保持拒绝回落直连的规则 |
| 网络策略 | `domestic-v4`，AI 保护优先，保留已批准的国内、视频、LAN 和其他业务例外 |
| IPv6 | 完整配置默认关闭选定联网接口及相关代理层 IPv6，将准确接口、影响与恢复列入方案，现场逐层读回 |
| UDP 与视频 | AI 目标 UDP 拒绝，选定国内视频例外直连，其余 UDP 拒绝，按实际业务复核 |
| DNS | 分别核对系统、代理核心、浏览器和节点引导，记录各层实际采用的路径 |
| 时区 | 完整配置提出指定稳定出口对应的具体时区，记录原值和自动选项，按批准方案处理 |
| 浏览器语言 | 有明确目标时列入方案，其余沿用已有设置 |
| 清理范围 | 默认仅选择已确认可再生的缓存，登录、历史、配置及持久数据分别选择 |
| 验收范围 | 默认验证本轮实际使用入口的正常功能，更新、重启、睡醒、换网和故障事件按需要纳入 |

网络候选支持 Mihomo YAML／JSON 与 macOS 小火箭原生 `.conf`。完整国内分流、视频和 IPv6 规则的细节见 [统一出口](.agents/skills/claude-mac-readiness/references/unified-ipv4.md)、[国内视频与 UDP](.agents/skills/claude-mac-readiness/references/domestic-video-udp.md)、[小火箭适配](.agents/skills/claude-mac-readiness/references/shadowrocket-domestic.md) 和 [时区策略](.agents/skills/claude-mac-readiness/references/timezone-policy.md)。

## 已有工具与平台范围

统一工具入口为对应 Skill 下的 `scripts/claude_setup.py`。Codex 按当前命令与平台支持准备参数，使用者通过自然语言说明需求。

| 能力 | 当前实现与范围 |
| --- | --- |
| 本机检查与报告 | macOS／Windows 的限定元数据采集、脱敏报告和离线 HTML 面板，缺失或失败字段保留未知 |
| 网络候选与审计 | 配置结构、隐含请求、直连例外、UDP、AI 分组和教程扩展的检查与候选生成 |
| 文件应用与恢复 | 精确文本计划、备份、写入、读回、冲突检查和限定恢复，保护候选之后的修改 |
| 原生 Clash 规则 | macOS Clash Verge Rev 2.5.8、2.5.10 的专属 rules 扩展写入、检查和回滚，实际载入与路由另行核验 |
| Claude 数据隔离 | macOS 限定根与 Windows 本机固定 NTFS 卷上的限定根，独立备份、隔离、部分失败对账和恢复 |
| 浏览器 WebRTC | 在实际使用的浏览器 Profile 中打开临时本机页面，点击后采集指定 STUN 的 ICE 样本并生成脱敏报告 |
| 访谈与续接 | 保存已有事实、当前缺口和冲突，利用私有进度、计划与回执继续任务 |
| Skill 更新核对 | 固定本仓库 GitHub 提交，比较逐文件差异并保留本地独有内容的清单 |
| 系统出站防护 | macOS PF、Windows 原生防火墙、Linux nft 的专项计划、状态检查、限时恢复与可选持久化 |
| Linux 远端模块 | Debian／Ubuntu systemd 目标的受限 core／TUN、SSH、反向隧道、核心自愈和入站防护，提供目标机执行包 |
| 事件复查 | 当前使用、客户端／代理更新、重启、系统重启、睡醒、换网和故障恢复的证据模板与审阅 |

Windows 数据隔离要求原目录与备份位于同一固定 NTFS 卷，当前覆盖用户资料内的有效 Claude Code 配置根和受支持的 Roaming AppData Claude Desktop 根。MSIX 私有存储、资料外重定向、重解析点、硬链接、备用数据流和不支持的权限布局需要另行处理。

Windows Clash、小火箭及其他产品的配置应用，由 Codex 按实际版本采用支持的原生设置或导入入口。文件候选、文本写入、客户端载入、进程采用和实际功能各有独立核验结果。

系统防护当前可准备 `unified-v4`、明确的静态例外及 Linux 入站管理方案。默认 `domestic-v4` 的动态国内／视频规则尚未自动编译到系统防火墙，需要另行明确兼容方案。真实提权、既有规则、控制通道、持久状态与故障恢复按目标设备验收。

完整命令、输入和限制见 [执行能力](.agents/skills/claude-mac-readiness/references/execution-capabilities.md) 与 [工具说明](.agents/skills/claude-mac-readiness/references/automation.md)。

## 分项清理怎么做

Codex 先定位实际配置根、浏览器资料或安装来源，列清每类对象的本轮选择、影响和恢复条件，再处理获准项。

| 类别 | 当前处理方式 |
| --- | --- |
| 可再生缓存 | 随包工具支持限定的 CLI 缓存与 Desktop 资源、代码及图形缓存，默认只选这一类 |
| Claude 登录态 | CLI 可整体隔离有效配置根中的 `.credentials.json`，Keychain、Desktop 加密状态和其他共享秘密按专项方案处理 |
| 历史与日志 | 可显式选择工具支持的 history、projects、todos、debug 等对象，其他任务材料按实际对象核对 |
| 配置与扩展 | 对工具支持的 settings、Skills、plugins、hooks、agents 等分别选择，项目配置和其他根独立判断 |
| Chrome／Edge 站点数据 | 确定实际 Profile、站点／origin、分区和数据类型，由 Codex 通过当前可用的浏览器原生入口完成并核验 |
| Desktop 持久根 | 整根隔离涉及多类持久数据，计划中须写明全部影响与恢复边界 |
| 卸载或重装 | 根据 native、包管理器、Desktop 或集成入口的实际来源处理，程序、用户数据和云端对象分别确定范围 |

当前随包 CLI 的浏览器能力包含偏好检查和 WebRTC 检测，普通 Chrome／Edge 的定向删除通过原生界面处理。具体操作是否可由 Codex 直接完成，取决于目标浏览器、可用工具和权限，受限步骤会交给使用者并继续后续核对。

登录数据可能与 MCP／插件共享，处理前需要确认保留范围。浏览器登录、OS 加密密钥、过期或被撤销的凭据，以及云端任务各有恢复条件。备份文件可读时，实际登录和工作资料仍需分别验证。

详细对象与步骤见 [客户端清理](.agents/skills/claude-mac-readiness/references/client-cleanup.md)、[浏览器清理](.agents/skills/claude-mac-readiness/references/browser-cleanup.md) 和 [事故分流](.agents/skills/claude-mac-readiness/references/incident-and-cleanup.md)。

## 中断、写入不明与恢复

- **普通续接**。读取上次私有进度、事实、原计划和回执，核对配置及目标变化，再继续当前缺口。
- **隔离部分失败**。先通过 `cleanup-reconcile` 检查原位置、隔离材料和冲突，再依据新的观察决定恢复。
- **文本写入结果不明**。按完整回执或 intent 的实际类型和摘要调用对应检查器，保留后续修改及原始恢复材料。
- **原生规则恢复**。由受支持适配器产生的记录使用 `native-client-check`，Windows 的精确文本操作使用 `recovery-check`，根据检查结果准备后续动作。
- **系统设置恢复**。分别保存 DNS、IPv6、时区及自动选项的原值，通过相同原生层恢复并读回。
- **系统防护恢复**。执行前准备独立恢复入口和限时保险丝，核对运行规则与开机状态。已部署的旧恢复脚本继续按保存的摘要检查，新计划绑定当前工具版本。

私有索引记录计划、备份、回执、观察、创建时间和摘要，Codex 负责定位与核对。写入超时、材料冲突、缺权限或未取得实际结果时，交付中说明阶段、原因和下一步。

[进度与继续](.agents/skills/claude-mac-readiness/references/workflow-progress.md) · [回执与恢复](.agents/skills/claude-mac-readiness/references/recovery-and-acceptance.md) · [更新和生命周期](.agents/skills/claude-mac-readiness/references/lifecycle-checks.md)

## 运行条件与数据处理

- 使用支持本项目 Skill 的 Codex，在实际目标电脑上操作。macOS、Windows 原生、WSL、VM 和远端分别确认执行位置与权限。
- 随包 Python 工具需要 Python 3.9+，YAML 处理需要 `PyYAML==6.0.3`。优先复用已有运行时，缺少依赖时先准备具体安装方案。
- macOS／Linux 的系统防护独立恢复另需已核实可运行且权限合适的 Python，Windows 恢复依赖系统 PowerShell 与相应原生组件。
- 登录、验证码、付款、钥匙串及系统认证由使用者处理。可能中断当前连接的操作先准备私有离线恢复材料。
- 使用外部检测时说明准确目的地和传出信息，将本轮范围纳入方案。网络前置条件按目标入口核验，首次在线使用需要已有可信连接。
- 完整配置、凭据、真实 IP、私人链接、差异和证据留在本机私有目录，聊天和 GitHub 只使用必要的脱敏摘要。

## 验证状态与待完成项

| 状态 | 目前的证据与含义 |
| --- | --- |
| 源码与方法可查 | 当前命令、平台范围、输入、失败和恢复分支可从源码及专题核对 |
| 自动化验证已有 | macOS／Windows／Linux CI，文件事务与合成网络回归，Windows NTFS 临时目录测试，以及 PowerShell 内存夹具覆盖的策略和恢复检查 |
| 目标设备待验 | 实际浏览器、用户现有数据、客户端载入、有效路由、管理员防火墙、独立管理通道、重启／睡醒／换网和真实远端部署 |
| 机制存在、效果待验 | 本地设置修改、隔离、指纹参数、加密归档或线路优化的机制，各自需要对应目标和功能证据 |
| 社区因果未证 | 换 seed、清日志／本地 ID、语言／时区一致、住宅出口、邮箱、等待期或并发阈值与账号封禁概率之间的关系 |

源码中的平台限制与实际执行能力持续保留。独立浏览器、身份保险库、加密跨机迁移、细粒度认证字段清理及特定 Reality／VLESS → 住宅 SOCKS5 部署链，已有来源方法记录，完整产品执行能力仍有缺口。

当前复核可参考 [2026-11-11 来源差距表](docs/research/claude-environment/source-gap-review-20261111.md)、[对应源码 CI](https://github.com/LOM2729/claude-environment-check/actions/runs/42955611088) 和 [完整方法分类](docs/research/claude-environment/complete-environment-method.md)。每份证据按其提交、平台和观察范围使用，目标设备的验收状态按实际结果更新。

## 按任务查详细资料

| 主题 | 资料入口 |
| --- | --- |
| 完整配置与日常任务 | [五步流程](.agents/skills/claude-mac-readiness/references/five-step-setup.md)、[专题路由](.agents/skills/claude-mac-readiness/references/workflow-methods.md) |
| 代理、DNS、IPv6 与业务例外 | [配置导入](.agents/skills/claude-mac-readiness/references/proxy-import.md)、[统一出口](.agents/skills/claude-mac-readiness/references/unified-ipv4.md)、[业务与 UDP](.agents/skills/claude-mac-readiness/references/domestic-video-udp.md) |
| 当前客户端与执行位置 | [服务路径](.agents/skills/claude-mac-readiness/references/service-routing-checks.md)、[本机／WSL／VM／远端](.agents/skills/claude-mac-readiness/references/execution-paths.md) |
| 系统时区 | [时区目标、原值和恢复](.agents/skills/claude-mac-readiness/references/timezone-policy.md) |
| 清理、登录与程序维护 | [客户端分项清理](.agents/skills/claude-mac-readiness/references/client-cleanup.md)、[浏览器清理](.agents/skills/claude-mac-readiness/references/browser-cleanup.md) |
| 故障、订阅与账单 | [事故处理](.agents/skills/claude-mac-readiness/references/incident-and-cleanup.md)、[账号准备](.agents/skills/claude-mac-readiness/references/account-preparation.md)、[账单核对](.agents/skills/claude-mac-readiness/references/billing-checks.md) |
| VM／VPS 与出口路线 | [部署路线](.agents/skills/claude-mac-readiness/references/deployment-routes.md)、[专项执行能力](.agents/skills/claude-mac-readiness/references/execution-capabilities.md) |
| 更新、恢复与交付报告 | [生命周期](.agents/skills/claude-mac-readiness/references/lifecycle-checks.md)、[恢复与验收](.agents/skills/claude-mac-readiness/references/recovery-and-acceptance.md)、[报告面板](.agents/skills/claude-mac-readiness/references/report-dashboard.md) |
| Windows 专项问题 | [Windows Skill](.agents/skills/claude-windows-readiness/SKILL.md)、[原生系统与防火墙检查](.agents/skills/claude-windows-readiness/references/windows-checks.md) |
| 默认、可选、未验证和已纠正的方法 | [完整方法分类](docs/research/claude-environment/complete-environment-method.md) |
| Guardian／CCBaga 的阅读与对照 | [来源覆盖](docs/research/claude-environment/source-coverage.md)、[差距复核](docs/research/claude-environment/source-gap-review-20261111.md)、[Guardian 参考](.agents/skills/claude-mac-readiness/references/guardian-integration.md)、[CCBaga 方法](docs/research/claude-environment/ccbaga-methods.md) |

专题资料按实际任务读取。Guardian、CCBaga 等来源的作者经验、源码实现、测试记录与本项目选用方式在对应资料中保留日期和范围。

## 历史桌面资料

`desktop/` 与历史 Release 保存过往桌面实现、构建说明和版本产物。当前日常使用采用上面的两套 Skill，旧桌面资料按对应标签和版本阅读。
