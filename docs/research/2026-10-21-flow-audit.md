# 自动配置顺序审计与新手流程建议

审计日期：2026-10-21。审计对象：v0.6.1，提交 `c1d1e64e64a206d77523b329054cbf1026fdf3ae`。

这是审阅和研究结果，不是修复完成记录。运行源码、客户发布包和 GitHub Release 尚未改变。只新增研究文档；没有安装外部工具、操作客户配置、启动 Claude/OpenAI 客户端或进行真实 AI 服务探测。

## 结论

已有 `network-check` 阶段门槛能阻止缺少当前 DNS/代理核验记录的服务探针，也能在 bootstrap 混入已知 AI 目标时拒绝整份计划。但这一约束还没有完整覆盖浏览器重启、安装、登录、自动测速和最终启动瞬间，不能将当前包描述成“所有入口都已保证不会提前接触 AI”。

## 已确认问题

| 优先级与性质 | 触发条件及后果 | 最小修正 |
| --- | --- | --- |
| P1：流程缺口 | 语言任务可并行，但 Mac/Windows 语言模块要求重开 Chrome。恢复旧 Claude/ChatGPT 标签页可能提前产生请求 | 将语言字段检查/保存与浏览器重启分开；启动、重启、会话恢复、页面脚本检查均遵守网络前置条件。不得删除客户标签页来规避 |
| P1：流程缺口 | 导入/重载流程未完整盘点自动请求。合成 `url-test.url=https://claude.ai/` 配置被候选生成器原样保留；核心启用后可能自行探测 | 在核心校验、导入、重载、刷新前检查测速、health-check、provider、规则资源、脚本和客户端附加 AI 检测的目标与副作用。涉及 AI 或无法确定时先准备并批准初始化方案，不静默改用户 URL |
| P2：已复现代码缺陷 | 最后一个服务探测后核验记录过期；启动前只重查基线，仍发出启动请求 | 紧邻 Popen 前再次检查当前核验记录、有效期、指纹和本轮代理入口；失败则未完成且不启动 |
| P2：说明缺口 | 本机只读清单混入应用内登录、CLI doctor/auth/版本入口；某些入口可能激活应用或执行包装脚本，安装器也可能启动应用 | 前置只读改用文件元数据、PATH、安装清单和已知离线状态。不能确认离线的命令、安装/更新、登录跳转和自动启动后置 |
| 入口前提 | 说明要求客户先打开 Codex；如果要求涵盖 Codex 自身第一次连接，就存在自举问题 | 区分已有可用控制通道与全新未准备电脑。前者保护现有通道再配置；后者先用离线/人工基础引导，再让 Codex 接手 |

具体定位（固定提交，避免之后行号漂移）：

- [Mac 语言模块](https://github.com/LOM2729/claude-environment-check/blob/c1d1e64e64a206d77523b329054cbf1026fdf3ae/.agents/skills/claude-mac-readiness/references/locale-and-language.md#L15-L20)、[Windows 语言模块](https://github.com/LOM2729/claude-environment-check/blob/c1d1e64e64a206d77523b329054cbf1026fdf3ae/.agents/skills/claude-windows-readiness/references/locale-and-language.md#L18-L20)。
- [配置导入](https://github.com/LOM2729/claude-environment-check/blob/c1d1e64e64a206d77523b329054cbf1026fdf3ae/.agents/skills/claude-mac-readiness/references/proxy-import.md#L21-L26)。
- [启动代码](https://github.com/LOM2729/claude-environment-check/blob/c1d1e64e64a206d77523b329054cbf1026fdf3ae/src/readiness_lifecycle.py#L255-L265)。
- [Mac 前置检查](https://github.com/LOM2729/claude-environment-check/blob/c1d1e64e64a206d77523b329054cbf1026fdf3ae/.agents/skills/claude-mac-readiness/references/mac-checks.md#L7-L9)、[Windows 前置检查](https://github.com/LOM2729/claude-environment-check/blob/c1d1e64e64a206d77523b329054cbf1026fdf3ae/.agents/skills/claude-windows-readiness/references/windows-checks.md#L7-L19)。
- [客户入口](https://github.com/LOM2729/claude-environment-check/blob/c1d1e64e64a206d77523b329054cbf1026fdf3ae/START-HERE.md#L6-L9)。

### 合成复现证据

1. 时间以 mock 注入：核验记录开始时为 1798 秒，最后一个 worker 后推进 5 秒。`preflight` 返回必需检查满足并调用一次 mocked Popen；此时记录年龄为 1803 秒，独立检查返回过期。没有真的启动进程。
2. 只生成候选：含指向 Claude 的 url-test 组仍被保留。保留客户配置语义本身正确，缺少的是启用前副作用审查。没有启动核心或发出测速请求。
3. 现有 139 项测试的已通过证据复用；本轮没有重跑无变化套件，也没有将新增审计复现说成“新版本已通过”。

### 官方资料补充

- Claude 官方安装命令直接从 `claude.ai` 下载脚本，所以“先安装工具，之后再检查网络”也会发生服务域名接触。官方同时说明启动及运行期间可能检查更新；这支持将安装/启动放到明确阶段，而不是仅看动作名称是否叫检查。[安装与更新文档](https://code.claude.com/docs/en/setup)
- 官方要求在启动前设置代理变量；运行会话不会自动读入之后改动的 shell 环境，因此不能靠改完环境变量就认为旧进程已采用。[网络配置](https://code.claude.com/docs/en/network-config)
- Mihomo provider 的 health-check 有目标 URL 与间隔；url-test 同样是主动请求来源。[provider health-check](https://wiki.metacubex.one/config/proxy-providers/#health-check)

以上没有证明当前安装的 `claude --version` 必然联网，也没有证明任意安装器都会自动启动。未知行为应后置或静态核实，不能把可能性写成必然事实。

## 更适合新手的目标流程

对外显示五步，由 Codex 管理内部参数和证据：

| 客户看到的步骤 | Codex 负责 | 客户需要做 |
| --- | --- | --- |
| 1. 准备 | 识别系统、已有代理客户端、配置类型、当前活动配置；盘点已运行程序和恢复通道 | 提供已有订阅/配置；多个可选节点时选一个；仅回答无法读取的关键问题 |
| 2. 确认方案 | 展示具体变更、保留项、会联网的阶段与目标；把备份和恢复说明保存在本机 | 确认一次具体方案；系统认证在本机处理 |
| 3. 配置并验证网络 | 检查节点解析依赖；检查导入/重载的隐含请求；保存到持久化入口；读取最终运行配置；非 AI 路径验证 | 必要时完成工具无法代替的明确点击，不填写 JSON、端口或命令行 |
| 4. 打开和验证服务 | 紧邻动作重新核验；再安装/启动/打开网页、登录及真实功能测试 | 自己登录、输入验证码；必要时确认产品使用范围 |
| 5. 交付与续做 | 生成已完成/未完成报告，列一个明确的下一步；保存本机基线和离线恢复材料 | 阅读结果；以后从未完成步骤继续 |

时间准确性、明确要求的时区和不激活网页的本地设置可以并行。重启浏览器不属于纯本地独立步骤。涉及同一配置、重载、连接或唯一远控通道的操作要串行。

建议优先完成：

1. 修复启动瞬间重新核验，并补针对性回归。
2. 建立唯一的动作顺序表，覆盖浏览器、登录、安装器、更新、核心重载和主动探测；旧参考从该表引用规则。
3. 增加“导入/重载前副作用检查”，给出具体自动请求来源与目标；不要笼统关掉所有测速或删配置。
4. 将端口、路径、活动 profile、版本和计划 JSON 的处理留给 Codex；客户只回答实际缺口。
5. 明确全新电脑的基础网络入口，提供无需在线 AI 才能阅读的准备与恢复说明。已有可信控制通道时沿用，不重复安装/配置。
6. 从中断处继续，保留原观测时间；设置或网络变化只使依赖它的结果失效。不能为了绿灯而刷新旧证据时间。

这是一份可实施的修正方案，不代表上述能力已经新增。

## X 与 GitHub 资料

外部源码/官方资料的详细核实见 [同类流程研究](2026-10-21-setup-workflows.md)。

本轮通过 X 网页实际读取了以下帖子：

| 资料 | 可取的交互方向 | 不采纳的结论 |
| --- | --- | --- |
| [阿蔺对 claude-switcher 的分享](https://x.com/alin_zone/status/2112391214326743091) | 用户能理解“先体检，再启动”的单入口体验 | 每 10 秒检查后关进程不能证明一次直连都不会发生；语言/时区不提供账号保证 |
| [HalfBit 的整合检测页推荐](https://x.com/justhalfbit/status/2103387647997857943) | 将多项检查汇总在一个页面，减少工具来回切换 | 推荐帖不证明检测完整性或平台认可 |
| [Cyan 的检测分数经验](https://x.com/CyanCloud77/status/2108839867774103789) | 体现用户希望得到清晰的可用性结果 | “90 分再用”没有在本轮找到官方依据；继续使用已完成/未完成及原因 |

未访问帖子推荐的检测站执行本机探测，没有点赞、回复或发帖。搜索到的 `anshaneja5/Claude-Guardian` 是审批悬浮窗项目，不能与本研究的 `DUNHKpcc/Claude-Guardian` 环境流程混淆。

GitHub/官方资料中最适合吸收的是：Guardian 的阶段与证据失效、Clash Verge 的最终配置处理链、Mihomo 的 DNS 引导依赖、WinGet 的依赖失败隔离。没有查到可以未经适配和目标机验证、直接替代本项目的通用 Mac/Windows/小火箭一键包。

## 未做的事项

没有修改运行代码、两套已安装 Skill、客户 ZIP 或 GitHub Release；没有将这些待修复项标为完成。没有验证真实 Windows/macOS 客户机导入、现有后台进程、浏览器恢复标签页、实际账号登录或系统级断网保护。
