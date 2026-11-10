# Claude 环境检测桌面端

独立桌面入口，界面参考 CCBaga 的分步操作方式，代码与品牌独立实现。macOS 13+ Apple Silicon 与 Windows x64 首发，内含检查引擎和两套 Skill，无需客户安装 Python。

## 客户使用

1. 打开应用，选择代理客户端导出的完整配置；填写实际用途、保留业务，选择已有节点。
2. 点击只读检查、准备方案。准备失败会显示原因，不能把节点订阅当成完整配置覆盖。
3. 确认具体方案后导出到新文件。导出不修改原配置、不自动启用或重启；有激活待核对项时先复制提示词，让 Codex 继续配置。
4. 通过客户端的正常入口导入，必要重启由客户手动完成。选择客户端实际导出的文件进行读回比对。
5. 查看已完成／未完成结果和下一步，打开本机材料目录取得报告、候选和备份。文件匹配不代表 DNS、真实出口或应用功能通过。

初次启动不自动采集、联网或启动 AI。点击“只读检查”才读取本机元数据。桌面端当前负责文件准备、确认导出和读回；系统 DNS／TUN／IPv6 的实际配置、原生导入与网络实测仍由内置 Skill 引导 Codex 在准确方案和授权下完成。不能仅凭导出文件、用户点击“已导入”或旧记录标记网络已完成。

配置、缓存备份和回执保存在本机。界面资源随包提供。浏览器检测和 Skill 更新核对各有独立的联网确认。

## 构建

开发依赖 Node.js 24+、Python 3.11+；依赖在任务环境中安装。

```sh
python -m pip install -r desktop/requirements-build.txt
npm ci --prefix desktop
python desktop/build_backend.py
npm test --prefix desktop
npm --prefix desktop exec electron-builder -- --mac zip --arm64
# Windows 原生执行：npm --prefix desktop exec electron-builder -- --win zip --x64
```

开发运行需先指定 `CLAUDE_KIT_PYTHON` 为已装项目依赖的 Python，再执行 `npm start --prefix desktop`。打包版自动使用自带引擎，不读取该开发变量。

首版构建未配置商业代码签名证书；不以关闭 Gatekeeper、SmartScreen 或公司策略的方式安装。受管理设备应由管理员审核。安装包能构建、合成测试通过，不代表真实客户代理、网络或系统权限已验收。

## 专项工具

| 入口 | 操作 |
| --- | --- |
| 需求访谈 | 逐项记录本轮事实并复制给 Codex |
| 浏览器 WebRTC / IPv6 | 从已选配置准备临时本机页面，复制链接到平时使用的浏览器资料，手动开始检测 |
| Claude 缓存隔离与恢复 | 选择 Claude Code 或 Desktop 的受支持目录，预览后确认隔离，通过「核对隔离状态」生成恢复依据 |
| Clash Verge Rev 域名规则 | macOS 2.5.8、2.5.10，读取策略组后预览、备份写入或恢复原规则 |
| 系统断线保护 | 选择已审阅的计划 JSON，生成供目标设备运行的交接包 |
| Linux 部署 | 选择已审阅的 Debian／Ubuntu 计划 JSON，生成离线执行包 |
| Skill 更新核对 | 选择已安装的本平台 Skill，读取 GitHub 固定提交并比较文件 |

Windows 缓存入口要求同一固定 NTFS 卷，并核对所选根和文件权限。登录、历史、配置、浏览器数据和卸载仍由适用 Skill 按用户选定范围处理。早期隔离记录的私有目录中保留恢复说明和原始材料。

内置后端提供 `--cli capabilities` 和 `--cli <具体命令> --help`。断线保护与 Linux 部署由用户在实际目标设备确认后运行。真实浏览器、管理员操作、防火墙和重启恢复尚待目标设备验收。
