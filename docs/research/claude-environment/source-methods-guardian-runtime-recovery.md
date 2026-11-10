# Guardian：清理事务、恢复与证据工具完整补充

来源固定为 DUNHKpcc/Claude-Guardian `e934166adbdbd582f169b1b14adb7be76aa90a77`，核对日期 2026-11-10。
本参考保留原作者方法、参数、顺序和限制；阅读不授权执行。遵守用户本次任务范围以及已有网络、语言、时区偏好。
本轮为源码和测试全文静态阅读，没有在用户设备运行。测试所用 synthetic/tmpdir/mock 不能写成用户环境已验收。
账号节奏、浏览器和客户端分类清理原方法见 [账号与清理方法](source-methods-guardian-account-cleanup.md)；CCBaga 对照见 [CCBaga完整方法](source-methods-ccbaga-cleanup.md)。

## 1. 先选择实际有能力的入口

固定来源：[宿主库](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/host-libraries.md)、[环境入口](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/docs/environment-entry-decision.md)。

- 先区分本机、VM客机、VPS开发机；“VPS只是出口”仍可能是本机路线。声明目标和真实执行命名空间分开核对。
- 没有购买代理、网络资源未知或选择直连，不阻断已授权离线盘点；导入配置不代表配置生效。
- `environment_entry` 验证归一化选择，输出只是可进入后续检查。它不确认设备身份、安装情况、用户许可或网络可用。
- `guardian.py check` 收集固定系统元数据和默认代理摘要；进程架构不是硬件或Rosetta结论，代理摘要不是真实路径证据。
- `inventory_cli.py static-audit` 为Mac限定静态读取，现行请求schema是 `/2`，含 `entry_request`；早期docs中的 `/1` 示例需更新后使用。
- 该CLI的 `2.5.5/1.19.0` 是合成schema标签，不代表真实版本认证。2.5.8规则写入有独立入口，不能混用版本标签。
- `--entry-file` 安全文件读取是POSIX能力；Windows可审阅宿主传入dictionary的接口，不能宣称同一CLI文件形式已原生支持。
- VPS默认只有basic nonintrusive入口，不能从选VPS自动推导清理隔离或配置执行器可用。
- 目标/路线撤回会使新读写计划失效；已留存精确回执的恢复仍可单独处理，不能丢掉旧恢复义务。

## 2. C5 备份、计划、隔离、恢复

固定来源：[清理CLI](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/cleanup_cli.py)、[事务核心](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/cleanup_transactions.py)、[Mac宿主](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/native_cleanup_mac.py)。

前提与参数：

- 核心仅POSIX；精确根、保护路径和隔离目录不能重叠。相同用户/组、同文件系统、无目录链接/硬链接和不支持元数据。
- 单计划最多16根、4,096项、64 MiB总内容、深度32；私有文档4 MiB，默认操作预算30秒、最大60秒，计划10分钟。
- 预留未来回执体积；大量Unicode路径即使内容小也可能触限。超限先报告，按明确范围重做独立批次，不能悄悄删上限。
- 通用 `cleanup_cli` 默认没有宿主；`HOST_ADAPTER_UNAVAILABLE`表示缺真实归属、备份和写入者核验，不是允许换成无保护删除命令。

完整顺序：

1. 正常退出目标Claude写入者，核定当前用户、home/配置根、数据类别和明确保护清单；保留源码、Git、Codex及非本次范围。
2. 创建独立备份并按相对结构、大小、哈希核对。Mac原宿主将其放在 `~/.claude-guardian/backups/<backup_ref>`，目录0700、文件0600，加入保护路径；已有目录拒绝覆盖。
3. `plan`读取精确原件与身份、生成私有计划和摘要；审阅将移动哪些根、是否包含会话/自动记忆/配置。计划不是清理完成。
4. `quarantine`开始前及每根提交前复核归属、写入者、摘要与原快照；逐根先写prepared日志，再同卷rename，再哈希/身份复查，写done。
5. 回传实际移动数量、未移动项、阻断原因。独立备份与隔离记录都保留，不默认永久删除。
6. 需要恢复时，用原计划/回执及摘要 `reconcile` 当前状态；仅将仍在隔离区且原位置空缺的项目单独确认后 `restore`。

失败与恢复：

- 非零退出可能发生在移动之后、日志之前；保留 recovery_id、moved_count、stage，并检查实际两处位置，禁止盲目重放隔离。
- 部分恢复中断后重新对账，再处理剩余项目。旧计划10分钟过期不禁止恢复，但当前内容/身份/归属必须匹配。
- 原位置出现后来文件、空目录、symlink、后续编辑或备份损坏均拒绝覆盖；冲突材料由用户选择保留/另存，不制造新快照绕过。
- Mac名单不允许整根 `~/.claude`；projects/history属于单独对话类别，debug属于可再生日志；完整Desktop数据根属于持久状态，不能标成缓存。
- Mac宿主拒绝在Claude父进程下运行，未知父链/进程列表也拒绝。该进程检查及协作锁不提供任意第三方写入者的原子排他保证。
- 证据边界：源测试有tmpdir隔离和故障注入，未由此证明真实Mac C5允许路径、Windows清理或任意版本Desktop兼容。

## 3. 无Agent也可使用的精确文件恢复

固定来源：[独立恢复流程](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/docs/offline-recovery.md)、[恢复CLI](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/recovery_cli.py)、[精确文件核心](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/transactions.py)。

- 在任何可能断线的变更前，本地保存 `recovery_cli.py` 与 `transactions.py`；准备可独立进入的终端，确认精确target、batch位置及私有回执。
- 只支持现有单链接普通文件、4 MiB、原用户/组/mode及支持的元数据；不覆盖Windows registry/ACL、多文件原子恢复、应用和网络语义。
- 第一步 `inspect --receipt <精确回执>`：只读所选回执，得到候选摘要，不读取其内嵌目标。摘要不证明回执真实性。
- 第二步 `preview`：显式提供 `--receipt-digest`、`--target-ref`、`--target-path`、`--backup-batch`，与可信原记录核对后检查目标和备份。
- 第三步 `rollback`：在真实终端确认持续排除所有写入者，再确认完整摘要，提交前另一次新挑战。默认每次60秒，`--approval-timeout`允许1–300秒。
- 每次清空预输入，新随机挑战阻止提前粘贴后续回答；没有 `--yes`、pipe或保存的授权令牌。这是人机工作流，不能认证操作者或证明OS排他。
- 如果只有prepared回执：先 `reconcile`；v2的prepared_candidate_observed才能进入 `restore-prepared`，需另传完整reconciliation digest。
- original_observed表示原件仍在，无需恢复；applied_observed使用普通回执；legacy_identity_unproven/conflict保持只读；restore_not_committed/restored_candidate_observed不得重放旧恢复。
- 恢复也先写 `restore-<attempt_id>.prepared.json`。日志失败时可能已经恢复原件，先核现场，不要由“失败”推导“没有修改”。
- 暂存清理/描述符关闭失败单独报告；保留可能含秘密的staging/backup，不默认上传或清除。
- POSIX rename不是CAS；独立写入者排除仍是实际前提。输入超时不是文件系统硬超时，使用经核实的本地存储。

## 4. 规则调整：保留现有配置的四条路径

固定来源：[语义计划](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/remedy_plans.py)、[merge编译](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/config_edit_plan.py)、[prepend编译](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/rules_extension_plan.py)。

- keep-existing：选择既有规则和明确出口组；explicit-rule：所选应用采用已确认HTTP/mixed入口；tun-rule：限定TUN路线；scoped-compatibility：限定IPv4/WebRTC兼容方案。
- 编译前记录目标/范围、原revision、版本、控制通道与救援、当前组图；嵌套DIRECT、组循环、空组、未知成员或协议要阻断/保持未知。
- DNS分别检查正常和失效分支的解析依赖图；保留本地解析、DoH、bootstrap及policy优先级，禁止无语义的深合并。
- 显式代理+TUN组合需单独核回环/排除；IPv4调整先核节点外层是否依赖IPv6；临时诊断规则有明确移除步骤。
- merge编辑只更改明确DOMAIN/DOMAIN-SUFFIX三字段规则的策略token；拒绝已知前置覆盖，保持其他字节，重新解析完整语法树。
- prepend只向单行空`[]`插入已选顺序；非空仅接受整列表精确重复，delete必须空。保留append与其他字段，检查base/append重复与受保护规则重叠。
- YAML限4 MiB、20k事件、48层；无别名/anchor/tag/merge-key/重复键。调用者声明的保护索引不证明保护列表完整。
- no-change只做当前快照观察，不创建操作计划、备份或回执；不能把过期旧计划转换成“已成功”。

固定来源：[Agent应用编辑任务](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/agent_rules_task.py)、[Mac原生适配器](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/native_clash_verge_mac.py)。

- Agent编辑任务更窄：2.5.8、单个DOMAIN、三序列SeqMap、append/delete为空，操作前核当前选中配置；保存前再次读回编辑器内容和归属。
- 含注释时必须保留精确字节；删除/改动注释、BOM、换行不能当“仅格式化”通过。无注释时有限语义相等只标supplied snapshot comparison。
- Mac原生适配器仅支持固定App plist及support/profiles的rules-prepend，要求单profile唯一归属；shared/global/default扩展拒绝。
- 退出GUI即可；作者专门保留root core/service，以免无谓切断TUN。提交前后重新核GUI/源文件身份。
- 文件读回成功只叫written_but_not_verified；重启GUI后应用是否载入、规则优先级和实际流量另行验。回滚使用上一节精确回执，不覆盖后来编辑。
- 编译器apply_supported=false与受限原生宿主可执行是不同层；旧docs“production总拒绝”不能替代当前代码能力判断。

## 5. 登录态、SIMPLE与时区的原生边界

固定来源：[Mac状态操作源码](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/native_claude_state_mac.py)、[对应合成测试](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/tests/test_native_claude_state_mac.py)。

- 作者Keychain方式先按service查询是否存在，不读秘密值，然后整项删除`Claude Code-credentials`或`Claude Safe Storage`；声明不可恢复，操作前后用进程护栏。
- 它没有对自定义配置根、account项目和OAuth字段做精确归属/CAS，也不承诺保留共用blob中的MCP登录。列为原方法，不冒充我方默认安全字段清理；不能整删SafeStorage作为默认操作。
- SIMPLE原方式只修改`settings.json.env.CLAUDE_CODE_SIMPLE`，on设`1`，off移除；保留其它设置/遥测key并私有备份，遇同值不写。
- 2026-11-10根代理官方核查：bare/SIMPLE不读OAuth/Keychain，需API_KEY或`--settings apiKeyHelper`；显式`--add-dir`的skills例外。它不适合作为订阅轻量模式；`--safe-mode`另为保留正常认证/工具/权限的自定义配置排障方式。
- timezone原方式用户选IANA地区、显示原值和恢复命令，sudo在终端收密码；systemsetup之后最多10次×0.5秒等`/etc/localtime`异步更新。未读回匹配不能报成功。
- 这些原生方法未替代自动时区开关、其它应用时区、语言偏好或真机验收；本轮均未执行。

## 6. 报告绿色需要带上证据范围

固定来源：[固定策略](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/traffic_policy.py)、[网络投影](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/probe_evidence.py)、[验证器测试](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/tests/test_egress_verifier.py)。

- `whole_machine/IPv4_ONLY/disabled/no_direct`是所选策略常量，不是当前机测量结果。
- 面板把24小时内network pass映成verified，未来/陈旧未知；附加network与主报告需人工/宿主核对同目标、平台、配置、时刻，它不会自动完成该绑定。
- egress_verifier的established可以同时伴随firewall未部署、OS IPv6开启的advisory；restart/sleep_wake/network_change单独决定persistence，必须一起呈现。
- 源network_check的IPv6错误→unreachable、DNS国家启发式、故障请求失败→恢复后no_direct有证据限制；保持“这一路径样本/该端点失败”，不扩成所有浏览器、UDP或系统防直连结论。
- 静态HTML只投影已有报告，不刷新证据。CI的桌面/手机布局和键盘测试使用合成报告，network_isolation_verified=false，不可称用户设备环境验收。
- 具体WebRTC比较：单次12秒请求、固定Cloudflare STUN、所选browser/profile、手动同意；只比较srflx IPv4与用户输入HTTPS样本，host/mDNS/prflx/relay与IPv6另列。
- 无候选、701、timeout保持未知；展示最多128候选/32错误，超限标记truncated，聚合仍检查后续差异。相同IP不等于同路径或实际选中媒体路径。
- 取消/pagehide关闭peer/channel/timer并清内存参考；loopback helper结束不自动终止已加载网页，URL发布后异常需另关页面。

## 7. 续接只追当前缺口，保存原有事实

固定来源：[访谈状态机](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/interview_flow.py)、[续接流程](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/docs/interview-resume.md)。

- 先归一化当前回复中所有事实，再原子更新后问一个真正缺口；未知/拒答/暂缓不循环追问。
- account/device/task/route分别绑定；账号封禁历史不能自动推导当前设备需清理，当前限制事件与过去已解决事件分开。
- 普通读档不等于中断；实际中断用新的resume_id，审阅六类结果：不变、变了、不知道、拒绝、稍后、目标变了。只使变动字段陈旧，不刷新旧测量时间。
- 目标变了先重新绑定；未使用路线的历史事实保留，路线重新生效时再审阅。凭据/数据事故优先处理，但保留后续恢复义务。
- 普通网络/清理任务不重新问支付；仅具体功能依赖才问当前套餐。当前套餐、想升级的套餐、历史渠道与未来渠道不互相替代。
- 账单页面冲突先记录episode原事实、页面关系/状态及时间；解决需当前明确答复，分同目标现有订阅、别的账号页面、旧页面，不能只设false。
- 部分答复只保留互补字段的原始来源/时间；历史导入、新任务或重复付款完成记录不能洗成新证据，也不能自动清除仍未解决矛盾。
- work_items记录范围、影响、前置条件、回传证据和未完原因；acceptance未完成保留blocking_next_session，恢复会话先看该清单。
- 原程序G3始终blocked，user:标签不是认证。A档authorization_check还有“只看scope active未核allowed_actions”的实现缺口；不能让它替代本会话用户授权。
- 原程序恢复会话使权限记录陈旧属于作者策略；我方持续有效授权、一次批准具体计划的偏好仍按用户会话决定。

## 8. 更新、归档和资料完整性

固定来源：[更新检查](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/update_check.py)、[打包](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/tools/package_skill.py)、[章节索引生成](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/tools/gen_section_index.py)。

- 原检查每会话一次GitHub树逐文件hash比较，分别列changed/upstream-only/local-only；只有本地额外文件不算更新。失败继续安装版并标“未查明最新”。本轮阅读任务不运行该检查器。
- 更新前审阅固定commit差异，Skill目录外备份、保留二开；更新后新会话加载，失败恢复旧版。不要将浮动main比对当已固定下载包身份。
- 发布显式列表+source manifest SHA256，排除私有报告；ZIP不含docs/tests，离线依赖说明需确保可取得。
- 主题入口与章节索引只是定位；逐文件正文、PDF逐页视觉、历史报告分别记阅读状态，哈希相同才复用，不能以链接存在算已读。
- 原Wiki导出会重写导航/图片路径并覆盖当前同名页面；在明确目标目录使用，先保留自定义页面。regex脱敏不能证明所有敏感内容已除。
- 17份VPS索引与manifest对“PDF字节不变/已Ghostscript压缩”的说明存在不一致；以每份original/distributed哈希及实际页内容为准，原始未压缩文件不可冒算已读。

## 9. 最新状态与历史证据如何一起交付

固定来源：[ADR-039起的历史记录](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/docs/decisions.md#L303)、[ADR-062/063/064](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/docs/decisions.md#L547)、[文案契约测试](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/tests/test_guides.py)。

- latest已合入Issue #25五处`${var}`展开边界修复；“尚未合入”只适用于更早记录。bash3.2.57 en_US.UTF-8复现，C未复现；此次是离线诊断回归，无新增PF现场测量。
- 11/09“全部PF已验收”保留为作者状态；没有逐项补造日志。独立历史测试报告已从当前树删除，固定历史commit可追溯。
- Mac15.7.4/Verge2.5.8的旧记录有规则写入、重载、回滚和时区样本；C5允许路径、实际Keychain删除、SIMPLE和完整生命周期没有同等证据。
- “所有平台都验证过”是作者陈述；CI、函数名native、测试总数和文案assertIn不能扩展为真实Windows权限/清理/防火墙验收。
- 3/15天、并发1–3、超过3个封号弃设备、每周打开App、2–7天申诉等原方法继续保留并标“作者经验阈值，未独立验证因果”；测试只锁定其文字。
- 保留S03第4页真实时区/语言不必英文/IPv6统一出口或关闭与latest作者默认的冲突，不删原话来源。latest先原版CLI与env-cleanup前两周Desktop/App的冲突也应并列。
- ADR-048/049/050已删旧探测库、Windows事务、旧设计台账；只能称历史实现，不在当前包虚构入口。现行缺口明确交付，后续可按用户批准范围单独补验。
