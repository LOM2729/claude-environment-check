# Claude 环境检测桌面端

独立桌面入口，界面参考 CCBaga 的分步操作方式，代码与品牌独立实现。macOS 13+ Apple Silicon 与 Windows x64 首发，内含检查引擎和两套 Skill，无需客户安装 Python。

## 客户使用

1. 打开应用，选择代理客户端导出的完整配置；填写实际用途、保留业务，选择已有节点。
2. 点击只读检查、准备方案。准备失败会显示原因，不能把节点订阅当成完整配置覆盖。
3. 确认具体方案后导出到新文件。导出不修改原配置、不自动启用或重启；有激活待核对项时先复制提示词，让 Codex 继续配置。
4. 通过客户端的正常入口导入，必要重启由客户手动完成。选择客户端实际导出的文件进行读回比对。
5. 查看已完成／未完成结果和下一步，打开本机材料目录取得报告、候选和备份。文件匹配不代表 DNS、真实出口或应用功能通过。

初次启动不自动采集、联网或启动 AI。点击“只读检查”才读取本机元数据。桌面端当前负责文件准备、确认导出和读回；系统 DNS／TUN／IPv6 的实际配置、原生导入与网络实测仍由内置 Skill 引导 Codex 在准确方案和授权下完成。不能仅凭导出文件、用户点击“已导入”或旧记录标记网络已完成。

数据只留本机。界面不加载外部网页、CDN 或遥测；不会修改现有 Claude／Codex 图标、启动方式或安装后台守卫。

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
