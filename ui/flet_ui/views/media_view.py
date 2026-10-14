# ui/flet_ui/views/media_view.py

import asyncio
import json
from pathlib import Path
from queue import Empty, Queue

import flet as ft

from tools.image.converter import convert_image, batch_convert
from tools.multimedia.video import convert_to_mp4, convert_to_gif, extract_audio, extract_video
from tools.multimedia.merge import merge_video_audio, replace_audio, concat_videos, DurationMode
from tools.multimedia.cut import cut_media
from tools.utils.ffmpeg import FFmpegCancelled
from tools.utils.paths import get_settings_path


def _get_mp4_compatibility() -> str:
    try:
        settings = json.loads(get_settings_path().read_text(encoding="utf-8"))
        return settings.get("video", {}).get("mp4_compatibility", "standard")
    except Exception:
        return "standard"


async def _run_blocking(worker, on_progress=None):
    """在工作线程执行同步任务，并把进度安全地交回 Flet UI 线程。"""
    progress_queue = Queue()
    task = asyncio.create_task(asyncio.to_thread(worker, progress_queue.put))

    while not task.done():
        while True:
            try:
                value = progress_queue.get_nowait()
            except Empty:
                break
            if on_progress:
                on_progress(value)
        await asyncio.sleep(0.05)

    while True:
        try:
            value = progress_queue.get_nowait()
        except Empty:
            break
        if on_progress:
            on_progress(value)

    return await task


def create_view(page: ft.Page) -> ft.Control:

    pickers = {
        "image": ft.FilePicker(), "folder": ft.FilePicker(), "video": ft.FilePicker(),
        "adv_v": ft.FilePicker(), "adv_a": ft.FilePicker(), "concat": ft.FilePicker(),
        "out_dir": ft.FilePicker(), "cut": ft.FilePicker(),
    }
    for picker in pickers.values():
        page.services.append(picker)

    async def on_pick_out_dir(e, state_dict, text_ui):
        dir_path = await pickers["out_dir"].get_directory_path()
        if dir_path:
            state_dict["out_dir"] = dir_path
            text_ui.value = f"📁 输出至: {dir_path}"
            page.update()

    def _unique_output_path(output_dir: Path, stem: str, suffix: str = ".mp4") -> Path:
        output_path = output_dir / f"{stem}{suffix}"
        if not output_path.exists():
            return output_path

        index = 1
        while True:
            output_path = output_dir / f"{stem}({index}){suffix}"
            if not output_path.exists():
                return output_path
            index += 1

    def _render_sortable_list(state_list: list, list_container: ft.Column, empty_hint: str = "暂无文件，请先添加"):
        list_container.controls.clear()

        if not state_list:
            list_container.controls.append(ft.Text(empty_hint, italic=True, color=ft.Colors.GREY_500, size=13))
            page.update()
            return

        for i, path in enumerate(state_list):
            def make_move_up(idx):
                def _up(e):
                    state_list[idx], state_list[idx - 1] = state_list[idx - 1], state_list[idx]
                    _render_sortable_list(state_list, list_container, empty_hint)
                return _up

            def make_move_down(idx):
                def _down(e):
                    state_list[idx], state_list[idx + 1] = state_list[idx + 1], state_list[idx]
                    _render_sortable_list(state_list, list_container, empty_hint)
                return _down

            def make_delete(idx):
                def _del(e):
                    state_list.pop(idx)
                    _render_sortable_list(state_list, list_container, empty_hint)
                return _del

            list_container.controls.append(
                ft.Row([
                    ft.Text(f"{i + 1}. {Path(path).name}", expand=True, no_wrap=True),
                    ft.IconButton(ft.Icons.ARROW_UPWARD, on_click=make_move_up(i), disabled=i == 0),
                    ft.IconButton(ft.Icons.ARROW_DOWNWARD, on_click=make_move_down(i), disabled=i == len(state_list) - 1),
                    ft.IconButton(ft.Icons.DELETE, on_click=make_delete(i), icon_color=ft.Colors.RED_500),
                ])
            )
        page.update()

    # ============================================================
    # 1. 图片格式转换
    # ============================================================

    img_state = {"path": None, "is_batch": False, "out_dir": None, "cancel_flag": False}

    img_path_text = ft.Text("未选择文件", italic=True, color=ft.Colors.GREY_500)
    img_out_text = ft.Text("📁 默认保存至原文件同级目录", color=ft.Colors.GREY_500)
    img_status = ft.Text("", size=14)
    img_progress = ft.ProgressBar(value=0, visible=False)

    img_format_dropdown = ft.Dropdown(
        label="目标格式",
        value="png",
        width=150,
        options=[ft.dropdown.Option(x) for x in ["png", "jpg", "webp", "bmp"]],
    )

    img_start_btn = ft.ElevatedButton("🚀 开始转换", icon=ft.Icons.PLAY_ARROW)
    img_stop_btn = ft.Button(content=ft.Text("停止"), icon=ft.Icons.STOP, visible=False, bgcolor=ft.Colors.RED_50, color=ft.Colors.RED_900)

    async def on_pick_image(e):
        files = await pickers["image"].pick_files()
        if files:
            img_state["path"] = files[0].path
            img_state["is_batch"] = False
            img_path_text.value = f"📄 单文件: {Path(files[0].path).name}"
            page.update()

    async def on_pick_folder(e):
        dir_path = await pickers["folder"].get_directory_path()
        if dir_path:
            img_state["path"] = dir_path
            img_state["is_batch"] = True
            img_path_text.value = f"📁 文件夹: {Path(dir_path).name}"
            page.update()

    def stop_img_click(e):
        img_state["cancel_flag"] = True
        img_stop_btn.disabled = True
        img_status.value = "⏳ 正在停止..."
        page.update()

    img_stop_btn.on_click = stop_img_click

    def on_start_image_convert(e):
        if not img_state["path"]:
            img_status.value = "❌ 请先选择图片或文件夹"
            img_status.color = ft.Colors.RED_500
            page.update()
            return

        img_state["cancel_flag"] = False
        img_status.value = "⏳ 正在拼命转换中，请稍候..."
        img_status.color = ft.Colors.ORANGE_500
        img_start_btn.disabled = True
        img_progress.visible = img_state["is_batch"]
        img_progress.value = 0
        img_stop_btn.visible = img_state["is_batch"]
        img_stop_btn.disabled = False
        page.update()

        async def _task():
            try:
                target_fmt = img_format_dropdown.value

                if img_state["is_batch"]:
                    def worker(emit):
                        return batch_convert(
                            img_state["path"],
                            target_fmt,
                            output_dir=img_state["out_dir"],
                            progress_callback=lambda current, total: emit((current, total)),
                            cancel_check=lambda: img_state["cancel_flag"],
                        )

                    def on_progress(value):
                        current, total = value
                        fraction = current / total if total else 0
                        img_progress.value = fraction
                        img_status.value = f"⏳ 转换中 {current}/{total} ({fraction * 100:.1f}%)"
                        page.update()

                    results = await _run_blocking(worker, on_progress)
                    img_status.value = f"✅ 批量转换完成！共处理 {len(results)} 张图片"
                else:
                    def worker(emit):
                        return convert_image(img_state["path"], target_fmt, output_dir=img_state["out_dir"])

                    out_file = await _run_blocking(worker)
                    img_status.value = f"✅ 转换成功: {Path(out_file).name}"

                img_status.color = ft.Colors.GREEN_500

            except InterruptedError as ex:
                img_status.value = f"⏹️ 已取消：{ex}"
                img_status.color = ft.Colors.ORANGE_500

            except Exception as ex:
                img_status.value = f"❌ 失败: {ex}"
                img_status.color = ft.Colors.RED_500

            finally:
                img_start_btn.disabled = False
                img_stop_btn.visible = False
                page.update()

        page.run_task(_task)

    img_start_btn.on_click = on_start_image_convert

    image_content = ft.Container(
        padding=20,
        content=ft.Column([
            ft.Text("🖼️ 图片格式互转", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("支持单张图片或整个文件夹批量转换", color=ft.Colors.GREY_500),
            ft.Divider(),
            ft.Row([
                ft.ElevatedButton("选择单张图片", icon=ft.Icons.IMAGE, on_click=on_pick_image),
                ft.ElevatedButton("选择文件夹 (批量)", icon=ft.Icons.FOLDER, on_click=on_pick_folder),
            ]),
            img_path_text,
            ft.Row([
                ft.ElevatedButton("更改输出目录", icon=ft.Icons.FOLDER, on_click=lambda e: page.run_task(on_pick_out_dir, e, img_state, img_out_text)),
                img_out_text,
            ]),
            ft.Divider(),
            ft.Row([img_format_dropdown, img_start_btn, img_stop_btn]),
            img_progress,
            img_status,
        ], scroll=ft.ScrollMode.AUTO),
    )

    # ============================================================
    # 2. 视频提取与转换
    # ============================================================

    vid_state = {"paths": [], "out_dir": None, "cancel_flag": False}

    vid_path_text = ft.Text("未选择视频", italic=True, color=ft.Colors.GREY_500)
    vid_out_text = ft.Text("📁 默认保存至原文件同级目录", color=ft.Colors.GREY_500)
    vid_status = ft.Text("", size=14)
    vid_progress = ft.ProgressBar(value=0, visible=False)
    vid_stop_btn = ft.Button(content=ft.Text("停止"), icon=ft.Icons.STOP, visible=False, bgcolor=ft.Colors.RED_50, color=ft.Colors.RED_900)

    async def on_pick_video(e):
        # 不限制扩展名，交给 FFmpeg 判断实际是否可处理。
        files = await pickers["video"].pick_files(allow_multiple=True)

        if files:
            vid_state["paths"] = [f.path for f in files]
            vid_path_text.value = (
                f"🎬 视频: {Path(vid_state['paths'][0]).name}"
                if len(files) == 1
                else f"🎬 已选择 {len(files)} 个视频"
            )
            vid_status.value = "就绪"
            vid_status.color = ft.Colors.BLUE_500
            page.update()

    def stop_vid_click(e):
        vid_state["cancel_flag"] = True
        vid_stop_btn.disabled = True
        vid_status.value = "⏳ 正在停止..."
        page.update()

    vid_stop_btn.on_click = stop_vid_click

    ACTION_FUNCS = {
        "mp4": convert_to_mp4,
        "gif": convert_to_gif,
        "audio": extract_audio,
        "video": extract_video,
    }

    def on_process_video(action_type: str, btn: ft.Control):
        paths = vid_state["paths"]

        if not paths:
            vid_status.value = "❌ 请先选择视频文件"
            vid_status.color = ft.Colors.RED_500
            page.update()
            return

        vid_state["cancel_flag"] = False
        vid_status.value = "⏳ FFmpeg 正在运算中，请耐心等待..."
        vid_status.color = ft.Colors.ORANGE_500
        btn.disabled = True
        vid_progress.visible = True
        vid_progress.value = 0
        vid_stop_btn.visible = True
        vid_stop_btn.disabled = False
        page.update()

        async def _task():
            total = len(paths)
            succeeded = []
            mp4_compatibility = _get_mp4_compatibility() if action_type == "mp4" else None

            try:
                func = ACTION_FUNCS[action_type]

                for i, path in enumerate(paths):
                    if vid_state["cancel_flag"]:
                        raise FFmpegCancelled("用户手动取消了任务")

                    file_name = Path(path).name
                    vid_status.value = f"⏳ 处理中 ({i + 1}/{total}): {file_name} - 0.0%"
                    page.update()

                    def worker(emit, path=path):
                        kwargs = {
                            "output_dir": vid_state["out_dir"],
                            "progress_callback": lambda fraction: emit(fraction),
                            "cancel_check": lambda: vid_state["cancel_flag"],
                        }
                        if action_type == "mp4":
                            kwargs["compatibility"] = mp4_compatibility
                        return func(path, **kwargs)

                    def on_progress(fraction, idx=i, name=file_name):
                        if fraction is None:
                            vid_status.value = f"⏳ 处理中 ({idx + 1}/{total}): {name} - 计算中..."
                            page.update()
                            return

                        fraction = max(0, min(1, fraction))
                        vid_progress.value = (idx + fraction) / total
                        vid_status.value = f"⏳ 处理中 ({idx + 1}/{total}): {name} - {fraction * 100:.1f}%"
                        page.update()

                    out = await _run_blocking(worker, on_progress)
                    succeeded.append(out)
                    vid_progress.value = (i + 1) / total
                    page.update()

                vid_status.value = f"✅ 处理完成，共 {len(succeeded)} 个文件：\n" + "\n".join(succeeded)
                vid_status.color = ft.Colors.GREEN_500

            except FFmpegCancelled:
                vid_status.value = f"⏹️ 已取消（已完成 {len(succeeded)}/{total} 个文件）"
                vid_status.color = ft.Colors.ORANGE_500

            except Exception as ex:
                vid_status.value = f"❌ 失败（已完成 {len(succeeded)}/{total} 个文件）: {ex}"
                vid_status.color = ft.Colors.RED_500

            finally:
                btn.disabled = False
                vid_stop_btn.visible = False
                page.update()

        page.run_task(_task)

    video_content = ft.Container(
        padding=20,
        content=ft.Column([
            ft.Text("🎬 视频提取与转换", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("高效的视频转码与音画分离提取，支持一次选择多个文件批量处理", color=ft.Colors.GREY_500),
            ft.Divider(),
            ft.Row([
                ft.ElevatedButton("选择视频文件（可多选）", icon=ft.Icons.VIDEO_FILE, on_click=lambda e: page.run_task(on_pick_video, e)),
                ft.Container(content=vid_path_text, expand=True),
            ]),
            ft.Row([
                ft.ElevatedButton("更改输出目录", icon=ft.Icons.FOLDER, on_click=lambda e: page.run_task(on_pick_out_dir, e, vid_state, vid_out_text)),
                vid_out_text,
            ]),
            ft.Divider(),
            ft.Row([
                ft.ElevatedButton("转为 MP4", on_click=lambda e: on_process_video("mp4", e.control)),
                ft.ElevatedButton("转为 GIF", on_click=lambda e: on_process_video("gif", e.control)),
                ft.ElevatedButton("提取纯音频", on_click=lambda e: on_process_video("audio", e.control)),
                ft.ElevatedButton("提取纯画面", on_click=lambda e: on_process_video("video", e.control)),
                vid_stop_btn,
            ], wrap=True),
            ft.Container(height=10),
            vid_progress,
            vid_status,
        ], scroll=ft.ScrollMode.AUTO),
    )

    # ============================================================
    # 3. 音画合成与拼接
    # ============================================================

    adv_state = {
        "video": None,
        "audio": None,
        "concat_files": [],
        "out_dir": None,
        "duration_mode": "shortest",
        "cancel_flag": False,
    }

    concat_state = {"out_dir": None}

    adv_v_text = ft.Text("未选择视频", italic=True, color=ft.Colors.GREY_500)
    adv_a_text = ft.Text("未选择音频", italic=True, color=ft.Colors.GREY_500)

    duration_dropdown = ft.Dropdown(
        label="合并后时长",
        width=220,
        value="shortest",
        options=[
            ft.dropdown.Option("shortest", "最短时长"),
            ft.dropdown.Option("longest", "最长时长"),
            ft.dropdown.Option("video", "以画面长度"),
            ft.dropdown.Option("audio", "以音频长度"),
        ],
    )

    def on_duration_change(e):
        adv_state["duration_mode"] = e.control.value

    duration_dropdown.on_change = on_duration_change

    adv_out_text = ft.Text("📁 默认保存至原视频文件同级目录", color=ft.Colors.GREY_500)
    concat_out_text = ft.Text("📁 默认保存至首个视频文件同级目录", color=ft.Colors.GREY_500)

    adv_merge_status = ft.Text("", size=14)
    adv_merge_progress = ft.ProgressBar(value=0, visible=False)
    adv_merge_stop_btn = ft.Button(content=ft.Text("停止"), icon=ft.Icons.STOP, visible=False, bgcolor=ft.Colors.RED_50, color=ft.Colors.RED_900)

    concat_list_ui = ft.Column()
    concat_status = ft.Text("", size=14)
    concat_progress = ft.ProgressBar(value=0, visible=False)
    concat_stop_btn = ft.Button(content=ft.Text("停止"), icon=ft.Icons.STOP, visible=False, bgcolor=ft.Colors.RED_50, color=ft.Colors.RED_900)

    async def on_pick_adv_v(e):
        files = await pickers["adv_v"].pick_files()
        if files:
            adv_state["video"] = files[0].path
            adv_v_text.value = Path(files[0].path).name
            page.update()

    async def on_pick_adv_a(e):
        files = await pickers["adv_a"].pick_files()
        if files:
            adv_state["audio"] = files[0].path
            adv_a_text.value = Path(files[0].path).name
            page.update()

    async def on_pick_concat(e):
        files = await pickers["concat"].pick_files(allow_multiple=True)
        if files:
            adv_state["concat_files"].extend([f.path for f in files])
            _render_sortable_list(adv_state["concat_files"], concat_list_ui, "暂无视频，请点击「多选视频」")

    async def on_pick_concat_out_dir(e):
        dir_path = await pickers["out_dir"].get_directory_path()
        if dir_path:
            concat_state["out_dir"] = dir_path
            concat_out_text.value = f"📁 输出至: {dir_path}"
            page.update()

    _render_sortable_list(adv_state["concat_files"], concat_list_ui, "暂无视频，请点击「多选视频」")

    def stop_merge_click(e):
        adv_state["cancel_flag"] = True
        adv_merge_stop_btn.disabled = True
        adv_merge_status.value = "⏳ 正在停止..."
        page.update()

    def stop_concat_click(e):
        adv_state["cancel_flag"] = True
        concat_stop_btn.disabled = True
        concat_status.value = "⏳ 正在停止..."
        page.update()

    adv_merge_stop_btn.on_click = stop_merge_click
    concat_stop_btn.on_click = stop_concat_click

    def on_start_merge(action_type: str, btn: ft.Control):
        if not adv_state["video"] or not adv_state["audio"]:
            adv_merge_status.value = "❌ 缺少素材"
            adv_merge_status.color = ft.Colors.RED_500
            page.update()
            return

        adv_state["cancel_flag"] = False
        adv_merge_status.value = "⏳ 合成中... 0.0%"
        adv_merge_status.color = ft.Colors.ORANGE_500
        btn.disabled = True
        adv_merge_progress.visible = True
        adv_merge_progress.value = 0
        adv_merge_stop_btn.visible = True
        adv_merge_stop_btn.disabled = False
        page.update()

        async def _task():
            try:
                v_path = Path(adv_state["video"])
                out_dir = Path(adv_state["out_dir"]) if adv_state["out_dir"] else v_path.parent
                suffix = "_merged" if action_type == "merge" else "_replaced"
                out_path = out_dir / f"{v_path.stem}{suffix}.mp4"

                def worker(emit):
                    if action_type == "merge":
                        return merge_video_audio(
                            adv_state["video"], adv_state["audio"], str(out_path),
                            duration_mode=adv_state["duration_mode"],
                            progress_callback=lambda fraction: emit(fraction),
                            cancel_check=lambda: adv_state["cancel_flag"],
                        )

                    return replace_audio(
                        adv_state["video"], adv_state["audio"], str(out_path),
                        duration_mode=adv_state["duration_mode"],
                        progress_callback=lambda fraction: emit(fraction),
                        cancel_check=lambda: adv_state["cancel_flag"],
                    )

                def on_progress(fraction):
                    if fraction is None:
                        adv_merge_status.value = "⏳ 合成中... 计算中"
                    else:
                        fraction = max(0, min(1, fraction))
                        adv_merge_progress.value = fraction
                        adv_merge_status.value = f"⏳ 合成中... {fraction * 100:.1f}%"
                    page.update()

                final_out = await _run_blocking(worker, on_progress)
                adv_merge_progress.value = 1
                adv_merge_status.value = f"✅ 成功: {final_out}"
                adv_merge_status.color = ft.Colors.GREEN_500

            except FFmpegCancelled:
                adv_merge_status.value = "⏹️ 已取消"
                adv_merge_status.color = ft.Colors.ORANGE_500

            except Exception as ex:
                adv_merge_status.value = f"❌ 失败: {ex}"
                adv_merge_status.color = ft.Colors.RED_500

            finally:
                btn.disabled = False
                adv_merge_stop_btn.visible = False
                page.update()

        page.run_task(_task)

    def on_start_concat(btn: ft.Control):
        if len(adv_state["concat_files"]) < 2:
            concat_status.value = "❌ 至少需 2 个视频"
            concat_status.color = ft.Colors.RED_500
            page.update()
            return

        adv_state["cancel_flag"] = False
        concat_status.value = "⏳ 拼接中(重编码统一尺寸)... 0.0%"
        concat_status.color = ft.Colors.ORANGE_500
        btn.disabled = True
        concat_progress.visible = True
        concat_progress.value = 0
        concat_stop_btn.visible = True
        concat_stop_btn.disabled = False
        page.update()

        async def _task():
            try:
                first_vid = Path(adv_state["concat_files"][0])
                out_dir = Path(concat_state["out_dir"]) if concat_state["out_dir"] else first_vid.parent
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = _unique_output_path(out_dir, f"{first_vid.stem}_concat", ".mp4")

                concat_status.value = "⏳ 拼接中(重编码统一尺寸)... 0.0%"
                concat_progress.value = 0
                page.update()

                def worker(emit):
                    return concat_videos(
                        adv_state["concat_files"], str(out_path),
                        progress_callback=lambda fraction: emit(fraction),
                        cancel_check=lambda: adv_state["cancel_flag"],
                    )

                def on_progress(fraction):
                    if fraction is None:
                        concat_status.value = "⏳ 拼接中(重编码统一尺寸)... 计算中"
                    else:
                        fraction = max(0, min(1, fraction))
                        concat_progress.value = fraction
                        concat_status.value = f"⏳ 拼接中(重编码统一尺寸)... {fraction * 100:.1f}%"
                    page.update()

                final_out = await _run_blocking(worker, on_progress)
                concat_progress.value = 1
                concat_status.value = f"✅ 拼接成功: {final_out}"
                concat_status.color = ft.Colors.GREEN_500
                page.update()

            except FFmpegCancelled:
                concat_status.value = "⏹️ 已取消"
                concat_status.color = ft.Colors.ORANGE_500
                page.update()

            except Exception as ex:
                concat_status.value = f"❌ 失败: {ex}"
                concat_status.color = ft.Colors.RED_500
                page.update()

            finally:
                btn.disabled = False
                concat_stop_btn.visible = False
                page.update()

        page.run_task(_task)

    adv_content = ft.Container(
        padding=20,
        content=ft.Column([
            ft.Text("🎞️ 音画合成与拼接", size=24, weight=ft.FontWeight.BOLD),
            ft.Divider(height=20),
            ft.Text("1. 音视频合并与声音替换", size=18, weight=ft.FontWeight.BOLD),
            ft.Row([ft.ElevatedButton("选择视频", icon=ft.Icons.VIDEO_FILE, on_click=lambda e: page.run_task(on_pick_adv_v, e)), adv_v_text]),
            ft.Row([ft.ElevatedButton("选择音频", icon=ft.Icons.AUDIO_FILE, on_click=lambda e: page.run_task(on_pick_adv_a, e)), adv_a_text]),
            ft.Row([duration_dropdown]),
            ft.Row([ft.ElevatedButton("更改输出目录", icon=ft.Icons.FOLDER, on_click=lambda e: page.run_task(on_pick_out_dir, e, adv_state, adv_out_text)), adv_out_text]),
            ft.Row([
                ft.ElevatedButton("无声合并", icon=ft.Icons.MERGE_TYPE, on_click=lambda e: on_start_merge("merge", e.control)),
                ft.ElevatedButton("替换原声", icon=ft.Icons.SWAP_HORIZ, on_click=lambda e: on_start_merge("replace", e.control)),
                adv_merge_stop_btn,
            ]),
            adv_merge_progress,
            adv_merge_status,
            ft.Divider(height=30),
            ft.Text("2. 多视频重新编码拼接", size=18, weight=ft.FontWeight.BOLD),
            ft.ElevatedButton("多选视频", icon=ft.Icons.LIBRARY_ADD, on_click=lambda e: page.run_task(on_pick_concat, e)),
            ft.Container(content=concat_list_ui, bgcolor=ft.Colors.GREY_100, border_radius=8, padding=10),
            ft.Row([
                ft.ElevatedButton("更改输出目录", icon=ft.Icons.FOLDER, on_click=lambda e: page.run_task(on_pick_concat_out_dir, e)),
                concat_out_text,
            ]),
            ft.Row([
                ft.ElevatedButton("🚀 开始拼接", icon=ft.Icons.PLAY_ARROW, on_click=lambda e: on_start_concat(e.control)),
                concat_stop_btn,
            ]),
            concat_progress,
            concat_status,
        ], scroll=ft.ScrollMode.AUTO),
    )

    # ============================================================
    # 4. 视频 / 音频指定长度截取
    # ============================================================

    cut_state = {"path": None, "out_dir": None, "cancel_flag": False}

    cut_path_text = ft.Text("未选择文件", italic=True, color=ft.Colors.GREY_500)
    cut_out_text = ft.Text("📁 默认保存至原文件同级目录", color=ft.Colors.GREY_500)

    cut_start = ft.TextField(label="起始时间 (如 0:30 或 90)", value="0", width=220, dense=True)

    cut_mode_dropdown = ft.Dropdown(
        label="截取方式",
        width=180,
        value="duration",
        options=[ft.dropdown.Option("duration", "按时长"), ft.dropdown.Option("end", "按结束时间")],
    )

    cut_end_or_duration = ft.TextField(label="截取时长 (秒，如 30 或 1:00)", value="30", width=260, dense=True)

    cut_reencode_check = ft.Checkbox(label="精确切割 (重新编码，较慢)", value=False)

    cut_status = ft.Text("", size=14)
    cut_progress = ft.ProgressBar(value=0, visible=False)
    cut_start_btn = ft.ElevatedButton("🚀 开始截取", icon=ft.Icons.CONTENT_CUT)
    cut_stop_btn = ft.Button(content=ft.Text("停止"), icon=ft.Icons.STOP, visible=False, bgcolor=ft.Colors.RED_50, color=ft.Colors.RED_900)

    def on_cut_mode_change(e):
        cut_end_or_duration.label = "截取时长 (秒，如 30 或 1:00)" if cut_mode_dropdown.value == "duration" else "结束时间 (如 1:30)"
        page.update()

    cut_mode_dropdown.on_change = on_cut_mode_change

    async def on_pick_cut_file(e):
        files = await pickers["cut"].pick_files()
        if files:
            cut_state["path"] = files[0].path
            cut_path_text.value = f"🎬 {Path(files[0].path).name}"
            page.update()

    def stop_cut_click(e):
        cut_state["cancel_flag"] = True
        cut_stop_btn.disabled = True
        page.update()

    cut_stop_btn.on_click = stop_cut_click

    def on_start_cut(e):
        if not cut_state["path"]:
            cut_status.value = "❌ 请先选择视频或音频文件"
            cut_status.color = ft.Colors.RED_500
            page.update()
            return

        cut_state["cancel_flag"] = False
        cut_status.value = "⏳ 正在截取... 0.0%"
        cut_status.color = ft.Colors.ORANGE_500
        cut_start_btn.disabled = True
        cut_progress.visible = True
        cut_progress.value = 0
        cut_stop_btn.visible = True
        cut_stop_btn.disabled = False
        page.update()

        async def _run_cut_task():
            try:
                kwargs = {
                    "input_path": cut_state["path"],
                    "start": cut_start.value,
                    "output_dir": cut_state["out_dir"],
                    "reencode": cut_reencode_check.value,
                }
                kwargs["duration" if cut_mode_dropdown.value == "duration" else "end"] = cut_end_or_duration.value

                def worker(emit):
                    return cut_media(
                        **kwargs,
                        progress_callback=lambda fraction: emit(fraction),
                        cancel_check=lambda: cut_state["cancel_flag"],
                    )

                def on_progress(fraction):
                    if fraction is None:
                        cut_status.value = "⏳ 正在截取... 计算中"
                    else:
                        fraction = max(0, min(1, fraction))
                        cut_progress.value = fraction
                        cut_status.value = f"⏳ 正在截取... {fraction * 100:.1f}%"
                    page.update()

                out = await _run_blocking(worker, on_progress)
                cut_progress.value = 1
                cut_status.value = f"✅ 截取成功: {out}"
                cut_status.color = ft.Colors.GREEN_500

            except FFmpegCancelled:
                cut_status.value = "⏹️ 已取消"
                cut_status.color = ft.Colors.ORANGE_500

            except Exception as ex:
                cut_status.value = f"❌ 失败: {ex}"
                cut_status.color = ft.Colors.RED_500

            finally:
                cut_start_btn.disabled = False
                cut_stop_btn.visible = False
                page.update()

        page.run_task(_run_cut_task)

    cut_start_btn.on_click = on_start_cut

    cut_content = ft.Container(
        padding=20,
        content=ft.Column([
            ft.Text("✂️ 指定长度截取", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("从视频或音频中截取任意一段，支持按时长或结束时间点截取", color=ft.Colors.GREY_500),
            ft.Divider(),
            ft.Row([ft.ElevatedButton("选择视频/音频", icon=ft.Icons.MOVIE_FILTER, on_click=lambda e: page.run_task(on_pick_cut_file, e)), cut_path_text]),
            ft.Row([ft.ElevatedButton("更改输出目录", icon=ft.Icons.FOLDER, on_click=lambda e: page.run_task(on_pick_out_dir, e, cut_state, cut_out_text)), cut_out_text]),
            ft.Divider(),
            ft.Row([cut_start, cut_mode_dropdown, cut_end_or_duration]),
            cut_reencode_check,
            ft.Row([cut_start_btn, cut_stop_btn]),
            cut_progress,
            cut_status,
        ], scroll=ft.ScrollMode.AUTO),
    )

    return ft.Tabs(
        length=4,
        selected_index=0,
        expand=True,
        content=ft.Column(
            expand=True,
            controls=[
                ft.TabBar(tabs=[
                    ft.Tab(label=ft.Text("🖼️ 图片转换", font_family="Microsoft YaHei UI")),
                    ft.Tab(label=ft.Text("🎬 视频处理", font_family="Microsoft YaHei UI")),
                    ft.Tab(label=ft.Text("🎞️ 音画合成", font_family="Microsoft YaHei UI")),
                    ft.Tab(label=ft.Text("✂️ 长度截取", font_family="Microsoft YaHei UI")),
                ]),
                ft.TabBarView(expand=True, controls=[image_content, video_content, adv_content, cut_content]),
            ],
        ),
    )