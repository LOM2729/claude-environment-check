# Claude 环境完整方法：默认、可选、未验证与已纠正

这是两份 Skill 的统一方案分类入口。用于完整方案、全部方法、CCBaga 比较及历史未验证项展示；普通局部任务只读取对应模块。分类入口于 2026-11-10 补充来源流程；既有默认与历史实测仍各按原日期记录，不把本页整理当新实测。

2026-11-11 已按我方 v0.18.0 与 Guardian 最新整机模式更新能力口径，完整剩余差距和验证范围见 [本轮来源对照](source-gap-review-20261111.md)。历史方法已收录、CLI／桌面已实现与目标实机验收各自记录。

**仅修改 Skill、研究或展示清单时，只处理文件与资料，不运行真实环境采集、网络探测、浏览器／Claude 清理、登录、安装、重启或故障试验。** 以下保留以前研究但未采用的说法；“以前记录过”不能改写成“已在用户机器执行过”。

## “完整”的范围与来源方法

本页是方案分类，不等于所有来源文件均已读完，也不能替代具体步骤。此次补齐原先只有术语/链接的来源流程，详见 [实际阅读范围及映射](source-coverage.md)：

- [Guardian 网络与部署](source-methods-guardian-network.md)：IPv6、PF/Windows、Guardian Switch、S10 两机案例、VM/VPS、SSH/Realm/BBR、失败恢复和 PF 历史/最新验收分别记录。
- [Guardian 账号与清理](source-methods-guardian-account-cleanup.md)：注册订阅、手机、申诉、SIMPLE/bare、项目 purge、痕迹与集成清理，以及来源内部矛盾。
- [CCBaga 与三个清理 Skill](source-methods-ccbaga-cleanup.md)：按阶段部署、精确配置条件、身份迁移、三种 CC Switch 处理、六个隐私变量、共享历史保护与原始经验参数。
- [cc-hahaeasy](cchahaeasy-review.md)：官网 1.0.10 发布清单、完整公开教程、34 项自检、暂停/退出/恢复、条款例外与尚未取得的桌面实现证据。

这些来源路线作为**可选方法**保留；各作者的等待期、并发/触顶阈值、账号存活率为**经验或效果未证**，未被提升为默认。已纠正项保留原说法和具体反证。未读的附件/实现、部分源码和未做的真机验证在索引明确列出。

完整源码/附件补读后新增的可选流程、未证效果和已纠正解释统一见 [第二轮方法入口](source-coverage.md#第二轮补读已完成范围与新增方法)。源码覆盖阅读与目标机实测继续分开，默认配置选择未变。

## 分类与证据分开记录

| 方案分类 | 使用方式 |
| --- | --- |
| 默认方案 | 完整搭建中的既有选择与保留项；局部任务只取相关部分，用户明确范围优先 |
| 可选方案 | 有具体需求、故障或明确选择时才准备方案；不能因为列在目录中就默认开启 |
| 未经验证的做法与效果 | 分成“机制／实现存在，但目标效果待验”和“社区因果说法未证”；两类都完整保留 |
| 已纠正的说法 | 明确记录原说法与正确解释；不重新降格成“也许有效的可选方案” |

每项再独立标注证据：**机制明确**（官方／标准）、**源码确认**（固定提交静态阅读）、**局部证据**（限定版本与场景的历史测试）、**待验证**（缺实际目标证据）、**经验未证**（没有因果依据）、**已纠正**。默认／可选描述选用方式，不等于验证通过；来源、上游测试、文件读回、进程采用与真实功能不能互相代证。

向用户展示全部方法时，按本页四类列出；历史局部测试写清范围，未验证项不省略。制定执行方案时另标“本轮采用／保留现状／可选未采用／不适用”，不把这些选择标签当完成状态或批准记录。

## 默认方案

以下保持已有用户决定，不因参考新工具而自动改动。实际目标未取得证据的部分仍为待验证。

| 项目 | 既有默认 | 证据边界／详细入口 |
| --- | --- | --- |
| 使用位置 | 沿用现有本机和实际使用的客户端；区分 VM、WSL、SSH、容器、后台与出口位置 | 本机结果不代替远端，见 [执行位置](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/execution-paths.md) |
| 原有业务 | 保留有效代理、订阅、指定节点、企业网、LAN、会议／视频／远控及用户例外 | 不为了统一模板删除例外，见 [五步流程](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/five-step-setup.md) |
| 固定出口 | 使用指定稳定节点，不自动测速择优、轮换、负载均衡或回落 DIRECT | 同名节点仍可能按目的地采用不同公网出口，实际链路待验 |
| Claude 专属组 | Claude 组与基础组绑定同一具体节点 | 分组用于辨识，不代表使用不同出口；见 [服务路径](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/service-routing-checks.md) |
| 规则优先级 | AI 保护 → IPv6／明确拒绝 → 国内视频 → 其余 UDP 拒绝 → 普通国内直连 → 国外指定节点 | 以最终运行配置与进程连接为准，不只看候选文本 |
| 服务范围 | 第一方、内容／MCP、认证、CDN、安装更新与 Artifacts 共享依赖 | 按功能核验，不把共享域名全称为 Claude 核心必需 |
| 社区补充匹配 | Sentry／Statsig／Datadog／Intercom、选定关键词、IP／ASN／geosite 快照 | 会影响其他应用；非永久完整清单，见 [教程覆盖](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/tutorial-coverage.md) |
| IPv6 | 完整配置默认关闭选定接口及相关代理层 IPv6，保留已批准依赖处理 | 系统、入口、节点外层、目标侧分别验，不是官方通用防封条件 |
| UDP 与国内视频 | domestic-v4：AI 目标 UDP 拒绝；选定国内视频直连；其余 UDP 拒绝 | 视频名单含哔哩哔哩、抖音、爱奇艺、优酷的选定服务／CDN，不是所有国内平台；见 [UDP 策略](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/domestic-video-udp.md) |
| DNS 与联网顺序 | 先配置／读回 DNS、代理及非 AI 路径，再启动、登录或访问 AI | 节点引导、系统、核心、浏览器分别核对；见 [生命周期](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/lifecycle-checks.md) |
| 时间与语言 | 完整搭建把时区对齐指定稳定出口纳入方案；保留系统语言、输入法和键盘 | 时区、浏览器 Intl、UTC 校时独立核对；这是 [用户偏好](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/timezone-policy.md)，不是防封证明 |
| 实际认证 | 分清订阅、Console/API、网关／云平台，以及环境变量、配置根和启动入口 | 变量存在不等于生效，见 [客户端模块](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/client-cleanup.md) |
| 具体方案与恢复 | 准备原值、候选、影响、备份／恢复；需要确认时集中一次，已有批准不重复问 | [变更确认](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/change-confirmation.md)；维护 Skill 不触发设备操作 |
| 控制通道 | 不自行重启会中断 Codex／远控的代理、核心、服务或机器 | 按 [手动交接](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/five-step-setup.md#客户手动重启与恢复) 保存进度与离线恢复 |
| 验收与交付 | 默认验证本轮实际入口的正常使用，按影响复用有效证据，报告未完成及原因 | 其他生命周期事件按需选择；当前正常不等于持续故障保护 |

## 可选方案

这些是可按需选择的方法，不是必须逐项执行的清单。已有网络、语言和时区保留项继续有效；冲突方案先说明，不能叠加互斥配置。

### 网络、连接与系统

| 可选方法 | 用途与范围 | 限制／入口 |
| --- | --- | --- |
| DNS 分层调整 | 系统 DNS、代理 DNS、浏览器 DoH、Fake-IP／真实 IP、节点 bootstrap、TCP／UDP 53 接管 | 各层独立取证，见 [DNS 分层](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/customer-setup.md#dns分层查不用一个开关代表全部) |
| TYPE64／65 过滤 | 特定兼容性或解析问题；Mihomo 对应解析器参数、小火箭相关开关 | 非默认全关；需已知可返回记录的对照，不能混淆 DNS64 |
| DNS64 调整 | IPv6-only／NAT64 兼容问题 | 先确认依赖，移动网络可能需要它 |
| WebRTC／STUN／QUIC 限制 | 限制非代理 UDP 或特定媒体／HTTP3 路径 | 需评估通话／共享影响，禁 UDP443 不覆盖所有 WebRTC |
| 旁路核查与修复 | NO_PROXY、PAC bypass、skip-proxy、bypass-tun、TUN 排除、Global／Direct 模式 | 仅修已定位问题，保留业务例外；见 [服务路径](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/service-routing-checks.md) |
| 外层 TLS Chrome 指纹 | 适用节点协议与核心版本的握手参数 | 不改变 CLI 内层 TLS；效果待验，见 [连接设置](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/connection-reuse.md) |
| TCP keepalive | 保活与失效连接发现 | 与 HTTP 连接池／HTTP2／MUX／SMUX 分开，不默认全部开启 |
| UDP NTP 校时例外 | 当前限制与实际校时需求冲突时准备精确方案 | 当前 UDP NTP 代理明确未完成，不能全局放开 UDP 或宣称隐藏时区 |
| 分层对照排障 | 显式代理、保留 TLS 的地址对照、系统 DNS、正常 HTTPS；Windows WFP／5157 | 不采用关闭 TLS 校验的捷径，见 [Guardian 分层方法](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/guardian-integration.md) |
| 持续出站防护 | LuLu、Windows 出站策略、macOS PF、Linux nftables／guard | 当前已有独立 guard 与恢复模块。默认国内／视频动态分流尚未自动衔接，真实防护效果待目标机验收 |
| 自动回滚任务 | 高影响网络变更的恢复辅助 | 存在不等于有效，上游旧规则恢复／持久化有缺口 |
| 系统地区／语言／定位 | 用户明确需要时更改体验或权限设置 | 默认仍保留语言；时区、地区格式、校时、定位分开 |
| 线路优化 | 中转、SSH 动态转发、透明转发、BBR／TCP 参数 | 先有同条件基线；不保证通用收益，见 [路线规划](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/deployment-routes.md) |

### 浏览器、客户端与清理

| 可选方法 | 范围 | 限制／入口 |
| --- | --- | --- |
| 独立资料／临时对照 | 普通浏览器 Profile、无痕、临时禁用相关扩展 | 本地隔离或诊断，不保证指纹／远端身份隔离 |
| 浏览器语言／时区／定位 | 分别调整网页首选语言、界面语言、Intl 时区及站点权限 | 改设置的机制与防封效果分开 |
| 单站点数据清理 | Cookie、Local／Session Storage、IndexedDB、Service Worker／Cache Storage | 按资料、origin、分区和数据类型处理，见 [浏览器清理](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/browser-cleanup.md) |
| PWA／扩展／本机桥接 | PWA 所属资料、扩展存储与权限、Native Messaging | 网页清理不等于卸载扩展；共享服务分区不能一并删 |
| 全资料重置 | 密码、书签、历史、扩展、设置与网站登录 | 单独列出损失与恢复条件，不作为单站点故障的自动下一步 |
| 账号与订阅准备 | 官方网页、Apple／Google Play、订阅与 API／云平台选择，原订单、权益、续费、恢复购买与支持 | 按真实用途和当前官方规则，已有账号不重注册；见 [账号准备](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/account-preparation.md)、[账单核对](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/billing-checks.md) |
| CLI 认证修复 | 环境覆盖、实际 CONFIG_DIR、Keychain／凭据文件、profile／provider、官方登录退出 | 退出可能影响 MCP／插件；本地删除不等于服务端撤销 |
| CLI／Desktop 缓存 | 目标版本确认可再生的资源、图形、状态及必要诊断对象 | 不按 cache／debug／telemetry 名称批量判断可删 |
| 用户历史／工作材料 | projects、sessions、history、file-history、plans、uploads、tasks、快照／反馈等 | 含真实工作成果，默认保护；见 [客户端清理](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/client-cleanup.md) |
| 配置与扩展能力 | settings、Skills、commands、agents、hooks、MCP、plugins、项目配置 | 清缓存或卸载不自动包括这些对象 |
| 账号字段／本地设备记录 | 指定账号缓存、userID／machineID／anonymousId、应用设备记录 | 仅明确隐私／迁移目标下讨论；去关联／防封效果未证，不默认轮换 |
| Desktop／Cowork 重置 | 持久数据、会话、技能、工作文件、任务导出及当次重置提示 | 可能涉及云端删除；Safe Storage 不作普通缓存 |
| 卸载／重装 | native、npm/bun、Homebrew、WinGet、Desktop、IDE／浏览器集成与自启动 | 多入口、共享状态分别处理，卸载与删用户数据分开 |
| 备份恢复／历史备份整理 | 私有一致性备份、哈希清单、隔离、冲突保护与限定恢复 | 不能整树覆盖后续编辑；旧备份可能是唯一恢复证据 |
| Windows 应用修复 | 安装方式确有“修复”入口时使用 | 修复不等于重置，不保证修好或无数据影响 |
| 遥测／非必要流量控制 | 按目标版本官方开关决定需要关闭的具体类别 | 不等于隐匿身份、退出认证或删除云端历史 |

### CCBaga、身份迁移与部署

[CCBaga 完整能力表](ccbaga-methods.md)保留逐项参数、源码链接和平台限制；下列**全部属于可选工具路线**，其源码确认不能升级为我方真机验证。

| 可选路线 | 包含方法 | 必须区分 |
| --- | --- | --- |
| 安装 A／B | 原生宿主、Fingerprint Chromium、独立资料、默认浏览器与分平台更新 | Mac 打开 A 可启动 B；支持架构、签名、固定引擎补丁范围另核对 |
| 指纹与地区 | seed、Canvas／ClientRects、语言／时区、代理、定位、13 个地区预设、美国出口自动对齐 | 保留真实 OS／CPU／引擎；font/audio/GPU spoofing 当前关闭；快捷轮换会清显式代理并重启 |
| 浏览器三类清理 | 仅缓存、扩大站点数据、整个当前身份资料重置 | 不等于普通 Chrome 单站点清理；删除路径无自动备份，全部重置会删密码／书签等 |
| 身份管理 | 原地保存、更新归档、切换、空白身份、分类保留、加密保险库、失败回滚／中断恢复 | 默认目录范围、凭据和 Safe Storage 影响需明确，不代表服务端换身份 |
| 身份删除与跨机迁移 | 当前身份直接删除、删除保存卡片、同 OS 密码保护导入／导出 | 直接删除不先归档；身份包可含登录材料，浏览器迁移只带可选指纹设置；可能重登 |
| 进程与程序维护 | 精确识别 Claude 进程、停止、卸载／重装 CLI | 可能强制终止并中断工作；保险库、程序、配置与历史互不自动包含 |
| VM 路线 | Omarchy／macOS 等客机、NAT／桥接／host-only、快照与受限共享 | 客机不自动产生独立公网出口；架构／镜像／桌面／恢复另验 |
| VPS 开发机 | 远端 Claude、Xvfb／noVNC、Remote-SSH／tmux | 与 VPS 仅作代理出口不同；管理入口、重启／OOM／任务恢复另验 |
| CCBaga 网络部署 | Debian 12/13、SSH 密钥、Reality/VLESS → VPS → 住宅 SOCKS5、Mihomo TUN | 系统升级、SSH、防火墙、自动更新、BBR 等连带影响分别列出 |
| 订阅与供应链 | SSH 取私有 YAML、HTTP 订阅、远程安装器与版本选择 | HTTP token 不提供 TLS；固定主仓不等于固定远程 main／latest 依赖 |
| 检测与生命周期 | 官方域名探针、出口／环境体检、服务端自检、客户端更新／重启／睡眠／换网／故障复查 | 每项覆盖范围独立；全绿／服务端通过不代替真实客户端与故障验收 |

## 未经验证的做法与效果

### 有机制或实现，但实际目标仍待验证

下表保留历史证据的准确边界，不把所有东西说成“完全没测”，也不把局部测试当全量通过。

| 项目 | 已有依据／局部证据 | 仍未证明或未完成 |
| --- | --- | --- |
| 固定节点、分组与域名扩展 | 已选方案、生成器及静态审计 | 目标进程实际采用、所有目的地出口一致、未来域名与任意 MCP／网关覆盖 |
| domestic-v4 与国内视频 | 有限定核心的合成 loopback 测试 | 目标 TUN／防火墙／真实 UDP、真实视频与节点传输；播放可能只是 TCP 回退 |
| Mihomo 初始化 | 记录过 v1.19.32 合成测试中监听早于两份 inline provider 就绪 | 客户端版本的初始化行为与首个真实请求，不能仅凭端口监听通过 |
| 小火箭 | macOS 2.2.92（3445）合成配置导入／编译／读回；节点只到 loopback，未启用 | 真实 UDP/TCP、视频播放、iOS／iPadOS；Mac 文本生成不代 Windows／手机 |
| IPv6 各层 | 有接口／核心／DNS 检查方法 | 本机入口、节点外层、目标侧与全部旁路，不能用单次超时代证 |
| DNS、TYPE64／65、DNS64 | 有标准／产品机制 | 真实浏览器解析路径、已知对照；小火箭两项参数的版本优先级与共同效果 |
| 外层 TLS、连接保活 | 有适配检查与候选能力 | 目标采用、稳定性／性能收益、HTTP 连接实际复用；不能推内层 TLS 改变 |
| UDP NTP | 当前策略明确拒绝该流量 | **UDP NTP 代理未完成**；实际系统校时与所需例外另核对 |
| Clearpath | 有历史接口研究、模拟及部分历史浏览器实测 | 不据历史 0.7.1 记录断言当前已上线、当前目标或 Windows 通过 |
| DNS／STUN／IPv4／IPv6 多来源 | 有限定采样方法与历史结果 | 无响应原因、实际公网路径、所有查询覆盖；多个来源不自动构成独立安全证明 |
| IP 类型、ASN、Emoji、请求摘要 | 数据库分类与检测页局部读数 | 家宽／独享真实性、字体真实来源、Claude 实际所见及其账号处理 |
| CCBaga 环境全绿 | 源码确认比对项与回传条件 | 不检查账号状态、模型功能、Canvas 有效性或独立 DNS／WebRTC 泄漏 |
| CCBaga 指纹引擎 | 固定版本、哈希及上游交付记录 | Chromium fork 的安全回补覆盖、目标版本兼容性与识别效果 |
| CCBaga 身份与跨机恢复 | 有真实归档／恢复实现和上游测试记录 | 本机恢复、自定义 CONFIG_DIR／Console profiles、Keychain／DPAPI 与服务端有效性 |
| 文件事务与恢复 | 临时文件、合成事件的工具测试 | 应用重新载入、系统设置／网络恢复、登录有效；不覆盖浏览器数据库或云端恢复 |
| Windows 全流程 | 有原生 NTFS 隔离引擎、8 项临时目录测试及构建 CI | **无完整端到端真机证据**；桌面隔离适配器、真实用户目录、企业策略和网络仍待分别验收 |
| VM／VPS 与线路优化 | 有我方受限远端模块、既有方法与上游记录 | 真实部署、管理恢复、住宅出口、完整 VM／VPS 安装、客户端 TUN、BBR／中转收益 |
| 出站防火墙／回滚任务 | 有我方 guard、超时恢复和持久化管理实现及相关夹具 | 有效规则完整读回、既有 Allow、管理例外及真实失联／重启恢复，详见本轮对照 |
| 后续七类事件 | 有事件模型和合成验证 | client_update、proxy_update、client_restart、system_restart、sleep_wake、network_change、proxy_fault_recovery 未发生／未观察就保留未完成 |
| 持续保护 | 有启动前检查与可选原生防火墙 guard，远端另有受限核心自愈 | 跨客户端持续出口监测、默认策略的整机衔接和故障期真实保护仍待补齐，不保证检查与启动之间无竞态 |

历史依据：[教程覆盖](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/tutorial-coverage.md)、[小火箭验证边界](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/shadowrocket-domestic.md#测试与报告边界)、[检测工具记录](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/score-check.md)、[恢复与生命周期](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/recovery-and-acceptance.md)、[Guardian](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/guardian-integration.md)。没有新实测时，不更改这些状态。

### 社区经验与因果效果未证

下列以前提过但未证明有效或未采用为默认；完整展示时必须保留。机制确实能改某个值，不等于能降低封禁概率。涉及账号／付款的说法只记录和评估，不变成虚构资料或反复开户的操作流程。

| 原有做法／说法 | 当前标注与处理 |
| --- | --- |
| 静态住宅、原生、独享、家宽 IP 提高账号权重 | 经验未证；网络稳定性与账号因果分开 |
| 固定一个出口、减少切换就能防封 | 可测稳定性，防封因果未证 |
| 注册前几天决定以后命运 | 经验未证 |
| 新电脑比旧电脑安全 | 个案，经验未证 |
| 封过三个账号就换设备 | 经验阈值未证，未设为默认 |
| 老邮箱、长期邮箱、购买教育邮箱更安全 | 经验未证，不作为开户或采购要求 |
| 换 Proton 降低 Claude 封号 | 邮件防跟踪有机制，封号效果未证；Gmail 图片代理也不能推出账号安全 |
| 英文系统／浏览器比中文安全 | 经验未证；已有个案中文可用 |
| 语言、地区、时区与 IP 一致就安全 | 可核对一致性，不提供账号安全保证 |
| Android 拔 SIM 更安全 | 上游经验，未证 |
| 指纹浏览器／换 seed／Canvas／ClientRects 扰动可防关联 | 部分源码存在，服务端效果未证 |
| 清 Cookie、缓存、旧账号字段可以洗环境／恢复权重 | 只确认所选本地状态变化，远端效果未证 |
| 删除设备 ID／UUID 就是新设备 | 本地记录变化不等于硬件密钥或服务端设备记录变化 |
| 删除字体、改变 Emoji 能降低风险 | 经验未证；不是按检测扣分改系统的理由 |
| 删除 IP 查询历史、代理／VPN 日志能降低风险 | 经验未证；隐私整理另有目标与保留范围 |
| 关闭遥测就不会被识别 | 目标版本开关作用需核对，身份隐匿推断未证 |
| Free 等 3 天、Pro 等 15 天再升级 | 未证的固定等待阈值 |
| 新邮箱必须养固定天数 | 经验未证 |
| 先聊几次、隔一天再订阅／升级 | 经验未证 |
| 每周打开一次 App | 未证，不作使用门槛 |
| 禁止 workflow／自动化更安全 | 未证，按实际服务规则和用途判断 |
| 新账号只能 1–3 并发、单 IP 不超过 5 并发 | 非已证实通用安全阈值；真实限流按响应／额度／负载判断 |
| 某套餐档位或付款渠道更不易封 | 社区推测，未建立因果 |
| 不辱骂、不强迫突破拒绝、不索取内部思考降低封号 | 作者建议，不把该因果当已证实；官方服务规则另核对 |
| 所有检测必须全绿 | 无依据作为账号安全门槛 |
| KYC 出现就弃号／重注册 | 原资料出现，未采用为修复；官方验证／申诉另处理 |
| 伪装账单地区与出口一致就能通过 | 无可靠保证，不能代替真实资料要求 |
| 礼品卡一律免绑卡／免地址 | **已有官方反例，通用说法已纠正**，见下表 |
| 退款一定成功、稳定率高、固定时间到账 | 无通用保证；按真实订单和当前规则处理 |
| BBR／缓冲参数必然提速 | 有配置机制，具体链路收益未验 |
| 加密保险库完全隔离同用户其他程序 | 加密／权限有作用，绝对隔离说法不成立 |
| 跨设备导入一定免登录 | OS 绑定、账号状态、过期／撤销均可能导致重登 |

出处：[原帖主题核对](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/guided-workflow.md)、[账号准备](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/account-preparation.md)、[来源记录](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/evidence-sources.md)、[CCBaga 固定源码](ccbaga-methods.md)。以上是截至本次记录的范围，不宣称穷尽互联网所有说法。

## 已纠正的说法

原说法可能是机制混淆、错误推断或被官方反例否定。再次遇到时直接使用右栏，不把左栏包装成可尝试的有效方案。

| 原说法／错误推断 | 正确解释 |
| --- | --- |
| 代理 NTP 能隐藏或改变系统时区 | NTP 同步时钟，系统时区是另一层；当前 UDP 策略还未实现 UDP NTP 代理 |
| TYPE64 就是 DNS64；TYPE65 是端口 65 或跟踪器 | TYPE64 是 SVCB，TYPE65 是 HTTPS 记录；DNS64 是地址合成机制 |
| no-resolve 是反向 DNS 防泄漏开关 | 控制相应 IP 规则是否触发目标解析，不是通用防泄漏开关 |
| 外层代理 Chrome TLS 指纹会改变 CLI 内层 TLS | 是不同连接层，不能由外层字段推断内层握手 |
| TCP keepalive 等于 HTTP／HTTP2 连接复用 | 保活、HTTP 连接池与多路复用是不同机制 |
| AAAA 为空、IPv6 请求超时就证明整机 IPv6 关闭 | 仅是该次解析／请求观察，其他地址来源、入口及层次仍需取证 |
| STUN 超时、网页打不开就证明没有直连 | 也可能是服务失败、解析失败或整机断网；需有效观察和对照 |
| 内网地址、链路本地地址或 mDNS 候选就是公网 IP 泄漏 | 必须区分候选类型与已核对公网基线 |
| 解析器国家／ASN 不同就证明绕过代理 | 地理／组织标签不能单独证明请求路径 |
| Fake-IP 答案证明真实上游已解析、路由正确 | 只证明当前映射结果；真实解析与连接路径另验 |
| 配置正确、端口监听就证明应用已载入并采用 | 文件、核心就绪、进程采用与端到端功能分别确认 |
| 节点不回落 DIRECT 就等于核心退出后全机断网保护 | 规则只覆盖进入该核心并匹配的请求，系统级故障另验 |
| 入站防火墙能证明出站固定；Windows 默认出站 Block 覆盖全部已有 Allow | 入站与出站不同；既有放行、管理例外和规则优先级需核对 |
| 只禁 UDP443 就控制所有 WebRTC；开启 TUN／any:53 就覆盖所有 DNS | 端口、协议和进程范围不同，不能据单字段推全部路径 |
| CCBaga 选择国家就改变公网 IP，且随机化全部指纹 | 地区选择不换 IP；该版本保留真实 OS／CPU／引擎并关闭 font/audio/GPU spoofing |
| CCBaga 时区同时写入 Preferences | 已核对版本通过 --timezone 传入；Preferences 另处理语言、WebRTC、定位等 |
| CCBaga 所有清理都先备份；B 的清理等于普通 Chrome 单站点清理 | 身份切换归档与直接删除是不同路径；B 只处理其独立资料，部分路径永久删除无备份 |
| 加密身份包／独立资料能保证去关联或绝对隔离 | 只提供对应本地存储与权限机制，不保证远端或同用户程序完全隔离 |
| 本地清凭据就等于服务端会话撤销 | 删除本地副本和服务端撤销是不同动作 |
| 本地备份能撤销云端删除，恢复文件一定恢复有效登录 | 云端数据、OS 加密绑定、会话过期／撤销不由文件恢复保证 |
| Reset App Data 永远只清本地缓存 | 2026-11-03 官方变化已说明部分确认流程会删除云端 Cowork 任务；执行看当前版本与确认框 |
| HTTP 订阅有随机 token 就是加密传输 | token 控制访问不提供 TLS，优先受支持的加密交付 |
| 固定主仓提交／下载哈希匹配就代表所有依赖固定且无漏洞 | 远程 main／latest 及 fork 安全补丁覆盖需另核对 |
| 礼品卡余额一律免绑卡／免地址 | 官方说明部分购买仍可能需要登记付款方式，不能作通用承诺 |

原始依据分布在 [DNS 与协议说明](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/customer-setup.md)、[服务路径](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/service-routing-checks.md)、[检测分数](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/score-check.md)、[客户端清理](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/client-cleanup.md)、[账号准备](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/account-preparation.md)、[CCBaga 源码核对](ccbaga-methods.md)。纠正的是这里列明的解释，不把真实可用的诊断或配置机制一并否定。

## 如何组合成实际方案

执行顺序只在 [五步流程](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/five-step-setup.md) 维护；本页是分类与选择依据，不提供第二条相冲突的自动执行顺序。

1. 依据用户目标选默认范围及必要可选项，保留指定语言、节点、业务和其他明确保留项。纯清理不展开整机重配；CCBaga 替代路线不与现有网络配置盲目叠加。
2. 准备阶段完成离线盘点、候选、备份与精确影响清单；清理缓存、退出登录、身份迁移、卸载、历史／云端删除分别选择。一个组合按钮的副作用也全部列明。
3. 先给具体方案，需要确认时集中确认；已有明确授权范围连续执行。未证效果如实展示，已纠正说法不能作为实施理由，目录／源码／历史报告不授予操作许可。
4. 网络配置和非 AI 路径核验在前，客户端启动／安装／登录／实际 AI 请求在后；离线清理按其自身条件处理，重启与首次联网仍遵守网络门槛。
5. 只报告实际完成与未完成及原因。每项分别注明文件、应用、进程、功能和事件覆盖；历史局部测试不升级为本轮或跨平台通过。用户只要说明或修改 Skill 时，停留在文件与资料层。

完整对象和操作细节按需读取 [浏览器清理](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/browser-cleanup.md)、[客户端清理](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/client-cleanup.md)、[CCBaga 参数与源码](ccbaga-methods.md)、[恢复与验收](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/recovery-and-acceptance.md)。分类变化需有新证据或用户新选择；不得为了让清单好看而把“待验证”改成完成。
