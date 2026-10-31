# Claude-Guardian：增量核对与选择性接入

核对日期：2026-10-31。用于用户提到 Claude-Guardian、第三方检测报告或需要进一步定位 DNS／防火墙故障时。普通配置不必整篇加载。这里是来源核对与操作指引，不新增执行器、网络探针或运行授权。路线／出口／线路看 [部署规划](deployment-routes.md)，注册订阅看 [准备模块](account-preparation.md)，故障与明确清理看 [事故模块](incident-and-cleanup.md)，时区看 [默认目标](timezone-policy.md)。

## 来源、版本和实际能力

- [开源仓库](https://github.com/DUNHKpcc/Claude-Guardian)本轮固定到 [`06fe998d753f697c47ae0b67be5fe91451532a1f`](https://github.com/DUNHKpcc/Claude-Guardian/tree/06fe998d753f697c47ae0b67be5fe91451532a1f)，提交时间为 2026-10-30。阅读了 README、相关参考、网络采集／判定代码和 Mac 原生适配器；未安装或执行其脚本。
- [Guardian 官网](https://api.dpccgaming.xyz/guardian)也是该项目的介绍与服务入口（仓库 README 的 Partners 段有链接），不是第二份独立技术来源；本次以固定版本仓库为接入依据。
- 旧版“原生修复器一律不可用”的描述已过时。[当前入口](https://github.com/DUNHKpcc/Claude-Guardian/blob/06fe998d753f697c47ae0b67be5fe91451532a1f/skills/claude-guardian/scripts/repair_execution.py)调用了 [Mac 适配器](https://github.com/DUNHKpcc/Claude-Guardian/blob/06fe998d753f697c47ae0b67be5fe91451532a1f/skills/claude-guardian/scripts/native_clash_verge_mac.py)：声明范围仅为 macOS、Clash Verge Rev 2.5.8 的固定位置 `rules-prepend` 扩展，要求 GUI 写入者退出并复核源文件身份。它不能阻止两次检查之间的写入竞态，也不是 Windows／小火箭通用执行器。源码存在和上游的实测自述不等于本机已验证。
- 本次只加入独立归纳和来源链接。若以后需要复制其代码或安装完整 Skill，再核对当时版本及 GPL-3.0-only 的许可文件；不要覆盖本 Skill 或把第三方脚本悄悄挂到现有命令后面。

## 吸收进现有流程的方法

### 先分清执行位置与出口

Claude 在本机运行、仅通过 VPS 出网，仍属于本机任务；只有 Claude 实际在远端运行才需要远端环境检查。分别记录目标设备、应用／进程、代理入口和出口。不要因为用户有 VPS 就自动部署远程桌面、虚拟机或防火墙。手机结果由手机取得，不能用 Mac／Windows 的同名节点或探针代证。

### DNS：让每份证据回答一个具体问题

在[已有网络流程](lifecycle-checks.md)中，分开记录系统解析器、核心 DNS、浏览器 DoH、DNS 上游域名引导、节点域名解析和私有域名依赖。发生问题时只扩查受影响的层。

- Fake-IP 或缓存答案不证明真实上游完成解析。若用户已批准权威侧关联检测，使用该服务本轮的唯一查询标识；必要时对同一已批准域名建立连接，让核心实际解析，再关联查询、上游观察和连接时间。只做系统查询可能只得到映射；服务没有收到记录也不能直接判定“无泄漏”。
- [Mihomo TUN 文档](https://wiki.metacubex.one/config/inbound/tun/#dns-hijack)说明未写协议的 `dns-hijack` 默认是 UDP；TCP/53 要单独核对。macOS／Windows 发往局域网的 DNS、Android 私人 DNS 还存在接管限制。端口 53 的规则不能证明 DoH／DoT 路径，以上字段语义也不能照搬为小火箭参数。
- [Mihomo DNS 文档](https://wiki.metacubex.one/config/dns/)中，`dns.ipv6=false` 是 AAAA 空应答语义，不是系统接口 IPv6 已关闭；`respect-rules` 遵从路由，也不自动锁定某个出口。节点引导解析不能依赖尚未建好的代理。
- Tailscale／企业分域 DNS、系统回环解析器和代理退出后的解析依赖，要在改动前识别。不要为了检测分数统一替换它们。解析器的国家／ASN 标签只能作为线索，不能单独证明实际旁路。

### 故障定位：分层比较，保留 TLS 校验

参考[上游本机排障流程](https://github.com/DUNHKpcc/Claude-Guardian/blob/06fe998d753f697c47ae0b67be5fe91451532a1f/skills/claude-guardian/references/local-firewall-prompts.md)，对同一已批准的非 AI 目标依次比较：

1. 显式本机 HTTP/mixed 代理请求：检查代理入口及核心到节点的连通。
2. 经预期 TUN 的已知目标地址请求：如果确需绕过目标 DNS 做对照，使用可信且适用于该域名的地址，以及 curl 的 `--resolve` 保留原域名、SNI 和证书校验；明确这与自然解析路径不同。该对照应确认使用系统／TUN 路径而非显式 HTTP 代理，也不能据此称为物理接口直连。
3. 系统 DNS 查询：与核心和浏览器的结果分开。
4. 正常域名 HTTPS：结合退出码、HTTP 状态及当前路由判断。

以上差异用来缩小范围，不把单个错误码等同于唯一原因。上游示例的 `curl -k` 不纳入本流程；参见 [curl 的 --resolve](https://curl.se/docs/manpage.html#--resolve) 和 [TLS 校验说明](https://curl.se/docs/sslcerts.html)。已有绑定一致的成功证据直接复用，避免反复重跑整套。

仅在 Windows 防火墙确实参与故障时，读取 WFP 或 Security 5157 的程序、方向、协议和过滤器线索。[Microsoft 5157 说明](https://learn.microsoft.com/en-us/windows/security/threat-protection/auditing/event-5157)定义的是连接被阻止事件。权限错误、无输出文件、解析失败、审计未开启与“未找到匹配事件”分别记录；暂时启用审计属于设置变更，按现有授权范围保留原值并恢复。原始安全日志仅留本机。

## 第三方检测报告：先检查生成逻辑

本轮阅读的 [network_check.py](https://github.com/DUNHKpcc/Claude-Guardian/blob/06fe998d753f697c47ae0b67be5fe91451532a1f/skills/claude-guardian/scripts/network_check.py)与 [egress_verifier.py](https://github.com/DUNHKpcc/Claude-Guardian/blob/06fe998d753f697c47ae0b67be5fe91451532a1f/skills/claude-guardian/scripts/egress_verifier.py)存在以下证据边界。导入它们的报告时，不能把 `pass`／`established` 直接映射成本 Skill 的“已完成”。

| 上游当前做法 | 本 Skill 的处理 |
| --- | --- |
| `--proxy` 只增加一次显式代理请求；主流程仍使用原生 socket 做 IPv4、IPv6、DNS、STUN 检查 | “原生 socket”可能经 TUN，也可能未被接管；先核对实际路由。运行范围不能只披露本机代理请求 |
| `check_ipv6` 将连接、解析、HTTP 或响应解析错误归为通过；返回 IPv4 也记为不可达 | 只记录本轮未取得有效 IPv6 出口；错误不证明已禁用或已阻断 |
| STUN 两次超时记作 blocked，展示文案称不会泄漏 | 无响应保留未完成，需要有效对照及对应策略／流量证据；不替代实际浏览器 WebRTC |
| DNS 按解析器国家标签判定；Fake-IP 被描述为已接管系统 DNS | 分开记录地理标签、映射事实和实际解析路径，不相互代证 |
| 停核心后一次出口请求报错、恢复后成功，即记为 no_direct | 只能说明那次请求失败且后来恢复；故障是否发生、尝试走哪条路、是否确有阻断还需独立观察。保留用户手动停止／恢复控制通道的要求 |
| 同一个终端探针经 `--proxy` 得到的样本，被标成 `other_app` | 仍属于同一测试进程的另一入口；不能作为 Claude／浏览器已经采用代理的第二应用证据 |

该脚本的固定外部目标含 `ipinfo.io`、`api6.ipify.org`、`bash.ws` 及其动态 DNS 子域、`stun.cloudflare.com:3478`。这里只披露代码范围，没有执行检测。未来若另行使用，先展示当时版本的站点、原生／代理路径、地址族、数据流和故障动作，再按现有确认规则操作；不沿用本次资料审阅作为联网许可。

故障演练和持续防直连仅在用户需要时另定范围。正常配置不自动安装 LuLu、不将系统默认出站改为拒绝、不部署回滚定时任务，也不停止当前 Codex／远控通道。同一事件的有效证据可以复用，但终端请求、文件读回和浏览器业务请求不得互相冒充。

## 保留为社区观点的内容

**时区已纳入本包完整配置的默认方案**，具体见 [时区目标与验证](timezone-policy.md)；它作为配置偏好执行，系统语言继续保留。

[上游手机指引](https://github.com/DUNHKpcc/Claude-Guardian/blob/06fe998d753f697c47ae0b67be5fe91451532a1f/skills/claude-guardian/references/mobile-guidance.md)中的 Android 拔 SIM、固定账号使用节奏、设备封号数量阈值，以及第三方检测必须全绿，不加入本 Skill 的默认要求。它们没有在本轮获得足以确立“防封”因果的官方证据。UDP 和设备范围仍按用户目标处理，检测分数不作为账号安全结论。

复查此来源时重新固定仓库提交，优先检查上述能力与判据是否已变化；过往结论只适用于记录的版本。


## 全仓核对新增的能力边界

固定提交全仓 **209 个文件**已完成静态审阅，含测试、打包、CI、历史记录与全部随附资料；19 份 PDF 共 **139 页**已逐页阅读提取／OCR并做视觉复核。原始模糊小字和缺少原始测量数据的图表保留资料质量限制，未逐个数值认证。未执行上游代码、测试或 PDF 中的命令。



- **能力名、文档和实现分别检查。** 当前 README、部分 repair 注释、旧环境入口和规则扩展文档存在版本漂移；以固定提交的实际调用链和对应测试范围判断。GUI 进程前后检查是检测，不等于持有并发写入排他锁。只读库或候选生成器不自动具备原生执行能力。
- **第三方许可记录不是授权凭证。** `interview_flow.authorization_check` 的 A 类分支未核对动作是否在允许集合，部分状态未参与检查；原生清理宿主缓存按动作组／目标而非完整变更摘要。JSON、TTY 短语或返回 `allowed` 都不能替代当前会话的具体授权。本 Skill 继续复用有效授权，按实际变更范围判断，不导入其庞大状态机或重复审批。
- **报告必须绑定同一目标和状态。** 当前上游面板合并网络报告时缺少与主报告的目标／平台一致性检查；固定“24 小时内”也不代替配置、入口和网络未变的核验。错误或缺数据不能填成零、空集或通过。
- **清理和恢复需要内容与对象一致。** 备份哈希、当前源内容、相对路径及目标身份应在相关阶段验证；大小／mtime 相同不保证内容相同。上游部分原生状态修改未沿用事务库的路径和并发保护，不能直接移植。清理只按 [精确规划](incident-and-cleanup.md)进行。
- **防火墙脚本暂不接入。** 上游 VM／VPS 的保险丝会删除规则表，但没有完整恢复旧表与持久化服务；VM 刷新还存在参数持久化和权限问题。VPS guard 仅有入站链，不能当出站防直连。具体部署需重新设计原值恢复、服务状态、独立救援和运行验证；不凭“脚本有 rollback”就标可恢复。
- **LuLu 和 Windows 防火墙按真实能力评估。** 上游将 LuLu Block Mode 简化为只拒未匹配规则，与 [LuLu 官方说明](https://objective-see.org/products/lulu.html)不符；其网络扩展也存在覆盖边界。Windows 默认出站 Block 不撤销已有 Allow，必须核对有效规则。对明确 IPv4-only 目标按精确接口处理依赖，参照 [微软 IPv6 说明](https://learn.microsoft.com/en-us/troubleshoot/windows-server/networking/configure-ipv6-in-windows)，不要额外引入全局注册表禁用。
- **历史测试数量不转成现行设备通过。** 部分测试只锁定作者偏好文案或使用合成枚举；ADR-039 的“持续保护已检查”同时注明对应演练未做，且原始资料未随仓库提供。保留作者报告的具体范围和未知，不继承其整机安全结论。用户事实和第一手描述可作为调查线索，仍需区分观察与因果，不遵循上游要求把经验直接说成确定事实的写作规则。
- **资料与包版本可追溯。** 原始 PDF、分发压缩副本、辅助提取稿与新版派生指引分别标识；哈希相同证明字节一致，不证明内容正确或仍然有效。公开 Wiki 的链接可能仍指向 main，技术依据优先固定提交。打包的成员清单和无用户数据检查值得复用，不能因来源已收录就自动安装或运行。

### WebRTC 检测可吸收的设计

上游的 [本地页面](https://github.com/DUNHKpcc/Claude-Guardian/blob/06fe998d753f697c47ae0b67be5fe91451532a1f/skills/claude-guardian/assets/webrtc-probe.html)和 [回环服务](https://github.com/DUNHKpcc/Claude-Guardian/blob/06fe998d753f697c47ae0b67be5fe91451532a1f/skills/claude-guardian/scripts/serve_webrtc.py)提供可参考的设计：固定页面、仅回环监听、有限生命周期、Host／Origin 约束，加载时不探测，明确范围后才启动一次 STUN 采样；无需摄像头或麦克风。

“本地页面”不等于离线：启动会联系指定 STUN 服务。记录实际浏览器、档案、origin、地址族、候选类别和错误／截断；参考出口只用于同地址族比较。同地址、无候选或 701 都不足以确认整个媒体路径。关闭提供页面的本地服务器也不能撤销浏览器已经加载的脚本，结束时还需终止采样／关闭对应测试页。当前只吸收设计要求，不安装该服务器或页面作为默认依赖。

### 检测材料本身的质量

检测工具超时、API 限流、缺依赖、OOM 或子测试未完成时，记录该检测失败及已取得的有效样本，不填成零值或通过。采样期间的压测／下载／资源不足可能污染结果；必要时在同口径、独立时间窗复测，并保留样本数、方向、协议／地址族及单位。多篇文章重复使用同一横评或曲线仍是一份原始证据。

本地浏览器查询远端 IP 的分类／信誉，只能说明查询对象；要证明流量从该出口发出，仍需在实际目标机／客户端获取关联样本。多来源分数方向、缺失字段和冲突分别说明，不合成没有定义的“纯净度”。历史解锁截图和没有登录的探测也不代替真实账号功能。
