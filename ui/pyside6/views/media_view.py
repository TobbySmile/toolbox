# ui/pyside6/views/media_view.py
#
# PySide6 版本的媒体处理视图，作为整个 PySide6 UI 层的参考实现。
#
# v3 变更：拖拽和点击选择合并成一个交互面（ui/pyside6/widgets.py 的
# DropArea），之前"拖拽区域 + 下面单独一个选择按钮"的冗余布局去掉了，
# 整块拖拽区域本身就是可点击的文件选择入口。
#
# v2 变更（对齐 Flet 版观感 + 补齐功能缺口）：
#   1. 每个 Tab 内容套一层 QScrollArea，对应 Flet 版 scroll=AUTO
#   2. 引入 ui/pyside6/theme.py 的统一样式：卡片分区、强调色按钮、
#      跟 Flet 版一致的状态文字配色
#   3. 截取 Tab 数值输入框标签跟着"按时长/按结束时间"模式切换
#   4. 合并 Tab 视频/音频状态拆成两行分别显示
#
# 设计原则（后续视图照着这个模式搬）：
#   1. tools/ 层完全不碰
#   2. 耗时任务一律通过 ui.pyside6.worker.TaskWorker 包装
#   3. 需要"组合多个 tools 函数循环处理一批文件"的场景，用模块级小函数包装一层
#   4. 文件输入统一用 DropArea，拖拽和点击合一

from pathlib import Path
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel, QPushButton,
    QFileDialog, QComboBox, QLineEdit, QCheckBox,
    QListWidget, QListWidgetItem, QMessageBox, QAbstractItemView,
)

from tools.image.converter import convert_image, batch_convert
from tools.multimedia.video import convert_to_mp4, convert_to_gif, extract_audio, extract_video
from tools.multimedia.merge import merge_video_audio, replace_audio, concat_videos
from tools.multimedia.cut import cut_media
from tools.utils.ffmpeg import FFmpegCancelled

from ui.pyside6.worker import TaskWorker
from ui.pyside6.widgets import DropArea, ProgressBar, card, wrap_scrollable, make_clear_button
from ui.pyside6.theme import set_status, set_muted, style_primary, style_stop, section_title_style, subsection_title_style
from tools.utils.paths import get_settings_path


def _get_mp4_compatibility() -> str:
    """读取设置页保存的 MP4 编码兼容性模式，跟 Flet 版 _get_mp4_compatibility() 行为一致，
    两套 UI 共用同一份 config/settings.json，任一边改了这个设置，另一边下次转换也会用上。"""
    try:
        settings = json.loads(get_settings_path().read_text(encoding="utf-8"))
        return settings.get("video", {}).get("mp4_compatibility", "standard")
    except Exception:
        return "standard"

# v3 变更：不再限制具体扩展名。之前列的是"常见格式白名单"，但 FFmpeg
# 实际支持的格式多得多，像 .qt（QuickTime 容器）这种不算特别罕见的格式
# 就会被这份白名单挡在文件选择框外面——选不出来，看着像是"不支持"，
# 其实只是筛选器画蛇添足。改成空字符串，QFileDialog 不加筛选，
# 显示全部文件，具体是否能处理交给 ffmpeg 自己在执行时判断。
IMAGE_FILTER = ""
VIDEO_FILTER = ""
AUDIO_FILTER = ""
MEDIA_FILTER = ""


# ==========================================================
# 模块级辅助函数：组合已有 tools 函数处理"一批文件"，不修改 tools/ 本身
# ==========================================================

def _convert_images_batch_loose(paths, output_format, output_dir=None, progress_callback=None, cancel_check=None):
    """对一组零散选中/拖入的图片文件批量转换（不是整个文件夹）"""
    total = len(paths)
    results = []
    for i, path in enumerate(paths):
        if cancel_check and cancel_check():
            raise InterruptedError(f"用户手动取消了批量转换（已完成 {i}/{total} 张）")
        out = convert_image(path, output_format, output_dir=output_dir)
        results.append(out)
        if progress_callback:
            progress_callback(i + 1, total)
    return results


_VIDEO_ACTION_FUNCS = {
    "mp4": convert_to_mp4,
    "gif": convert_to_gif,
    "audio": extract_audio,
    "video": extract_video,
}


def _process_videos_batch(paths, action_type, output_dir=None, progress_callback=None, cancel_check=None):
    """依次对多个视频文件执行同一种操作，汇报"已完成文件数 + 当前文件进度"换算出的整体分数"""
    func = _VIDEO_ACTION_FUNCS[action_type]
    total = len(paths)
    results = []
    # 只有转 MP4 才用得上编码兼容性设置，其余操作（GIF/提取音频/提取画面）没有这个参数
    mp4_compatibility = _get_mp4_compatibility() if action_type == "mp4" else None

    for i, path in enumerate(paths):
        if cancel_check and cancel_check():
            raise FFmpegCancelled(f"用户手动取消了任务（已完成 {i}/{total} 个文件）")

        def on_file_progress(fraction, idx=i):
            if progress_callback is None:
                return
            if fraction is None:
                progress_callback(None)
            else:
                progress_callback((idx + fraction) / total)

        kwargs = dict(output_dir=output_dir, progress_callback=on_file_progress, cancel_check=cancel_check)
        if action_type == "mp4":
            kwargs["compatibility"] = mp4_compatibility

        out = func(path, **kwargs)
        results.append(out)
        if progress_callback:
            progress_callback((i + 1) / total)

    return results


class MediaView(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        tabs.addTab(wrap_scrollable(self._build_image_tab()), "🖼️ 图片转换")
        tabs.addTab(wrap_scrollable(self._build_video_tab()), "🎬 视频处理")
        tabs.addTab(wrap_scrollable(self._build_merge_tab()), "🎞️ 音画合成")
        tabs.addTab(wrap_scrollable(self._build_cut_tab()), "✂️ 长度截取")

    # ==========================================================
    # Tab 1：图片格式转换
    # ==========================================================
    def _build_image_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)

        self.img_state = {"paths": [], "is_folder": False, "out_dir": None}
        self.img_worker = None

        title = QLabel("🖼️ 图片格式互转")
        title.setStyleSheet(section_title_style())
        outer.addWidget(title)
        sub = QLabel()
        set_muted(sub, "支持单张/多张图片或整个文件夹批量转换")
        outer.addWidget(sub)

        self.img_drop = DropArea(
            "📥 拖拽图片到这里，或点击选择（可多选）", self._on_img_files_dropped,
            mode="files", file_filter=IMAGE_FILTER,
            secondary_label="或选择整个文件夹（批量转换）", secondary_mode="folder",
        )

        self.img_path_label = QLabel()
        set_muted(self.img_path_label, "未选择文件")

        out_row = QHBoxLayout()
        btn_out_dir = QPushButton("更改输出目录")
        btn_out_dir.clicked.connect(self._pick_img_out_dir)
        self.img_out_label = QLabel()
        set_muted(self.img_out_label, "📁 默认保存至原文件同级目录")
        out_row.addWidget(btn_out_dir)
        out_row.addWidget(self.img_out_label)
        out_row.addStretch()

        action_row = QHBoxLayout()
        self.img_format_combo = QComboBox()
        self.img_format_combo.addItems(["png", "jpg", "webp", "bmp"])
        self.img_start_btn = QPushButton("🚀 开始转换")
        style_primary(self.img_start_btn)
        self.img_start_btn.clicked.connect(self._start_img_convert)
        self.img_stop_btn = QPushButton("停止")
        style_stop(self.img_stop_btn)
        self.img_stop_btn.setVisible(False)
        self.img_stop_btn.clicked.connect(self._stop_img_convert)
        action_row.addWidget(self.img_format_combo)
        action_row.addWidget(self.img_start_btn)
        action_row.addWidget(self.img_stop_btn)
        action_row.addStretch()

        self.img_progress = ProgressBar()
        self.img_progress.setVisible(False)
        self.img_status = QLabel("")
        self.img_status.setWordWrap(True)

        outer.addWidget(card(
            self.img_drop, self.img_path_label,
            out_row, action_row, self.img_progress, self.img_status,
        ))
        outer.addStretch()
        return widget

    def _on_img_files_dropped(self, paths: list[str]):
        if len(paths) == 1 and Path(paths[0]).is_dir():
            self.img_state["paths"] = [paths[0]]
            self.img_state["is_folder"] = True
            self.img_path_label.setText(f"📁 文件夹: {Path(paths[0]).name}")
        else:
            self.img_state["paths"] = paths
            self.img_state["is_folder"] = False
            self.img_path_label.setText(f"📄 已选择 {len(paths)} 张图片" if len(paths) > 1 else f"📄 {Path(paths[0]).name}")

    def _pick_img_out_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if folder:
            self.img_state["out_dir"] = folder
            self.img_out_label.setText(f"📁 输出至: {folder}")

    def _stop_img_convert(self):
        if self.img_worker:
            self.img_worker.cancel()
            self.img_stop_btn.setEnabled(False)
            set_status(self.img_status, "⏳ 正在停止...", "warning")

    def _start_img_convert(self):
        if not self.img_state["paths"]:
            QMessageBox.warning(self, "提示", "请先选择图片或文件夹")
            return

        fmt = self.img_format_combo.currentText()
        out_dir = self.img_state["out_dir"]

        if self.img_state["is_folder"]:
            worker = TaskWorker(batch_convert, self.img_state["paths"][0], fmt, output_dir=out_dir)
        elif len(self.img_state["paths"]) > 1:
            worker = TaskWorker(_convert_images_batch_loose, self.img_state["paths"], fmt, output_dir=out_dir)
        else:
            worker = TaskWorker(convert_image, self.img_state["paths"][0], fmt, output_dir=out_dir)

        self.img_worker = worker
        self.img_start_btn.setEnabled(False)
        self.img_stop_btn.setVisible(True)
        self.img_stop_btn.setEnabled(True)
        self.img_progress.setVisible(True)
        self.img_progress.setRange(0, 100)
        self.img_progress.setValue(0)
        set_status(self.img_status, "⏳ 正在转换中，请稍候...", "warning")

        worker.progress.connect(self._on_img_progress)
        worker.finished_ok.connect(self._on_img_finished)
        worker.failed.connect(self._on_img_failed)
        worker.cancelled.connect(self._on_img_cancelled)
        worker.start()

    def _on_img_progress(self, value):
        if isinstance(value, tuple):
            current, total = value
            fraction = current / total if total else 0
            self.img_progress.setValue(int(fraction * 100))
            set_status(self.img_status, f"⏳ 转换中 {current}/{total} ({fraction * 100:.1f}%)", "warning")

    def _reset_img_buttons(self):
        self.img_start_btn.setEnabled(True)
        self.img_stop_btn.setVisible(False)
        self.img_worker = None

    def _on_img_finished(self, result):
        count = len(result) if isinstance(result, list) else 1
        msg = f"✅ 转换完成，共处理 {count} 个文件" if isinstance(result, list) else f"✅ 转换成功: {result}"
        set_status(self.img_status, msg, "success")
        self._reset_img_buttons()

    def _on_img_failed(self, message):
        set_status(self.img_status, f"❌ 失败: {message}", "error")
        self._reset_img_buttons()

    def _on_img_cancelled(self):
        set_status(self.img_status, "⏹️ 已取消", "warning")
        self._reset_img_buttons()

    # ==========================================================
    # Tab 2：视频提取与转换
    # ==========================================================
    def _build_video_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)

        self.vid_state = {"paths": [], "out_dir": None}
        self.vid_worker = None

        title = QLabel("🎬 视频提取与转换")
        title.setStyleSheet(section_title_style())
        outer.addWidget(title)
        sub = QLabel()
        set_muted(sub, "高效的视频转码与音画分离提取，支持一次拖入/选择多个文件批量处理")
        outer.addWidget(sub)

        self.vid_drop = DropArea(
            "📥 拖拽视频到这里，或点击选择（可多选）", self._on_vid_files_dropped,
            mode="files", file_filter=VIDEO_FILTER,
        )

        self.vid_path_label = QLabel()
        set_muted(self.vid_path_label, "未选择视频")

        out_row = QHBoxLayout()
        btn_out_dir = QPushButton("更改输出目录")
        btn_out_dir.clicked.connect(self._pick_vid_out_dir)
        self.vid_out_label = QLabel()
        set_muted(self.vid_out_label, "📁 默认保存至原文件同级目录")
        out_row.addWidget(btn_out_dir)
        out_row.addWidget(self.vid_out_label)
        out_row.addStretch()

        action_row = QHBoxLayout()
        for label, action_type in [("转为 MP4", "mp4"), ("转为 GIF", "gif"), ("提取纯音频", "audio"), ("提取纯画面", "video")]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked=False, a=action_type: self._start_vid_process(a))
            action_row.addWidget(btn)
        self.vid_stop_btn = QPushButton("停止")
        style_stop(self.vid_stop_btn)
        self.vid_stop_btn.setVisible(False)
        self.vid_stop_btn.clicked.connect(self._stop_vid_process)
        action_row.addWidget(self.vid_stop_btn)
        action_row.addStretch()

        self.vid_progress = ProgressBar()
        self.vid_progress.setVisible(False)
        self.vid_status = QLabel("")
        self.vid_status.setWordWrap(True)

        outer.addWidget(card(
            self.vid_drop, self.vid_path_label,
            out_row, action_row, self.vid_progress, self.vid_status,
        ))
        outer.addStretch()
        return widget

    def _on_vid_files_dropped(self, paths: list[str]):
        self.vid_state["paths"] = paths
        if len(paths) == 1:
            self.vid_path_label.setText(f"🎬 视频: {Path(paths[0]).name}")
        else:
            self.vid_path_label.setText(f"🎬 已选择 {len(paths)} 个视频")

    def _pick_vid_out_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if folder:
            self.vid_state["out_dir"] = folder
            self.vid_out_label.setText(f"📁 输出至: {folder}")

    def _stop_vid_process(self):
        if self.vid_worker:
            self.vid_worker.cancel()
            self.vid_stop_btn.setEnabled(False)
            set_status(self.vid_status, "⏳ 正在停止...", "warning")

    def _start_vid_process(self, action_type: str):
        if not self.vid_state["paths"]:
            QMessageBox.warning(self, "提示", "请先选择视频文件")
            return

        worker = TaskWorker(_process_videos_batch, self.vid_state["paths"], action_type, output_dir=self.vid_state["out_dir"])
        self.vid_worker = worker

        self.vid_stop_btn.setVisible(True)
        self.vid_stop_btn.setEnabled(True)
        self.vid_progress.setVisible(True)
        self.vid_progress.setRange(0, 100)
        self.vid_progress.setValue(0)
        set_status(self.vid_status, "⏳ FFmpeg 正在运算中，请耐心等待...", "warning")

        worker.progress.connect(self._on_vid_progress)
        worker.finished_ok.connect(self._on_vid_finished)
        worker.failed.connect(self._on_vid_failed)
        worker.cancelled.connect(self._on_vid_cancelled)
        worker.start()

    def _on_vid_progress(self, value):
        if isinstance(value, tuple):
            return
        if value is None:
            set_status(self.vid_status, "⏳ 处理中... 计算中", "warning")
            return
        self.vid_progress.setValue(int(value * 100))
        set_status(self.vid_status, f"⏳ 处理中... {value * 100:.1f}%", "warning")

    def _reset_vid_buttons(self):
        self.vid_stop_btn.setVisible(False)
        self.vid_worker = None

    def _on_vid_finished(self, result):
        count = len(result) if isinstance(result, list) else 1
        set_status(self.vid_status, f"✅ 处理完成，共 {count} 个文件", "success")
        self._reset_vid_buttons()

    def _on_vid_failed(self, message):
        set_status(self.vid_status, f"❌ 失败: {message}", "error")
        self._reset_vid_buttons()

    def _on_vid_cancelled(self):
        set_status(self.vid_status, "⏹️ 已取消", "warning")
        self._reset_vid_buttons()

    # ==========================================================
    # Tab 3：音画合成与拼接
    # ==========================================================
    def _build_merge_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)

        self.merge_state = {"video": None, "audio": None, "out_dir": None}
        self.concat_state = {"out_dir": None}
        self.merge_worker = None
        self.concat_worker = None

        title = QLabel("🎞️ 音画合成与拼接")
        title.setStyleSheet(section_title_style())
        outer.addWidget(title)

        # ---- 1. 合并/替换 ----
        sub1_title = QLabel("1. 音视频合并与声音替换")
        sub1_title.setStyleSheet(subsection_title_style())

        self.merge_v_drop = DropArea(
            "📥 拖拽或点击选择视频", lambda paths: self._set_merge_file("video", paths),
            mode="file", file_filter=VIDEO_FILTER,
        )
        self.merge_a_drop = DropArea(
            "📥 拖拽或点击选择音频（也支持视频文件，用于提取其中的声音替换原声）",
            lambda paths: self._set_merge_file("audio", paths),
            mode="file", file_filter=AUDIO_FILTER,
        )
        drop_row = QHBoxLayout()
        drop_row.addWidget(self.merge_v_drop)
        drop_row.addWidget(self.merge_a_drop)

        self.merge_v_label = QLabel()
        set_muted(self.merge_v_label, "未选择视频")
        self.merge_a_label = QLabel()
        set_muted(self.merge_a_label, "未选择音频")

        mode_row = QHBoxLayout()
        self.duration_combo = QComboBox()
        self.duration_combo.addItem("最短时长", "shortest")
        self.duration_combo.addItem("最长时长", "longest")
        self.duration_combo.addItem("以画面长度", "video")
        self.duration_combo.addItem("以音频长度", "audio")
        mode_row.addWidget(QLabel("合并后时长:"))
        mode_row.addWidget(self.duration_combo)
        mode_row.addStretch()

        out_row = QHBoxLayout()
        btn_out = QPushButton("更改输出目录")
        btn_out.clicked.connect(self._pick_merge_out_dir)
        self.merge_out_label = QLabel()
        set_muted(self.merge_out_label, "📁 默认保存至原视频文件同级目录")
        out_row.addWidget(btn_out)
        out_row.addWidget(self.merge_out_label)
        out_row.addStretch()

        merge_btn_row = QHBoxLayout()
        btn_merge = QPushButton("无声合并")
        style_primary(btn_merge)
        btn_merge.clicked.connect(lambda: self._start_merge("merge"))
        btn_replace = QPushButton("替换原声")
        style_primary(btn_replace)
        btn_replace.clicked.connect(lambda: self._start_merge("replace"))
        self.merge_stop_btn = QPushButton("停止")
        style_stop(self.merge_stop_btn)
        self.merge_stop_btn.setVisible(False)
        self.merge_stop_btn.clicked.connect(self._stop_merge)
        merge_btn_row.addWidget(btn_merge)
        merge_btn_row.addWidget(btn_replace)
        merge_btn_row.addWidget(self.merge_stop_btn)
        merge_btn_row.addStretch()

        self.merge_progress = ProgressBar()
        self.merge_progress.setVisible(False)
        self.merge_status = QLabel("")
        self.merge_status.setWordWrap(True)

        outer.addWidget(card(
            sub1_title, drop_row, self.merge_v_label, self.merge_a_label,
            mode_row, out_row, merge_btn_row, self.merge_progress, self.merge_status,
        ))

        # ---- 2. 拼接 ----
        sub2_title = QLabel("2. 多视频重新编码拼接")
        sub2_title.setStyleSheet(subsection_title_style())
        sub2_hint = QLabel()
        set_muted(sub2_hint, "下方列表支持直接拖动条目调整顺序（双击某一项可移除）")

        self.concat_drop = DropArea(
            "📥 拖拽或点击选择多个视频，依次加入拼接列表", self._on_concat_files_dropped,
            mode="files", file_filter=VIDEO_FILTER,
        )

        self.concat_list = QListWidget()
        self.concat_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.concat_list.setMaximumHeight(120)
        self.concat_list.itemDoubleClicked.connect(self._remove_concat_item)

        # 拼接单独有自己的输出目录，不再跟上面"合并/替换"共用一个
        # （之前共用容易搞混：改了合并的输出目录，结果拼接也被影响了）
        concat_out_row = QHBoxLayout()
        btn_concat_out = QPushButton("更改输出目录")
        btn_concat_out.clicked.connect(self._pick_concat_out_dir)
        self.concat_out_label = QLabel()
        set_muted(self.concat_out_label, "📁 默认保存至首个视频文件同级目录")
        concat_out_row.addWidget(btn_concat_out)
        concat_out_row.addWidget(self.concat_out_label)
        concat_out_row.addStretch()

        concat_btn_row = QHBoxLayout()
        btn_clear_concat = make_clear_button(self.concat_list)
        btn_start_concat = QPushButton("🚀 开始拼接")
        style_primary(btn_start_concat)
        btn_start_concat.clicked.connect(self._start_concat)
        self.concat_stop_btn = QPushButton("停止")
        style_stop(self.concat_stop_btn)
        self.concat_stop_btn.setVisible(False)
        self.concat_stop_btn.clicked.connect(self._stop_concat)
        concat_btn_row.addWidget(btn_start_concat)
        concat_btn_row.addWidget(self.concat_stop_btn)
        concat_btn_row.addWidget(btn_clear_concat)
        concat_btn_row.addStretch()

        self.concat_progress = ProgressBar()
        self.concat_progress.setVisible(False)
        self.concat_status = QLabel("")
        self.concat_status.setWordWrap(True)

        outer.addWidget(card(
            sub2_title, sub2_hint, self.concat_drop, self.concat_list,
            concat_out_row, concat_btn_row, self.concat_progress, self.concat_status,
        ))
        outer.addStretch()
        return widget

    def _set_merge_file(self, kind: str, paths: list[str]):
        self.merge_state[kind] = paths[0]
        if kind == "video":
            self.merge_v_label.setText(f"🎬 {Path(paths[0]).name}")
        else:
            self.merge_a_label.setText(f"🎵 {Path(paths[0]).name}")

    def _pick_merge_out_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if folder:
            self.merge_state["out_dir"] = folder
            self.merge_out_label.setText(f"📁 输出至: {folder}")

    def _stop_merge(self):
        if self.merge_worker:
            self.merge_worker.cancel()
            self.merge_stop_btn.setEnabled(False)

    def _start_merge(self, action_type: str):
        if not self.merge_state["video"] or not self.merge_state["audio"]:
            QMessageBox.warning(self, "提示", "请先选择视频和音频")
            return

        v_path = Path(self.merge_state["video"])
        out_dir = Path(self.merge_state["out_dir"]) if self.merge_state["out_dir"] else v_path.parent
        suffix = "_merged" if action_type == "merge" else "_replaced"
        out_path = out_dir / f"{v_path.stem}{suffix}.mp4"
        duration_mode = self.duration_combo.currentData()

        func = merge_video_audio if action_type == "merge" else replace_audio
        worker = TaskWorker(func, self.merge_state["video"], self.merge_state["audio"], str(out_path), duration_mode=duration_mode)
        self.merge_worker = worker

        self.merge_stop_btn.setVisible(True)
        self.merge_stop_btn.setEnabled(True)
        self.merge_progress.setVisible(True)
        self.merge_progress.setRange(0, 100)
        self.merge_progress.setValue(0)
        set_status(self.merge_status, "⏳ 合成中... 0.0%", "warning")

        worker.progress.connect(self._on_merge_progress)
        worker.finished_ok.connect(self._on_merge_finished)
        worker.failed.connect(self._on_merge_failed)
        worker.cancelled.connect(self._on_merge_cancelled)
        worker.start()

    def _on_merge_progress(self, value):
        if value is None:
            set_status(self.merge_status, "⏳ 合成中... 计算中", "warning")
        elif not isinstance(value, tuple):
            self.merge_progress.setValue(int(value * 100))
            set_status(self.merge_status, f"⏳ 合成中... {value * 100:.1f}%", "warning")

    def _reset_merge_buttons(self):
        self.merge_stop_btn.setVisible(False)
        self.merge_worker = None

    def _on_merge_finished(self, result):
        set_status(self.merge_status, f"✅ 成功: {result}", "success")
        self._reset_merge_buttons()

    def _on_merge_failed(self, message):
        set_status(self.merge_status, f"❌ 失败: {message}", "error")
        self._reset_merge_buttons()

    def _on_merge_cancelled(self):
        set_status(self.merge_status, "⏹️ 已取消", "warning")
        self._reset_merge_buttons()

    def _pick_concat_out_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if folder:
            self.concat_state["out_dir"] = folder
            self.concat_out_label.setText(f"📁 输出至: {folder}")

    def _on_concat_files_dropped(self, paths: list[str]):
        for p in paths:
            item = QListWidgetItem(f"{Path(p).name}")
            item.setData(Qt.ItemDataRole.UserRole, p)
            self.concat_list.addItem(item)

    def _remove_concat_item(self, item: QListWidgetItem):
        self.concat_list.takeItem(self.concat_list.row(item))

    def _stop_concat(self):
        if self.concat_worker:
            self.concat_worker.cancel()
            self.concat_stop_btn.setEnabled(False)

    def _start_concat(self):
        paths = [self.concat_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.concat_list.count())]
        if len(paths) < 2:
            QMessageBox.warning(self, "提示", "至少需要 2 个视频")
            return

        first_vid = Path(paths[0])
        out_dir = Path(self.concat_state["out_dir"]) if self.concat_state["out_dir"] else first_vid.parent
        out_path = out_dir / f"{first_vid.stem}_concat.mp4"

        worker = TaskWorker(concat_videos, paths, str(out_path))
        self.concat_worker = worker

        self.concat_stop_btn.setVisible(True)
        self.concat_stop_btn.setEnabled(True)
        self.concat_progress.setVisible(True)
        self.concat_progress.setRange(0, 100)
        self.concat_progress.setValue(0)
        set_status(self.concat_status, "⏳ 拼接中(重编码统一尺寸)... 0.0%", "warning")

        worker.progress.connect(self._on_concat_progress)
        worker.finished_ok.connect(self._on_concat_finished)
        worker.failed.connect(self._on_concat_failed)
        worker.cancelled.connect(self._on_concat_cancelled)
        worker.start()

    def _on_concat_progress(self, value):
        if value is None:
            set_status(self.concat_status, "⏳ 拼接中... 计算中", "warning")
        elif not isinstance(value, tuple):
            self.concat_progress.setValue(int(value * 100))
            set_status(self.concat_status, f"⏳ 拼接中... {value * 100:.1f}%", "warning")

    def _reset_concat_buttons(self):
        self.concat_stop_btn.setVisible(False)
        self.concat_worker = None

    def _on_concat_finished(self, result):
        set_status(self.concat_status, f"✅ 拼接成功: {result}", "success")
        self._reset_concat_buttons()

    def _on_concat_failed(self, message):
        set_status(self.concat_status, f"❌ 失败: {message}", "error")
        self._reset_concat_buttons()

    def _on_concat_cancelled(self):
        set_status(self.concat_status, "⏹️ 已取消", "warning")
        self._reset_concat_buttons()

    # ==========================================================
    # Tab 4：视频/音频指定长度截取
    # ==========================================================
    def _build_cut_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)

        self.cut_state = {"path": None, "out_dir": None}
        self.cut_worker = None

        title = QLabel("✂️ 指定长度截取")
        title.setStyleSheet(section_title_style())
        outer.addWidget(title)
        sub = QLabel()
        set_muted(sub, "从视频或音频中截取任意一段，支持按时长或结束时间点截取")
        outer.addWidget(sub)

        self.cut_drop = DropArea(
            "📥 拖拽或点击选择视频/音频", self._on_cut_file_dropped,
            mode="file", file_filter=MEDIA_FILTER,
        )

        self.cut_path_label = QLabel()
        set_muted(self.cut_path_label, "未选择文件")

        out_row = QHBoxLayout()
        btn_out = QPushButton("更改输出目录")
        btn_out.clicked.connect(self._pick_cut_out_dir)
        self.cut_out_label = QLabel()
        set_muted(self.cut_out_label, "📁 默认保存至原文件同级目录")
        out_row.addWidget(btn_out)
        out_row.addWidget(self.cut_out_label)
        out_row.addStretch()

        params_row = QHBoxLayout()
        self.cut_start_input = QLineEdit("0")
        self.cut_start_input.setPlaceholderText("如 0:30 或 90")
        self.cut_mode_combo = QComboBox()
        self.cut_mode_combo.addItem("按时长", "duration")
        self.cut_mode_combo.addItem("按结束时间", "end")
        self.cut_mode_combo.currentIndexChanged.connect(self._on_cut_mode_changed)
        self.cut_value_label = QLabel()
        self.cut_value_input = QLineEdit("30")
        params_row.addWidget(QLabel("起始:"))
        params_row.addWidget(self.cut_start_input)
        params_row.addWidget(self.cut_mode_combo)
        params_row.addWidget(self.cut_value_label)
        params_row.addWidget(self.cut_value_input)

        self._on_cut_mode_changed()

        self.cut_reencode_check = QCheckBox("精确切割（重新编码，较慢）")
        self.cut_reencode_check.setChecked(True)
        reencode_hint = QLabel()
        set_muted(
            reencode_hint,
            "已默认勾选：快速模式（不重新编码）受限于视频关键帧间隔，"
            "起点可能比你要求的提前几秒，长度会跟着偏；"
            "不在意这点误差、只想要速度快，可以取消勾选。",
        )
        reencode_hint.setWordWrap(True)

        btn_row = QHBoxLayout()
        btn_start = QPushButton("🚀 开始截取")
        style_primary(btn_start)
        btn_start.clicked.connect(self._start_cut)
        self.cut_stop_btn = QPushButton("停止")
        style_stop(self.cut_stop_btn)
        self.cut_stop_btn.setVisible(False)
        self.cut_stop_btn.clicked.connect(self._stop_cut)
        btn_row.addWidget(btn_start)
        btn_row.addWidget(self.cut_stop_btn)
        btn_row.addStretch()

        self.cut_progress = ProgressBar()
        self.cut_progress.setVisible(False)
        self.cut_status = QLabel("")
        self.cut_status.setWordWrap(True)

        outer.addWidget(card(
            self.cut_drop, self.cut_path_label, out_row,
            params_row, self.cut_reencode_check, reencode_hint, btn_row, self.cut_progress, self.cut_status,
        ))
        outer.addStretch()
        return widget

    def _on_cut_mode_changed(self):
        if self.cut_mode_combo.currentData() == "duration":
            self.cut_value_label.setText("截取时长(秒):")
            self.cut_value_input.setPlaceholderText("如 30 或 1:00")
        else:
            self.cut_value_label.setText("结束时间:")
            self.cut_value_input.setPlaceholderText("如 1:30")

    def _on_cut_file_dropped(self, paths: list[str]):
        self.cut_state["path"] = paths[0]
        self.cut_path_label.setText(f"🎬 {Path(paths[0]).name}")

    def _pick_cut_out_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if folder:
            self.cut_state["out_dir"] = folder
            self.cut_out_label.setText(f"📁 输出至: {folder}")

    def _stop_cut(self):
        if self.cut_worker:
            self.cut_worker.cancel()
            self.cut_stop_btn.setEnabled(False)

    def _start_cut(self):
        if not self.cut_state["path"]:
            QMessageBox.warning(self, "提示", "请先选择视频或音频文件")
            return

        kwargs = dict(
            start=self.cut_start_input.text(),
            output_dir=self.cut_state["out_dir"],
            reencode=self.cut_reencode_check.isChecked(),
        )
        if self.cut_mode_combo.currentData() == "duration":
            kwargs["duration"] = self.cut_value_input.text()
        else:
            kwargs["end"] = self.cut_value_input.text()

        worker = TaskWorker(cut_media, self.cut_state["path"], **kwargs)
        self.cut_worker = worker

        self.cut_stop_btn.setVisible(True)
        self.cut_stop_btn.setEnabled(True)
        self.cut_progress.setVisible(True)
        self.cut_progress.setRange(0, 100)
        self.cut_progress.setValue(0)
        set_status(self.cut_status, "⏳ 正在截取... 0.0%", "warning")

        worker.progress.connect(self._on_cut_progress)
        worker.finished_ok.connect(self._on_cut_finished)
        worker.failed.connect(self._on_cut_failed)
        worker.cancelled.connect(self._on_cut_cancelled)
        worker.start()

    def _on_cut_progress(self, value):
        if value is None:
            set_status(self.cut_status, "⏳ 正在截取... 计算中", "warning")
        elif not isinstance(value, tuple):
            self.cut_progress.setValue(int(value * 100))
            set_status(self.cut_status, f"⏳ 正在截取... {value * 100:.1f}%", "warning")

    def _reset_cut_buttons(self):
        self.cut_stop_btn.setVisible(False)
        self.cut_worker = None

    def _on_cut_finished(self, result):
        set_status(self.cut_status, f"✅ 截取成功: {result}", "success")
        self._reset_cut_buttons()

    def _on_cut_failed(self, message):
        set_status(self.cut_status, f"❌ 失败: {message}", "error")
        self._reset_cut_buttons()

    def _on_cut_cancelled(self):
        set_status(self.cut_status, "⏹️ 已取消", "warning")
        self._reset_cut_buttons()
