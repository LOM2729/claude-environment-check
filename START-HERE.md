# Claude 客户环境配置包

版本：0.2.0 · Mac / Windows 两套 Skill · 中文现场流程

## 三步开始

1. 在客户电脑上完整解压，找到包含本文件和 `启动提示词.txt` 的 `Claude-Setup-Kit` 文件夹。不要在压缩包内直接操作；保留隐藏的 `.agents` 目录。
2. 在客户电脑的 Codex 中打开这个文件夹，以本机方式开展任务。若已有代理配置文件，可放入 `客户配置`；没有就保留为空，先检查现有环境。
3. 新建聊天，复制 [启动提示词](启动提示词.txt) 的全文发送。由 Codex 识别系统并选择对应清单；无需将两套文件复制到全局 Skill 目录。

[OpenAI 官方 Skill 文档](https://learn.chatgpt.com/docs/build-skills)说明了工作目录中的 `.agents/skills` 发现机制。如果没有出现在选择器中，启动提示词仍要求直接读取该路径；先确认解压完整和工作目录正确，必要时重启 Codex。若存在同名全局 Skill，本次明确读取本包文件，不覆盖原安装。

## 快速入口

- [Mac：18 项现场清单](.agents/skills/claude-mac-readiness/assets/customer-checklist.md)
- [Windows：18 项现场清单](.agents/skills/claude-windows-readiness/assets/customer-checklist.md)
- [Mac Skill](.agents/skills/claude-mac-readiness/SKILL.md)
- [Windows Skill](.agents/skills/claude-windows-readiness/SKILL.md)
- [官方、源码及个人经验的依据区分](.agents/skills/claude-mac-readiness/references/evidence-sources.md)

每项包含检查入口、处理方法和完成标志。覆盖时间／语言、配置导入、分流、DNS TYPE64/65、IPv6、WebRTC、Claude 客户端、自启、故障与恢复。

## 包内内容与使用条件

```text
Claude-Setup-Kit/
├── START-HERE.md
├── 启动提示词.txt
├── AGENTS.md
├── 客户配置/
├── 交付记录/
├── .agents/skills/
│   ├── claude-mac-readiness/
│   └── claude-windows-readiness/
├── PACKAGE-INFO.json
└── SHA256SUMS.txt
```

两套 Skill 各自保留完整 references、assets 和脚本。Mac 脚本使用系统 zsh；Windows 脚本使用原生 PowerShell，仅输出指定环境变量的存在状态，不联网、不打印值。Windows 执行策略阻止时不自动绕过或修改策略。阅读流程不需要 Python；新统一工具需要 Python 3.9+，YAML 分析另需 PyYAML 6.0.3。先使用现有运行时，缺失时说明安装范围；不自行安装或绕过策略。

需要客户机上的 Codex 有相应本地文件、终端权限；界面操作依现场工具决定。没有电脑控制能力时由操作者完成必要点击，Codex 继续做读回和验证。登录、验证码、管理员密码由客户本人处理。

本包包含操作知识、统一只读采集、自动报告和配置差异／读回工具，没有现成代理节点、订阅凭据、真实客户配置或第三方 Guardian 执行代码。Guardian 有用的方法已归纳进清单，其未开放的执行器不能当作已安装能力。资料中的版本、软件入口及官方政策在实际使用时按目标版本复核。

## 客户资料与后续使用

每位客户使用原始 ZIP 新解压一份。客户配置与备份留在其本地受控位置；交付记录仅保存脱敏摘要，不能再把已服务过的整个文件夹转发给下一位客户。重新分发时发送原始 ZIP。

`SHA256SUMS.txt` 用于核对包内原始文件是否完整，不证明客户设置正确或授予操作权限。本包已移除服务者电脑专属的历史报告路径；未打包私人源码、缓存或账号资料。完整客户机导入、网络效果和故障保护需现场验收，文件校验不能替代。

## 新工具使用顺序

读取对应 Skill 的 `references/automation.md`，使用其 `scripts/claude_setup.py`：`collect → report → plan → 获准实际应用 → verify → 实际客户端复测`。工具的 plan 不会应用配置；verify 只验证读回内容，所有未测的网络项保持未知。私有计划快照和逐行差异可能含凭据，留在客户本机受控目录，不能上传。
