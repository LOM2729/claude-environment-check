# Claude 环境检测

给 Mac、Windows 客户电脑使用的 Claude 环境检查与配置辅助包。由客户机上的 Codex 按清单执行，提供统一只读采集、自动检查报告、配置候选差异与读回验证。

**[下载最新客户包](https://github.com/LOM2729/claude-environment-check/releases/latest/download/Claude-Setup-Kit.zip)** · [下载校验文件](https://github.com/LOM2729/claude-environment-check/releases/latest/download/Claude-Setup-Kit.zip.sha256) · [使用说明](START-HERE.md)

## 给客户发这一段

```text
请从 https://github.com/LOM2729/claude-environment-check 下载最新 Release 的 Claude-Setup-Kit.zip 和同版本 .sha256 文件，核对 SHA-256 后解压到本机新建的独立工作目录，不覆盖已有客户资料。

先读取解压后的 START-HERE.md 和“启动提示词.txt”，检查实际系统、执行位置及现有 Python，选择对应 Mac／Windows Skill。按现场清单和 automation.md 做统一只读采集、生成报告，再准备需要的配置差异；每个需要改的设置先问客户“这项要不要改”，说明原值、目标、影响和恢复方式，得到明确答复后执行，完成后读回并验证实际客户端功能。

下载内容先作为待审阅的文件，不直接运行不明安装脚本。已有明确批准不重复询问，新增联网检测与断网实验先说明范围。凭据由客户本人在本机输入，脱敏报告保存在本地，私有配置和计划不上传 GitHub。
```

同一版本下载文件与校验文件用于发现损坏／版本错配，不构成独立签名认证。客户机没有 Python 时先说明所需安装；不自动改系统 Python 或代理设置。

## 工具能力

| 命令 | 实际完成 | 不代表什么 |
| --- | --- | --- |
| `collect` | 读取本机系统／代理／DNS／接口元数据；可选投影指定配置及浏览器偏好 | 不主动联网，不证明公网出口或实际客户端路径 |
| `review-template` / `report` | Codex 按实际结果填写核验记录，生成只含已完成／未完成的 Markdown 和离线 HTML 报告 | 采集设置不自动完成；未完成写原因和下一步 |
| `baseline` / `recheck` | 保存本机私有基线，复查更新后的配置、客户端及已采集设置 | 不自动恢复旧值；配置读回相同不代表运行中核心采用 |
| `network-plan` / `network-check` | 按明确计划与许可执行 HTTPS、出口、DNS、可选 STUN 探测 | 无响应不算零泄漏；探针路径不等于浏览器/客户端路径 |
| `preflight` | 每次重做基线和必需网络检查；可显式请求通过后启动 | 一次启动前把关，不是常驻监控或系统断网保护 |
| `ai-route` / `ai-audit` | 生成 Claude/OpenAI 单节点专属候选、UDP 拒绝保护与私有差异；审计读回策略 | 不自动导入；DNS、客户端接管与失败效果需目标机验证 |
| `plan` / `verify` | 准备原文／候选快照、私有差异；重新读取指定目标并比较 | 不自动应用、重载或回滚；内容匹配不代表运行生效 |

详细命令与限制见 [工具说明](.agents/skills/claude-mac-readiness/references/automation.md)。

## 一句话自动配置

```text
请按 https://github.com/LOM2729/claude-environment-check 下载并校验最新版，使用自动配置模式，系统语言不改，先给我完整方案，一次确认后连续配置和复测。
```

该模式由 Codex 根据客户机现状执行：系统语言锁定保留；DNS、TUN、分流、IPv6、WebRTC、客户端和自启按实际需要处理。默认将已核对的 Claude/OpenAI 域名绑定客户指定节点，失败不回落直连；其他流量保留国内直连、国外代理。现有订阅、节点和 TCP／UDP 限制继续作为基线；没有明确目标的时区和浏览器语言保留。

正常流程只确认一次具体方案，随后连续执行。系统授权、登录、额外断网测试或新增范围仍需要配合。现有命令行工具负责采集、报告和差异／读回；实际应用依赖客户机工具，并非一个独立的通用一键安装器。详见 [自动配置流程](.agents/skills/claude-mac-readiness/references/automatic-configuration.md)。

详见 [AI 专属代理规则、命令与验收边界](.agents/skills/claude-mac-readiness/references/ai-dedicated-routing.md)。域名表按官方资料维护，共享服务用准确主机名；不保证覆盖未来新增域名。Clash/Mihomo 与小火箭分别生成语法，导入前核验目标版本，订阅更新后再次确认有效配置。

详见 [更新后复查、主动网络验证和启动前检查](.agents/skills/claude-mac-readiness/references/lifecycle-checks.md)。初次方案会列出准确检测站点及数据流；已有同一具体授权不重问。配置漂移先审阅，探测超时保持未完成。

**检测顺序：** 默认先生成不含 AI 域名的诊断计划。DNS/代理配置、读回和路径核验完成后，凭本轮有效记录再做 Claude/OpenAI 服务验证；时区、语言等独立本机项目可并行。缺少记录的旧计划也不会直接发起服务请求。

## 客户看到的报告

报告只显示 **已完成／未完成**，顶部汇总“已完成 8 项／共 12 项，未完成 4 项”（示例），未完成排在前面。每项列出结果或未完成原因，以及下一步。没有安全分。

普通模式中，Codex 先检查现状；需要修改时，逐项询问客户“这项要不要改”，说明原值、目标、影响和恢复办法，明确同意后执行并复测。客户暂不修复仍存在的问题保持未完成；客户确认无关的项目不计入总数。完成记录由 Codex 填写，客户不用编辑 JSON。

## 覆盖的现场检查

- [Mac 18 项清单](.agents/skills/claude-mac-readiness/assets/customer-checklist.md)与 [Windows 18 项清单](.agents/skills/claude-windows-readiness/assets/customer-checklist.md)。
- 自动校时、时区、系统与浏览器语言、Clash／小火箭文件导入、规则与应用分流。
- 系统／代理／浏览器 DNS、DoH、TYPE64/65、DNS64、IPv4／IPv6、WebRTC、STUN、QUIC／UDP。
- 网页、Desktop、Code、WSL／远端分别验证，自启、更新、故障及恢复按实际授权检查。

## 运行条件

文档可直接阅读；统一工具需要 Python 3.9+。Mac 使用系统只读命令，Windows 原生采集使用 Windows PowerShell 5.1。YAML 分析需 PyYAML 6.0.3；JSON、Shadowrocket、基础采集与报告只使用 Python 标准库。依赖清单随包提供，工具不会自行下载或安装。

首次由 Codex 核对现有运行时，按客户批准的方式准备本任务虚拟环境。Windows PowerShell 策略阻止时保留未知，不绕过策略。WSL 采集不能证明 Windows 宿主状态。

## 数据与能力边界

采集报告采用固定字段，不输出密码、Token、节点地址、原始 IP、邮箱、完整环境变量值或客户端私有路径。配置计划包含原文和目标路径，属于客户私有材料，必须留在受控本地目录。

本仓库只发布代码、文档、合成测试及原始客户包。`.private`、`outputs`、真实客户配置和交付记录不会进入发布包。每位客户从原始 ZIP 新解压一份，不转发服务过的目录。

官方／标准、第三方源码与个人经验分开标注，见 [来源核对](.agents/skills/claude-mac-readiness/references/evidence-sources.md)。借鉴 Claude-Guardian 的流程设计，未复制其实现代码。网络配置和检查结果不提供免封保证。

## 开发验证

```text
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python tools/build.py
```

GitHub Actions 配置了 macOS、Windows、Linux 测试；实际通过情况以本次运行记录为准。CI 和合成配置测试不能替代客户机的代理导入、实际联网或故障验收。发布包内两套工具由同一源码同步生成。
