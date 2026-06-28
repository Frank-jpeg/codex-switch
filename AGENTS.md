# AGENTS.md

## 项目速查

- 源码入口：`CODEX切换器.py`；当前主界面：`codex_switcher_v2_app.py`。
- 打包配置：`CODEX切换器.spec`；源码指路：`source-info.json`。
- 细节文档：`docs/ARCHITECTURE.md`、`docs/OPERATIONS.md`。
- 发布产物是 `.app` / zip，不要把 `.app` 当源码目录改。

## 红线

- macOS 打包必须用 conda/mamba Python/Tk，避免系统 Tk 白屏。
- 启动时不要自动跑全量会话扫描；会话修复必须由用户手动打开。
- 替换 `/Applications/自己做的/CODEX切换器.app` 前先备份旧 `.app`。
- 导出到 CC Switch 前必须备份 `~/.cc-switch/cc-switch.db`。
- 官方登录/官方+中转档案不要导出到 CC Switch，避免复制登录态。
- `outputs/`、`build/`、`dist/` 是生成物，不提交。

## 命令

```bash
/Users/mini/Desktop/codex项目/koutu_chatu_mac_app/mamba_env/bin/python -m py_compile CODEX切换器.py codex_switcher_v2_app.py CODEX切换器.spec
/Users/mini/Desktop/codex项目/koutu_chatu_mac_app/mamba_env/bin/pyinstaller --noconfirm --clean CODEX切换器.spec
```

## 发布

本机打包和冒烟测试后替换 `/Applications/自己做的/CODEX切换器.app`，生成 `outputs/CODEX切换器-latest-macos.zip`。公开新版下载时推送 `main` 并打 `v*` 标签。
