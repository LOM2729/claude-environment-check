# X/GitHub 经验在 Windows 的适用边界

2026-10-20 新增的 EianLu 全文／四张配图与 Claude-Guardian 固定版本核对见 [新增来源与依据](evidence-sources.md)；客户现场执行见 [操作流程](customer-setup.md)。Mac 配图及第三方源码不代表 Windows 真机通过。

参考：[夙愿学长的 X 长文](https://x.com/suyuan1711/status/2102744129235193975)、[claude-env-cleanup](https://github.com/pnedfff/claude-env-cleanup)、[claude-sonar](https://github.com/AschoofAlpha/claude-sonar)。这是独立归纳，不复制原文截图或第三方脚本，也不把 Mac 截图当成 Windows 验证。

| 经验 | Windows 版处理 |
| --- | --- |
| 先查实际出口、DNS、WebRTC，再改配置 | 保留为可验证流程；Windows 上分别核对系统路由、运行中的 TUN、浏览器和 CLI，外部测试先告知目标网站。 |
| 住宅 IP、指纹浏览器、改时区/语言能“养号” | 无公开可核验的普适封号因果；不作为必要条件。实际使用地点须符合[官方支持地区](https://www.anthropic.com/supported-countries)，IP 等信号可被用于粗略地区判断。[Anthropic 位置说明](https://privacy.claude.com/en/articles/11186740-does-claude-use-my-location) |
| 代理节点坏了要阻止 DIRECT | 区分“节点失效但 TUN 仍在”和“程序退出/隧道消失”；Windows 上还需检查 DNS 多宿主行为及 IPv6。Mihomo strict-route 可能增加防火墙规则并影响其他软件，不能无确认套用。[Mihomo 文档](https://wiki.metacubex.one/en/config/inbound/tun/) |
| IPPure 等检测分数 | 用户同意后，在实际浏览器记录分数和 WebRTC/DNS/语言/时区警告；同站点复测具体变化。[IPPure](https://ippure.com/claude) 和 [Net.Coffee](https://ip.net.coffee/claude/) 的分数定义不同，均非 Anthropic 官方风控概率。 |
| 邮箱像素跟踪 | Proton 可阻挡已知像素；Gmail 图片可由 Google 代理加载。不能据此推断换邮箱会减少封号。[Proton](https://proton.me/support/email-tracker-protection) · [Gmail](https://support.google.com/mail/answer/145919) |
| Claude Code 与订阅 | 按[官方 Windows 安装文档](https://code.claude.com/docs/en/setup)检查 CLI；套餐资格现查，订阅、Console/API 与云服务路径分别核对。变量存在状态只能发现检查线索，实际认证结合[官方认证说明](https://code.claude.com/docs/en/authentication)与目标会话状态确认。 |
| KYC、账单地址、升级节奏 | 不指导虚构地址、绕过身份验证或反复开户；官方价格、支付方式和政策每次现查。 |

本 Skill 可用于收费的 Windows 环境审查服务，不能宣传“防封保证”“官方认证”或“已在所有 Windows 代理客户端验证”。若要重用原帖截图、长段文字或 GitHub 仓库代码，先确认各自授权；链接和归纳不等于取得转载许可。
