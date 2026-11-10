# Claude-Guardian：流程、实际能力与证据的深入复核

研究日期：2026-11-10。当前公开 main：`e934166adbdbd582f169b1b14adb7be76aa90a77`（2026-11-09，`fix:remove high policy`），与先前归档版本一致。

本轮通过 GitHub API 读取当前提交、完整树和 CI 状态，本地235个源文件逐一匹配固定 Git blob；语义复核聚焦入口、网络、清理、恢复和直接相关实现／测试，全文与选段分别列在各专项末尾。哈希校验不算重新读完全部正文；本轮没有运行上游脚本、测试、探针，没有访问 Claude 服务或读取本机实际账号／浏览器数据。

## 核心判断

Guardian 的价值在于让 Agent 根据任务选择路线、复用事实、准备具体差异、按能力执行、遇到部分失败先对账，并保留离线恢复；它包含实际脚本，但跨平台的全自动覆盖仍需逐项核实。[编排闭环](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/agent-remediation.md#L5-L29)

| 该学的方法 | 我们的采用方式 | 保留的边界 |
| --- | --- | --- |
| 按任务动态提问、复用一轮中的多个事实 | 简短入口先确定阶段／系统／目标，只有路线未定且影响方案时才比较 | 清理、事故和纯解释不强迫走购买问卷；未知／拒答不视为接受 |
| 具体计划集中批准、关键动作单列 | 沿用现有有效批准，不逐开关重复问 | 其结构化授权记录不鉴别人或替代实际宿主权限 |
| 区分文件写入、应用载入、进程采用、实际功能 | 保留在五步必要验收中 | 单次网络请求和UI绿灯不填满其他层 |
| 隔离、独立备份、prepared日志、恢复前对账 | 清理／恢复模块按任务读取 | 部分失败后先查现状，不覆盖后续新数据；本包未新增其执行器 |
| 独立救援、限时保险丝、确认后持久化 | 作为持续防护的条件化方法 | 具体源脚本存在下面的实现差距，未独立实测，不承诺完整恢复 |

## 本轮必须分清的事实

1. **称呼是我们的自定义。**当前公开 `SKILL.md` 没有“队长”或逐句称呼要求；211份UTF-8文本检索也未命中。无法从当前仓库判断截图对话的个性化称呼来自哪里，我们的“每句老大”按用户明确偏好保留，不能说是上游当前规则。[交流规则](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/SKILL.md#L10-L20)
2. **IPv6默认存在平台差异。**Guardian 默认 Windows 关闭实际物理网卡IPv6；Mac／Linux主要限制代理核心和TUN，系统网卡默认保留。我们精确接口关闭、国内／视频DIRECT、其余UDP拒绝的 `domestic-v4` 是既有用户选择，与他的整机UDP统一转发不同，不能互相归因或混成一套。[原策略](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/agent-remediation.md#L42-L62)
3. **自动写规则的准入很窄。**实际原生适配器只开放 Mac＋Clash Verge Rev 2.5.8 的 `rules-prepend`；其他产品、版本、系统及 `merge-policy` 不自动开放。写入返回 `written_but_not_verified`，应用重载及实际路由仍未运行。[准入](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/native_clash_verge_mac.py#L1-L15)、[写入结果](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/repair_execution.py#L214-L220)
4. **盘点只采有限元数据。**`guardian.py check` 可读取OS、语言／时区、默认代理摘要等，但不自动发现全部客户端、进程、代理端点／例外和真实路径；当前native入口只接纳本机角色。VM／VPS入口声明不等于自动远端适配器。[当前采集](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/guardian.py#L804-L855)、[角色边界](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/host-libraries.md#L128-L132)
5. **C5是有边界的隔离。**POSIX、16根／4096项／64MiB／深度32；Mac原生宿主存在，但不强制互斥、可能漏Node CLI，结果仍标真机未验收。浏览器数据库、钥匙串和卸载不属于C5；独立Keychain功能确实会删除整项。[范围与实现](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/cleanup_transactions.py#L38-L43)、[Mac限制](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/native_cleanup_mac.py#L20-L32)、[钥匙串动作](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/native_claude_state_mac.py#L88-L181)
6. **账号效果仍按经验保存。**3／15天、并发1–3、封超过3号换设备、苹果内购更稳等，不能当官方门槛或已证因果；作者本身也补有iOS KYC升级反例。我们现有默认／可选／未验证／纠正分类继续适用。[经验与反例](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/account-onboarding.md#L1-L53)

## 具体不足与验证状态

| 发现 | 源码支持的判断 | 尚未验证的部分 |
| --- | --- | --- |
| IPv6请求错误被记pass／unreachable；STUN超时被概括为blocked | 检查失败的标签不能证明协议已阻断，须保留原因和其他层证据 | 没有在真实目标上复现不同错误分支 |
| 一次IPv4 HTTPS故障演练推导no_direct | 缺故障期DNS／IPv6／UDP及真实停核证明 | 不能据此断言真实设备必然泄漏或已全机保护 |
| Mac PF先载入／启用并写日志，最后启动保险丝 | 中间失败路径可能没有已启动的独立撤销；这是代码顺序的静态推论 | 没有进行中断或断网试验 |
| Linux VM／VPS初装先enable开机项；超时只删runtime表 | 未确认的持久状态可能仍在，重启可能重新载入；与后来Switch路径区分 | 没有在客机／服务器重启复现 |
| C5备份阶段枚举限额与后续事务预算不同 | 不能认为备份前已按64MiB／4096项预限 | 没有用真实用户资料测量资源占用 |
| 部分入口测试只构造输入或断言夹具 | 测试名称／通过数量不能代替有效行为覆盖 | 这不自动证明对应源码机制失效；本轮未运行测试 |

以上具体固定行号、原方法和恢复分支见下方专项。多数检测边界此前归档已记录；本轮新明确的是保险丝启动前窗口、初装持久回滚差距、备份阶段预算区别和若干测试断言不足，不能把旧发现包装成版本更新。

## CI与真实设备证据

GitHub当前提交的 [CI run 42578646836](https://github.com/DUNHKpcc/Claude-Guardian/actions/runs/42578646836) 为success；实际完成的是scope和ubuntu测试，Python 3.10任务跳过。工作流对文档更新只跑Linux，其Mac／Windows smoke也明确只是元数据检查，不能当桌面、代理／权限、真实浏览器及断线保护验收。[工作流](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/.github/workflows/tests.yml#L10-L40)、[原生smoke边界](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/.github/workflows/tests.yml#L76-L79)

原生Clash适配测试把平台、进程列表与目录替换为夹具；它可验证代码路径和失败状态，不是目标机独立测量。作者另有单台Mac的写入／回滚与PF样本陈述，按设备、版本和事件保留，不扩大成任意Mac／Windows已通过。[测试夹具](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/tests/test_native_clash_verge_mac.py#L1-L29)、[作者限定真机范围](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/host-libraries.md#L13-L15)

## 对我们流程的结论

保留现有精简入口与按需模块；已吸收的动态分流、具体方案、分层验收与恢复不再重复追加。新增风险留在研究归档，若将来实现持续防护，单独验证保险丝先于有影响的动作、确认后才持久化，并分别恢复运行时与开机状态。上游经验的表达语气不改变证据级别。

研究阶段仅生成本报告，没有执行上游代码或环境操作。后续文档改动已将动态分流、探针错误保留和持续防护恢复范围纳入两平台Skill；新增静态风险留在来源归档。运行实现与默认网络策略未改，未更新共享记忆。

## 专项详细记录

以下保留研究阶段三个专项的原始结论、引用和实际阅读边界；其中“未修改／未推送”描述当时的研究阶段，后续文档应用见上节，按需展开。


### Guardian 当前入口、称呼与批准流程复核

核对日期：2026-11-10。GitHub API `commits/main` 返回固定提交 **e934166adbdbd582f169b1b14adb7be76aa90a77**，提交时间 2026-11-09T07:19:43Z，说明 `fix:remove high policy`。本轮未执行任何上游脚本、测试、采集或环境操作。

#### 当前称呼规则：公开仓库没有“队长”或逐句称呼要求

- 最新 `SKILL.md` 的交流规则为简短说明动作、观察与下一步，按主题提供资料，避免把执行门禁念成台词；**没有要求称呼“队长”，也没有要求每句、每条回复或首次回复加称呼**。[入口交流规则](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/SKILL.md#L10-L20)
- 对固定树 235 个 blob 全部核对 Git blob SHA，211 份可解码 UTF-8 文本机械搜索“队长／老大”，零命中。这个搜索只支持文本规则未出现，不称作本轮重新语义阅读全仓，也无法解释截图对话里称呼来自哪个用户指令、个性化设置或其他版本。
- 我方两平台 `SKILL.md` 第8行的“每句以老大开头”是本次用户明确选择的自定义风格；应保留为我方偏好，不能归因成照搬了上游现行规则。刚加入的阶段／系统／目标、路线比较后再检查，则与上游真实流程一致。

#### 真正值得吸收的是按任务变化的分流

1. 普通订阅准备从首次／到期重订／已有订阅开始，再补系统与用途；清理直接处理目标及保护范围，紧急事故优先，已有答案复用。它没有要求所有任务都先走支付问卷。[开场分流](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/SKILL.md#L24-L31)
2. 本机仅是建议，用户明确接受或已经指定的任务目标才形成选择；有 VPS 不意味着程序运行在 VPS，单纯用 VPS 当出口仍可属于本机／VM 路线。比较、拒绝、撤回或冲突时停在解释，不能偷偷选本机。[环境入口](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/SKILL.md#L34-L42)
3. 一轮一个主要决策，只补当前缺口；相关少量问题可合并。未知、拒答和延期停止自动追问，不能当作默认接受。暂停、覆盖、条件方案与事故优先有独立状态。[访谈规范](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/intake.md#L1-L17)、[问题调度实现](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/interview_flow.py#L1552-L1805)
4. 我方已收进简短入口的“复用事实、需要时选路线、只比较不操作”足够承接该优点；不需要重新把整套问题 ID、每轮必附表、三套 G 标签复制到默认入口。

#### 文档之外有哪些实际实现

| 项目 | 实现能支持的结论 | 仍由宿主／Agent负责 |
| --- | --- | --- |
| 入口判定 | `assess_entry`／`require_entry` 为纯输入判定；路线未选时不开放目标检查，主客机别名和角色分别约束，VPS只给基础非侵入范围 | 用户真实选择、真实设备绑定、具体权限和原生观察 |
| 访谈 | `applicable_questions` 按清理、事故、账单、升级和路线分支；`next_question` 选一个相关未答题，限制澄清次数 | 把自然语言真实含义归一化成事实，脚本没有自然语言理解器 |
| 资料比较 | `interview_cli --references-only` 可只路由资料，输出 `action_executed=false`、`saved=false` | 真的阅读材料并给有依据的解释 |
| 方案／动作 | `assessment` 分开G1覆盖和G2信息就绪，G3明确保持blocked | 独立动作／接触门槛及真实执行 |

依据：[完整入口实现](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/environment_entry.py#L1-L291)、[访谈评估](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/interview_flow.py#L2017-L2119)、[CLI纯资料与输出](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/interview_cli.py#L60-L145)。

#### 批准并非每个开关重复问

- A 档在确认范围内连续只读／研究；B 档整份可撤销且不切断访问的计划批准一次；C 档在关键点确认，账号／支付／敏感认证由本人处理。[档位定义](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/authorization-tiers.md#L6-L78)
- 代码分别记录范围、B计划、C确认；C确认一次使用，用户来源标签有格式校验，换路线或真正resume使旧记录陈旧。普通序列化读回不是实际中断。[实现](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/interview_flow.py#L2345-L2525)、[对应离线测试](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/tests/test_interview_authorization.py#L182-L253)。
- 这些是可信宿主下的结构化追溯，`user:`字符串本身不鉴别人，也不执行动作；其G3保持关闭。我方沿用会话中已有具体授权的规则属于本项目选择，不应重新引入无变化就重复审批的流程。

#### 两处研究时必须保留的警惕

**交流风格不应改变证据级别。**上游要求参考经验直接按事实说且不加“可能／据说”，也禁止大量限制句式；我们可以吸收简短、给下一步的表达，仍需明确来源经验与实测结果，尤其账号因果和历史阈值。[上游原规则](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/SKILL.md#L14-L20)

**测试名称不能代替测试内容。**本轮全文读了 `test_environment_entry.py`，发现以下覆盖不足，未运行测试：

- `test_direct_is_a_terminal_kind_not_a_proxy_protocol` 构造冲突、调用判定，但没有断言冲突被拒；随后又替换输入。[118–124行](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/tests/test_environment_entry.py#L118-L124)
- `test_http_and_mixed_can_lead_to_final_socks5_proxy` 只断言夹具中的协议字符串，未调用入口判定器核实组合。[205–210行](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/tests/test_environment_entry.py#L205-L210)
- `test_tun_path_does_not_mistake_unused_listener_for_code_configuration` 仅构造输入，没有调用或断言。[221–225行](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/tests/test_environment_entry.py#L221-L225)
- `test_existing_aliases_need_no_new_prefix` 仅赋值别名，没有送入校验器。[354–360行](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/tests/test_environment_entry.py#L354-L360)

对应源码确实存在路线、协议与别名限制，以上发现只削弱这些用例所声称的覆盖强度，不直接推出产品机制失效。另有实质断言的用例覆盖比较／未知路线不准检查、主客机范围、缺资源仅离线预检、撤回后不能复用资格与纯函数无I/O；这些仍只是合成测试源码，本轮没有运行或真机验证。

#### 本轮实际阅读与未读边界

- 全文分段阅读：`SKILL.md` 201行、`references/intake.md` 298行、`references/routes-and-platforms.md` 262行、`references/authorization-tiers.md` 102行、`references/contact-and-safety.md` 39行、`scripts/environment_entry.py` 291行、`scripts/interview_cli.py` 165行、`tests/test_environment_entry.py` 402行、`tests/test_interview_authorization.py` 258行、`tests/test_route_withdrawal.py` 274行；以及我方两平台当前 `SKILL.md`。
- 选段阅读：`scripts/interview_flow.py` 的1552–1808行（任务调度／提问）、1870–2120行（主题资料／评估）、2320–2535行（批准记录与判定）；其他段本轮仅定位搜索，不算全文读。
- 元数据核对：18份下载／复用文件与当前固定树 Git blob SHA 一致；旧快照235个blob全部匹配当前树。211文本零称呼命中的机械检查不等于重新读全仓。
- `README.md`、其余访谈测试等虽已下载或定位，本轮没有全文阅读，不列入本轮阅读完成数。网络／清理的实际实现及历史验收由主研究分支另核；本报告只覆盖入口、交互、路线和批准。
- 本轮只读取公开GitHub和本地源码材料、写本临时报告；未运行上游代码或测试，未访问Claude服务，未接触个人环境数据，没有修改我方Skill、推送或发布。


### Guardian 网络与恢复：固定版本复核

日期：2026-11-10。固定提交：`e934166adbdbd582f169b1b14adb7be76aa90a77`。GitHub API 获取该 commit 的 recursive tree 后，以 Git blob SHA1 对照本地原始快照；全文复读的 19 个文本文件均匹配。研究过程只读取源码、文档和测试及公开 Issue，不执行上游代码、测试、探针、PF／防火墙或系统网络命令。

#### 结论

他的强项是把路线、目标设备、实际运行配置、网络路径、故障恢复和真实使用入口串成闭环，尤其保留了 Windows 两台设备的相反 DNS 修复案例、桌面入口测试失真事故和 Mac PF 的历史边界。适合学操作与证据结构，不能直接继承其绿灯语义或把作者目标当成我们的默认。

这次没有新版本差异；我方归档已明确写出不少关键限制，不能把这些旧发现冒充今天才发现。新增值得补充的是 Mac PF 启动保险丝前的中断窗口，以及 Linux VM／VPS 初次安装的保险丝未撤销开机状态；下面明确区分代码事实与静态推论。

#### 1. IPv6 的实际范围与两套默认

- Guardian 当前默认是整机普通应用／子进程／后台的 TCP、UDP、DNS 统一同一 IPv4 出口；DIRECT 例外必须列清，允许用户明确选择仅 Claude 的窄范围。[当前策略](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/agent-remediation.md#L42-L50)
- 作者对 Windows 默认关闭实际物理网卡的 `ms_tcpip6`；macOS／Linux 先在核心和 TUN 层限制，系统接口不动；Mac 系统关闭只作可选，未关只产生 advisory。这不是“所有平台都必须系统级关闭 IPv6”。[策略与网卡](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/agent-remediation.md#L45-L62)、[Mac 可选与判定](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/whole-machine-ipv4.md#L45-L53)
- 核心 `ipv6:false`、DNS IPv6 off、IPv6 REJECT 与末尾代理兜底、节点外层 IPv4、TUN／strict-route、系统接口和实际探测是不同层。作者也明确 AAAA 空或超时不能单独证明阻断。[分层解释](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/network-and-remedies.md#L24-L35)
- 我们的 `domestic-v4` 保留国内／视频 DIRECT 并拒绝其余 UDP、要求精确选定接口 IPv6 关闭；与 Guardian 的整机 UDP 转发和 Mac 可选系统关闭不同。这是已明确保存的用户默认，现有 `unified-ipv4.md` 和来源归档有区分，不能说成“按他的方案就必须这样”。

#### 2. 检测器真正证明到哪里

| 实现事实 | 能支持的结论与限制 |
| --- | --- |
| `network_check.py` 真实发起中性 HTTPS、DNS 相关域名连接、IPv4 STUN 与可选交互演练 | 它不是单纯 metadata 检查；不过依赖特定站点、一次地址族请求与采样窗口，不能证明全时间、全进程、全目标 |
| IPv6 发生 OSError、HTTP 错误、坏 JSON 等时都返回 pass／unreachable | **不能把“检测失败”显示成“IPv6 已堵住”直接吸收。**应另保留失败原因、接口／规则证据和对照；当前测试确实固定了 OSError → unreachable 的行为 |
| UDP 两次 STUN timeout 后为 warn／blocked，摘要说“不通但不会漏” | 只证明这两次没收到有效回复；不能推出全部 UDP 被阻断。原网络文档本身要求 timeout inconclusive，这里存在文案／实现收敛不足 |
| 演练由用户按回车，停核期一次 IPv4 中性 HTTPS error、恢复后 pass 即给 no_direct | 代码没有独立确认核心已停，也没在故障期测 DNS／IPv6／UDP。应学前中后三阶段，不能用该标签代替完整故障证据 |
| 同一 Python 程序经显式代理的出口样本导出成 `other_app` | 不能冒充真实 Desktop／CLI／后台进程已采用代理；判定器只要求至少两种 process 标签，未验证标签的来源 |
| `egress_verifier.py` 只读供给 JSON，不采集；firewall、os_ipv6 只作 advisory | `established` 不等于系统防火墙已有效、接口已关或全部场景已验收；persistence 只检查三种名称是否被填入，不自动触发事件或核其时间证据 |

代码依据：[IPv6](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/network_check.py#L149-L158)、[STUN 与演练](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/network_check.py#L216-L266)、[样本导出](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/network_check.py#L303-L323)、[摘要](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/network_check.py#L343-L363)、[判定器](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/egress_verifier.py#L107-L161)。测试是 mock／供给观测：[network tests](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/tests/test_network_check.py#L1-L17)、[egress tests](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/tests/test_egress_verifier.py#L1-L26)，此次只阅读，未运行。

以上检测限制已在我们归档 `source-methods-guardian-network.md` 的 3.3 节大体明确；当前精简五步与 `unified-ipv4.md` 继续要求实际状态，未直接拿它们的 pass 作本机通过。

#### 3. Mac PF：方法有价值，恢复不应过度承诺

可吸收的部署链：先 TUN／出口正常 → 明确物理接口、节点真实 IPv4 与端口、DHCP、必要 bootstrap DNS／LAN 例外 → render 审阅 → apply → 正常透明 TUN／域名／显式代理核验 → confirm → 故障期新连接验证 → persist。PF 对物理接口而非进程拦截，utun／lo 不纳入物理阻断；不改 `/etc/pf.conf` 正文，缺主 anchor 时会加载系统规则集，后者仍是系统级变更。[规则生成](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/mac-killswitch/guardian-pf-killswitch.sh#L159-L171)、[apply／持久化](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/mac-killswitch/guardian-pf-killswitch.sh#L289-L403)

维护边界：脚本不保证规则早于任何联网加载，没有换网监控或新接口自动补齐；节点／接口变更需要人工重新 apply／confirm。当前 `status` 的新网卡警告只筛有 IPv4 地址的非 lo／utun 接口，不能靠它证明全部地址族接口覆盖。[boot／status](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/mac-killswitch/guardian-pf-killswitch.sh#L416-L447)、[当前文档承认的边界](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/local-firewall-prompts.md#L88-L100)

**新增静态风险，未实测复现：**apply 的实际顺序是先载入 PF 规则（335）、启用 PF（336）、写日志（337），最后才启动独立保险丝（338）；`set -e` 下中间失败没有 trap 负责回滚，因此不能承诺每条部分执行／中断路径都已有有效保险丝。源码事实明确，真实目标的故障概率与具体结果未验证。[代码](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/mac-killswitch/guardian-pf-killswitch.sh#L323-L341)

验证证据分层：当前指南称 2026-11-09 PF 全项已验收，同时明确该日未新增自动测量；公开 [Issue #25](https://github.com/DUNHKpcc/Claude-Guardian/issues/25) 的具体样本覆盖 render/apply/confirm/停核/persist，并报告 locale 崩溃修正版及 DNS／管理链路约束；它没有给出所有开机前窗口、新网卡、睡眠与换网的逐项测量。项目接受状态、历史报告与每个目标机的新验收不能合并。PF 测试文件主要运行离线 render／DNS fixture 以及文案断言，文件头明确真实 apply／保险丝／持久化／演练需设备检查。[验收说明](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/local-firewall-prompts.md#L119-L141)、[测试边界](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/tests/test_mac_pf_killswitch.py#L1-L5)、[文案同步断言](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/tests/test_mac_pf_killswitch.py#L202-L228)。

#### 4. Windows：先部署，开关只管已有规则

首次本机部署主要是提示词：TUN 先通 → 备份原规则／原默认动作 → 独立保险丝 → 精确 core 到节点、TUN、DHCP、回环／管理例外 → 三档默认 Block → 正常与停核验证；要查 ActiveStore、所有 Profile 和原有宽 Allow，不能只看 guardian-* 存在。S10 第一台曾用物理 53 Block 修 DNS 直连，第二台发现它拦核心上游 DNS而撤掉，不能拼成统一配方。[首次部署](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/local-firewall-prompts.md#L154-L179)、[S10 相反分支](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/S10-windows-deployment-sanitized.md#L174-L188)

Switch 已实现真实 PowerShell 后端，不是首次规则生成器；精确 Name 列表、设备绑定、私有 OFF 基线，ON 先注册 SYSTEM 180秒恢复任务再改策略，读回 ActiveStore；OFF 只恢复它拥有的字段和规则状态。与旧提示词整体恢复／删 guardian-* 区分。[后端](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/killswitch/windows-switch.ps1#L20-L60)、[保险丝与提交](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/killswitch/windows-switch.ps1#L67-L116)

有价值的交付经验：真实双击入口 → UAC → 三档真实状态 → 联网／阻断行为，不能用 SSH／SYSTEM／带 Bypass 的调试命令通过代替用户入口通过。S10 自己也保留了该事故及修复后尚未真实切换防火墙的缺口。[事故](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/S10-windows-deployment-sanitized.md#L220-L255)

#### 5. VM／VPS：角色与持久状态分别研究

- Linux VM 的 inet INPUT／OUTPUT drop、lo／TUN／已建连接、节点 IPv4／端口、DHCP 与限定 LAN 管理例外是真实现；`ct established` 被放行，故障验收应使用新连接，不能把已有连接是否存活当全部策略结论。[nft 规则](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/vm-killswitch/install-flclash-killswitch.sh#L125-L158)
- 自动刷新固定从家目录的安装脚本运行，首次参数 LAN_NET／NIC 等没有自动写入 refresh.service；timer、路径、用户 sudo 能力和参数持久化必须补齐。我们归档已保存这一点。[unit／timer](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/vm-killswitch/install-flclash-killswitch.sh#L209-L243)
- **新增静态推论，未实测：**VM installer 先启用开机 unit，再 apply；保险丝超时只删运行时表，未删除持久规则或 disable unit。未 confirm 的安装超时后若重启，仍可能再次加载未确认规则。VPS guard 也先 enable 再 apply，保险丝只删表，有相同状态差距。不能把其“保险丝恢复”理解为完整撤回持久配置。[VM](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/vm-killswitch/install-flclash-killswitch.sh#L168-L183)、[VM enable](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/vm-killswitch/install-flclash-killswitch.sh#L238-L246)、[VPS](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/vps-firewall/vps-guard.sh#L67-L108)
- 后来的 Linux Switch ON 路径另有改进：先 systemd-run 创建独立恢复任务，成功 KEEP 后才 enable 持久单元，异常走 OFF。这不能反向证明旧初装脚本也已修复。[Switch ON](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/killswitch.py#L170-L208)
- VPS 开发机、VPS 代理中转和 VPS 自己作公网出口要区分。`vps-guard` 只有 INPUT drop，出站不受限，因此是入站加固，不能当出站 kill switch；VPS 上实际套 FlClash TUN 时才走 Linux 出站后端。[实际规则](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/vps-firewall/vps-guard.sh#L48-L63)、[角色分流](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/vps-guidance.md#L1-L13)
- VM 作者偏好桥接、Omarchy／Mac 客机，VPS 资源预算、控制通道保护、临时浏览器回环监听与 SSH 转发有具体方法；这些是条件化选型与管理手段，不变成每个现有 Mac 配置任务的前置。VM 参数化脚本和 VPS guard 文档均保留未在真实客机／服务器完整实测边界。[VM](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/vm-guidance.md#L1-L18)、[VPS 资源与浏览器](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/vps-guidance.md#L57-L84)、[VPS 未实测](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/vps-guidance.md#L92-L100)

#### 建议我方如何处理

1. 继续保留简短任务入口和按需模块；不为吸收 Guardian 而重建重复访谈、要求全量报告或把一次普通配置升级成全生命周期故障试验。
2. 已有归档对检测器、IPv6 多层、Mac／Windows默认、S10冲突、VPS角色的记录基本准确；无需重复添加同一清单。
3. 只在研究归档补上新增的保险丝启动窗口、Linux初装持久状态回滚差距，标“静态代码推论／未目标机复现”。若将来实现相应功能，必须让保险丝先于破坏性动作、确认后才持久化，恢复运行时与持久状态分别对账。
4. 不把官网／文案全绿作为唯一结论。当前作者“除语言全绿”的浏览器规则和风险分／换出口建议是其产品验收口径，不能推出官方认可或免封概率。

#### 实际阅读边界

本轮全文复读并按 Git blob 核验：8份引用文档（network-and-remedies、local-firewall-prompts、whole-machine-ipv4、vm-guidance、vps-guidance、killswitch-switch、local-advanced-route、agent-remediation）；3份脚本（network_check、egress_verifier、killswitch）；4份资产实现（Mac PF、Linux VM killswitch、VPS guard、Windows Switch）；3份对应测试（network_check、egress_verifier、Mac PF）；S10 Windows全文；另读取公开 Issue #25 原始正文并确认没有评论。实际文件／行数另有本次临时阅读记录。

未在本轮重读所有235文件、19份PDF或全部图像，也未复核所有历史PF测量原始包；这些范围复用此前固定版本记录，不作本轮新增全文担保。未执行上游测试，未独立复现任何真实设备效果。仅研究不修改上游或我方运行实现。


### Guardian 清理、离线恢复与账号经验：只读复核

研究日期：2026-11-10。固定提交 `e934166adbdbd582f169b1b14adb7be76aa90a77`，与此前研究版相同。本轮先通过 GitHub recursive tree 校验 27 个相关 blob，再补核 `transactions.py`、`native_claude_state_mac.py`；本地正文匹配 Git blob SHA。没有导入、运行任何上游模块、测试、探针、清理或账户操作，也没有读取本机实际浏览器/Claude数据。

#### 实际值得吸收的工程方法

1. **隔离、独立备份和永久删除分开。** C5 是同文件系统逐根 rename 的可恢复隔离；保留独立备份、manifest、逐根 prepared/done 和回执，绝不是全批原子事务。恢复前重新观察两边位置及文件快照，原位出现新数据就阻止覆盖。这一链有实质实现与失败注入测试，超过了“删目录后再看是否存在”的普通清单。[核心隔离](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/cleanup_transactions.py#L769-L845)、[恢复保护](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/cleanup_transactions.py#L848-L915)、[部分失败测试](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/tests/test_cleanup_transactions.py#L796-L916)。
2. **失败不等于没有发生修改。** 错误保留 recovery_id、moved_count 和 stage；特别有 rename 已完成但异常/日志未写完的路径，先 reconcile，再单独恢复，不重放原动作。[模糊 rename 测试](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/tests/test_cleanup_transactions.py#L836-L885)。
3. **恢复通道独立于 Agent 和联网。** `recovery_cli.py` 用普通终端对一个明确回执、目标和批次恢复；inspect 不读回执里嵌入的目标，reconcile 只观察；v2 prepared 必须有见证且当前候选精确匹配，才能另行 `restore-prepared`。不从旧回执恢复权限、不制造历史 apply 成功。[离线说明](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/docs/offline-recovery.md#L1-L24)、[CLI 绑定与恢复](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/recovery_cli.py#L76-L199)、[实际 core](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/transactions.py#L821-L947)。
4. **原路线撤回不能搁置既有恢复义务。** 新 plan/quarantine 绑定当前完整 entry，改变目标/路线需重做；既有 reconcile/restore 不要求先重填路线问卷，但仍核真实宿主、备份、停写、摘要和新的恢复批准。[dispatcher](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/cleanup_cli.py#L260-L367)。

#### 不能夸大的实际能力边界

| 项目 | 源码/文档确认 | 不成立的外推 |
| --- | --- | --- |
| C5 范围 | 16 根、4096 项、总 64 MiB、深度 32；仅普通文件/目录；同卷、同用户/组；拒绝软链、硬链、特殊文件及不支持元数据 | 任意容量、任意目录、跨平台全量清理器 |
| 普通 cleanup_cli | 无真实 host 时根操作拒绝；capabilities/结构校验可工作 | 给个 `--yes`、JSON 或摘要即可获得执行能力 |
| Mac 原生宿主 | 有固定位置清单、缓存/日志/持久数据/可选对话分类、真实 TTY 确认、备份核验 | 只是“库没适配器所以完全不能用”也不准确；实际有 `native_cleanup_mac.py` |
| 停写与互斥 | 按可执行名检测；进入/退出 exclusive 段查进程 | 强制阻止进程重启或任意写入；源码明说 Node 启动的 CLI 可能漏检 |
| 备份核验 | 创建时比源/备份内容哈希；后续 backup 哈希检查有进程内缓存，活跃源主要比较 signature，事务核心另读内容 | 每阶段源、备份都重新逐字节比对，或宿主检测是 OS 隔离 |
| Windows/Linux | Windows 无内置宿主/事务引擎，主要是人工执行指引；新版 Windows 同盘隔离明确未真机重跑；Linux 也无对应原生宿主 | Mac 的实现或合成测试就是 Windows/Linux 验收 |
| 浏览器/凭据/卸载 | C5 不包括浏览器数据库、钥匙串、CLI 程序、应用卸载；分开处理 | 一次 C5 覆盖整机/全部身份/云端数据 |

依据：[预算](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/cleanup_transactions.py#L38-L43)、[安全扫描](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/cleanup_transactions.py#L486-L572)、[无 host 拒绝](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/cleanup_cli.py#L222-L230)、[Mac 漏检声明](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/native_cleanup_mac.py#L20-L32)、[Mac 核验/互斥实现](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/native_cleanup_mac.py#L331-L419)、[Windows 限制](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/windows-cleanup.md#L163-L167)。

`native_acceptance: not_run` 被当前 C5 结果硬编码，说明文档也将证据写作 synthetic/CI；本轮只能确认实现和测试设计存在，不能说真实设备已通过。`test_native_cleanup_mac.py` 将平台、home、进程及祖先进程打桩，并使用 scripted terminal；名字里的 native/real_core 不消除这个边界。[结果状态](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/cleanup_transactions.py#L459-L483)、[测试夹具](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/tests/test_native_cleanup_mac.py#L1-L83)、[上游明确边界](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/cleanup-cli-usage.md#L97-L120)。

另一个容易误写的区别：**C5 不永久删除，不代表整个 Skill 没有不可恢复动作。** `native_claude_state_mac.py keychain` 真正调用 `security delete-generic-password` 删除整项；Safe Storage 的删除可能使 Desktop 旧数据无法解密。`simple_mode` 有备份和原子替换，但不是 C5/事务核心的完整并发与路径保护；只检查若干遥测键不能证明所有设置均保持。[状态动作](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/native_claude_state_mac.py#L88-L181)。

#### 账号/订阅建议的证据口径

- 上游确实给出 Free 3 天→Pro、Pro 15 天→Max、新号并发 1–3、封超过 3 个账号换设备/出口、内购每周使用手机 App 等数字；这是作者/社区经验，不是本轮发现的官方平台门槛或可复现因果结果。[原文](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/account-onboarding.md#L1-L31)。
- “苹果内购退款/稳定较好”的推荐旁边，作者自己又加了 11 月 5 日 iOS 内购 KYC 升级、介意可换方案的备注；吸收时必须一起保留，不可只留下首选结论。[推荐及反例](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/account-onboarding.md#L39-L53)。
- 支付流程真正可复用的是区分产品/渠道、先确认官方 App/套餐入口和本人目标账号，再核卡种/地区/含税总额；购买、兑换、订单、权益分别对账，超时先查状态，不重复扣款。这些可以采用，不需要依赖“更稳”的未证因果。[支付卡](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/accounts-and-payments.md#L133-L212)。
- 同一 Gmail 的 Google/邮箱登录“必定为不同账号”、礼品卡“必定免绑卡/地址”、KYC 固定判死等表述，本轮只确认作者这样写，未验证现行官方机制；不升级为真实用户诊断事实，也不据此自动弃号/重购。账号手册本身同时保留应先分诊/不循环注册的原则与弃号建议，存在内部张力。[登录断言](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/account-onboarding.md#L7-L16)、[支付前提](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/accounts-and-payments.md#L21-L34)。

痕迹清理的原目标也应准确表达：作者明确说日志在本地不自动上传，担心以后 Agent 读取或用户粘贴，才进入对话；不能转写成“服务端能自动读取全机日志”。该隐私目标存在，不等于擦旧 IP 痕迹能降低风控概率。[原说明](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/trace-cleanup.md#L1-L8)。

#### 与我们的当前方法对照

现归档 `source-methods-guardian-account-cleanup.md` 已保留上述原方法与冲突，并写清 Mac 哈希缓存/进程检查、C5 容量/平台、钥匙串永久性、bare/认证差别、Windows 未复跑等；浏览器/客户端专题也未冒称已有通用自动执行器。本轮没有发现必须往主入口增加一整套新默认的遗漏；应继续保持缓存默认、具体范围、停写/备份/对账/恢复和真实结果，按任务展开源方法。可以补充一条研究层面的容量提醒：Mac backup 阶段自身的枚举限额（2,000,000）与后续 C5 的 4096 项/64 MiB 不同，不能把 C5 上限当作备份阶段已做预限；未按用户授权运行实测。[备份实现](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/native_cleanup_mac.py#L425-L478)。

#### 本轮实际阅读范围

全文：

- `scripts/cleanup_transactions.py`（952 行）、`cleanup_cli.py`（406）、`native_cleanup_mac.py`（573）、`native_claude_state_mac.py`（225）、`recovery_cli.py`（319）。
- `references/cleanup-cli-usage.md`（124）、`trace-cleanup.md`（112）、`accounts-and-payments.md`（223）、`account-onboarding.md`（69）、`windows-cleanup.md`（167）、`linux-cleanup.md`（95）、`docs/offline-recovery.md`（244）。
- `tests/test_native_cleanup_mac.py`（465；首次输出截断的 235–285 行已补读）。

选段：`transactions.py` 138–220、650–947；`test_cleanup_transactions.py` 490–655、796–920；`test_prepared_recovery.py` 1–245（另看测试名称索引，未将仅名称计为已读实现）。我方归档账号/清理方法相关段落用于对照。

未重新全文阅读：其他清理/恢复测试、历史已移出当前 tree 的验收报告、S02/S03 原稿及全部外链；未验证当前官方账户映射、价格、订阅与退款政策。此前完整材料阅读可复用，但本报告不把旧覆盖数字冒充本轮重新阅读或真机实测。


## 主研究分支补读范围

全文：`references/agent-remediation.md`、`agent-rules-task.md`、`host-libraries.md`；`scripts/repair_execution.py`、`native_clash_verge_mac.py`、`environment_entry.py`、`inventory_cli.py`、`traffic_policy.py`、`probe_evidence.py`；`.github/workflows/tests.yml`、`tests/README.md`、`tests/test_native_clash_verge_mac.py`。

选段：`guardian.py` 500–855、`status_dashboard.py` 80–150、Mac PF 1–100／280–385、Linux VM killswitch 160–260；其余本轮仅搜索定位的不计全文。上述与专项范围有交叉，不累计成独立文件总数。

本轮未重新逐页阅读19份PDF、全部图像及所有外链，也未独立取得所有作者实机原始日志；不作新一轮全仓语义审计或真机效果保证。
