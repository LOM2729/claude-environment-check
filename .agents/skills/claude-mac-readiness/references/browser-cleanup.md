# 浏览器：按站点和资料清理

需要还原作者整套清理时，另读 [Guardian 浏览器/痕迹链](source-methods-guardian-account-cleanup.md)与 [CCBaga/清理来源方法](source-methods-ccbaga-cleanup.md)。单站点、整 Profile、扩展/Native Messaging、PWA 与共享身份分别列出；仅记录作者工具/路径，不自动在目标机逐个清理。

用于明确的浏览器清理、网页登录循环、页面状态损坏；先按 [故障分流](incident-and-cleanup.md) 判断是否确实涉及本地状态。仅审查或优化 Skill 时，不读取真实浏览器数据、不打开诊断页面、不运行清理。2026-11-06 核对下列官方资料；菜单名称、数据分类和分区行为以目标版本为准。

## 先确定对象与最小动作

记录目标设备、浏览器、实际使用的资料（Profile）、站点和原故障。Chrome／Edge／Brave／Arc 的资料不能互相代证；Safari／Firefox 使用各自入口。网页、PWA、扩展和 Claude Desktop 的数据归属分别确认，不能凭外观相同认为共用登录态。

| 目标或现象 | 首选处理 | 影响与边界 |
| --- | --- | --- |
| 页面显示或资源加载异常 | 普通刷新；确需绕过资源缓存时再选强制刷新 | 强制刷新不等于清除登录、IndexedDB 或 Service Worker |
| 怀疑扩展或现有资料干扰 | 按需暂禁相关扩展，或使用独立临时资料作对照，记录原状态 | 不自动同步主账号或导入密码。无痕的 Cookie／扩展策略可能不同，对照成功只说明差异，不能证明唯一原因 |
| 清理 Claude 登录／站点状态 | 在指定资料中按具体站点清除已选数据 | 会退出相关网站并可能丢未提交草稿、离线数据；不勾选全部网站、密码、历史或自动填充 |
| 特定持久状态或离线缓存损坏 | 在开发者工具按 origin 检查 IndexedDB、Local／Session Storage、Cache Storage 和 Service Worker | 只处理有依据的类别；清 Cookie 不证明这些对象都已清除 |
| 扩展集成或 PWA 残留 | 分别检查扩展权限／存储、Native Messaging 归属和 PWA 的实际资料 | 清站点数据不等于卸载扩展；卸载集成须有对应范围 |
| 整个资料损坏或设备交接 | 另行列出完整资料重置的具体损失、导出和恢复条件 | 不作为单站点排障的自动下一步 |

对照若要新开／重启浏览器或访问 Claude，沿用 [生命周期前置条件](lifecycle-checks.md)，可复用仍有效的网络证据；离线查看已授权的资料设置不需要重配整机。确认当前浏览器是否承载 Codex／远控，不能为了清理把控制通道关掉。

## 按浏览器选择受支持入口

优先使用浏览器自己的站点数据设置。下列为定位线索；执行前核对目标版本界面，不依赖固定坐标或猜测内部数据库结构。

| 浏览器 | 单站点入口 | 必须区分 |
| --- | --- | --- |
| Chrome | 设置 → 隐私和安全 → 第三方 Cookie → 查看所有网站数据和权限 → 搜索目标站点 | “清除浏览数据”的缓存、历史、密码与站点数据是不同类别；不要全选 |
| Edge | 设置 → 隐私、搜索和服务 → Cookie → 查看所有 Cookie 和站点数据 → 搜索目标站点 | Cookie／站点数据与同步的历史、密码、自动填充分别处理 |
| Safari（macOS） | 设置 → 隐私 → 管理网站数据 → 选择站点 → 移除 | 不用“清除历史”替代；网站数据可能被其他 App 使用，iCloud 历史另有跨设备影响 |
| Firefox | 设置 → 隐私与安全 → Cookie 和网站数据 → 管理数据 → 选择站点 → 保存更改 | “忘记此站点”比清站点数据范围更大，不把二者当同一个动作 |

常见起点是 `claude.ai`、`claude.com`、`anthropic.com`，实际只处理已确认相关的 origin／域名及子域；不能用字符串包含 `claude` 匹配任意网站、书签或扩展。Persona、Cloudflare、hCaptcha 等第三方服务可能被多个网站共用：必须核对顶层站点／存储分区；无法限定到 Claude 时保留并说明缺口。

高级排障可在 Chromium 开发者工具 Application → Storage 中选择数据类型；查看 Service Workers、Cache Storage、IndexedDB 等实际对象。明确是否包含第三方 Cookie，不通过“Clear site data”按钮名称推断它只影响缓存。站点权限、扩展权限另列，不顺带重置。

## 执行、复核与恢复

1. 保存未提交草稿或必要本地成果；列清浏览器、资料、站点／分区、数据类型、会退出哪些登录和保留项。按 [确认方式](change-confirmation.md) 复用已有明确授权；不可恢复删除遵守实际使用工具的动作时确认要求。
2. 根据操作入口关闭会回写目标数据的相关标签、PWA 或后台任务。需要退出整个浏览器时说明影响，保护控制通道；不要无差别杀浏览器进程。
3. 优先由原生设置执行定向删除。其效果可能不可撤销，不能承诺恢复 Cookie 后账号会话仍有效。浏览器同步的历史／密码等不能因本机清理而跨设备删除。
4. 默认不直接编辑浏览器数据库。专项数据库处理另核对版本、数据库一致性与停写条件：SQLite 只读检查使用受支持方式，备份须考虑 WAL／SHM；锁冲突就停止该项，不能删除锁文件或用强制只读绕过一致性问题。LevelDB 不得按文本命中后删除整库。禁止整删 Cookies、Local Storage、Session Storage、QuotaManager 或 Service Worker 根目录。
5. 先复核指定对象与保留范围，再按批准范围重新打开目标站点，验证原失败操作。站点重新生成 Cookie／缓存是正常现象；“目录仍存在”不代表失败，“删完了”也不代表故障修复。故障未变则回到分流，不自动扩大删除或反复清理。
6. 只有明确适用于当前版本且具备一致性备份时才尝试恢复；先保护清理后新增的数据，不能把整份旧资料覆盖回去。浏览器／系统加密、会话过期和服务端撤销都可能使备份不能恢复登录。备份可能含登录材料，仅保存在用户私有位置，后续保留或销毁另按用户范围处理。

## 官方资料与来源边界

- [Chrome 按站点清理](https://support.google.com/chrome/answer/95647)、[数据分类与同步](https://support.google.com/chrome/answer/2392709)、[开发者工具 Application](https://developer.chrome.com/docs/devtools/application)、[Cache Storage](https://developer.chrome.com/docs/devtools/storage/cache)。
- [Edge Cookie 管理](https://support.microsoft.com/en-us/edge/manage-cookies-in-microsoft-edge-view-allow-block-delete-and-use)、[浏览数据范围](https://support.microsoft.com/en-us/edge/view-and-delete-browser-history-in-microsoft-edge)。
- [Safari 网站数据](https://support.apple.com/en-gb/guide/safari/sfri11471/mac)、[Firefox Cookie 与站点数据](https://support.mozilla.org/en-US/kb/clear-cookies-and-site-data-firefox)。

社区清理清单仅提供对象线索，不能证明目标版本的数据归属或防封效果。源码核对与采用范围见 [清理资料核对](evidence-sources.md#清理资料核对2026-11-06)。
