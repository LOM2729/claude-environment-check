# Mac 时区与 Chrome 语言：可选配置模块

自动配置顺序以 [五步流程](five-step-setup.md) 为准。网络及选定接口 IPv6 未核验前，不打开/安装/登录 AI，不运行未证明离线的 CLI 诊断，不重启浏览器恢复标签。代理校验/导入/启用/重载前先检查测速、health-check、资源下载及附加请求。纯本机时间/语言字段检查可并行。

完整客户搭建服务先只读记录；局部任务按需使用。先记录自动校时、原始时区及自动时区、Mac 地区、系统与浏览器应用语言、网页首选语言；只有客户明确需要时才修改。自动校时和自动时区是不同设置，手动选择时区通常不需要关闭自动校时。它们影响界面与格式，不改变实际使用地点，也不保证 Claude 账号安全。

## Mac 时区

1. 先只读核对系统设置中的“通用 → 日期与时间”，以及终端的 systemsetup -gettimezone；必要时核对 /etc/localtime 指向。不要仅凭菜单时钟同为 UTC+8 判断时区已变。
2. 用户指定目标时区后，优先在“日期与时间”关闭自动设置时区并选择对应城市。若当前 macOS 城市列表无法选中目标，可使用 Apple 提供的 systemsetup -settimezone 命令；命令应采用系统识别的时区标识。需要管理员认证时，由用户在本机终端自行输入密码，不能发到聊天里。
3. 修改后重新读取系统时区，并检查日历等依赖时区的功能。后续若又改 Mac 地区或打开自动时区，必须复查时区是否保持目标值。
4. 回退：恢复记录的原时区及自动时区选项。不要把 Asia/Singapore、Asia/Taipei 或任何其他值当成所有用户的默认设置。[Apple systemsetup 说明](https://support.apple.com/guide/remote-desktop/about-systemsetup-apd95406b8d/mac)

## Mac 地区与 Chrome 界面

- Mac“通用 → 语言与地区 → 地区”控制日期、数字和货币等格式；与时区是不同设置。只有用户要求时才修改，并在变更后核对原有工作软件的格式。参考 [Apple 语言与地区说明](https://support.apple.com/guide/mac-help/change-the-language-your-mac-uses-mh26684/mac)。
- macOS 上 Chrome 的界面语言通常跟随系统默认语言；若只想让 Chrome 使用英语，可先检查 Mac“语言与地区 → 应用程序”中是否能为 Google Chrome 单独指定 English，设置后完全退出并重新打开 Chrome。不要为了改 Chrome 界面而自动改变全机首选语言。[Google Chrome 语言说明](https://support.google.com/chrome/answer/173424)区分 Mac 与 Windows 的界面语言行为。

## Chrome 首选语言与验证

1. Chrome 菜单 → 设置 → 语言 → 首选语言；按用户要求添加 English (United States) 或其他英语变体，并移到首位。不要自动删除中文或其他语言，除非用户明确要求。首选语言影响网页内容协商，和 Chrome 菜单语言是两回事。[Google Chrome 帮助](https://support.google.com/chrome/answer/173424)
2. 重启 Chrome，在设置页核对排序与应用界面。需要时，在用户已打开的网页中只读查看浏览器报告的语言与 Intl 时区/区域值；页面脚本结果只能证明该浏览器当下所报告的值，不能替代系统设置核对。
3. 如果当前工具或浏览器阻止自动操作内部设置页，直接给用户可照做的 UI 步骤，并在其完成后复测；不要用其他自动化接口绕过阻止。
4. 回退：按记录恢复 Chrome 首选语言排序、应用语言、Mac 地区和时区。逐项复测，避免只恢复一处而留下不一致。

## Edge 或其他浏览器

沿用菜单语言、网页首选语言、页面实际报告值分开核对的方法；从客户实际浏览器的“设置 → 语言”读取当前界面与支持项，不直接照搬 Chrome 的按钮或写入其配置。企业管理策略优先确认来源。选择英语变体、是否保留中文、是否新建工作 Profile 均按客户目标；不以“代理出口在美国”为理由自动改整机地区或语言。
