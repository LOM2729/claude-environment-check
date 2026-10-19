# 同类 GitHub 与 X 资料核对（2026-09）

2026-10-20 新增的 EianLu 全文／四张配图与 Claude-Guardian 固定版本核对见 [新增来源与依据](evidence-sources.md)；客户现场执行见 [操作流程](customer-setup.md)。以下保留原有来源，不将旧日期核对冒称为本次重验。

这些链接是公开经验或软件文档，用于发现检查盲点。不要复制它们的脚本、文案或私有配置。单个账号案例无法证明封号因果；技术行为以当前官方软件文档和本机实测为准。

| 来源 | 纳入的判断 | 不纳入的推断 |
| --- | --- | --- |
| [claude-env-cleanup](https://github.com/pnedfff/claude-env-cleanup) | 审查本机旧路由覆盖、代理环境变量与脱敏报告；把对外探测从本机只读检查中分开。 | 清站点数据、轮换本机标识或等待“养号期”能恢复账号权重。 |
| [claude-sonar](https://github.com/AschoofAlpha/claude-sonar) | 比较 HTTP 出口与 DNS 路径，保留最小数据，变更前预览与回退。 | 任一“纯净度”分数能预测封号。 |
| [Clash Verge Mac FAQ](https://github.com/clash-verge-rev/clash-verge-rev.github.io/blob/main/docs/faq/macos.md) 与 [Mihomo TUN 文档](https://wiki.metacubex.one/en/config/inbound/tun/) | TUN 可能修改系统 DNS，Mac 上局域网 DNS 劫持有例外；排查必须看客户端实际运行配置和解析路径。 | 所有 Clash 客户端都应使用同一 DNS 地址或规则模板。 |
| [另一篇 X 个人案例](https://x.com/mkdir700/status/2034448922429870472) | 住宅代理也可能掉线，不能把代理类别当作稳定性保证。 | 作者猜测的付费档位、支付方式或住宅 IP 与封号的因果关系。 |

官方[Claude Code 环境变量说明](https://code.claude.com/docs/en/env-vars)进一步确认认证与路由变量有优先级：API key 或自定义 BASE_URL 可能使用户实际走的路径不同于预期。检查时只汇报键名和是否冲突，不显示凭据或完整网关 URL。
