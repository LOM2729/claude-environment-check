# Claude 客户端：缓存、认证、用户数据与卸载

原生备份/迁移/重装和失败恢复的最新细节见 [CCBaga原生](https://github.com/LOM2729/claude-environment-check/blob/main/docs/research/claude-environment/source-methods-ccbaga-native.md)、[维护界面与安装](https://github.com/LOM2729/claude-environment-check/blob/main/docs/research/claude-environment/source-methods-ccbaga-ui-maintenance.md)及 [Guardian事务/离线恢复](https://github.com/LOM2729/claude-environment-check/blob/main/docs/research/claude-environment/source-methods-guardian-runtime-recovery.md)。这些方法分别有范围和容量限制，不将全部reset/删除统一写成先备份可恢复。

原作者的完整分支另见 [Guardian 账号与清理](https://github.com/LOM2729/claude-environment-check/blob/main/docs/research/claude-environment/source-methods-guardian-account-cleanup.md)和 [三个清理 Skill](https://github.com/LOM2729/claude-environment-check/blob/main/docs/research/claude-environment/source-methods-ccbaga-cleanup.md)：SIMPLE/bare、项目 purge、六隐私变量、CC Switch 窄覆盖/弃路由/整卸载、Teamo 共用历史、滚动备份 ID 同步和 Keychain 恢复边界。它们作为可选来源方法保留，不因收录变成默认缓存清理。

用于明确要求清理、重认证、卸载，或证据指向客户端状态损坏的排障。先按 [事故分流](incident-and-cleanup.md) 识别目标；网页站点数据转 [浏览器清理](browser-cleanup.md)。只改 Skill／阅读资料的任务不盘点真实客户端，也不以真机清理验证文档。以下产品行为于 2026-11-06 核对，执行前复核当前版本。

## 先划定数据范围

| 对象 | 要识别的内容 | 默认保留／限制 |
| --- | --- | --- |
| 程序与入口 | 安装方式、全部命令入口、版本、符号链接目标、对应包管理器或应用包 | 卸载程序不自动删除配置、会话或项目 |
| 可重建缓存 | 目标版本确认可再生的缓存、图形缓存、临时状态 | 日志可能是排障证据，不能仅凭名字含 cache／debug／telemetry 就删 |
| CLI 认证 | 实际 `CLAUDE_CONFIG_DIR`、凭据存储、环境变量／profile／provider 覆盖、启动入口 | 凭据、配置目录和其他工具共享状态分开；存在不等于生效 |
| CLI 用户数据 | `~/.claude.json`、有效配置根下的 settings、projects、历史、Skills、hooks、MCP、plugins 等 | 保护项目 `.claude`、`.mcp.json`、源代码和 Git；没有明确用户数据清理要求就保留 |
| Desktop 持久数据 | 实际应用数据目录、登录、Chat／Code／Cowork 会话、技能、工作目录与导出 | 不把整个应用数据目录当缓存；区分本地与云端任务 |
| 集成与自启动 | IDE 扩展、PWA、浏览器扩展、Native Messaging、更新器、服务与路由工具 | 先证实归属及依赖；不因 Claude 关键词删除其他应用或用户仍在用的路由 |

盘点只报告路径／类别、存在状态、数量及必要元数据；不显示 Cookie、令牌、钥匙串值、账号原文或完整命令参数。实际内容核对如不可避免，应在目标机过滤后只输出结论，不能先把秘密读进对话再遮挡。

## 平台与安装边界

- **macOS CLI**：默认配置根 `~/.claude`；先检查启动入口是否设置 `CLAUDE_CONFIG_DIR`。凭据通常在登录钥匙串；钥匙串不可写时当前版本可回落到配置根内的 `.credentials.json`。不同配置根可对应不同钥匙串项目；固定默认服务名不足以覆盖全部，也不能按前缀批量删除。
- **Windows 原生 CLI**：定位目标用户及实际配置根，默认凭据文件在用户的 `.claude` 下。Process／User／Machine 环境和已运行 IDE／Desktop 环境分别判断。Home 目录重定向、MSIX、旧安装并存时按实际路径确认，不扫全盘按名称删除。
- **WSL／SSH／容器**：只检查本轮使用且获准的发行版／远端／容器用户、配置根和挂载卷。Windows 浏览器完成 OAuth 不说明 WSL 的凭据文件已更新；Windows 清理也不覆盖 WSL。不要为盘点自动启动无关发行版或容器。
- **Desktop**：Mac 的常见起点是 `~/Library/Application Support/Claude`，不是删除清单；Windows 按安装类型、应用信息及当前官方说明定位，不能把某个历史 `%APPDATA%`／Packages 路径当永久唯一根。Desktop 内嵌 Code 与独立 CLI、IDE 扩展可能共享部分状态，先确认写入者和使用方。
- 查多个安装入口可用 Mac 的 `type -a claude`／`which -a claude`，Windows 的 `Get-Command claude -All`／`where.exe claude`，再结合安装记录核对；只检查 PATH 的第一个结果不能证明全部卸载。这些是执行任务时的检查示例，不是阅读本文件就自动运行的命令。

## 登录故障：先定位来源，再决定是否退出

在已有网络前置条件满足后，按目标版本使用官方状态入口核实当前认证；不要为了查看状态调用任意 wrapper、`apiKeyHelper`、hook 或可能联网的诊断。需要启动／登录时仍遵循 [生命周期顺序](lifecycle-checks.md)，复用有效证据。

- 变量检查同时覆盖 API key／auth token／OAuth token、BASE_URL、CONFIG_DIR、ANTHROPIC_PROFILE 和 Bedrock／Vertex／Foundry 选择项；只记录存在状态。仅有变量不能推断实际优先级，要结合启动方式与官方认证说明。移除覆盖应定位到具体 shell、IDE、服务或配置项，不清空全部环境变量。
- 优先使用官方 `/login` 或当前版本支持的登录入口处理过期认证。确需 `/logout` 时，先说明它可能同时清除已保存的 MCP 登录及插件敏感值，后续需要重新授权／录入；不能当作无损刷新。
- `CLAUDE_CONFIG_DIR` 同时影响凭据文件和 Mac 钥匙串归属；某类不创建 API key 的 Console 登录保存在配置目录外，不能承诺“换目录即可绝对隔离全部账号状态”。
- CLI 本地退出、删除浏览器 Cookie、服务端撤销密钥／会话是不同动作。删除本地副本不等于撤销远端凭据；疑似暴露按 [凭据事件](incident-and-cleanup.md#凭据疑似暴露) 处理。
- 手工处理钥匙串只用于已定位的专项问题，先确认所属配置、具体项目和影响，不导出秘密。**Claude Safe Storage 是 Desktop 加密相关材料，不能作为普通缓存或 CLI 登录项顺带删除。**
- 登录、验证码和钥匙串认证由用户在官方界面完成；备份不保证能恢复已过期或已撤销的登录。

官方依据：[认证与存储](https://code.claude.com/docs/en/authentication)、[安装及登录排障](https://code.claude.com/docs/en/troubleshoot-install#not-logged-in-or-token-expired)。

## Desktop：先确认重置是否涉及云端

**Reset App Data 不属于常规缓存清理。** 官方 Desktop v4.16336.0（2026-11-03）说明：在确认框明示的情况下，重置会先删除当前登录账号在 Anthropic 服务器上的 Cowork 任务；相关菜单已更名为 Delete Cowork Data and Restart。必须读取目标版本、当前账号及当次确认框，不能只按按钮旧名称或社区旧教程推断影响。

1. 区分需要修复的缓存和持久数据，以及本地／云端任务。先保留必要工作文件、任务和技能；根据实际入口选择单任务下载或 Cowork 导出，核对导出内容能覆盖需要保留的数据。导出不等于自动恢复能力，不能承诺完整重建账号状态。
2. 若问题只涉及明确可重建缓存，优先处理那个对象；没有理由就不升级到整个 App Data 或 Cowork 重置。
3. 涉及云端任务删除、历史丢失或不可恢复操作，单列准确影响，在最终动作前按工具要求取得确认；一般“清缓存”授权不涵盖这些动作。本地目录备份不能撤销云端删除。
4. 需要退出或重启时先保存任务并保护控制通道。重置后分别验证目标功能和保留范围；不要把重装成功、目录重建或登录成功当成历史／任务已恢复。

官方依据：[Desktop 更新记录](https://claude.com/docs/cowork/changelog)、[Cowork 数据位置与导出](https://support.claude.com/en/articles/15520349-use-claude-cowork-on-web-desktop-and-mobile)。

## 卸载及定向文件处理

按目标安装方式使用 [当前官方卸载说明](https://code.claude.com/docs/en/setup#uninstall-claude-code)：native、Homebrew、WinGet、npm 等分别判断；第三方客户端按其实际产品说明处理。不复制宽范围删除命令，不把卸载应用扩展为删除所有 `.claude` 数据。

确需文件／JSON 清理时按 [清理准备与恢复](incident-and-cleanup.md#清理准备与恢复) 执行：先停止目标写入者、备份并校验，再只隔离已批准对象或修改已确认字段，保留未知字段和后续编辑。遇未知版本、无法确认归属、链接指向范围外或恢复冲突，停止该项并解释，不猜路径继续删。

程序卸载后核对安装记录、全部相关入口、目标进程／自启动与已批准集成的状态；明确哪些配置和会话有意保留。VS Code、JetBrains、Desktop 或其他共享工具可能重建 `~/.claude`，目录再出现不单独证明卸载失败。不要为证明卸载主动启动会重装 CLI 的入口。

macOS 与 Windows 的限定数据隔离见 [可选执行能力](execution-capabilities.md)。桌面工具默认只预览受支持的缓存，隔离后保留备份、对账记录和恢复说明。浏览器数据库、卸载及云端数据按各自专题的范围确认。社区脚本的静态审查与目标机的清理、恢复结果分别记录。
