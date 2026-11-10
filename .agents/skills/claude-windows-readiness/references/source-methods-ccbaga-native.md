# CCBaga 原生、浏览器运行包与 vendor 补读

固定提交：`6db5ad55e799c5b020be8ff5e4def2c147cd5602`。本轮仅静态阅读；未运行源码、测试、安装或探针。本参考对应的原生、运行包与vendor现已完成全文覆盖；逐文件证据合并于 [完整阅读记录](source-complete-read-manifest.json)，阅读不等于安全认证或目标机验收。

## 原生基础层与当前入口

- Tauri WebView公开能力仅core/window拖动、updater和process restart；没有通用fs/shell插件权限。自定义命令仍包括身份、文件选择迁移、系统和浏览器等，不能因此称应用无原生读写权限。网络Skill仍在应用外。
- 源码版本配置为0.2.0，正式发布脚本另覆盖版本；不能从Cargo/tauri静态默认推断安装包正在运行0.2.0。Mac最低12.0、dev签名为ad-hoc，正式Developer ID由发布流程覆盖。
- Mac旧凭据扫描枚举属性，识别默认及Claude Code-credentials-*后缀与Safe Storage；但Identity快照/恢复只处理三个固定默认服务。旧Cleanup.m单项删除函数存在不等于有当前WebView删除入口：native.rs已移除它的包装，main.rs也不注册该批量动作。需要区分可见代码、内部函数与可用操作。
- Mac浏览器占用识别使用SingletonLock、bundle、可执行名、唯一绝对user-data-dir、目录device/inode、UID及启动时间复核；未知不能退出。浏览器quit只请求正常terminate；其他Claude停止路径需继续读Rust，不拿此函数代证。
- Mac系统语言写首选并保留后备；地区先目录预检再时区/locale写入，部分失败会留下已改时区；时区命令会关闭自动时区。定位依靠系统设置Accessibility语义开关及CoreLocation读回，不写locationd私有DB；无权限保持未完成。
- 区域目录固定13项，Chicago/Phoenix/US-Pacific等非目录组合保持未知；locale国家单独解析，支持ICU/POSIX与BCP47 rg覆盖，语言/字体脚本不推国家。
- 原生出口probe显式no_proxy，再按指定proxy建立同一路由client；两服务顺序备援、8秒、禁止重定向、响应32768字节上限。checks中图形/字体与DNS/WebRTC始终待测；主体显示包括完整出口IP，不等于我方脱敏报告输出。浏览器与机器出口对照显示“上次检测”，需明确样本时间。
- native测试定义使用临时Keychain、内存偏好、合成argv和测试自身/已回收子进程；本轮未运行。UI语言仅zh/en，独立于系统语言，正常关闭窗口只是隐藏，托盘退出才退出宿主。

## 清理入口、范围与不可混用的保护

来源：[cleaner.rs](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/cleaner.rs)、[目标与扫描](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/cleaner_targets.rs)、[文件残留入口](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/cleaner_residue.rs)。以下均为源码行为，不是本机执行结果。

- 当前残留清理不提供任意路径删除：从本轮扫描的固定ID选择，复核范围、完整统计、快照和Claude停止状态；恢复日志未完成时阻断。风险safe不等于无损，账号、历史、备份等需单独选择；直接删除没有隐式备份和撤销。开始前失效不删；中途Claude重新启动或删除失败则停止并报告已完成数/剩余项，不能称全部完成。
- 固定路径统计完整遍历，不读内容计算摘要；其指纹是路径/元数据树（inode/device、mtime/ctime、长度等），不是每个文件内容SHA。独立“选择文件夹扫描”有5秒、100000条目、深度64边界，跳过依赖/构建/vendor/browser-runtime等目录，超限会给不完整警告，不能统一宣称所有扫描无上限。
- 旧通用collect/transform包含shell、npm、git、ClaudeBackups及Keychain属性等定义，当前residue过滤这些对象，通用删除RPC已移除。注册的旧扫描入口仍可只读发现文件夹/组织会话；有函数或测试不证明当前UI有删除按钮。
- 可选组织查找确实读取json/jsonl/log/txt正文，以8–100字符组织ID做边界匹配；限64MiB/文件、20000条目、深度10、5秒。默认残留扫描不调用它，不能写成“应用从不读会话正文”。
- 5种锁名只将常规文件/空目录列为残留，未知非空锁目录保留；扫描后新增内容使快照失效。身份备份只排除这些瞬态锁，不顺带删除工作区锁。唯一例外是备份当前默认`.claude/debug/latest`时省略该生成链接；通用归档/导入/恢复仍拒绝链接，不能泛化为任意同名链接可忽略。
- 配置修改按键保留未知字段、MCP/项目索引/主题等；残留credentials仅去`claudeAiOauth`、`trustedDeviceToken`。旧settings转换能去代理/ANTHROPIC环境键，但不是当前残留清理或默认身份切换的同义操作。
- Windows使用实际APPDATA/LOCALAPPDATA及固定MSIX包`Claude_pzs8sxrjxfjjc`目录，保留程序、MCP、plugins、Local State等个人配置；Linux只处理自身XDG缓存/日志，不能套macOS Desktop路径。
- POSIX Claude停止识别默认版本路径、确切CLI名、官方Node入口等，重查PID+可执行路径后TERM→800ms→KILL→200ms，最多3轮。该路径没有浏览器识别使用的启动时间字段；Windows则持有句柄并核查创建时间/可执行文件/当前用户。不能把两种保护强度说成一致，也不保证未识别安装方式都已停止。

## 身份备份、切换、删除、恢复与迁移

来源：[store.rs](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/identities/store.rs)、[archive.rs](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/identities/archive.rs)、[portable.rs](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/identities/portable.rs)、[identity选择](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/cleaner_identity.rs)。

- 七项“保留”策略：skills、plugins、MCP、settings、projects默认true，history/cache默认false；true是留在当前工作区，不随身份归档交换。skills还包括commands/agents/hooks；MCP覆盖OAuth/客户端/IdP等字段。保留settings仍交换3个认证env键与apiKeyHelper，但保留ANTHROPIC_BASE_URL及共享代理；切换账号不等于切换API提供商或出口。
- 原地备份需Claude停止：选定源快照→凭据读取/格式范围验证→不可变归档新代次→fsync→重新核对所有源→解包并验收认证结尾→SQLite提交。工作区、锁和浏览器选择不因此切换。已有同账号归档以本地主密钥HMAC的UUID/组织（或规范邮箱/组织）匹配，保留自定名称；不同组织/未知账号不合并。
- 切换先完整验收目标归档，再保存当前身份并提交recovery/target记录，之后清当前→凭据清理→按本次保留策略恢复目标→提交选择。数据库与文件系统并非一个原子事务。无修改阶段失败撤销标记；修改后失败尝试恢复原身份；Claude仍在运行或自动恢复失败时保留恢复日志并要求显式恢复。
- 显式恢复会先再次备份崩溃后当前状态为独立checkpoint，避免新工作直接被覆盖，再清相关目标、恢复原身份、提交。共享配置以字段合并保护较新的非身份设置；整目录来源依然可能清理并恢复对应目录，不能泛称所有后续编辑都原位合并。恢复需可读完整归档和密钥，服务器令牌有效性未验证。
- 当前身份“直接删除”没有隐式恢复副本，部分失败提示部分已删除；删除已保存身份用`.trash-ID`协调文件和SQLite，提交后清理暂存，失败保留下次回收。它不等于可恢复的系统回收站，也不是自动创建备份。
- 本机归档为BAGAID01、每档随机密钥+AES-256-GCM、64KiB认证帧和认证空终止帧；Zstd级别3/checksum，兼容旧gzip，解压window log27。解包必须排空认证结尾，拒绝截断、附加密文、重复/穿越/特殊成员；核对平台、原home、ID及允许源。主密钥缺失而已有归档时拒绝重建覆盖；丢失密钥不能靠新建恢复。
- 列表刷新不解密归档、不回收归档文件、不查询钥匙串；但Database::open会初始化/迁移**应用自己的**SQLite与目录，并非绝对零写入。当前卡片有界读取默认配置/文件凭据，只输出显示字段和本地expiry状态；local_unexpired/refresh_available/api_key不是服务器登录验证。进程查询失败显示unknown而不是已停止。
- 显式Store维护可清旧stage、处理trash、索引旧归档及回收未引用代次；transfer专用open不做这些维护，恢复日志存在时拒绝迁移。保留这一区别，不能因为列表只读就说所有打开保险库都无回收。
- `.bagapack`只支持同OS跨设备单身份迁移；原生选择器发放5分钟单次且操作类型绑定的token，WebView不传任意路径。导出目标必须不存在，文件/父路径不能链接且需当前用户归属。导入前后重查所选文件对象、长度、mtime。
- 迁移密码至少12个字符且≤1024 UTF-8字节；固定PBKDF2-HMAC-SHA256 600000次、32字节盐，随后认证加密。总数据8GiB、100000成员、4096源、8MiB元数据、4096字节成员名；GNU长名额外块计预算，拒绝PAX/链接/设备/重复/未知字段/隐藏尾随数据，Windows另拒绝ADS、保留设备名与大小写碰撞。
- 迁移先全部认证/解压/白名单验收，再重定位home、分配新ID、用目标机器主密钥重封存、提交新增行。重名账号拒绝，数据库失败仅移除本次新文件；当前身份与浏览器选择不切换，不操作目标钥匙串。可选带seed/follow_machine/language/timezone/native_graphics，**不带代理、Cookie、网站登录资料、浏览器profile、SQLite或主密钥**。Mac迁移中的3种默认服务凭据存在于加密包内，敏感性不能因为“非浏览器资料”被忽略。

## 浏览器资料、安全边界与真实状态

来源：[browser工作区](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/browser/workspaces.rs)、[profile.rs](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/browser/profile.rs)、[server.rs](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/browser/server.rs)、[browser_link.rs](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/identities/browser_link.rs)。

- 身份联动默认开，每个随机身份ID分配独占slot及非零seed，最多1024次碰撞尝试；seed取本软件随机ID的SHA而非账号UUID。首次空资料的预留ID用于第一次保存，保持种子；合并旧同账号卡保留当前slot，但不会删除被替代profile。关闭联动切legacy；开启可选接纳legacy或新资料，恢复未完成时不能改变选择。
- 正常身份动作先退出关联B，动作结束刷新参数；动作成功且联动开、或此前B正在运行时再启动。重开失败作为独立警告，不能推翻已提交身份成功。原地备份不做此切换。当前Claude与绑定卡不匹配显示mismatch，不能将旧B卡改名成新账号。
- Mac启动优先已安装B，然后应用数据/开发资源；可从内置Browser.zip用ditto解包。A启动会打开B测量页；B已运行时再开一页重新接通本次会话。原生browser_rotate本身先退出、改seed/地区、清代理、native_graphics=false并更新会话后返回，是否再次启动由调用流程决定。
- 缓存/站点清理是停B后固定目录递归删除；**完整reset**才做全树归属/链接/快照预检、深度优先逐文件删除、每250ms和边界复查占用/元数据、新增文件不递归吞掉，失败报告n/N。二者保护不同。根SingletonLock/Cookie/Socket受限例外仅删除链接本身，其他链接拒绝。
- 删除已保存身份时可另选删除对应B资料；必须不是当前/占用资料，身份动作提交后再删目录，可能得到“身份已删，资料部分未删”，没有自动rollback。该路径也不是完整reset逐成员算法。普通Chrome资料不属于这些B清理范围。
- Preferences写入语言、WebRTC策略、普通/粗略/精确地理定位deny并清过往允许项；时区不写Preferences。浏览器退出是正常窗口关闭请求，最多等5秒，仍运行则停止后续资料操作。
- 本地测量服务监听127.0.0.1随机端口、24随机字节nonce；最多32并发，头8192/体16384字节，整体3秒期限。过期nonce410；刷新机器/身份后锁内重查token。固定静态资源根、MIME和CSP；无通用Tauri/文件写接口。收到测量报告不等于Claude认证已成功。
- Linux默认浏览器注册只在明确选择时用GIO/xdg-mime，正确转义Exec；Windows注册HKCU固定capability/class，受保护UserChoice只读，打开系统默认应用界面后读回，不冒称默认设置已完成。

## 网络导航、系统差异与测试证据限度

来源：[network_links.rs](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/network_links.rs)、[linux.rs](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/linux.rs)、[windows.rs](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/windows.rs)、[claude_cli.rs](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/claude_cli.rs)。

- GUI网络资源只接受webshare/dmit/skill固定枚举；供应商URL保留作者推广参数，网络Skill在应用外执行，不是GUI已经安装VPS/SSH。四域名GET诊断显式no_proxy、5秒连接/8秒总超时、并发、不跟随重定向，不发送Cookie/Authorization。
- claude.ai/api.anthropic.com/platform.claude.com的2xx、401、404、官方HTTPS重定向或带cf-mitigated:challenge的403可记可达；下载源必须HTTP200且≤64字节严格三段数字版本正文。显示的remote_addr是连接对端，不能称出口IP、DNS泄漏通过或账号可用。
- Linux时区用timedatectl并读回；语言/区域只验证当前会话已有值，不提供通用写入，须桌面设置后注销重登；保留locale modifier，防止rg误判。只GNOME gsettings定位可写并读回，其他桌面unknown；GNOME关闭也不证明portal/其他服务关闭。Secret Service/KWallet不自动读删。
- Windows时区通过tzutil应用并原生读回，拒绝则打开系统设置；时区映射取固定Unicode CLDR48，一对多返回首个代表区、固定地区locale可帮助消歧。显示语言用GetUserDefaultUILanguage，区别区域格式。保存首选语言不证明当前登录会话切换，需注销/语言包；定位只能读注册表并打开设置让用户手动关，不直接改定位值。凭据管理器不自动读删。
- Windows浏览器仅对候选引擎/明确资料参数核验当前用户、创建时间、目录卷/文件ID；畸形/未知参数拒绝动作。Windows CLI的旧PEB参数读取与浏览器QUERY_LIMITED_INFORMATION路径不同；WOW64读取不支持不能泛称覆盖所有CLI安装。文件安全只信当前用户/实际默认owner SID，不因管理员组成员身份认定归属。
- CLI管理仅read/uninstall/reinstall固定动作；Windows去继承PSModulePath并使用固定嵌入脚本；POSIX用交互登录zsh初始化真实PATH。读任务60秒、写任务600秒；超时结束本次进程组/Windows Job并提示可能部分完成，不把子进程启动当完成。输出需固定DONE标记、退出成功和版本核验；真正安装/卸载范围还需结合对应脚本阅读证据。
- 测试源码覆盖临时文件/合成账号、加密损坏/截断、恢复checkpoint、代理保持、MSIX/XDG、进程复查、网络localhost响应、真实阶段次序等；本轮全部**只读未运行**。有测试不等于上游CI本次通过。Windows时区测试仅GITHUB_ACTIONS=true时才真实改并恢复；签名发布包验收测试ignored、须显式提供manifest/archive；普通套件不能代证下载发布包真实性。性能基准也ignored，不能写成本轮速度实测。

## 运行包资源与依赖补丁

来源：[Mac B启动器](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/browser-runtime/launcher/CCBrowser.c)、[NSIS钩子](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/windows/installer-hooks.nsh)、[GLib来源清单](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/vendor/glib/UPSTREAM.json)、[修复后的迭代器](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/vendor/glib/src/variant_iter.rs#L121)。

- Mac从B独立入口打开时，启动器查当前用户的A进程，未运行则以同目录A或固定bundleID后台启动；等宿主发布launch.args且没有identity-switch.pending，最长8秒，不就绪直接失败，不退到另一个资料。已带user-data-dir参数则绕过注入；固定本机start.url要求回环地址/有效端口，并尝试连接，刚启A还检查文件时间。它最后exec同包Chromium，不修改profile。该C入口主要是本机协作，不具有Rust资料重置的完整归属/链接校验，不能代证防同用户篡改。
- Mac浏览器entitlements仅allow-jit，并按注释仅供Renderer/GPU helper；没有任意库加载、调试或未签名执行内存授权。此为配置可见，正式包签名、公证是否真实有效还需发布证据。
- Linux.desktop声明B为HTTP/HTTPS/html处理候选，不等于成为默认；Windows安装钩子建B快捷方式，卸载仅删该快捷方式及自身HKCU关联注册，不删资料、不改其他浏览器UserChoice。
- 两PNG已视觉查看：橙色清理人物与橙色Chromium样式标志；两ICNS全部11成员、两ICO全部6尺寸成员已解析，ICNS info是assetcatalog名称字典。它们是品牌/分辨率资源，没有设置步骤；未把二进制图像说成可运行环境工具。
- Cargo.lock已从首行至5792行完整读完：列出固定Rust解析版本/来源checksum/依赖边，并不下载或验收这些crates本体。例如本快照zstd实际锁到0.14.3，而旧兼容测试注释提0.14.2；描述本次依赖应以lock为准，不将旧注释当实际构建版本。
- vendor/glib是GTK3链的0.18.5发布库，最低GLib2.56/Rust1.70；唯一项目行为回补是VariantStrIter给C输出参数传可变引用。我们静态算hash对照UPSTREAM.json的121原文件：120一致，variant_iter唯一差异恰与patched_sha256一致。这只验证与仓库内清单一致，未另取官方crate/提交验证清单可信度，也没运行优化测试。
- 通用GLib绑定含日期/时区、文件/环境、spawn、URI、日志、GObject、线程/事件循环等库API；注释掉的GIR TODO是未生成绑定，不能列成CCBaga未实现功能；库内spawn/unlink等能力也不等于应用向用户开放任意命令或删除入口。库测试/编译失败stderr/基准仅证实作者定义了相应约束，不能当本次执行通过。全文读取不构成依赖零缺陷审计。
