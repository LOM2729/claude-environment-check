# Mac 环境检查参考

按用户的请求选用，不把清单机械地全跑一遍。不要收集或输出完整 IP、邮箱、代理凭据、Cookie、令牌、个人文件。网络探测会把当前出口 IP 发给被测网站；说明目的，优先用用户已信任的服务。

## 客户端

- Desktop：检查是否安装、来源与签名、应用版本、应用内是否已登录、计划等级、自启状态。签名通过只能说明当前二进制完整性，不能证明账号安全。
- Claude Code：先检查命令位置、版本和安装方式；可用 `command -v claude`、`claude --version`。按 [官方安装文档](https://code.claude.com/docs/en/setup)核对当前要求。安装正常或 Desktop 已登录都不代表 CLI 已认证。
- `claude doctor` 是终端只读诊断；会话内 `/doctor` 可能应用修复，不混用。检查登录时先核实本机 `claude auth --help` 是否支持 `claude auth status`，不为缺少命令自动升级或重新登录。doctor 和认证 JSON 可能含路径、邮箱或组织资料：在采集端仅保留安装问题、登录标记、认证类型和提供商等必要字段；无法可靠脱敏时引导用户本机查看并提供摘要，不把原始输出送进聊天。认证状态不证明当前凭据可成功请求。命令能力以 [当前 CLI 文档](https://code.claude.com/docs/en/cli-reference)及已安装版本为准。

## 认证与代理覆盖

在实际启动 Code 的终端中执行下面的只读脚本；`<skill-dir>` 替换为本 Skill 的安装目录。脚本不读凭据文件、不发网络请求、不修改环境，只输出 `process / 键名 / absent、empty 或 present`。

```zsh
/bin/zsh -f "<skill-dir>/scripts/check-env.zsh"
```

- 检查 API key、AUTH_TOKEN、OAUTH_TOKEN、BASE_URL、配置目录/配置档选择、云服务开关和代理变量的存在状态；同时看大小写代理变量。存在不代表启用，例如值为 `0` 的云服务开关不能当作已选中云提供商。
- 需要溯源时再检查当前终端、shell 启动文件、实际生效的用户/项目/组织配置；只报告键名与来源，不输出值、整个 PATH、完整设置文件或 `env`/`printenv` 全量结果。不运行配置中的 `apiKeyHelper` 来取得密钥。自定义 `CLAUDE_CONFIG_DIR` 或启动参数可能改变配置来源，不固定假设都是 `~/.claude`。GUI 启动的 Desktop 不一定继承终端环境。
- [官方认证文档](https://code.claude.com/docs/en/authentication)说明认证有优先级，也受交互模式和已批准 API key 等状态影响；不要看到变量就宣布覆盖，也不要只看“已登录”便断言使用订阅。怀疑路径冲突时结合现有会话 `/status` 的脱敏摘要核对实际来源，不为检查开启新模型会话。订阅与 API 配额按 [官方说明](https://support.claude.com/en/articles/9876003-i-have-a-paid-claude-subscription-pro-max-team-or-enterprise-plans-why-do-i-have-to-pay-separately-to-use-the-claude-api-and-console)区分；套餐资格每次现查，不硬编码。

## 按现象选择下一项检查

| 现象 | 优先核对 | 结论边界 |
| --- | --- | --- |
| 找不到命令、启动失败 | 命令位置、版本、安装来源、安装诊断 | 先定位安装/PATH 问题，不直接重装或清登录数据 |
| 网页正常、CLI 失败 | 认证来源、BASE_URL、HTTP(S)_PROXY/NO_PROXY、CLI 是否进入 TUN | 浏览器成功不能排除 CLI 的路径或认证问题 |
| CLI 正常、Desktop 失败 | Desktop 自身登录、启动环境、应用路由与版本 | CLI 认证和出口不能外推到 Desktop |
| 超时、解析或证书错误 | 实际路径、DNS、TLS、代理或可信证书配置 | 不通过关闭 TLS 验证掩盖错误；服务证书错误也可能来自拦截或目标错误 |
| HTTP 401/403 | 请求是否携带有效认证、实际提供商、响应来源及脱敏错误 | 无认证探测的拒绝可证明收到 HTTP 响应，不能证明账号可用；403 不自动等于封号 |
| HTTP 429 或 5xx | 限流/配额提示、响应来源；必要时查 [官方状态页](https://status.claude.com/) | 状态码本身不能归因于本机设置，不据此盲目换节点 |

网络探测使用有限超时，不携带密钥到检测站，不为连通性测试新建账号、订阅或默认发送模型请求。账号功能可由用户在已有会话中提供最小结果；未测就标为待验证。

## 网络与断线矩阵

| 状态 | 应检查的事实 | 不能据此推断 |
| --- | --- | --- |
| 正常连接 | VPN 状态、到外网的路由接口、出口国家/ASN、DNS 路径、Claude TLS 与浏览器/CLI 可达性 | 能访问就符合账号政策 |
| 代理节点失效、隧道仍在 | 最终规则是否指向代理、代理组是否回退至 DIRECT、失败回退切到哪里 | VPN 图标亮着就不会直连 |
| VPN 隧道消失 | 系统是否自动重连、断线期间是否允许普通直连、全流量隧道选项及例外 | 自动重连等于无泄露窗口 |
| 睡眠、重启、换网 | 睡眠断开、始终开启/按需连接、重连前的流量行为 | 静态设置检查等于真实故障演练 |

- Shadowrocket：在 UI 中核实当前生效配置与全局路由、始终开启、按需求连接、睡眠时断开、包括所有网络、启用回退。其[社区 Wiki](https://github.com/LOWERTOP/Shadowrocket/wiki)说明“始终开启”会尝试意外断开后重连，“包括所有网络”仍有系统服务例外，“启用回退”会切换其他可用节点。不要把任何一个开关单独称为绝对 kill switch。
- Clash 类：核实当前生效配置、规则顺序、DNS 和终端流量是否进入 TUN。系统代理不一定接管 CLI。Mac 上 TUN 可能改变系统显示的 DNS，且向局域网 DNS 的请求未必被自动劫持；因此需要结合实际解析路径和外部结果判断，不能见到某个系统 DNS 地址就直接判泄露。见 [Mihomo TUN 文档](https://wiki.metacubex.one/en/config/inbound/tun/)与 [Clash Verge Mac FAQ](https://github.com/clash-verge-rev/clash-verge-rev.github.io/blob/main/docs/faq/macos.md)。最终兜底指向代理可使代理失败时连接失败，但只有隧道失效场景的实测或可信平台机制才能支持更强结论。
- 无认证访问 Claude API 返回 401/405 且 TLS 验证通过，只能作为网络可达证据。外网路由走 VPN 接口也只说明当前连线；继续检查实际出口。修改后验证国内站点、Claude 相关站点和 CLI。
- IPv4 与 IPv6 分别核对；只测 IPv4 不能排除 IPv6 的另一条路径。浏览器可能启用独立 DoH，不能用系统 DNS 设置代替浏览器解析结果。未使用或未成功测试的地址族与客户端，明确标为未验证。
- 故障演练可能让远程操作失联。先确认恢复路径，再按用户明确授权测试。记录注入的故障类型、预期、实际和恢复结果；未演练时写“未实测”。
- 网络变更后读回生效配置，复核 VPN/路由、DNS、实际客户端出口、Claude 连通性及用户依赖的国内网站；沿用已同意的检测范围。故障演练结束恢复原网络并核实这些结果，不能把测试命令退出或 VPN 图标出现当作恢复完成。

## 浏览器与邮件

- WebRTC 泄露要在用户实际使用的浏览器里测，记录是否观察到真实公网 IP；关闭 STUN 或 WebRTC 可能影响音视频。IP 检测站的“风险分”是其启发式评分，不是 Anthropic 的封号概率。访问第三方检测站前告知站点和会传出的出口 IP，并取得该站点的确认；不要把原始 candidate 或完整 IP 写入报告。
- 远程图片像素可让发件方知道邮件被打开；跟踪链接也可能记录点击。[Proton 的说明](https://proton.me/support/email-tracker-protection)介绍其拦截机制。[Gmail 的说明](https://support.google.com/mail/answer/145919)指出远程图片经 Google 代理加载，不能直接把“显示图片”推断为向发件方暴露真实 IP。邮箱选择不证明账号“权重”。
- 浏览器语言、Mac 地区和时区主要影响用户界面与格式。只有用户明确要求时才改，并提醒其影响整台机器。操作与验证见 [语言与时区模块](locale-and-language.md)。不要为迎合某个出口 IP 自动伪装设备信息。

## 交付口径

每个结论标为“本机实测”“官方文档”“第三方经验”或“尚未验证”。报告实际配置值、变更与回退、通过的连通性测试、未测的故障路径，并单列地区政策风险。不要出现“零封号”“绝对不泄露”。
