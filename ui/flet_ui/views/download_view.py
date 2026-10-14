# ui/flet_ui/views/download_view.py

import asyncio
from pathlib import Path
from queue import Empty, Queue

import flet as ft

# ==========================================
# tools 层
# ==========================================
from tools.multimedia.downloader import (
    parse_video_info,
    download_video,
    DownloadCancelled,
)
from tools.wallpaper import (
    download_wallpapers,
    WallpaperCancelled,
)


def create_view(page: ft.Page) -> ft.Control:

    async def _run_thread_with_events(worker, on_event):
        """在工作线程执行同步任务，事件在 Flet asyncio/UI 线程处理。"""
        event_queue = Queue()
        task = asyncio.create_task(
            asyncio.to_thread(worker, event_queue.put)
        )

        while not task.done():
            while True:
                try:
                    event = event_queue.get_nowait()
                except Empty:
                    break
                on_event(event)

            await asyncio.sleep(0.05)

        while True:
            try:
                event = event_queue.get_nowait()
            except Empty:
                break
            on_event(event)

        return await task

    # =====================================================
    # Flet 0.86.5 FilePicker
    # =====================================================
    video_picker = ft.FilePicker()
    wallpaper_picker = ft.FilePicker()

    page.services.append(video_picker)
    page.services.append(wallpaper_picker)

    # =====================================================
    # 视频下载状态
    # =====================================================
    video_state = {
        "url": "",
        "title": "",
        "formats": [],
        "save_dir": None,
        "cancel_flag": False,
    }

    # =====================================================
    # 视频 UI 控件
    # =====================================================
    video_url = ft.TextField(
        label="🔗 视频链接",
        hint_text="支持 B站 / YouTube / 抖音",
        expand=True
    )
    video_status = ft.Text()
    format_dropdown = ft.Dropdown(
        label="选择清晰度",
        expand=True,
        visible=False,
    )
    aria2_check = ft.Checkbox(
        label="使用 Aria2 加速",
        value=False,
        visible=False,
    )
    save_path_text = ft.Text(
        "未选择保存目录",
        visible=False,
    )
    progress_bar = ft.ProgressBar(
        value=0,
        visible=False,
    )
    progress_text = ft.Text()
    parse_button = ft.Button(
        content=ft.Text("解析视频"),
        icon=ft.Icons.SEARCH,
    )
    choose_dir_button = ft.Button(
        content=ft.Text("选择输出目录"),
        icon=ft.Icons.FOLDER,
        visible=False,
    )
    download_button = ft.Button(
        content=ft.Text("开始下载"),
        icon=ft.Icons.DOWNLOAD,
        visible=False,
    )
    stop_video_button = ft.Button(
        content=ft.Text("停止下载"),
        icon=ft.Icons.STOP,
        visible=False,
        bgcolor=ft.Colors.RED_50,
        color=ft.Colors.RED_900,
    )

    # =====================================================
    # 选择视频输出目录
    # =====================================================
    async def choose_video_directory(e):
        directory = await video_picker.get_directory_path()
        if directory:
            video_state["save_dir"] = directory
            save_path_text.value = f"📁 输出目录: {directory}"
            save_path_text.update()

    choose_dir_button.on_click = choose_video_directory

    # =====================================================
    # 视频解析
    # =====================================================
    def parse_video_click(e):
        url = video_url.value.strip()

        if not url:
            video_status.value = "❌ 请输入视频链接"
            video_status.color = ft.Colors.RED
            page.update()
            return

        parse_button.disabled = True
        video_status.value = "⏳ 正在解析视频..."
        video_status.color = ft.Colors.ORANGE
        page.update()

        async def worker():
            try:
                title, formats = await asyncio.to_thread(parse_video_info, url)

                video_state["url"] = url
                video_state["title"] = title
                video_state["formats"] = formats

                format_dropdown.options.clear()
                for index, fmt in enumerate(formats):
                    format_dropdown.options.append(
                        ft.dropdown.Option(key=str(index), text=fmt.display_name)
                    )

                if formats:
                    format_dropdown.value = "0"

                format_dropdown.visible = True
                aria2_check.visible = True
                choose_dir_button.visible = True
                save_path_text.visible = True
                download_button.visible = True

                video_status.value = f"✅ 解析成功: {title}"
                video_status.color = ft.Colors.GREEN

            except Exception as ex:
                video_status.value = f"❌ 解析失败: {ex}"
                video_status.color = ft.Colors.RED
            finally:
                parse_button.disabled = False
                page.update()

        page.run_task(worker)

    parse_button.on_click = parse_video_click

    # =====================================================
    # 停止视频下载
    # =====================================================
    def stop_video_click(e):
        video_state["cancel_flag"] = True
        stop_video_button.disabled = True
        progress_text.value = "⏳ 正在发送停止指令，请稍候..."
        progress_text.color = ft.Colors.RED
        page.update()

    stop_video_button.on_click = stop_video_click

    # =====================================================
    # 视频下载
    # =====================================================
    def download_video_click(e):
        if not video_state["save_dir"]:
            video_status.value = "❌ 请先选择输出目录"
            video_status.color = ft.Colors.RED
            page.update()
            return

        if not format_dropdown.value:
            video_status.value = "❌ 请先选择清晰度"
            video_status.color = ft.Colors.RED
            page.update()
            return

        selected_index = int(format_dropdown.value)
        selected_format = video_state["formats"][selected_index]

        video_state["cancel_flag"] = False
        download_button.disabled = True
        stop_video_button.visible = True
        stop_video_button.disabled = False
        progress_bar.visible = True
        progress_bar.value = 0
        progress_text.value = "准备下载..."
        progress_text.color = ft.Colors.BLUE
        page.update()

        def handle_video_event(event):
            event_type, data = event

            if event_type != "progress":
                return

            if data.get("status") != "downloading":
                return

            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            current = data.get("downloaded_bytes", 0)

            if total:
                value = current / total
                progress_bar.value = value
                progress_text.value = f"下载中 {value * 100:.1f}%"
            else:
                progress_text.value = (
                    f"下载中... 已下载 "
                    f"{current / (1024 * 1024):.1f}MB"
                )

            page.update()

        async def worker():
            try:
                output = await _run_thread_with_events(
                    lambda emit: download_video(
                        video_format=selected_format,
                        save_dir=video_state["save_dir"],
                        title=video_state["title"],
                        use_aria2=aria2_check.value,
                        threads=4,
                        progress_hook=lambda data: emit(("progress", data)),
                        cancel_check=lambda: video_state["cancel_flag"],
                    ),
                    handle_video_event,
                )

                progress_bar.value = 1
                progress_text.value = f"✅ 下载完成:\n{output}"
                progress_text.color = ft.Colors.GREEN

            except DownloadCancelled:
                progress_text.value = "⏹️ 下载已取消"
                progress_text.color = ft.Colors.ORANGE

            except Exception as ex:
                progress_text.value = f"❌ 下载失败:\n{ex}"
                progress_text.color = ft.Colors.RED

            finally:
                download_button.disabled = False
                stop_video_button.visible = False
                page.update()

        page.run_task(worker)

    download_button.on_click = download_video_click

    # =====================================================
    # 视频下载页面 UI
    # =====================================================
    video_content = ft.Container(
        padding=20,
        content=ft.Column(
            [
                ft.Text("🎬 视频全能下载器", size=24, weight=ft.FontWeight.BOLD),
                ft.Text("支持 B站 / YouTube / 抖音等平台", color=ft.Colors.GREY_500),
                ft.Divider(),
                ft.Row([video_url, parse_button]),
                video_status,
                ft.Row([format_dropdown, aria2_check]),
                ft.Row([choose_dir_button, save_path_text]),
                ft.Row([download_button, stop_video_button]),
                progress_bar,
                progress_text,
            ],
            scroll=ft.ScrollMode.AUTO,
        )
    )

    # =====================================================
    # Bing 壁纸下载模块
    # =====================================================
    wallpaper_state = {
        "save_dir": None,
        "cancel_flag": False,
    }

    wallpaper_days = ft.TextField(label="下载天数 (1-8)", value="8", width=180)
    wallpaper_regions = ft.TextField(label="地区数量 (1-8)", value="3", width=180)
    wallpaper_path_text = ft.Text("未选择保存目录")
    wallpaper_progress = ft.ProgressBar(value=0, visible=False)
    wallpaper_status = ft.Text()

    wallpaper_choose_button = ft.Button(content=ft.Text("选择保存目录"), icon=ft.Icons.FOLDER)
    wallpaper_download_button = ft.Button(content=ft.Text("开始下载壁纸"), icon=ft.Icons.WALLPAPER)
    stop_wallpaper_button = ft.Button(
        content=ft.Text("停止下载"),
        icon=ft.Icons.STOP,
        visible=False,
        bgcolor=ft.Colors.RED_50,
        color=ft.Colors.RED_900,
    )

    async def choose_wallpaper_directory(e):
        directory = await wallpaper_picker.get_directory_path()
        if directory:
            wallpaper_state["save_dir"] = directory
            wallpaper_path_text.value = f"📁 输出目录: {directory}"
            page.update()

    wallpaper_choose_button.on_click = choose_wallpaper_directory

    def stop_wallpaper_click(e):
        wallpaper_state["cancel_flag"] = True
        stop_wallpaper_button.disabled = True
        wallpaper_status.value = "⏳ 正在发送停止指令..."
        wallpaper_status.color = ft.Colors.RED
        page.update()

    stop_wallpaper_button.on_click = stop_wallpaper_click

    def wallpaper_download_click(e):
        if not wallpaper_state["save_dir"]:
            wallpaper_status.value = "❌ 请先选择输出目录"
            wallpaper_status.color = ft.Colors.RED
            page.update()
            return

        try:
            days = int(wallpaper_days.value)
            regions = int(wallpaper_regions.value)
            if regions < 1 or regions > 8:
                wallpaper_status.value = "❌ 地区数量必须在 1 到 8 之间"
                wallpaper_status.color = ft.Colors.RED
                page.update()
                return
            if days < 1 or days > 10:
                wallpaper_status.value = "❌ 下载天数必须在 1 到 10 之间"
                wallpaper_status.color = ft.Colors.RED
                page.update()
                return
        except ValueError:
            wallpaper_status.value = "❌ 天数和地区必须是纯数字"
            wallpaper_status.color = ft.Colors.RED
            page.update()
            return

        wallpaper_state["cancel_flag"] = False
        wallpaper_download_button.disabled = True
        stop_wallpaper_button.visible = True
        stop_wallpaper_button.disabled = False
        wallpaper_progress.visible = True
        wallpaper_progress.value = 0
        wallpaper_status.value = "⏳ 开始下载..."
        wallpaper_status.color = ft.Colors.ORANGE
        page.update()

        def handle_wallpaper_event(event):
            event_type, data = event

            if event_type == "log":
                wallpaper_status.value = data
                page.update()

            elif event_type == "progress":
                current, total = data
                if total:
                    wallpaper_progress.value = current / total
                    page.update()

        async def worker():
            try:
                await _run_thread_with_events(
                    lambda emit: download_wallpapers(
                        region_count=regions,
                        day_count=days,
                        save_dir=Path(wallpaper_state["save_dir"]),
                        on_log=lambda message: emit(("log", message)),
                        on_progress=lambda current, total: emit(
                            ("progress", (current, total))
                        ),
                        cancel_check=lambda: wallpaper_state["cancel_flag"],
                    ),
                    handle_wallpaper_event,
                )

                wallpaper_progress.value = 1
                wallpaper_status.value = "✅ 壁纸下载完成"
                wallpaper_status.color = ft.Colors.GREEN

            except WallpaperCancelled:
                wallpaper_status.value = "⏹️ 下载已取消"
                wallpaper_status.color = ft.Colors.ORANGE

            except Exception as ex:
                wallpaper_status.value = f"❌ 下载失败: {ex}"
                wallpaper_status.color = ft.Colors.RED

            finally:
                wallpaper_download_button.disabled = False
                stop_wallpaper_button.visible = False
                page.update()

        page.run_task(worker)

    wallpaper_download_button.on_click = wallpaper_download_click

    wallpaper_content = ft.Container(
        padding=20,
        content=ft.Column(
            [
                ft.Text("🖼️ Bing 每日壁纸", size=24, weight=ft.FontWeight.BOLD),
                ft.Text("自动下载高清 Bing 壁纸", color=ft.Colors.GREY_500),
                ft.Divider(),
                ft.Row([wallpaper_days, wallpaper_regions]),
                ft.Text("提示：最多支持获取 8 个地区、8 天壁纸", size=12, color=ft.Colors.GREY_500),
                ft.Row([wallpaper_choose_button, wallpaper_path_text]),
                ft.Row([wallpaper_download_button, stop_wallpaper_button]),
                wallpaper_progress,
                wallpaper_status,
            ],
            scroll=ft.ScrollMode.AUTO,
        )
    )

    # =====================================================
    # Tabs 页面
    # =====================================================
    return ft.Tabs(
        length=2,
        selected_index=0,
        expand=True,
        content=ft.Column(
            expand=True,
            controls=[
                ft.TabBar(tabs=[ft.Tab(label="🎬 视频下载"), ft.Tab(label="🖼️ 壁纸下载")]),
                ft.TabBarView(expand=True, controls=[video_content, wallpaper_content])
            ]
        )
    )