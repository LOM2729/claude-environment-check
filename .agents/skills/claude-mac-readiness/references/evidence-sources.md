# 新增来源核对与可复用结论

核对日期：2026-10-20。本文记录来源及学习边界，不保存客户环境或运行许可。官方页面会更新，实际服务时复核与目标版本有关的段落和生效日期；尚未生效的政策不能当作现行规则。

## 标注方式

| 标签 | 能支持的结论 |
| --- | --- |
| 官方／标准 | Anthropic、操作系统／浏览器／代理软件自身文档或 IETF 标准；支持机制和产品规则，不证明客户机已采用 |
| 第三方源码 | 固定提交的实现、限制与设计；静态阅读不等于执行通过，项目自己的产品策略不等于行业或 Anthropic 要求 |
| 个人经验／社区资料 | 作者自述、配图操作、社区参数说明；可提出检查线索，因果与跨版本行为需另证 |
| 本轮目标机实测 | 实际目标、版本、时间、步骤与观察；只适用于已覆盖的程序、协议和状态 |
| 用户提供／模拟测试 | 用户描述、导入报告、fixture／mock；分别标注，不能自动升级为目标机实测 |

## EianLu：正文与四张图已核对

来源：[2026-10-19 原帖](https://x.com/EianLu/status/2112096071023497521)，本会话已在 X 展开全文并逐张查看；不是仅依据用户截取的第一页。

| 作者内容（个人经验） | 本 Skill 的处理 |
| --- | --- |
| 这次用新电脑 | 不列为必要条件，不据此购买设备或清除设备标识 |
| Claude 域名固定节点，减少切换 | 纳入配置核对：分组、域名规则、有效优先级、运行路径及出口变化；不承诺防封 |
| 建议正常使用，避免强迫突破拒绝、索取内部思考或辱骂模型 | 不将其与封号建立已证实因果；服务规则按官方说明核对 |
| 使用长期邮箱，中文界面和交流在其案例中可用 | 不强制换邮箱或英文环境；语言按体验需求设置 |

配图示例是 select 组＋三个 DOMAIN-SUFFIX：`claude.ai`、`claude.com`、`anthropic.com`。后两张图确实包含规则步骤；操作化见 [导入与分流](proxy-import.md)。这是起点，具体功能域名按官方网络文档及实际请求补充。

## Claude-Guardian：吸收方法，保留实现边界

项目：[DUNHKpcc/Claude-Guardian](https://github.com/DUNHKpcc/Claude-Guardian)。截图版本为 `95015be0fc70d2a1b143b43aab09e7a7ab7a7565`；2026-10-20 核对的远端 HEAD 为 **`29f9d39e0cd4438ff4cd5eac1835ec42fdccd0bb`**，已读取相关源码与说明差异。未安装或执行第三方脚本，未运行其测试，不引用历史测试数量作为本次验证。

纳入现有 Skill 的方法：复用已有信息；绑定真实目标与执行环境；分开配置声明、应用载入、进程采用和端到端观察；先准备最小差异与备份，再执行已批准项；恢复时保护之后的用户修改；按版本／配置／网络变化复验受影响项。

固定版本依据：

- [Agent 操作与生命周期复验](https://github.com/DUNHKpcc/Claude-Guardian/blob/29f9d39e0cd4438ff4cd5eac1835ec42fdccd0bb/skills/claude-guardian/references/agent-remediation.md)：提供流程设计，不能代替真实工具能力和批准。
- [生产修复入口](https://github.com/DUNHKpcc/Claude-Guardian/blob/29f9d39e0cd4438ff4cd5eac1835ec42fdccd0bb/skills/claude-guardian/scripts/repair_execution.py#L21-L29)：`_native_session` 仍抛出 `NATIVE_REPAIR_ADAPTER_UNAVAILABLE`，不能宣称已提供通用自动配置器。
- [单条规则辅助任务](https://github.com/DUNHKpcc/Claude-Guardian/blob/29f9d39e0cd4438ff4cd5eac1835ec42fdccd0bb/skills/claude-guardian/references/agent-rules-task.md)：限 Clash Verge Rev 2.5.8、已有专属扩展和单条 DOMAIN，库准备候选／比较供给读回；实际保存、载入、网络和恢复仍由目标机执行与验证。不能外推成任意 Clash／小火箭一键导入。
- [验收状态](https://github.com/DUNHKpcc/Claude-Guardian/blob/29f9d39e0cd4438ff4cd5eac1835ec42fdccd0bb/docs/rebuild-status.md)：区分合成或宿主 fixture 验证和完整真实设备修复。

该次核对的项目说明新增“整机默认统一路径、普通应用目标侧 IPv4-only”。这是**该仓库特定用户的产品选择**，不是本会话客户的授权或 Anthropic 官方要求。本 Skill 按客户实际选择确认整机／Claude 专用／应用例外范围；不自动移植其全机策略、账号重置、VM／VPS部署或逐查询询问机制。已有明确批准清单依本 Skill 的确认协议复用。

本次是独立归纳流程与链接，未复制其代码或把整个项目嵌套安装。其仓库标注 GPL-3.0-only；未来若要分发原代码或修改版，另核对许可证、声明和源码提供义务，保留许可证。客户只需本平台现有 Skill 即可按清单服务，不依赖 Guardian 的未开放执行器。

## 官方／标准依据索引

| 来源 | 本次采用范围 |
| --- | --- |
| [Anthropic 位置说明](https://privacy.claude.com/en/articles/11186740-does-claude-use-my-location)、[封禁与申诉](https://support.claude.com/en/articles/8241253-safeguards-warnings-and-appeals) | IP 等信号可用于大致地区判断；网络配置不代替账号规则。未找到新电脑／老邮箱／不辱骂可防封的官方保证 |
| [Claude Code 网络](https://code.claude.com/docs/en/network-config) | CLI 代理配置、按功能的域名需求；浏览器／Desktop／CLI 分别验证 |
| [RFC 9460](https://www.rfc-editor.org/rfc/rfc9460.html)、[RFC 6147](https://www.rfc-editor.org/rfc/rfc6147.html) | TYPE64=SVCB、TYPE65=HTTPS，与 DNS64 合成机制分开；不把过滤视为通用安全要求 |
| [Mihomo DNS](https://wiki.metacubex.one/en/config/dns/)、[TUN](https://wiki.metacubex.one/en/config/inbound/tun/) | DNS 参数作用层、核心版本、接管与平台差异；单开关不证明全路径保护 |
| [Clash Verge Rev 导入](https://www.clashverge.dev/guide/profile.html)、[规则](https://www.clashverge.dev/guide/rules.html) | 本地文件导入副本、持续规则扩展、顺序匹配；不采用关闭 TLS 验证的排错建议 |
| [RFC 8828](https://www.rfc-editor.org/rfc/rfc8828.html) | WebRTC IP 路径、代理与媒体功能取舍；与 HTTPS、DNS 分开观察 |
| [Chrome 语言](https://support.google.com/chrome/answer/173424)及本 Skill 平台语言模块所列 Apple／Microsoft 文档 | 区分系统／应用界面／网页首选语言、时区／地区／自动校时 |

[Shadowrocket Wiki](https://github.com/LOWERTOP/Shadowrocket/wiki)属于社区技术资料，单列为第三方；其中 DNS／UDP／STUN 隐式参数需当前软件帮助和目标机复测支持。不能将其冒称为 Anthropic 官方规范，也不把修改这些参数当作默认客户动作。

## Net.Coffee 全部拓展链接的核对（2026-10-21）

截图当前8项均已阅读，逐项处理见 [专属组与拓展资料](service-routing-checks.md)。采用可验证的分组/优先级、功能域名、代理变量生效和故障分层；不采纳第三方分数、防封因果、NTP返回时区等推测。电视文章只作场景参考，不增加设备控制权限或默认修改。

## 2026-10-23 增量：事务恢复与逐事件验收

另审阅 Claude-Guardian 固定版本 `1d424d52876c664b535a9d4ba7858e1b9f79e896` 的事务恢复、出口判定、相关测试和 ADR-039～041；仅静态审阅，未运行第三方代码或测试。该版本原生写入仅覆盖 Mac 的 Clash Verge Rev 2.5.8 rules 扩展，不覆盖小火箭或 Windows。其判定器依赖供给观测；ADR-039 中持久性判定与尚未进行重启／唤醒／换网复验的记录不能互相代证。本包独立实现并测试文本文件恢复与逐事件证据检查，实际客户机结果仍需现场核验。具体见 [可靠回滚与生命周期验收](recovery-and-acceptance.md)。
