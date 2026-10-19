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

生成 `report.md`、`report.html`。HTML 使用内嵌样式，不载入第三方字体／脚本，不发网络请求。报告投影固定字段，不渲染导入 JSON 的任意额外字段。未知／未执行单列：DNS TYPE64/65、DNS64实际行为、公网 IPv4/IPv6、WebRTC、规则实际命中、账号请求和断线保护仍需按清单单独核验。没有综合“安全分”或自动全项通过。

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
