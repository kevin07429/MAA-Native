# Official resource update / 官方资源更新

Updated (UTC): 2026-11-01T17:58:49+00:00

Upstream: MaaAssistantArknights/MaaAssistantArknights dev-v2 `296c32d7e8d75b648772a65c2db9ae77c26b8640`

Resource version: 2026-11-01 13:43:20.000

## Resource changes / 资源变更

- `a03ca9e6041e` fix: SwitchTheme 恢复未缩放原图，仅齿轮保留 v2 模板
- `b641572ad22d` feat: 支持活动通关后的双形态模板
- `b6885ea86a35` chore: Auto Templates Optimization
- `84771dcc8b41` fix: RA3 交付木材 8+ 正则表达式 (#18996)
- `ed4603ea92bd` chore: 添加 TL-4 搓玉关卡导航 (#18994)
- `c635d452edcb` feat(Minigame): 战时新闻委员会 (#18991)
- `3727f7d75800` chore: Auto Update Game Resources - 2026-11-01
- `914f90ca554f` chore: optimize templates
- `d8a98c72a456` Release v6.21.1 (#18987)

## Changed files / 变更文件

- `resource/global/YoStarEN/resource/tasks/RA/Reclamation3.json`
- `resource/global/YoStarJP/resource/tasks/RA/Reclamation3.json`
- `resource/global/YoStarKR/resource/tasks/RA/Reclamation3.json`
- `resource/tasks/MiniGame/WartimePressCommittee.json`
- `resource/tasks/RA/Reclamation3.json`
- `resource/tasks/Stages/TL.json`
- `resource/tasks/UiTheme/SwitchTheme.json`
- `resource/tasks/UiTheme/SwitchThemeByName.json`
- `resource/template/MiniGame/WartimePressCommittee/MiniGame@WartimePressCommittee@Max.png`
- `resource/template/MiniGame/WartimePressCommittee/MiniGame@WartimePressCommittee@MaxButton.png`
- `resource/template/MiniGame/WartimePressCommittee/MiniGame@WartimePressCommittee@NextPage.png`
- `resource/template/StageNavigation/SideStory/TL/TLChapterToTL2.png`
- `resource/template/UiTheme/SwitchTheme/SwitchTheme@CancelThemeChange-v2.png`
- `resource/template/UiTheme/SwitchTheme/SwitchTheme@CancelThemeChange.png`
- `resource/template/UiTheme/SwitchTheme/SwitchTheme@ChangeTheme-v2.png`
- `resource/template/UiTheme/SwitchTheme/SwitchTheme@ChangeTheme.png`
- `resource/template/UiTheme/SwitchTheme/SwitchTheme@ConfirmThemeChange-v2.png`
- `resource/template/UiTheme/SwitchTheme/SwitchTheme@ConfirmThemeChange.png`
- `resource/template/UiTheme/SwitchTheme/SwitchTheme@SelectLightTheme-v2.png`
- `resource/template/UiTheme/SwitchTheme/SwitchTheme@SelectLightTheme.png`
- `resource/template/UiTheme/SwitchTheme/SwitchTheme@ToggleSettingsMenu.png`
- `tools/OptimizeTemplates/optimize_templates.json`

## Program changes pending review / 待检查的程序变更

These program commits were not merged by the resource workflow. / 以下程序提交未由资源流程合入。

- `2454195aa5ed` ci: bump actions/setup-python from 6 to 7 in /.github/workflows in the github-actions group (#18947)
- `c635d452edcb` feat(Minigame): 战时新闻委员会 (#18991)
- `b33c819b1a15` fix: 战时新闻委员会本地化 key 补 TL 活动段
- `d9d220ea1b9f` docs: 更新 v6.21.1 更新日志
- `d8a98c72a456` Release v6.21.1 (#18987)
- `296c32d7e8d7` ci: 仅允许 base 为 dev-v2 的 PR 触发 ci action
