# ui/flet_ui/views/transfer_view.py

import asyncio
import base64
import os
import platform
import subprocess
from io import BytesIO
from pathlib import Path

import flet as ft
import qrcode

from tools.transfer.receiver import ReceiverNode, TransferConfig, event_queue
from tools.transfer.sender import SenderNode
from tools.network.node import NodeIdentity


def generate_qr_base64(data: str) -> str:
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()


def open_transfer_dir(e=None):
    target = str(TransferConfig.save_dir)

    try:
        if platform.system() == "Windows":
            os.startfile(target)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
    except Exception:
        pass


def create_view(page: ft.Page) -> ft.Control:
    for service in list(page.services):
        if isinstance(service, ft.FilePicker):
            page.services.remove(service)

    pickers = {
        "send_file": ft.FilePicker(),
        "save_dir": ft.FilePicker(),
    }

    for picker in pickers.values():
        page.services.append(picker)

    state = {
        "node": None,
        "online": False,
        "send_files": [],
    }

    # ======================================================
    # 顶部：服务器控制与状态
    # ======================================================
    btn_toggle = ft.ElevatedButton(
        "启动传送服务",
        icon=ft.Icons.ROCKET_LAUNCH,
        width=200,
    )

    status_text = ft.Text(
        "当前状态: 离线",
        color=ft.Colors.GREY_500,
        size=16,
    )

    url_text = ft.Text(
        "",
        selectable=True,
        size=14,
        color=ft.Colors.BLUE_600,
    )

    qr_image = ft.Image(
        src="",
        width=160,
        height=160,
        visible=False,
    )

    qr_container = ft.Container(
        content=qr_image,
        bgcolor=ft.Colors.WHITE,
        padding=10,
        border_radius=12,
        visible=False,
    )

    def toggle_node(e):
        if state["online"]:
            if state["node"]:
                state["node"].stop_listening()

            state["node"] = None
            state["online"] = False

            btn_toggle.text = "启动传送服务"
            btn_toggle.icon = ft.Icons.ROCKET_LAUNCH
            status_text.value = "当前状态: 离线"
            status_text.color = ft.Colors.GREY_500
            qr_container.visible = qr_image.visible = False
            url_text.value = ""

        else:
            ip = NodeIdentity.get_local_ip()
            state["node"] = ReceiverNode(port=8000)
            token = state["node"].start_listening()
            state["online"] = True

            url = f"http://{ip}:8000/?token={token}"

            btn_toggle.text = "关闭传送服务"
            btn_toggle.icon = ft.Icons.STOP_CIRCLE
            status_text.value = "🟢 运行中，请用手机扫码"
            status_text.color = ft.Colors.GREEN_600

            qr_image.src = (
                "data:image/png;base64," + generate_qr_base64(url)
            )
            qr_image.visible = qr_container.visible = True
            url_text.value = url

        page.update()

    btn_toggle.on_click = toggle_node

    top_panel = ft.Container(
        padding=20,
        border_radius=12,
        bgcolor=ft.Colors.GREY_100,
        content=ft.Row([
            ft.Column([
                ft.Text(
                    "⚡ 万象传送阵",
                    size=24,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(
                    "电脑开局域网服务，手机扫码直连，动态 Token 保护",
                    color=ft.Colors.GREY_600,
                ),
                ft.Container(height=10),
                ft.Row([btn_toggle, status_text]),
                url_text,
            ], expand=True, alignment=ft.MainAxisAlignment.CENTER),
            qr_container,
        ]),
    )

    # ======================================================
    # 左侧：电脑发送至手机
    # ======================================================
    send_text_input = ft.TextField(
        label="输入文本",
        multiline=True,
        min_lines=3,
        max_lines=3,
    )

    send_files_summary = ft.Text(
        "未选择文件",
        color=ft.Colors.GREY_500,
        expand=True,
        no_wrap=True,
        overflow=ft.TextOverflow.ELLIPSIS,
    )

    send_files_list_ui = ft.Column(spacing=2)
    send_status = ft.Text("", size=14)

    def _render_send_files_list():
        send_files_list_ui.controls.clear()

        if not state["send_files"]:
            send_files_list_ui.controls.append(
                ft.Text(
                    "暂无文件，请点击「选择文件」",
                    italic=True,
                    color=ft.Colors.GREY_500,
                    size=13,
                )
            )

        else:
            for i, path in enumerate(state["send_files"]):
                def make_remove(idx):
                    def _remove(e):
                        state["send_files"].pop(idx)
                        _render_send_files_list()
                    return _remove

                send_files_list_ui.controls.append(
                    ft.Row([
                        ft.Text(
                            f"📄 {Path(path).name}",
                            expand=True,
                            no_wrap=True,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            size=13,
                        ),
                        ft.IconButton(
                            ft.Icons.CLOSE,
                            icon_size=16,
                            on_click=make_remove(i),
                        ),
                    ])
                )

        count = len(state["send_files"])
        send_files_summary.value = (
            f"已选择 {count} 个文件"
            if count
            else "未选择文件"
        )

        page.update()

    _render_send_files_list()

    async def pick_send_file(e):
        files = await pickers["send_file"].pick_files(
            allow_multiple=True
        )

        if files:
            state["send_files"].extend([f.path for f in files])
            _render_send_files_list()

    async def send_action(action):
        if not state["online"]:
            send_status.value = "❌ 请先启动闪传服务"
            send_status.color = ft.Colors.RED_500
            page.update()
            return

        try:
            if action == "text":
                # 文本发送通常很快，不需要额外线程。
                await asyncio.to_thread(
                    SenderNode.send_text,
                    send_text_input.value,
                )

                send_status.value = "✅ 文本已发送至网页端"
                send_status.color = ft.Colors.GREEN
                send_text_input.value = ""

            elif action == "file":
                if not state["send_files"]:
                    raise ValueError("请先选择文件")

                files = list(state["send_files"])

                send_status.value = "⏳ 正在发送文件..."
                send_status.color = ft.Colors.ORANGE_500
                page.update()

                sent_names = await asyncio.to_thread(
                    SenderNode.send_files,
                    files,
                )

                if not sent_names:
                    raise ValueError(
                        "所选文件均已失效，请重新选择"
                    )

                if len(sent_names) < len(files):
                    send_status.value = (
                        f"⚠️ 已发送 {len(sent_names)} 个文件，"
                        f"{len(files) - len(sent_names)} 个文件无效已跳过"
                    )
                    send_status.color = ft.Colors.ORANGE
                else:
                    send_status.value = (
                        f"✅ 已发送 {len(sent_names)} 个文件，请在手机网页下载"
                    )
                    send_status.color = ft.Colors.GREEN

                state["send_files"] = []
                _render_send_files_list()
                return

            else:
                raise ValueError(f"未知操作: {action}")

        except Exception as ex:
            send_status.value = f"❌ {ex}"
            send_status.color = ft.Colors.RED_500

        page.update()

    left_send_col = ft.Column([
        ft.Text(
            "📤 电脑发送至手机",
            size=20,
            weight=ft.FontWeight.BOLD,
        ),
        ft.Divider(),
        ft.Text("文本发送", weight=ft.FontWeight.BOLD),
        send_text_input,
        ft.ElevatedButton(
            "发送文本",
            icon=ft.Icons.SEND,
            on_click=lambda e: page.run_task(
                send_action,
                "text",
            ),
        ),
        ft.Divider(
            height=20,
            color=ft.Colors.TRANSPARENT,
        ),
        ft.Text(
            "文件分享（支持多选）",
            weight=ft.FontWeight.BOLD,
        ),
        ft.Row([
            ft.ElevatedButton(
                "选择文件",
                icon=ft.Icons.FILE_OPEN,
                on_click=lambda e: page.run_task(
                    pick_send_file,
                    e,
                ),
            ),
            send_files_summary,
        ]),
        ft.Container(
            content=send_files_list_ui,
            bgcolor=ft.Colors.GREY_100,
            border_radius=8,
            padding=8,
        ),
        ft.ElevatedButton(
            "发送文件",
            icon=ft.Icons.UPLOAD,
            bgcolor=ft.Colors.GREEN_50,
            color=ft.Colors.GREEN_900,
            on_click=lambda e: page.run_task(
                send_action,
                "file",
            ),
        ),
        ft.Container(height=10),
        send_status,
    ], expand=True)

    # ======================================================
    # 右侧：电脑接收手机消息
    # ======================================================
    received_text = ft.TextField(
        multiline=True,
        read_only=True,
        min_lines=3,
        max_lines=3,
        expand=True,
    )

    receive_status = ft.Text("", size=14)
    received_files_list = ft.Column(spacing=4)

    save_dir_text = ft.Text(
        f"{TransferConfig.save_dir.resolve()}",
        color=ft.Colors.BLUE_600,
        selectable=True,
    )

    async def pick_save_dir(e):
        path = await pickers["save_dir"].get_directory_path()

        if path:
            TransferConfig.save_dir = Path(path)
            save_dir_text.value = (
                f"{TransferConfig.save_dir.resolve()}"
            )
            page.update()

    async def copy_received_text(e):
        if not received_text.value:
            return

        try:
            clipboard = ft.Clipboard()
            await clipboard.set(received_text.value)
            receive_status.value = "✅ 已复制到剪贴板"
            receive_status.color = ft.Colors.GREEN

        except Exception as ex:
            receive_status.value = f"❌ 复制失败: {ex}"
            receive_status.color = ft.Colors.RED_500

        page.update()

    async def consume_phone_events():
        while True:
            changed = False

            while not event_queue.empty():
                event = event_queue.get()

                if event["type"] == "text":
                    received_text.value = event["data"]
                    receive_status.value = "✅ 收到手机文本"
                    receive_status.color = ft.Colors.GREEN
                    changed = True

                elif event["type"] == "file":
                    fname = Path(event["data"]).name

                    received_files_list.controls.insert(
                        0,
                        ft.Text(
                            f"📄 {fname}",
                            size=13,
                        ),
                    )

                    if len(received_files_list.controls) > 5:
                        received_files_list.controls.pop()

                    receive_status.value = f"✅ 收到文件: {fname}"
                    receive_status.color = ft.Colors.GREEN
                    changed = True

            if changed:
                page.update()

            await asyncio.sleep(0.2)

    page.run_task(consume_phone_events)

    right_receive_col = ft.Column([
        ft.Text(
            "📥 手机发送至电脑",
            size=20,
            weight=ft.FontWeight.BOLD,
        ),
        ft.Divider(),
        ft.Row([
            ft.Text("收到文本", weight=ft.FontWeight.BOLD),
            ft.Container(expand=True),
            ft.IconButton(
                ft.Icons.COPY,
                tooltip="复制",
                on_click=lambda e: page.run_task(
                    copy_received_text,
                    e,
                ),
            ),
        ]),
        received_text,
        ft.Divider(
            height=20,
            color=ft.Colors.TRANSPARENT,
        ),
        ft.Row([
            ft.Text(
                "文件接收目录",
                weight=ft.FontWeight.BOLD,
            ),
            ft.Container(expand=True),
            ft.IconButton(
                icon=ft.Icons.FOLDER,
                tooltip="修改保存目录",
                on_click=lambda e: page.run_task(
                    pick_save_dir,
                    e,
                ),
            ),
            ft.ElevatedButton(
                "打开目录",
                icon=ft.Icons.FOLDER_OPEN,
                on_click=open_transfer_dir,
            ),
        ]),
        save_dir_text,
        ft.Container(height=10),
        receive_status,
        ft.Text(
            "最近收到的文件",
            weight=ft.FontWeight.BOLD,
            size=13,
        ),
        received_files_list,
    ], expand=True)

    return ft.Container(
        padding=20,
        expand=True,
        content=ft.Column([
            top_panel,
            ft.Divider(
                height=30,
                color=ft.Colors.TRANSPARENT,
            ),
            ft.ResponsiveRow([
                ft.Container(
                    left_send_col,
                    col={"xs": 12, "md": 6},
                    padding=ft.Padding.only(right=10),
                ),
                ft.Container(
                    right_receive_col,
                    col={"xs": 12, "md": 6},
                    padding=ft.Padding.only(left=10),
                ),
            ]),
        ], expand=True, scroll=ft.ScrollMode.AUTO),
    )