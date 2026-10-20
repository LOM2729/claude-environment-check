# Windows 时区、区域与 Chrome 英语：可选模块

自动配置顺序以 [五步流程](five-step-setup.md) 为准。网络及选定接口 IPv6 未核验前，不打开/安装/登录 AI，不运行未证明离线的 CLI 诊断，不重启浏览器恢复标签。代理校验/导入/启用/重载前先检查测速、health-check、资源下载及附加请求。纯本机时间/语言字段检查可并行。

完整客户搭建服务先只读记录；局部任务按需使用，先核实用户是否要求修改。自动校时、时区及自动时区、国家或地区、区域格式、Windows 显示语言、浏览器首选语言和菜单语言是不同设置；修改前按 [逐项确认协议](change-confirmation.md)预览并复用已有明确批准。手动选择时区通常保留自动设置时间。设置变化不证明实际使用地点，也不保证账号不会受限制。

## Windows 时区

1. 只读记录“设置 → 时间和语言 → 日期和时间”中的“自动设置时区”和当前时区，并用 PowerShell 的 Get-TimeZone 核对。不能因显示时间与某地相同就推断时区标识正确。
2. 用户选定目标后，在“日期和时间”中关闭自动时区并从列表选择；也可在用户逐项确认后使用 Microsoft 文档支持的 Set-TimeZone，先用 Get-TimeZone -ListAvailable 查目标 ID，不盲填。由用户处理 Windows 管理员提示。[微软设置说明](https://support.microsoft.com/en-us/windows/experience/personalization/set-time-date-and-time-zone-settings-in-windows) · [Set-TimeZone 文档](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/set-timezone)
3. 修改后再运行 Get-TimeZone，检查日历与本地时间显示。回退时恢复原时区和“自动设置时区”原值。若之后改变区域或网络定位选项，复核是否被重置。

## Windows 区域和系统语言

- “设置 → 时间和语言 → 语言和区域”的国家或地区、区域格式影响本地格式与部分服务展示；Windows 显示语言影响系统界面。只改用户单独确认的项，保留原值与回退。不要为设置 Chrome 英语自动改变整个 Windows。[微软语言与区域说明](https://support.microsoft.com/en-us/windows/hardware/input-devices/manage-the-language-and-keyboard-input-layout-settings-in-windows)
- PowerShell 的 Get-Culture、Get-UICulture、Get-WinUserLanguageList 可帮助读取不同层次；Get-WinSystemLocale 主要涉及旧式非 Unicode 程序的代码页，不能当作 Chrome 或网页 Intl 区域的直接验证。[微软 International 命令说明](https://learn.microsoft.com/en-us/powershell/module/international/get-winuserlanguagelist)

## Chrome 的两种语言设置

1. Chrome 菜单 → 设置 → 语言 → 首选语言：按用户目标加入 English (United States) 或其他英语变体并移到首位。是否移除中文另行确认；不要自动清空其他语言。
2. 若用户还要求 Chrome 菜单为英语，Windows 版可在英语语言项的菜单中选择“以这种语言显示 Google Chrome”，然后完全退出并重开 Chrome。这与网页首选语言是不同动作，分别确认和验证。[Google Chrome 帮助](https://support.google.com/chrome/answer/173424)
3. 核对设置页排序和重启后的 Chrome 菜单；需要时只读查看浏览器报告的 navigator.languages 与 Intl 时区/区域。它们只能反映该浏览器当前运行状态，不能证明账号政策适用性。
4. 回退时按原记录恢复 Chrome 两项、Windows 区域与时区。若浏览器内部设置页被当前工具阻止自动操作，给用户手动步骤并在完成后复测，不绕过工具限制。

## Edge 或其他浏览器

从实际浏览器“设置 → 语言”分别核对菜单和网页语言；按钮名称与是否支持单独界面语言以当前版本为准，不直接套用 Chrome 配置文件。检查企业管理策略来源，保留所需中文与输入法。浏览器报告时区、Windows 时区与实际 WSL 环境分别记录；Windows 的显示值不能证明 WSL 内状态。
