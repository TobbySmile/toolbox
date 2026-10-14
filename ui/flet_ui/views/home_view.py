# ui/fflet_ui/views/home_view.py
import flet as ft

def create_view(page: ft.Page) -> ft.Control:
    return ft.Container(
        expand=True,
        content=ft.Column(
            controls=[
                # 遵循新版：去掉 name=，使用 ft.Icons 和 ft.Colors 大写
                ft.Image(src="icon.png", width=96, height=96),
                ft.Text("万象阁", size=32, weight=ft.FontWeight.BOLD),
                ft.Text("极简、私密、高效的本地化数字工具空间", size=16, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Divider(height=40, color=ft.Colors.TRANSPARENT),
                ft.Text("请在左侧导航栏选择需要使用的功能模块 👈", size=14, italic=True)
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
    )