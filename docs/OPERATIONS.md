# 运维与发布

## 本机验证

```bash
/Users/mini/Desktop/codex项目/koutu_chatu_mac_app/mamba_env/bin/python -m py_compile CODEX切换器.py codex_switcher_v2_app.py CODEX切换器.spec
git diff --check
```

检查 CC Switch 导出逻辑时，优先复制数据库到临时目录测试，不要直接写真实 `~/.cc-switch/cc-switch.db`。

## 本机打包

```bash
/Users/mini/Desktop/codex项目/koutu_chatu_mac_app/mamba_env/bin/pyinstaller --noconfirm --clean CODEX切换器.spec
```

输出：

- `dist/CODEX切换器.app`
- `dist/CODEX切换器/`

Mac 新手类比：`dist/` 类似 Windows 打包工具输出目录，`.app` 类似一个程序文件夹。

## 替换本机 App

正式 App 路径：

```text
/Applications/自己做的/CODEX切换器.app
```

替换前先备份旧包，例如：

```bash
mv "/Applications/自己做的/CODEX切换器.app" "/Applications/自己做的/CODEX切换器.app.backup-$(date +%Y%m%d-%H%M%S)"
ditto "dist/CODEX切换器.app" "/Applications/自己做的/CODEX切换器.app"
xattr -dr com.apple.quarantine "/Applications/自己做的/CODEX切换器.app" 2>/dev/null || true
```

## 生成本地 zip

```bash
mkdir -p outputs
ditto -c -k --sequesterRsrc --keepParent "/Applications/自己做的/CODEX切换器.app" "outputs/CODEX切换器-latest-macos.zip"
```

`outputs/` 是本地交付物目录，已忽略，不提交。

## GitHub 发布

推送 `main` 会触发 `Build Desktop Packages`。打 `v*` 标签会触发 `Release Desktop Packages` 并上传：

- `codex-switch-macos.zip`
- `codex-switch-windows.zip`

常用流程：

```bash
git add <files>
git commit -m "<message>"
git push origin main
git tag vX.Y.Z
git push origin vX.Y.Z
```

## 排障

### macOS 打开白屏

优先确认是不是用系统 Python/Tk 打包。解决方式是用 conda/mamba 的 Python/Tk 重新打包，并确认 GitHub macOS workflow 仍使用 conda-forge。

### 启动卡顿

启动时不应自动跑 `analyze_session_health()`。会话检查只能由用户点击“会话修复”触发。

### 新装 Codex 打不开

当前版本启动时会自动补最小 `~/.codex/config.toml` 和 `~/.codex/auth.json`。如果用户反馈 fresh install 仍打不开，优先检查：

- `~/.codex/` 是否可写。
- `provider_profiles.json` 是否损坏；损坏时程序会自动备份成 `provider_profiles.invalid-时间戳.json`。
- 是否有安全软件或权限限制阻止写入用户目录。

### CC Switch 导出后没显示

先重启 CC Switch。导出只写数据库，不控制 CC Switch 前端刷新。

### CC Switch 数据库写入失败

检查：

- `~/.cc-switch/cc-switch.db` 是否存在。
- CC Switch 是否正在迁移数据库。
- 是否能在 `~/.cc-switch/backups/codex-switcher-export/` 看到导出前备份。
- 失败后优先用备份恢复，不要手工改生产库。
