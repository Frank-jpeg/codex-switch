# CODEX切换器

一个给本地 Codex 配置做可视化切换、会话诊断/修复、CC Switch 配置互导的小工具。

## 立即下载

[![下载 Windows 版](https://img.shields.io/badge/Download-Windows-blue?style=for-the-badge)](https://github.com/Frank-jpeg/codex-switch/releases/latest/download/codex-switch-windows.zip)
[![下载 macOS 版](https://img.shields.io/badge/Download-macOS-black?style=for-the-badge)](https://github.com/Frank-jpeg/codex-switch/releases/latest/download/codex-switch-macos.zip)
[![查看全部版本](https://img.shields.io/badge/Releases-View%20All-success?style=for-the-badge)](https://github.com/Frank-jpeg/codex-switch/releases)

- Windows 直接下载：[`codex-switch-windows.zip`](https://github.com/Frank-jpeg/codex-switch/releases/latest/download/codex-switch-windows.zip)
- macOS 直接下载：[`codex-switch-macos.zip`](https://github.com/Frank-jpeg/codex-switch/releases/latest/download/codex-switch-macos.zip)
- 全部版本列表：[`Releases`](https://github.com/Frank-jpeg/codex-switch/releases)

如果下载链接一时打不开，通常是最新 `Release` 还在生成，等几十秒刷新就行。

## 现在能做什么

- 组合档案切换：纯官方 / 官方+中转 / 纯中转
- 官方账号快照保存与恢复
- 会话桶位诊断、异常摘要、可视化修复
- 从 CC Switch 导入 Codex 线路
- 将本工具里的纯中转档案导出到 CC Switch
- 记住主窗口上次关闭时的位置和大小
- 新装 Codex 时自动补齐最小 `config.toml` / `auth.json`，避免首启打不开

更多实现和运维细节见：

- [架构说明](./docs/ARCHITECTURE.md)
- [运维与发布](./docs/OPERATIONS.md)

## 本地运行

```bash
python3 CODEX切换器.py
```

如果你是从 Windows 转到 Mac，可以把它理解成：

- `python3 xxx.py` 类似 Windows 里双击开发版脚本启动
- `.app` 类似 Windows 的打包版程序
- 首次自动生成 `~/.codex/config.toml` / `auth.json`，类似很多 Windows 软件第一次启动先写默认 `ini/json`

## 本地打包

macOS：

```bash
/Users/mini/Desktop/codex项目/koutu_chatu_mac_app/mamba_env/bin/pyinstaller --noconfirm --clean CODEX切换器.spec
```

本机 macOS 打包建议使用上面的 mamba/conda Python 环境，避免系统 Tk 打包后出现白屏。产物默认在 `dist/` 下，和 Windows 里常见的 `dist` 输出目录是一个意思。

## 下载方式

最方便的下载入口是仓库右侧或上方的 `Releases`：

- `Windows`：下载 `codex-switch-windows.zip`
- `macOS`：下载 `codex-switch-macos.zip`

如果只是临时测试，也可以去 `Actions` 下载构建产物。

## 自动打包

仓库内已提供 GitHub Actions 工作流：

- 推送到 `main` 会自动构建 `Windows` 和 `macOS` 包
- 也可以在 GitHub 的 `Actions` 页面手动点 `Build Desktop Packages`
- 打 `v*` 标签时会自动创建 `Release` 并附带下载包
- GitHub macOS 构建使用 conda-forge Python/Tk，避免系统 Tk 白屏问题

这相当于把“本机打包 EXE / APP”改成“GitHub 云端帮你打包”，你在 Mac 上也能产出 Windows 版本。

## CC Switch 互导说明

- `导入 CC`：只读取 `~/.cc-switch/cc-switch.db`，把可识别的 Codex API 线路导入为“纯中转”档案。
- `导出到 CC`：只导出本工具里的“纯中转”档案；官方登录和官方+中转不会导出，避免搬运登录态。
- 导出前会自动备份 CC Switch 数据库到 `~/.cc-switch/backups/codex-switcher-export/`。
- 如果导出后 CC Switch 没有立刻显示，重启 CC Switch 即可。

## macOS 提示

GitHub 产出的 `.app` 默认没有 Apple 签名。

这和 Windows 里“第一次运行未知发布者 EXE 会弹提醒”很像：

- Mac 可能提示应用来自未验证开发者
- 需要在“系统设置 -> 隐私与安全性”里允许一次

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
