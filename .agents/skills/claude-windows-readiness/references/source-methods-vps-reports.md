# 17份VPS报告：完整阅读后的选型与检查方法

补读日期2026-11-10。固定来源为 [Guardian随附报告目录](https://github.com/DUNHKpcc/Claude-Guardian/tree/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/vps-recommendations)。17份PDF共123页均已提取全文并逐页查看渲染，含截图、表格、曲线与末尾限制；连同上轮S03/S08共19份139页。图中故意模糊的IP、小字号/原始像素损失保留，不声称逐个数值独立认证。PDF指向的外部文章/商家网站未递归全站审计。

这些是**历史测试记录与作者选型方法**，不是我方本机测试，也不是现价推荐。商家星级、短期使用感受、共享人数估计、家宽标签与账号效果分别看。下表保留17份各自的实际分支，不把“没有账号因果验证”当作删去方法的理由。具体部署继续按 [Guardian网络方法](source-methods-guardian-network.md)，采购/真实网络操作需要对应任务范围，本次没有执行。

## 逐份报告留下的不同方法

链接均为固定提交原件；“适合”表示作者在该历史样本下的取舍。

| 报告/页数 | 作者方法、适用条件与遗漏后容易误判的细节 |
| --- | --- |
| [EC2台北 t3.micro](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/vps-recommendations/biz-aws-ec2-taipei.pdf) / 6 | 轻量区域开发；把CPU积分、不到1GB内存、根分区与套餐盘容量分开。国际测速好不能代国内家宽；同轮43包ICMP截图有失败/丢包，不能抹成零丢包。持续计算/数据库先核资源与总账单。 |
| [Lightsail马来西亚](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/vps-recommendations/biz-aws-lightsail-my.pdf) / 7 | 套餐式轻服务，逐方向核吞吐/传输额度及超量成本。新加坡互联与国内吞吐分开；双栈路由和ChatGPT结果分开，保留Unknown及Netflix模块分歧。免费广告不构成当前资格。 |
| [Azure新加坡B2ats](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/vps-recommendations/biz-azure-sg-b2ats.pdf) / 2 | x86兼容优先；1GB内存、CPU/磁盘突发、出口账单单列。IPv6经附加基本负载均衡器接入，不当原生双栈。宿主“64-Core”不表示实例得64核。 |
| [Azure日本B2pts ARM](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/vps-recommendations/biz-azure-jp-b2pts.pdf) / 2 | 先核程序/容器ARM64支持，再选轻应用。5秒CPU、QD32磁盘短测不足以选持续重负载；没有完整IP信誉记录则留缺项，IPv6网络失败不填服务通过。 |
| [DMIT产品线](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/vps-recommendations/biz-dmit.pdf) / 11 | 作者按地区和运营商选择T1/EB/PRO：LAX的EB偏联通/移动、PRO偏电信，T1偏国际/落地；不跨地区照搬。AN5跑分不套AN4；2025与2026样本的流量计费方向、IPQS/解锁变化分别保存。 |
| [VMISS](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/vps-recommendations/value-vmiss.pdf) / 11 | 线路机/预算路线；双向总流量不是上下行各一份。标称200Mbps与某工具近6Gbps矛盾要调查。IPv4/IPv6地区、IPQS与路由不同；2025没有Claude/Gemini结论，不由其他AI Yes补上；2026另一台样本不可追认旧样本。 |
| [VMRACK L3](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/vps-recommendations/value-vmrack.pdf) / 5 | 三网路由与轻量网络用途；广东移动样本明显较差，不能用上海电信代全国体验。无IPv6不套双栈结论；磁盘表是IOPS，不把“顺序669”写成669MB/s。 |
| [搬瓦工MINIBOX/MegaBOX](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/vps-recommendations/value-bandwagon.pdf) / 7 | 先分两套餐/两日期；MINIBOX文字CPU和输出不一致，保留型号冲突。小内存和持续CPU限制需要采购前核；MegaBOX的普通IPv6路由不承接IPv4优化保证。套餐升级截图不是升级后样本。 |
| [千宿NTT样本](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/vps-recommendations/value-qiansu.pdf) / 11 | **独立低负载采样与受限补测**：检测阶段OOM/接口限流造成NoData/ERROR，先留失败；结束重负载后重新计时采样。内存补测为1线程、64MiB顺序缓冲、各5秒、虚拟地址上限256MiB；这不是整机容量/原内存复制测试。正文29包表与截图82包/旧时间窗不同，不能互相代证。保留Claude Yes与BANNED冲突、网页/脚本分值差和完整IP查询与实际出口的区别。 |
| [AaITR](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/vps-recommendations/home-aaitr.pdf) / 19 | AT&T/Frontier静态、动态NAT、日本SoftBank、后续Verizon分别选；作者偏Frontier/Verizon静态作中转后固定出口，建议先月付。100Mbps样本近满载重传时给约90Mbps持续速率建议，仅是样本起点。维护/断电/断流与四个月使用经验同时保留；商宽/家庭办公属性仍有争论。 |
| [NodeMach](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/vps-recommendations/home-nodemach.pdf) / 7 | 国内直连丢包明显而美国本地较好，作者建议月付并加中转；独享50Mbps上下行对等与不限流量分别核。标称盘和根盘、文字价格与套餐图各留。IPQS100与IPData79低风险相反，不能由五星结论覆盖。 |
| [NovixLink COX](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/vps-recommendations/home-novixlink.pdf) / 6 | COX落地与同品牌NTT/Cogent分别判断；洛杉矶中转短但有延迟尖峰，国内丢包，轻量出口优先。双栈住宅标签与企业网标签、IPv6 ChatGPT Unknown均保留；历史不退款须在付款前核。 |
| [QQPW夏威夷](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/vps-recommendations/home-qqpw.pdf) / 6 | 美国固定出口能接受额外跨海延迟才选；比较美西与香港中转两段路径。主套餐、NAT/升级奖励不混配；超流量降速影响体验，不能只记峰值400Mbps；黑名单2项不能写全部未标记。 |
| [RadoNet静态NAT](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/vps-recommendations/home-radonet.pdf) / 6 | **固定共享IPv4＋映射端口＋/128 IPv6**路线；核够用的入站端口、回环能力及共享滥用换IP条款。10Gbps为共享端口，忙时单独采样；DNS解锁与原生标签不同，静态不推出独享。 |
| [ResidentialVPS](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/vps-recommendations/home-residentialvps.pdf) / 6 | 带宽优先的美国出口，默认Windows RDP；把中转额外延迟、RDP画面体验、FUP单列。付费Fresh IP仍有IPQS75，不承诺无风险；IPv6与IPv4的解锁及分值不能混合。 |
| [Tokyonline KDDI](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/vps-recommendations/home-tokyonline.pdf) / 5 | 只有明确需要KDDI出口且接受波动时作为来源候选；200Mbps峰值、降速后丢包、慢人工交付及不退款同时看。SAS HDD与老CPU限制重负载，低IPQS不抵消网络/交付问题。 |
| [ZoroCloud AT&T](https://github.com/DUNHKpcc/Claude-Guardian/blob/e934166adbdbd582f169b1b14adb7be76aa90a77/skills/claude-guardian/sources/vps-recommendations/home-zorocloud.pdf) / 6 | 作者看重短时近百兆平稳出口，仍建议中转。无ICMP回应不直接判服务不可用。禁建站/转售、不退款属于当时使用条件；IPQS75、Gemini模块Yes/No与DNS解锁都必须保留。 |

## 可选的连贯选型与验收方法

1. **先定用途。** 仅出口、远端CLI、临时浏览器、完整桌面、长期服务分别列资源和管理依赖；住宅出口机不必承担编译/数据库。ARM64、内存和磁盘限制先筛兼容。
2. **把出口属性拆开。** 静态/动态、独享/共享、原生/广播、运营商/机房标签、物理家用/商用、NAT/独立公网各是不同维度；索取具体套餐承诺，样本只描述分配到的那个地址。家宽、独享、Fresh、新段不提供账号安全保证。
3. **在付款前核限制。** 当期价格/库存、税与总成本、双向或单向流量、超量停机/降速、FUP、持续CPU限制、端口映射、是否可换IP、退款、交付时长及用途条款分别核。历史优惠不默认有效，不以星级或推广链接排序。作者的先月付建议保留为可选采购策略。
4. **分两段比较线路。** 用户/管理端→中转、以及中转→落地分别记录；同运营商/地区/时间窗、去回程、协议与地址族对照。跨洲国际多千兆、第三方公共探测点和真实用户家宽互不代证。实际任务需用户授权后才做采样，本次只保留方法。
5. **分开验证双栈。** 核IPv6来源是原生、转发、负载均衡还是仅link-local；分别确认路由、服务地区、DNS和客户端采用。统一出口或关闭的选择沿现有目标；检测不到公网IPv6不证明其他接口被禁用。
6. **先保管理再测性能。** 从最小负载开始，核内存/Swap/磁盘/流量预算；检测器OOM/限流/缺API数据时留失败，不能因最终JSON写ok就全过。必要时分时重测或用有界低内存参数，不把补测直接并回原负载。
7. **保持量纲和测试口径。** Mbps/MB/s/MiB/s/IOPS分开；记录块大小、QD、direct、顺序/随机、读写分离或混合、线程/时长。截图短测、CPU积分/突发与持续业务负载不同；单独读的峰值不能代表整盘/底层介质。
8. **交叉来源保留分歧。** IPData信任分方向与欺诈风险分相反；空字段保未知。地区/ASN/分类冲突按来源和时间记录，不合成纯净度；黑名单与已标记集合不同。脚本Yes、DNS解锁、API/Cloudflare可达与实际账号使用分别取证。
9. **验后再决定长期使用。** 同配置正常业务、适用故障与恢复、晚高峰及所需客户端分别有证据后再判断。出问题留原地址/配置和恢复材料，先定位来源或联系商家，不能把反复买机/换IP当必然有效修复。

## 历史证据与仍未经验证的效果

报告中的测速/跑分/路由截图属于作者历史局部样本，保留日期、机器/套餐/地址族和失败项；本次没有复测。相同2026-04横评图被多份报告重复使用，只算同一原始对照。曲线自述挑较差样本，部分图纵轴有重复/排版异常；没有原数据就不据图重新计算精确均值或置信区间。

作者星级、约90Mbps限速、先月付、偏某运营商/套餐的建议作为可选经验，不升级为默认。家宽标签能防封、Fresh IP零标记、某商家永远解锁、低风险分保证账号安全、单样本零丢包代表长期稳定，均没有在这些资料中得到证明。

报告原件的静态阅读已经完成；商家现价、当前库存、当前IP/网络、真实订单履约及账号结果仍需后续具体任务核实。这里不把“读完”改写成“实测通过”。


原件口径：本轮查看的是固定仓库实际分发的PDF。INDEX称字节不变，而sources/manifest.json注明Ghostscript压缩且部分original/distributed哈希不同；没有取得的压缩前原稿不冒算已读。文本层缺字时已对照整页图像，原图本身模糊的字段仍未知。
