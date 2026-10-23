# 可靠回滚与生命周期验收

Mac、Windows 使用同一组工具与报告状态：**已完成／未完成**。Codex 填写路径、摘要和证据，客户只确认具体方案、处理必要认证，以及手动完成可能中断通道的操作。供给的 JSON、哈希、旧报告或 CLI 标志都不提供新的操作授权。

## 1. 修改前准备恢复材料

按 [五步流程](five-step-setup.md) 在批准前完成实际平台／版本／配置归属核对、完整最终候选、原值、私有差异、备份位置、恢复方式与复测范围。同一份具体方案获准后连续执行，紧邻写入仍要复核目标未变；不能把恢复材料留到批准后才准备。

`recovery-*` 只处理明确指定的现存纯文本 `.json`／`.yaml`／`.yml`／`.conf` 配置文件；不是任意系统设置写入器。它不修改应用数据库、系统 DNS、网卡、防火墙、订阅账户，不启动、重载或重启客户端。保护当前控制通道。权限、文件元数据或路径归属不能满足检查时停止，不用关闭检查来强行执行。

以下参数由 Codex 按实际材料填写；客户不编辑 JSON：

```text
python <Skill>/scripts/claude_setup.py recovery-plan --target <原文件> --candidate <最终候选> --out <新私有计划目录>
python <Skill>/scripts/claude_setup.py recovery-apply --plan <计划目录> --plan-sha256 <已审阅的计划摘要> --allow-write --writer-stopped --out <新操作目录>
python <Skill>/scripts/claude_setup.py recovery-check --receipt <操作目录> --receipt-sha256 <已审阅的恢复依据摘要> --out <新核对报告目录>
python <Skill>/scripts/claude_setup.py recovery-rollback --receipt <操作目录> --receipt-sha256 <已审阅的恢复依据摘要> --allow-write --writer-stopped --out <新恢复报告目录>
```

计划和操作目录必须新建，保留在客户本机，不能放进 Git、共享盘、公开聊天或转发给下一个客户。摘要用于识别准确材料，不能认证材料的作者，也不代替本轮批准。`--writer-stopped` 表示操作者已确认该文件没有并发写入者，不是工具自动证明；不要为满足该标志自行停止代理核心。应用仍会写目标时，改走其受支持的导出、编辑或导入方式。

还要核实文件是否会被运行中的客户端、同步程序或订阅管理器自动监控／加载。停写确认不等于自动加载已停止；只退出界面也不能证明后台核心不会采用文件变化。无法确认保存不会中断当前通道时，只准备候选或处理离线导出副本，活动配置通过受支持入口交接给客户操作。工具报告的 `proxy_reloaded=false` 仅表示工具没有请求重载，运行中程序是否自行重载仍未核验。

工具先保存原始快照与恢复依据，复核文件身份和摘要，再原子替换并读回。恢复时不仅检查备份，还要检查当前目标仍对应这次写入；客户后续修改、替换文件或权限变化引起冲突时停止覆盖，保留材料并重新出最小方案。写后报告或回执失败时，不能断言“没有改动”；先用操作目录里的恢复依据核对实际状态，禁止盲目重试。

成功操作的 `receipt_sha256` 对应操作目录中的 `receipt.private.json`；应用与回滚均产生各自的新操作目录。最终回执缺失／未完成时，只能用 `intent_sha256` 钉住 `intent.private.json` 做 `recovery-check`，结果保留未完成；不能据此自动回滚。保留原始备份、恢复依据与后续修改，人工审阅精确差异后重新规划。计划／回执不含可恢复的操作授权。

### 应用导入与系统设置的边界

- **小火箭**：修改前通过应用导出当前 `.conf`，保留原文件、选择状态和必要设置。候选通过原生入口导入；不把 SQLite 数据库、编译规则或共享偏好交给文本恢复工具。恢复前再导出当前活动配置，与本轮导入后读回比较；已有后续变化就暂停。需要恢复时，经已批准范围导入原始备份并读回、复测。仅恢复导出文件，不能标记小火箭已恢复。
- **Clash／Mihomo**：先识别订阅、合并扩展和最终运行配置的归属。只在精确方案内处理可编辑文本；不能仅恢复缓存或最终生成文件就声称持久化成功。重新载入与实际流量单独验收。
- **系统设置**：DNS、IPv6、时区、防火墙等保留各自的原值与原生恢复步骤，不塞进文本事务。Windows 原生与 WSL 分开处理；Mac 网络服务与虚拟接口分开处理。
- **权限与元数据**：Windows 文件锁、ACL、reparse point 和替换语义与 Mac 不同；以目标机实际检查结果为准。工具拒绝未知情况时保留未完成原因，不能用另一平台的测试代证。

文件读回成功只表示文件这一层完成；应用载入、进程采用、网络和恢复效果仍需证据。原生应用需要重启，或保存／重载可能影响当前 Codex／远控时，保存进度和离线恢复说明，交客户手动操作。

## 2. 生命周期按事件分开验收

先确定本轮实际使用的客户端。浏览器、终端、Claude/Codex 桌面端、各 CLI、后台进程分别记录，不强制客户安装或启动所有客户端。目标机器、平台与当前执行机分开标识；本机结果不能替客户机、虚拟机或远端服务器出具结论。

```text
python <Skill>/scripts/claude_setup.py lifecycle-template --config <实际配置读回> --target-alias <本机目标别名> --platform <macos或windows> --client <实际使用的客户端类型> --out <新私有记录目录>
python <Skill>/scripts/claude_setup.py lifecycle-accept --config <同一配置读回> --input <记录目录>/lifecycle-record.private.json --target-alias <同一别名> --platform <同一平台> --evidence-dir <本轮私有证据目录> --out <新验收报告目录>
```

默认只有 `normal_use` 为本次必需验收；其他七类事件列后续复查，未实测显示未完成并写原因与下一步，不进入本次必需完成数。客户明确选择本轮事件时重复 `--required-event <事件ID>`，`normal_use` 始终必需；显式纳入的事件严格验收，不能把失败项改成可选。旧版本全必需记录保持全必需，不自动降级。

事件ID：`normal_use`、`client_update`、`proxy_update`、`client_restart`、`system_restart`、`sleep_wake`、`network_change`、`proxy_fault_recovery`。例如明确选择本轮换网时，创建模板加 `--required-event network_change`；工具只记录范围，不执行切网，也不授予该动作许可。

多个客户端重复 `--client`。允许类型为 `browser`、`terminal`、`claude_gui`、`codex_gui`、`claude_cli`、`codex_cli`、`background`。先创建未完成模板，由 Codex 依据真正发生的操作和采样填写事件、进程观察、证据文件及摘要，再运行验收；不能为使检查通过补写不存在的事件。

模板创建成功的退出码为 0，表示材料已生成，不表示验收通过；`lifecycle-accept` 仍有本次必需项未完成时退出码为 2；仅后续复查未完成不阻止本次必需验收。模板可以离线准备其他平台材料，但验收执行平台与实际目标不一致时全部保持未完成，不能由 Mac 代 Windows 或由 Linux 代客户电脑验收。

| 事件 | 本轮必须核实的事实 |
| --- | --- |
| 正常使用 | 指定客户端真实请求、实际代理路径与必要的 DNS／地址族观察 |
| AI 客户端更新后 | 更新确实发生；新版本与进程路径已核对；受影响客户端重新验收 |
| 代理客户端／核心更新后 | 更新确实发生；最终运行配置和当前路径重新核对 |
| 客户端重启后 | 真正退出并重新启动所选客户端，不能只激活窗口 |
| 系统重启后 | 机器已实际重启；自启与网络恢复后的路径重新核对 |
| 睡眠唤醒后 | 实际睡眠／唤醒；恢复后的连接、DNS 与客户端路径重新核对 |
| 换网后 | 实际网络切换；新接口与 DNS 已识别，不复用旧网络通过结论 |
| 代理故障与恢复 | 探测原先确实可用、故障确实发生、有能力观察直连及恢复结果；本来就断网或只有超时不能证明阻断成功 |

客户报告按本次必需与后续复查分别汇总：短摘要使用 `required_completed`／`required_incomplete`，其他事件使用 `followup_completed`／`followup_incomplete` 单列；旧 `completed`／`incomplete` 仍为全部事件的兼容计数，不能拿来充当本次必需计数。详细客户端和路径证据留本机。没发生、客户暂不做、拒绝、观察不全、证据过期或配置变化，都显示未完成并写清原因与下一步。当前正常使用通过可完成默认本次必需范围，但不替其他七类事件通过；有些事件通过，也不产生“持续保护已完成”的整体推断。

### Codex 填写证据的契约

模板的 `events` 保留全部八项，未执行项不填事件实例、时间或回执；拒绝的实验使用 `state=declined`，不要删除来刷完成率。确实发生的事件填 `state=performed`、本轮唯一 `instance_id`、`started_at`／`ended_at`、`event_receipt` 及所选客户端的 `observations[].receipt`。所有文件引用均为证据目录下的相对文件名与 SHA-256，不能带绝对路径、父目录跳转或符号链接。

每份回执都绑定模板的 `record_id`、完整 `binding`、`event_id`、`event_instance_id`、`evidence_mode` 和 `observed_at`。时间带时区，必须在模板创建之后、对应事件窗口之内；模板和观测有七天时效。只有实际观察才标 `observed`；合成、静态、来源不明不通过。哈希只能说明文件没变，不证明其内容真实。

| 回执 | 字段与来源 |
| --- | --- |
| 事件 | `schema=claude-lifecycle-event/1`，`source={kind,artifact:{file,sha256}}`，`details` 记录实际事件。来源类型是 `native_event_log`、`version_readback` 或 `operator_event_record` |
| 客户端 | `schema=claude-lifecycle-observation/1`，`client`、`process_identity_sha256` 和 `proofs`。进程身份建议绑定真实可执行文件、PID及启动时间；不同客户端不能共用一份进程观察 |
| 每项路径证明 | `proofs` 每项含 `check`、`outcome`、`source={kind,artifact:{file,sha256}}`。`function` 需真实功能观察；`proxy_path` 需关联该进程的指定代理流；`dns_path` 需关联 DNS 流；UDP／IPv6 需有对应流量、核心阻断或原生接口关闭证据 |

`details` 依事件分别记录：正常使用的 `actual_use_observed`；更新前后的不同版本摘要；客户端重启前后每个客户端的不同进程身份摘要；系统重启／换网前后不同身份摘要；睡眠与唤醒时间。具体键和严格格式可只读查包内 `scripts/lifecycle_acceptance.py` 的 `_event_evidence`，不让客户填写这些字段。

故障与恢复需记录 `healthy_before_at`、`fault_started_at`、`fault_ended_at`、`recovered_at` 的正确先后顺序，以及实际发生、尝试、阻断、恢复的证据；`fault_clients` 必须逐所选客户端绑定故障期进程和真实尝试。故障后恢复成功的功能观察不能代替故障期间的阻断观察。详情摘要不可信时保留未完成，不能通过填写布尔值制造结论。

## 3. 证据与操作顺序

1. 新建／修复环境仍按 [五步顺序](five-step-setup.md)：网络配置、读回、非 AI 核验与当前 `dns-ready` 在前，Claude／OpenAI 访问及客户端启动在后。记录事件不允许提前启动 AI。
2. 本模块只读取供给材料，不自行联网、采集真实客户端流量、认证事件真实性或执行故障实验。现有 `network-check`／`recheck`／`preflight` 的报告可作为限定辅助材料，不代替客户端采用、事件确实发生和故障观察。
3. 原始材料绑定本轮记录、目标、平台、配置摘要、事件实例、进程身份及时间。配置、目标、平台或执行机变化时，重新核对绑定并创建新的本轮记录，不能只改摘要复用结论。
4. IPv6 探测超时、没有候选或端点返回 IPv4，只能说明本轮未得到 IPv6 出口，不能单独证明整机已阻断 IPv6。DNS 解析器地区和 Fake-IP 也不能替代实际路径证据。
5. 重启、换网、故意破坏节点或断开代理的实验都必须在本轮具体授权与可用恢复路径下安排；可能中断当前控制通道时交客户手动操作。用户选择仅本机只读时，不做这些实验，相关项保留未完成。

## 4. 来源与实现边界

方法参考 Claude-Guardian 固定版本 `1d424d52876c664b535a9d4ba7858e1b9f79e896` 的 [事务恢复思路](https://github.com/DUNHKpcc/Claude-Guardian/blob/1d424d52876c664b535a9d4ba7858e1b9f79e896/skills/claude-guardian/scripts/transactions.py)与[分层验收](https://github.com/DUNHKpcc/Claude-Guardian/blob/1d424d52876c664b535a9d4ba7858e1b9f79e896/skills/claude-guardian/scripts/egress_verifier.py)。本包独立实现，不安装或复制其脚本，不沿用其保存的授权或验收结论。第三方源码是实现参考，社区注册／养号经验不是官方防封依据。

Mac、Windows 自动化测试验证的是临时配置文件与合成事件的工具行为；不等于客户代理、睡眠、换网、故障或原生应用导入已在真实设备通过。客户机实际未验收的项目仍保持未完成。
