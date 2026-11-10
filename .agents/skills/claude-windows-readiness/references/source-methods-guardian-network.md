# Guardian 网络、系统与运行路线：完整可选方法

核对至 2026-11-10。现行源码固定到 `e934166adbdbd582f169b1b14adb7be76aa90a77`（2026-11-09）；历史事实按各自日期保留。本页独立归纳操作方法与适用条件，没有复制执行脚本，也不安装或运行第三方工具。

**按需加载：**用户比较 Guardian 全套方案、要求系统断线保护、需要 VM/VPS/远程协助或具体性能排障时读对应小节。资料阅读和修改 Skill 不触发目标环境检查、网络探针、清理或配置；公开资料检索按用户请求进行。本 Skill 原有五步流程、用户语言/节点/国内业务保留项与当前有效授权优先；这里保存可选来源方法，不把来源默认值悄悄改成本 Skill 默认。

## 1. 方案、实现和证据分开

每项同时记录四件事：本轮采用与否、工具实际支持范围、已有样本来自哪里、这台目标机测到了什么。作者经验、源码实现、历史实测、项目宣布验收和本轮实测分别标注。缺官方因果证明不等于方法不存在；保留其条件、步骤、验证与恢复，效果主张单独注明。

Guardian 的整机默认目标是：所有普通应用/子进程/后台 TCP、UDP、DNS 走同一指定 IPv4 出口，代理失效不直连、不换未经批准的出口；例外单列。**本 Skill 的 domestic-v4 默认保留国内/视频直连并拒绝其余 UDP，两者不是相同方案。**用户选 Guardian 全机转发路线时，先说明与现有国内业务和 UDP 策略的差异，不叠加互相矛盾的规则。

源码中的 `pass/established` 不直接填成本 Skill 的完成状态。接触前准备、客户端正常功能、故障期阻断、恢复后功能分别完成；脚本输出、进程存在、规则读回均有各自范围。

来源：[现行 SKILL](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/SKILL.md)、[路线与阶段](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/routes-and-platforms.md)。

## 2. 目标与能力准备

先明确程序运行在本机、VM客机、WSL/容器还是VPS；VPS仅作代理出口不改变程序执行位置。本地编辑器界面、远端扩展和浏览器分别记录。目标机已有可用Agent时直接在目标机做，不为普通本机配置先安装SSH/Tailscale。

Guardian原流程在目标机核 Python 3.10+、`inventory_cli.py capabilities`、`network_check.py --help`、`egress_verifier.py --help`，随后统一使用随包检测链。缺依赖时说明可信来源、架构、范围、权限、PATH与卸载恢复，沿现有授权处理；未装成保留未完成。使用我方独立工具时说明这是另一实现，不声称已执行Guardian命令。

记录版本、实际配置来源/活动实例、监听入口、真实节点、管理链路与恢复入口。资源不足或没有代理仍可离线准备，不要求先采购。来源变化后只使受影响证据/计划失效，已有恢复义务继续。

修复闭环为：已有事实 → 对应检查 → 根据证据选动作 → 具体差异/原值/备份/恢复 → 获准后一次执行 → 文件/系统读回 → 同目标复测。上游 `agent_remediation.py` 是动作选择器，不执行或授权；缺适配器时继续调查目标支持接口，不能把“有能力缺口”当绕过权限拒绝、过期计划或目标不符的理由。

中断交接写明已做、未做、前置依赖、用户要在哪台机器做什么、需要回传什么、保险丝期限与离线恢复。Guardian用目标绑定的私有work_items和blocking_next_session保留未完验收；我方可复用现有进度记录，不强制每个小任务创建长台账。

来源：[检测与修复闭环](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/agent-remediation.md)、[动作选择器源码](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/agent_remediation.py)。

## 3. 全机IPv4、DNS、UDP与浏览器

### 3.1 先确定持久化来源，再修改运行配置

1. 记录当前订阅、merge、rules扩展、GUI设置、活动Profile及最终 `clash-verge.yaml`。不要把生成文件当维护源。
2. Guardian完整路线开启TUN、auto-route、strict-route；核心 `ipv6:false`，DNS关闭IPv6、使用Fake-IP并接管适用53流量；末尾拒绝IPv6目标，再MATCH指定代理组；DIRECT例外列目的、协议、理由。
3. Verge的 `enable_tun_mode`、`enable_dns_settings` 开启时可能生成覆盖同名段。选择一个明确维护入口并读回最终配置。S10完整订阅方案关闭DNS覆写、从订阅更新DNS/TUN；GUI仍核strict-route。不能无条件同时改GUI、订阅和生成文件。
4. GUI运行时直接改其设置可能被旧内存状态回写；先解决写入者和未保存工作。GUI重开后检查singleton、实际用户会话、核心启动时间、运行文件时间；受控控制器 `/configs` 仅在已有合法接口与权限时使用，不临时公开控制器。
5. Windows只对实际联网的物理接口处理ms_tcpip6；记录原Enabled及身份，恢复同一对象原值；TUN/WSL/Hyper-V/VPN另列。Guardian在Mac/Linux通常先在核心/TUN层限制；我方选定接口关闭策略另按已有决定。
6. 原值、候选与实际读回分别保存，应用载入与实际进程连接另验。节点域名只有AAAA、IPv6-only/NAT64、企业网络依赖出现时先解决兼容，不偷偷切成“优先IPv4”。

### 3.2 DNS按责任层核对

- 系统实际resolver及网络服务、核心普通DNS、解析器域名bootstrap、节点域名解析、浏览器DoH、私有/split DNS分别记录。`default-nameserver`与`proxy-server-nameserver`承担不同引导职责，避免自身依赖循环。
- Fake-IP只说明当前映射；需要真实上游证据时，用本轮唯一查询关联并建立获准连接触发解析，再与权威侧/流量关联。缓存或未收到查询不能填无泄漏。
- `dns-hijack any:53`的默认UDP语义、TCP53、LAN DNS、DoH/DoT分开；macOS/Windows发往局域网DNS不一定被接管。
- Tailscale核MagicDNS、split DNS、exit node、接受DNS设置及Quad100职责；更改前保护私有域名。代理退出时隧道仍在线，不等于私有名字仍可解析。
- 回滚Fake-IP/TUN后若仍缓存198.18.0.0/15，可按已批准范围清系统DNS缓存，再验证真实解析；这不是清账号数据。

### 3.3 Guardian一轮检测与八层判定

采用该工具路线时，先披露确切中性端点与原生/显式代理路径，再由目标机执行已批准的 `network_check.py run --target-ref <别名> --proxy <本机HTTP或mixed入口> --evidence-output <新私有文件>`。`--home-country`按真实基线明确，不机械沿用CN。故障演练另加 `--failure-drill` 并准备独立恢复。

它检查目标路由、IPv4出口、可选显式代理出口、IPv6、关联DNS域名及连接、STUN；网页WebRTC仍是not_run。普通报告不含出口原值；证据文件包含地址，须新建私有保存。

随后补齐TUN/strict-route、核心IPv6、DNS、规则、真实不同程序样本、浏览器及故障观察，交给 `egress_verifier.py check`。8层为TUN、core IPv6、DNS、规则、出口IPv4、IPv6探测、WebRTC、failure drill；全部满足才established。重启、睡眠唤醒、换网另决定persistence，firewall和os_ipv6在原判定器中仅为advisories。不要将配置项或同一终端的第二种入口冒充第二个实际应用。

保留实现限制：该版网络脚本把IPv6解析/HTTP等失败也归unreachable；STUN两次超时标blocked；显式代理终端样本导出为other_app；停核心演练主要靠用户回车与单次出口失败/恢复。使用时补实际核心状态、路由、流量与对照，不能把这些快捷标签直接当全机保护证据。方法可用与证据不足同时记录，不因此删除完整检测流程。

### 3.4 浏览器与非浏览器UDP分别处理

Chrome可选Google WebRTC Network Limiter（ID `npeicpdbkakmehahjeeohfdhnlpdklia`），核开发者，选只用Chrome配置代理并勾 `Disable non-proxied UDP`；或按目标版本采用 `WebRtcIPHandling=disable_non_proxied_udp` 策略。策略与扩展优先级、实际Profile、管理范围分别核对。原文S05示例HKCU、后续指引示例HKLM，按实际作用域选择，不能当同一范围。

每个使用的Profile独立验证，保留原值与扩展状态；告知媒体/通话影响。`serve_webrtc.py`只提供固定本地页，手动打开原Profile、每轮同意后采12秒ICE/STUN；记录候选类型、有效IPv4参考、错误/超时/截断。页面不要求摄像头麦克风，取消或离开关闭连接；停止本地server不撤销已加载页面。

Desktop/Electron自己的STUN/UDP不由Chrome扩展控制。Guardian路线要求实际Desktop运行时核TUN严格路由、节点UDP能力/配置、规则不落DIRECT，STUN映射与TCP出口一致，并做故障/恢复观察。我方默认拒绝UDP是另一方案；不能用其无响应来声称已完成Guardian的UDP转发验收。

来源：[全机方案](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/whole-machine-ipv4.md)、[DNS案例方法](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/macos-dns-case-lessons.md)、[网络分层](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/network-and-remedies.md)、[network_check](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/network_check.py)、[egress_verifier](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/egress_verifier.py)、[WebRTC页](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/webrtc-probe.html)。

## 4. macOS PF方案及证据更新

### 4.1 适用与操作顺序

条件：已选全机路线、TUN与预期出口已通、实际物理网卡和IPv4节点明确、本机/独立恢复入口可用。PF按网卡拦；LuLu按进程的透明TUN方案曾拦正常流量，切PF前记录并处理冲突的LuLu默认拒绝。不是据此否定LuLu所有用途。

PF规则在 `com.apple/claude-guardian` 子anchor，物理接口仅放节点真实IPv4/端口、DHCP、明确bootstrap DNS/LAN，utun和lo不写入阻断。使用 `pfctl -E/-X`引用计数，不改 `/etc/pf.conf` 正文；主anchor缺失时脚本可能载入系统规则集，须在具体方案说明现有PF状态。

| 顺序 | 参数与动作 | 验证／恢复 |
|---|---|---|
| 盘点与render | CONFIG为真实Verge运行配置；或NODE_IPS与NODE_PORTS同时给定；NICS为实际物理接口；BOOTSTRAP_DNS仅节点引导，LAN_NET为明确例外 | render可能为域名节点做DNS/DoH读取，不是纯离线；排除Fake-IP，核provider节点和端口，Hysteria2端口跳跃该版不支持 |
| apply | 语法核验→待确认规则→加载专属anchor/PF引用→180秒保险丝 | 保险丝内测透明TUN字面IP、域名HTTPS、显式代理三路径；失败走原恢复，不靠扩大例外碰运气 |
| confirm | 网络与管理入口验证后本人确认 | 成功才将pending规则作为已确认版本；未确认保险丝撤当前规则与本次PF引用 |
| 故障演练 | 真实停止核心，核目标路由回物理接口，发新的TCP/DNS/适用UDP请求 | 原本正常→故障确发生→阻断证据→核心恢复且同出口；GUI退出核心仍在不能算停核 |
| persist/status | LaunchDaemon开机载入已确认版；查PF启用、主anchor、本anchor、实际NIC覆盖与计数 | 当前脚本无联网前强制顺序、无新NIC自动补规则或换网监控，按实际开机/切换窗口验收 |
| 维护与退出 | 节点/网卡变化重新apply/confirm；`rollback`仅撤当前，`unpersist`去开机项，`uninstall`两者加生成文件 | 日常正常关机保留长期防护；主动OFF先按第7节安全退出。恢复DNS/LuLu等原值另核，不关闭整个系统防火墙 |

### 4.2 PF下的DNS与丢包定位

原方法要求逐网络服务检查自动/手动DNS、实际resolver去往utun/lo还是物理接口；自动DHCP路由器DNS可能在换网后被PF拦。原配方是手动公网IPv4系统DNS，与BOOTSTRAP_DNS地址区分，避免通过LAN_NET放行系统DNS而绕过代理。已有企业split DNS、VPN、内部名字依赖先列出，不把配方无条件套全机。

`dns`只读总结每个服务和resolver路径；`blocked <5–600秒>`抓pflog0后按接口、目的地类别、协议/端口汇总，不输出原IP。公网TCP443、UDP/STUN提示未进TUN；公网UDP53可能是核心上游解析；组播/链路本地/IPv6另分类。

定向复测保留“换网前DNS→并行抓取窗口→真实换网→三条连接与网络报告→换网后DNS→UDP前后三次”的次序。记录有效样本及失败，不因图上绿色覆盖工具错误。系统DNS恢复必须按本次记录的原值，原先自动才恢复automatic/empty。

### 4.3 验证状态按时间保留

- 11-02历史报告：单台macOS15.7.4/Verge2.5.8/Mihomo1.19.32/gVisor/VLESS有停核心、T5重测、真实重启关键保护和回滚通过；R3换网域名exit6、UDP不稳及部分浏览器/新NIC缺证，整单当时未过。DHCP路由器DNS解释当时是推断。
- Issue25由现行文档转述：11-05 macOS26.6.2/bash3.2/Verge2.5.10/VLESS+REALITY域名节点的现场修正版报告通过核心链及established。
- 11-09 ADR-062把PF全项改为上游“已验收”，明确未新增自动测量；ADR-063合入5处变量边界修复并做离线回归。保持这个**现行项目状态**，同时不伪装我方或所有设备真机通过。
- ADR-064将旧报告/测试单移出当前目录，理由是清理已完成验收文档；不是撤回旧事实。历史可从固定提交查，不用旧待验收总括覆盖新状态。

来源：[现行PF与场景说明](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/local-firewall-prompts.md)、[PF脚本](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/mac-killswitch/guardian-pf-killswitch.sh)、[ADR-060至064](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/docs/decisions.md)、[11-02历史报告](https://github.com/DUNHKpcc/Claude-Guardian/blob/9b607dba3833b08e49765b614ac3493e990e3225/reports/mac-pf-isolated-acceptance-2026-11-02.md)。

## 5. Windows首次防火墙与S10两机差异

### 5.1 首次部署流程

条件：非组织受管防火墙，目标管理员权限和独立恢复入口具备；TUN/指定出口先正常；取得正在运行的真实core路径、节点真实IP/端口与DNS引导依赖。Windows防火墙是持久策略，正常重启不会自动删规则；仍要检查ActiveStore、三档Profile和匹配条件。

1. 导出原wfw并记录Domain/Private/Public的Enabled及默认入/出站；保存要调整的精确规则状态。
2. 在阻止前安排独立SYSTEM限时恢复任务，核可运行和结果路径；它必须在控制会话断开后仍能恢复。原示例约3分钟，实际风险/窗口先确定。
3. 先加精确Allow：core完整路径到实际节点IP和TCP/UDP端口；实际TUN接口；DHCP；核回环及必要管理/LAN例外。服务模式core可能不在安装目录。
4. 最后把三档默认出站设Block，并检查三档启用、实际ActiveStore、已有广泛Allow是否架空保护。不能只数guardian规则。
5. 在保险丝窗口内验证正常路径；失败依次查显式代理→保TLS的地址对照→系统DNS→域名HTTPS。curl6/7/28/35/60区分层次；不采用关闭TLS校验的常规修复。
6. 故障演练使用实际新连接，必要时先清DNS正缓存；成功后撤保险丝；失败先恢复访问与原策略，再核问题，不原样循环。
7. 换节点/端口/客户端/TUN接口后复核实际路径、地址过滤和规则条件。回滚恢复本次原默认值/规则状态；不要用一次全库导入覆盖期间用户新规则。

Issue13给出的局部经验：某版本拒绝 `::1` 地址过滤时，使用已核实的Loopback接口；InterfaceAlias只有一项时可能是字符串，不取 `[0]`。WFP查询明确输出私有文件、区分命令失败/无文件/解析失败；必要时暂开5157失败审计，保留并恢复原审计设置。

### 5.2 S10不能拼成单一配方

| 情景 | 原作者当时的方法与观察 | 实施时应保留的条件 |
|---|---|---|
| Windows-a游戏加速器宽Allow | Program=Any出站规则让默认Block仍可直连；查有效Allow及程序/接口/端口过滤 | 识别业务与本次自有guardian规则，精确记录停用和恢复清单，不盲扫全部Any |
| Windows-a DNS | LocalSubnet规则放行svchost到路由器；采用物理TCP/UDP53 Block；清正缓存后演练 | 这是第一台历史状态；不能忽略第二台随后发现它拦核心解析 |
| Windows-b DNS | 物理53 Block优先于core程序Allow，导致核心上游解析失败；撤该Block，核svchost DNS和默认出站拒绝 | 先找实际受阻路径，再选分支；不同时合并两台互斥方案 |
| UDP有规则却无包 | DNS/fake-ip正常而UDP/STUN不通；查实际节点 `udp`、runtime文件、日志与远端对照 | 作者“默认关UDP/全系协议不兼容”限当时版本组合，不扩全产品 |
| GUI未加载 | singleton/旧实例、GUI内存回写、SYSTEM会话空配置；回实际用户交互会话，唯一配置维护源，核strict-route | 不用SYSTEM成功代替桌面GUI状态；不要额外杀无关共享进程 |
| TUN接口重建 | Meta/Mihomo名称与身份变化使接口条件失配；实际Fake-IP网段Allow加当前接口兜底 | 作者GUID归因为历史报告，当前版本另核；只放Fake-IP不能覆盖所有字面IP流量 |
| PS5.1编码/传输 | 无BOM中文脚本按ANSI解释；用ASCII动态网卡或UTF-8 BOM，JSON读utf-8-sig；先文件后scp避免多层引号 | 脚本、SYSTEM用户目录与交互用户目录分开；变量和输出先脱敏 |
| 真实桌面入口事故 | 裸.ps1在Restricted下未加载，自提权代码无机会运行；换.lnk入口参数、UAC、三档读回、联网行为 | 15次SSH/SYSTEM带参测试不代双击；进程级参数不绕过组织/宿主限制 |

S10第一台作者报告8层established但persistence和国内DIRECT去留未完；第二台报告STUN/故障通过，strict-route被重置、实际浏览器与persistence仍待。保留这些具体状态，不概括成“Windows没测过”或“Windows都过”。新工具的测试也不能追补当时没发生的事件。

来源：[现行Windows流程](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/local-firewall-prompts.md#windows)、[S10完整案例](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/S10-windows-deployment-sanitized.md)。

## 6. Guardian Switch：已有防护的日常开关

这是2026-11-09新增能力，不是首次规则生成引擎。采用前先完成对应平台部署，确认系统工具、稳定Skill/Python位置和原始恢复基线。新设备不能复制旧设备的验收结论。

配置模板包含 `version=1`、精确 `target=platform.node()`、`backend`、`protected_processes`、`mac`、`windows`。后端为mac_pf/linux_flclash/windows_firewall；进程清单需包含实际Claude/CLI/所用浏览器/Helper，由首次目标机核对归属，不自动杀进程。Mac参数为CONFIG或NODE_IPS+NODE_PORTS，可选NICS/BOOTSTRAP_DNS/LAN_NET；Windows按精确规则Name（非DisplayName/通配符）分enable/disable列表。

Windows首次 `snapshot` 只接受三档启用且默认出站明确Allow的恢复基线，专用ProgramData目录限SYSTEM/管理员；已有Block部署必须从原备份核实基线，不能把Block当OFF。配置不放订阅链接或密码。

| 操作 | Mac | Linux FlClash | Windows |
|---|---|---|---|
| ON | PF apply→本人KEEP→confirm→persist | 已部署nft文件；systemd180秒独立保险丝→启动规则→KEEP后启用服务/refresh.timer | 精确规则状态＋三档默认Block；SYSTEM任务180秒恢复基线，确认后移除任务 |
| OFF | unpersist→rollback，保留配置 | 停用服务与刷新，移除专属表，保留配置 | 恢复快照中的三档原值与所选规则状态，不关整个防火墙、不导入全机备份 |
| status | PF/anchor/接口覆盖、开机项载入 | nft output drop与units启用状态 | ActiveStore三档与指定Name实际状态 |
| uninstall | OFF后原卸载 | OFF后原部署脚本卸载 | 恢复基线后删除本开关快照/保险丝副本，保留原防火墙规则 |

只含入站链的vps-guard不纳入Switch；VPS确实部署FlClash出站防护才走Linux后端。ON已开启且startup一致时不重复加载；混合状态先核对。开启失败保险丝恢复访问，不表示失败期持续保护。

命令为 `python <稳定路径>/scripts/killswitch.py <on|off|status|uninstall|snapshot|gui|desktop> --config <私有配置>`；desktop另给不存在的新输出目录。系统动作在本人本机管理员终端输入动作+目标确认，ON另输入KEEP，不接受管道自动确认。

GUI用标准库临时回环服务与随机会话路径，固定操作/同源限制，不载远程资源；普通用户网页打开终端sudo/UAC，不直接以管理员运行GUI。Mac.app、Win.lnk、Linux.desktop均是可检查启动入口，不是签名安装包。90秒旧结果提示刷新，关闭标签不撤规则，服务最长15分钟；移动程序/配置后重建入口。

真实交付按“双击→GUI→终端/UAC/sudo→本人确认→读回→网络场景”验收；OFF须先完成下一节安全退出，读回保护与开机保持都关、再次ON可恢复。源码进程检查只按配置名字，不能代替完整PID归属/监听/自动重启核查。上游记录有控制器/HTTP/PowerShell夹具、浏览器演示和Mac临时.app启动，未因此填真实目标防火墙/出口通过。

来源：[完整Switch指引](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/killswitch-switch.md)、[控制器](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/killswitch.py)、[GUI/桌面入口](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/killswitch_ui.py)、[Windows后端](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/killswitch/windows-switch.ps1)。

## 7. 安全退出与十类场景验收

主动OFF/停用保护时：保持代理和防护→保存工作、正常退出目标客户端→在目标设备/用户/命名空间核PID/父子/路径、TCP监听/连接、UDP socket，含Helper/native host/MCP→只终止已确认且获准对象→复查自动拉起→才停代理、撤本次规则。窗口消失不等于退出，监听也不等于已外联；归属不明、共享浏览器或查询失败先保留保护。正常关机/重启不要求撤长期规则；故障演练、保险丝及紧急恢复沿原恢复计划，不被正常退出条件挡住。

Guardian最新首次交付要求选适用场景，每项保留“触发前正常→变化/故障期间→恢复后”的真实新连接和恢复方式：

1. 精确core崩溃/TUN消失：核进程与路由真的变化、物理出口无非批准直连、恢复同出口。
2. 节点不可达：本地网络仍正常，不转DIRECT/未批准节点，原节点恢复后同出口。
3. 真正重启：核启动时间，客户端未启动与启动后分别观察；登录后样本不代登录前全时间。
4. 正常关机再开机与Windows快速启动分开；突发断电只在实际发生后记录，不为验收拔电。
5. 睡眠唤醒：观察恢复过程及正常后路径；无睡眠能力标不适用。
6. Wi-Fi/热点/有线切换：Windows Profile/接口、Mac NIC和DHCP DNS、Linux路由重新确认。
7. 新NIC/TUN重建：先核规则覆盖，再承载业务；Mac未知接口需人工更新，规则存在不等于匹配。
8. 节点域名/地址更新：源可信，Mac重新apply/confirm，Linux核刷新，Windows核地址过滤；系统DNS与节点bootstrap分别检查。
9. 订阅/客户端更新与出口漂移：比较持久/运行配置及原预期出口，不自动接受新出口或反复换节点。
10. Agent/SSH中断：独立恢复能执行，重连读结果；SSH断线不作阻断成功证据。

首次配置现有系统持久防护、客户端支持的自启/重连和已安装恢复组件；日常已自动恢复且配置没变时不重跑Skill。持续失败、新NIC未覆盖、出口漂移才检查受影响项。分别交付自动恢复、人工恢复、未配置的通知/恢复能力；恢复不依赖在线Agent，不以临时手工修复冒充自动恢复。

来源：[安全退出](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/routes-and-platforms.md#safe-shutdown)、[分平台场景与提示词](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/local-firewall-prompts.md#incident-acceptance)。

## 8. VM完整可选路线

作者默认Omarchy，Mac宿主偏macOS客机；创建前选桥接LAN独立接口而非shared NAT。先确认架构/镜像许可、资源、客户需求；这些是作者选型，不自动替换既有VM，也不意味着桥接产生独立公网IP。旧磁盘保留、变更前快照，保护共享目录/剪贴板/凭据；宿主和客机各自取证。

Linux客机顺序：

1. 在控制台确认NIC/LAN与管理入口；`enable-guest-ssh.sh`装OpenSSH、校验sshd并启用；ufw已开时只放SSH_SRC到22。
2. `install-flclash-tun.sh`按固定版本/架构下载并校验SHA256，安装托盘依赖和root属主文件、TUN helper及模块、自启。默认0.9.1/arm64是历史脚本值，不当当前最佳版本。
3. 0.9.2历史helper需要owner UID/GID和RuntimeDirectory；AppImage属主导致授权失败时与deb路径分开处理。核目标内核/模块、服务active/enabled，不只看/dev/net/tun文件存在。
4. 在真实桌面会话导入个人节点并开TUN，GLOBAL与实际策略组都选目标节点，curl和浏览器出口分别验证。
5. TUN正常后才装killswitch，先保证VM控制台救援；配置为实际NIC、TUN、LAN_NET、SSH_PORT，节点真实IPv4/端口，反向隧道存在时核TUNNEL_UNIT解析成功。
6. nft inet INPUT/OUTPUT默认drop，lo/TUN/已建连接、节点、DHCP、限定管理源SSH/ping例外；priority10在conntrack之后；规则单事务替换；180秒内confirm，之后核服务及refresh.timer实际active和下次触发。
7. 核节点更新、核心退出、TUN/策略路由残留、IPv6和浏览器；所选NTP路径被拦时单独列例外或RTC方案。退出/恢复需原规则和服务状态，不能只删表即称恢复完毕。

当前参数化脚本还有需要实施前补齐的条件：刷新ExecStart实际脚本位置、LAN_NET/NIC等参数持久化、定时用户sudo能力、旧规则和服务原值恢复。把这些作为部署前核验，不删除整个参考方法。macOS客机复用Mac系统远程登录、Clash与PF方法，不运行Linux脚本。

来源：[VM完整指引](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/vm-guidance.md)、[客机SSH](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/vm-killswitch/enable-guest-ssh.sh)、[FlClash/TUN安装](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/vm-killswitch/install-flclash-tun.sh)、[nft防护](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/vm-killswitch/install-flclash-killswitch.sh)。

## 9. 远端Linux反向隧道与自愈

条件：目标无法直接管理、已有TUN指定出口、需要长期管理、机器和网络授权明确、另有控制台救援；不是第四种运行路线。目标可直连或已有Agent时不强加它。

架构为目标 `ssh -R` 到VPS回环落点，管理端 `ssh -L` 到同落点再登录目标；代理出口与管理出站白名单分开。顺序必须是VPS sshd/公钥与第二会话验证→独立密钥反向隧道→实际穿透→自愈→最后killswitch白名单覆盖隧道IP/端口→保险丝窗口内探活/确认。

`install-reverse-tunnel.sh`参数包含VPS_HOST真实IPv4、VPS_SSH_PORT、KEY_PATH、TARGET_USER及可选落点/本地SSH端口；密钥不内嵌，复制后核属主与600权限。落点只回环；各目标端口不冲突。VPS的ClientAlive回收占端口僵尸，目标服务Restart重连。首次主机指纹仍按实际可信来源核对，不能因示例accept-new省掉核实。

遇到activating循环：对公钥指纹→同钥直连对照→检查私钥属主→临时无options行对照→独立sshd-ddd端口→restrict/permitlisten逐项二分，防其他已通过公钥行污染结果。无options退化是作者特定版本的可用性取舍，保留回环落点/专用钥匙/ClientAlive边界，不普遍删除有效限制。落点监听存在但穿透reset时另查目标sshd是否安装/监听。

FlClashCore死亡后可能留下ip rule/策略表黑洞：`flclash-crash-heal.sh routes`在TUN不存在时清指向该TUN的残留；隧道ExecStartPre调用。watchdog每30秒检查，core和TUN均缺持续90秒后以桌面用户启动GUI；写全DISPLAY/WAYLAND_DISPLAY/XDG_RUNTIME_DIR/DBUS_SESSION_BUS_ADDRESS，oneshot用KillMode=process，SSH手拉用setsid并脱离stdin。作者两台Omarchy报告约140秒恢复、约3分钟管理盲窗；参数化包未整体重跑，不能把时序保证给新机器。

验收覆盖核心被杀、节点失效、未知进程新连接、DNS/UDP、冷启动、节点IP刷新、管理隧道、换网络IPv6；按故障前/期间/恢复后取样，STUN超时保留原因未明。root改规则、LAN救援例外和VPS单点是明确边界。

原文还提供短时VPS随机名HTTP下载站送脚本的方法：只分发脚本、不传私钥、用完关闭进程/文件/云端口，精确匹配防杀自身。它不提供传输加密与完整鉴权；实际已有SFTP时优先复用，若采用临时站则使用专用最小目录，不把原示例根目录长期暴露。

来源：[进阶完整方法](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/advanced-route.md)、[反向隧道脚本](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/remote-hardening/install-reverse-tunnel.sh)、[自愈脚本](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/remote-hardening/flclash-crash-heal.sh)。

## 10. VPS开发机：S08连贯路线与内存保活

### 10.1 S08完整顺序

1. 先判断项目能否离开本机，是否依赖本地GUI/硬件。作者起点是x86_64 Ubuntu24.04、2–4核、公网IPv4，内存2G最低、4G较舒适、大项目8–16G；按工作负载、价格与真实支持地区再核选型，不当统一门槛。
2. 服务器创建时配置SSH公钥，核主机身份和带外控制台；可选非root开发用户，`.ssh`700、authorized_keys600并核属主；新会话验证后才收窄旧入口。
3. 在远端准备Node/npm/git及所需依赖；Claude Code安装/登录后置于网络和既有许可阶段。Remote-SSH界面在本机，项目/终端/所选扩展在VPS，逐层记录。
4. 仅需注册、订阅、OAuth或重新授权时启动临时图形链：Xvfb→Openbox→Chrome独立资料→x11vnc→websockify/noVNC。原示例显示器`:99`和1440×900是起点；资源不足先检查内存预算。
5. VNC5900/5901与网页6080只回环监听，通过本地SSH-L访问；不公开无密码VNC。共享主机回环也不是独占访问，按实际认证和用户隔离核验。
6. 在该远端浏览器完成本人真实订阅/OAuth，返回远端终端；如果选择官方支持的本地浏览器/手动登录码流程，应明确那是另一方案。作者要求同环境及先Free使用的收益属于经验主张，不伪装官方必要条件。
7. 授权后关闭本次专属Chrome/noVNC/x11vnc/Xvfb及转发，核监听和实例消失；不要照抄广泛pkill影响其他会话。
8. 日常Remote-SSH到项目、`tmux new -A`/attach恢复同一任务；连接断开先找旧会话，不重复启动。按负载使用swap并监控内存/磁盘，原4G swap示例不重复追加fstab、不覆盖已有swap。

S08原PDF全11页和R02图由本轮主线程另作视觉核对；本页同时依据随包文字与详细VPS指引。原安装管道在实际执行前先审阅可信版本，不因来源已收录自动运行。

### 10.2 部署前保住SSH与内存

Guardian给出的具体方法：读取nproc、free的available、swap、磁盘、PSI与OOM记录；至少预留512MB给系统/sshd/tmux作为作者起点；2G及以下示例2G swap，4G示例2–4G，8G示例4G，先核磁盘/文件系统及容器VPS是否允许。

可选earlyoom避sshd/systemd/tmux、优先临时Chrome/Xvfb/x11vnc；不把sshd设OOMScoreAdjust=-1000导致子会话继承不可杀。高峰任务用systemd-run scope的MemoryMax/MemorySwapMax，按内存限制编译并行；小机器避免浏览器与编译/多代理同时峰值。保留tmux、ServerAlive及带外救援。失败查前次OOM后缩小预算，不原样重试。

新增swap/sysctl/earlyoom前记录原值、文件/服务归属；读回swapon/服务/available。恢复仅撤本次fstab/sysctl和服务变更，并恢复运行值；不能把删除文件当实时设置已恢复。

### 10.3 VPS防火墙按出口角色分支

VPS自己IP就是出口时，`vps-guard.sh`是**入站加固**：INPUT drop，回环/已建连接/ADMIN_NET的SSH与ping/DHCP/IPv6邻居发现；OUT不限制。先render、语法检查、云安全组与系统层分别核、180秒保险丝、另一会话确认。MOSH=1才给ADMIN_NET放可配置UDP60000–61000；漫游到管理源外会断。VPS另套家宽TUN时才选VM的出站killswitch，加入管理通道出站白名单。

入站guard没有出站防直连是其用途边界，不是整个方法无价值。回滚须恢复本次旧表/服务状态；源脚本默认删专属表不足以证明任意既有部署已完整恢复，实施前补准确恢复方案。

来源：[VPS详细指引](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/vps-guidance.md)、[S08 PDF](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/S08-vps-claude-tutorial.pdf)、[S08文字定位](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/S08-extracted-text.md)、[入站guard](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/assets/vps-firewall/vps-guard.sh)。

## 11. 线路优化：保留具体可回退操作

先区分本地→A、A→B、出口→网站和应用负载；同时间/数据量/客户端建立基线。晚高峰绕路优先线路，大流量差看方向和重传，下载挤占先限速，画面卡且CPU高先降负载。三网、去回程、IPv4/IPv6、流量计费分别核；一次只变一个因素。

**方案A：浏览器在A、B只提供家宽出口。**前提A已有浏览器、B的SSH可达且允许转发。A执行SSH动态转发到 `127.0.0.1:1080`，保留主机核验与ServerAlive；A浏览器配SOCKS5并核远端DNS。容器loopback指容器自身。用socks5h的curl与实际浏览器分别核B出口；停止本次SSH、恢复浏览器原设置回退。自启/自动重连是另项，不默认加服务。CLI不直接SOCKS不能与浏览器方案混淆。

**方案B：浏览器或服务在B、A只做中转。**选架构匹配Realm，A的endpoint监听指定端口转发B真实服务端口；云/系统防火墙只放管理来源。连接A转发口时核B主机指纹。前台停Realm、撤本次配置和放行回退。单端透明中转不额外加密；双端隧道才增加A—B封装，不是方案A必须多加一层。

**轻桌面入口。**已有VNC在A回环5901、noVNC回环6080，再由本机SSH-L访问；不把这两端口开公网。可从1280×720、较低画质/帧率开始，先保文字可读。收益同用途复测。

**BBR逐步卡。**先记tcp_congestion_control、available列表、default_qdisc及实际tc qdisc；有系统模块才尝试modprobe，仍不可用就跳过不换内核。只临时设bbr，重建实际业务TCP观察；效果差立即恢复原算法。确认保留且无同名文件才写本次sysctl.d文件；回退要删除本次文件并恢复实时原算法。保留CAKE/mq/noqueue等实际队列，不把default_qdisc当当前网卡事实。BBR不改运营商国际路由，换DNS也不是线路升级。

源案例“两机IPv4方向异常、换该段IPv6后部分恢复”的因果仍是案例推断；可保留对照方法，不能变成所有链路必须IPv6。它还与严格IPv4外层方案有冲突，选实验前明确范围及当前约束。

来源：[线路操作指引](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/line-optimization.md)、[R02完整来源](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/R02-vps-line-optimization.md)。

## 12. 出口、TCP/UA经验与远程协助

作者比较托管机场、自建VPS、家宽拼车，Max偏自建、Pro偏托管，给3x-ui、优化线路、可选家宽及桌面/手机客户端组合。保留为其选型经验：实际选用仍核共享/固定性、运维、费用、取消和故障支持；不由套餐推出强制采购。新协议/TLS/传输/UDP选所有实际客户端兼容组合，桌面成功不代手机；S10协议对照可以参考，不把当时“REALITY全系不兼容”变成通用结论。

作者浏览器路线还提出：浏览器延迟含本机→出口，网站TCP握手仅见出口→目标，因此好线路美国或近地出口可缩小差异；出口TCP指纹与本机UA/TLS/JS来自不同层，Linux出口可考虑Linux客机/VPS，Mac/iOS称TTL更近；不要单改UA制造其它层不一致。保存这些条件与理由，但OS/TTL、IP分数与账号处罚的因果尚未建立。若验证，先对照现状、原生UA/Client Hints与实际链路，不能直接要求换系统或买设备。

Guardian的Net.Coffee“除语言全绿”是其交付口径：原Profile本人打开，出口/地区/风险标签/连通/DNS/WebRTC/设备/时区逐项看，按对应层处理。可以展示该完整方案与作者换出口建议，不把分数当官方封号概率；本Skill当前不自动刷绿或换出口的选择另列。

异机协助仅在用户需要时启用：先复用已有通道，核两端身份和实际可达；Windows管理员公钥位置取决sshd_config与权限，Mac用系统远程登录限管理用户、按需Tailscale/屏幕共享，GUI必须在真实桌面会话。远程故障用独立于SSH的“停→测→恢复→私有结果”，Windows计划任务与SYSTEM路径、Mac单次launchd与FileVault接手者分别说明，不另装无需求的常驻服务。

Agent就在被改网络时，先把自身路径分直连/本机代理/TUN/宿主或LAN代理；列出会短断和持续断开的动作。先保存离线交接及保险丝期限，用户执行可能断开步骤，重连先读回是否已被保险丝撤销，不原样重试。作者要求安装killswitch前Agent改用本机TUN而不为宿主代理开旁路；这是完整路线的策略选择，不能暗中修改我方已批准控制通道。

来源：[出口选择](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/egress-ip-options.md)、[TCP/UA原方法](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/exit-consistency.md)、[本机远程协助](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/local-advanced-route.md)、[Agent同机链路](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/agent-on-target.md)。

## 13. Clash单规则修改的窄范围方法

Guardian的实际原生写入范围仅macOS/Verge2.5.8固定位置、当前Profile独占的rules扩展、支持的空prepend。先绑定应用plist、profile index、基础配置、扩展和元数据，生成单条DOMAIN→现有组的候选。准备精确差异、私有备份与离线恢复，解决旧编辑器和写入者；退出GUI，不要求停仍在工作的root核心/服务。执行前后多次核内容/归属，备份原子替换，读回后重开应用核载入、实际规则、路径。

若走受支持GUI，Save可能同时重载，不能再额外重载；结果丢失/超时先读状态不再保存。`agent_rules_task.py`只是供给快照的纯内存辅助：精确字节匹配、原文未变、无注释限定语义重排、意外差异分别判断。任一含注释时不能把删除/移动注释当允许格式化。后续用户修改/换Profile时停止整文件恢复，重新审阅；旧计划和哈希不授权新操作。

这套窄范围有指定Mac历史写入/读回/重启/恢复记录；不等于Windows、小火箭、任意版本通用原生执行器。可参考其动作次序与内容保留，不要求用户降级软件来凑适配。

来源：[完整应用编辑卡](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/agent-rules-task.md)、[原生适配](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/native_clash_verge_mac.py)、[执行链](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/repair_execution.py)。

## 交付时保留什么

采用哪条路线、目标/版本/实际配置、原值与精确变化、当前正常功能、故障期间证据、恢复结果、自动/人工/待做的场景、离线恢复入口及来源固定版本。没采用的方法仍可在目录找到完整条件，没验证的效果仍保留作者方案与下一项检验，不把它们删成一句“未知”。本页没有产生任何真实设备通过证据。
