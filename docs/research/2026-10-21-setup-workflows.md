# 客户环境配置流程研究（2026-10-21）

范围：为 Claude/OpenAI 客户环境工具核对可复用的流程设计，重点是 DNS/代理准备之前不新发起 AI 服务访问，以及小白能理解的配置、验证、续做与恢复。这里只静态读取公开文档和源码，没有安装或运行外部项目，没有修改客户机网络。X 检索由主任务另行处理，本文不声称覆盖 X。

## 结论与建议优先级

最值得吸收的是明确的依赖关系、最终运行配置核对、变更后失效及离线恢复材料。不能将其他项目的“自动化”“安全”“防封”表述当作已验证结果。

| 优先级 | 建议 | 对应证据 |
| --- | --- | --- |
| 本次应落实 | 把“不得启动/访问 AI”覆盖到安装后自动启动、浏览器恢复旧标签页、登录跳转、版本/健康检查及代理软件的 AI 解锁检测。网络未就绪时，不为检查安装情况而打开 AI 应用 | Guardian 的接触阶段；Clash Verge 含主动 AI 检测模块。此处列举入口是本项目的风险推导 |
| 本次应落实 | 先核对代理节点解析与 DNS 上游依赖，再启用依赖这些路径的设置；不能让解析代理节点本身又必须先连上该代理 | Mihomo 官方 DNS 文档 |
| 本次应落实 | 配置文件生成 → 客户端持久化入口保存 → 等待重载 → 本次读取最终运行配置 → 非 AI 路径核验 → AI 服务验证；中间任何一步失败都不跳到登录 | Clash Verge 的完整配置处理链 |
| 本次应落实 | 网络线有依赖，时区等本地项目独立推进；失败只阻断依赖项，不把整份清单反复从头执行 | WinGet 官方依赖配置及集成测试 |
| 本次应落实 | 审阅订阅中的自动测速/健康检查目标，再启动或重载核心；配置里引用 AI 检测地址也可能主动访问服务 | Mihomo 的 `url-test` 与 provider `health-check` 官方文档 |
| 优先后续增强 | 网络服务/接口切换、代理节点或活动 profile 改变时，重新读回并复验；报告继续已完成/未完成 | Clash Verge 的网络变更处理；Guardian 证据失效设计 |
| 优先后续增强 | 改网络前把备份、恢复说明和所需脚本留在本机；断网时不能依赖在线 Codex 才能恢复 | Guardian 离线恢复设计 |
| 优先后续增强 | 小白只决定“用哪个现有客户端/配置/节点”和保留项；Codex 完成版本识别、具体路径与参数填写，提供一个当前阻塞点及下一步 | Guardian 按需访谈；本项目交互设计推导 |

这些建议不是新增自动关闭程序、安装客户端、改防火墙或恢复旧配置的授权。对已经运行的 Codex/浏览器只能如实说明现状；一次检查不构成持续断网保护。

## 1. Claude-Guardian：阶段、续接、恢复

核实版本：[DUNHKpcc/Claude-Guardian @ 29f9d39e0cd4438ff4cd5eac1835ec42fdccd0bb](https://github.com/DUNHKpcc/Claude-Guardian/tree/29f9d39e0cd4438ff4cd5eac1835ec42fdccd0bb)。这是社区项目，不是 Anthropic 官方政策。

### 可复用

- **服务接触单独建模**：代码区分本地、非 AI 探测、Claude、登录与支付；本地计划/审计不会自动开放服务接触。观察到接触或相关前提失效后，证据与动作需要当前 `contact_epoch`。这能提醒我们审核每一个可能联网的入口，而不只限制最后的 HTTPS 探针。[workflow_guard.py](https://github.com/DUNHKpcc/Claude-Guardian/blob/29f9d39e0cd4438ff4cd5eac1835ec42fdccd0bb/skills/claude-guardian/scripts/workflow_guard.py)
- **续做不等于从零重问，也不等于直接重用旧结论**：保留已有事实与原观测时间，真实中断恢复后按相关范围复核；回答“没变化”也不会刷新原证据时间或开放操作权限。[interview-resume.md](https://github.com/DUNHKpcc/Claude-Guardian/blob/29f9d39e0cd4438ff4cd5eac1835ec42fdccd0bb/docs/interview-resume.md)
- **恢复材料前置**：离线恢复脚本及依赖在变更前就应在本机，恢复预览先核对当前目标与原备份；不能静默覆盖之后的用户修改。[offline-recovery.md](https://github.com/DUNHKpcc/Claude-Guardian/blob/29f9d39e0cd4438ff4cd5eac1835ec42fdccd0bb/docs/offline-recovery.md)

### 限制与不照搬项

README 明确完整自动修复尚未验收，生产配置写入适配器未开放；离线恢复入口仅覆盖限定 POSIX 文件事务，明确不支持 Windows，也不证明网络和 GUI 实际恢复。其逐次授权、IPv4-only 策略是该项目设计，不能覆盖本客户包已批准的具体批量方案，也不是降低封号概率的官方证据。[README](https://github.com/DUNHKpcc/Claude-Guardian/blob/29f9d39e0cd4438ff4cd5eac1835ec42fdccd0bb/README.md)

建议借鉴行为契约，自行实现本项目的最小状态与测试，不搬入庞大的访谈/支付/账号流程。该项目标示 GPL-3.0-only；若以后复制源码，须先核对许可证兼容和履行义务，本文只研究设计。

## 2. Clash Verge Rev：持久化入口、最终配置、切网失效

核实版本：[clash-verge-rev/clash-verge-rev @ 27d8a71d4141c0be677fbca41d1caee53fc27cbd](https://github.com/clash-verge-rev/clash-verge-rev/tree/27d8a71d4141c0be677fbca41d1caee53fc27cbd)。这是该客户端上游源码，不是 Claude/OpenAI 官方支持保证，也不等于所有客户安装的稳定版本。

官网来源链：上游 [README](https://github.com/clash-verge-rev/clash-verge-rev/blob/27d8a71d4141c0be677fbca41d1caee53fc27cbd/README.md) 指向 `clash-verge-rev.github.io`，本次访问转到 `www.clashverge.dev`。搜索结果存在多个名称相似站点，本研究没有依据名称把它们当官方。

### 可复用

- **不能只核对订阅原文或扩展文件**：当前 `enhance/mod.rs` 依次应用规则/节点编辑、基础应用设置、内置处理、TUN/DNS、全局与订阅扩展，最后再执行 `authoritative.enforce`。GUI 接管的端口、模式、TUN 等字段可能覆盖扩展输入。因此必须核对最终运行结果和当前 profile。[处理链源码](https://github.com/clash-verge-rev/clash-verge-rev/blob/27d8a71d4141c0be677fbca41d1caee53fc27cbd/src-tauri/src/enhance/mod.rs)
- **持久化分层需识别版本**：官方说明扩展的顺序及列表/对象替换行为；不能假设把一条 DNS policy 写进扩展就是无损追加。订阅原文、全局扩展、订阅扩展、GUI 设置都应在变更计划中注明实际归属。[扩展配置文档](https://www.clashverge.dev/guide/extend.html)
- **本地导入会复制文件**：导入后应检查客户端保存的副本和使用状态，不能继续修改桌面原文件并称已生效。[订阅导入文档](https://www.clashverge.dev/guide/profile.html)
- **备份应覆盖必要关联文件**：上游备份包含 profiles 目录、Clash/Verge 设置、可选 DNS 配置和 profiles 索引；只留订阅 YAML 可能无法恢复扩展选择和 GUI 设置。[备份源码](https://github.com/clash-verge-rev/clash-verge-rev/blob/27d8a71d4141c0be677fbca41d1caee53fc27cbd/src-tauri/src/core/backup.rs)
- **macOS 网络服务切换有实际影响**：系统代理是按网络服务保存的。源码监听主服务变化并重新应用代理，且在锁内复核仍启用代理、存在网络服务。这支持把 Wi-Fi/网卡/网络服务变化视为重新核验触发条件。[network_watch.rs](https://github.com/clash-verge-rev/clash-verge-rev/blob/27d8a71d4141c0be677fbca41d1caee53fc27cbd/src-tauri/src/core/network_watch.rs)

### 限制与不照搬项

其导入文档存在“允许无效证书”的排错建议，本工具不能照搬。备份文件仍可能含节点、订阅与凭据，留在客户私有目录，不上传公开 GitHub。macOS 的网络服务行为不能直接当作 Windows 实现证据。读取“配置已保存”与确认“核心已载入”仍是不同检查。

上游还有 [Claude 检测模块](https://github.com/clash-verge-rev/clash-verge-rev/blob/27d8a71d4141c0be677fbca41d1caee53fc27cbd/crates/clash-verge-media-unlock/src/claude.rs)；存在检测功能不代表会默认运行。本研究未执行它。客户流程应避免在网络验收前点击 AI 解锁/可用性检测。

## 3. Mihomo：DNS 引导路径是配置依赖

依据：2026-10-21 读取的 [Mihomo 官方 DNS 文档](https://wiki.metacubex.one/config/dns/)。这是核心配置语义，不是账号安全建议。

文档区分：解析 DNS 上游域名的 `default-nameserver`、解析代理节点域名的 `proxy-server-nameserver`、目标域名 `nameserver-policy`，以及 DNS 连接如何遵守路由或指定代理。经代理查询或 `respect-rules` 需要节点解析安排，以避免循环依赖。

**可复用顺序**：先识别节点是 IP 还是域名、引导解析器怎样可达、DoH/DoT 怎样建连、哪些目标策略需要代理，再准备候选。不能先把全部解析送进尚未建立的代理，再用 AI 域名试错。使用非 AI 验证目标也应确认其走与待验策略相符的路径，普通国外出口不能替代 AI 专属节点证据。

同一文档提供 TYPE65 过滤配置，但“支持过滤”不等于“所有客户必须关闭”。不要为了配置简便批量关闭 TLS 验证、全机 IPv6、UDP 或所有 TYPE64/65。这里只评估依赖关系，未对客户机实际解析路径做实验。

另一个容易漏掉的入口是代理自身的定时请求。官方 [url-test](https://wiki.metacubex.one/config/proxy-groups/url-test/) 和 [provider health-check](https://wiki.metacubex.one/config/proxy-providers/#health-check) 文档都包含目标 URL、间隔等参数。因此“用户没有打开 Claude”不能排除配置重载后核心自动检查 Claude。应静态检查当前及候选中的测试 URL、订阅/规则资源 URL 和客户端附加检测功能；AI 目标后移到网络验收之后，不把所有测速一概关闭。

## 4. WinGet Configuration：明确依赖，独立项继续

核实版本：[microsoft/winget-cli @ 3d9083c062c1e7a7086e05becb414d4e005e4ab6](https://github.com/microsoft/winget-cli/tree/3d9083c062c1e7a7086e05becb414d4e005e4ab6)；并读取 Microsoft 官方配置文档。

- 官方将前置条件与资源操作分开，可声明依赖，而不是只依靠清单排序。[配置文件说明](https://learn.microsoft.com/en-us/windows/package-manager/configuration/create)
- 端到端测试明确覆盖“前置资源失败，依赖资源不执行”与“一个资源失败，不相关资源仍执行”。这与我们的网络线阻断 AI、时区等独立本机项继续完全对应。[ConfigureCommand.cs](https://github.com/microsoft/winget-cli/blob/3d9083c062c1e7a7086e05becb414d4e005e4ab6/src/AppInstallerCLIE2ETests/ConfigureCommand.cs)、[依赖失败夹具](https://github.com/microsoft/winget-cli/blob/3d9083c062c1e7a7086e05becb414d4e005e4ab6/src/AppInstallerCLIE2ETests/TestData/Configuration/DependentResources_Failure.yml)
- `show`、`validate`、`test` 与实际 `configure` 分开，适合借鉴“先展示方案/校验，再改，再测”的用户体验。[命令说明](https://learn.microsoft.com/en-us/windows/package-manager/winget/configure)

**限制**：不是建议把我们的 Mac/Windows 工具改成 WinGet，也不建议为运行检查而自动下载 DSC 资源或执行安装器。外部配置模块会有自己的副作用；静态校验和 desired-state 测试不能证明真实网络路径。

## 推荐的小白流程（本项目设计推导）

1. **识别当前环境**：自动读取本机系统、现有客户端/内核、活动配置；复用已知信息。只询问缺少的配置来源、具体节点、保留项。
2. **给出简短方案**：系统语言保持；哪些正常项保留、哪些需要改、哪些需要客户点击、怎样恢复。明确所需的非 AI 检测站点与后续 AI 验证范围。
3. **先做好恢复准备**：本机私有备份及可离线查看的恢复说明；不要把唯一远控/当前 Codex 通道当作可以随意中断的测试对象。
4. **网络线串行执行**：依赖检查 → 持久化配置 → 单次重载 → 当前运行配置读回 → 非 AI 路径验证 → 记录本轮有效证据。时间/客户明确指定的时区等独立任务可并行，TLS 检查前确保时钟准确。
5. **最后才接触 AI**：允许服务探针、打开页面/应用、登录及业务验收。版本确认优先文件/元数据，避免为“检查是否安装”提前启动客户端。
6. **失败停在当前步骤**：报告“未完成：为什么；下一步”。不为追求完成把失败项改成可选，不循环换节点/重试登录，不让小白编辑 JSON。
7. **下次继续有依据**：保留已做事项和原观测时间，重新读取影响网络的条件；变化只使依赖它的结论失效。合法客户修改不自动覆盖。

客户报告仍只呈现“已完成／未完成”；内部阶段与证据用于控制执行，不需要让客户理解 epoch、哈希、JSON 或底层配置层级。

## 与本轮顺序审计的衔接建议

以下是针对本项目的设计推导，具体缺陷和实现验证由主审计记录，不宣称外部项目已经替我们解决：

- **准备工具也有前置条件**：运行 Codex 本身通常已有服务通信。因此“全新电脑零 AI 接触直到配置完成”不能由在线 Codex 自己保证。客户已有可信控制通道时保护它；完全没有可用路径时，应先用离线说明/预备材料建立基础网络，再让 Codex 接手。只对本轮新发起的 AI 诊断、启动和登录承诺阶段控制。
- **本地项目也可能有联网副作用**：时区、语言可以独立检查和修改，但“重启浏览器应用语言”可能恢复已有 AI 标签；语言修改与浏览器重启要拆开，后者遵守接触门槛。安装器的完成后启动、登录深链、`doctor`、自更新不能因名称像检查就归为离线动作。未知副作用优先读静态元数据。
- **最后一次检查之后仍需检查**：网络探针成功与实际启动之间，核验记录可能过期、配置可能变化。紧邻实际启动前再次验证所依赖的证据；失败不调用启动工具。这个同步检查仍不等于防火墙或持续 Kill Switch。
- **固定阶段，隐藏参数**：让 Codex 自动读取本机端口、活动 profile、客户端版本与路径，只在无法确定时补问。对外显示“准备 → 配置网络 → 验证网络 → 打开服务 → 交付”，内部保留每项的依赖、保护项、变更/读回状态、证据时间和具体阻塞原因。不要把 URL、端口、参数和 JSON 表单交给小白。
- **从停下的位置继续**：已有合格项保留，发生变化的依赖重新验证，保存未知状态而不是替用户选择。不要每次恢复都重装工具、重导订阅、重新要求批准已授权的同一具体清单。

## 本次证据边界

- 读取了以上固定提交的源码/测试文本；没有运行这些项目的测试，不能将其断言当成本机测试通过。
- 官方资料说明功能语义；社区项目提供设计参考；最后的优先级和客户流程是本项目推导。
- 没有任何来源证明“环境一致”“住宅节点”“固定时区”可以保证账号不受限，本工具不作此类承诺。
- 没有验证 Shadowrocket 真机、Windows GUI 写入、系统级断网保护、现有后台应用流量或客户业务登录。这些必须在具体目标机及授权范围内分别验收。
