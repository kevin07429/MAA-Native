# MAA Native v6.22.0-native.23

自动同步官方 dev-v2 `201cbb73e7505884f61027b06294ecf049c670c7`，保留手机适配、快速截图、后台控制与暂停/恢复。

## 本次官方提交

201cbb73e7 fix: 限時簽到第 10 天認不到 LOGIN 而沒領取
7f297d651d fix: 肉鸽飞三层关闭投资时第二层也直飞 (#19243)
96c2c4eee7 fix: 修改任务列表时检查是否处于运行中
35ed335cfe fix: 修复 stream() 路径 rotate() 未持锁导致的多线程日志轮转竞态闪退 (#19240)
9fa68456de fix: 自动战斗关卡识别 `Operation` 识别为 `Dperation`
3ace5808af chore: bump resource version
d8e5e8c28b fix: 锏ocrReplace
8f25d1e35e feat(mac): WebGPU 推理后端 (#19222)
bd8a2439ab fix: 关卡详细信息-关卡名OCR后缀 `*`
64cc141477 chore: Auto Templates Optimization
180444b737 fix: KR add missing Silent Chapter template for IS2
dafac2c217 chore: Auto update by pre-commit hooks https://github.com/MaaAssistantArknights/MaaAssistantArknights/actions/runs/42698716992 [skip changelog]
901e01c600 Release v6.22.0 (#19199)
c33d228870 docs: 更新 v6.22.0 更新日志
1d5d0402e1 chore: 干员列表排除”狂躁铁皮“
5fd2b068bb Merge commit from fork
35367384b6 fix: 模板优化脚本改用 subprocess 参数列表, 消除文件名 shell 命令注入
df9aad3999 fix: 卫戍协议提示补充需要使用默认皮肤
9bcc9388a1 fix: ClickedCorrectStage roi 过大, 导致关卡名 OCR 错误 (#19195)
9cc729dfb4 fix: ClickedCorrectStage roi过大, 导致关卡名OCR错误
0f4dcb2c23 Revert "fix: 关卡名确认 roi 缩窄移入 base，全客户端生效 (#19188)"
96261a66b6 fix: TaskQueue 非全部任务开始时, 任务状态可能未被设为跳过
4fe298b5f9 chore: bump resource version
fbe41a7537 fix: 繁中孑ocrReplace
3cc51fd52f fix: 一键长草开始时传入任务列表副本
fd6e693712 fix: `has_multi_stages` rename to `has_multi_phases`

完整包用于新安装；程序更新包由内置更新器使用，保留配置、数据、资源和壁纸。资源继续同步官方 MaaResource。

AGPL-3.0，非官方发行版。
