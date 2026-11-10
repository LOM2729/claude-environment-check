# CC Baga：完整能力与待验证方法

完整原生实现和界面/程序维护/签名供应链已补读，新增流程分别见 [原生与资料保护](source-methods-ccbaga-native.md)、[界面与维护](source-methods-ccbaga-ui-maintenance.md)。旧函数、测试或遗留文案不自动等于当前可用入口。

2026-11-10 补齐：[CCBaga 与清理来源完整方法](source-methods-ccbaga-cleanup.md)保留九字段、密钥/TOFU、check→deploy→fetch→TUN→断开及部分失败恢复，也保留身份/历史勾选和迁移限制。本页能力表不再作为完整步骤的替代；作者文档、静态实现和上游验收分别标记。

用于用户要求参考 CC Baga／CCBaga、列出整套做法，或保留未经检验选项时。与 [完整环境方法](complete-environment-method.md) 配合使用；只列方法时不安装、不运行、不扫描真实环境。

来源：[liseami/CCBaga 固定提交](https://github.com/liseami/CCBaga/tree/6db5ad55e799c5b020be8ff5e4def2c147cd5602)，提交日期 2026-10-28，本次静态核对 2026-11-06。以下覆盖本轮确认的功能与相关未验证主张，不能代表未来版本。未复制或执行项目代码。源码能确认动作，不证明目标机成功，更不证明降低封禁概率。

## 一、应用与浏览器运行环境

| 功能／做法 | 已确认实现 | 限制与选择条件 |
| --- | --- | --- |
| 双应用结构 | A 为原生宿主，B 为独立 Fingerprint Chromium；通过随机令牌的回环会话交换测量 | Mac 打开 A 会准备／启动 B，不是纯离线查看；首次启动也遵守本 Skill 网络前置条件 |
| 浏览器来源与版本 | 固定引擎 148.0.7778.215，开发下载器检查 SHA-256、架构、版本；正式包带 B | 下载器会执行引擎版本命令，不能当只读下载；不在本轮安装／运行 |
| 支持平台 | macOS ARM64、Windows x86_64、Linux x86_64 | Intel Mac、Linux ARM64、Windows ARM 不是原生支持目标；本 Skill 不因此新增 Linux 执行能力 |
| 独立浏览器资料 | 每个本地身份绑定自己的 user-data-dir，内部使用 Default | 与普通 Chrome／Edge 的资料不同；隔离本地目录不等于消除服务器关联 |
| 默认浏览器 | 注册 HTTP／HTTPS 关联并读取状态，Windows 转系统默认应用界面 | 会改变普通链接的打开位置；不强改 Windows UserChoice |
| 安装与更新 | 项目有分平台安装包和更新流程 | Windows 安装器未做 Authenticode 签名；不要把绕过系统安全提示写成默认安装步骤。A、B 升级范围按当前包核对 |

实现入口：[应用启动](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/main.rs#L96)、[引擎获取](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/scripts/fetch-browser.py#L17)、[平台与发行说明](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/README.md)。

## 二、浏览器指纹、代理与清理

| 功能／参数 | 已确认机制 | 尚不能推出的结论／连带影响 |
| --- | --- | --- |
| seed | 非零 32 位种子，初始值来自本地身份 ID，快捷轮换生成新值 | 不是服务端身份重置，也不来自 Anthropic 账号 UUID |
| OS／平台版本／CPU | 使用真实机器值 | 不能宣传为任意伪造整套设备 |
| 浏览器品牌／版本 | Chrome 品牌、实际引擎版本 | 版本字符串一致不证明安全补丁覆盖 |
| Canvas／ClientRects | 默认 native_graphics 保留真实输出；快捷换指纹关闭此选项，使 seed 作用于这两类输出 | 对网站识别及账号接受效果未验证；持续轮换也可能破坏会话一致性 |
| 字体／Audio／GPU | 该版本始终关闭这三类 spoofing | 不应列为“已随机化字体、音频和显卡” |
| 语言 | 可跟随机器或指定：en-US/en-CA/en-GB/en-SG/en-AU/en、简繁中文、法／德／西／意／日／韩 | 修改网页首选语言不等于修改系统语言，也不能证明真实地区 |
| 时区 | 可跟随机器或指定，通过 --timezone 启动参数传入；资料偏好另处理语言等 | 目标城市、DST 与本机状态仍需分别核对；不靠拨动系统时钟实现 |
| 显式代理 | HTTP／HTTPS／SOCKS5／SOCKS5H 主机与显式端口，拒绝 URL 内认证、路径及查询参数 | 认证代理需外部客户端处理；空白表示依赖系统／TUN，不代表已接管 |
| 快捷指纹轮换 | 重建 seed、应用所选地区语言／时区、清空显式代理并重启 B | 可能改变现有路由并丢失未提交工作，不是单独无损换 seed |
| SOCKS DNS／回环 | 有 DNS resolver 限制及回环豁免 | 不证明系统、DoH 或其他程序的解析路径 |
| WebRTC／QUIC | 限制 non-proxied UDP，关闭 QUIC，设置相关资料偏好 | 没有独立 WebRTC 泄漏验收；也不证明故障时全机不直连 |
| 浏览器定位 | 默认拒绝相关定位并清除该资料已有定位例外 | 影响该资料所有网站；不改变 IP 地理位置 |
| 仅清缓存 | 清独立资料资源／代码／图形／Service Worker 缓存及崩溃报告，保留登录与个人数据 | 直接删除、无自动备份；范围仅该配套浏览器 |
| 扩大清站点数据 | 后端可清 Cookie、Local／Session Storage、IndexedDB、Service Worker、WebStorage、Sessions、Trust Tokens、DIPS 等 | 作用于当前独立资料的这些类别，不是普通 Chrome 的 Claude 单站点操作；不要猜造 UI 中未暴露的入口 |
| 清空全部浏览器数据 | 删除当前身份资料的所有内容，包含密码、加密元数据、书签、历史、扩展、设置和内部其他 profiles | 永久删除、无备份；其他身份资料及身份保险库保留，不代表本次可恢复 |
| 环境体检 | 比较出口国家、时区、语言、地区、OS、CPU、引擎和定位，检查结果是否回传 | 不测账号状态、Canvas 有效性，也不独立验证 DNS／WebRTC |
| 出口检测 | 请求 ipwho.is，必要时同路由回退 ipapi.co | 会向第三方传出出口地址等请求信息；地理定位只是估计，不能证明住宅独享／真实物理位置 |

源码：[配置及启动参数](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/browser/config.rs#L111)、[资料写入与清理](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/browser/profile.rs#L81)、[重置与快捷操作](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/browser/mod.rs#L538)、[实际测量判据](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src/browser-verification.ts#L10)。

普通浏览器仍按 [单站点流程](browser-cleanup.md) 处理；不能把 B 的整资料清理方法套到用户主浏览器。

## 三、系统地区与权限

| 方法 | CCBaga 实际做法 | 本 Skill 如何使用 |
| --- | --- | --- |
| 地区预设 | 13 个选择：美国东西岸、加拿大、英国、法国、德国、日本、韩国、新加坡、台湾、香港、中国大陆、澳大利亚；联动语言、地区格式与时区 | 全部列作选项，不直接应用；选地区不会更改公网 IP |
| 系统时区 | Mac 关闭自动时区后设置；Windows 将 IANA 转为系统 ID；Linux 用 timedatectl | 保留原值及自动选项，区别 NTP 校时；部分失败可能已写入，先读回 |
| 系统语言／地区格式 | Mac 改 AppleLanguages／AppleLocale；Windows 改用户语言、UI override、culture／地区 | 我方默认保留系统语言、键盘和输入法；只有明确选择该方案才改，不能从“参考 CCBaga”推定授权 |
| Linux 语言／定位 | 语言要求用户在桌面设置修改及重新登录；定位针对 GNOME | 非 GNOME 未知不能当作关闭，不能把 Mac 命令当跨平台实现 |
| 系统定位 | Mac 打开设置并可能依赖 Accessibility 控制；Windows 打开隐私设置 | 影响整机业务，所需权限单列；浏览器拒绝定位不等于整机定位关闭 |
| 按实际出口对齐机器 | 当前代码仅接受美国出口，设置 en-US／en_US、出口时区、关闭系统定位、浏览器跟随机器 | 这是组合变更，不是检查按钮；非美国不能声称已支持；与保留语言默认冲突时作为另选方案 |

来源：[系统设置实现](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/system.rs#L98)、[美国出口对齐路径](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/browser/mod.rs#L658)。这些机制可核对，改变封禁概率的因果效果未核实。

## 四、身份归档、迁移、进程与程序维护

| 功能 | 已确认做法 | 影响与边界 |
| --- | --- | --- |
| 原地保存／更新归档 | 保存选定当前状态，保留当前登录、工作区及浏览器绑定 | 归档可能包含敏感登录材料，不是单纯配置备份 |
| 切换／空白身份 | 归档并验证退出的身份，再清理或恢复工作区；SQLite 记录恢复状态，失败回滚并支持中断恢复 | 属于本地状态切换，不是修改服务端账号身份；失效认证仍要重登 |
| 保留策略 | Skills/commands、插件、MCP、个人设置、项目记录、历史、缓存／日志可分类；默认前五类留工作区，历史／缓存随身份走 | 登录数据随身份归档，源码外的项目不会扫描；保留类别应以当前确认页再核对 |
| 保险库 | tar/Zstd、AES-256-GCM、本机随机密钥、HMAC 账号索引与私有权限 | 同用户／管理员不是绝对隔离边界；我方不将秘密导出进对话 |
| Mac 认证 | 识别默认 Claude Code-credentials、Claude Code、Claude Safe Storage，并按策略处理 MCP／插件秘密 | 会触及认证与解密密钥；自定义配置根派生项目不自动覆盖 |
| 直接删除当前身份 | 不创建归档，删除所选当前数据 | 永久删除，不能套用“切换前先备份”的保证 |
| 删除保存身份 | 删除该归档，浏览器资料另有选项 | 不等于服务端撤销会话，也不证明其他副本已删除 |
| 同 OS 跨机导出／导入 | 密码保护的 .bagapack，PBKDF2／AES-GCM；导入新增卡片，不直接切换／启动 | 身份包可能含获准归档的 Claude 登录材料和 Mac 默认 Safe Storage 项；可选浏览器部分只带指纹设置，不携带浏览器 Cookie、密码、会话、代理或 OS 保护密钥；跨机仍可能需重登 |
| 默认目录限制 | 管理默认本地数据路径，提示自定义 CLAUDE_CONFIG_DIR 未纳入 | 不能声称所有配置根／Console profiles 都已切换或清除 |
| 停止 Claude | 身份操作识别目标进程；POSIX 先 SIGTERM，短暂等待后可能 SIGKILL | 可能中断未保存任务，不能称仅正常退出；保护 Codex／远控和其他项目进程 |
| CLI 卸载／重装 | 识别 native、npm/bun、Homebrew、WinGet，处理程序并检查版本，拒绝未知自定义启动器 | 与删除身份保险库／用户配置分开；下载安装须在网络前置条件满足后 |

证据：[身份存储与迁移](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/docs/identity-storage.md#L73)、[Mac 认证桥](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/native/Identity.m#L14)、[进程处理](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/cleaner.rs#L651)、[CLI 管理](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/claude_cli.rs#L188)。

## 五、文件清理完整对象分类

下列是该版本源码中的候选范围，**不是我方默认删除清单**。实际需先确认平台、版本、数据归属和用户选择。residue 入口先扫描、绑定一次性选择与元数据；应用运行时拒绝处理，不主动停进程；选中后永久删除，不新增备份。此路径不访问 Keychain，也不处理 B 的资料或保险库。

| 类别 | 源码涉及对象 | 不能混淆 |
| --- | --- | --- |
| Code 缓存／状态 | cache、stats-cache、telemetry、usage-data／usage JSONL、paste-cache、statsig、todos、ide、daemon 日志／状态、downloads、清理／更新标记及可确认的再生锁文件 | 名称在清单中不证明目标版本可无损删除；锁文件不能在写入者活动时删除 |
| 历史／工作材料 | projects、sessions、history.jsonl、file-history、debug、plans、image-cache、uploads、session-env、tasks、shell-snapshots、feedback-bundles、feedback/drafts、dev-mods、jobs | 包含附件、工具结果、文件快照及任务材料，不能称纯缓存 |
| CLI 账号／本地 ID | 凭据文件中的 claudeAiOauth／trustedDeviceToken；账号 JSON 白名单中的身份／API key／引导及功能缓存；.user-id、.machine-id 等 | 当前入口保留共享 MCP／插件秘密；ID 文件清除不等于服务端设备注销或硬件身份更换 |
| Desktop 状态 | 账号缓存、ant-did／registry、Local／Session Storage、IndexedDB、Cookie、Service Worker、Storage、DIPS、Trust Tokens 等 | 可能丢登录及持久状态；不同于官方 Reset App Data，后者还需核对云端影响 |
| 历史配置备份 | 默认 .claude/backups 与根配置的滚动备份 | 可能删除唯一恢复证据；不因要清当前状态顺带清备份 |
| 当前入口排除 | Shell 配置、共享 npm／Git 代理、Skills／插件、整份 ClaudeBackups、保险库与浏览器资料 | 旧底层目标定义存在不代表当前 UI 能执行，不把不可达旧代码宣传为功能 |

实现：[残留扫描](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/cleaner_residue.rs#L36)、[删除事务](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/cleaner_transaction.rs#L17)、[目标定义与过滤](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/cleaner_targets.rs#L150)。我方实际清理仍按 [准备与恢复](incident-and-cleanup.md#清理准备与恢复) 先形成具体方案，不直接执行这张源码目录表。

## 六、网络与 VPS 可选路线

| 能力 | 实际做法 | 需要单列的影响／未验证部分 |
| --- | --- | --- |
| 应用网络入口 | 供应商链接、工具选择和安装独立 ccbaga-network 的提示 | A 本身不部署服务器；供应商链接带推广参数，不是技术必需或推荐依据 |
| 前提 | Debian 12/13、root 密钥登录、SSH 22；Python／OpenSSH／curl；PEM／PPK／PUB 一致性与主机指纹检查 | 三份文件是同一密钥的不同表示，不是三因素认证；私密文件本地处理，不粘贴凭据进对话 |
| Windows 支持 | 原生 OpenSSH 与用户私有 NTFS ACL | 不必为了此路线安装 WSL；公司策略／目标权限仍待现场核对 |
| 系统变更 | full-upgrade、软件包、BBR/fq/sysctl、SSH key-only、fail2ban、自动更新、ufw 22/443/8443 | 可能影响已有业务和 SSH；不是原子回滚，需具体服务器方案与独立恢复条件 |
| 供应链 | 下载 XTLS main 安装脚本，默认 Xray latest | 固定 CCBaga 提交不等于固定全部远程依赖；需审查当时来源，不能直接执行漂移脚本 |
| 连接路径 | 客户端 → Reality/VLESS TCP443 → VPS → 认证住宅 SOCKS5 | 服务端限制 UDP／私网／BT，TCP 无 direct fallback；这不是客户设备全机 fail-closed 证明 |
| 路由细节 | 客户端列明国内／bootstrap DNS 可直连；AI/default 组用 node 或 REJECT | 不是所有流量同一出口；wrapper 禁用旧脚本的 Stripe 直连例外，不绕过 wrapper 套底层默认 |
| DNS／TUN | Mihomo fake-IP／IPv4，TUN ON、System Proxy OFF、B 显式代理为空 | 属于替代配置路线，不能盲目叠加我方现有策略；any:53 不证明 TCP53／DoH 全接管 |
| 订阅交付 | 可经 SSH 取私有本地 YAML；另有 HTTP 8443 随机 token 路径 | token 不是 TLS；优先 SSH 取文件，不公开订阅 URL／receipt |
| 服务端自检 | 服务／配置、fail2ban、BBR、订阅及临时 VLESS 客户端出口检查 | 不代替真实客户 TUN、浏览器、DNS／WebRTC、断网恢复验收 |
| 本地 tun-check | 忽略代理环境变量核对固定出口 | 终端探针不代表所有进程，正常连接也不证明故障保护 |
| 官方域名探针 | 对 Claude 网页、API、Console、下载域名作固定 HTTPS 检查 | 无账号凭据；HTTP／挑战响应不能证明登录、模型可用或分流正确 |

源码：[网络 Skill](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/skills/ccbaga-network/SKILL.md#L77)、[VPS 部署脚本](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/skills/ccbaga-network/scripts/setup-vps.sh#L135)、[域名探针](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/src/network_links.rs)。

## 七、方案分类与未验证效果

CCBaga 的安装、指纹／地区联动、身份迁移、清理和 VPS 部署均属于本 Skill 的**可选工具路线**；上文保留具体源码能力、参数与副作用。完整方案的默认选择、历史待验项和错误解释统一在 [完整方法分类](complete-environment-method.md) 维护，避免多处重复后状态不一致。

- [默认方案](complete-environment-method.md#默认方案)：保留原语言、时区目标、节点和业务；不会因参考 CCBaga 自动改成其组合预设。
- [可选方案](complete-environment-method.md#可选方案)：按用途选择上述能力，具体对象和副作用纳入方案。
- [未经验证的做法与效果](complete-environment-method.md#未经验证的做法与效果)：包括指纹／语言／住宅出口／本地 ID 的账号因果、fork 安全补丁、跨机登录、自定义配置根、真实 VPS／TUN／DNS／WebRTC／故障路径，以及此前其他来源的养号、邮箱、设备和并发说法。
- [已纠正的说法](complete-environment-method.md#已纠正的说法)：包括“选国家就换 IP”“全指纹随机化”“所有清理先备份”“时区写入 Preferences”“HTTP token 等于加密”等，不能重新标为可能有效的默认或可选方案。

已读取的 [上游交付记录](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/docs/release-verification-0.2.50.json#L192) 和 [安全范围说明](https://github.com/liseami/CCBaga/blob/6db5ad55e799c5b020be8ff5e4def2c147cd5602/src-tauri/SECURITY.md#L62) 只标“上游记录／本轮未复跑”。源码实现不等于目标机实测，未证效果不隐藏，也不包装成承诺。

## 纳入本 Skill 的方式

- **直接吸收方法**：范围分类、身份与浏览器资料区分、动作前展示连带影响、实际参数与测量分开、备份校验和部分失败记录。
- **列为独立可选路线**：安装 A/B、身份归档／跨机迁移、地区联动、指纹轮换、VPS 部署。选择后才形成具体方案，不覆盖现有系统语言、时区及网络偏好。
- **保留为待验证选项**：上表所有未检验做法，列来源、目的、影响、恢复限制与证据缺口；用户只要求列出时不执行，不以清理／改标识代替账号官方处理。
- 本轮只维护上述方法与引用。未来执行需重新核对所用版本、目标与实际授权，不把来源里的 CONFIRM、示例参数或测试通过字段当用户批准。
