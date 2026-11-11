# Claude-Guardian、CCBaga 与 v0.18.0 的剩余差距

核对日期为 2026-11-11。本次验证方式为固定版本源码审阅、现有方法库对账及既有发布测试证据复核。实际设备操作、目标网络和账号效果继续按各自证据记录。

后续采用方向已由用户确定为直接使用两平台 Skill。本轮收整了 Skill 的分项清理、浏览器原生操作、系统设置、续接、回执恢复与事件复查方法，旧桌面应用转入历史归档。下面的桌面差距表保留 v0.18.0 审阅时的事实，后续操作以当前 Skill 和随包能力为准。

## 版本与阅读范围

| 对象 | 本轮固定版本 | 与前次的关系 |
| --- | --- | --- |
| 我方工具与两套 Skill | `8c689a5fa32cc79fd8767655d76d38eb702df527`，v0.18.0 | 以刚发布的实际源码为准 |
| Claude-Guardian | `62814950d30401ba5861beca67e6382b9fa112b6` | 相对此前 `e934166a…` 前进 4 个提交，23 个文件变化，新增 Windows 整机出口模式与覆盖检查 |
| CCBaga | `6db5ad55e799c5b020be8ff5e4def2c147cd5602` | main 未变，423 文件与既有全文阅读清单逐项 SHA-256 匹配 |

Guardian 的更新发生在我方 v0.18.0 发布之后。旧版全文记录保存在 [完整阅读清单](source-complete-read-manifest.json)，同 SHA 内容复用既有阅读证据。本轮复查当前入口、变更及其调用、恢复和验证分支。CCBaga 另外完整复读了四份既有专题，再核当前注册入口及直接实现。外部 Chromium 引擎、依赖本体和供应商后端的实现仍有独立边界。 [Guardian 固定版本](https://github.com/DUNHKpcc/Claude-Guardian/tree/62814950d30401ba5861beca67e6382b9fa112b6) · [CCBaga 固定版本](https://github.com/liseami/CCBaga/tree/6db5ad55e799c5b020be8ff5e4def2c147cd5602)

下文的“方法已收录”指 Skill／研究中存在说明，“CLI 已有”指随包存在相应执行接口，“桌面已有”指有可达交互入口，“待实机”指缺少相应目标设备证据。源码审阅得到的风险推论单列，实际发生情况仍需复现。

## 第一版已选需求的欠项

| 已选范围 | v0.18.0 当前状态 | 剩余交付及验证 |
| --- | --- | --- |
| 缓存、站点登录数据、Claude 登录态、历史和配置分项选择，默认缓存 | 桌面完成 Claude Code／Desktop 缓存预览、隔离、对账、恢复。CLI 对有限登录文件、历史和配置支持显式类别 | **桌面分项清理未完成**。需要类别勾选、准确影响与恢复说明。CLI 登录项目前整体隔离 `.credentials.json`，细粒度保留 MCP／插件秘密的编辑器待补 |
| Chrome／Edge 自动清理 | 已有按 Profile、站点、origin、数据类型划分的方法。WebRTC 检测已实现 | **普通浏览器指定站点自动清理未实现**。WebRTC 页面提供检测，站点登录清理仍通过方法指引处理 |
| 基础设置、已有代理规则、DNS、IPv6，预览备份后执行 | 候选配置、离线差异、精确文本事务、原值检查和 Skill 执行流程已存在 | **桌面完整原生配置闭环未完成**。系统 DNS、接口 IPv6、TUN／路由、时区的预览与原值备份、应用和恢复仍需整合。五步界面目前以导出、手动导入、文件读回和 Codex 交接为主 |
| Clash Verge Rev 覆盖 Mac／Windows，macOS 小火箭 | Mihomo／小火箭候选格式存在，macOS Clash 2.5.8、2.5.10 有窄规则写入与回滚 | **Windows Clash 和 macOS 小火箭的原生应用适配待补**。支持候选格式的证据只覆盖文件层，实际客户端载入与路由仍待验 |
| 双平台源码、测试和 Windows 构建入口，实机后补 | 已发布 Mac arm64、Windows x64 ZIP 与两平台 Skill 包，相关 CI 已有通过证据 | **源码与构建交付完成，目标设备验收待补**。Windows 8 项 NTFS 测试覆盖隔离引擎。桌面适配器测试类仍限于 POSIX，Windows 桌面选择目录到恢复的完整链另需验证 |

上述属于先前已选需求的实际欠项。依据为 [桌面清理入口](https://github.com/LOM2729/claude-environment-check/blob/v0.18.0/desktop/ui/index.html#L171-L200)、[固定缓存请求](https://github.com/LOM2729/claude-environment-check/blob/v0.18.0/desktop/operation_tools.py#L138-L169)、[CLI 数据类别](https://github.com/LOM2729/claude-environment-check/blob/v0.18.0/src/scoped_cleanup.py#L29-L36)、[平台能力声明](https://github.com/LOM2729/claude-environment-check/blob/v0.18.0/src/claude_setup.py#L25-L39)、[桌面适配器测试范围](https://github.com/LOM2729/claude-environment-check/blob/v0.18.0/tests/test_desktop_operation_tools.py#L25)、[Windows NTFS 测试](https://github.com/LOM2729/claude-environment-check/blob/v0.18.0/tests/test_scoped_cleanup_windows.py)。

## Guardian 新变化及系统防护差距

| 项目 | Guardian 当前能力 | 我方现状与缺口 | 证据状态 |
| --- | --- | --- | --- |
| Windows 整机出口模式 | 新增显式 `whole_machine`，按完整已审核出站 Allow 集合检查两种策略存储，普通 Claude 目录更新可沿用整机策略 | 我方已有三档默认出站阻止、非我方 Allow 审查、精确停用和恢复。需要逐字段补齐有效策略核对，应用更新后的保持范围需单独验收 | 上游源码与 CI 可核，双方真实 Windows 出口与业务效果仍待目标机验证 |
| 有效规则条件读回 | 逐条对照 PersistentStore、ActiveStore 与快照，包含 ICMP、动态目标和应用策略 ID 等条件 | 我方 `Rule-Record` 缺 `IcmpType`、`DynamicTarget`、`PolicyAppId`。owned 规则快照主要来自 PersistentStore，ActiveStore 的额外 Allow 核对主要保留名称。**同名有效规则条件分歧的完整检查待补** | **静态发现，未复现实机差异或泄漏** |
| Windows 更新与错误分诊 | 补充更新前、更新后首次联网和更新后验收，区分包内程序、包外 Code／Cowork，明确 Error 5、UDP Send 和 5157 的关联条件 | 我方有生命周期和一般 WFP 说明。上述三时点、协议／FilterRTID／测试时间的精确关联，以及有限权限错误分诊细节可补进专题 | **方法与验收细节待补**，当前新模式的 LAN 内容属于例外审阅，尚无专门自动生成 Windows Update 白名单的新增能力 |
| 日常防护控制面 | 提供 ON／OFF／status／uninstall、单独覆盖状态、首次快照和桌面入口。失败与 unknown 会阻止继续，恢复入口保留 | 我方 CLI 与可双击交接入口已存在，桌面主工具目前只生成包。还缺统一展示当前防护、开机状态、有效覆盖、最近操作与恢复的控制页 | 我方已有夹具与冻结包证据，实际 UAC／sudo／真实状态读回待验 |
| 正常停用前的应用核对 | `protected_processes` 检查相关应用仍运行时阻止正常 OFF／卸载 | 我方 Skill 有安全退出方法，正常停用尚缺桌面化的精确应用核对与确认。紧急恢复继续使用独立回滚流程 | **方法已收录，日常操作待补**。名称清单对未知 Helper／共享 Node 进程的覆盖仍需现场核对 |
| 默认国内分流与系统防护衔接 | 整机模式要求明确审核国内、LAN、虚拟机、Cowork、VPN 与远程例外，并说明 OFF 的影响 | 我方 guard 明确拒绝自动编译 `domestic-v4`。默认国内／视频动态规则与系统防护目前要分别准备方案。固定 IP／端口例外不能直接代替动态域名／视频策略 | **明确未支持自动衔接**，现有其他 guard 策略可单独使用，真实兼容性待验 |
| 更新、睡醒、换网和故障后的复查 | 更新说明明确何时无需重新绑定，策略／节点／网卡／例外变化要复核。Switch 按 status／ON／KEEP 检查 | 我方已有生命周期事件模型和证据审阅 CLI，桌面缺可采证的复查界面。跨客户端自动复查与持续出口监测待补 | Guardian 同样明确无新增常驻监控，当前读取不证明持续保护 |
| 真实路径驱动的验收 | 配置 pass 后仍要求 TCP／UDP、DNS、IPv6、WebRTC 与故障期观察 | 我方 guard／remote 的 observed 字段来自操作人，生命周期工具审阅外部证据。需要把实测采集与确认步骤接成可审核流程 | **已有证据结构，独立测量闭环待补** |

Windows 规则对照依据为 [上游条件与覆盖检查](https://github.com/DUNHKpcc/Claude-Guardian/blob/62814950d30401ba5861beca67e6382b9fa112b6/skills/claude-guardian/assets/killswitch/windows-switch.ps1#L21-L114)、[上游整机模式与例外说明](https://github.com/DUNHKpcc/Claude-Guardian/blob/62814950d30401ba5861beca67e6382b9fa112b6/skills/claude-guardian/references/killswitch-switch.md#L35-L54)、[我方规则快照](https://github.com/LOM2729/claude-environment-check/blob/v0.18.0/src/system_guard_windows.ps1#L73-L99)、[我方 domestic-v4 拒绝条件](https://github.com/LOM2729/claude-environment-check/blob/v0.18.0/src/system_guard.py#L159-L197)。

更新与停用的补充依据为 [更新和证据要求](https://github.com/DUNHKpcc/Claude-Guardian/blob/62814950d30401ba5861beca67e6382b9fa112b6/skills/claude-guardian/references/local-firewall-prompts.md#L197-L221)、[维护后的部署示例](https://github.com/DUNHKpcc/Claude-Guardian/blob/62814950d30401ba5861beca67e6382b9fa112b6/skills/claude-guardian/sources/S05-local-protection.md#L284-L350)、[正常 OFF／卸载前检查](https://github.com/DUNHKpcc/Claude-Guardian/blob/62814950d30401ba5861beca67e6382b9fa112b6/skills/claude-guardian/scripts/killswitch.py#L236-L249)。完整规则／网络证据的判定器仍依赖输入材料，探针错误、超时与真正阻断的解释沿用 [此前深入复核](guardian-review-20261110.md)。

## 桌面流程仍需补齐

| 项目 | 已有基础 | 剩余差距 |
| --- | --- | --- |
| 访谈续接 | CLI 状态模型和每版私有事实文件存在 | 桌面 token／revision 仅在内存，重开后缺少继续旧访谈、批量复用事实和编辑已有答案的入口 |
| 规则写入中断后继续 | 原计划、文本备份、回执、CLI check 与 rollback 存在 | 桌面未开放 native_check，不明确结果只显示保留材料。需要检查、识别精确回执和继续恢复的入口 |
| 旧操作管理 | 最近记录和每次缓存恢复说明存在 | 缺可浏览的历史记录列表、关联方案／回执／备份与准确恢复动作 |
| 计划准备与执行包交接 | 复制提示词让 Codex 准备计划，再选择 JSON 导出包 | 目标、影响、差异、恢复与模块选择尚未集成到桌面计划准备页，仍有跨工具交接 |
| 进度和客户端生命周期 | busy、最终结果、人工退出确认和隔离对账存在 | 缺完整维护进度、部分完成明细、保存任务后的精确退出和重开流程 |
| 更新展示 | 逐文件比较报告和摘要计数存在 | 桌面缺逐项差异审阅、保留本地二开、备份后安装和升级失败恢复的完整交互 |

依据为 [桌面访谈](https://github.com/LOM2729/claude-environment-check/blob/v0.18.0/desktop/toolbox.py#L18-L77)、[桌面内存状态](https://github.com/LOM2729/claude-environment-check/blob/v0.18.0/desktop/ui/tools.js#L24-L31)、[计划交接入口](https://github.com/LOM2729/claude-environment-check/blob/v0.18.0/desktop/tools-main.cjs#L103-L125)、[规则执行状态](https://github.com/LOM2729/claude-environment-check/blob/v0.18.0/desktop/operation_tools.py#L309-L369)、[现有 CLI check](https://github.com/LOM2729/claude-environment-check/blob/v0.18.0/src/native_client.py#L286-L310)。

## CCBaga 已收录方法中尚未做成产品的部分

下表是可选产品扩展及维护差异。Linux 桌面不在已选首版平台范围。

| 方法 | CCBaga 当前可达能力 | 我方实际状态及未验证部分 |
| --- | --- | --- |
| 细粒度认证清理 | 残留入口针对认证字段编辑，保留 MCP／插件秘密 | 我方有整体文件隔离与精确文本事务，专用字段语义执行器待补。实际目标版本、共享使用方与恢复需要验证 |
| Claude CLI 维护 | 识别来源并卸载／重装，部分原生路径预取安装器并备份 | 我方 Skill 方法已收录，桌面与通用维护执行器缺失。安装来源、程序读回和可恢复范围待目标机验收 |
| 浏览器／系统综合体检 | 比较出口国家、语言、时区、地区、OS、CPU、引擎和定位 | 我方本机有限采集和浏览器 ICE 检测已存在，完整跨层比较面板待补。任何绿灯与账号状态分别判断 |
| 时区与地区设置页 | 单项系统设置与组合地区动作 | 我方方法已收录，桌面缺原值、目标、影响、恢复和权限交接页。系统语言沿用用户已选保留范围 |
| 独立 Chromium／Profile | A 管理独立 B，各身份使用各自资料目录与浏览器参数 | 我方产品未实现独立 B 浏览器、资料与参数管理器。实际兼容性、安全补丁和服务端识别效果待验证 |
| 身份保险库与切换 | 加密归档、SQLite 索引、保留策略、切换与恢复 checkpoint | 我方有定向文件隔离恢复，完整身份档案与切换事务未实现。实际登录恢复及 OS 密钥仍待验证 |
| 加密跨机迁移 | 同 OS 的密码保护 `.bagapack`，导入新增卡片，浏览器部分只带可选参数 | 我方方法已收录，迁移包与导入器未实现。跨机有效登录、Keychain／DPAPI 绑定和失效令牌分别验证 |
| 自更新与签名链 | Tauri updater 验签下载、安装与重开，A/B 更新范围各自有边界 | 我方已提供 Release、SHA-256 和内置 Skill 一致性检查，桌面自更新、升级恢复、代码签名／公证待补。上游 Windows NSIS 仍有未做 Authenticode 的限制 |
| Reality／VLESS → 住宅 SOCKS5 | 独立 ccbaga-network 提供特定密钥／SSH 校验、部署、出口验证和配置 fetch | 我方已有 Linux core、SSH、反向隧道、核心自愈和入站防护。该 Xray 专用链路与三文件密钥校验、fetch 交付尚未完整实现，真实服务商／VPS／客户 TUN 待验 |
| VM／VPS 完整工作环境 | 相关方法涵盖客机、远程开发及维护组件 | 我方已有部分远端模块。VM 创建、noVNC、tmux、Realm／BBR 等整套安装与恢复仍以方法为主，目标部署与收益待验 |

来源包括 [CCBaga 认证字段清理](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/cleaner_residue.rs#L36-L64)、[CLI 维护](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/claude_cli.rs#L188-L222)、[浏览器验证模型](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/browser-verification.ts#L10-L38)、[身份切换](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/identities/mod.rs#L179-L246)、[迁移接口](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/identities/portable.rs#L421-L472)、[自更新](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/app-update.tsx#L29-L59)、[网络部署层](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/skills/ccbaga-network/scripts/network.py#L258-L309)。完整原方法及副作用仍见 [CCBaga 方法库](ccbaga-methods.md)、[原生机制](source-methods-ccbaga-native.md)、[维护与安装](source-methods-ccbaga-ui-maintenance.md)、[网络与清理路线](source-methods-ccbaga-cleanup.md)。

## 未验证项继续保留

| 对象 | 当前可复用的证据 | 尚待验证 |
| --- | --- | --- |
| 我方平台构建 | v0.18.0 三平台测试和两平台冻结后端／ZIP 构建通过 | 用户实际安装、权限提示与真实桌面完整流程 |
| Windows 隔离 | 8 项 NTFS 临时目录测试通过 | 实际 Claude 数据、真实写入者、Windows 桌面全链、企业策略和 MSIX 等未支持范围 |
| macOS Clash 规则 | 2.5.8／2.5.10 版本绑定、写入和回滚的合成测试 | 实际应用载入、进程采用、不同功能域名与有效路由 |
| WebRTC | 有当前 Profile 的 ICE 采样与脱敏报告实现 | 用户实际浏览器、参考出口、真实媒体选择、其他客户端和故障期样本 |
| PF／Windows Firewall／nft | 有独立执行与恢复实现、合成回执和状态验证 | 真实提权、既有策略、故障期协议路径、管理通道和开机恢复 |
| 生命周期 | 有当前使用、更新、重启、睡醒、换网、代理故障等事件模型 | 相应事件的目标观察、重新采证与端到端功能 |
| Linux 部署 | 有受限模块、导出、备份、回滚和核心自愈代码 | 实际 Debian／Ubuntu、依赖安装、SSH 第二会话、重启／OOM 与远端恢复 |
| 上游 CI／作者报告 | Guardian 最新固定提交的单测和合成页面 CI 为 success。CCBaga 保留固定版作者记录 | 本轮实际设备独立复现与跨版本／跨平台推广 |
| 指纹、清理和账号关联 | seed／Canvas 等参数、隔离／删除本地状态的机制可查 | 降低封禁、改变服务端关联、恢复所谓账号权重的因果 |
| 语言、时区、住宅出口、邮箱与套餐 | 可测设置、一致性与连接属性，原经验条件已保留 | 账号稳定性的因果、住宅独享真实性、通用套餐安全优势 |
| 等待期、并发、SIM、设备与日志 | 历史来源和具体阈值保存在完整方法中 | 3／15 天等等待、1–3 并发、拔 SIM、换设备／本地 ID／清日志等防封效果 |
| BBR／中转优化 | 可查具体参数与实现方法 | 当前链路同条件基线和实际收益 |
| 身份跨机恢复 | 上游有加密归档和导入实现 | 服务端会话仍有效、无需重登、OS 绑定秘密可恢复 |

既有验证来源为 [我方跨平台 CI](https://github.com/LOM2729/claude-environment-check/actions/runs/42927626591)、[我方发布产物校验](https://github.com/LOM2729/claude-environment-check/actions/runs/42928345455)、[Guardian 最新单测](https://github.com/DUNHKpcc/Claude-Guardian/actions/runs/42934607870)、[Guardian 合成面板](https://github.com/DUNHKpcc/Claude-Guardian/actions/runs/42934607909)。历史所有未证经验、参数和反例继续在 [完整分类](complete-environment-method.md#社区经验与因果效果未证) 保留。

## 本轮需要纠正的解释

- “七个专项入口已完成”只能对应各入口写明的范围。分项清理、完整系统配置和全部客户端适配仍有上述欠项。
- “当前完全没有系统防护”已过时。v0.18.0 有 guard 和恢复模块，默认国内策略自动衔接及真实故障验收仍待补齐。
- “Windows 8 项通过”等于 NTFS 引擎夹具的证据。桌面适配器、现有用户资料与目标网络各有独立验证范围。
- “Guardian 最新整机模式通过”说明已审查规则与基线的检查结果。实际出口、DNS、UDP、IPv6、WebRTC 和持续监测仍各需证据。
- “CCBaga 清理都可恢复”不成立。身份切换归档与直接残留删除／整 Profile 重置的恢复条件不同。
- “全部指纹随机化”不符合固定源码。真实 OS／CPU／引擎与已关闭的 font／audio／GPU spoofing 仍须准确表达。

## 后续优先顺序

先完成已选的分项清理、Chrome／Edge 定向站点入口、系统设置与客户端适配，再补桌面访谈续接、中断对账和历史记录。Windows 有效策略条件与读回检查宜同步补齐，并用对应夹具和目标设备验证。默认国内分流与整机防护的兼容方案需要明确设计和目标验收。

独立 B 浏览器、身份保险库、跨机迁移和特定住宅出口部署属于可选产品扩展。账号因果效果继续按未证记录，实施优先级由实际使用目标决定。

## 本轮阅读与验证边界

- Guardian 当前树为 238 文件，215 个与旧完整阅读清单的 SHA-256 相同。四次提交中的 23 个变化文件全部纳入审阅。行为文件、测试、配置和页面完整复读，较大历史文档复核全部变更与关联上下文。图标按实际预览和容器／生成关系处理。
- Guardian 额外复读出口判定器及访谈续接分支。其余同 SHA 内容复用此前全文记录。最新测试使用 NetSecurity 夹具，最新浏览器预览使用合成报告，真实防火墙和实际业务仍待目标验证。
- CCBaga 423 文件全部与此前全文清单匹配。本轮完整复读四份我方专题，另外核查当前命令注册、浏览器保存／启动／清理、身份保存／切换／恢复／迁移、CLI 维护、清理白名单、验证模型、自更新和网络部署相关实现。
- 我方完整复读桌面专项工具四个主要模块、访谈状态机、生命周期验收及完整分类。系统防护、Windows 后端、数据隔离、远端、UI 和测试按具体调用范围核查。先前 v0.18.0 测试与发布证据按相同提交复用。
- 本轮验证属于源码／资料层。仓库外引擎、系统内核、供应商后端、正式安装包实际运行与真实账号环境均保留独立验证范围。
