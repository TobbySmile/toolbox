# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

# 1. 静态资源与引擎打包配置
datas = [
    ('assets', 'assets'),
]

binaries = []

# 全量收集 Flet 0.86.5 及其桌面端依赖组件
flet_datas, flet_binaries, flet_hidden = collect_all('flet')
flet_dt_datas, flet_dt_binaries, flet_dt_hidden = collect_all('flet_desktop')

datas += flet_datas + flet_dt_datas
binaries += flet_binaries + flet_dt_binaries

# 2. 隐式导入 (hiddenimports)
hiddenimports = (
    flet_hidden +
    flet_dt_hidden +
    collect_submodules('ui.flet_ui') +
    collect_submodules('tools') +
    [
        'flet_desktop',
        'fitz',
        'PIL',
        'PIL.Image',
        'yt_dlp',
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'fastapi',
        'aiofiles',
        'psutil',
    ]
)

block_cipher = None

a = Analysis(
    ['ui/flet_ui/main.py'],  # 更新后正确的入口路径
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6', 'pytest', 'unittest', 'numpy'],
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
    name='万象阁',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.ico'],
)