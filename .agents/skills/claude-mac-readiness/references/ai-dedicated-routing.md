# Claude / OpenAI 专属代理（兼容模式）

当前自动配置以 [Claude专属组与服务路径](service-routing-checks.md)、[国内视频与UDP](domestic-video-udp.md) 为准；默认 domestic-v4 会建立同节点 Claude 专属组。明确选择旧统一策略时使用 [统一出口与 IPv4](unified-ipv4.md) 和 [五步顺序](five-step-setup.md)。以下仅供明确选择 ai-only 的兼容任务；不覆盖新的默认目标。

自动配置模式默认将**已核对目录内的 Claude、OpenAI 域名固定到客户指定的一个代理节点**，代理失败时不改走 DIRECT。其余配置沿用现有国内直连、国外代理的规则、顺序、DNS 和传输限制。系统语言保持不变。

这项默认策略先进入具体配置方案，客户批准后才应用。专属组名默认为 `AI-ONLY`，可以用一个节点同时服务两家；需要分开节点时另做明确方案。必须确定真实节点，不能把“自动选择”“全球代理”等可能包含 DIRECT 的组当作指定节点。

## 规则与范围

- 在原有前置拒绝规则之后、普通分流规则之前插入 AI 规则。保留显式拒绝组；混合拒绝组、后置拒绝规则或脚本干预必须先复核，不能悄悄放宽原限制。
- 每个域名按“该域名 UDP 拒绝 → TCP 等其余流量送 AI-ONLY → 同域名拒绝保护”排列。Mihomo 使用 `NETWORK,udp`；Shadowrocket 使用 `PROTOCOL,UDP` 和 `REJECT-NO-DROP`。不要互相复制语法。
- AI-ONLY 只有一个本地明确声明的代理节点，没有 DIRECT、自动测速、故障转移或嵌套选择组。Mihomo 同时设 `disable-udp: true`。显式 UDP 拒绝很必要：Mihomo 文档说明，节点不支持 UDP 时可能继续匹配后续规则。
- 不修改代理节点自身的外层传输；SOCKS/HTTP 目标侧的 TCP-only 不等于把 Hysteria/TUIC/WireGuard 底层 UDP 关掉。语音、实时通信等需要 UDP 的功能可能受限，不能为恢复功能偷偷放行。
- 不把整个 Cloudflare、Google、GitHub、AWS、WorkOS 等共享服务划入专属组。对官方清单中的部分共享服务采用**准确主机名**；这些主机也可能被其他网站共用，方案中说明这一影响。
- 域名目录位于同 Skill 的 `scripts/ai_domains.json`，带核对日期和来源。它覆盖已知第一方域名及部分配套域名，**不是永久完整清单**。第三方网关、Bedrock/Vertex、MCP、插件、安装更新及新增共享主机需按实际产品另查；不能根据一次成功访问就宣称所有相关域名已覆盖。

## 生成候选与差异

先读 [工具条件](automation.md)，复用当前 Python。以下命令中的配置路径、节点名称和输出目录由 Codex 根据客户机实际情况填写；不能照抄占位值。本文件所在 Skill 的 `scripts/claude_setup.py` 同时适用于 Mac 与 Windows：

```text
python <Skill>/scripts/claude_setup.py ai-route --policy ai-only --config <当前完整配置> --node <已核对的具体节点名> --out <新的本地私有目录>
```

可指定 `--format yaml|json|shadowrocket`、`--group <新组名>`。默认按文件扩展名识别。含空格的路径和名称按当前 shell 正确引用；不要把配置内容拼入 shell。

输出：

- `candidate.yaml` / `candidate.json` / `candidate.conf`：新候选。
- `plan/`：原始与候选快照、哈希、私有差异和脱敏结构摘要。
- `ai-audit.json`：静态策略比较；网络、DNS、载入状态保持未验证。

工具不改原文件，不应用或重载代理、不联网、不下载规则集。候选、快照、差异可能含节点凭据，必须留在客户本地。若计划生成失败，保留的候选仍未应用，检查错误及私有目录，不把半成品当成功。

生成器要求已有完整配置：本地具体节点、显式直连规则以及指向已声明代理/组的末尾 `MATCH`/`FINAL`。这只验证基线结构；国内规则是否完整、国外兜底当前选了哪个节点仍需现场核对。工具不会从零猜一套国内外规则。

仅节点订阅、动态 provider 内未导出的节点、链式代理、已存在同名组、非规则模式、复杂内联 YAML 或脚本等无法安全确认时停止候选生成，说明原因和下一步。由 Codex 读取当前客户端导出的有效配置，核对更新持久化入口后再准备候选；不能把节点订阅当完整配置覆盖。重复运行也不能自动叠加同名组，应沿用已保存基线与审计。

## 应用与验收

1. 在一次确认方案中列出指定节点、AI 域名目录版本、专属组、UDP 限制、原有分流、共享主机影响、保存位置、备份及恢复方法。沿用 [自动配置流程](automatic-configuration.md) 的授权；已有具体批准不重问。
2. 用目标客户端/核心自带配置校验。Mihomo 示例为其 `-t -f <候选>`，但包含外部规则提供者时校验可能联网，先核对范围。Shadowrocket 需在目标版本验证语法及实际载入，不能以 Mihomo 校验替代。
3. 用当前 Clash 客户端支持的覆写/扩展/合并方式持久保存，检查最终合并顺序；Shadowrocket 使用实际配置入口。订阅更新后仍应生效。不要只改会被订阅刷新覆盖的临时生成文件；不额外安装插件或启动系统服务。
4. 导入后确认处于规则路由模式、选中了当前配置、AI-ONLY 只有指定节点，客户端没有额外 DIRECT 回退。小火箭的全局路由、UDP fallback 和链设置要单独核对。对其他流量维持既有策略；不要为 AI 目的全局修改其 UDP fallback。
5. 导出实际生效配置，在本地运行 `verify --plan <候选目录>/plan --target <读回文件> --exported-readback`。再运行：

```text
python <Skill>/scripts/claude_setup.py ai-audit --policy ai-only --baseline <候选目录>/plan/original.bin --config <读回文件> --format <实际格式> --node <同一节点名>
```

若生成时指定了 `--group`，审计时必须传入同一 `--group`。`ai-audit` 只有与“原基线 + 本次专属规则”语义完全一致才通过；额外 DNS/其他配置变化也会被检出。批量方案含其他修改时，先分步保存基线并核验每步，或另审完整差异，不能直接忽略不匹配。`verify` 的格式/注释变化仍需复核；退出码 2 表示不匹配，1 表示输入或操作错误。

6. DNS 路径单独核验：系统、代理核心、浏览器 DoH、节点域名解析各层分开，检查需要的代理解析是否仍直连。域名路由规则本身不保证 DNS 查询走专属代理；IPv6、IP 字面量、DNS TYPE64/65、WebRTC/STUN 也不能因此自动打勾。 取得本轮核验记录后才进入下一步。
7. 先按五步流程做动作前检查，再在已批准的影响范围内重建相关连接/会话，避免旧 TCP 连接或 UDP NAT 会话沿用先前规则。新规则不保证追溯接管既有连接，同一目标 IP/端口的复用流量也需关注域名可见性。分别验证 Claude 与 ChatGPT/Codex 实际使用的登录、请求、文件/图片、长连接等功能，查看核心连接日志中的命中规则和出口组。同时复测国内直连与普通国外代理；日志按需脱敏，不上传原文。
8. 客户允许具体故障演练且有恢复路径时，才暂时让指定节点不可用，确认 AI 请求失败，并结合核心日志/目标机流量证据检查未直连、未换节点，恢复后复测。只看到连接错误不等于无泄露。

这组规则在核心有效接管时约束匹配的流量；代理应用退出、TUN 关闭、应用绕过系统代理或域名不可见时，不能充当系统断网保护。系统防火墙/断网保护属于单独方案，不自动加入。本版本未在真实客户机上完成故障验收。

## 报告

客户报告仍只有**已完成 / 未完成**。核验模板新增 `ai_policy`（Claude/OpenAI 专属代理）及 `ai_failure`（AI 代理失败不回落直连）两项，默认未完成。AI 专属策略、应用载入、Claude/OpenAI 实际请求、DNS、IPv6、故障保护分别记录；仅生成候选时，后续项均未完成，原因写“尚未应用/尚未在目标机验证”，下一步写具体操作。不得用静态审计结果代替实际无直连结论。

## 依据类型

- **官方产品资料**：[OpenAI 网络建议](https://help.openai.com/en/articles/9247338-network-recommendations-for-chatgpt-errors-on-web-and-apps)、[Claude Code 网络配置](https://code.claude.com/docs/en/network-config)：域名和产品连接要求。它们不是本工具的“防封”承诺，也不能证明账户一定可用。
- **Mihomo 项目文档**：[规则与 UDP 行为](https://wiki.metacubex.one/config/rules/)、[select 组](https://wiki.metacubex.one/config/proxy-groups/select/)：核心匹配语法和策略组机制。不同 Clash 客户端/旧内核仍需目标版本校验。
- **社区资料**：[LOWERTOP Shadowrocket Wiki](https://github.com/LOWERTOP/Shadowrocket/wiki)：小火箭规则、UDP 拒绝、回退与链选项参考；不是 Apple/Shadowrocket 官方保证，合成文本测试不能替代真机验收。
- **本项目的工程选择**：单节点、禁 AI 目标 UDP、不扩大共享后缀、保留其他配置、失败项不记完成。个人账号经验没有作为这些规则有效性的证据。
