# Claude 环境检测：从这里开始
版本：0.7.0 · Mac / Windows

## 客户只需准备
1. 已有的配置文件或订阅，以及希望使用的节点。文件可放入“客户配置”目录；不要把订阅凭据贴到公开聊天。
2. 在客户电脑的 Codex 中打开本包文件夹，保留隐藏的 .agents 目录。
3. 使用 [自动配置提示词](自动配置启动提示词.txt)。Codex 填写参数，客户确认一次具体方案，处理必要的本机认证和登录。

如果电脑尚无可用网络，在线 Codex 无法先替自己准备首次连接。先用已有可信代理材料与离线说明/人工协助建立基础通道，再由 Codex 接手；保护当前 Codex/远控通道。

## 五步顺序
| 步骤 | 客户看到的结果 |
| --- | --- |
| 1. 准备 | 自动识别系统、软件、文件，确认节点和保留项；不提前启动 AI |
| 2. 确认 | 一份具体方案、影响、备份恢复和检测范围；一次确认 |
| 3. 配置网络 | 先检查隐含请求和直连例外，配置统一代理、DNS、IPv6，读回并用非 AI 目标验证 |
| 4. 打开服务 | 再核验当前记录，才安装/启动/打开/重启浏览器/登录，验证实际功能 |
| 5. 交付 | 已完成/未完成报告，未完成原因和下一步，本机基线和恢复说明 |

默认国内及已确认本地例外直连，普通国外与 AI 共用一个指定节点；选定联网接口和代理层关闭 IPv6，系统显示语言不改。时区等独立本机项目可并行，浏览器重启和恢复标签必须后置。

## Codex 读取入口
- [Mac Skill](.agents/skills/claude-mac-readiness/SKILL.md)
- [Windows Skill](.agents/skills/claude-windows-readiness/SKILL.md)
- [五步执行细则](.agents/skills/claude-mac-readiness/references/five-step-setup.md)
- [统一出口与 IPv6 关闭](.agents/skills/claude-mac-readiness/references/unified-ipv4.md)
- [主动检测与本轮核验记录](.agents/skills/claude-mac-readiness/references/lifecycle-checks.md)
- [逐项确认模式（可选）](启动提示词.txt)

先选实际系统，只加载对应 Skill。若有同名全局 Skill，本次使用包内文件，不覆盖客户原安装。缺 Python/YAML 依赖时先由 Codex 说明准备范围；不改系统 Python 或绕过执行策略。

## 报告与资料
报告只显示已完成/未完成。静态配置、应用载入、真实客户端功能分别验证。小火箭未做目标版本导入/运行验证时，相应项保持未完成；脚本不是通用的跨客户端设置写入器，由 Codex 在已批准范围内执行实际操作。

私有配置、完整出口、备份、核验记录留在客户本机。每个客户从原始 ZIP 新解压一份，不转发用过的目录。SHA256SUMS.txt 用于完整性核对，不证明环境安全或提供新授权。没有安装常驻监控或系统断网保护。
