# 可选执行工具

只在本轮需要对应功能时读本页，普通配置仍按 [五步流程](five-step-setup.md)。先用 `python <Skill>/scripts/claude_setup.py capabilities` 核对当前随包命令；声明能力、隔离测试与目标机验收分别记录。Codex准备输入和具体方案，客户不填写JSON或选择技术参数。

## 支持范围

| 模块 | 命令 | 当前范围 |
| --- | --- | --- |
| 程序化访谈 | `intake-start / intake-answer / intake-assess` | 纯离线任务分流；保存事实、冲突和下一缺口，不恢复授权或执行操作 |
| 浏览器WebRTC | `webrtc-plan / webrtc-serve / webrtc-report` | 在用户实际Profile中采集ICE；本机随机URL、页面点击后才发指定STUN请求 |
| Skill更新核对 | `skill-update-check` | 只比较本平台Skill与固定GitHub提交，列出差异，不自动覆盖 |
| Claude数据隔离 | `cleanup-inventory / cleanup-plan / cleanup-quarantine / cleanup-reconcile / cleanup-restore` | macOS 限定根及 Windows 本机固定 NTFS 卷上的限定根 |
| 原生规则适配 | `native-client-plan / native-client-apply / native-client-check / native-client-rollback` | macOS 上 Clash Verge Rev 2.5.8、2.5.10 的专属 rules 扩展 |
| 系统防护开关 | `guard-plan / guard-export / guard-inspect / guard-on / guard-confirm / guard-off / guard-status / guard-uninstall / guard-launch` | Mac PF、Windows原生防火墙、Linux nft；精确拥有范围和独立恢复，不默认启用 |
| VM／VPS部署维护 | `remote-plan / remote-export / remote-apply / remote-confirm / remote-rollback / remote-status` | Debian／Ubuntu systemd目标：TUN、SSH／反向隧道、自愈与防火墙；在实际Linux目标执行，不从本机隐式SSH |

当前维护入口为本 Skill 的 `scripts/claude_setup.py`。Codex 复用已有目标、范围和材料，准备计划、差异、备份、准确参数及恢复说明，按获准范围调用对应工具。普通浏览器清理和系统设置使用各自受支持的原生入口。真实设备、浏览器、管理员操作和重启恢复按实际结果记录。

工具的支持类型与完整方法范围不同。下列清理、规则和防护命令按其当前平台边界调用；浏览器自动数据库清理、Keychain 字段恢复、完整身份保险库／加密迁移等仍属于方法或未实现能力，不能通过写文档将其标为工具已实现。

Mac／Linux系统防护的独立恢复worker另需已核实可运行、root-owned的Python3.9+；Windows恢复使用系统PowerShell。Skill脚本运行时与提权后独立恢复运行时分别核实。缺依赖先准备具体安装／恢复方案，不自动安装开发工具、不改系统Python或绕过执行策略。

## 访谈只追当前缺口

普通小任务直接按上下文做，不强制创建状态文件。问题跨轮、多人交接或确需记录时才使用程序化访谈：`intake-start --task <任务> --output <新私有状态>`，随后根据当前已有信息准备 `--answers` 批量提交；`intake-answer`输出新的状态文件，不覆盖上一版。`intake-assess --state <当前状态>`只选择相关下一问和资料，不接触设备。

任务为 `setup / diagnose / cleanup / compare / maintenance / hardening / remote / billing / subscribe`。输入只接收规定枚举和非识别性目标别名，不存自由文本、命令、URL、凭据或完整配置。批量答案的形式如下，字段和值按真实上下文填写：

```json
[
  {"field":"platform","state":"known","value":"macos","source":"user"},
  {"field":"client","state":"known","value":"browser","source":"user"},
  {"field":"cleanup_category","state":"known","value":"cache","source":"user"},
  {"field":"cleanup_scope","state":"known","value":"profile","source":"user"}
]
```

未知、拒答或暂缓保留状态，不反复自动追问，也不视为接受。新旧已知事实不一致先形成冲突；当前变化已明确时才用 `--accept-changes`接纳事实变化，它不批准动作。路线／设备改变会使相关绑定、计划和网络证据需要重核，未涉及的事实继续保留。`ready_for_plan`仅表示可准备方案。中断后由 Codex 读取上次事实文件，使用同一 `intake-assess --state` 选择当前缺口，再以 `intake-answer --state --answers --output` 保存新版本；较完整的执行上下文同时按 [私有进度](workflow-progress.md) 绑定，复用已知事实。

## WebRTC只说明当前浏览器样本

1. `webrtc-plan`指定实际配置、目标／Profile别名、平台、准确 `stun:hostname:port` 和时间预算；计划不联网。
2. 网络前置条件与检测范围已批准后，`webrtc-serve --allow-network`启动仅绑定127.0.0.1的临时服务，把随机URL写入新的私有 `--session-output` 文件，不自动打开浏览器。
3. 在实际使用的现有Profile中打开该URL，核对STUN目的地，按需在页内输入本轮已核实的HTTPS出口IPv4，然后点击开始；不索取摄像头或麦克风权限。
4. 页内分别统计host／mDNS、srflx IPv4／IPv6及relay等，参考IP只留浏览器内存；导出不含原候选或原IP。超时、无候选、ICE错误或截断保持未完成，相同IPv4只说明样本相同。
5. 取消、pagehide、到期或本地服务心跳失效会关闭PeerConnection；服务退出到页面发现之间存在短窗口，不能承诺瞬时远程终止。结束后关闭专属页，私有session文件不公开。

`webrtc-report`可校验导出的脱敏观察与原计划／配置，导入材料仍注明未独立核实。这个工具不证明Desktop、其他Profile、实际媒体选择路径或整机故障保护。

## 更新先比较，安装另做具体方案

`skill-update-check --skill-root <明确Skill目录> --platform mac|windows --allow-network --output <新私有报告>`只访问本仓库固定GitHub API，先固定commit／tree再逐文件比较；可选 `--snapshot-output`保存固定快照。没有网络或请求失败不能报告已是最新。

已有快照使用 `--snapshot`离线比较，不声称查到了最新main。报告区分changed、upstream-only和local-only；本地二开先保留，更新前另列精确差异和目录外备份，不自动删除本地独有文件。文件哈希匹配不认证Release安装包。

## 数据清理与原生规则

数据隔离默认只选明确可再生缓存。按 [客户端分项清理](client-cleanup.md#分项方案与当前执行范围) 记录缓存、登录、历史、配置各自的本轮选择，再将受支持对象写入 `cleanup-plan` 请求，非缓存类别通过对应 `--allow-category` 显式纳入。只列指定配置根／Desktop根。计划在备份之前核容量、数量、深度、同卷与保护范围，独立备份、隔离材料和恢复说明留在私有任务目录。

提交时绑定已审阅计划摘要、当前目标与停写前提；进程观察只是防意外措施，不能强制阻止Node／未知写入者。部分失败先用 `cleanup-reconcile`对账，恢复只处理原位空缺且隔离材料未变的项目，不覆盖新数据；具体参数读对应命令 `--help`，不猜造字段。

Windows 原生范围为用户资料内的有效 `CLAUDE_CONFIG_DIR`（默认 `~/.claude`）及当前用户的 `%APPDATA%\Claude`。原目录与私有备份须在同一固定 NTFS 卷。重定向至资料外的目录、MSIX 私有数据、重解析点、硬链接、备用数据流和不支持的权限布局需要单独核对。

Clash 原生适配先核已安装版本、活动 profile、独占 rules 扩展、基础配置和当前字节，保留注释和未知内容。退出 GUI 后通过精确文本事务备份、写入和回滚。`written_but_not_verified` 记录文件层结果，重新打开后按原五步核对客户端载入及实际路由。2.5.10 的字段与规则合并顺序已对照上游固定提交，目标设备仍待验收。 [上游规则加载源码](https://github.com/clash-verge-rev/clash-verge-rev/blob/c83f7ad529c7c9cb3d2d54a0955ef8c1b22a411b/src-tauri/src/enhance/mod.rs#L167-L214)

### Codex准备的清理／规则请求

实际路径由目标机已授权的精确上下文提供；下列占位值不直接执行，先核有效配置根与保护范围：

```json
{"schema":"claude-cleanup-scope/1","target_alias":"device-1","config_root":"<有效配置根绝对路径>","desktop_root":null,"roots":[{"kind":"cli-cache","path":"<同一根>/cache"}],"protected":[]}
```

`cleanup-plan --request <私有请求> --out <新计划目录>` 返回计划摘要；`cleanup-quarantine`绑定该目录和摘要，再加实际成立的 `--allow-write --writers-stopped`。失败后使用返回的操作目录／摘要创建 `cleanup-reconcile`观察，再用新的观察摘要恢复，不能把计划摘要、操作摘要和观察摘要混用。

原生规则请求只接受当前基础配置中真实存在的策略组／节点或REJECT：

```json
{"schema":"clearpath-native-rules/1","target_alias":"device-1","rules":["DOMAIN,example.com,ExistingGroup"]}
```

`native-client-plan --request <私有请求> --out <新计划目录>`准备精确字节候选；apply绑定计划目录／摘要和已成立的 `--allow-write --writer-stopped`，check／rollback另绑定同一计划产生的操作回执与摘要。写入结果不明时先保留原计划和操作目录，按 [回执核对](recovery-and-acceptance.md#原生规则写入结果不明时) 选择检查入口，再决定是否恢复。具体当前参数以命令 `--help`为准。

## 系统防护和远端部署

先准备精确节点IPv4／端口、物理／TUN接口、DNS引导及必保业务例外和独立救援。当前系统防护支持 `unified-v4 / explicit-exceptions`，Linux入站加固用 `inbound-management`；不支持把完整域名／GeoIP国内分流自动编译成系统层 `domestic-v4`，遇到该组合明确拒绝，不能自动换策略。普通 `domestic-v4` 配置保持原流程；需要系统防护时另列一份可实施且获准的精确方案。已有连接、第三方规则及未覆盖接口的边界分别说明。

计划／导出默认离线；真正变更要求精确计划摘要、`--allow-system-change`、`--control-channel-independent`及`--recovery-ready`，这些标志由Codex按本轮具体授权和现场事实填写，不能让保存文件替用户授权。影响当前Codex／远控的操作交客户在独立终端执行。

正常 `guard-off`／`guard-uninstall` 前，先读取当前状态和本轮例外，保存受保护任务，确认浏览器、Claude 与相关后台已按实际归属安全退出。核对 OFF 会恢复的出站行为，再用当前计划／状态目录执行并读回规则与开机状态。紧急恢复沿用独立救援入口，不等待普通停用清单。

先建立并核实独立限时恢复，再应用并读回；确认文件只记录现场观察，不认证其真实性。Mac／Linux确认后才新增开机加载；Windows原生防火墙修改本身持久，须先建立SYSTEM限时及开机恢复任务，待确认时明确标记，确认后才撤恢复任务。恢复分别核运行规则和开机／定时状态，保护后来新增的规则。

远端TUN安装使用本轮明确可信来源与SHA256，先下载校验再替换；校验不认证发布者，版本／架构和来源另行核对。v1配置采用明确的JSON格式Mihomo配置，须包含选定的TUN名称与专属路由表；现有YAML先经本包解析器准备私有JSON候选，保留原件。配置、密钥和known_hosts由用户准备，不自动登录AI。

SSH模块只支持已核标准 `ssh.service`、默认配置来源和空SSHD_OPTS；active或enabled的 `ssh.socket`、自定义启动／unit覆盖明确拒绝。必须显式设置 `ssh.activation="restart"`，计划写明采用当前已核unit/default配置；客户在独立终端执行，先具备第二会话／带外控制台，不能把HUP静默换成restart。会做语法及有效配置／端口核对，但恢复只承诺本次保存的文件和服务状态，不承诺旧daemon未落盘的-f/-o参数或旧SSH可达性。该模式的 `runtime_restored=false` 不可改成已完整恢复。

SSH drop-in及原本已启用的服务本身具有持久性，计划会标 `requires_persist`；确认前先布置限时及开机恢复，最终确认须显式 `--persist`。反向隧道严格known_hosts、固定密钥、禁用隐含SSH配置与agent，仅请求回环监听；实际中转端GatewayPorts和绑定仍需现场验证。入站加固不冒充出站防直连，自愈只处理本包拥有的服务／残留，不宽范围杀进程或重置整机网络。

### 双击入口与手动交接

系统防护方案已具体审阅后，在实际目标设备使用 `guard-export --plan <计划> --plan-sha256 <返回摘要> --out <新私有目录>`；可选 `--check-plan <已批准bootstrap检查计划>`，导出不联网、不启动终端、不提权。Mac生成 `启用断线保护.command`，Windows生成 `启用断线保护.cmd`和明确UAC包装，Linux生成 `.sh`，并附离线恢复说明。其他平台离线导出的包不生成假可用入口，须在实际目标重新导出。

把准确入口、要做什么、会影响什么、保险丝时限和恢复说明交给客户；客户自己双击、处理sudo／UAC并在可见终端输入APPLY。助手不控制终端、代输确认词或索取密码；入口／runtime／计划改动后重新导出，不手改manifest跳过校验。

只提供检查计划时才自动运行其准确端点，且仅允许bootstrap非AI目标；没有计划就明确要求客户自行检查，不宣称“三项都绿”。检查预算和剩余窗口不够、任何项失败或CONFIRM超时都不确认；只精确撤销本次新pending代际，不撤已有confirmed保护或另一轮改动，未知状态先对账。控制器显示本次实际剩余确认时间，不用经过时长代替恢复读回。

正常使用及独立管理通道都经客户现场核实后，才输入CONFIRM并提交持久化。失败只展示简短阶段／原因／下一步，详细日志留私有目录；超时或已撤销始终保持未完成，不把“好了”当通过，不为修复自动换节点／改DNS。系统状态、限定探针和整机网络效果仍分别记录。

### 系统／远端计划的格式入口

以下仅展示计划格式，文档保留地址不能用于实际部署；Codex从真实已授权目标填写节点／接口／管理来源，客户不编辑JSON：

```json
{"schema":"clearpath-guard-input/1","scope":"example","platform":"macos","policy":"unified-v4","interfaces":["en0"],"tunnels":["utun8"],"nodes":[{"address":"192.0.2.10","ports":[443],"protocol":"tcp"}],"exceptions":[],"bootstrap_dns":[],"fuse_seconds":180,"trusted_python":"/usr/bin/python3"}
```

`guard-plan --input <私有请求> --output <新计划>` 返回规范化计划摘要，后续直接使用返回值，不以随意重排JSON后的文件哈希替代。Windows计划还需已核真实核心路径；先用 `guard-inspect`形成私有原生快照，完整核对 PersistentStore、ActiveStore 的三档默认策略、同名规则数量、启用状态及全部条件。程序／包／服务、接口、地址、协议、端口和安全条件逐项审阅，当前工具未取得的字段保留未完成，未知有效策略不直接写入。

```json
{"schema":"clearpath-remote-input/1","scope":"example","platform":"linux","distribution":"ubuntu","modules":["inbound_guard"],"fuse_seconds":180,"trusted_python":"/usr/bin/python3","inbound_guard":{"management_networks":["198.51.100.0/24"],"tcp_ports":[22]}}
```

`remote-plan --input <私有请求> --output <新计划>` 后用返回的计划SHA进行 `remote-export`；目标机apply绑定导出返回的bundle摘要，两者不可混用。计划与导出不SSH、不读取目标设备，实际运行只在声明匹配的Linux目标。SSH的请求对象还包括 `activation / port / password_authentication / permit_root_login / allow_users`，存在Match／额外Include时再准备覆盖允许用户的 `validation_contexts`。

guard现场验证文件使用 `schema=clearpath-guard-verification/1`、精确 `plan_sha256`、`normal_path="observed"`、`management_path="observed"`；remote使用 `schema=clearpath-remote-verification/1`，涉及SSH／入站时再要求 `second_session="observed"`。这些字段只记录实际观察，不鉴别人、授权或证明网络包；不得填不存在的观察来过门槛。

任何可能失联的实际变更前，将本轮确切路径、摘要、原值和独立恢复命令放入客户私有离线说明。guard保留的root-owned worker可用可信Python的 `-I <state-dir>/runtime.py _recover <state-dir> --plan-sha256 <已核摘要> --allow-system-change --control-channel-independent --recovery-ready`独立恢复；它只处理既有回执范围。remote导出的Linux worker可独立执行同名CLI，Windows离线导出使用完整随包工具；rollback仍绑定固定state目录与计划摘要，不依赖在线Codex。恢复材料和临时URL都不公开。

只对本轮选中功能安排目标机验收，系统级实际配置、提权、重启、故障和恢复结果不能由临时目录／mock测试代证。
