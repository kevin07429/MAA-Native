# MAA Native v6.21.4-native.14

自动同步官方 dev-v2 `5ef76046a02907b3a1b88682e9406cd2eb093f70`，保留手机适配、快速截图、后台控制与暂停/恢复。

## 本次官方提交

5ef76046a0 chore: Auto Update Game Resources - 2026-11-05
3badedda9b perf: OCR 大升级 (#18246)
d75bf9a42d fix(minigame): 环圣骏堡电车 ocr
c8d82e8308 chore: bump resource version
bbddd7f5e7 chore: YostarJP ocr fix (#19108)
a673d11384 chore: 优化全屏下的提示位置
3128241c83 chore: 繁中服剿滅入口截圖與補充基建彈窗文字 (#19097)
52d0b2acac Release v6.21.4 (#19096)
bcc1cde9c4 docs: 更新 v6.21.4 更新日志
c3a3117c49 chore: 增加 GitHub Token TooltipBlock 提示
440ee50666 chore: DragDrop.DoDragSourceMove 错误改为静默忽略
bfa590a032 feat: Android OCR ncnn 模型改为本地预转换入库 (#19088)
b8a65381a6 chore: 允许在连接设置后跳过教程
c05e80a311 Revert "docs: 更新 v6.21.4 更新日志"
80bcbd6fbd Revert "fix: 精简 WPF 设置指引并允许跳过 (#19084)"
2e13d67c9d Release v6.21.4 (#19086)
48d90ddcef docs: 更新 v6.21.4 更新日志
0e940011a9 fix: 精简 WPF 设置指引并允许跳过 (#19084)
dce8e808ec chore: 注释
f33217850e fix: GItHub Token 重复验证
6ff2f8bbe4 feat(ocr): 补齐 v6 ASCII 模型并修正识别字典标签 (#18812)
561e7f0715 feat: 更新 MaaDeps
78a9b73ae3 fix: 修复 webgpu 初始化问题
94405d5968 docs: 补充推理后端选择与实验性 WebGPU 的说明
dabbbdaa0c feat: 资源加载后预热 WebGPU 推理会话（实验性）
7812dce93d feat: wpf 与 core 支持推理后端选择及实验性 WebGPU 选项
24648364a3 feat: PaddleOCR 切换至新模型
4351f1816a feat: maacore 与 ncnn 支持 ppocr v6

完整包用于新安装；程序更新包由内置更新器使用，保留配置、数据、资源和壁纸。资源继续同步官方 MaaResource。

AGPL-3.0，非官方发行版。
