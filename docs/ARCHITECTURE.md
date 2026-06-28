# 架构说明

## 入口

`CODEX切换器.py` 是 PyInstaller 主入口。启动时会配置 Tk 字体和缩放，然后导入 `codex_switcher_v2_app.App` 作为当前主界面。

`codex_switcher_v2_app.py` 负责主窗口布局、表单、按钮、弹窗和用户操作编排。核心配置读写、迁移、会话修复、CC Switch 互导逻辑放在 `CODEX切换器.py`，避免 UI 文件继续膨胀。

## 本地数据

- Codex 配置：`~/.codex/config.toml`
- Codex 鉴权：`~/.codex/auth.json`
- 本工具档案：`~/.codex/provider_profiles.json`
- CC Switch 数据库：`~/.cc-switch/cc-switch.db`
- CC Switch 导出备份：`~/.cc-switch/backups/codex-switcher-export/`

`provider_profiles.json` 当前 schema 包含：

- `settings.main_window_geometry`：主窗口上次关闭时的大小和位置。
- `official_snapshots`：官方登录快照元信息，敏感正文放进 macOS Keychain。
- `combo_profiles`：组合档案，支持纯官方、官方+中转、纯中转。
- `official_onboarding`：接入官方账号流程的临时状态。

## 窗口布局

主窗口默认约 `1120x700`。首次启动居中偏上；之后关闭窗口时保存 geometry，下次打开恢复。若外接屏变化导致坐标超出当前屏幕，会自动夹回屏幕内。

主界面用普通 `tk.Frame` 左右布局，不使用 `ttk.PanedWindow`。这是为了避开 macOS/Tk 下曾出现的绘制白屏问题。

## 切换模型

组合档案分三类：

- `official_only`：恢复某个官方账号快照。
- `official_plus_proxy`：保留官方登录态，并把目标 provider 的 `base_url` 和 bearer token 写入配置。
- `proxy_only`：写入第三方 Base URL 和 API Key。

切换时会同时处理 `auth.json` 和 `config.toml`，失败时回滚。会话桶位诊断不在启动时自动执行，只在用户打开“会话修复”时运行。

## CC Switch 互导

导入 CC Switch：

- 只读打开 `~/.cc-switch/cc-switch.db`。
- 读取 `providers` 中 `app_type='codex'` 的记录。
- 从 `settings_config.config` 提取 Codex TOML 的 `base_url`，从 `settings_config.auth` 提取 `OPENAI_API_KEY`。
- 导入为本工具的 `proxy_only` 档案。

导出到 CC Switch：

- 只允许导出本工具里的 `proxy_only` 档案。
- 写入前用 SQLite backup API 备份数据库。
- 对齐 CC Switch `save_provider` 的写法：事务写入 `providers`，再写 `provider_endpoints`。
- `settings_config` 使用 `{ "auth": {"OPENAI_API_KEY": ...}, "config": "..." }`。
- `meta` 写入 `commonConfigEnabled`、`endpointAutoSelect`、`apiFormat=openai_responses`。
- 重复判断按标准化 Base URL + API Key 比对。

## 打包

本地 macOS 打包使用：

```bash
/Users/mini/Desktop/codex项目/koutu_chatu_mac_app/mamba_env/bin/pyinstaller --noconfirm --clean CODEX切换器.spec
```

GitHub Actions 中，Windows 用 `actions/setup-python`，macOS 用 conda-forge Python/Tk。这样可以避免 macOS 系统 Tk 打包后白屏。
