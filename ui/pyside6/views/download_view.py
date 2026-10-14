# ui/pyside6/views/download_view.py

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel, QPushButton,
    QFileDialog, QComboBox, QLineEdit, QCheckBox, QMessageBox,
)

from tools.multimedia.downloader import parse_video_info, download_video
from tools.wallpaper import download_wallpapers

from ui.pyside6.worker import TaskWorker
from ui.pyside6.widgets import card, wrap_scrollable, ProgressBar
from ui.pyside6.theme import set_status, set_muted, style_primary, style_stop, section_title_style


class DownloadView(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        tabs.addTab(wrap_scrollable(self._build_video_tab()), "🎬 视频下载")
        tabs.addTab(wrap_scrollable(self._build_wallpaper_tab()), "🖼️ 壁纸下载")

    # ==========================================================
    # Tab 1：视频全能下载器
    # ==========================================================
    def _build_video_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)

        self.video_state = {"formats": [], "title": "", "save_dir": None}
        self.parse_worker = None
        self.download_worker = None

        title = QLabel("🎬 视频全能下载器")
        title.setStyleSheet(section_title_style())
        outer.addWidget(title)
        sub = QLabel()
        set_muted(sub, "支持 B站 / YouTube / 抖音等平台")
        outer.addWidget(sub)

        url_row = QHBoxLayout()
        self.video_url_input = QLineEdit()
        self.video_url_input.setPlaceholderText("🔗 粘贴视频链接")
        self.parse_btn = QPushButton("解析视频")
        self.parse_btn.clicked.connect(self._parse_video)
        url_row.addWidget(self.video_url_input)
        url_row.addWidget(self.parse_btn)

        self.video_status = QLabel("")
        self.video_status.setWordWrap(True)

        self.format_combo = QComboBox()
        self.format_combo.setVisible(False)
        self.aria2_check = QCheckBox("使用 Aria2 加速")
        self.aria2_check.setVisible(False)
        format_row = QHBoxLayout()
        format_row.addWidget(self.format_combo, stretch=1)
        format_row.addWidget(self.aria2_check)

        self.choose_dir_btn = QPushButton("选择输出目录")
        self.choose_dir_btn.setVisible(False)
        self.choose_dir_btn.clicked.connect(self._pick_video_out_dir)
        self.save_path_label = QLabel("未选择保存目录")
        self.save_path_label.setVisible(False)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.choose_dir_btn)
        dir_row.addWidget(self.save_path_label)
        dir_row.addStretch()

        self.download_btn = QPushButton("开始下载")
        style_primary(self.download_btn)
        self.download_btn.setVisible(False)
        self.download_btn.clicked.connect(self._start_download)
        self.stop_download_btn = QPushButton("停止下载")
        style_stop(self.stop_download_btn)
        self.stop_download_btn.setVisible(False)
        self.stop_download_btn.clicked.connect(self._stop_download)
        dl_btn_row = QHBoxLayout()
        dl_btn_row.addWidget(self.download_btn)
        dl_btn_row.addWidget(self.stop_download_btn)
        dl_btn_row.addStretch()

        self.download_progress = ProgressBar()
        self.download_progress.setVisible(False)
        self.download_status = QLabel("")
        self.download_status.setWordWrap(True)

        outer.addWidget(card(
            url_row, self.video_status, format_row, dir_row,
            dl_btn_row, self.download_progress, self.download_status,
        ))
        outer.addStretch()
        return widget

    def _parse_video(self):
        url = self.video_url_input.text().strip()
        if not url:
            set_status(self.video_status, "❌ 请输入视频链接", "error")
            return

        self.parse_btn.setEnabled(False)
        set_status(self.video_status, "⏳ 正在解析视频...", "warning")

        worker = TaskWorker(parse_video_info, url)
        self.parse_worker = worker
        worker.finished_ok.connect(self._on_parse_finished)
        worker.failed.connect(self._on_parse_failed)
        worker.start()

    def _on_parse_finished(self, result):
        title, formats = result
        self.video_state["title"] = title
        self.video_state["formats"] = formats

        self.format_combo.clear()
        for fmt in formats:
            self.format_combo.addItem(fmt.display_name, fmt)
        self.format_combo.setVisible(True)
        self.aria2_check.setVisible(True)
        self.choose_dir_btn.setVisible(True)
        self.save_path_label.setVisible(True)
        self.download_btn.setVisible(True)

        set_status(self.video_status, f"✅ 解析成功: {title}", "success")
        self.parse_btn.setEnabled(True)

    def _on_parse_failed(self, message):
        set_status(self.video_status, f"❌ 解析失败: {message}", "error")
        self.parse_btn.setEnabled(True)

    def _pick_video_out_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if folder:
            self.video_state["save_dir"] = folder
            self.save_path_label.setText(f"📁 输出目录: {folder}")

    def _stop_download(self):
        if self.download_worker:
            self.download_worker.cancel()
            self.stop_download_btn.setEnabled(False)
            set_status(self.download_status, "⏳ 正在发送停止指令，请稍候...", "warning")

    def _start_download(self):
        if not self.video_state["save_dir"]:
            set_status(self.video_status, "❌ 请先选择输出目录", "error")
            return
        selected_format = self.format_combo.currentData()
        if not selected_format:
            set_status(self.video_status, "❌ 请先选择清晰度", "error")
            return

        worker = TaskWorker(
            download_video,
            video_format=selected_format,
            save_dir=self.video_state["save_dir"],
            title=self.video_state["title"],
            use_aria2=self.aria2_check.isChecked(),
            threads=4,
        )
        self.download_worker = worker

        self.download_btn.setEnabled(False)
        self.stop_download_btn.setVisible(True)
        self.stop_download_btn.setEnabled(True)
        self.download_progress.setVisible(True)
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(0)
        set_status(self.download_status, "准备下载...", "info")

        worker.progress.connect(self._on_download_progress)
        worker.finished_ok.connect(self._on_download_finished)
        worker.failed.connect(self._on_download_failed)
        worker.cancelled.connect(self._on_download_cancelled)
        worker.start()

    def _on_download_progress(self, data):
        # yt-dlp 风格的 hook 数据，字段含义跟 Flet 版 progress_hook 里解读的一致
        if not isinstance(data, dict):
            return
        if data.get("status") != "downloading":
            return
        total = data.get("total_bytes") or data.get("total_bytes_estimate")
        current = data.get("downloaded_bytes", 0)
        if total:
            fraction = current / total
            self.download_progress.setValue(int(fraction * 100))
            set_status(self.download_status, f"下载中 {fraction * 100:.1f}%", "info")
        else:
            set_status(self.download_status, f"下载中... 已下载 {current / (1024*1024):.1f}MB", "info")

    def _reset_download_buttons(self):
        self.download_btn.setEnabled(True)
        self.stop_download_btn.setVisible(False)
        self.download_worker = None

    def _on_download_finished(self, output):
        set_status(self.download_status, f"✅ 下载完成:\n{output}", "success")
        self._reset_download_buttons()

    def _on_download_failed(self, message):
        set_status(self.download_status, f"❌ 下载失败:\n{message}", "error")
        self._reset_download_buttons()

    def _on_download_cancelled(self):
        set_status(self.download_status, "⏹️ 下载已取消", "warning")
        self._reset_download_buttons()

    # ==========================================================
    # Tab 2：Bing 每日壁纸
    # ==========================================================
    def _build_wallpaper_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)

        self.wallpaper_state = {"save_dir": None}
        self.wallpaper_worker = None

        title = QLabel("🖼️ Bing 每日壁纸")
        title.setStyleSheet(section_title_style())
        outer.addWidget(title)
        sub = QLabel()
        set_muted(sub, "自动下载高清 Bing 壁纸，最多支持获取 8 个地区、8 天壁纸")
        outer.addWidget(sub)

        params_row = QHBoxLayout()
        self.wallpaper_days_input = QLineEdit("8")
        self.wallpaper_regions_input = QLineEdit("3")
        params_row.addWidget(QLabel("下载天数 (1-10):"))
        params_row.addWidget(self.wallpaper_days_input)
        params_row.addWidget(QLabel("地区数量 (1-8):"))
        params_row.addWidget(self.wallpaper_regions_input)
        params_row.addStretch()

        out_row = QHBoxLayout()
        btn_out = QPushButton("选择保存目录")
        btn_out.clicked.connect(self._pick_wallpaper_out_dir)
        self.wallpaper_path_label = QLabel()
        set_muted(self.wallpaper_path_label, "未选择保存目录")
        out_row.addWidget(btn_out)
        out_row.addWidget(self.wallpaper_path_label)
        out_row.addStretch()

        btn_row = QHBoxLayout()
        self.wallpaper_download_btn = QPushButton("开始下载壁纸")
        style_primary(self.wallpaper_download_btn)
        self.wallpaper_download_btn.clicked.connect(self._start_wallpaper_download)
        self.wallpaper_stop_btn = QPushButton("停止下载")
        style_stop(self.wallpaper_stop_btn)
        self.wallpaper_stop_btn.setVisible(False)
        self.wallpaper_stop_btn.clicked.connect(self._stop_wallpaper_download)
        btn_row.addWidget(self.wallpaper_download_btn)
        btn_row.addWidget(self.wallpaper_stop_btn)
        btn_row.addStretch()

        self.wallpaper_progress = ProgressBar()
        self.wallpaper_progress.setVisible(False)
        self.wallpaper_status = QLabel("")
        self.wallpaper_status.setWordWrap(True)

        outer.addWidget(card(
            params_row, out_row, btn_row, self.wallpaper_progress, self.wallpaper_status,
        ))
        outer.addStretch()
        return widget

    def _pick_wallpaper_out_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if folder:
            self.wallpaper_state["save_dir"] = folder
            self.wallpaper_path_label.setText(f"📁 输出目录: {folder}")

    def _stop_wallpaper_download(self):
        if self.wallpaper_worker:
            self.wallpaper_worker.cancel()
            self.wallpaper_stop_btn.setEnabled(False)
            set_status(self.wallpaper_status, "⏳ 正在发送停止指令...", "warning")

    def _start_wallpaper_download(self):
        if not self.wallpaper_state["save_dir"]:
            set_status(self.wallpaper_status, "❌ 请先选择输出目录", "error")
            return

        try:
            days = int(self.wallpaper_days_input.text())
            regions = int(self.wallpaper_regions_input.text())
        except ValueError:
            set_status(self.wallpaper_status, "❌ 天数和地区必须是纯数字", "error")
            return

        if not (1 <= regions <= 8):
            set_status(self.wallpaper_status, "❌ 地区数量必须在 1 到 8 之间", "error")
            return
        if not (1 <= days <= 10):
            set_status(self.wallpaper_status, "❌ 下载天数必须在 1 到 10 之间", "error")
            return

        worker = TaskWorker(
            download_wallpapers,
            region_count=regions, day_count=days,
            save_dir=Path(self.wallpaper_state["save_dir"]),
        )
        self.wallpaper_worker = worker

        self.wallpaper_download_btn.setEnabled(False)
        self.wallpaper_stop_btn.setVisible(True)
        self.wallpaper_stop_btn.setEnabled(True)
        self.wallpaper_progress.setVisible(True)
        self.wallpaper_progress.setRange(0, 100)
        self.wallpaper_progress.setValue(0)
        set_status(self.wallpaper_status, "⏳ 开始下载...", "warning")

        worker.log.connect(self._on_wallpaper_log)
        worker.progress.connect(self._on_wallpaper_progress)
        worker.finished_ok.connect(self._on_wallpaper_finished)
        worker.failed.connect(self._on_wallpaper_failed)
        worker.cancelled.connect(self._on_wallpaper_cancelled)
        worker.start()

    def _on_wallpaper_log(self, message):
        set_status(self.wallpaper_status, message, "warning")

    def _on_wallpaper_progress(self, value):
        if isinstance(value, tuple):
            current, total = value
            if total:
                self.wallpaper_progress.setValue(int(current / total * 100))

    def _reset_wallpaper_buttons(self):
        self.wallpaper_download_btn.setEnabled(True)
        self.wallpaper_stop_btn.setVisible(False)
        self.wallpaper_worker = None

    def _on_wallpaper_finished(self, _result):
        set_status(self.wallpaper_status, "✅ 壁纸下载完成", "success")
        self._reset_wallpaper_buttons()

    def _on_wallpaper_failed(self, message):
        set_status(self.wallpaper_status, f"❌ 下载失败: {message}", "error")
        self._reset_wallpaper_buttons()

    def _on_wallpaper_cancelled(self):
        set_status(self.wallpaper_status, "⏹️ 下载已取消", "warning")
        self._reset_wallpaper_buttons()
