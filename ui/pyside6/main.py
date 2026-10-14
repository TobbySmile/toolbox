# ui/pyside6/main.py
#
# PySide6 桌面应用入口（GUI 第二套实现，Flet 版本在 ui/flet_ui/ 下）。
# 原来叫 app.py，改名 main.py 是为了跟 ui/flet_ui/main.py 保持对称的入口命名，
# 后续 PyInstaller 打包（万象阁-pyside6.spec）也是指向这个文件。
#
# v3 变更（这轮 PyInstaller 打包排查带来的修复）：
#   1. 【关键】无控制台模式下 stdout/stderr 为 None 的兜底
#      PyInstaller 用 console=False 打包 GUI 程序时，Windows 下
#      sys.stdout / sys.stderr 可能直接是 None（没有控制台窗口可写）。
#      tools/utils/ffmpeg.py 的 run_ffmpeg() 默认会往 sys.stdout 打印
#      任务日志和进度百分比，如果不提前处理，第一次跑任何媒体处理任务
#      就会直接崩在 'NoneType' object has no attribute 'write' 上。
#      这个问题 Flet 版本在 ui/flet_ui/main.py 里已经踩过并修好了，
#      PySide6 用的是同一个 tools/utils/ffmpeg.py，必须在入口这里
#      做一模一样的兜底，不能假设"两套 UI 各自处理"。
#   2. 窗口/任务栏图标、首页图标的路径解析统一改用
#      tools.utils.paths.get_assets_dir()，不再自己用 __file__ 现算——
#      那种算法在 PyInstaller 打包后会指向临时解压目录，是
#      config/settings.json 曾经踩过的同一类坑（详见 tools/utils/paths.py）

import os
import sys

if getattr(sys, "frozen", False):
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

import json

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout,
    QListWidget, QListWidgetItem, QStackedWidget,
)

from tools.utils.paths import get_settings_path, get_assets_dir
from ui.pyside6.theme import apply_theme_mode, APP_FONT_FAMILY
from ui.pyside6.views.home_view import HomeView
from ui.pyside6.views.download_view import DownloadView
from ui.pyside6.views.media_view import MediaView
from ui.pyside6.views.document_view import DocumentView
from ui.pyside6.views.utility_view import UtilityView
from ui.pyside6.views.transfer_view import TransferView
from ui.pyside6.views.settings_view import SettingsView

ICON_PATH = get_assets_dir() / "icon.ico"

NAV_ITEMS = [
    ("🏠", "首页"),
    ("⬇️", "下载"),
    ("🎬", "媒体"),
    ("📄", "文档"),
    ("🛠️", "工具"),
    ("⚡", "传送"),
    ("⚙️", "设置"),
]


def _load_theme_mode() -> str:
    """启动时读取用户上次选择的外观模式，跟设置页共用同一个持久化路径"""
    try:
        data = json.loads(get_settings_path().read_text(encoding="utf-8"))
        return data.get("appearance", {}).get("theme_mode", "system")
    except Exception:
        return "system"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("万象阁")
        self.resize(1000, 700)
        self.setMinimumSize(900, 600)

        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(96)
        self.nav_list.setIconSize(QSize(22, 22))
        self.nav_list.setStyleSheet("""
            QListWidget { border: none; border-right: 1px solid palette(mid); padding-top: 8px; background: palette(window); }
            QListWidget::item { padding: 12px 4px; text-align: center; border-radius: 8px; margin: 2px 6px; }
            QListWidget::item:selected { background: rgba(37, 99, 235, 0.16); color: palette(text); }
            QListWidget::item:hover:!selected { background: rgba(37, 99, 235, 0.06); }
        """)
        for icon, label in NAV_ITEMS:
            item = QListWidgetItem(f"{icon}\n{label}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.nav_list.addItem(item)

        self.stack = QStackedWidget()
        self.stack.addWidget(HomeView())
        self.stack.addWidget(DownloadView())
        self.stack.addWidget(MediaView())
        self.stack.addWidget(DocumentView())
        self.stack.addWidget(UtilityView())
        self.stack.addWidget(TransferView())
        self.stack.addWidget(SettingsView())

        self.nav_list.currentRowChanged.connect(self.stack.setCurrentIndex)

        root_layout.addWidget(self.nav_list)
        root_layout.addWidget(self.stack, stretch=1)

        self.nav_list.setCurrentRow(0)


def main():
    app = QApplication(sys.argv)
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    apply_theme_mode(app, _load_theme_mode())
    app.setFont(QFont(APP_FONT_FAMILY, 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
