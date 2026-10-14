# tests/test_filepicker.py

import flet as ft


def main(page: ft.Page):

    picker = ft.FilePicker()

    page.overlay.append(picker)


    async def select_folder(e):

        path = await picker.get_directory_path()

        print(path)


    page.add(
        ft.ElevatedButton(
            "选择目录",
            on_click=select_folder
        )
    )


ft.app(main)