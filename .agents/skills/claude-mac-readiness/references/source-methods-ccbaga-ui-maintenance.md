# CCBaga UI、维护与供应链：剩余源码完整阅读补充

固定版本：`liseami/CCBaga@6db5ad55e799c5b020be8ff5e4def2c147cd5602`，阅读日期 2026-11-10。本文供整合到 Claude Mac/Windows readiness 的 CCBaga 可选方法，**不是默认执行清单**。本轮没有启动 CCBaga、浏览器、CLI、网络探针、测试、安装器、系统设置或钥匙串操作。

阅读分工为固定 Git tree 除 `src-tauri/`、`browser-runtime/`、`vendor/` 外的全部 142 个文件：17 个已有完整阅读记录经 SHA-256 匹配复用；125 个本轮新读。全部 Git blob SHA 与固定 tree 匹配，分工内未读文件为零。逐文件、范围、方式、哈希见 [完整阅读记录](source-complete-read-manifest.json)。这不等于另三个目录已由本代理审计，也不等于第三方依赖源码全部审计。

UI、测试代码、作者说明和真实执行证据必须分开：本文确认实现和断言存在，不宣布测试已通过。已有网络 Skill、docs/usage、identity-storage、Windows/Linux 和历史发布 JSON 的完整方法复用 [source-methods-ccbaga-cleanup.md](source-methods-ccbaga-cleanup.md)；本补充增加 UI 实际调用顺序、错误/未知处理、安装供应链和现有测试的准确边界。

## 1. 先选产品与入口，避免把按钮名当范围

来源：[main](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/main.tsx)、[quick-actions](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/quick-actions.tsx)、[README](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/README.md)。

- A 是 Tauri 原生维护界面，B 是独立 Chromium；启动 A 可自动启动 B，不能把开 A 说成严格离线只读。
- 首页先选目标地区，再选动作；地区选择本身不改变公网 IP。
- “清理浏览器缓存”：先读 B 当前状态，正常退出 B，`browser_clear(includeSiteData:false)`，原先运行才重开；原先关闭则保持关闭。退出失败停止，成功文案须区分是否重开。默认保留登录、书签、密码，仍会中断未保存网页任务。
- “切换浏览器指纹”：更新 seed/目标地区后启动 B；原文网络跟随 TUN。这是浏览器设置/生命周期变化，不是换公网出口或账号恢复。
- “重置时区、语言”调用组合 `system_set_region`，会改语言和区域；不能纳入我方“保留系统语言”的默认修复。应先展示原值、目标时区/语言/地区、影响和恢复方式，用户选组合动作后才做。
- “清理 Claude 痕迹”走身份页“空身份”确认，不等同直接删除全部文件或普通缓存清理。
- 全局 busy 状态覆盖快捷动作、先进页面操作和更新；更新中主工作区 inert。方法上保留操作互斥、完成后重新读取、错误可见；不根据计时器伪造进度。

## 2. 身份策略、备份、切换、删除是四种不同操作

来源：[identities.tsx](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/identities.tsx)、[identity-model.ts](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/identity-model.ts)、[identity-storage](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/docs/identity-storage.md)。

1. 先保存任务并读当前身份、已保存卡、恢复事务及进程预览；进程列表不可读取时显示“未知”，不能当“没有进程”。最多显示前 32 个不代表只处理 32 个，执行层还要重新识别完整范围。
2. `Keep in workspace` 的 `true` 表示继续留在共享工作区；作者默认 skills/commands、plugins、MCP、settings、project records 为 true，history/cache/log 为 false。未勾的类别随身份归档，不是“未选择就不管”。执行前按具体保留/归档列表确认，不能把默认反译成所有个人资产都进备份。
3. 保存/更新备份也先 `identities_stop`，再 `identities_save`。它保留当前工作区、登录和身份绑定，但会结束识别到的进程；“无需退出工作区”不等于“进程不中断”。
4. 切换已存身份/空身份：确认 → stop → native switch → 读返回状态。恢复路径复用保存的 policy，而非把当前界面勾选强塞给旧归档。未完成恢复事务存在时阻断其他写入。
5. 操作失败仍尝试刷新状态，但保留原始错误；刷新失败不宣称回滚完成。残留扫描 revision 随身份变化失效，避免旧扫描 ID 用到新身份。
6. 当前身份永久删除会先 stop；删除已保存卡不必结束当前工作区进程。删除不新增备份，必须单列保留类别与实际损失，并勾选不可撤销确认。删除绑定浏览器资料是独立、默认未勾的选项。
7. 当前备份/保存卡不是无限历史版本；同一身份更新后的旧代次处理由原生存储契约决定，不承诺找回每个历史版本。
8. “本地未过期”仅检查本地期限元数据；UI 计时到期后重新分类；refresh_available 仅表示可尝试续期，未知/旧状态不涂绿。API key 也不等于在线有效。不得用这些徽章推导服务端认证、额度或封禁状态。

恢复：优先已有 recovery 入口和对应归档，先保护后续编辑；原生恢复失败时保留检查点并报告实际范围，不重复 switch 当“重试恢复”。完整加密、路径和 ACL 边界由原生目录对账补充。

## 3. 浏览器与身份联动，保存身份与网页登录分开

来源：[identities](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/identities.tsx)、[browser-start](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/browser-start.tsx)。

- Link browser 变化前说明会正常关闭并重开 B。启用时“把现有资料关联当前身份”不默认勾选；默认建立新资料并保留旧资料。
- 关闭联动回到共享浏览器资料，但保留各身份独立目录；重启失败与身份提交成功分别报告。
- 身份提交成功、B 重开失败时只提供重新打开 B，不能再次执行身份切换来补救。
- B 顶部身份卡显示本地绑定名/邮箱/组织；CLI 身份变化后可显示 mismatch，不代表网页已登录该账号。新资料首次仍需网页登录。
- 本地隔离和稳定 seed 不改变公网 IP，不证明远端无法关联；独立 profile 不等于加密身份归档的一部分。

## 4. 加密迁移的真实 UI 操作链

来源：[identity-transfer](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/identity-transfer.tsx)、[迁移 UI 断言](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/scripts/test-identity-transfer.ts)。

1. 选“已保存身份”或当前卡已有备份，检查备份时间。导出的是保存代次，不自动抓取当前所有后续编辑。
2. 由原生选择保存位置/导入文件；前端只持一次性 token 与显示文件名，不接受任意路径。每次重选、取消、选择失败都先丢旧 token 并清来源确认。
3. 密码按 Unicode 字符数至少 12，UTF-8 最多 1024 字节；导出再确认一次密码。UI 不持久化密码，提交时清输入；失败后重新选文件/输密码，不暗中复用票据。
4. 浏览器可选项默认未勾，仅在绑定存在时提供；包含指纹配置，不包含 Cookie、网站密码/登录资料。保留在共享工作区的类别不自动带入迁移包。
5. 导入确认来源可信，并说明恢复后 hooks/plugins/MCP/settings 可能执行命令；认证加密不等于可信来源或内容净化。
6. 导入仅相同 OS，新增保存身份，不切换当前身份；已有同账号/浏览器配置拒绝覆盖。原生 8 GiB/100000 成员、白名单/解包/权限与同机重加密细节看身份存储原文及原生审计。
7. 导入后刷新失败可能是“已新增，但返回失败”，UI 刷新目录并继续保留错误；不要自动再导入。文件导入成功不证明 Windows DPAPI、macOS Keychain account 或远端令牌可用。
8. 密码不可恢复；不覆盖已有导出文件，私有保管文件和密码。恢复具体身份是后续独立动作。

## 5. 文件残留清理与 B 全清理：两条完整范围

来源：[claude-residue-panel](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/claude-residue-panel.tsx)、[cleaner-model](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/cleaner-model.ts)、[browser](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/browser.tsx)。

文件残留：

1. 进入页面不自动扫描；用户检查后只默认选择 `risk=safe && exact=true`。不完整统计项不可选；无条目但有警告显示“部分未检查”，不说环境干净。
2. 展示路径、规模、影响和具体 JSON 字段名；不把凭据正文送进 UI。文件残留路径不访问 Keychain，默认 Claude 目录外的自定义配置根不在范围。
3. 多选按真实父子路径去重；Windows 折斜杠/大小写，POSIX 保留大小写、空格、反斜杠意义。取消子项也取消包含它的父目录选择，避免隐式扩大删除。
4. “全选可清理”可包含登录/历史；确认窗重新列出具体选中项、登录需要重登、历史永久消失、无备份，并默认聚焦取消，需勾不可撤销。
5. 确认 → 清旧扫描与选择 → stop → 清指定 ID → 无论成功/部分删除/异常都重扫 → 刷新身份。进程停止失败也不继续删除；新扫描不自动沿用选择或自动再执行。
6. 这是直接删除，不能用身份保险库的恢复能力覆盖所有文件残留；执行前需要恢复保证时另做已授权一致备份。

B 浏览器：

1. 配置修改与清理前须停止 B；缓存按钮还要求已知非登录 cache 候选及无 cache_error。
2. 全清理按钮即使缓存列表为空也可使用，因为密码、历史等并非 cache 行。全清理单独强确认，发送 `includeSiteData:true, resetProfile:true`；仅缓存不发送 resetProfile。
3. 全清理范围是**当前身份整个本地 profile**：登录、密码/密钥、书签、历史、扩展、设置、缓存；不留备份。其他身份 profile 和身份保险库不在此次范围。
4. 这不是普通 Chrome/Edge 单站点清理，也不是只清 claude.ai Cookie。来源 YAML 残留的“清空站点数据/保书签密码”等旧词条不能覆盖当前全清理确认文案。
5. 失败如已删部分应报告已处理数量/后续未执行，再核实际剩余；重试必须重新确认，不把旧成功样式当已完成。

## 6. 浏览器环境配置、测量与绿灯的精确含义

来源：[browser-network](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/browser-network.ts)、[browser-verification](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/browser-verification.ts)、[browser-model](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/browser-model.ts)、[browser-start](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/browser-start.tsx)。

1. 稳定 seed 为 1–4294967295 整数；显式 proxy 需协议主机端口，带密码代理交给本机工具；follow_machine 与手动语言/时区是不同模式。先保存再启动/对齐，不能修改正在运行的 B 参数后声称生效。
2. 设为默认浏览器是向 OS 发请求，随后最多 20 次、每 1.5 秒读回；请求已发不是已成为默认。用户取消/未完成时保持实际状态。
3. 机器出口检测与 B 网页测量分开；机器探针不替代浏览器证据。
4. B 页面启动自动测量 navigator/Intl、UA high entropy 平台版本/浏览器版本、CPU、geolocation 权限状态与 HTTPS 出口；不请求真实坐标。出口服务按序回退，每个 8 秒、最多 32 KiB，必须合法 IPv4/IPv6 和两位国家码；备用服务请求仍沿同一浏览器网络路径，不是直连回退。
5. 本地随机 token 回环 context/report 连接独立；heartbeat 10 秒，断连或回报失败不能全绿。当前目标改变后旧结果重新比对，重测立即进入 checking，不复用旧绿。
6. 核验覆盖：出口国家、网页时区相对配置/机器/出口、本机首选语言与区域、网页语言、平台/版本/CPU、引擎版本、网页定位 denied、本机定位 false；未知值保持待核，不能用空串填通过。
7. Windows 平台要求 Win32；Mac 核平台/版本/CPU；Linux 平台与 CPU 能核，但该模型不比较 Linux OS 版本。不要泛化成三平台 OS 版本都实测一致。
8. full passed 需要目标存在、完整回报、连接有效、所有检查 true、无错误。**没有独立 DNS、WebRTC/STUN、Canvas/audio/font/GPU 泄漏或账号业务验证**；“真实设备图形”配置开关不是测量结果。绿灯仅说明本次这些观测与目标匹配。
9. “对齐美国系统”先核实际代理出口 US 与有效时区，再改机器时区/en-US/en_US并关闭系统定位；不改代理节点，可能部分成功，需读回；其他地区不能套用美国操作。我方保留语言默认仍优先。

恢复：保留原配置和原系统时区/语言/地区/定位；B 停止后恢复原参数，再启动并读回各项。没有来源证据能保证清理、seed 或对齐解决账号限制。

## 7. 系统页面：draft、readback、权限与重新登录

来源：[system](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/system.tsx)、[windows-region.ps1](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/scripts/windows-region.ps1)。

- 原状态和待应用值分开；focus 刷新只读，不能把表单选择当系统已改。
- 时区、语言、定位各自操作、各自核验。打开定位设置只说明设置窗口已开；只有读回明确 false 才算关闭，unknown 不涂绿。
- Windows 语言脚本将目标排到首位并保留其他语言及输入法；写 UI override、按需文化区域。当前 PowerShell 的 Culture 缓存不能证明持久化，原生方另起会话核对。显示语言还可能需安装语言包、注销重登。
- Mac Keychain unlock 仅解锁，后续每条凭据删除仍需 OS 判断权限；不重设所有者、ACL、不跳过授权。Windows UI 不提供此 Mac 入口。
- 所有恢复依据操作前原值；不能把改语言、禁定位当修复网络的必选步骤。

## 8. CLI 维护：按安装来源，预取安装器，再核程序

来源：[claude-cli-panel](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/claude-cli-panel.tsx)、[POSIX CLI](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/scripts/claude-cli.sh)、[Windows CLI](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/scripts/claude-cli.ps1)。

1. UI 先确认维护会结束已识别 Claude 进程，stop 成功后才管理程序；保留设置/Skills/会话/项目/身份库不等于保留正在执行任务。
2. POSIX 检查原生 `~/.local/share/claude` 与指向 versions 的 launcher、macOS Homebrew 两个 cask、PATH 与 nvm 的 npm global roots；roots 去重，多重来源先卸载再按 npm 优先、brew 次之、native 最后重装。未知/自定义入口或链接目录停。
3. 原生重装先 HTTPS 取官方 install.sh（60 秒、shebang、<64 KiB）；完成下载检查后才同卷移动旧程序/launcher 至私有备份，再运行安装器。安装器内容格式检查不是代码签名或固定版本审计。
4. POSIX npm/brew 重装不享有原生程序归档的全套回滚；不能把“失败恢复原程序”泛化到所有来源。原生捕获失败触发 EXIT 恢复；恢复失败保留唯一目录，不能宣称断电/强杀也自动恢复。
5. Windows 识别 native、npm、bun、winget：native launcher SHA 对照 versions 文件；npm shim 内容/全局根、bun 固定位置、winget固定包/链接目标逐项识别。拒 reparse 路径或自定义 launcher。
6. Windows native 先取 install.ps1（60 秒、≤1 MiB、严格 UTF-8 或字符串、param 开头、可解析 ScriptBlock），再备份 launcher/version 并核 SHA。安装/版本核验失败逐文件恢复核 SHA；恢复受阻保留副本。包管理器路径没有等价通用备份保证。
7. 使用原管理器卸载/重装，真正完成需程序来源、PATH、旧安装消失或新 `--version`成功，且收到完成标记；中断、超时、版本异常不能报完成。只读“版本”查询仍会运行识别到的 CLI，此研究不执行。
8. 配置目录、登录材料和卸载 CLI 程序分开；CLI 重装不会删除自定义配置根、旧登录或服务端状态，也不自动保证登录可用。

## 9. 安装、升级与可恢复事务

来源：[install-apps](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/scripts/install-apps.py)、[dev-install](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/scripts/dev-install.py)、[install-linux](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/scripts/install-linux.py)、[app-update](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/app-update.tsx)。

- Mac 正式安装先检查固定 bundle ID、codesign deep strict、Gatekeeper和 A 内嵌页面实际引用；准备完整 A/B 暂存，再只退出固定安装路径程序，最多等 15 秒。程序不退出则保持原安装。
- 移动旧两 App → 发布新两 App → 再验签/注册；捕获异常/中断按磁盘实际状态恢复，双重失败留恢复 stage。Dock 只刷新匹配身份的旧/新项；Dock 刷新失败不撤销已成功安装。
- 开发入口仅 Apple Silicon/macOS，过滤 Apple/updater 凭据，构建 ad-hoc debug；`--development`不能接受外来 DMG。它不是关闭 Gatekeeper 的通用手段；正式安装继续严格校验。
- Linux 源码安装要求 host/B 可执行且 UI 引用完整；目标为专用用户前缀，拒链接父目录、非自有目标、自定义 launcher和运行中的 A/B。同卷 stage、替换、desktop文件/launcher恢复；失败不能合并覆盖旧资源或删唯一恢复副本。
- Linux desktop Exec 同时处理两层引用与 % 字段转义，以固定 `/usr/bin/nice -n 0 --`原样执行，不使用 shell 或环境赋值解释；特殊路径如中文、空格、%U、=、$不能手工拼接简化。
- A 界面启动可静默检查更新（20 秒），真正下载/安装由用户按钮触发，按真实字节显示进度；未知总量不伪造百分比。Windows安装前正常退出 B。
- Mac sidebar update 仅 A；完整 A+B 需 DMG。Windows updater安装器更新 A+B；Linux不调用 app updater，走安装包/包管理/源码流程。
- 安装成功但 relaunch失败：重试仅 relaunch，不重新下载/安装。完成时分别报“已安装”“未重启”“B 是否更新”；不要把所有平台归成同一自动更新承诺。
- Windows NSIS未 Authenticode签名；Tauri updater签名仍可验证下载版本/字节，两者不同。不得用关闭系统/组织安全策略替代核来源。

## 10. 固定引擎、构建与发布供应链

来源：[fetch-browser](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/scripts/fetch-browser.py)、[browser_ui](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/scripts/browser_ui.py)、[release workflow](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/.github/workflows/release.yml)、[release scripts](https://github.com/liseami/CCBaga/tree/6db5ad55e799c5b020be8ff5e4def2c147cd5602/scripts)。

1. Chromium 固定 148.0.7778.215，三平台各固定来源 URL/SHA；不抓 latest。Linux/Windows限 x86_64，Mac含 arm64。先校验档案摘要、架构与版本，完整暂存复制成功才 publish；现有目标拒覆盖，失败清暂存或报告保留位置。
2. Linux tar data filter、Windows zip拒绝绝对路径/.. /冒号/反斜杠；保留引擎资源与许可。资源替换是完整替换，不并集合并已删除库。摘要证明取得预期字节，不证明 fork 安全补丁齐全。
3. browser_ui验收 HTML≤2 MiB、必须 module入口、script/modulepreload/stylesheet引用为本地存在文件且 resolve 不越根；不执行页面。它只核资源契约，不证明运行逻辑安全。
4. Mac签名按叶子 Mach-O → Helper app → Framework → outer app，不跟随 symlink；正式runtime/timestamp，开发ad-hoc无runtime。仅Renderer/GPU JIT entitlement。先给 B 公证装订，再封装进 A，禁止后来重签破坏票据；A/更新归档/DMG各验签、公证/装订/Gatekeeper。
5. stapler仅 error68且NSURLErrorDomain网络失败最多3次；无效签名/票据即停。更新私钥仅给签名子进程；构建和DMG工具不继承 Apple/updater secrets。
6. Linux标准发行产物 Ubuntu22.04基线、glibc≤2.35：DEB、RPM、AppImage逐一提取核 host/engine/资源/符号需求。Arch另固定容器摘要、当前 Arch依赖构建，不冒充同一glibc基线。PKGBUILD源码默认main可变；官方CI用提交固定，社区本地配方与可复现固定版本应区分。
7. Windows MSVC/NSIS构建与真实安装验收阶段分离；一次性 GitHub runner 有保护，不碰已有应用/Claude数据。Windows2025和2022对同一安装器做安装/升级/卸载/实际B回报；只是存在验收程序，当前本轮没跑。
8. Release权限以 repo/ref/actor/triggering_actor限制 owner，正式release重新构建；main手动 installer_run仅复核既有无签名样本，不是绕过正式发布链。最终tag绑定已验收commit，校验九文件白名单后发布。
9. 公开九文件：六个完整安装器（MacDMG、WinEXE、DEB/RPM/AppImage/Arch）、Mac updater archive、合并latest.json、SHA256SUMS；独立签名、公证记录、engine map仅CI。汇总前逐平台清单必须覆盖要求文件，重新hash不能补救“未经过平台验收的漏项”。
10. bun.lock逐项版本/依赖/peer/OS/CPU/integrity已读，锁定不能代替依赖安全审计。checks workflow用frozen lock、固定Rust/Bun/Node/Python与Action SHA，单独cargo-audit/bun audit；当前公告结果仍需当次查询，不能引用历史JSON证明今天无漏洞。
11. GLib回补是锁定上游0.18.5原始字节与官方两行修复、构建patch path与优化variant_iter断言；未伪升版本。vendor完整源码由另分工读，不能将来源回补测试等同完整第三方源码审计。

## 11. 现有测试到底验证了什么

本轮全部静态读正文，**零测试执行**。固定来源：[tests](https://github.com/liseami/CCBaga/tree/6db5ad55e799c5b020be8ff5e4def2c147cd5602/tests)、[scripts tests](https://github.com/liseami/CCBaga/tree/6db5ad55e799c5b020be8ff5e4def2c147cd5602/scripts)、[src tests](https://github.com/liseami/CCBaga/tree/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src)。

| 程序/fixture | 实际断言边界 | 不能推导 |
| --- | --- | --- |
| identities-fixture + UI/operation/transfer | 40虚构身份、mockIPC、显式释放channel事件、取消默认、参数、busy、失败刷新、真实事件百分比、语言、到期、迁移密码/重选票据 | 真Keychain/文件事务或真实账号有效 |
| browser-cleanup | 无cache也能全清、独立checkbox、仅缓存窄参数、进度、错误 | 真资料目录删除/恢复成功 |
| browser-verification +纯模型 | 目标未知不通过、断连/HTTP错误、US/JP冲突、语言脚本、CPU/平台、回传与样式 | DNS/WebRTC/账号风控通过 |
| browser-profiles | 实际隔离持久Chromium两profile、合成Cookie/localStorage与空profile | 全部浏览器存储、DPAPI跨机器或网站隔离效果 |
| residue + cleaner-model | safe/exact默认、父子去重、不完整拒选、stop失败、部分删后清选择与重扫 | 原生路径ACL/TOCTOU完整安全 |
| network-diagnostics | 四域名、Cloudflare质询可达、缺结果/null失败、重测清旧绿 | Claude登录/模型/API调用成功或固定出口 |
| fetch/package/install tests | 临时树、移动前后取消、双重失败保留恢复目录、资源/链接、原生GIO路径参数 | 断电、磁盘损坏或客户机完整灾难恢复 |
| windows CLI/System | 临时假CLI及安装器样本、native回滚哈希、npm/winget来源、自定义保护；系统变化仅一次性CI后恢复 | 所有真实npm/bun/brew包/语言包和权限组合均验证 |
| sign/release-env/assembly | 假Mach-O树、签名顺序、JIT范围、凭据环境过滤、票据网络重试、九文件完整性 | 真签名、公证或当前可下载产物可信 |
| test-skill-install | npm skills@1.7.2四agent临时HOME实际复制安装并比较文件 | UI未固定版本的skills命令未来行为不变 |

## 12. 完整文案、样式和图像的对账结果

- 两个locale各1237项：逐项解析所有key/value，中文值均等于中文源key；配对阅读全部英文值。词条仍含旧的全局清理、SSH/VPS原生表单、Keychain清理等遗留描述。**词条存在不是当前入口可用**，以main实际组件、invoke和原生注册为准；不能从语言包恢复已移除功能。
- UI本身是短操作、确认、结果与折叠日志；日志保存原始消息，仅展示时翻译，未知消息保留原文。路径/用户输入不翻译。进度channel隔离不同operation，最多2000条，未知总量无百分比，失败/回滚不被完成样式掩盖。
- 所有CSS、响应式和reduced-motion规则已读；没有运行UI，不宣布可访问性或视觉验收通过。可复用的是取消默认焦点、未知/错误有文本、busy禁重入、日志可展开这些方法。
- 四张本轮图片已视觉查看：两品牌标、双App拖入Applications的DMG装饰背景、README双电脑像素图。它们没有新增环境步骤或实测证据。
- docs/brand-logos.svg全部markup与两个完整base64图像已解析；图像SHA匹配所看原JPG。architecture.svg完整几何/箭头/正文已读，图示A UI→Rust→platform，B↔token回环，UI提示独立Skill→VPS→住宅出口；platform文字仍写Objective-C/Linux Rust而未提Windows，不能据此否定源码中的Windows实现。SVG查看器不支持，未虚称渲染验收。
- 五个AI SVG完整读源、MIT许可读完；无script/外部请求，品牌标不代表厂商背书。第三方Cromma许可与Chromium完整credits由NOTICE及对应vendor分工继续确认；总仓MIT不能自动覆盖第三方资源权利。

## 13. 可直接补进 Skill 的准确纠正

1. 保留 CCBaga完整可选路线及作者条件，不把所有动作并入默认“修复”；语言/区域变化、正常退出B和结束Claude进程在预览前说清。
2. 缓存、文件残留、空身份、当前身份永久删、保存卡永久删、B整个profile重置、CLI卸载、迁移导入分别列范围和恢复，不共用“可恢复/不动登录”的承诺。
3. 备份“工作区不变”仍可能stop进程；导出仅已保存备份；导入成功不自动切换、不证明登录恢复；重开浏览器失败独立重试。
4. 浏览器绿灯必须附核验项和当前timestamp，标DNS/WebRTC/账号未测；连接对端IP不当公网出口。
5. 更新/安装确认最终实际版本、A/B覆盖、签名类别、程序是否重启；原生安装器预取与有限回滚条件保留，不复制成自动无损重装保证。
6. 固定依赖/源码/发布哈希与运行结果分层；上游测试定义、上游历史报告、本轮静态阅读、目标机现场结果分四栏。不存在的证据不填绿，也不因未证把作者完整方法从目录删掉。
