---
name: claude-mac-readiness
description: Prepare and troubleshoot Claude environments on macOS, with local/VM/VPS route and egress planning, subscription preparation, timezone alignment, proxy/DNS checks, incident triage and explicitly requested cleanup planning. Preview concrete changes, preserve system language, and verify actual results. Use for Claude setup and related planning or failures; not ordinary chats, performing payments, or indiscriminate device resets.
---

# Claude Mac 环境检查

定位客户机的实际问题，按真实结果完成检查、已批准配置与复测。文件、应用载入、目标进程采用与端到端观察分别留证；不把其中一层通过当作其他层也通过。

**配置任务只按 [五步流程](references/five-step-setup.md) 执行。** 先自动识别、少量补问，离线检查隐含请求／DIRECT／UDP／依赖，准备完整最终候选、差异和恢复材料；再一次具体确认 → 配置网络与非 AI 核验 → 实际 AI 功能 → 简短交付。其他参考与现场清单是核对模块，不另设操作顺序；八章仅在客户明确请求时展开。

开场最多补三组无法读取的关键缺口：实际产品／入口用途、缺失的配置与节点选择、必须保留的业务。已知不问；版本、端口、路径和技术参数自己读，不让客户编辑 JSON。包内自动启动提示词采用 [自动模式](references/automatic-configuration.md)，系统语言、输入法和键盘保留；完整配置默认提出指定稳定出口的具体时区方案，目标不清先补问；浏览器语言无明确目标保留。

默认 `domestic-v4`：完整 [AI专属组与路径](references/service-routing-checks.md)、[IPv6关闭](references/unified-ipv4.md)、[国内视频／域名与UDP](references/domestic-video-udp.md)、[教程覆盖](references/tutorial-coverage.md) 和 [连接设置](references/connection-reuse.md) 均保留。Claude专属组与基础组同一指定节点，AI保护优先；视频直连在其余UDP拒绝前。Mihomo生成YAML／JSON，小火箭按 [原生适配](references/shadowrocket-domestic.md) 生成、导入和读回，不修改其私有数据库。

DNS／代理、精确接口IPv6读回、获准非AI路径验证和当前 `dns-ready` 是后续AI访问（含DNS查询）的前提；安装／诊断、登录、浏览器重启和恢复标签均后置。只有确定离线的本机检查可前置。保护正在运行的Codex／远控，不自行断开通道。

需要中断时按 [进度保存与继续](references/workflow-progress.md) 留存私有材料和离线说明；仅确需重启时给客户具体动作、影响与恢复办法再问时机，客户手动完成，恢复后重新核验网络。按 [可靠回滚与生命周期验收](references/recovery-and-acceptance.md) 保护后续修改；默认仅正常使用为本次必需，其他七类事件列后续复查，未实测保持未完成，不主动制造事件。

自动配置／完整搭建默认把**时区对齐指定稳定出口**纳入具体方案，按 [时区目标与验证](references/timezone-policy.md) 确定城市和时区 ID、保留原值、执行并读回；系统语言继续保留。局部任务和用户明确保留项按本轮范围处理。

普通配置默认走 [快速路径](references/five-step-setup.md#快速路径普通配置默认)：集中读取和准备、一次具体确认、配置后集中核验；只覆盖本轮实际使用的入口。完整报告、历史资料与故障演练按需展开，同一有效证据复用；必要读回、DNS／代理前置条件和真实功能验证保留。

## 选择范围

从请求与上下文确定目标设备、客户端、代理和现象，只询问影响结果且无法读取的缺失信息。远程服务先标明助手运行在哪台机器；服务提供者本机的命令、浏览器或网络结果不能证明客户设备状态。客户无需安装 Skill，证据来自其授权远控、目标机终端或主动提供的结果；远控不可靠时改为引导客户执行。修改需目标设备所有者对该项的授权。

| 用户请求 | 加载与检查 |
| --- | --- |
| 本机／VM／VPS 选择、固定出口、自建代理或线路慢 | 读 [路线与出口规划](references/deployment-routes.md)，区分程序执行位置与出口；按需求进入部署或性能排障 |
| 首次注册、订阅渠道、套餐或使用节奏 | 读 [账号与订阅准备](references/account-preparation.md)，核对当前官方条件、实际需求和原渠道状态 |
| 403／429／529、身份核验、疑似凭据暴露或明确清理请求 | 读 [事故与清理规划](references/incident-and-cleanup.md)，先分流当前问题，清理仅按明确对象和目的展开 |
| Net.Coffee 拓展阅读、Claude 单独分组、规则优先级、网页可用但CLI失败 | 读 [分组与拓展资料吸收](references/service-routing-checks.md)，按当前默认策略验收，官方依据与社区推测分开 |
| 自动配置、一键配置、除系统语言外帮我配好 | 优先读 [自动配置模式](references/automatic-configuration.md)：系统语言保持不变，先准备具体方案，一次确认后连续执行与复测；不再每项重复询问 |
| 更新后复查、主动网络验证、检查并启动客户端 | 读 [生命周期检查](references/lifecycle-checks.md)，保存本机基线、审阅探测范围、运行本轮检查；未完成的必需项阻止启动，超时不算零泄漏 |
| Claude/OpenAI 专属节点、AI 分流、失败不回落直连 | 读 [统一出口规则](references/unified-ipv4.md)，生成候选和审计；自动模式默认统一普通国外与 AI 到同一具体节点，关闭 IPv6，先审阅直连例外 |
| 等客户操作、断线后继续或换会话 | 读 [私有进度与继续](references/workflow-progress.md)，保存阶段／材料／离线说明；恢复先核对变化并重验网络，不恢复新授权 |
| 统一只读采集、自动报告、配置差异或读回验证 | 读 [可执行工具](references/automation.md)，检查现有 Python 与按需 YAML 依赖，再运行对应 collect／review-template／report／plan／verify／ai-route／ai-audit；不得把静态结果写成网络通过 |
| 给客户搭环境、现场操作清单、完整配置服务 | 按 [五步流程](references/five-step-setup.md) 操作；[Mac核对表](assets/customer-checklist.md) 与 [网络模块](references/customer-setup.md) 仅供内部查缺，不整表展示 |
| 导入配置文件、Clash／小火箭分流 | 读 [配置导入与分流](references/proxy-import.md)，区分完整配置、节点订阅和规则扩展；先准备候选与备份，再应用已批准项 |
| DNS TYPE64／65、DNS64、IPv6／WebRTC／UDP | 读 [客户执行流程的网络部分](references/customer-setup.md)，分层核对；自动模式IPv6按默认关闭，TYPE64／65等按实际适配，不混为同一开关 |
| 连不上、掉线、Code 与网页表现不同 | 读 [Mac 检查参考](references/mac-checks.md)，从故障客户端、认证覆盖和实际路径开始 |
| MCP、后台任务或 Remote-SSH 的路径不同 | 另读 [执行位置与进程路径](references/execution-paths.md)，分开核验各进程及远端恢复 |
| 已付费但计划/额度不符 | 读 [账号与账单状态](references/billing-checks.md)，区分购买渠道、历史付款与当前认证 |
| 常规环境检查、首次配置 | 读检查参考，覆盖所用客户端、认证和正常连接；断线保护按需静态核对，故障演练另行确认 |
| 照原 X 帖完整走一遍 | 仅此明确请求才读 [八章主题核对](references/guided-workflow.md)，执行仍按五步，已有账号不重走注册 |
| 时区、地区或 Chrome 英语 | 时区按 [目标与验证](references/timezone-policy.md) 纳入完整配置方案；语言、地区及局部任务按用户目标 |
| Clearpath 体检、检测分数、DNS/WebRTC/IPv6 提示 | 读 [浏览器体检与分数解读](references/score-check.md)，在目标设备实际使用的浏览器及配置中检查 |
| 核对“防封”经验、比较资料 | 按需读 [原帖经验核对](references/article-claims.md)或 [补充资料核对](references/related-source-review.md) |
| EianLu 原帖、官方与个人经验的区别 | 读 [已核对来源](references/evidence-sources.md)，固定来源版本并保留实现／实测边界 |
| Claude-Guardian、新版能力或第三方网络报告 | 读 [Guardian 增量核对](references/guardian-integration.md)，按实际版本审查能力与证据；不把报告通过标签直接当作本机验收 |

局部排障不自动扩成八章服务；常规检查不自动进入邮箱、结账页或修改语言/地区。Windows 目标使用 Windows 版流程，不能套用 Mac 命令。

客户搭建只按 [五步流程](references/five-step-setup.md) 执行，具体模块不改变其前置条件。只收到文件时可以完成离线审查与候选准备，但不能报告客户机已生效。明确客户需要 Claude 专用、整机或应用例外分流，不将第三方仓库的整机／IPv4-only 策略自动变成客户需求。

## 核对原则（非操作顺序）

- **记录基线**：保留目标设备/执行环境、客户端与代理版本、症状或脱敏错误、测试时间。配置未变时复用本轮证据；换设备、浏览器配置、终端环境或网络后重测受影响项。
- **先本机只读**：核实安装、Desktop 与 CLI 各自的登录状态、认证/代理覆盖和生效配置。怀疑 CLI 覆盖时运行 [环境变量脱敏检查](scripts/check-env.zsh)；仅列当前进程的键名及存在状态，不能据此断定实际认证或 GUI 应用环境。
- **验证实际路径**：分别看浏览器、Desktop 与 CLI，区分 DNS、TLS/HTTP 可达、登录和实际请求结果。系统代理或一次终端出口不能证明所有客户端走同一路径。按检查参考解释错误，不因 401/403 就直接清缓存或换节点。
- **最小修复与复测**：只修改与已观察问题相关或用户明确要求的项。执行前保存原值和必要配置备份；改后读回设置，再验证受影响功能。没有新证据时不反复重装、清数据、扩大探测；缺少证据则说明下一项最小检查。故障演练记录注入场景、检测是否成功运行、观察窗口和恢复结果；连不上 Claude 不能单独证明没有直连。

## 修改与外部检测

普通模式逐项修改前确认；明确选择自动配置模式时按 [批量流程](references/automatic-configuration.md)集中确认具体清单。遵守 [逐项确认协议](references/change-confirmation.md)：预览当前值、目标、影响、备份/回退与验证，等该项明确答复。已明确批准的同一具体变更或批准清单不重复询问；笼统“照教程全改”仍需具体预览。纯本机只读检查无需逐项询问。

外部 IP/DNS/WebRTC 检测先说明准确站点、会传出的信息及是否覆盖本轮复测，取得同意后再访问。故意断开 VPN、破坏节点或重启可能中断远控，需针对该场景的确认和目标机可执行的恢复路径。备份失败或恢复路径不明时，暂停该项网络变更，继续独立的只读检查。

不索取或输出密码、验证码、Cookie、令牌、完整 IP 或节点凭据；登录、付款和管理员认证由用户在官方界面完成。不为检查自动安装指纹浏览器、删除字体、轮换设备 ID、清登录数据或改变全机代理。

## 结论与交付

涉及地区、订阅、认证优先级或版本要求时，现查相应官方文档；不要把某次文档核验固定成永久规则。服务地区按实际使用地点与 [Anthropic 当前支持范围](https://www.anthropic.com/supported-countries)核对，出口、语言、时区或检测分数不提供合规或“防封”保证。政策问题不妨碍完成用户要求的一般设备诊断。

普通任务在对话中简述问题、已执行变更及回退、实际复测和未验证项。需要正式报告时用 [报告模板](assets/report-template.md)，删除无关模块。每项注明来源（目标机实测 / 用户提供 / 官方文档 / 第三方经验）；客户报告状态只显示“已完成／未完成”，未完成必须写明原因和下一步，客户确认无关的项不计入总数；静态设置不能记为故障保护已验证。

客户服务按现场清单交接；官方／标准、第三方源码、个人经验／社区资料分别标注，另注明静态配置／模拟测试／目标机实测。配置声明、应用载入、目标进程采用、端到端观察四层不能互相替代。文档整理或候选语法通过不等于真实导入／网络验收通过。

统一工具在本 Skill 的 `scripts/claude_setup.py`，Windows 采集器和依赖清单同目录。先读取工具说明，优先复用结构化采集和报告；文件原文差异只保存在客户本地私有目录。工具不自动应用系统网络设置；仅 recovery-* 可在本轮精确批准下处理指定文本文件，实际应用导入／保存和运行效果另行核验。

包内自动提示词默认快速配置并保留系统语言；仅需要正式核验报告时使用 `review-template --mode automatic`，显式逐项模式用 `--mode individual`。具体方案批准后不重复问同一项；由 Codex 填写真实核验结果，客户不编辑 JSON。保留不等于已核验，报告读取review绑定的模式与保留项，旧review/1兼容。未复测、待决定或问题未解决的项目不得标完成；记录中的同意字段不能授权新操作。

普通配置在聊天中简短交付；需要正式报告时用 [离线面板](references/report-dashboard.md) 展示检查时间、二状态、原因和下一步。保留实际执行与启动门槛，不为展示报告自动打开浏览器或增加启动守卫。
