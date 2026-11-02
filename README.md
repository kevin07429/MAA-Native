# MAA Native

基于 [MAA](https://github.com/MaaAssistantArknights/MaaAssistantArknights) dev-v2 的非官方 Windows x64 手机适配版。

- 保留手机原生分辨率，游戏异形屏 UI 适配为 0；USB 与无线 ADB 使用内置快速截图通道。
- 自适应识别与点击、会客室线索和基建导航修复、当前任务暂停/恢复。
- 游戏资源直接同步官方 MaaAssistantArknights/MaaResource，资源重载时自动补回本地适配。

## 下载与使用

从 [Releases](https://github.com/kevin07429/MAA-Native/releases) 下载 `MAA-v...-win-x64.zip`，完整解压后运行 MAA.exe。
支持 Windows x64，自带 .NET。首次使用需要在手机上授权 USB / 无线调试，并设置连接地址。
设置页的 ｢检查并下载程序更新｣ 使用本仓库，｢更新资源｣ 使用官方资源源。首次游戏介绍需要先关闭。
程序不会因为下载完成而中断任务；应用程序更新会等待空闲并提示重启。

## 自动更新与发布

GitHub Actions 每 15 分钟检查官方 dev-v2；本仓库 native 分支的程序或资源变动在推送后立即触发。也可手动运行 [Auto Update and Publish MAA Native](https://github.com/kevin07429/MAA-Native/actions/workflows/auto-update-native.yml)。GitHub 定时任务可能排队延迟。

检测到更新后自动合并官方程序与资源，递增 native 版本，编译 Debug / Release 核心与 Windows x64 自包含界面，验证手机适配、暂停/恢复、更新协议及五个客户端的新旧资源兼容性。通过后提交源码并发布完整包、程序更新包与 SHA256 校验文件；上传校验通过才公开新版本。合并冲突或验证失败会停止发布，保留现有正式版。

每次发布生成 [更新清单](RESOURCE_UPDATES.md)。MAA 内置程序更新使用本仓库，游戏资源仍从官方 MaaResource 获取。原 ｢Sync Official Resources｣ 保留为手动资源同步工具。

English: GitHub checks upstream dev-v2 every 15 minutes and reacts immediately to app/resource pushes on native. Scheduled runs may be delayed. Conflict-free updates are merged and built, then must pass Debug native/pause checks, update protocol tests and five-client current/previous resource compatibility checks before publishing complete and program-update ZIPs with verified SHA256 digests. Failed merges or checks preserve the current public release. The client keeps using official MaaResource for game resources.

## 构建

GUI 使用 `dotnet publish -r win-x64 --self-contained true -p:DisableBeauty=True`，核心使用 CMake / Visual Studio 2026。核心版本参数为 `-DNATIVE_APP_VERSION=v6.21.0-native.N`，GUI InformationalVersion 必须一致。
构建与打包脚本位于 `.github/scripts/build-native.ps1` 和 `tools/native-release/`。手机端截图组件源码位于 `tools/wireless-native/MaaNativeCap.java`。
资源和常规配置仍沿用上游格式。修改代码时遵守 AGENTS.md。

## 验证范围

使用ViVO、IQOO、RedMi、XiaoMi等设备进行了测试，目前没有发现问题

## 许可证

AGPL-3.0，见 LICENSE。保留上游版权和许可证。本项目不是 MAA 官方发行渠道。

English: This unofficial native-resolution Windows x64 phone edition tracks official dev-v2. Native capture, layout adaptation, background debugging, and pause/resume are retained. App updates are fetched only from this repository; game resources remain on the official MaaResource channel. Releases include complete source through the corresponding Git tag. Personal configuration and logs are never part of public packages.
