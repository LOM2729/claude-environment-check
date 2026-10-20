# 国内视频 UDP 例外与国内域名

**v0.10 专属组验收：** 默认 domestic-v4 为 Claude 第一方域名增加 <基础组名>-Claude（默认 AI-ONLY-Claude），与基础组绑定同一具体节点，AI保护块仍优先。生成后检查最终合并和运行连接链，按 [分组与服务路径检查](service-routing-checks.md) 验收；旧候选迁移需先审阅差异。

自动配置默认 `domestic-v4`，适用于 Mac/Windows 的 Mihomo 内核客户端；旧 `unified-v4` 和 `ai-only` 保留兼容。小火箭使用同一策略的原生 .conf 适配，由 Codex 自动展开规则、导入与读回，详见 [小火箭适配](shadowrocket-domestic.md)。Windows 可以生成文件，实际应用验收须在目标 Apple 设备进行。

## 先检查 UDP 禁用位置

先对真正活动配置运行 `udp-check --config <实际配置> --out <新私有目录>`。工具只离线盘点 UDP 字段/规则，不修改系统，不读取凭据到公开报告。文件检查已完成不代表系统已完成；Codex 补充以下目标机证据：

- 路由层：`NETWORK,udp,REJECT` 等全局规则的位置、扩展/覆写、条件拒绝和企业策略。生成器只自动重排明确的无条件 UDP 拒绝；复杂拒绝冲突要先审阅。既有 AI 域名拒绝不应被新的代理允许规则默默覆盖。
- 节点/组：`udp: false`、`disable-udp: true` 可以继续保留，国内视频走 DIRECT 不依赖节点转发 UDP；不要一键把所有代理节点 UDP 开启。节点自身的外层 UDP 传输与用户 UDP 请求不同，不误封 Hysteria/TUIC 等必要传输。
- 应用/TUN：核对软件全局 UDP 开关、TUN/透明接管、绕过路由与运行模式。仅开启 HTTP 系统代理不代表 UDP 被接管。若 UDP 在进入规则前已被整体丢弃，先按已批准具体方案解除这一层冲突，保持路由层其余 UDP 拒绝。
- Mac：只读核对所用客户端、系统 VPN/网络过滤器、PF 等实际启用的限制；无管理员读取能力时标未完成，不关闭整个防火墙。
- Windows：只读核对客户端及有效防火墙出站策略（含企业策略、程序/端口/接口范围）、第三方网络过滤器与原生网络栈；WSL 单独检查。只处理已确认冲突的具体项，不能关闭整个 Defender 防火墙或绕过企业管理。
- 浏览器：检查 QUIC/WebRTC 策略；视频能回退到 TCP 不等于 UDP 已放行，不为播放视频解除全部 WebRTC 隐私限制。
- DNS/控制通道：确认 DNS 劫持/解析器与代理自身连接在正确层处理，不能把 DNS/NTP/远控必需流量误当视频或随意全局放行。需要新增例外时展示具体范围，取得有效授权后再处理；未知保持未完成。

任何可能断开控制通道的动作和代理重启都交客户执行，按 [手动重启与恢复](five-step-setup.md#客户手动重启与恢复) 保存进度，再重新核验。

## 规则顺序

1. Claude/OpenAI 已知域名保护：UDP 拒绝、TCP 指定代理、失败不直连。
2. IPv6 拒绝与保留的非 AI 明确拒绝规则。操作系统关闭 IPv6 仍需单独读回。
3. 国内视频服务/CDN 域名直连，允许这些命中的 UDP 与 TCP。
4. 其余 UDP 拒绝。普通国内域名和 LAN 规则不能绕过这条；需要的 DNS/企业通话/远控另核对并明确解决，不能假装兼容。
5. 国内域名直连，再沿用已审阅的国内 IP/本地例外与其他规则；普通国外和 AI 共用指定节点。

国内普通域名列表不放在 UDP 拒绝前。名单表示服务域名归类，不保证服务器物理位于国内，也不是零泄漏证明。国内直连会向对应服务暴露真实出口，这是客户选择的策略。AI 域名未被识别、UDP 绕过核心、旧连接和外部过滤器仍须实际检查。

## 来源和维护

采用 [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat) 固定提交 `d13b14cc2288dd4c61adcc77a90dc2f82ac5316f` 的 `cn.list` 国内域名快照，110445 条。视频白名单从同版本 bilibili/douyin/iqiyi/youku 列表筛选服务和 CDN 域名，排除游戏、漫画、海外变体和宽泛共享 CDN 后缀；当前覆盖哔哩哔哩、抖音、爱奇艺、优酷的选定域名，非完整播放保证。腾讯视频等其他平台先补准确来源和验证，不默认包含。

数据来源/上游和本包 SHA256 记录在 Skill 的 `scripts/domestic_sources.json`，再分发数据许可证为 `scripts/DOMESTIC-DATA-LICENSE.txt`（GPL-3.0）；原工具许可证不因此改写。快照本地随包分发，Mihomo 配置采用 inline domain provider，小火箭展开为原生 DOMAIN/DOMAIN-SUFFIX；两者均无新增运行时规则下载。来源维护不等于本包实时更新：更新名单需重新取证、差异审核、跑顺序/代理失败测试并发布新包，不原地刷新未知名单。

规则机制依据：[Mihomo 路由规则](https://wiki.metacubex.one/config/rules/)、[inline rule provider](https://wiki.metacubex.one/config/rule-providers/)。平台域名分类来自第三方数据；实际播放和路径结论只能来自客户机实测。

## 生成和验收

Codex 填写路径、节点、参数；客户不用手写 JSON。先准备具体方案、UDP 位置清单与备份，再运行 `ai-route --policy domestic-v4`，有未知 DIRECT 时先处理 `direct-review`。完整差异包含原全局 UDP 拒绝的移动和新增国内名单；只生成候选不能算应用完成。用同一 `--policy domestic-v4` 运行 `ai-audit` 和 `baseline`，更新后 `recheck` 保留该策略。

Mac/Windows 均先配置 DNS/代理/IPv6、读回和非 AI bootstrap 验证，之后才测试 AI。实际客户验收至少记录：

- 国内视频页面与播放/CDN路径；抓到 UDP 命中 DIRECT 才能说视频 UDP 已完成，仅播放成功可能是 TCP。
- 普通国内 TCP 直连，普通国内/未知/AI UDP 按规则拒绝；主动测试的准确目标与数据范围先纳入方案。
- AI 与普通国外 TCP 同一指定节点、没有 DIRECT 回落；断代理演练可能断开控制通道，须另有明确授权与恢复条件，不能自动停止唯一代理。
- 重新读取有效规则、TUN/应用接管及系统限制，客户手动必要重启后复查。报告仍只用已完成/未完成，未完成附原因和下一步。

本仓库真实核心测试全在 loopback 上运行，证明规则在指定 Mihomo 版本的测试行为，不代表客户防火墙/TUN/浏览器或真实视频网站已验收。
