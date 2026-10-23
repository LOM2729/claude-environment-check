# 统一指定代理与关闭 IPv6

执行顺序只按 [五步流程](five-step-setup.md)，完整默认候选明确使用 `--policy domestic-v4`；下文 `unified-v4` 命令仅用于客户明确选择的兼容策略，不覆盖当前默认。

需要重启代理客户端/核心/服务或机器时，由客户手动操作；可能中断当前 Codex/远控通道的网络动作或影响不明的重载也交给客户。先保存进度和离线恢复说明，等待客户恢复连接后重新核验，不能自行断开通道；集中批准不替代人工交接。 具体按 [客户手动重启与恢复](five-step-setup.md#客户手动重启与恢复) 执行。

本文件说明统一出口与 IPv6 关闭的机制；当前自动模式在此基础上使用 `domestic-v4` 加入视频和国内域名规则。统一目标为：国内/确认的本地例外直连，其他原代理流量与 Claude/OpenAI 同走一个指定节点，失败不改走 DIRECT；选定联网接口和代理层关闭 IPv6。不是根据经验帖推断“关闭 IPv6 可以防封”。系统语言继续保留。

## 统一规则候选

```text
python <Skill>/scripts/claude_setup.py ai-route --policy unified-v4 --config <完整配置> --node <具体节点> --out <新私有目录>
```

统一所有原代理动作（包括最终兜底）到同一个单节点组；AI 域名规则仍置于普通分流前，并保留目标 UDP 拒绝。保留明确拒绝和国内/必要本地直连。组名沿用 AI-ONLY 以兼容旧版，名称不代表现在仅服务 AI。可显式选新组名，但后续命令须一致。

**DIRECT 不一定是国内。** 工具仅直接识别 CN 类型规则与明确私网/回环 CIDR；其他 DIRECT 必须先分类。CN 数据集内容和实际地域仍需核对。遇到待分类项：

```text
python <Skill>/scripts/claude_setup.py direct-review --config <原完整配置> --output <私有审阅.json>
```

Codex 在本地按客户目标填写每条的 keep（国内/已确认例外）或 proxy（应走统一代理）及原因，将结果纳入一次具体方案；客户不用编辑 JSON。不自动把国外例外说成国内。再将同一 --direct-review 文件传给 ai-route、ai-audit、baseline。审阅绑定原配置语义，配置变更后不能复用旧决定冒充新核验。

JSON/YAML 候选设置：顶层 `ipv6: false`、`dns.ipv6: false`、选定具体节点 `ip-version: ipv4`；新增 IPv6 目标拒绝规则。IPv6 字面节点地址直接要求复核；只有 AAAA、IPv6-only/NAT64 网络等需要在现场检查，不能离线假定有 IPv4。保留节点凭据，不改代理自身必要的 UDP 外层传输。

旧版精确匹配的 AI 专属块可以迁移；重复执行不重复堆规则。无法识别的同名组或复杂语义停下复核。修改段可能重新排版或移动/移除段内注释，必须检查私有差异；未修改段保留。生成、解析和静态审计均不代表客户端载入或真实出口验证。

```text
python <Skill>/scripts/claude_setup.py ai-audit --policy unified-v4 --baseline <本轮生成器原配置> --config <实际读回> --node <同一节点>
```

若 content_changed=false，无需为了生成计划而重复导入，可用本轮输入作为基线来源。原 ai-only 模式仍需显式指定 `--policy ai-only`，只用于已明确选择的兼容任务，不是当前自动配置默认。旧基线需按新的目标重新核验和建立，不能改个版本号就算迁移。

## 四层 IPv6 分开读回

| 层 | 目标 | 不能冒充的结论 |
| --- | --- | --- |
| 代理内核 | 当前最终运行配置 IPv6 关闭 | 不等于系统协议已关闭 |
| 代理 DNS | AAAA 处理符合关闭目标 | 不等于浏览器 DoH/其他解析器已关闭 |
| 指定节点外层 | 仅 IPv4；不是 ipv4-prefer | 不证明远端服务器到目标也只用 IPv4 |
| 本机选定出站接口 | 关闭后读回同一接口 | 保留 loopback；未选接口不能说已关闭 |

默认给客户核对所有实际出站接口；企业 VPN、唯一远控或 IPv6-only 依赖必须明确处理。存在冲突时标未完成并给下一步，不偷偷改成“优先 IPv4”。不把 ::1 存在自动判为失败。

### macOS

使用真实 network service 名称，不是 en0/utun0。先读取服务与硬件接口对应、原 IPv6 模式和 manual 参数，保存本地恢复材料。批准后可用系统命令：

```text
/usr/sbin/networksetup -setv6off <精确服务名>
```

读回用 networksetup -getinfo 和本包 ipv6-check。恢复按原值选择 -setv6automatic、-setv6linklocal 或 -setv6manual（原地址/前缀/路由）；不能一律改回 automatic。Link-local only 仍有本地 IPv6，不能当作关闭。不要批量处理 loopback、未知虚拟接口或企业/远控依赖服务。

### Windows

核对实际适配器名称、稳定身份、当前绑定和远控依赖；参数禁止通配符。按精确对象操作 ms_tcpip6，修改前保存 Enabled 原值。

```powershell
$binding = @(Get-NetAdapterBinding -ComponentID ms_tcpip6 | Where-Object { $_.Name -ceq '<已核对的精确名称>' })
# 先核对恰好一个对象及接口身份，再对这个 InputObject 执行获准动作。
$binding | Disable-NetAdapterBinding
```

由客户机 Codex 以安全参数填写实际名称，不将未经处理的文件文本拼进 PowerShell。恢复仅对原本启用、且本次关闭的同一对象使用 Enable-NetAdapterBinding。实际命令参数以目标机帮助为准。不要使用 `-Name '*'`、`-AllBindings` 或默认修改全局 DisabledComponents 注册表。

微软说明解绑 IPv6 可能带来不受支持的配置；命令也可能重启适配器并导致断连。把此影响、准确接口和离线恢复路径列入客户的具体方案。0x20 是偏好 IPv4，不等于关闭；loopback 仍保留。无法安全执行的接口保留未完成，独立项继续。

### Shadowrocket

生成器可准备统一规则与 `ipv6 = false` 声明；具体字段属于需目标版本核对的社区配置语义。通过实际版本 UI 关闭 IPv6并导出读回，系统接口也要读回。不要把 Mihomo 的 ip-version 字段搬进小火箭；没有外层/远端地址族的可验证证据时，该层保持未完成。配置文本通过不等于真机支持。

## 门槛与报告

IPv6 调整发生在非 AI 验证之前。`dns-ready` v2 要求 --ipv6-interface，并即时读取指定接口确为关闭；后续重新开启、状态变化或无法读取会使记录失效。v1 记录不再开启服务阶段，需要重新核验。`ipv6-check` 是状态检查，不是完整恢复备份。

统一代理组也不保证上游提供商对所有目的地永远使用同一公网 IP。配置后核对 AI 与普通国外连接命中同一指定节点，分别记录可验证的出口证据；DNS、WebRTC 和远端 IPv6 均不得用组名代替实测。

## 依据

- [Mihomo 全局 IPv6](https://wiki.metacubex.one/config/general/#ipv6)、[DNS](https://wiki.metacubex.one/config/dns/#ipv6)、[节点 ip-version](https://wiki.metacubex.one/config/proxies/#ip-version)。
- [Apple networksetup](https://support.apple.com/en-ae/guide/remote-desktop/apdd0c5a2d5/mac)、[TCP/IP 模式](https://support.apple.com/en-gb/guide/mac-help/mh14129/mac)；精确命令以目标机 man networksetup 为准。
- [Microsoft IPv6 配置说明](https://learn.microsoft.com/en-us/troubleshoot/windows-server/networking/configure-ipv6-in-windows)、[Disable-NetAdapterBinding](https://learn.microsoft.com/en-us/powershell/module/netadapter/disable-netadapterbinding)、[Enable-NetAdapterBinding](https://learn.microsoft.com/en-us/powershell/module/netadapter/enable-netadapterbinding)。
- 用户提供的本地经验文档已核对。账号养号、语言导致封号、支付渠道和风险分等说法不作为本工具的官方依据，不打包或公开原文件，也不据此默认改语言、付款或账号状态。
