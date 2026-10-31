# MAA Native

基于 [MAA](https://github.com/MaaAssistantArknights/MaaAssistantArknights) dev-v2（v6.21.0-beta.3 后，`110c5ffc`）的非官方 Windows x64 手机适配版。

- 保留手机原生分辨率，游戏异形屏 UI 适配为 0；USB 与无线 ADB 使用内置快速截图通道。
- 自适应识别与点击、会客室线索和基建导航修复、当前任务暂停/恢复。
- 程序更新仅使用本仓库的 Releases，校验 SHA256 后注册程序更新；配置、数据、缓存和资源目录保留。
- 游戏资源直接同步官方 MaaAssistantArknights/MaaResource，资源重载时自动补回本地适配。
- 调试使用当前用户专用后台接口，不操作桌面鼠标或键盘。

## 本次同步

v6.21.0-native.4 合并官方 127 个提交，包含基建选人提速与识别修复、肉鸽分队确认和点击修复、库存计算调整，以及生息演算迁移到工具箱。手机原生分辨率适配、内置快速截图、后台调试和任务暂停/恢复保留。

## 下载与使用

从 [Releases](https://github.com/kevin07429/MAA-Native/releases) 下载 `MAA-v...-win-x64.zip`，完整解压后运行 MAA.exe。
支持 Windows x64，自带 .NET。首次使用需要在手机上授权 USB / 无线调试，并设置连接地址。
设置页的 ｢检查并下载程序更新｣ 使用本仓库，｢更新资源｣ 使用官方资源源。首次游戏介绍需要先关闭。
程序不会因为下载完成而中断任务；应用程序更新会等待空闲并提示重启。

## 发布新版本

在 Actions 中运行 ｢Publish MAA Native｣，填写版本号，例如 `v6.21.0-native.5`。发布流程从当前源码编译自包含 GUI、核心与更新器，生成完整包、程序更新包及 SHA256。
也可以推送同样格式的标签，由 Release Pipeline 调用相同构建流程。
请先确认本次核心变更通过 Debug 验证；不要把个人 config、data、debug、cache 或 ADB 私钥提交到仓库。

## 构建

GUI 使用 `dotnet publish -r win-x64 --self-contained true -p:DisableBeauty=True`，核心使用 CMake / Visual Studio 2026。核心版本参数为 `-DNATIVE_APP_VERSION=v6.21.0-native.N`，GUI InformationalVersion 必须一致。
构建与打包脚本位于 `.github/scripts/build-native.ps1` 和 `tools/native-release/`。手机端截图组件源码位于 `tools/wireless-native/MaaNativeCap.java`。
资源和常规配置仍沿用上游格式。修改代码时遵守 AGENTS.md。

## 验证范围

本机实测为原生横屏 2772×1280，UI 适配 0，USB 及无线 ADB。已验证部分基建设施、会客室线索、暂停/恢复和界园事件，并做过不同尺寸的截图回放。
这些记录不代表所有手机、主题、关卡和事件都已实测。首次介绍窗口、其他设备的 UI 布局仍需实际验证。

## 许可证

AGPL-3.0，见 LICENSE。保留上游版权和许可证。本项目不是 MAA 官方发行渠道。

English: native.4 merges all 127 upstream commits through 110c5ffc (dev-v2, after v6.21.0-beta.3), including infrastructure speed improvements, Roguelike fixes, inventory corrections, and Reclamation moving to the toolbox. Native capture, layout adaptation, background debugging, and pause/resume are retained. This is an unofficial native-resolution Windows x64 phone edition of MAA. App updates are fetched only from this repository; game resources remain on the official MaaResource channel. Releases include complete source through the corresponding Git tag. Personal configuration and logs are never part of public packages.
