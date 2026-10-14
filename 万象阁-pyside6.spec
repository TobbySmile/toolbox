# -*- mode: python ; coding: utf-8 -*-
#
# 万象阁-pyside6.spec
#
# PySide6 独立打包配置，跟 万象阁-flet.spec 是两个完全独立的 spec，
# 分别打包各自的 UI，不共用依赖收集规则——这是 2026.08.16 工作记录里明确
# 定下的原则："不要让 Flet spec 与 PySide6 spec 共用收集规则"。
#
# 用法：
#   pyinstaller 万象阁-pyside6.spec
#
# 产物在 dist/万象阁-pyside6.exe（--onefile）下。
#

from pathlib import Path

block_cipher = None

PROJECT_ROOT = Path(SPECPATH).resolve()

# ----------------------------------------------------------------
# 数据文件：只打包 PySide6 UI 实际会用到的静态资源
#   - assets/icon.ico / icon.png：窗口图标、首页图标
#   - assets/ffmpeg/bin/：自带 FFmpeg，见 tools/utils/ffmpeg.py 的路径解析
#
# 注意：不要把 config/cookies/ 打进去——那是开发者本机的 Cookie，
# 打包给别人用的话，config/ 下的用户数据应该是空的，让对方自己在
# 设置页导入（详见 tools/utils/paths.py + tools/utils/cookie.py 的说明）。
# ----------------------------------------------------------------
datas = [
    (str(PROJECT_ROOT / "assets" / "icon.ico"), "assets"),
    (str(PROJECT_ROOT / "assets" / "icon.png"), "assets"),
    (str(PROJECT_ROOT / "assets" / "ffmpeg" / "bin"), "assets/ffmpeg/bin"),
]

# ----------------------------------------------------------------
# 隐藏导入：PyInstaller 静态分析有时找不到的动态导入模块
# ----------------------------------------------------------------
hidden_imports = [
    "yt_dlp",
    "qrcode",
    "uvicorn.lifespan.on",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "fitz",  # PyMuPDF，tools/pdf/* 用
]

a = Analysis(
    [str(PROJECT_ROOT / "ui" / "pyside6" / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 只收集 PySide6 这一套 UI 的子模块，不要收集整个 ui/，
    # 避免把 ui/flet_ui/ 和 flet 依赖一起打进来
    excludes=["flet", "flet_desktop", "ui.flet_ui"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="万象阁-pyside6",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI 程序不弹控制台窗口；对应 ui/pyside6/main.py 里
                     # 那段 sys.stdout is None 的兜底就是专门为这个模式写的
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "assets" / "icon.ico"),
)