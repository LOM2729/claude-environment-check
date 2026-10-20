# 统一采集、报告与配置读回工具

`scripts/claude_setup.py` 是跨平台统一入口，Python 3.9+。Windows 原生采集由同目录 `collect_windows.ps1` 完成，使用系统 Windows PowerShell；不绕过执行策略。YAML 分析另需 `PyYAML==6.0.3`，其他 JSON、Shadowrocket、采集和报告功能只用 Python 标准库。

## 先检查运行条件

在客户机确认已有 `python3`（Mac）或 `py -3`／`python`（Windows），不要把 WSL Python 的采集结果当作 Windows 原生。缺 Python 时先说明安装范围；不能声称包本身附带 Python。需要 YAML 时可在客户批准后用现有 Python 创建本任务 `.venv`，从随包 `scripts/requirements.txt` 安装固定依赖；不全局安装、不自动联网安装、不执行配置内代码。Mac 资料与 Windows 脚本结果都只能反映执行端。

以下 `<PYTHON>`、`<TOOL>`、`<当前配置>` 等表示已核实的本地路径，不是原样执行的字符串。`<TOOL>` 指当前 Skill 的 `scripts/claude_setup.py`。运行时用参数数组，含空格路径正确引用，禁止把文件内容拼成 shell 命令。

## 1. collect：统一只读采集

```text
<PYTHON> <TOOL> collect --output <新建的collection.json> --target-alias client-01
<PYTHON> <TOOL> collect --output <另一个collection.json> --config <当前配置> --format yaml --browser-preferences <明确选定的Preferences文件>
```

输出文件父目录必须已存在，文件必须尚不存在。默认读取系统版本、系统时区／语言、可获取的时间服务或自动选项、系统代理开关、DNS 地址条目数、接口地址族计数、当前进程特定环境变量存在状态，以及 Claude 命令是否能在 PATH 找到。Mac 的地址族计数来自 ifconfig 地址条目，Windows 来自接口列表，不能跨平台当成同一网络数量指标。

不发公网探测、不查询 DNS、不启动 Claude、不检查登录凭据、不修改网络；只有显式 `--config`／`--browser-preferences` 才读取选定文件。浏览器偏好仅投影语言、DoH 模式和 WebRTC 策略值，不是运行中 Profile 或企业策略证明。报告不输出代理地址、密码、UUID、邮箱、主机名、原始 IP、完整路径或环境变量值。

权限不足、PowerShell 策略阻止、命令缺失和读取失败对应字段保持未知；其他可用项继续。`--config` 不支持的语法保留固定错误码。Linux／WSL 只记录执行上下文和变量存在状态，原生 Mac／Windows 字段保持未知。没有已读取字段不等于设置关闭。

## 2. report：自动生成检查报告

```text
<PYTHON> <TOOL> report --input <collection.json> --out <尚不存在的报告目录>
```

生成 `report.md`、`report.html`。客户报告的状态栏只使用 **已完成／未完成**，顶部显示已完成项数、适用总数和未完成项数，未完成排在前面，必须说明原因与下一步。不打安全分。HTML 内嵌样式，不加载第三方脚本或字体；原始采集信息折叠在表格后。

仅 collect 取得的设置不证明检查及必要处理已闭环，因此默认项目都是未完成。Codex 在客户机完成实际检查／处理／复测后，填写核验记录再生成交付报告；客户无需编辑 JSON。

```text
<PYTHON> <TOOL> review-template --input <collection.json> --output <新建的review.json>
<PYTHON> <TOOL> report --input <collection.json> --review <review.json> --out <新的交付报告目录>
```

模板有 14 个汇总检查项，对应现场清单的任务组；不是把静态采集字段数当完成数。可只填写部分项目，其余保持未完成。每个条目字段：

| 字段 | 填写规则 |
| --- | --- |
| `id` | 保留模板固定 ID，不重复或添加未知项目 |
| `applicable` / `scope_confirmed` | 与客户确认无关的项目可设 false / true，并写排除原因；不计入分母，报告单列说明，不增加第三种状态 |
| `status` | 仅 `completed` 或 `incomplete`，报告分别显示已完成／未完成 |
| `change` / `decision` | `none/proposed/applied`；客户决定 `pending/approved/declined/not_required`。这里只记录事实，不产生操作许可 |
| `verified` / `verified_at` / `evidence` | 完成项必须有实际复核、带时区的验证时间和脱敏证据。时间不能早于该次采集；未复测、仅有候选不能完成 |
| `reason` / `next_step` | 未完成项两者必填：说明没检查／缺权限／问题未解决／客户暂不修改等具体原因，以及下一步 |

所有已实际修改的项目都必须记录客户的明确批准，不能把未获批准的修改隐藏在未完成或不计入范围的项目中。若实际发生未经批准的操作，应停止并如实告知客户、处理恢复，不能补造 approved 字段来通过报告。已完成的修改项还必须有复测；客户拒绝／待答复、修改尚未生效均不能填已完成。若经检查现状已满足目标、客户选择保留，可用 `change=none`、`decision=not_required`，写明依据和复核结果。客户暂不修复仍存在的问题保留未完成；不能把拒绝修改自动视为不适用。

核验文件绑定该次 collection 的 SHA-256 与目标别名。采集文件变了要重新生成模板，并逐项复核旧记录是否仍适用，不能只改摘要强行续用。核验记录是操作者声明，工具不能证明其真实性，也不能从保存的 `approved` 字段恢复未来操作权限。报告必须对应客户实际设备、范围与本轮结果。

填写证据和原因时只保留脱敏说明。工具拒绝部分常见密钥、IP、邮箱或私有路径形状，但不能代替人工检查。完成记录不代替服务资格或账号安全结论。

输入报告只是来源材料；目标别名不证明设备身份。确认采集发生在本轮目标机，时间和环境仍适用后再使用。真实采集报告只留客户本地，不提交 GitHub。

## 3. plan：配置差异、快照与静态检查

```text
<PYTHON> <TOOL> plan --current <当前配置> --candidate <候选配置> --format yaml --out <尚不存在的私有计划目录>
```

支持 `json`、`yaml`、`shadowrocket`；`auto` 按 `.json/.yaml/.yml/.conf` 判断。候选由 Codex 根据已核对的客户目标和实际版本准备。工具只分析和记录，不提供 apply 命令，不触发订阅刷新或核心重载。

生成：

- `summary.json`：可供聊天核对的结构摘要，不含节点／域名／凭据文本。
- `plan.json`、`plan.sha256`：绑定原目标路径、原文和候选哈希、格式与创建时间；都是私有计划，摘要不是操作授权。
- `original.bin`、`candidate.bin`、`diff.private.txt`：**包含配置原文，可能含凭据**。只放客户本地私有目录，不在聊天打印全文、不上传仓库。Windows 权限继承父目录 ACL；不能把 POSIX 的 0600 描述成 Windows 隐私保证。

静态检查包括重复节点／组名、已定义组之间循环、未解析引用、兜底规则后的条目、脚本／内容改写／MITM 配置存在和关闭 TLS 验证的提示。这些存在标志不等于功能已启用。外部节点、provider、基础 profile、扩展合并及内核特殊语法可能需要现场补证据。YAML 别名／锚点／合并键／自定义标签当前明确不支持，拒绝时不得为通过检查删除客户配置的语义；可保持原配置并走独立手工审查。成功解析不代表核心语法完全合法、已载入或网络正确。

先看结构摘要；需要逐行审阅时在客户机用编辑器查看私有差异，向对话只提供已脱敏的必要改动。任何实际保存、导入、重载、服务／系统设置修改按原清单预览、批准、备份及恢复要求执行。

## 4. verify：从真实目标再次读回

```text
<PYTHON> <TOOL> verify --plan <计划目录> --target <原目标文件> --output <新的readback.json>
```

工具重新读取显式指定的原目标文件，与计划快照比较；不自动跟随导入计划内任意路径读取。结果：

| 状态 | 解释与下一步 |
| --- | --- |
| `candidate_bytes_match` | 该次文件字节等于候选；继续核对应用载入、进程采用和功能 |
| `unchanged_original` | 仍是原文，不能说应用了候选；检查是否保存到另一副本 |
| `formatting_or_comments_changed_review_required` | 解析后内容相同，但格式／注释改变；必须审阅，不自动认可 |
| `unexpected_content_conflict` | 出现非预期内容或解析失败；保留现状，检查并发修改，不覆盖回去 |

若应用只能导出当前配置到另一文件，可加 `--exported-readback`；结果明确标为调用者提供的导出文件，不能当作活动文件身份或运行时证明。`plan.sha256` 和快照哈希只检查本地材料一致性，不是数字签名、目标认证或许可。

退出码：0 为命令完成（verify 中仅候选字节匹配），2 为 verify 不匹配／需审阅，1 为输入／工具能力等错误。stdout/stderr 只提供摘要与固定错误码；不存在的输出父目录、已有文件／目录会拒绝，不覆盖之前的报告。

## 按清单交付

工具产物只填有证据的检查项；其余由 Codex 完成目标客户端、外部检测及故障实验的授权与验证。差异和读回不会把“写入内容匹配”升级为“网络安全”。没有自动回滚命令；恢复前须检查后续修改及批准范围，按清单选择恢复原配置或重新规划。

## AI 专属代理默认策略

自动配置模式按 [Claude / OpenAI 专属规则](ai-dedicated-routing.md) 先生成单节点候选（`ai-route`）与差异，再由客户机 Codex 应用已批准方案。AI 失败不改走 DIRECT，目标 UDP 显式拒绝，其他国内直连／国外代理及原配置保持。`ai-audit` 比较读回后的静态策略；DNS、客户端接管和故障效果另验。
