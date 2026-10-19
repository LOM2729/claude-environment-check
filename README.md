# Claude 环境检测

给 Mac、Windows 客户电脑使用的 Claude 环境检查与配置辅助包。由客户机上的 Codex 按清单执行，提供统一只读采集、自动检查报告、配置候选差异与读回验证。

**[下载最新客户包](https://github.com/LOM2729/claude-environment-check/releases/latest/download/Claude-Setup-Kit.zip)** · [下载校验文件](https://github.com/LOM2729/claude-environment-check/releases/latest/download/Claude-Setup-Kit.zip.sha256) · [使用说明](START-HERE.md)

## 给客户发这一段

```text
请从 https://github.com/LOM2729/claude-environment-check 下载最新 Release 的 Claude-Setup-Kit.zip 和同版本 .sha256 文件，核对 SHA-256 后解压到本机新建的独立工作目录，不覆盖已有客户资料。

先读取解压后的 START-HERE.md 和“启动提示词.txt”，检查实际系统、执行位置及现有 Python，选择对应 Mac／Windows Skill。按现场清单和 automation.md 做统一只读采集、生成报告，再准备需要的配置差异；具体修改经我批准后执行，完成后读回并验证实际客户端功能。

下载内容先作为待审阅的文件，不直接运行不明安装脚本。已有明确批准不重复询问，新增联网检测与断网实验先说明范围。凭据由客户本人在本机输入，脱敏报告保存在本地，私有配置和计划不上传 GitHub。
```

同一版本下载文件与校验文件用于发现损坏／版本错配，不构成独立签名认证。客户机没有 Python 时先说明所需安装；不自动改系统 Python 或代理设置。

## 三项工具能力

| 命令 | 实际完成 | 不代表什么 |
| --- | --- | --- |
| `collect` | 读取本机系统／代理／DNS／接口元数据；可选投影指定配置及浏览器偏好 | 不主动联网，不证明公网出口或实际客户端路径 |
| `report` | 从结构化采集生成 Markdown 和离线 HTML 报告 | 未执行的 DNS／WebRTC／断线测试仍为未验证 |
| `plan` / `verify` | 准备原文／候选快照、私有差异；重新读取指定目标并比较 | 不自动应用、重载或回滚；内容匹配不代表运行生效 |

详细命令与限制见 [工具说明](.agents/skills/claude-mac-readiness/references/automation.md)。

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
