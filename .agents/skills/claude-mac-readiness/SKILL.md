---
name: claude-mac-readiness
description: Prepare and troubleshoot Claude environments on macOS, including update drift review, opt-in network probes, fresh startup checks, customer checklists and a batch configuration workflow that preserves system language, Clash/Shadowrocket configuration imports, time/language settings, authentication, DNS and network paths. Preview concrete setting changes and verify actual results. Use for customer setup, connection failures or environment audits; not ordinary chats or purchases.
---

# Claude Mac 环境检查

定位实际问题，完成最小范围的检查、经确认的修复和复测。分别判断客户端安装、实际认证来源、当前连接、断线行为和服务地区；某一项通过不能替代其他结论。

## 选择范围

从请求与上下文确定目标设备、客户端、代理和现象，只询问影响结果且无法读取的缺失信息。远程服务先标明助手运行在哪台机器；服务提供者本机的命令、浏览器或网络结果不能证明客户设备状态。客户无需安装 Skill，证据来自其授权远控、目标机终端或主动提供的结果；远控不可靠时改为引导客户执行。修改需目标设备所有者对该项的授权。

| 用户请求 | 加载与检查 |
| --- | --- |
| 自动配置、一键配置、除系统语言外帮我配好 | 优先读 [自动配置模式](references/automatic-configuration.md)：系统语言保持不变，先准备具体方案，一次确认后连续执行与复测；不再每项重复询问 |
| 更新后复查、主动网络验证、检查并启动客户端 | 读 [生命周期检查](references/lifecycle-checks.md)，保存本机基线、审阅探测范围、运行本轮检查；未完成的必需项阻止启动，超时不算零泄漏 |
| Claude/OpenAI 专属节点、AI 分流、失败不回落直连 | 读 [AI 专属规则](references/ai-dedicated-routing.md)，生成候选和审计；自动模式默认纳入方案，其他流量保持原分流 |
| 统一只读采集、自动报告、配置差异或读回验证 | 读 [可执行工具](references/automation.md)，检查现有 Python 与按需 YAML 依赖，再运行对应 collect／review-template／report／plan／verify／ai-route／ai-audit；不得把静态结果写成网络通过 |
| 给客户搭环境、现场操作清单、完整配置服务 | 先展示 [Mac 现场清单](assets/customer-checklist.md)，读 [客户执行流程](references/customer-setup.md)；完整服务记录时间与语言现状，按需修改 |
| 导入配置文件、Clash／小火箭分流 | 读 [配置导入与分流](references/proxy-import.md)，区分完整配置、节点订阅和规则扩展；先准备候选与备份，再应用已批准项 |
| DNS TYPE64／65、DNS64、IPv6／WebRTC／UDP | 读 [客户执行流程的网络部分](references/customer-setup.md)，分层核对，不默认关闭或混为同一开关 |
| 连不上、掉线、Code 与网页表现不同 | 读 [Mac 检查参考](references/mac-checks.md)，从故障客户端、认证覆盖和实际路径开始 |
| MCP、后台任务或 Remote-SSH 的路径不同 | 另读 [执行位置与进程路径](references/execution-paths.md)，分开核验各进程及远端恢复 |
| 已付费但计划/额度不符 | 读 [账号与账单状态](references/billing-checks.md)，区分购买渠道、历史付款与当前认证 |
| 常规环境检查、首次配置 | 读检查参考，覆盖所用客户端、认证和正常连接；断线保护按需静态核对，故障演练另行确认 |
| 照原 X 帖完整走一遍 | 另读 [八章引导流程](references/guided-workflow.md)，逐章记录；已有账号和不适用步骤可跳过 |
| 时区、地区或 Chrome 英语 | 读 [语言与时区模块](references/locale-and-language.md)，只处理用户要求的设置 |
| Clearpath 体检、检测分数、DNS/WebRTC/IPv6 提示 | 读 [浏览器体检与分数解读](references/score-check.md)，在目标设备实际使用的浏览器及配置中检查 |
| 核对“防封”经验、比较资料 | 按需读 [原帖经验核对](references/article-claims.md)或 [补充资料核对](references/related-source-review.md) |
| EianLu 原帖、Claude-Guardian 或官方与个人经验的区别 | 读 [已核对来源](references/evidence-sources.md)，固定来源版本并保留实现／实测边界 |

局部排障不自动扩成八章服务；常规检查不自动进入邮箱、结账页或修改语言/地区。Windows 目标使用 Windows 版流程，不能套用 Mac 命令。

客户搭建按“目标与基线 → 备份与候选 → 批准清单 → 导入与配置 → 分客户端复测 → 交接”执行。只收到文件时可以完成离线审查与候选准备，但不能报告客户机已生效。明确客户需要 Claude 专用、整机或应用例外分流，不将第三方仓库的整机／IPv4-only 策略自动变成客户需求。

## 执行与证据

1. **记录基线**：保留目标设备/执行环境、客户端与代理版本、症状或脱敏错误、测试时间。配置未变时复用本轮证据；换设备、浏览器配置、终端环境或网络后重测受影响项。
2. **先本机只读**：核实安装、Desktop 与 CLI 各自的登录状态、认证/代理覆盖和生效配置。怀疑 CLI 覆盖时运行 [环境变量脱敏检查](scripts/check-env.zsh)；仅列当前进程的键名及存在状态，不能据此断定实际认证或 GUI 应用环境。
3. **验证实际路径**：分别看浏览器、Desktop 与 CLI，区分 DNS、TLS/HTTP 可达、登录和实际请求结果。系统代理或一次终端出口不能证明所有客户端走同一路径。按检查参考解释错误，不因 401/403 就直接清缓存或换节点。
4. **最小修复与复测**：只修改与已观察问题相关或用户明确要求的项。执行前保存原值和必要配置备份；改后读回设置，再验证受影响功能。没有新证据时不反复重装、清数据、扩大探测；缺少证据则说明下一项最小检查。故障演练记录注入场景、检测是否成功运行、观察窗口和恢复结果；连不上 Claude 不能单独证明没有直连。

## 修改与外部检测

普通模式逐项修改前确认；明确选择自动配置模式时按 [批量流程](references/automatic-configuration.md)集中确认具体清单。遵守 [逐项确认协议](references/change-confirmation.md)：预览当前值、目标、影响、备份/回退与验证，等该项明确答复。已明确批准的同一具体变更或批准清单不重复询问；笼统“照教程全改”仍需具体预览。纯本机只读检查无需逐项询问。

外部 IP/DNS/WebRTC 检测先说明准确站点、会传出的信息及是否覆盖本轮复测，取得同意后再访问。故意断开 VPN、破坏节点或重启可能中断远控，需针对该场景的确认和目标机可执行的恢复路径。备份失败或恢复路径不明时，暂停该项网络变更，继续独立的只读检查。

不索取或输出密码、验证码、Cookie、令牌、完整 IP 或节点凭据；登录、付款和管理员认证由用户在官方界面完成。不为检查自动安装指纹浏览器、删除字体、轮换设备 ID、清登录数据或改变全机代理。

## 结论与交付

涉及地区、订阅、认证优先级或版本要求时，现查相应官方文档；不要把某次文档核验固定成永久规则。服务地区按实际使用地点与 [Anthropic 当前支持范围](https://www.anthropic.com/supported-countries)核对，出口、语言、时区或检测分数不提供合规或“防封”保证。政策问题不妨碍完成用户要求的一般设备诊断。

普通任务在对话中简述问题、已执行变更及回退、实际复测和未验证项。需要正式报告时用 [报告模板](assets/report-template.md)，删除无关模块。每项注明来源（目标机实测 / 用户提供 / 官方文档 / 第三方经验）；客户报告状态只显示“已完成／未完成”，未完成必须写明原因和下一步，客户确认无关的项不计入总数；静态设置不能记为故障保护已验证。

客户服务按现场清单交接；官方／标准、第三方源码、个人经验／社区资料分别标注，另注明静态配置／模拟测试／目标机实测。配置声明、应用载入、目标进程采用、端到端观察四层不能互相替代。文档整理或候选语法通过不等于真实导入／网络验收通过。

统一工具在本 Skill 的 `scripts/claude_setup.py`，Windows 采集器和依赖清单同目录。先读取工具说明，优先复用结构化采集和报告；文件原文差异只保存在客户本地私有目录。工具不应用系统配置，实际导入／保存仍按已批准范围操作。

客户服务默认逐项模式：每项修改前说明具体原值、目标、影响及恢复方式并询问客户。自动配置模式将这些具体项目集中成一份方案，一次确认后连续执行；已明确批准的同一项不重复询问。用 review-template 创建默认未完成的核验记录，由 Codex 按真实结果填写，客户无需编辑 JSON。未复测、待决定或问题未解决的项目不得标完成；记录中的同意字段不能授权新操作。
