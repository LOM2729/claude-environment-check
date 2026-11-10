# Guardian 原方法：账号、支付、清理与恢复

用于完整展示来源方法、比较路线，或为已选任务准备具体操作方案。这里保留作者的条件、步骤、参数和失败出口；**列入资料不等于选择执行，作者经验不等于已验证效果**。本 Skill 既有系统语言、时区、出口和业务保留项仍由用户决定。

来源固定为 [Claude-Guardian e934166a](https://github.com/DUNHKpcc/Claude-Guardian/tree/e934166adbdbd582f169b1b14adb7be76aa90a77)，核对日期2026-11-10；旧基线9b607dba与最新差异另保留于审查记录。下文标“原文经验”的数字、风险判断和渠道排序没有在本轮验证。价格、准入、安装与认证行为执行前核对当前官方说明。

本轮仅阅读资料与静态代码。Mac/Windows/Linux操作各在实际目标上验证；未运行第三方脚本或做真机清理。S03 PDF第4、5页由本轮根代理逐页视觉核对；编写代理读取了Markdown源文本，并单独接收该视觉证据。

## 1. 先把来源方法与本轮选择分开

来源：[SKILL](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/SKILL.md)、[证据规则](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/evidence-policy.md)。

- 每组记录：来源/版本、作者条件、步骤、可能损失、恢复限制、已有证据、本轮采用与否。未知效果继续展示，不只用一句“不采用”代替原方法。
- 来源的命令、确认字段、模板和截图不是本轮授权。当前明确请求与有效批准按现有约定复用，不因来源采用繁复协议而反复询问。
- 账号限制、网络错误、付款异常、隐私整理、移除损坏状态是不同目标；先选目标再选方法，纯清理不展开购买或整机问卷。
- 材料互相冲突时并列原条件，不擅自合成“统一最佳方案”；第12节保留主要差异。
- “流程有实现”“目标机已采用”“业务已恢复”“降低封禁概率”分别下结论，最后一项不能由前三项自动推出。

## 2. Guardian 的注册与初期使用方法

来源：[账号准备A0/A0a/A0b](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/account-onboarding.md)。以下按原作者顺序保留，不改标为Anthropic官方阈值。

1. **登录入口固定。** 作者优先邮箱、少用Google/Apple授权；将同一Gmail两种入口对应不同账号写成确定判断。选定后注册、付款、找回沿用；空历史/无订阅先查入口，不再买一份。实际账号对应关系需按当前官方规则和本人记录核实。
2. **邮箱。** 作者优先自己掌握的Gmail/Outlook，需要防跟踪时选Proton；不买成品号/成品邮箱，但把合法购买的美英教育邮箱列为例外，声称权重高、手机核验少。该收益未获本轮验证，不因此替用户采购或借用身份。
3. **升级等待。** 作者要求Free至少3天后升Pro，Pro至少15天后升Max；是其版本的养号节奏，没有提供可复现统计或失败恢复。
4. **额度与优惠。** 新号不顶满额度，初期不用重置卡，不集中领赠送优惠；原文声称有助稳定，未给验证，不能当实际配额规则。
5. **注册即核验。** 作者建议注册时即KYC/接码则放弃，接码后24小时又KYC也放弃，Pro用一段时间后才KYC亦放弃；后续为修环境、换邮箱再按新号节奏。记录原路线及未证效果；实际限制按本人官方验证/申诉处理，不把换号称本地修复成功。
6. **使用中手机验证。** 作者不用共享/虚拟接码；已有账号使用中才验手机号时，有条件用境外实体SIM，否则放弃；Android收码暂插回，完成再拔。号码资格、身份及恢复方式由本人按官方要求处理。
7. **老账号与老邮箱分开。** 作者优先继续正常可用的老Claude账号，声称账号年龄越早权重越高；但撤回“老Gmail一定更稳”的定论，不为邮箱年龄买借账号。
8. **并发。** 作者给新号1–3个同时请求的范围，合计网页、手机、Desktop、多个终端及子代理，超过3建议减少；不按session数量直接计数。子代理可能顺序或并行，须看真实在途请求。
9. **Workflow。** 作者要求新号不用workflow，未给准确能力定义或因果验证；记录原说法，不据此禁用用户已有合法自动化。
10. **设备经历。** 严格原条件为“超过3个受限账号”则换设备并同时换新出口，旧设备不再登录；3个以内先清本地残留再用，手机同样。阈值未验证，不能改写成“3个即触发”或硬件黑名单已证实。
11. **内购活跃。** Apple/Play内购后手机App至少每周用一次，选渠道及续费时提醒，手机电脑同出口。没有证明这个频率是平台门槛。
12. **最新原版CLI优先。** 新注册初期先用原版Claude Code CLI，暂缓CC Switch、oh-my-pi等需OAuth的第三方工具；未给初期结束时限。这与其他来源的Desktop优先路线冲突，见第12节。
13. **新手组合。** 初次订阅且拿不定主意：Apple内购＋自有Gmail/Outlook＋独占VPS出口＋VM或本机＋Pro；声称退款/稳定较好。原文另加11-05备注：iOS内购KYC增多，介意则换方案；不能只留“首选苹果”。
14. **异常时间线。** 原文按注册分钟至1小时、开套餐数分钟至当天、首次Code后0.5小时至数小时、注册1–2天、数周/月给排查方向。根代理视觉确认S03 PDF第5页该表存在；它是风险假设，不是按时间自动判因的诊断器。

## 3. 支付与购买后的处理路径

来源：[支付手册A1–A3/B1–B7](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/accounts-and-payments.md)、[S02支付原文](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/S02-ai-payments.md)。

- **先权益后渠道。** 分清聊天/Code订阅、API或聚合余额、商店余额、组织席位；按设备、地区、已有工具、预算选1–3候选，标源文A官方/B自述实测/C推广。99%/100%与星级不是本轮统计；零新增工具费用就不引导开户。
- **历史候选。** S02列Google Play/App Store、Starryblu、OpenRouter、Bybit、Plasma、SafePal/Fiat24、Bitget等；补表还有RooGoo、MEXC、Rain系、Krak。企业列Mercury、Airwallex、Slash、Relay，个人美卡列Velo/East West。用途、地区、KYC/KYB、费用分别核实，能办卡不推Claude必收。
- **高门槛路线。** S02保留LLC→EIN→Mercury→Stripe/Wise历史链，并列真实经营地址、经营存在、KYB和税务责任；不是普通订阅默认前置，不因资料有路线就替用户注册公司或开户付款。
- **Apple礼卡渠道。** 作者首选Apple官网，失败时列Pockyt Shop、支付宝海外礼卡、微信PockytShop，Amazon US/JP备用；低价闲鱼淘宝不推荐，币安/USDT仅少量反馈。先核卡种、发行/兑换地区、面额、交付和退款；“美区通常$10起”等是历史信息。
- **无Apple账户的原方法。** 本人在account.apple.com创建账户，作者选美国，填真实资料、自有邮箱及可收码手机号，完成邮箱/短信验证；iPhone/iPad App Store补商店信息，选None、核storefront，等3–7天再充值。地区仍须符合实际资格，不代填虚假信息。
- **Apple ID等待失败出口。** 作者把立即充值后卡在支付/扣款失败/会员不到视为风险表现；联系Apple，不换账号反复兑换、不再买一份。3–7天是作者阈值，与Claude的3/15天分开。
- **Apple购买顺序。** 设备/Apple验证/storefront→卡种地区→官方App/套餐入口→正确Claude账号→当前含税金额/周期/余额→本人购卡兑换→结算→分别核余额、订单、权益。地区不符、入口/税费不明先补条件，不购卡试错。
- **礼卡免绑卡说法。** 作者后增段断言余额无需绑卡/地址，同文件前文却要求检查额外付款方式。保留内部冲突；[Apple余额说明](https://support.apple.com/en-us/118245)有部分购买仍需付款方式的反例，不能通用承诺。
- **Apple续费入口建议。** 作者据一次已扣未到账案例，要求到期从Claude App内订阅页续费，而非App Store订阅管理页。保留入口及案例条件，执行前查当前官方流程；失败先原渠道对账，不重复订。
- **Google Play顺序。** Android/Google验证/Play国家与付款类别→官方App/套餐→正确Google与Claude账号、含税金额/账期→本人付款→Play订单和权益。失败走Play恢复购买/支持，不网页重订；卸载不等于取消订阅。
- **网页卡。** 核卡类别、发行地区、真实账单资料、线上/循环支付；本人官方结算处理3DS。作者建议发卡方登记地址，不任填免税州，并提出地址/IP/币种对齐经验。拒付先查待处理/已扣，再联系银行，不反复小额试刷。
- **API/组织。** 明确需求才查提供方、项目、调用/付费权限、用途、预算、重试成本、告警/硬上限；购额度、自动充值、建Key分开。组织才查席位/合同/KYB；未创建的控制写计划，不把提醒称硬限额。
- **付款交接。** 列产品、收款方、本人核对的账号、含税总价/币种、周期/续费、协议及取消退款；金额/条款变先更新。付款/兑换/秘密输入本人完成，不擅自勾自动充值或升级。
- **购买后。** 核一次订单、权益、渠道、生效/续费；升级核抵扣与生效，跨渠道先核旧订阅退出避免双订；取消续费、立即停权益、退款、申诉分别处理。
- **故障出口。** 入口缺失不买卡；兑换错交Apple/卖家；超时先查订单；已扣未开通核账号/恢复购买；双订分别记录不全取消；身份审核转官方。不能用再付款判断网络。

## 4. 手机与申诉原方法

来源：[手机指引](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/mobile-guidance.md)、[申诉模板](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/ban-appeal.md)、[S03 PDF](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/S03-claude-experience.pdf)。

1. **触发。** 手机注册/登录、手机主要设备、选IAP或仅手机时加载；本人在手机操作/付款，电脑结果不能代替。
2. **出口。** 作者固定国家，最好ISP/ASN稳定，允许动态家宽但不频繁跨国/运营商；手机电脑同出口，避免跨国同时在线，不共享/批量切号。
3. **网络。** Guardian手机页要求客户端关IPv6、DNS与出口一致、重点查WebRTC公网候选。但S03 PDF第4页是“正常统一出口，或关闭IPv6”两分支，根代理已视觉确认；保留场景差别。
4. **时区/语言。** Guardian让iOS关“自动设置”选出口城市、Android关自动时区选目标，先记原值、不频繁改；语言不强改。S03 p4却写保持真实时区；实际平台可能联动校时，先说明再操作。
5. **App/定位。** 优先官方App；源文Android8+/iOS18+需现场核当前要求。无需求可不给定位，需要地图/本地功能另授权；本人真实账单不能用代理地区代替。
6. **Android SIM。** 作者平时拔卡，收码暂插境外实体卡、完成再拔；会影响通话/短信，iOS无同项要求。保留为未证方案，不默认操作。
7. **手机验收。** 作者要求Net.Coffee除语言外全绿、时区匹配；另称Android Linux与Linux出口一致、iOS TTL差异小、浏览器不改UA。浏览器检测不能验App路径或账号安全，TTL解释另需证据。
8. **申诉时间线。** 作者称2–7天回复，超过7天建议修环境换邮箱；等待不重复提交/登录，解封后不骤增使用/换出口/升Max，称解封账号权重较高。时间和权重是经验，不替代实际工单。
9. **两问模板。** 第一问实际用途；第二问官方要求解释的异常、本人是否发起、真实访问地区、人工复核/恢复诉求。删除不符事实的“并非本人”“非受限地区”等句，不制造陈述；英文模板见固定链接。
10. **交接。** 本人审核后官方提交，记录草稿/已提交/case；不多入口批量投。导出核当前可用范围、格式/有效期、私有存放；退款走原渠道，申诉成功不自动产生退款资格。

## 5. 清理对象与三平台方法

来源：[清理CLI/宿主](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/cleanup-cli-usage.md)、[Windows手册](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/windows-cleanup.md)、[Linux手册](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/linux-cleanup.md)、[S06 Mac](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/S06-macos-cleanup-sanitized.md)。

- **目的。** 退出登录、损坏缓存、卸载Desktop保CLI、精确状态移除、迁移、历史整理分别选；明确全清不依赖封禁史，但保护对象不能自动纳入。当前事故保留证据，no_cleanup结束问卷。
- **Mac候选。** 原白名单三档：可再生、Desktop持久、对话。CLI可再生含cache、stats-cache、telemetry、usage-data/usage.jsonl/usage.with-fix、remote-settings、policy-limits及stamp、shell-snapshots、statsig、logs、image-cache、debug；是固定版本候选，不仅凭名称清理。
- **Mac其他候选。** Library的claude-cli-nodejs缓存、Claude日志、指定Desktop缓存/崩溃；持久含Application Support的Claude/Claude-3p/claude-code-desktop/com.anthropic.claudefordesktop，及对应HTTPStorages、Preferences/ByHost、Saved Application State、WebKit。完整路径以源宿主allowed定义为准，不全盘展开通配删除。
- **对话。** projects/history.jsonl含会话、自动记忆、输入及旧命令输出；原作者建议另问是否移动，同意才选。旧会话暂不可见/不可续接，恢复仅针对本次隔离。
- **保护。** 源宿主拒绝整个.claude作根，保护settings、CLAUDE.md、skills/plugins/commands/agents/hooks/rules、file-history、sessions、plans/tasks/todos/uploads、backups/jobs/daemon、credentials等；.claude.json、CLI程序、浏览器、钥匙串、卸载另划范围；集成精确例外见第8节。
- **写入者。** 保存工作并退出目标Claude/IDE/终端会话，不由正在使用目录的Claude自己清。Mac宿主按可执行名查，Node会话可能漏；前后进程检查不是强制锁。未知归属/链接/共享根/变动/控制通道冲突停止该项。
- **备份。** 独立私有备份；0700/0600只是POSIX条件，Windows须实际ACL核验。逐相对路径/类型/大小/内容哈希比对，不一致停止；备份与隔离分开，都可能含登录材料，不上传。
- **隔离。** 原件移同卷私有目录，逐根记原路径/摘要/阶段。Windows允许另盘备份，但不跨盘删除原件；原位置仍在只能称备份完成。多个目录不是一个原子事务。
- **失败/恢复。** 失败先核原位置、隔离、备份与阶段，不称没移动、不盲重试。恢复前停写、核当前身份/内容/回执；新原件或后续编辑保留双方，重定精确范围。原Win/Linux简例直接Move回去，实际须补冲突保护。
- **Windows发现。** 分清USERPROFILE配置/credentials/native/WinGet、APPDATA/Anthropic profiles、VSCode globalStorage、TEMP scratchpad、Desktop配置日志；MSIX查实际包/数据，不猜Packages路径。
- **Windows顺序。** 进程/路径→私有ACL备份→Rel/Size/SHA256清单比→同盘Move→backup_verified/quarantined记录→核原位置消失/清单/保护项。作者新版未真机重跑，WhatIf只是对应命令预演。
- **Windows被拦。** 区分宿主拒绝、缺授权、OS占用；停止，不换工具绕过。只读对账后给保留、本人移动或撤回的具体选项；交接范围/影响/备份/阶段/回传，本人操作后仍复核。
- **Linux。** 区分本机/VM/VPS用户、有效CONFIG_DIR、~/.cache/claude-cli-nodejs、/tmp/claude-UID、VSCode Remote数据；退出IDE/tmux→私有cp-a/diff-r一致→同盘隔离→核保护项；/tmp跨卷先说明。无内置Linux宿主，不套Mac验收。

## 6. 认证、bare、项目purge与卸载

来源：[Mac状态脚本](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/native_claude_state_mac.py)、[Windows§6–8](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/windows-cleanup.md)、[S06§4–10](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/S06-macos-cleanup-sanitized.md)。

1. **钥匙串原动作。** 独立确认后精确查Claude Code-credentials、可选Claude Safe Storage，再用security删除整项；存在/未找到/访问失败分开。删除不可恢复、需重登，SafeStorage可能使Desktop数据不能解密；不是只去OAuth保留MCP，也不覆盖所有自定义命名空间。
2. **文件凭据。** Win/Linux原方案是单独备份后移credentials.json；官方/logout属于运行客户端。整个文件可能共享MCP/插件认证，先核schema/损失；本地移除不等于服务端撤销。
3. **Windows凭据管理器。** 原文列Claude相关目标后精确删除、另确认且不可恢复；没证明所有版本都有，不按关键词批量删除。
4. **配置登录字段。** S06曾见oauthAccount、旧primaryApiKey、Desktop oauth:tokenCache/V2/lastKnownAccountUuid；先备份，结构化仅删确认字段、解析复验。未知版本不猜，缺失路径不重建。
5. **设备记录。** S06还列machineID/userID、ant-did、ant-device-registry.json、config.json.journal；本地字段不是硬件UUID，删除/轮换不证明新设备或解除关联，普通退出不随机伪造。
6. **SIMPLE/bare。** 原方法在settings.json的env只增CLAUDE_CODE_SIMPLE=1或移此键；先备份/结构化改/对比其他字段，Win序列化足够深度。作者对应--bare：最小提示词/Bash文件工具，不自动发现hooks/skills/plugins/MCP/自动记忆/CLAUDE.md；不读OAuth/钥匙串，订阅登录不可用，只API key或apiKeyHelper。先确认认证与功能需求。
7. **SIMPLE恢复。** off移键，必要时无冲突恢复备份，不覆盖后改。源独立脚本没复用完整路径/并发事务保护，读回只重点查遥测键；不能因原子写就称全部设置保持，当前版本另验。
8. **项目purge。** 原文列claude purge <项目路径> --dry-run预览，再本人决定实际purge；清项目对话/自动记忆/.claude.json项目项，不清shell-snapshots/backups。先核当前CLI帮助/版本/损失；它会运行Claude，不是纯离线检查或已验证可恢复删除。
9. **卸载Desktop保CLI。** S06用App Cleaner详细视图按完整路径选目标，保留CLI入口、版本目录、.claude、.claude.json；额外Claude Code Haha、claude-code-desktop、URL Handler各判归属。Desktop vm_bundles/本地任务非纯缓存，先导出/备份。
10. **浏览器集成。** NativeMessagingHosts、PWA、扩展分开；删消息清单影响桥接，不等于卸载扩展/清Cookie。网站数据优先原生单站点入口，见[浏览器清理](https://github.com/LOM2729/claude-environment-check/blob/main/.agents/skills/claude-mac-readiness/references/browser-cleanup.md)。
11. **验收与永久性。** 核多安装入口、原位置、进程/集成、CLI/项目保留；移出、废纸篓、删除备份、SSD安全擦除分别说，TM/APFS不自动纳入。S06历史Edge12条Cookie只属于那次，不代表当前所有Profile。

**2026-11-10官方文档补核（根代理完成，未运行CLI）：** [bare模式](https://code.claude.com/docs/en/headless#start-faster-with-bare-mode)与[环境变量](https://code.claude.com/docs/en/env-vars)确认CLAUDE_CODE_SIMPLE等价bare，不读OAuth/Keychain；认证需ANTHROPIC_API_KEY或通过--settings提供apiKeyHelper；显式--add-dir的skills存在例外。**不要把bare称为“订阅轻量模式”。** [CLI参考](https://code.claude.com/docs/en/cli-reference)另有--safe-mode，保留正常认证、工具和权限，适合定位自定义配置故障；它与bare分开选择。

同次[CLI参考](https://code.claude.com/docs/en/cli-reference)核对的purge范围包括该项目transcripts、tasks、debug、file-history、prompt-history和.claude.json项目条目，可先dry-run。上文保留的是原作者摘要；实际确认必须按目标版本预览列出这份更细的损失清单，尤其不能把file-history/tasks当仍然保留。

## 7. 原作者的旧 IP 痕迹清理链

来源：[trace-cleanup全文](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/trace-cleanup.md)。原目标是减少以后Agent读文件/粘贴输出误传旧IP；原文明确日志不会自动上传。不能省略该隐私目标后只剩“防封未证”。

- **共同顺序。** 定隐私/迁移目标与保留证据→按应用列准确对象→停写→独立私有备份→只选定项隔离/过滤→核目标与保留项。事故日志、唯一恢复证据不自动清。
- **代理日志。** 找Verge/Mihomo/FlClash实际logs→退出目标GUI/核写入者→隔离logs保留profiles/config→重开验连接。作者说部分服务核心不写Verge logs，这是需版本核对的条件。
- **未来少记。** 作者另选log-level warning/silent，原值另存；不把少记与清历史隐含绑定，说明会减少排障资料。
- **VPN。** 盘点实际客户端→优先原生清日志→否则官方目录；需停服务或管理员权限时说明断网/交接，先备份再隔离，随后核连接。
- **zsh/bash。** 确定实际HISTFILE并停其他写入终端→匹配选定检测站/命令→本机先过滤秘密再展示行号摘要→整份备份→只移获准记录→核匹配/保留。源示例按行过滤，复杂多行格式另核。
- **匹配清单。** ipinfo.io、ip.sb、ifconfig.me/co、icanhazip、ipify、ip-api.com、ipapi.co、ip.gs、cip.cc、myip、ipecho、checkip、whatismyip、ping0.cc、ip.check.place、ip.net.coffee、ipleak、browserleaks、dnsleaktest；只按用户实际补充，不扩成所有网络命令。
- **回写。** SHARE_HISTORY/INC_APPEND_HISTORY可能回写旧记录；作者关其他窗口、当前不写历史、处理后重开。不能为此关掉唯一Codex/远控终端，应交接或暂停。
- **fish。** 用history delete --contains逐条选择，不grep改多行历史；保留需用记录，恢复不覆盖后来新增。
- **PowerShell。** 实际PSReadLine HistorySavePath→停其他写入窗口→整份备份→仅滤目标/清本窗口内存历史→复查；编码/并发另核。作者说cmd不持久历史，其他终端插件/日志仍按实际判断。
- **输出另找。** shell历史是命令，不是输出；分别查iTerm自动日志、tmux-resurrect capture-pane、script、tee/重定向。问原保存位置，不全盘搜私文件；同样停写/备份/隔离。
- **Claude会话。** projects/history可能有旧输出及自动记忆；作者另问并建议移动，解释无法续接，同意才纳入。
- **排除。** 系统统一日志/事件/journald、代理VPN配置、整份shell历史、浏览器历史/站点不属此链。源“直接拷回历史”须补后改冲突；空过滤结果/失败写入也对账，不只看退出码。

## 8. MCP、插件、hooks 与后台工具的定向处理

来源：[集成审计/清理原文](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/illegal-tools-cleanup.md)、[I1–I3/J1–J3](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/incidents-and-integrations.md)。原标题称“非法工具”，实际按功能/来源/数据及当前规则判断，非官方BASE_URL或关键词不能单独定性。

1. **位置矩阵。** 用户/项目mcpServers、.mcp.json、settings的hooks/env/apiKeyHelper/statusLine/enabledPlugins、skills/agents/commands/hooks/output-styles/mcp-servers、全局/项目CLAUDE.md、Desktop MCP/扩展、shell/Windows变量、LaunchAgents/systemd-user/任务/服务/Docker/npm/pip分别盘点。
2. **实际行为。** 作者关注破限提示、账号/订阅转发分发、秘密/对话外传；看每项来源、触发、命令、接收方、读写范围和依赖。正常开发工具保留，拿不准标未知，不批量禁用。
3. **脱敏审计。** 源示例打印args/URL/hooks正文会泄密；采集端先过滤参数、查询、内嵌脚本中的秘密，再输出必要名称/类别/行号。不要为了盘点运行apiKeyHelper、mcp list或未知诊断脚本。
4. **定向变更。** 先独立备份/内容比对；JSON只删确认的server/hook/env/plugin项，保留未知字段，预览差异、解析复验；独立插件/skill/脚本整项隔离，其他不动。
5. **环境覆盖。** shell只处理确认行；Win仅具体User/Machine键。原文只记“有/无”不足以恢复值：如需恢复，将原值留私有安全备份、不进聊天，再核新进程采用。
6. **后台服务。** 作者分别用launchctl bootout、systemd-user disable/stop、计划任务禁用、Docker取消自动重启后stop，配置移隔离。说明依赖中断；恢复要还原服务/自启状态；卸载全局包、删容器/镜像另划范围。
7. **凭据事件。** 组件读转OAuth/Key时说明影响，由本人官方撤销/重新认证；本地卸载不撤销远端授权，旧Key不是回滚。停止已有用户任务按实际授权，不因审计自动杀进程。
8. **复验。** 再盘点目标、解析JSON、确认正常MCP/插件保留，并核批准入口功能。stdio不证明离线；remote MCP新增接收方/权限、自动hook/插件更新分别核数据边界。
9. **最小试验。** 明确上游、认证/计费、无秘密输入、次数/超时/成本/取消；流式分首字节/终态/断流，重试先查副作用和费用，幂等只在接口支持时用。失败停新增请求、留脱敏样本，不换账号/IP代替限流处理。

## 9. 访谈、同机 Agent 与中断交接

来源：[intake](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/intake.md)、[同机Agent](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/agent-on-target.md)、[授权档位](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/authorization-tiers.md)。

- **访谈。** 区分首次/到期重订/当前订阅，事故优先；一次主要决定，已知不问、未知/拒答不循环，Q-C07退役。当前套餐只在真实功能依赖时问，不能用目标套餐当已付权益；退款不展开新购设备问卷。
- **事实冲突。** 保留来源、账号/目标、观测时间、当前/历史；订阅冲突用独立episode，明确新事实才解决，不能用false当解决。导入旧数据不刷新为本轮观察，账户/任务变化只失效受影响部分。
- **路线/能力。** 作者要求先选本机/VM/VPS，再核目标Python3.10+及随包工具；缺Python按范围安装，固定network_check→补证据→egress_verifier链。此是上游流程，不自动替代我方工具或要求为读资料安装依赖。
- **A/B/C原协议。** A范围内只读/临时文件；B整单批准、可撤销不失联；C账号钱凭据/删除/不可逆/失联/时区/SIMPLE等当场确认。上游记录仅追溯，C一次性，恢复会话即stale；我方同一有效批准按当前用户/共享规则复用，不机械重问。
- **Agent链路。** 查执行机、父子与代理变量类别，再核实际连接是物理直出/本机代理/TUN/宿主LAN代理；只展示类别，不输出秘密或完整端点。
- **断链原安排。** 开TUN最后交本人点；killswitch前迁Agent到本机TUN，不给宿主LAN代理另放行；长期失联动作交目标终端或独立管理端。禁止LAN例外是否采用，要与用户保留业务单独比较。
- **离线交接。** 断开前保存私有进度、已改项、保险丝期限、准确动作/离线恢复；重连先核规则/回滚/出口，不原样重复失败。VM/VPS先评估内存/OOM，tmux不保证重启/崩溃恢复。
- **待办。** 手动前先完成可做前置，列目标、范围、影响、恢复、回传和原因；作者把未验收项标blocking_next_session，下次优先提醒。提醒不授权，用户本轮不做保留未完成、不挡无关任务。
- **事故闭环。** 最小事实→按响应方分类→保留证据→支持/导出/退款分流→具体关闭标准→受影响功能复测。暂不报错不等于全好，已发数据/费用不能本地撤回。

## 10. 上游宿主、规则任务和恢复工具

来源：[host-libraries](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/host-libraries.md)、[cleanup契约](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/cleanup-cli-usage.md)、[单条rules任务](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/agent-rules-task.md)。这里说明入口，不把占位路径当可直接执行命令。

- **通用cleanup_cli。** 普通入口只capabilities/scope结构校验；plan/quarantine/reconcile/restore需可信宿主verify/approve/exclusive/cancel。保存JSON/摘要/“已授权”开关不是许可或所有权证据。
- **绑定/顺序。** plan绑定路线、目标、根、保护路径、同卷隔离/备份；quarantine要同一完整entry，变化重做，上游拒绝VPS quarantine。既有回执reconcile/restore不要求重填新路线问卷，但恢复条件独立核实。
- **Mac确认。** 宿主仅Mac，真实TTY分别confirm create_backup、plan、quarantine、需要时restore；read_reconcile/save_receipt复用范围。短语绑定操作名/review摘要前8位，Agent不可代输；仅固定清单、已退出目标。
- **命令差异。** cleanup_cli支持原文-I-S-B启动；native清理/状态/repair兄弟导入不能盲用同参数。quarantine/reconcile/restore需host-scope，plan/quarantine还绑定entry；下步用stdout document_digest，不混core action digest。
- **元数据。** 源适配容许Mac15 com.apple.provenance，其他不支持xattr拒绝后缩小/核范围，不删属性过门禁。进出查进程不是锁，Node会话可能漏。
- **多根事务。** 源有10分钟计划、逐根prepared/done、recovery_id/count/stage；失败可能已移动。对账当前位置/内容后用新回执恢复，新原件/未知差异停止，不手改日志/摘要。
- **独立文件恢复。** 先保留离线CLI/备份；失败inspect→绑定目标/批次/reconcile；仅v2prepared候选匹配才单独restore-prepared，当前观察摘要/停写必需。恢复后日志失败也先对账，不重放原apply。
- **2.5.8 GUI任务。** 仅现有独占rules扩展、一个DOMAIN到已有组、三空序列；app plist/index/extension/base有界快照→候选→保留BOM/CRLF/注释→具体批准→GUI存一次→核归属/内容/载入/实际规则。save超时先查，不重复存。
- **规则读回。** 无变化结束；有注释需精确字节，无注释才有限格式化语义比较；多字段/规则/后改不能当格式。恢复优先原字节，GUI重排另审。
- **原生修复。** repair只对Mac Clash Verge Rev2.5.8 rules-prepend开放固定适配；作者记录Mac15.7.4写/重启/回滚，后续script/merge仍可能覆盖。其他版本/Windows/merge-policy不能由此宣布可用。
- **静态边界。** inventory/remedy/config候选仅证声明/供给快照；面板把24h内network结果标已验证，导入仍核同目标/平台/配置/入口，不能用TTL代替绑定。返回pass不是本轮验收。

## 11. 更新、来源与交付

来源：[更新流程](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/skill-update.md)、[来源库](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/source-library.md)、[update_check](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/update_check.py)。

- 作者每会话开始查一次：GitHub tree/commits两GET，比git blob哈希；失败继续本地不循环，有更新再选。这里不将作者每次联网默认移植为我方无条件动作。
- 更新先取已知仓库，备份整个Skill到skills外，保留用户改动/本地独有文件后替换复查；出错从备份恢复。私有配置/秘密/用户数据不随包发布。
- 回答按主题附原文/节/PDF页，支付S02第一；清单逐项列已执行/未执行/原因，规划也列全。索引、辅助文字、PDF、历史报告、派生说明分开，名字存在不等于读过。
- 同哈希只算一来源，转载/节选不自动独立；固定提交/许可不替代适配或安全修补核验。
- 交付实际对象、原值/候选、处理/失败、备份/隔离/恢复限制、目标验证/未验；历史记录写机器/版本，不填成本轮完成。

## 12. 必须并列的原始资料冲突与额外阈值

来源：[S03源文本](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/S03-source-text.md)、[S03 PDF](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/S03-claude-experience.pdf)、[S04指南](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/S04-claude-guide.md)、[env-cleanup 56ba3fb3](https://github.com/pnedfff/claude-env-cleanup/blob/56ba3fb388449ff2533487f9044e17300178df1b/SKILL.md)。是比较目录，不要求叠加。

| 主题 | 分别保留的原说法 | 使用时标记 |
|---|---|---|
| 初期客户端 | 最新Guardian先原CLI、暂缓CC Switch/oh-my-pi；env前2周偏官方Desktop/App、避免独立CLI；S03少CLI多Desktop/网页 | 三条冲突；env完整路线见[另一来源方法](source-methods-ccbaga-cleanup.md)，不能合成共同结论 |
| 升级/额度 | Guardian Free3天/Pro15天，初期不顶满/重置卡/集中赠送；S03低价区半月、Pro一月、每周期不撞限；env Max升级后两周约≤3次触顶，约一月/首续费后放宽 | 原阈值分账号阶段保留，无本轮因果验证 |
| 使用节奏 | S03按出口工作时间、不深夜长在线；S04前3天每日5–10对话、每分钟<10请求、随机抖动、单会话≤2h，24–72h观察；另称每日<4h续费少问题 | 原条件/效果保留，不制造“像人使用”流量规避实际限额；真实负载与条款另核 |
| 套餐 | S04每日>2h推Max x20及历史价格；Guardian新手先Pro | 预算/用途不同，不能沿用旧价或默认最高档 |
| 邮箱入口 | S03少Outlook/老Gmail好、Google/Apple授权好；Guardian优先Outlook/邮箱、老Gmail无定论 | 保留来源/版本，账号映射本人实际核 |
| 位置 | S03尽量不在VM/VPS；S04推VPS独享Max并称架构排除风险；Guardian本机/VM/VPS并列 | 隔离/运维机制与账号效果分开，不称架构免封已证 |
| 手机IPv6/时区 | S03 p1偏关IPv6/语言对齐；**p4可统一正常出口或关IPv6，真实时区不频繁改、语言不必英文**；Guardian后改出口时区/关IPv6 | p4/p5根代理视觉核对；不截p1覆盖手机，用户偏好另列 |
| 设备 | S03曾封就换；Guardian严格>3换且联动出口，≤3先清 | 作者经验，不是已知硬件黑名单规则 |
| 支付/代充 | S03稳定代充可选但有退款/数据损失；S04含代订阅推广；Guardian不碰代充；S02本人渠道资格 | 不将推广排序当验证，保留原选择及后续差异 |
| KYC/申诉 | S04称KYC要美区SSN、申诉<5%；Guardian分阶段弃号及2–7天经验 | 官方当前要求/真实case优先，来源数字未验证 |
| 中文/邮件 | S03称输入中文比输出影响大、多级Agent风控、看Claude邮件也同出口；其他来源有中文正常个案 | 邮件跟踪机制与封禁因果分开，保留原场景 |
| 时间线 | S03 p5五窗给旧环境/支付/CLI/新号强度/累计行为方向 | 根代理视觉确认，仅列假设，仍按错误/来源/变更定位 |

## 13. 采用前需补的技术证据

来源：[Mac宿主](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/native_cleanup_mac.py)、[授权辅助器](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/scripts/interview_flow.py)、[原审计](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/references/illegal-tools-cleanup.md)。

- Mac备份有哈希，但后续活跃源主要比名称/类型/大小/mtime/mode等signature，备份检查也缓存；不能称每阶段重比源内容，实施需补当前内容和身份复核。
- SIMPLE独立写入没有完整路径/并发事务；钥匙串原法整项删除不可恢复。原生API没有字段级原子更新时，不能用两次读伪装CAS或承诺保留并发MCP令牌。
- Win/Linux的ACL、同卷、记录格式、停写和恢复冲突须目标机验；作者自己标Win新版未真机复跑。
- 原授权辅助器A档只见active scope即allowed，不能证明动作在批准集合；程序标记不替当前许可。
- 这些边界不意味着从目录删整条方法。选用后准备可验证的最小方案；只要求展示/维护资料时到此结束，不运行真实环境。
