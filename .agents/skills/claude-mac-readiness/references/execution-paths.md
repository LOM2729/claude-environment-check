# 本机 远程与后台进程的网络路径

用于 Desktop、CLI、MCP、后台任务或 Remote-SSH 的表现不一致时；简单连接问题不必加载。先定位实际执行端，不因一份 VPS 教程自动迁移环境、购买主机或部署远程桌面。

## 定位执行端与启动方式

按实际使用范围记录：目标设备/操作系统、进程与父进程、启动入口、安装方式/版本、配置来源、认证方式和网络路径。区分本机终端、GUI/托盘启动、VS Code 的本地或远程扩展、SSH 远端终端、MCP 服务及后台 supervisor。不收集完整命令行、进程环境或日志，避免其中的凭据与个人路径进入聊天。

- 终端导出的变量不会自动改变已运行的 GUI 或后台进程。先确认目标进程是否仍是旧实例；重启及其任务中断影响按逐项确认协议处理。Claude Code 后台会话的网络设置按 [当前作用域说明](https://code.claude.com/docs/en/network-config#apply-network-settings-to-background-agents)核对。
- 环境变量继承只证明输入，不证明网络库采用了代理。Node/Python/MCP、裸 socket 和系统服务分别核对；必要时查实际 Node 版本、HTTP agent 或环境代理开关。Windows 环境变量大小写不敏感，不能把大小写双写当作更强保护。[Node 子进程环境](https://nodejs.org/api/child_process.html)、[Node 内置代理支持](https://nodejs.org/api/http.html#built-in-proxy-support)
- Claude Code、cURL 和 Electron 的代理能力不同，按实际软件核对协议和 bypass。不要把 `ALL_PROXY=socks5h://…` 视作通用兜底；Claude Code 的代理支持以 [网络配置](https://code.claude.com/docs/en/network-config#proxy-configuration)为准。Electron 的 Chromium 网络代理不能代表其外部子进程。[cURL 变量规则](https://curl.se/libcurl/c/libcurl-env.html)、[Electron 代理开关](https://www.electronjs.org/docs/latest/api/command-line-switches#--proxy-serveraddressport)

## 验证覆盖而不是设置数量

先核实当前生效配置与目标进程，再用获授权的探测、功能请求或连接证据检查实际路径；区分正常连接、节点失败、代理退出、应用重启/更新和后台任务。沿用本轮同意的外部检测范围，不为取直连基线擅自关闭 VPN。

- TUN 是流量接入方式，可继续使用规则分流和排除路由。Fake-IP、DoH、禁 AAAA 和 `no-resolve` 分别解决不同问题；`no-resolve` 跳过 IP 规则匹配引发的域名解析，不是关闭所有 DNS/PTR 查询。核对谁解析、谁选 IPv4/IPv6、谁发 UDP，以及 bootstrap/节点解析与 bypass。[Mihomo TUN](https://wiki.metacubex.one/config/inbound/tun/)、[DNS](https://wiki.metacubex.one/config/dns/)、[no-resolve](https://wiki.metacubex.one/config/rules/#no-resolve)
- 浏览器独立资料目录可以隔离其 Cookie、历史与偏好，不能称为设备身份清零或系统网络沙箱。WebRTC 策略限制哪些路径，应在目标实例中验证；不能从策略名推断 WebRTC 全部关闭。[Chromium 资料目录](https://chromium.googlesource.com/chromium/src/%2B/HEAD/docs/user_data_dir.md)、[WebRTC 策略](https://raw.githubusercontent.com/chromium/chromium/main/components/policy/resources/templates/policy_definitions/WebRtc/WebRtcIPHandling.yaml)
- Windows 程序防火墙规则依赖实际完整路径；不能将 `.exe` 个数乘二或规则存在作为验收。需核对启用状态、活动策略、地址族/协议、安装目录外的子进程和更新后的新路径。更改前保留规则备份与恢复路径，不先清空旧保护再尝试建新规则。Mac 应核对其实际防火墙/网络机制，不运行 Windows 注册表或 NetSecurity 命令。[Microsoft 防火墙规则](https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/rules)

## Remote SSH 与 VPS

Remote-SSH 的 VS Code Server、远端终端与在其中启动的 Code 使用远端环境；本地 UI、部分扩展和浏览器仍可能在本机。分别核对本机、远端及容器，不能把 VPS 出口外推到所有客户端。[VS Code Remote-SSH](https://code.visualstudio.com/docs/remote/ssh)

已有远程环境先只读检查系统/架构、安装来源、资源、当前用户、SSH 主机身份、转发监听和认证入口。安装要求按 [Claude Code 当前说明](https://code.claude.com/docs/en/setup)与 [VS Code Server 要求](https://code.visualstudio.com/docs/remote/ssh#system-requirements)核对，不固定要求 Node20、特定 VPS 商家或 4C8G。

SSH OAuth 回调不可达时按 [官方登录流程](https://code.claude.com/docs/en/authentication#log-in-to-claude-code)使用浏览器登录及手动登录码，不默认搭建 Xvfb/noVNC。若用户确实需要远程浏览器，单独预览监听、认证、转发和关闭方式；共享主机上回环监听也不是独占访问。停止时只处理本次启动的实例/PID，不用宽匹配结束其他会话。[websockify](https://github.com/novnc/websockify/blob/master/README.md)

恢复分三项验收：SSH/转发重建、远端任务存活、正确会话可恢复。ServerAlive 只检测失去响应，tmux 可保留断线终端；它们不保证重启、OOM、进程崩溃或认证过期后自动恢复。VPS 固定出口仅是基础设施属性，不证明服务地区资格或防封效果。[OpenSSH](https://man.openbsd.org/ssh_config)、[tmux](https://github.com/tmux/tmux/wiki/Getting-Started)
