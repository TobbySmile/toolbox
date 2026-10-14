# ui/flet_ui/views/document_view.py

import asyncio
from pathlib import Path
from queue import Empty, Queue

import flet as ft

# ==========================================
# 导入 tools/pdf/ 下的所有底层纯函数
# ==========================================
from tools.pdf.extract import extract_text_batch
from tools.pdf.merge import merge_pdfs
from tools.pdf.split import split_pdf
from tools.pdf.convert import pdf_to_images, images_to_pdf
from tools.pdf.reorder import multi_move_pages
from tools.utils.file import safe_output_path


def _parse_page_ranges(range_str: str) -> list[int]:
    if not range_str.strip() or range_str.strip().lower() == "all":
        return None

    pages = set()

    for part in range_str.replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue

        if "-" in part:
            start, end = part.split("-", 1)
            pages.update(range(int(start) - 1, int(end)))
        else:
            pages.add(int(part) - 1)

    return sorted(list(pages))


def _parse_move_rules(rule_str: str) -> list[tuple[int, int]]:
    rules = []

    for part in rule_str.replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue

        separator = next(
            (sep for sep in ["->", ">", ":", "："] if sep in part),
            None,
        )

        if not separator:
            raise ValueError(
                f"规则需包含目标位置，如 8>2。出错部分: '{part}'"
            )

        src_str, tgt_str = part.split(separator, 1)
        tgt = int(tgt_str.strip()) - 1
        src_str = src_str.strip()

        if "-" in src_str:
            s_start, s_end = src_str.split("-", 1)

            for s in range(
                int(s_start.strip()),
                int(s_end.strip()) + 1,
            ):
                rules.append((s - 1, tgt))
                tgt += 1
        else:
            rules.append((int(src_str.strip()) - 1, tgt))

    return rules


def _safe_dir(path: Path) -> Path:
    """目录重名时自动添加 (1)、(2)..."""
    if not path.exists():
        return path

    index = 1
    while True:
        new_path = path.parent / f"{path.name}({index})"
        if not new_path.exists():
            return new_path
        index += 1


def create_view(page: ft.Page) -> ft.Control:
    async def _run_thread_with_events(worker, on_event):
        """
        在工作线程执行同步任务，并把事件交回 Flet asyncio/UI 线程。
        worker 接收一个 emit 函数：emit(event)。
        """
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

    pickers = {
        "merge": ft.FilePicker(),
        "split": ft.FilePicker(),
        "reorder": ft.FilePicker(),
        "p2i": ft.FilePicker(),
        "i2p": ft.FilePicker(),
        "extract": ft.FilePicker(),
        "out_dir": ft.FilePicker(),
    }

    for picker in pickers.values():
        page.services.append(picker)

    # ==========================================================
    # 空列表显示提示，避免出现空白小色块
    # ==========================================================
    def _render_sortable_list(
        state_list: list,
        list_container: ft.Column,
        empty_hint: str = "暂无文件，请先添加",
    ):
        list_container.controls.clear()

        if not state_list:
            list_container.controls.append(
                ft.Text(
                    empty_hint,
                    italic=True,
                    color=ft.Colors.GREY_500,
                    size=13,
                )
            )
            page.update()
            return

        for i, path in enumerate(state_list):
            def make_move_up(idx):
                def _up(e):
                    state_list[idx], state_list[idx - 1] = (
                        state_list[idx - 1],
                        state_list[idx],
                    )
                    _render_sortable_list(
                        state_list,
                        list_container,
                        empty_hint,
                    )
                return _up

            def make_move_down(idx):
                def _down(e):
                    state_list[idx], state_list[idx + 1] = (
                        state_list[idx + 1],
                        state_list[idx],
                    )
                    _render_sortable_list(
                        state_list,
                        list_container,
                        empty_hint,
                    )
                return _down

            def make_delete(idx):
                def _del(e):
                    state_list.pop(idx)
                    _render_sortable_list(
                        state_list,
                        list_container,
                        empty_hint,
                    )
                return _del

            list_container.controls.append(
                ft.Row([
                    ft.Text(
                        f"{i + 1}. {Path(path).name}",
                        expand=True,
                        no_wrap=True,
                    ),
                    ft.IconButton(
                        ft.Icons.ARROW_UPWARD,
                        on_click=make_move_up(i),
                        disabled=(i == 0),
                    ),
                    ft.IconButton(
                        ft.Icons.ARROW_DOWNWARD,
                        on_click=make_move_down(i),
                        disabled=(i == len(state_list) - 1),
                    ),
                    ft.IconButton(
                        ft.Icons.DELETE,
                        on_click=make_delete(i),
                        icon_color=ft.Colors.RED_500,
                    ),
                ])
            )

        page.update()

    # ==========================================
    # Tab 1：结构处理
    # ==========================================
    merge_state = {"paths": [], "out_dir": None}
    merge_list_ui = ft.Column()
    merge_out_text = ft.Text(
        "📁 默认保存至首个文件同级目录",
        color=ft.Colors.GREY_500,
    )

    split_state = {"path": None, "out_dir": None}
    split_text = ft.Text("未选择", color=ft.Colors.GREY_500)
    split_out_text = ft.Text(
        "📁 默认保存至原文件同级目录",
        color=ft.Colors.GREY_500,
    )

    reorder_state = {"path": None, "out_dir": None}
    reorder_text = ft.Text("未选择", color=ft.Colors.GREY_500)
    reorder_out_text = ft.Text(
        "📁 默认保存至原文件同级目录",
        color=ft.Colors.GREY_500,
    )

    split_input = ft.TextField(
        label="提取页码 (如: 1,3,5-7)",
        expand=True,
        dense=True,
    )

    reorder_input = ft.TextField(
        label="重排规则 (如: 8>2, 50-54>21)",
        expand=True,
        dense=True,
    )

    struct_status = ft.Text("", size=14)

    async def on_pick_merge(e):
        files = await pickers["merge"].pick_files(
            allow_multiple=True,
            allowed_extensions=["pdf"],
        )

        if files:
            merge_state["paths"].extend([f.path for f in files])
            _render_sortable_list(
                merge_state["paths"],
                merge_list_ui,
                "暂无文件，请点击「添加 PDF 文件」",
            )

    async def on_pick_split(e):
        files = await pickers["split"].pick_files(
            allowed_extensions=["pdf"]
        )

        if files:
            split_state["path"] = files[0].path
            split_text.value = f"📄 {Path(files[0].path).name}"
            page.update()

    async def on_pick_reorder(e):
        files = await pickers["reorder"].pick_files(
            allowed_extensions=["pdf"]
        )

        if files:
            reorder_state["path"] = files[0].path
            reorder_text.value = f"📄 {Path(files[0].path).name}"
            page.update()

    async def on_pick_out_dir(e, state_dict, text_ui):
        dir_path = await pickers["out_dir"].get_directory_path()

        if dir_path:
            state_dict["out_dir"] = dir_path
            text_ui.value = f"📁 输出至: {dir_path}"
            page.update()

    def run_struct_task(action_type):
        struct_status.value = "⏳ 正在处理中..."
        struct_status.color = ft.Colors.ORANGE_500
        page.update()

        async def _task():
            try:
                if action_type == "merge":
                    if len(merge_state["paths"]) < 2:
                        raise ValueError("至少需要2个PDF文件")

                    out_dir = (
                        Path(merge_state["out_dir"])
                        if merge_state["out_dir"]
                        else Path(merge_state["paths"][0]).parent
                    )

                    out_path = safe_output_path(
                        out_dir / "merged_output.pdf"
                    )

                    out_path = await asyncio.to_thread(
                        merge_pdfs,
                        merge_state["paths"],
                        out_path,
                    )

                elif action_type == "split":
                    if not split_state["path"]:
                        raise ValueError("未选择 PDF")

                    pages = _parse_page_ranges(split_input.value)

                    if not pages:
                        raise ValueError("提取页码无效")

                    out_dir = (
                        Path(split_state["out_dir"])
                        if split_state["out_dir"]
                        else Path(split_state["path"]).parent
                    )

                    out_path = safe_output_path(
                        out_dir
                        / f"{Path(split_state['path']).stem}_extracted.pdf"
                    )

                    out_path = await asyncio.to_thread(
                        split_pdf,
                        split_state["path"],
                        out_path,
                        pages,
                    )

                elif action_type == "reorder":
                    if not reorder_state["path"]:
                        raise ValueError("未选择 PDF")

                    rules = _parse_move_rules(reorder_input.value)

                    if not rules:
                        raise ValueError("规则为空")

                    out_dir = (
                        Path(reorder_state["out_dir"])
                        if reorder_state["out_dir"]
                        else Path(reorder_state["path"]).parent
                    )

                    out_path = safe_output_path(
                        out_dir
                        / f"{Path(reorder_state['path']).stem}_reordered.pdf"
                    )

                    out_path = await asyncio.to_thread(
                        multi_move_pages,
                        reorder_state["path"],
                        out_path,
                        rules,
                    )

                else:
                    raise ValueError(f"未知操作: {action_type}")

                struct_status.value = f"✅ 成功:\n{out_path}"
                struct_status.color = ft.Colors.GREEN_500

            except Exception as ex:
                struct_status.value = f"❌ 失败: {ex}"
                struct_status.color = ft.Colors.RED_500

            finally:
                page.update()

        page.run_task(_task)

    _render_sortable_list(
        merge_state["paths"],
        merge_list_ui,
        "暂无文件，请点击「添加 PDF 文件」",
    )

    struct_content = ft.Container(
        padding=20,
        content=ft.Column([
            ft.Text(
                "✂️ 页面与结构调整",
                size=24,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Divider(),
            ft.Row([
                ft.ElevatedButton(
                    "添加 PDF 文件 (合并)",
                    icon=ft.Icons.LIBRARY_ADD,
                    on_click=lambda e: page.run_task(
                        on_pick_merge,
                        e,
                    ),
                ),
                ft.ElevatedButton(
                    "更改输出目录",
                    icon=ft.Icons.FOLDER,
                    on_click=lambda e: page.run_task(
                        on_pick_out_dir,
                        e,
                        merge_state,
                        merge_out_text,
                    ),
                ),
                merge_out_text,
            ]),
            ft.Container(
                content=merge_list_ui,
                bgcolor=ft.Colors.GREY_100,
                border_radius=8,
                padding=10,
            ),
            ft.ElevatedButton(
                "🚀 按照以上顺序合并",
                on_click=lambda _: run_struct_task("merge"),
            ),
            ft.Divider(height=30),
            ft.Row([
                ft.ElevatedButton(
                    "选择 PDF (拆分)",
                    icon=ft.Icons.PICTURE_AS_PDF,
                    on_click=lambda e: page.run_task(
                        on_pick_split,
                        e,
                    ),
                ),
                split_text,
                ft.ElevatedButton(
                    "更改输出目录",
                    icon=ft.Icons.FOLDER,
                    on_click=lambda e: page.run_task(
                        on_pick_out_dir,
                        e,
                        split_state,
                        split_out_text,
                    ),
                ),
                split_out_text,
            ]),
            ft.Row([
                split_input,
                ft.ElevatedButton(
                    "提取页面",
                    on_click=lambda _: run_struct_task("split"),
                ),
            ]),
            ft.Divider(height=30),
            ft.Row([
                ft.ElevatedButton(
                    "选择 PDF (重排)",
                    icon=ft.Icons.SWAP_VERT,
                    on_click=lambda e: page.run_task(
                        on_pick_reorder,
                        e,
                    ),
                ),
                reorder_text,
                ft.ElevatedButton(
                    "更改输出目录",
                    icon=ft.Icons.FOLDER,
                    on_click=lambda e: page.run_task(
                        on_pick_out_dir,
                        e,
                        reorder_state,
                        reorder_out_text,
                    ),
                ),
                reorder_out_text,
            ]),
            ft.Row([
                reorder_input,
                ft.ElevatedButton(
                    "调整顺序",
                    on_click=lambda _: run_struct_task("reorder"),
                ),
            ]),
            ft.Divider(),
            struct_status,
        ], scroll=ft.ScrollMode.AUTO),
    )

    # ==========================================
    # Tab 2：格式互转
    # ==========================================
    p2i_state = {"path": None, "out_dir": None}
    i2p_state = {"paths": [], "out_dir": None}

    p2i_text = ft.Text("未选择", color=ft.Colors.GREY_500)
    p2i_out_text = ft.Text(
        "📁 默认输出至原文件同级目录",
        color=ft.Colors.GREY_500,
    )
    i2p_list_ui = ft.Column()
    i2p_out_text = ft.Text(
        "📁 默认输出至首个图片同级目录",
        color=ft.Colors.GREY_500,
    )
    cvt_status = ft.Text("", size=14)
    p2i_pages_input = ft.TextField(
        label="提取页码 (如: 1,3,5-7，留空转换全部)",
        expand=True,
        dense=True,
    )

    async def on_pick_p2i(e):
        files = await pickers["p2i"].pick_files(
            allowed_extensions=["pdf"]
        )

        if files:
            p2i_state["path"] = files[0].path
            p2i_text.value = f"📄 {Path(files[0].path).name}"
            page.update()

    async def on_pick_i2p(e):
        files = await pickers["i2p"].pick_files(
            allow_multiple=True,
            allowed_extensions=["png", "jpg", "jpeg", "bmp", "webp"],
        )

        if files:
            i2p_state["paths"].extend([f.path for f in files])

            _render_sortable_list(
                i2p_state["paths"],
                i2p_list_ui,
                "暂无图片，请点击「选择图片」",
            )

    def run_cvt_task(action_type):
        cvt_status.value = "⏳ 正在转换中..."
        cvt_status.color = ft.Colors.ORANGE_500
        page.update()

        async def _task():
            try:
                if action_type == "p2i":
                    if not p2i_state["path"]:
                        raise ValueError("未选择 PDF")

                    pdf_path = Path(p2i_state["path"])
                    pages = _parse_page_ranges(p2i_pages_input.value)

                    if p2i_state["out_dir"]:
                        out_dir = Path(p2i_state["out_dir"])
                    else:
                        out_dir = _safe_dir(
                            pdf_path.parent / f"{pdf_path.stem}_images"
                        )

                    out = await asyncio.to_thread(
                        pdf_to_images,
                        pdf_path,
                        out_dir,
                        pages=pages,
                    )

                    cvt_status.value = f"✅ 生成了 {len(out)} 张图"

                elif action_type == "i2p":
                    if not i2p_state["paths"]:
                        raise ValueError("未选择图片")

                    out_dir = (
                        Path(i2p_state["out_dir"])
                        if i2p_state["out_dir"]
                        else Path(i2p_state["paths"][0]).parent
                    )

                    out_path = safe_output_path(
                        out_dir / "images_merged.pdf"
                    )

                    out = await asyncio.to_thread(
                        images_to_pdf,
                        i2p_state["paths"],
                        out_path,
                    )

                    cvt_status.value = f"✅ 合成成功:\n{out}"

                else:
                    raise ValueError(f"未知操作: {action_type}")

                cvt_status.color = ft.Colors.GREEN_500

            except Exception as ex:
                cvt_status.value = f"❌ 失败: {ex}"
                cvt_status.color = ft.Colors.RED_500

            finally:
                page.update()

        page.run_task(_task)

    _render_sortable_list(
        i2p_state["paths"],
        i2p_list_ui,
        "暂无图片，请点击「选择图片」",
    )

    convert_content = ft.Container(
        padding=20,
        content=ft.Column([
            ft.Text(
                "🔄 PDF 与图片无损互转",
                size=24,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Divider(),
            ft.Row([
                ft.ElevatedButton(
                    "选择 PDF",
                    icon=ft.Icons.PICTURE_AS_PDF,
                    on_click=lambda e: page.run_task(
                        on_pick_p2i,
                        e,
                    ),
                ),
                p2i_text,
                ft.ElevatedButton(
                    "更改输出目录",
                    icon=ft.Icons.FOLDER,
                    on_click=lambda e: page.run_task(
                        on_pick_out_dir,
                        e,
                        p2i_state,
                        p2i_out_text,
                    ),
                ),
                p2i_out_text,
            ]),
            ft.Row([
                p2i_pages_input,
                ft.ElevatedButton(
                    "🚀 开始 PDF 转图片",
                    on_click=lambda _: run_cvt_task("p2i"),
                ),
            ]),
            ft.Divider(height=30),
            ft.Row([
                ft.ElevatedButton(
                    "选择图片",
                    icon=ft.Icons.PHOTO_LIBRARY,
                    on_click=lambda e: page.run_task(
                        on_pick_i2p,
                        e,
                    ),
                ),
                ft.ElevatedButton(
                    "更改输出目录",
                    icon=ft.Icons.FOLDER,
                    on_click=lambda e: page.run_task(
                        on_pick_out_dir,
                        e,
                        i2p_state,
                        i2p_out_text,
                    ),
                ),
                i2p_out_text,
            ]),
            ft.Container(
                content=i2p_list_ui,
                bgcolor=ft.Colors.GREY_100,
                border_radius=8,
                padding=10,
            ),
            ft.ElevatedButton(
                "🚀 开始图片转 PDF",
                on_click=lambda _: run_cvt_task("i2p"),
            ),
            ft.Divider(),
            cvt_status,
        ], scroll=ft.ScrollMode.AUTO),
    )

    # ==========================================
    # Tab 3：提取文本（支持多选 PDF + 进度 + 停止）
    # ==========================================
    ext_state = {
        "paths": [],
        "out_dir": None,
        "cancel_flag": False,
    }

    ext_list_ui = ft.Column(spacing=2)
    ext_out_text = ft.Text(
        "📁 默认各自保存至原文件同级目录",
        color=ft.Colors.GREY_500,
    )
    ext_status = ft.Text("", size=14)
    ext_progress = ft.ProgressBar(value=0, visible=False)

    ext_start_btn = ft.ElevatedButton(
        "🚀 开始提取纯文本",
        icon=ft.Icons.TEXT_SNIPPET,
    )

    ext_stop_btn = ft.Button(
        content=ft.Text("停止"),
        icon=ft.Icons.STOP,
        visible=False,
        bgcolor=ft.Colors.RED_50,
        color=ft.Colors.RED_900,
    )

    def _render_ext_list():
        ext_list_ui.controls.clear()

        if not ext_state["paths"]:
            ext_list_ui.controls.append(
                ft.Text(
                    "暂无文件，请点击「选择 PDF」",
                    italic=True,
                    color=ft.Colors.GREY_500,
                    size=13,
                )
            )
            page.update()
            return

        for i, path in enumerate(ext_state["paths"]):
            def make_delete(idx):
                def _del(e):
                    ext_state["paths"].pop(idx)
                    _render_ext_list()
                return _del

            ext_list_ui.controls.append(
                ft.Row([
                    ft.Text(
                        f"{i + 1}. {Path(path).name}",
                        expand=True,
                        no_wrap=True,
                    ),
                    ft.IconButton(
                        ft.Icons.DELETE,
                        icon_size=18,
                        on_click=make_delete(i),
                        icon_color=ft.Colors.RED_500,
                    ),
                ])
            )

        page.update()

    async def on_pick_ext(e):
        files = await pickers["extract"].pick_files(
            allow_multiple=True,
            allowed_extensions=["pdf"],
        )

        if files:
            ext_state["paths"].extend([f.path for f in files])
            _render_ext_list()

    def stop_ext_click(e):
        ext_state["cancel_flag"] = True
        ext_stop_btn.disabled = True
        page.update()

    ext_stop_btn.on_click = stop_ext_click

    def run_ext_task(e):
        if not ext_state["paths"]:
            ext_status.value = "❌ 请先选择至少一个 PDF"
            ext_status.color = ft.Colors.RED_500
            page.update()
            return

        ext_state["cancel_flag"] = False
        ext_start_btn.disabled = True
        ext_stop_btn.visible = True
        ext_stop_btn.disabled = False
        ext_progress.visible = True
        ext_progress.value = 0
        ext_status.value = "⏳ 正在提取..."
        ext_status.color = ft.Colors.ORANGE_500
        page.update()

        def handle_event(event):
            current, total = event
            fraction = current / total if total else 0

            ext_progress.value = fraction
            ext_status.value = (
                f"⏳ 提取中 {current}/{total} "
                f"({fraction * 100:.1f}%)"
            )
            page.update()

        async def _task():
            try:
                results = await _run_thread_with_events(
                    lambda emit: extract_text_batch(
                        ext_state["paths"],
                        output_dir=ext_state["out_dir"],
                        progress_callback=lambda current, total: emit(
                            (current, total)
                        ),
                        cancel_check=lambda: ext_state["cancel_flag"],
                    ),
                    handle_event,
                )

                ext_progress.value = 1
                ext_status.value = (
                    f"✅ 提取完成，共 {len(results)} 个文件"
                )
                ext_status.color = ft.Colors.GREEN_500

            except InterruptedError as ex:
                ext_status.value = f"⏹️ 已取消：{ex}"
                ext_status.color = ft.Colors.ORANGE_500

            except Exception as ex:
                ext_status.value = f"❌ 失败: {ex}"
                ext_status.color = ft.Colors.RED_500

            finally:
                ext_start_btn.disabled = False
                ext_stop_btn.visible = False
                page.update()

        page.run_task(_task)

    ext_start_btn.on_click = run_ext_task
    _render_ext_list()

    extract_content = ft.Container(
        padding=20,
        content=ft.Column([
            ft.Text(
                "📝 PDF 全文文本提取",
                size=24,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Text(
                "支持一次选择多个 PDF 批量提取，每个文件生成同名 _text.txt",
                color=ft.Colors.GREY_500,
            ),
            ft.Divider(),
            ft.Row([
                ft.ElevatedButton(
                    "选择 PDF（可多选）",
                    icon=ft.Icons.PICTURE_AS_PDF,
                    on_click=lambda e: page.run_task(
                        on_pick_ext,
                        e,
                    ),
                ),
                ft.ElevatedButton(
                    "更改输出目录",
                    icon=ft.Icons.FOLDER,
                    on_click=lambda e: page.run_task(
                        on_pick_out_dir,
                        e,
                        ext_state,
                        ext_out_text,
                    ),
                ),
                ext_out_text,
            ]),
            ft.Container(
                content=ext_list_ui,
                bgcolor=ft.Colors.GREY_100,
                border_radius=8,
                padding=10,
            ),
            ft.Row([ext_start_btn, ext_stop_btn]),
            ext_progress,
            ext_status,
        ], scroll=ft.ScrollMode.AUTO),
    )

    return ft.Tabs(
        length=3,
        selected_index=0,
        expand=True,
        content=ft.Column(
            expand=True,
            controls=[
                ft.TabBar(tabs=[
                    ft.Tab(
                        icon=ft.Icons.ACCOUNT_TREE_OUTLINED,
                        label="结构处理",
                    ),
                    ft.Tab(
                        icon=ft.Icons.SYNC_ALT,
                        label="格式互转",
                    ),
                    ft.Tab(
                        icon=ft.Icons.FIND_IN_PAGE_OUTLINED,
                        label="提取文本",
                    ),
                ]),
                ft.TabBarView(
                    expand=True,
                    controls=[
                        struct_content,
                        convert_content,
                        extract_content,
                    ],
                ),
            ],
        ),
    )