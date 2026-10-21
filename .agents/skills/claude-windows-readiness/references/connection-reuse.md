# 连接保活与复用：离线检查、候选和实际读回

自动配置在 [五步流程](five-step-setup.md) 的第三步、最终分流候选之前执行。Mac 与 Windows 使用同一离线工具；字段依据实际代理内核和版本，不按操作系统猜测。系统语言不变，代理重启仍交客户操作。

## Codex 执行

先从安装元数据、现有日志或客户端信息页确认内核与版本。未知时运行检查并保留未完成，不为了查版本提前启动会自动测速或联网的核心。

```text
python <Skill>/scripts/claude_setup.py connection-check --config <当前完整配置> --core <已确认内核> --core-version <实际版本> --out <新检查目录>
python <Skill>/scripts/claude_setup.py connection-plan --config <当前完整配置> --core <已确认内核> --core-version <实际版本> --out <新候选目录>
```

参数由 Codex 填写，客户不编辑 JSON。`connection-check` 只读；`connection-plan` 仅准备候选、私有差异和报告，不改活动文件，不启动客户端。只有支持当前字段的已确认 Mihomo 版本才生成 TCP 保活设置；其他内核、未知版本和小火箭不套用 Mihomo 字段，报告给出原因与下一步。

教程扩展模式同时核对已指定具体节点的外层 TLS 指纹。确认其协议、内核和版本支持后，由 Codex 在上述命令追加 `--node <已指定节点> --chrome-fingerprint`，将适用的 `client-fingerprint: chrome` 纳入同一候选和修改预览。不能把证书校验字段 `fingerprint` 改为 `chrome`；不适用的协议不启用 TLS 或更换节点来凑配置。

候选仅修改工具明确支持的顶层保活字段，以及明确指定且适配的节点客户端指纹，保留有效的现有保活正值，不改节点凭据、协议、SMUX、多路复用或服务端参数。无变更时仍生成原样候选和报告，不制造空差异。候选设置正确与应用已经载入分别记录；TCP 保活也不能证明 Claude HTTP/TLS 连接实际复用。

以连接候选作为 `ai-route --policy domestic-v4` 的输入，规则审计使用同一个输入基线；最终 `plan` 则比较原活动配置与最终分流候选，确保客户看到全部变更。之后再运行 `contact-scan`、动作检查和既有导入/读回流程，不改旧快照凑审计通过。私有差异不得公开上传。

## 实际验收

DNS、代理和规则库就绪之后，检查当前客户端是否载入设置，再用已批准的正常 Claude 会话观察流式响应、连接中断/重建与核心日志。不要为制造“复用率”循环调用收费 API，不故意断开唯一控制通道。HTTP keep-alive、HTTP/2、TCP keepalive、代理协议多路复用是不同层，不能只改一个开关就把所有层标完成。

TLS 指纹只核对实际协议、内核和版本支持的外层字段；不将外层 Chrome 指纹宣称成 Claude Code 内层 TLS 变成 Chrome，不关闭证书校验，不修改服务端要求。并发数量按客户任务、服务额度和实际限流调整；文章的“单 IP 不超过 5 个”作为社区起步建议，不能作为官方阈值或自动切换多个出口的理由。

依据：[Mihomo 通用配置](https://wiki.metacubex.one/config/general/)、[Claude Code 网络配置](https://code.claude.com/docs/en/network-config)。文章的稳定性经验见 [逐项覆盖表](tutorial-coverage.md)，与官方机制分开标注。报告状态仍只有已完成/未完成。
