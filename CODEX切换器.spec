# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys


PROJECT_ROOT = Path(globals().get("SPECPATH", ".")).resolve()
SCRIPT_PATH = PROJECT_ROOT / "CODEX切换器.py"
SOURCE_INFO_PATH = PROJECT_ROOT / "source-info.json"
MAC_ICON_PATH = PROJECT_ROOT / "assets" / "icon-windowed.icns"


a = Analysis(
    [str(SCRIPT_PATH)],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[(str(SOURCE_INFO_PATH), ".")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe_kwargs = {
    "exclude_binaries": True,
    "name": "CODEX切换器",
    "debug": False,
    "bootloader_ignore_signals": False,
    "strip": False,
    "upx": True,
    "console": False,
    "disable_windowed_traceback": False,
}
if sys.platform == "darwin":
    exe_kwargs.update(
        {
            "argv_emulation": False,
            "codesign_identity": None,
            "entitlements_file": None,
        }
    )

exe = EXE(
    pyz,
    a.scripts,
    [],
    **exe_kwargs,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CODEX切换器",
)
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="CODEX切换器.app",
        icon=str(MAC_ICON_PATH),
        bundle_identifier="com.mini.codexswitcher",
    )
