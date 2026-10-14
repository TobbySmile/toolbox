# tools/utils/paths.py
#
# 解决"打包成单文件 exe 后，用户导入的 Cookie / 改过的设置，重启就没了"
# 这个问题的核心工具函数。
#
# 背景（为什么原来 `PROJECT_ROOT / "config"` 这种写法在打包后会出问题）：
# 之前 config/settings.json、config/cookies/ 的路径都是用
# `Path(__file__).resolve().parent.parent.parent` 相对源码文件位置算出来的。
# 开发环境下这样没问题，但用 PyInstaller `--onefile` 打包成单文件 exe 后：
#   - 每次运行 exe，PyInstaller 会先把打包进去的所有文件解压到一个
#     系统临时目录（Windows 下是 %TEMP%\_MEIxxxxxx），`__file__` 在运行时
#     指向的其实是这个临时目录里的副本
#   - 这个临时目录在程序退出后通常会被清理掉，下次启动会解压出一份全新的
#   - 也就是说，如果 config/settings.json、config/cookies/ 还是相对
#     `__file__` 算路径，用户这次导入的 Cookie、改的主题设置，
#     下次打开程序就会消失——因为写入的其实是"临时目录里的一次性副本"，
#     不是真正持久化的位置
#
# 解决方式：跟用户可变数据（设置、Cookie）相关的路径，一律不要用相对
# `__file__` 的路径，改成系统级的"用户数据目录"：
#   Windows: %APPDATA%\万象阁\
#   macOS:   ~/Library/Application Support/万象阁/
#   Linux:   $XDG_CONFIG_HOME/万象阁/ 或 ~/.config/万象阁/
# 这个目录不受 PyInstaller 临时解压目录的生命周期影响，天然持久化，
# 也是桌面应用的标准做法。
#
# 注意：这个函数只用于"用户会修改的数据"（settings.json、cookies/）。
# 像自带的 FFmpeg 二进制（assets/ffmpeg/bin/）这种"只读、随程序一起分发
# 的静态资源"不受这个问题影响，该怎么找还怎么找（见 tools/utils/ffmpeg.py
# 里的 FLET_ASSETS_DIR / PyInstaller 场景的资源路径解析，是另一套逻辑）。

import os
import sys
from pathlib import Path

APP_NAME = "万象阁"

# 开发环境下的项目根目录（相对本文件位置往上找三层：utils -> tools -> 项目根）
_DEV_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包后的环境里。
    PyInstaller 会自动给 sys 模块加上 frozen=True 这个标记，
    这是官方文档推荐的检测方式。"""
    return getattr(sys, "frozen", False)


def get_user_data_dir() -> Path:
    """
    返回一个持久化的、不会因为单文件 exe 每次重新解压临时目录而丢失的
    用户数据目录。目录及其常用子目录（cookies/）会被自动创建好。

    开发环境（直接跑源码）：仍然用项目根目录下的 config/，
    方便开发时直接在文件管理器里看到、方便调试，行为跟以前完全一样。

    打包后（sys.frozen 为 True）：改用系统级用户数据目录，
    跟 exe 本身、跟 PyInstaller 的临时解压目录完全无关，
    用户导入的 Cookie、改过的设置会一直保留到下次打开。
    """
    if is_frozen():
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", str(Path.home())))
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        data_dir = base / APP_NAME
    else:
        data_dir = _DEV_PROJECT_ROOT / "config"

    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "cookies").mkdir(parents=True, exist_ok=True)
    return data_dir


def get_settings_path() -> Path:
    return get_user_data_dir() / "settings.json"


def get_cookies_dir() -> Path:
    return get_user_data_dir() / "cookies"


def get_assets_dir() -> Path:
    """
    返回 assets/ 目录（图标、自带 FFmpeg 等静态资源）的绝对路径。

    跟 get_user_data_dir() 不同：这里存的是"只读、随程序一起打包分发"的
    静态资源，不是用户会修改的数据，所以不需要迁移到 APPDATA，
    直接找程序自带的那份就行。

    开发环境：项目根目录下的 assets/
    打包后（PyInstaller）：优先用 sys._MEIPASS（--onefile 解压出来的临时
        目录），这是 ui/flet_ui/main.py 已经用 PyInstaller 实测验证过的
        路径解析方式；如果某些打包方式没有 _MEIPASS（比如 --onedir），
        退回 exe 所在目录。

    PySide6 的 UI 层（窗口图标、首页图标等）应该统一用这个函数，
    不要自己用 __file__ 现算项目路径——那种算法在 PyInstaller 打包后
    会指向临时解压目录，跟 config/settings.json 曾经踩过的坑是同一类问题。
    """
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass) / "assets"
        return Path(sys.executable).resolve().parent / "assets"
    return _DEV_PROJECT_ROOT / "assets"
