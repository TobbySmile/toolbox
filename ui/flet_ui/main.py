# ui/flet_ui/main.py

import os
import sys

if getattr(sys, "frozen", False):
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

import json
from pathlib import Path

def get_assets_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).resolve().parents[2] / "assets"

import flet as ft

# 引入项目统一的路径管理函数，实现打包与开发环境隔离
from tools.utils.paths import get_settings_path

from ui.flet_ui.views.home_view import create_view as load_home
from ui.flet_ui.views.download_view import create_view as load_download
from ui.flet_ui.views.media_view import create_view as load_media
from ui.flet_ui.views.document_view import create_view as load_document
from ui.flet_ui.views.utility_view import create_view as load_utility
from ui.flet_ui.views.transfer_view import create_view as load_share
from ui.flet_ui.views.settings_view import create_view as load_settings


def _load_theme_mode() -> str:
    """启动时从 AppData/settings.json 读取用户选择的外观模式，读取失败则默认跟随系统"""
    settings_file = get_settings_path()
    try:
        if settings_file.exists():
            data = json.loads(settings_file.read_text(encoding="utf-8"))
            mode_key = data.get("appearance", {}).get("theme_mode", "system")
            if mode_key in ["system", "light", "dark"]:
                return mode_key
        return "system"
    except Exception:
        return "system"


def main(page: ft.Page):
    page.title = "万象阁"
    page.window.icon = str(get_assets_dir() / "icon.ico")
    page.window.width, page.window.height = 1000, 700
    page.window.min_width, page.window.min_height = 900, 600
    
    # Flet 0.86+ 中，theme_mode 直接接收小写字符串
    page.theme, page.theme_mode = ft.Theme(font_family="Microsoft YaHei UI"), _load_theme_mode()

    # 路由表与页面缓存
    VIEW_ROUTER = {
        0: load_home,
        1: load_download,
        2: load_media,
        3: load_document,
        4: load_utility,
        5: load_share,
        6: load_settings,
    }
    views = {}

    def get_view(index):
        if index not in views and index in VIEW_ROUTER:
            views[index] = VIEW_ROUTER[index](page)
        return views.get(index)

    content_area = ft.Container(expand=True, padding=25, content=get_view(0))

    def on_navigation_clicked(e):
        # 设置页每次都重新构建，离开再回来时依赖检测状态最新
        index = e.control.selected_index
        if index == 6:
            views.pop(6, None)
        if (view := get_view(index)):
            content_area.content = view
            page.update()

    # 左侧导航栏
    rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=90,
        group_alignment=-0.95,
        destinations=[
            ft.NavigationRailDestination(icon=ft.Icons.HOME_OUTLINED, selected_icon=ft.Icons.HOME_ROUNDED, label="首页"),
            ft.NavigationRailDestination(icon=ft.Icons.DOWNLOAD_OUTLINED, selected_icon=ft.Icons.DOWNLOAD_ROUNDED, label="下载"),
            ft.NavigationRailDestination(icon=ft.Icons.PLAY_CIRCLE_OUTLINE, selected_icon=ft.Icons.PLAY_CIRCLE_FILLED_ROUNDED, label="媒体"),
            ft.NavigationRailDestination(icon=ft.Icons.DESCRIPTION_OUTLINED, selected_icon=ft.Icons.DESCRIPTION_ROUNDED, label="文档"),
            ft.NavigationRailDestination(icon=ft.Icons.CONSTRUCTION_OUTLINED, selected_icon=ft.Icons.CONSTRUCTION_ROUNDED, label="工具"),
            ft.NavigationRailDestination(icon=ft.Icons.BOLT_OUTLINED, selected_icon=ft.Icons.BOLT_ROUNDED, label="传送"),
            ft.NavigationRailDestination(icon=ft.Icons.SETTINGS_OUTLINED, selected_icon=ft.Icons.SETTINGS_ROUNDED, label="设置"),
        ],
        on_change=on_navigation_clicked,
    )

    page.add(ft.Row(controls=[rail, ft.VerticalDivider(width=1), content_area], expand=True, spacing=0))


if __name__ == "__main__":
    ft.run(main, assets_dir=str(get_assets_dir()))