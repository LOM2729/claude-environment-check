# Windows 检查参考

自动配置顺序以 [五步流程](five-step-setup.md) 为准。网络及选定接口 IPv6 未核验前，不打开/安装/登录 AI，不运行未证明离线的 CLI 诊断，不重启浏览器恢复标签。代理校验/导入/启用/重载前先检查测速、health-check、资源下载及附加请求。纯本机时间/语言字段检查可并行。

只选与用户请求相关的项目。下列 PowerShell 命令用于本机只读检查；若输出含用户名、内网地址、代理端口或完整外网 IP，对外报告前遮盖。不要把原始终端日志上传到第三方检测站。

## 客户端与自启

- Claude Desktop：按[官方安装说明](https://support.claude.com/en/articles/10065433-install-claude-desktop)核对 Windows 版本、下载来源、安装与应用内登录/计划。桌面端登录不代表 Claude Code CLI 已登录。检查 Windows“设置 → 应用 → 启动”与应用自身自启选项；两处都核实，只有用户要求时才改。[微软启动项说明](https://support.microsoft.com/en-us/windows/experience/startup-boot/configure-startup-applications-in-windows)
- Claude Code：按[官方 Windows 安装文档](https://code.claude.com/docs/en/setup)核对当前系统要求、安装方法、版本与诊断。套餐资格每次现查，订阅与 API Console 是不同产品。若用户选用 WSL，检查应在实际运行 claude 的发行版中进行，不把 Windows PATH/代理或另一个发行版当作结论；不为原生安装问题自动改用或安装 WSL。
- Windows PowerShell 的只读示例：

    Get-Command claude -ErrorAction SilentlyContinue
    claude --version
    Get-TimeZone
    Get-Culture
    Get-UICulture
    Get-WinUserLanguageList

  在目标机读取，只将必要摘要带入聊天；路径中的用户名也应遮盖。若命令不存在，先核实 Windows 版本和是否在 PowerShell/WSL 中，不猜测安装目录。
- `claude doctor` 是终端诊断；不能据此认定离线，必须在网络核验后执行，会话内 `/doctor` 可能应用修复，不混用。检查登录前先核实本机 `claude auth --help` 是否支持 `claude auth status`，不为缺少命令自动升级或重新登录。doctor 和认证 JSON 可能含路径、邮箱和组织资料：采集端仅保留安装问题、登录标记、认证类型与提供商等必要字段；无法可靠脱敏时引导客户本机查看并提供摘要。状态不证明当前凭据可成功请求。见 [当前 CLI 文档](https://code.claude.com/docs/en/cli-reference)。

## 认证与代理覆盖

在实际启动原生 Code 的 Windows PowerShell 中运行下面的只读脚本；`<skill-dir>` 替换为目标设备上脚本所在目录，可单独提供脚本，不要求客户安装 Skill。脚本不读凭据文件、不发网络请求、不修改环境或注册表，只输出作用域、键名和存在状态。

```powershell
& "<skill-dir>\scripts\check-env.ps1"
```

- 默认查 Process/User/Machine；可以 `-Scope Process` 只查当前进程。User/Machine 的持久值不代表已运行的终端、GUI 应用或 WSL 继承了它们。脚本若被执行策略禁止，改为指导用户查看必要键名；不为检查修改策略或默认绕过策略。
- 检查 API key、AUTH_TOKEN、OAUTH_TOKEN、BASE_URL、配置目录/配置档选择、云服务开关和代理变量。存在不代表启用，例如云服务开关可能为 `0`。需溯源时再查实际启动配置和用户/项目/组织设置，仅保留键名与来源；不输出整个设置文件、环境表、网关 URL 或密钥，不运行 `apiKeyHelper` 获取凭据。自定义配置目录和启动参数可能改变来源，不固定假设都是 `%USERPROFILE%\.claude`。
- WSL 中改查实际 Linux 进程和 shell 的存在状态；不使用此原生脚本替代。认证选择按 [当前官方认证文档](https://code.claude.com/docs/en/authentication)和必要时现有会话 `/status` 的脱敏摘要核对，不为检查开启新模型会话。看到变量不能直接宣布覆盖，看到登录也不能直接宣布走订阅。参照 [环境变量文档](https://code.claude.com/docs/en/env-vars)。

## 按现象选择下一项检查

| 现象 | 优先核对 | 结论边界 |
| --- | --- | --- |
| 找不到命令、启动失败 | 原生/WSL 环境、命令位置、安装来源与诊断 | 先定位安装/PATH 问题，不直接重装或清登录数据 |
| 网页正常、CLI 失败 | 认证来源、BASE_URL、HTTP(S)_PROXY/NO_PROXY、CLI 是否进入 TUN | Windows 浏览器成功不能证明 WSL 或 CLI 路径正常 |
| CLI 正常、Desktop 失败 | Desktop 自身登录、启动环境、应用路由与版本 | CLI 认证和出口不能外推到 Desktop |
| 超时、解析或证书错误 | 实际路径、DNS、TLS、代理或可信证书配置 | 不通过关闭 TLS 验证掩盖错误 |
| HTTP 401/403 | 认证是否有效、实际提供商、响应来源与脱敏错误 | 无认证探测的拒绝不能证明账号可用；403 不自动等于封号 |
| HTTP 429 或 5xx | 限流/配额提示、响应来源；必要时查 [官方状态页](https://status.claude.com/) | 状态码本身不能归因于本机设置，不据此盲目换节点 |

网络探测使用有限超时，不携带密钥到检测站，不为连通性测试新建账号、订阅或默认发送模型请求。账号功能可由客户在已有会话中提供最小结果；未测就标为待验证。

## 当前网络路径

- 在 PowerShell 中可用 Find-NetRoute -RemoteIPAddress 1.1.1.1 查看候选路由，用 Get-NetIPInterface 查看 IPv4/IPv6 接口，用 Get-DnsClientServerAddress 查看接口 DNS。三者是系统局部状态，不证明 Claude Code 或浏览器的最终出口；还要核对代理客户端当前生效配置、进程/扩展是否在运行和实际连接结果。[微软路由](https://learn.microsoft.com/en-us/powershell/module/nettcpip/find-netroute) · [微软 DNS](https://learn.microsoft.com/en-us/powershell/module/dnsclient/get-dnsclientserveraddress)
- 访问外部 IP 检测站前，告知站点名称与会传出的出口信息并确认。把 Windows PowerShell、Claude Code、Claude Desktop、Chrome 可能采用的路径区分开，不把一个检测结果外推给全部程序。无认证请求返回 HTTP 401/405 只能证明到达服务，不能证明登录或套餐资格。
- 浏览器 WebRTC 要在用户实际使用的浏览器中测；查 IPv4 和 IPv6，不把第三方“纯净度”评分当作封号概率。关闭 WebRTC/STUN 可能影响音视频，需单项确认。

## 断线矩阵

| 场景 | 检查重点 | 结果边界 |
| --- | --- | --- |
| 节点坏、TUN 仍在 | 最终规则与代理组是否可能回落 DIRECT；DNS 是否还可解析 | 连不上 Claude 可能是故障，不自动证明无直连 |
| 代理程序退出或隧道消失 | Windows 是否改用物理网卡、客户端是否有阻断策略、重连前窗口 | 自动重连不等于断线期间无流量 |
| 睡眠、重启、Wi-Fi 切换 | 自启、连接恢复、Windows 网络状态与 DNS 恢复 | 静态开关不能替代故障演练 |

- 对 Mihomo/Clash Verge 类客户端，读取当前运行配置，核对 TUN auto-route、DNS 劫持、strict-route、IPv6、规则顺序和代理回退。官方[Mihomo TUN 文档](https://wiki.metacubex.one/en/config/inbound/tun/)说明 Windows 的 strict-route 会增加防火墙规则以减少多宿主 DNS 泄露，也可能影响 VirtualBox 等软件；Windows 和 Mac 都不能自动劫持发往局域网的 DNS。不要把某一选项直接宣称为完整 kill switch，也不要在未确认影响和回退前修改防火墙。
- 如果用户使用其他 VPN 或代理客户端，以其当前官方文档和 UI 为准，不能把 Mihomo 配置套用到所有产品。多个代理、VPN、DNS 工具同时运行时，先只读查冲突，别直接卸载或禁用。
- 主动模拟节点、隧道或程序故障可能让远程协助失联。先准备本机可执行的恢复路径，再取得针对该场景的确认；没有实测就写“未实测”。
- 网络变更后读回生效配置，复核 VPN/路由、DNS、实际客户端出口、Claude 连通性及用户依赖的本地站点；沿用已同意的检测范围。故障演练结束恢复原网络并核实这些结果，不能把测试命令退出或 VPN 图标出现当作恢复完成。
