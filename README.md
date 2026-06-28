# CODEX切换器

一个给本地 Codex 配置做可视化切换和会话诊断/修复的小工具。

## 现在能做什么

- 组合档案切换：纯官方 / 官方+中转 / 纯中转
- 官方账号快照保存与恢复
- 会话桶位诊断、异常摘要、可视化修复
- 导入部分 CC Switch 线路配置

## 本地运行

```bash
python3 CODEX切换器.py
```

如果你是从 Windows 转到 Mac，可以把它理解成：

- `python3 xxx.py` 类似 Windows 里双击开发版脚本启动
- `.app` 类似 Windows 的打包版程序

## 本地打包

macOS：

```bash
python3 -m pip install pyinstaller
python3 -m PyInstaller CODEX切换器.spec
```

产物默认在 `dist/` 下，和 Windows 里常见的 `dist` 输出目录是一个意思。

## Windows EXE

仓库内已提供 GitHub Actions 工作流：

- 推送到 `main` 会自动构建一次
- 也可以在 GitHub 的 `Actions` 页面手动点 `Build Windows EXE`
- 构建完成后，到 `Artifacts` 下载 `codex-switch-windows.zip`

这相当于把“本机打包 EXE”改成“GitHub 云端帮你打包 EXE”，你在 Mac 上也能出 Windows 版本。

## 参考与致谢

- 配置切换兼容性思路参考了 [CCSwitch](https://github.com/farion1231/cc-switch)
- 会话诊断/修复的交互思路参考了 [CodexPlusPlus](https://github.com/BigPizzaV3/CodexPlusPlus)
- 详细说明见 [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)

截至 2026-06-28：

- `CCSwitch` 仓库公开标注为 `MIT`
- `CodexPlusPlus` 的 GitHub 仓库元数据未显示 SPDX license，因此本仓库不直接附带其源代码

## 说明

当前仓库还没有单独附带你自己的开源许可证文件。

这意味着：

- 仓库可以公开
- 但默认不是“别人可随便复用”的开源授权状态

如果你后面想明确开源，我建议再补一个 `LICENSE`。
