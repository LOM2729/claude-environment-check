# Claude 环境检测

让客户电脑上的 Codex 按五步完成环境配置：准备 → 确认方案 → 配置网络 → 打开服务 → 交付。支持 Mac / Windows，系统语言保持，报告只显示已完成／未完成。

**[下载最新客户包](https://github.com/LOM2729/claude-environment-check/releases/latest/download/Claude-Setup-Kit.zip)** · [校验文件](https://github.com/LOM2729/claude-environment-check/releases/latest/download/Claude-Setup-Kit.zip.sha256) · [使用说明](START-HERE.md)

## 给客户的一句话

请按 https://github.com/LOM2729/claude-environment-check 下载并校验最新版，使用五步自动配置模式：系统语言不改，国内直连，国外与 AI 统一指定代理，IPv6 关闭；先给我具体方案，一次确认后连续配置和复测。

## 默认流程
1. **准备**：读取本机元数据，识别现有软件和配置；不为检查安装情况而启动 AI。客户提供已有文件，必要时选一个节点。
2. **确认**：展示具体变更、保留项、备份恢复和准确检测范围，集中确认一次。
3. **配置网络**：审阅 DIRECT 例外和自动测速等隐含请求，统一代理、配置 DNS、分层关闭 IPv6；导入后读取最终运行配置，再做非 AI 验证。
4. **打开服务**：凭当前有效核验记录才安装、启动、打开网页、重启浏览器或登录；启动瞬间还要再次检查。
5. **交付**：报告已完成/未完成及原因和下一步，保留本机基线和恢复说明，中断后继续。

[五步细则](.agents/skills/claude-mac-readiness/references/five-step-setup.md) · [统一出口与 IPv6](.agents/skills/claude-mac-readiness/references/unified-ipv4.md)

## 实际工具
| 工具 | 能力 |
| --- | --- |
| collect / report | 本机元数据与离线 HTML/Markdown 报告；不将采集等同验证 |
| ai-route / ai-audit | 默认 unified-v4：统一已有代理动作与 AI 到指定节点，保留审核过的国内/本地直连，生成候选、私有差异与审计 |
| direct-review | 盘点不能直接判定的 DIRECT 规则，由 Codex 按方案填写保留或代理，客户不编辑 JSON |
| contact-scan / action-check | 启用代理前检查隐含目标；安装/登录/浏览器等动作前核验当前条件，不替用户执行动作 |
| ipv6-check / dns-ready | 精确接口关闭状态读回；本轮 DNS/代理记录绑定接口、配置和入口，缺失/过期/变化则服务请求停止 |
| baseline / recheck / preflight | 更新后复查，不自动恢复旧值；本次检查通过后可明确请求原生客户端启动 |

完整参数见 [工具说明](.agents/skills/claude-mac-readiness/references/automation.md) 和 [生命周期流程](.agents/skills/claude-mac-readiness/references/lifecycle-checks.md)。

## 使用条件与边界
客户已有可用控制通道时，Codex 继续处理；全新未配置电脑先用离线说明或人工准备基础代理，不能让在线 Codex 保证自身首次联网之前零 AI 请求。

Python 3.9+，YAML 需 PyYAML 6.0.3，优先使用现有运行时。原生 Windows 与 WSL 分别核验。软件实际保存、导入和管理员认证依客户机可用工具；不绕过权限，不自动关闭唯一远控通道。

IPv6 分为选定系统接口、代理核心、DNS 和节点外层，不能用“优先 IPv4”或无 AAAA 响应代替全部关闭；loopback 和未选接口不冒充已关闭。必要依赖冲突、小火箭版本行为或远端出口地址族没有证据时保留未完成。统一指定节点也不能保证供应商对所有目的地永远使用同一公网 IP，仍需实测。

候选与文件读回不等于运行生效，探针通过不等于客户端采用。报告完整 IP 只在本地私有证据里；配置和凭据不上传。每个客户新解压原始 ZIP，发布包采用文件白名单，测试证书、客户文件和运行报告均不打包。

没有常驻后台监控、系统 Kill Switch 或账号防封保证。官方资料、源码参考与个人经验分开，见 [来源说明](.agents/skills/claude-mac-readiness/references/evidence-sources.md)。

需要重启代理客户端/核心/服务或机器时，由客户手动操作；可能中断当前 Codex/远控通道的网络动作或影响不明的重载也交给客户。先保存进度和离线恢复说明，等待客户恢复连接后重新核验，不能自行断开通道；集中批准不替代人工交接。

自动配置默认先核对全局 UDP 限制所在层，再采用国内视频例外：AI 保护最先、国内视频直连、其余 UDP 拒绝、普通国内域名直连、国外统一代理。Mihomo 使用 domestic-v4；具体按对应 Skill 的 references/domestic-video-udp.md，不全局放开 UDP。
