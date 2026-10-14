# ui/flet_ui/views/settings_view.py

import json

import flet as ft

from tools.multimedia.video import MP4_COMPATIBILITY_PRESETS
from tools.utils.cookie import PLATFORM_INFO, import_cookie, get_cookie_status, remove_cookie
from tools.utils.ffmpeg import (
    check_ffmpeg_available,
    check_ffprobe_available,
    get_ffmpeg_path,
    get_ffprobe_path,
)
from tools.utils.paths import get_settings_path


SETTINGS_PATH = get_settings_path()

THEME_MODE_LABELS = {"system": "跟随系统", "light": "浅色", "dark": "深色"}


def _load_settings() -> dict:
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}

    data.setdefault("appearance", {}).setdefault("theme_mode", "system")
    data.setdefault("tree", {}).setdefault("default_max_depth", None)
    data.setdefault("video", {}).setdefault("mp4_compatibility", "standard")
    return data


def _save_settings(data: dict):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def create_view(page: ft.Page) -> ft.Control:
    settings = _load_settings()

    picker = ft.FilePicker()
    page.services.append(picker)

    def show_snack(msg, color=ft.Colors.GREEN_500):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True, bgcolor=color))
        page.update()

    # ============================================================
    # 外观设置
    # ============================================================

    theme_mode_map = {
        "system": ft.ThemeMode.SYSTEM,
        "light": ft.ThemeMode.LIGHT,
        "dark": ft.ThemeMode.DARK,
    }

    def on_theme_change(e):
        mode_key = e.control.value
        page.theme_mode = theme_mode_map.get(mode_key, ft.ThemeMode.SYSTEM)
        settings["appearance"]["theme_mode"] = mode_key
        _save_settings(settings)
        page.update()

    theme_radio = ft.RadioGroup(
        value=settings["appearance"]["theme_mode"],
        on_change=on_theme_change,
        content=ft.Row([
            ft.Radio(value="system", label="跟随系统"),
            ft.Radio(value="light", label="浅色"),
            ft.Radio(value="dark", label="深色"),
        ]),
    )

    appearance_section = ft.Column([
        ft.Text("🎨 外观设置", size=18, weight=ft.FontWeight.BOLD),
        ft.ListTile(
            leading=ft.Icon(ft.Icons.PALETTE_OUTLINED),
            title=ft.Text("主题模式"),
            subtitle=theme_radio,
        ),
    ])

    # ============================================================
    # 视频设置
    # ============================================================

    mp4_compatibility = ft.Dropdown(
        width=320,
        value=settings["video"]["mp4_compatibility"],
        options=[ft.dropdown.Option(key=key, text=value["label"]) for key, value in MP4_COMPATIBILITY_PRESETS.items()],
    )

    def on_mp4_compatibility_change(e):
        settings["video"]["mp4_compatibility"] = e.control.value
        _save_settings(settings)
        show_snack("✅ MP4 编码模式已保存")

    mp4_compatibility.on_change = on_mp4_compatibility_change

    video_section = ft.Column([
        ft.Text("🎬 视频设置", size=18, weight=ft.FontWeight.BOLD),
        ft.Row([
            ft.Icon(ft.Icons.VIDEO_SETTINGS_OUTLINED, size=24),
            ft.Column([
                ft.Text("MP4 编码模式", weight=ft.FontWeight.W_500),
                mp4_compatibility,
                ft.Text(
                    "通用高画质：H.264 High + YUV420P + AAC-LC\n"
                    "老旧设备兼容：H.264 Baseline + YUV420P + AAC-LC",
                    size=12,
                    color=ft.Colors.GREY_600,
                ),
            ], spacing=6, expand=True),
        ], vertical_alignment=ft.CrossAxisAlignment.START),
    ])

    # ============================================================
    # 外部依赖检测
    # ============================================================

    def build_dep_tile(name, ok, path, hint_ok, hint_fail):
        if ok and path:
            source = (
                "程序内置"
                if "\\assets\\ffmpeg\\bin\\" in path.lower() or "/assets/ffmpeg/bin/" in path.lower()
                else "系统 PATH"
            )
            subtitle = f"{hint_ok} · 来源：{source}"
        else:
            subtitle = hint_fail

        return ft.ListTile(
            leading=ft.Icon(
                ft.Icons.CHECK_CIRCLE if ok else ft.Icons.CANCEL,
                color=ft.Colors.GREEN if ok else ft.Colors.RED,
            ),
            title=ft.Text(name),
            subtitle=ft.Text(
                subtitle,
                color=None if ok else ft.Colors.RED_400,
            ),
        )

    ffmpeg_path = get_ffmpeg_path()
    ffprobe_path = get_ffprobe_path()
    ffmpeg_ok = check_ffmpeg_available()
    ffprobe_ok = check_ffprobe_available()

    def on_recheck(e):
        page.overlay.append(ft.SnackBar(ft.Text("正在重新检测..."), open=True))
        views_container.content = create_view(page)
        page.update()

    dependency_section = ft.Column([
        ft.Row([
            ft.Text("🔧 外部依赖检测", size=18, weight=ft.FontWeight.BOLD),
            ft.Container(expand=True),
            ft.TextButton("重新检测", icon=ft.Icons.REFRESH, on_click=on_recheck),
        ]),
        build_dep_tile(
            "FFmpeg",
            ffmpeg_ok,
            ffmpeg_path,
            "已检测到，可用于音视频转换、合并、截取",
            "未检测到，请确认 assets/ffmpeg/bin 中存在 ffmpeg，或将 FFmpeg 加入系统 PATH",
        ),
        build_dep_tile(
            "FFprobe",
            ffprobe_ok,
            ffprobe_path,
            "已检测到，可读取媒体时长并计算精确进度",
            "未检测到，请确认 assets/ffmpeg/bin 中存在 ffprobe，或将 FFprobe 加入系统 PATH",
        ),
    ])

    # ============================================================
    # Cookie 导入
    # ============================================================

    cookie_status_column = ft.Column(spacing=4)

    platform_dropdown = ft.Dropdown(
        label="选择平台",
        width=220,
        value="youtube",
        options=[ft.dropdown.Option(key, label) for key, (_, label) in PLATFORM_INFO.items()],
    )

    cookie_status_text = ft.Text("", size=13)

    def refresh_cookie_status():
        cookie_status_column.controls.clear()
        status = get_cookie_status()

        for key, (_, label) in PLATFORM_INFO.items():
            imported = status.get(key, False)
            cookie_status_column.controls.append(
                ft.Row([
                    ft.Icon(
                        ft.Icons.CHECK_CIRCLE if imported else ft.Icons.RADIO_BUTTON_UNCHECKED,
                        color=ft.Colors.GREEN if imported else ft.Colors.GREY_400,
                        size=18,
                    ),
                    ft.Text(label, expand=True),
                    ft.Text(
                        "已导入" if imported else "未导入",
                        color=ft.Colors.GREEN if imported else ft.Colors.GREY_500,
                        size=12,
                    ),
                    ft.IconButton(
                        ft.Icons.DELETE_OUTLINE,
                        icon_size=18,
                        tooltip="移除",
                        disabled=not imported,
                        on_click=lambda e, k=key: on_remove_cookie(k),
                    ),
                ])
            )

        page.update()

    def on_remove_cookie(platform_key):
        try:
            remove_cookie(platform_key)
            show_snack("✅ 已移除该平台的 Cookie")
        except Exception as ex:
            show_snack(f"❌ {ex}", ft.Colors.RED)
        refresh_cookie_status()

    async def on_pick_cookie_file(e):
        files = await picker.pick_files(allowed_extensions=["txt"])

        if not files:
            return

        try:
            target = import_cookie(platform_dropdown.value, files[0].path)
            cookie_status_text.value = f"✅ 已导入并重命名为: {target.name}"
            cookie_status_text.color = ft.Colors.GREEN
        except Exception as ex:
            cookie_status_text.value = f"❌ 导入失败: {ex}"
            cookie_status_text.color = ft.Colors.RED

        page.update()
        refresh_cookie_status()

    refresh_cookie_status()

    cookie_section = ft.Column([
        ft.Text("🍪 Cookie 导入", size=18, weight=ft.FontWeight.BOLD),
        ft.Text(
            "部分平台（会员内容 / 需要登录的视频）需要导入 Cookie 才能下载。"
            "使用浏览器插件导出 Netscape 格式的 cookies.txt，选择对应平台后导入，"
            "文件会自动复制并重命名为标准名称，无需手动改名。",
            color=ft.Colors.GREY_600,
            size=13,
        ),
        ft.Row([
            platform_dropdown,
            ft.ElevatedButton(
                "选择 Cookie 文件导入",
                icon=ft.Icons.UPLOAD_FILE,
                on_click=lambda e: page.run_task(on_pick_cookie_file, e),
            ),
        ]),
        cookie_status_text,
        ft.Container(height=6),
        ft.Text("导入状态", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_600),
        ft.Container(
            content=cookie_status_column,
            bgcolor=ft.Colors.GREY_100,
            border_radius=8,
            padding=10,
        ),
    ])

    views_container = ft.Container(
        content=ft.Column([
            ft.Text("⚙️ 系统设置", size=28, weight=ft.FontWeight.BOLD),
            ft.Divider(height=30),
            appearance_section,
            ft.Divider(height=30),
            video_section,
            ft.Divider(height=30),
            dependency_section,
            ft.Divider(height=30),
            cookie_section,
        ], scroll=ft.ScrollMode.AUTO),
        expand=True,
    )

    return views_container