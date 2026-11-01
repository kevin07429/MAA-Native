# MAA Native

基于 [MAA](https://github.com/MaaAssistantArknights/MaaAssistantArknights) dev-v2（v6.21.0-beta.3 后，`110c5ffc`）的非官方 Windows x64 手机适配版。

- 保留手机原生分辨率，游戏异形屏 UI 适配为 0；USB 与无线 ADB 使用内置快速截图通道。
- 自适应识别与点击、会客室线索和基建导航修复、当前任务暂停/恢复。
- 游戏资源直接同步官方 MaaAssistantArknights/MaaResource，资源重载时自动补回本地适配。

## 下载与使用

从 [Releases](https://github.com/kevin07429/MAA-Native/releases) 下载 `MAA-v...-win-x64.zip`，完整解压后运行 MAA.exe。
支持 Windows x64，自带 .NET。首次使用需要在手机上授权 USB / 无线调试，并设置连接地址。
设置页的 ｢检查并下载程序更新｣ 使用本仓库，｢更新资源｣ 使用官方资源源。首次游戏介绍需要先关闭。
程序不会因为下载完成而中断任务；应用程序更新会等待空闲并提示重启。

## 自动同步官方资源

仓库每 6 小时检查官方 dev-v2，也可在 Actions 手动运行 ｢Sync Official Resources｣。仅合并 `resource/` 与模板优化清单，先做三方合并、JSON 检查、当前手机适配版构建及 Debug 资源加载验证，通过后才提交到 native 分支。没有变化时跳过构建；冲突或验证失败时不提交，不强制覆盖。

每次同步生成 [资源变更清单](RESOURCE_UPDATES.md)，列出资源版本、提交、文件与待检查的程序提交。程序代码和工作流不会被自动合并；有程序变更时仍需人工检查与发版。MAA 客户端继续从官方 MaaResource 更新资源，这个流程不自动发布程序安装包。

English: ｢Sync Official Resources｣ checks upstream dev-v2 every six hours. Only game resources and the template optimization manifest are merged. Three-way conflicts and validation failures block commits. Changes must pass native build and Debug resource checks before a normal push. RESOURCE_UPDATES.md records the changes and program commits requiring review. This workflow does not merge program code or publish app releases; the client keeps using official MaaResource.

## 构建

GUI 使用 `dotnet publish -r win-x64 --self-contained true -p:DisableBeauty=True`，核心使用 CMake / Visual Studio 2026。核心版本参数为 `-DNATIVE_APP_VERSION=v6.21.0-native.N`，GUI InformationalVersion 必须一致。
构建与打包脚本位于 `.github/scripts/build-native.ps1` 和 `tools/native-release/`。手机端截图组件源码位于 `tools/wireless-native/MaaNativeCap.java`。
资源和常规配置仍沿用上游格式。修改代码时遵守 AGENTS.md。

## 验证范围

使用ViVO、IQOO、RedMi、XiaoMi等设备进行了测试，目前没有发现问题

## 许可证

AGPL-3.0，见 LICENSE。保留上游版权和许可证。本项目不是 MAA 官方发行渠道。

English: native.4 merges all 127 upstream commits through 110c5ffc (dev-v2, after v6.21.0-beta.3), including infrastructure speed improvements, Roguelike fixes, inventory corrections, and Reclamation moving to the toolbox. Native capture, layout adaptation, background debugging, and pause/resume are retained. This is an unofficial native-resolution Windows x64 phone edition of MAA. App updates are fetched only from this repository; game resources remain on the official MaaResource channel. Releases include complete source through the corresponding Git tag. Personal configuration and logs are never part of public packages.
