# ui/pyside6/views/transfer_view.py

import os
import platform
import subprocess
from io import BytesIO
from pathlib import Path

import qrcode
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QTextEdit, QListWidget, QListWidgetItem, QApplication, QFrame,
)

from tools.transfer.receiver import ReceiverNode, TransferConfig, event_queue
from tools.transfer.sender import SenderNode
from tools.network.node import NodeIdentity

from ui.pyside6.widgets import DropArea, card, make_clear_button
from ui.pyside6.theme import set_status, set_muted, style_primary, section_title_style

VIDEO_LIKE_ANY_FILTER = ""  # 发送文件不限制扩展名


def _generate_qr_pixmap(data: str) -> QPixmap:
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    pixmap = QPixmap()
    pixmap.loadFromData(buf.getvalue(), "PNG")
    return pixmap


def _open_transfer_dir():
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


class TransferView(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        self.state = {"node": None, "online": False, "send_files": []}

        layout.addWidget(self._build_top_panel())

        columns = QHBoxLayout()
        columns.addWidget(self._build_send_panel(), stretch=1)
        columns.addWidget(self._build_receive_panel(), stretch=1)
        layout.addLayout(columns)
        layout.addStretch()

        # 手机 -> 电脑事件轮询：对应 Flet 版用 page.run_task 起的异步轮询任务，
        # 这里用 QTimer 定期检查 event_queue（线程安全的 queue.Queue）
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_phone_events)
        self.poll_timer.start(200)

    # ==========================================================
    # 顶部：服务器控制
    # ==========================================================
    def _build_top_panel(self) -> QFrame:
        title = QLabel("⚡ 万象传送阵")
        title.setStyleSheet(section_title_style())
        sub = QLabel()
        set_muted(sub, "电脑开局域网服务，手机扫码直连，动态 Token 保护")

        self.toggle_btn = QPushButton("启动传送服务")
        style_primary(self.toggle_btn)
        self.toggle_btn.clicked.connect(self._toggle_server)
        self.status_label = QLabel("当前状态: 离线")
        set_muted(self.status_label, "当前状态: 离线")

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.toggle_btn)
        btn_row.addWidget(self.status_label)
        btn_row.addStretch()

        self.url_label = QLabel("")
        self.url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.url_label.setStyleSheet("color: #2563EB;")

        left_col = QVBoxLayout()
        left_col.addWidget(title)
        left_col.addWidget(sub)
        left_col.addLayout(btn_row)
        left_col.addWidget(self.url_label)

        self.qr_label = QLabel()
        self.qr_label.setFixedSize(150, 150)
        self.qr_label.setStyleSheet("background: white; border-radius: 8px;")
        self.qr_label.setVisible(False)

        row = QHBoxLayout()
        row.addLayout(left_col, stretch=1)
        row.addWidget(self.qr_label)

        return card(row)

    def _toggle_server(self):
        if self.state["online"]:
            if self.state["node"]:
                self.state["node"].stop_listening()
            self.state["node"] = None
            self.state["online"] = False

            self.toggle_btn.setText("启动传送服务")
            set_muted(self.status_label, "当前状态: 离线")
            self.qr_label.setVisible(False)
            self.url_label.setText("")
        else:
            ip = NodeIdentity.get_local_ip()
            node = ReceiverNode(port=8000)
            token = node.start_listening()
            self.state["node"] = node
            self.state["online"] = True

            url = f"http://{ip}:8000/?token={token}"

            self.toggle_btn.setText("关闭传送服务")
            set_status(self.status_label, "🟢 运行中，请用手机扫码", "success")
            self.qr_label.setPixmap(_generate_qr_pixmap(url).scaled(150, 150))
            self.qr_label.setVisible(True)
            self.url_label.setText(url)

    # ==========================================================
    # 左侧：电脑发送至手机
    # ==========================================================
    def _build_send_panel(self) -> QFrame:
        title = QLabel("📤 电脑发送至手机")
        title.setStyleSheet(section_title_style(18))

        self.send_text_input = QTextEdit()
        self.send_text_input.setPlaceholderText("输入文本")
        self.send_text_input.setMaximumHeight(80)
        btn_send_text = QPushButton("发送文本")
        style_primary(btn_send_text)
        btn_send_text.clicked.connect(self._send_text)

        drop = DropArea("📥 拖拽或点击选择文件（支持多选）", self._on_send_files_dropped, mode="files")
        self.send_files_list = QListWidget()
        self.send_files_list.setMaximumHeight(110)
        self.send_files_list.itemDoubleClicked.connect(self._remove_send_file)

        btn_send_files = QPushButton("发送文件")
        style_primary(btn_send_files)
        btn_send_files.clicked.connect(self._send_files)
        btn_clear_send_files = make_clear_button(self.send_files_list, extra_clear=lambda: self.state["send_files"].clear())
        send_files_btn_row = QHBoxLayout()
        send_files_btn_row.addWidget(btn_send_files)
        send_files_btn_row.addWidget(btn_clear_send_files)
        send_files_btn_row.addStretch()

        self.send_status = QLabel("")
        self.send_status.setWordWrap(True)

        return card(
            title, self.send_text_input, btn_send_text,
            QLabel("文件分享（支持多选，双击列表项可移除单个，也可以一键清空）"),
            drop, self.send_files_list, send_files_btn_row, self.send_status,
        )

    def _on_send_files_dropped(self, paths: list[str]):
        for p in paths:
            self.state["send_files"].append(p)
            self.send_files_list.addItem(QListWidgetItem(f"📄 {Path(p).name}"))

    def _remove_send_file(self, item: QListWidgetItem):
        row = self.send_files_list.row(item)
        self.send_files_list.takeItem(row)
        self.state["send_files"].pop(row)

    def _send_text(self):
        if not self.state["online"]:
            set_status(self.send_status, "❌ 请先启动传送服务", "error")
            return
        text = self.send_text_input.toPlainText()
        try:
            SenderNode.send_text(text)
            set_status(self.send_status, "✅ 文本已发送至网页端", "success")
            self.send_text_input.clear()
        except Exception as ex:
            set_status(self.send_status, f"❌ {ex}", "error")

    def _send_files(self):
        if not self.state["online"]:
            set_status(self.send_status, "❌ 请先启动传送服务", "error")
            return
        if not self.state["send_files"]:
            set_status(self.send_status, "❌ 请先选择文件", "error")
            return

        sent_names = SenderNode.send_files(self.state["send_files"])
        total = len(self.state["send_files"])
        if not sent_names:
            set_status(self.send_status, "❌ 所选文件均已失效，请重新选择", "error")
        elif len(sent_names) < total:
            set_status(self.send_status, f"⚠️ 已发送 {len(sent_names)} 个文件，{total - len(sent_names)} 个文件无效已跳过", "warning")
        else:
            set_status(self.send_status, f"✅ 已发送 {len(sent_names)} 个文件，请在手机网页下载", "success")

        self.state["send_files"] = []
        self.send_files_list.clear()

    # ==========================================================
    # 右侧：电脑接收手机消息
    # ==========================================================
    def _build_receive_panel(self) -> QFrame:
        title = QLabel("📥 手机发送至电脑")
        title.setStyleSheet(section_title_style(18))

        self.received_text = QTextEdit()
        self.received_text.setReadOnly(True)
        self.received_text.setMaximumHeight(80)
        btn_copy = QPushButton("复制收到的文本")
        btn_copy.clicked.connect(self._copy_received_text)

        btn_change_dir = QPushButton("修改保存目录")
        btn_change_dir.clicked.connect(self._pick_save_dir)
        btn_open_dir = QPushButton("打开目录")
        btn_open_dir.clicked.connect(lambda: _open_transfer_dir())
        dir_btn_row = QHBoxLayout()
        dir_btn_row.addWidget(btn_change_dir)
        dir_btn_row.addWidget(btn_open_dir)
        dir_btn_row.addStretch()

        self.save_dir_label = QLabel(str(TransferConfig.save_dir.resolve()))
        self.save_dir_label.setStyleSheet("color: #2563EB;")
        self.save_dir_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.save_dir_label.setWordWrap(True)

        self.receive_status = QLabel("")
        self.receive_status.setWordWrap(True)

        self.received_files_list = QListWidget()
        self.received_files_list.setMaximumHeight(110)

        return card(
            title, self.received_text, btn_copy,
            QLabel("文件接收目录:"), dir_btn_row, self.save_dir_label,
            self.receive_status, QLabel("最近收到的文件:"), self.received_files_list,
        )

    def _copy_received_text(self):
        text = self.received_text.toPlainText()
        if not text:
            return
        QApplication.clipboard().setText(text)
        set_status(self.receive_status, "✅ 已复制到剪贴板", "success")

    def _pick_save_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if folder:
            TransferConfig.save_dir = Path(folder)
            self.save_dir_label.setText(str(TransferConfig.save_dir.resolve()))

    def _poll_phone_events(self):
        changed_text = False
        while not event_queue.empty():
            event = event_queue.get()
            if event["type"] == "text":
                self.received_text.setPlainText(event["data"])
                changed_text = True
            elif event["type"] == "file":
                fname = Path(event["data"]).name
                self.received_files_list.insertItem(0, QListWidgetItem(f"📄 {fname}"))
                while self.received_files_list.count() > 5:
                    self.received_files_list.takeItem(self.received_files_list.count() - 1)
                set_status(self.receive_status, f"✅ 收到文件: {fname}", "success")

        if changed_text:
            set_status(self.receive_status, "✅ 收到手机文本", "success")
