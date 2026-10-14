# ui/pyside6/views/document_view.py

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel, QPushButton,
    QFileDialog, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QAbstractItemView,
)

from tools.pdf.extract import extract_text_batch
from tools.pdf.merge import merge_pdfs
from tools.pdf.split import split_pdf
from tools.pdf.convert import pdf_to_images, images_to_pdf
from tools.pdf.reorder import multi_move_pages

from ui.pyside6.worker import TaskWorker
from ui.pyside6.widgets import DropArea, card, wrap_scrollable, ProgressBar, make_clear_button
from ui.pyside6.theme import set_status, set_muted, style_primary, style_stop, section_title_style

PDF_FILTER = "PDF (*.pdf)"
IMAGE_FILTER = "图片 (*.png *.jpg *.jpeg *.webp *.bmp)"


def _parse_page_ranges(range_str: str) -> list[int] | None:
    if not range_str.strip() or range_str.strip().lower() == 'all':
        return None
    pages = set()
    for part in range_str.replace('，', ',').split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            start, end = part.split('-', 1)
            pages.update(range(int(start) - 1, int(end)))
        else:
            pages.add(int(part) - 1)
    return sorted(pages)


def _parse_move_rules(rule_str: str) -> list[tuple[int, int]]:
    rules = []
    for part in rule_str.replace('，', ',').split(','):
        part = part.strip()
        if not part:
            continue
        separator = next((sep for sep in ['->', '>', ':', '：'] if sep in part), None)
        if not separator:
            raise ValueError(f"规则需包含目标位置，如 8>2。出错部分: '{part}'")
        src_str, tgt_str = part.split(separator, 1)
        tgt = int(tgt_str.strip()) - 1
        src_str = src_str.strip()
        if '-' in src_str:
            s_start, s_end = src_str.split('-', 1)
            for s in range(int(s_start.strip()), int(s_end.strip()) + 1):
                rules.append((s - 1, tgt))
                tgt += 1
        else:
            rules.append((int(src_str.strip()) - 1, tgt))
    return rules


def _safe_dir(path: Path) -> Path:
    """目录重名时自动添加 (1)、(2)...，跟 Flet 版 _safe_dir 行为一致"""
    if not path.exists():
        return path
    index = 1
    while True:
        new_path = path.parent / f"{path.name}({index})"
        if not new_path.exists():
            return new_path
        index += 1


class DocumentView(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        tabs.addTab(wrap_scrollable(self._build_struct_tab()), "🗂️ 结构处理")
        tabs.addTab(wrap_scrollable(self._build_convert_tab()), "🔄 格式互转")
        tabs.addTab(wrap_scrollable(self._build_extract_tab()), "📝 提取文本")

    # ==========================================================
    # Tab 1：结构处理（合并 / 拆分 / 重排）
    # ==========================================================
    def _build_struct_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)

        title = QLabel("✂️ 页面与结构调整")
        title.setStyleSheet(section_title_style())
        outer.addWidget(title)

        # ---- 合并 ----
        self.merge_state = {"paths": [], "out_dir": None}
        self.merge_worker = None

        merge_drop = DropArea("📥 拖拽或点击选择多个 PDF 文件（依次加入合并列表）", self._on_merge_files_dropped, mode="files", file_filter=PDF_FILTER)
        self.merge_list = QListWidget()
        self.merge_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.merge_list.setMaximumHeight(110)
        self.merge_list.itemDoubleClicked.connect(lambda item: self.merge_list.takeItem(self.merge_list.row(item)))

        merge_out_row = QHBoxLayout()
        btn_merge_out = QPushButton("更改输出目录")
        btn_merge_out.clicked.connect(lambda: self._pick_out_dir(self.merge_state, self.merge_out_label))
        self.merge_out_label = QLabel()
        set_muted(self.merge_out_label, "📁 默认保存至首个文件同级目录")
        merge_out_row.addWidget(btn_merge_out)
        merge_out_row.addWidget(self.merge_out_label)
        merge_out_row.addStretch()

        btn_do_merge = QPushButton("🚀 按照以上顺序合并")
        style_primary(btn_do_merge)
        btn_do_merge.clicked.connect(self._start_merge)
        btn_clear_merge = make_clear_button(self.merge_list)
        merge_action_row = QHBoxLayout()
        merge_action_row.addWidget(btn_do_merge)
        merge_action_row.addWidget(btn_clear_merge)
        merge_action_row.addStretch()
        self.merge_status = QLabel("")
        self.merge_status.setWordWrap(True)

        outer.addWidget(card(
            QLabel("1. 合并多个 PDF"), merge_drop, self.merge_list,
            merge_out_row, merge_action_row, self.merge_status,
        ))

        # ---- 拆分 ----
        self.split_state = {"path": None, "out_dir": None}
        split_drop = DropArea("📥 拖拽或点击选择要拆分的 PDF", lambda paths: self._set_single(self.split_state, "path", paths[0], self.split_path_label, "📄"), mode="file", file_filter=PDF_FILTER)
        self.split_path_label = QLabel()
        set_muted(self.split_path_label, "未选择")

        split_row = QHBoxLayout()
        self.split_pages_input = QLineEdit()
        self.split_pages_input.setPlaceholderText("提取页码 (如: 1,3,5-7)")
        btn_split = QPushButton("提取页面")
        style_primary(btn_split)
        btn_split.clicked.connect(self._start_split)
        split_row.addWidget(self.split_pages_input)
        split_row.addWidget(btn_split)

        split_out_row = QHBoxLayout()
        btn_split_out = QPushButton("更改输出目录")
        btn_split_out.clicked.connect(lambda: self._pick_out_dir(self.split_state, self.split_out_label))
        self.split_out_label = QLabel()
        set_muted(self.split_out_label, "📁 默认保存至原文件同级目录")
        split_out_row.addWidget(btn_split_out)
        split_out_row.addWidget(self.split_out_label)
        split_out_row.addStretch()

        self.split_status = QLabel("")
        self.split_status.setWordWrap(True)

        outer.addWidget(card(
            QLabel("2. 拆分 / 提取页面"), split_drop, self.split_path_label,
            split_out_row, split_row, self.split_status,
        ))

        # ---- 重排 ----
        self.reorder_state = {"path": None, "out_dir": None}
        reorder_drop = DropArea("📥 拖拽或点击选择要重排的 PDF", lambda paths: self._set_single(self.reorder_state, "path", paths[0], self.reorder_path_label, "📄"), mode="file", file_filter=PDF_FILTER)
        self.reorder_path_label = QLabel()
        set_muted(self.reorder_path_label, "未选择")

        reorder_row = QHBoxLayout()
        self.reorder_rules_input = QLineEdit()
        self.reorder_rules_input.setPlaceholderText("重排规则 (如: 8>2, 50-54>21)")
        btn_reorder = QPushButton("调整顺序")
        style_primary(btn_reorder)
        btn_reorder.clicked.connect(self._start_reorder)
        reorder_row.addWidget(self.reorder_rules_input)
        reorder_row.addWidget(btn_reorder)

        reorder_out_row = QHBoxLayout()
        btn_reorder_out = QPushButton("更改输出目录")
        btn_reorder_out.clicked.connect(lambda: self._pick_out_dir(self.reorder_state, self.reorder_out_label))
        self.reorder_out_label = QLabel()
        set_muted(self.reorder_out_label, "📁 默认保存至原文件同级目录")
        reorder_out_row.addWidget(btn_reorder_out)
        reorder_out_row.addWidget(self.reorder_out_label)
        reorder_out_row.addStretch()

        self.reorder_status = QLabel("")
        self.reorder_status.setWordWrap(True)

        outer.addWidget(card(
            QLabel("3. 调整页面顺序"), reorder_drop, self.reorder_path_label,
            reorder_out_row, reorder_row, self.reorder_status,
        ))
        outer.addStretch()
        return widget

    def _set_single(self, state: dict, key: str, value, label, prefix: str):
        state[key] = value
        label.setText(f"{prefix} {Path(value).name}")

    def _pick_out_dir(self, state: dict, label):
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if folder:
            state["out_dir"] = folder
            label.setText(f"📁 输出至: {folder}")

    def _on_merge_files_dropped(self, paths: list[str]):
        for p in paths:
            item = QListWidgetItem(Path(p).name)
            item.setData(Qt.ItemDataRole.UserRole, p)
            self.merge_list.addItem(item)

    def _start_merge(self):
        paths = [self.merge_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.merge_list.count())]
        if len(paths) < 2:
            QMessageBox.warning(self, "提示", "至少需要 2 个 PDF 文件")
            return
        out_dir = Path(self.merge_state["out_dir"]) if self.merge_state["out_dir"] else Path(paths[0]).parent
        out_path = out_dir / "merged_output.pdf"

        set_status(self.merge_status, "⏳ 正在处理中...", "warning")
        worker = TaskWorker(merge_pdfs, paths, out_path)
        self.merge_worker = worker
        worker.finished_ok.connect(lambda r: set_status(self.merge_status, f"✅ 成功:\n{r}", "success"))
        worker.failed.connect(lambda m: set_status(self.merge_status, f"❌ 失败: {m}", "error"))
        worker.start()

    def _start_split(self):
        if not self.split_state["path"]:
            QMessageBox.warning(self, "提示", "未选择 PDF")
            return
        try:
            pages = _parse_page_ranges(self.split_pages_input.text())
        except Exception as ex:
            set_status(self.split_status, f"❌ 页码格式无效: {ex}", "error")
            return
        if not pages:
            set_status(self.split_status, "❌ 提取页码无效", "error")
            return

        src = Path(self.split_state["path"])
        out_dir = Path(self.split_state["out_dir"]) if self.split_state["out_dir"] else src.parent
        out_path = out_dir / f"{src.stem}_extracted.pdf"

        set_status(self.split_status, "⏳ 正在处理中...", "warning")
        worker = TaskWorker(split_pdf, self.split_state["path"], out_path, pages)
        self.split_worker = worker
        worker.finished_ok.connect(lambda r: set_status(self.split_status, f"✅ 成功:\n{r}", "success"))
        worker.failed.connect(lambda m: set_status(self.split_status, f"❌ 失败: {m}", "error"))
        worker.start()

    def _start_reorder(self):
        if not self.reorder_state["path"]:
            QMessageBox.warning(self, "提示", "未选择 PDF")
            return
        try:
            rules = _parse_move_rules(self.reorder_rules_input.text())
        except Exception as ex:
            set_status(self.reorder_status, f"❌ 规则无效: {ex}", "error")
            return
        if not rules:
            set_status(self.reorder_status, "❌ 规则为空", "error")
            return

        src = Path(self.reorder_state["path"])
        out_dir = Path(self.reorder_state["out_dir"]) if self.reorder_state["out_dir"] else src.parent
        out_path = out_dir / f"{src.stem}_reordered.pdf"

        set_status(self.reorder_status, "⏳ 正在处理中...", "warning")
        worker = TaskWorker(multi_move_pages, self.reorder_state["path"], out_path, rules)
        self.reorder_worker = worker
        worker.finished_ok.connect(lambda r: set_status(self.reorder_status, f"✅ 成功:\n{r}", "success"))
        worker.failed.connect(lambda m: set_status(self.reorder_status, f"❌ 失败: {m}", "error"))
        worker.start()

    # ==========================================================
    # Tab 2：格式互转
    # ==========================================================
    def _build_convert_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)

        title = QLabel("🔄 PDF 与图片无损互转")
        title.setStyleSheet(section_title_style())
        outer.addWidget(title)

        # ---- PDF -> 图片 ----
        self.p2i_state = {"path": None, "out_dir": None}
        p2i_drop = DropArea("📥 拖拽或点击选择 PDF", lambda paths: self._set_single(self.p2i_state, "path", paths[0], self.p2i_path_label, "📄"), mode="file", file_filter=PDF_FILTER)
        self.p2i_path_label = QLabel()
        set_muted(self.p2i_path_label, "未选择")

        p2i_row = QHBoxLayout()
        self.p2i_pages_input = QLineEdit()
        self.p2i_pages_input.setPlaceholderText("提取页码 (如: 1,3,5-7，留空转换全部)")
        btn_p2i = QPushButton("🚀 开始 PDF 转图片")
        style_primary(btn_p2i)
        btn_p2i.clicked.connect(self._start_p2i)
        p2i_row.addWidget(self.p2i_pages_input)
        p2i_row.addWidget(btn_p2i)

        p2i_out_row = QHBoxLayout()
        btn_p2i_out = QPushButton("更改输出目录")
        btn_p2i_out.clicked.connect(lambda: self._pick_out_dir(self.p2i_state, self.p2i_out_label))
        self.p2i_out_label = QLabel()
        set_muted(self.p2i_out_label, "📁 默认输出至原文件同级目录")
        p2i_out_row.addWidget(btn_p2i_out)
        p2i_out_row.addWidget(self.p2i_out_label)
        p2i_out_row.addStretch()

        self.p2i_status = QLabel("")
        self.p2i_status.setWordWrap(True)

        outer.addWidget(card(
            QLabel("1. PDF 转图片"), p2i_drop, self.p2i_path_label,
            p2i_out_row, p2i_row, self.p2i_status,
        ))

        # ---- 图片 -> PDF ----
        self.i2p_state = {"paths": [], "out_dir": None}
        i2p_drop = DropArea("📥 拖拽或点击选择多张图片（依次加入合成列表）", self._on_i2p_files_dropped, mode="files", file_filter=IMAGE_FILTER)
        self.i2p_list = QListWidget()
        self.i2p_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.i2p_list.setMaximumHeight(110)
        self.i2p_list.itemDoubleClicked.connect(lambda item: self.i2p_list.takeItem(self.i2p_list.row(item)))

        i2p_out_row = QHBoxLayout()
        btn_i2p_out = QPushButton("更改输出目录")
        btn_i2p_out.clicked.connect(lambda: self._pick_out_dir(self.i2p_state, self.i2p_out_label))
        self.i2p_out_label = QLabel()
        set_muted(self.i2p_out_label, "📁 默认输出至首个图片同级目录")
        i2p_out_row.addWidget(btn_i2p_out)
        i2p_out_row.addWidget(self.i2p_out_label)
        i2p_out_row.addStretch()

        btn_i2p = QPushButton("🚀 开始图片转 PDF")
        style_primary(btn_i2p)
        btn_i2p.clicked.connect(self._start_i2p)
        btn_clear_i2p = make_clear_button(self.i2p_list)
        i2p_action_row = QHBoxLayout()
        i2p_action_row.addWidget(btn_i2p)
        i2p_action_row.addWidget(btn_clear_i2p)
        i2p_action_row.addStretch()
        self.i2p_status = QLabel("")
        self.i2p_status.setWordWrap(True)

        outer.addWidget(card(
            QLabel("2. 图片转 PDF"), i2p_drop, self.i2p_list,
            i2p_out_row, i2p_action_row, self.i2p_status,
        ))
        outer.addStretch()
        return widget

    def _start_p2i(self):
        if not self.p2i_state["path"]:
            QMessageBox.warning(self, "提示", "未选择 PDF")
            return
        src = Path(self.p2i_state["path"])
        if self.p2i_state["out_dir"]:
            out_dir = Path(self.p2i_state["out_dir"])
        else:
            # 没指定输出目录时，默认目录名重复了就自动加 (1)(2)...，
            # 避免上次生成的图片跟这次的混在同一个文件夹里分不清
            out_dir = _safe_dir(src.parent / f"{src.stem}_images")
        pages = _parse_page_ranges(self.p2i_pages_input.text())

        set_status(self.p2i_status, "⏳ 正在转换中...", "warning")
        worker = TaskWorker(pdf_to_images, self.p2i_state["path"], out_dir, pages=pages)
        self.p2i_worker = worker
        worker.finished_ok.connect(lambda r: set_status(self.p2i_status, f"✅ 生成了 {len(r)} 张图", "success"))
        worker.failed.connect(lambda m: set_status(self.p2i_status, f"❌ 失败: {m}", "error"))
        worker.start()

    def _on_i2p_files_dropped(self, paths: list[str]):
        for p in paths:
            item = QListWidgetItem(Path(p).name)
            item.setData(Qt.ItemDataRole.UserRole, p)
            self.i2p_list.addItem(item)

    def _start_i2p(self):
        paths = [self.i2p_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.i2p_list.count())]
        if not paths:
            QMessageBox.warning(self, "提示", "未选择图片")
            return
        out_dir = Path(self.i2p_state["out_dir"]) if self.i2p_state["out_dir"] else Path(paths[0]).parent
        out_path = out_dir / "images_merged.pdf"

        set_status(self.i2p_status, "⏳ 正在转换中...", "warning")
        worker = TaskWorker(images_to_pdf, paths, out_path)
        self.i2p_worker = worker
        worker.finished_ok.connect(lambda r: set_status(self.i2p_status, f"✅ 合成成功:\n{r}", "success"))
        worker.failed.connect(lambda m: set_status(self.i2p_status, f"❌ 失败: {m}", "error"))
        worker.start()

    # ==========================================================
    # Tab 3：提取文本（多选 + 进度 + 停止）
    # ==========================================================
    def _build_extract_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)

        self.extract_state = {"paths": [], "out_dir": None}
        self.extract_worker = None

        title = QLabel("📝 PDF 全文文本提取")
        title.setStyleSheet(section_title_style())
        outer.addWidget(title)
        sub = QLabel()
        set_muted(sub, "支持一次选择多个 PDF 批量提取，每个文件生成同名 _text.txt")
        outer.addWidget(sub)

        drop = DropArea("📥 拖拽或点击选择多个 PDF", self._on_extract_files_dropped, mode="files", file_filter=PDF_FILTER)
        self.extract_list = QListWidget()
        self.extract_list.setMaximumHeight(110)
        self.extract_list.itemDoubleClicked.connect(self._remove_extract_item)

        out_row = QHBoxLayout()
        btn_out = QPushButton("更改输出目录")
        btn_out.clicked.connect(lambda: self._pick_out_dir(self.extract_state, self.extract_out_label))
        self.extract_out_label = QLabel()
        set_muted(self.extract_out_label, "📁 默认各自保存至原文件同级目录")
        out_row.addWidget(btn_out)
        out_row.addWidget(self.extract_out_label)
        out_row.addStretch()

        btn_row = QHBoxLayout()
        self.extract_start_btn = QPushButton("🚀 开始提取纯文本")
        style_primary(self.extract_start_btn)
        self.extract_start_btn.clicked.connect(self._start_extract)
        self.extract_stop_btn = QPushButton("停止")
        style_stop(self.extract_stop_btn)
        self.extract_stop_btn.setVisible(False)
        self.extract_stop_btn.clicked.connect(self._stop_extract)
        btn_clear_extract = make_clear_button(self.extract_list)
        btn_row.addWidget(self.extract_start_btn)
        btn_row.addWidget(self.extract_stop_btn)
        btn_row.addWidget(btn_clear_extract)
        btn_row.addStretch()

        self.extract_progress = ProgressBar()
        self.extract_progress.setVisible(False)
        self.extract_status = QLabel("")
        self.extract_status.setWordWrap(True)

        outer.addWidget(card(
            drop, self.extract_list, out_row, btn_row, self.extract_progress, self.extract_status,
        ))
        outer.addStretch()
        return widget

    def _on_extract_files_dropped(self, paths: list[str]):
        for p in paths:
            item = QListWidgetItem(Path(p).name)
            item.setData(Qt.ItemDataRole.UserRole, p)
            self.extract_list.addItem(item)

    def _remove_extract_item(self, item: QListWidgetItem):
        self.extract_list.takeItem(self.extract_list.row(item))

    def _stop_extract(self):
        if self.extract_worker:
            self.extract_worker.cancel()
            self.extract_stop_btn.setEnabled(False)

    def _start_extract(self):
        paths = [self.extract_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.extract_list.count())]
        if not paths:
            QMessageBox.warning(self, "提示", "请先选择至少一个 PDF")
            return

        worker = TaskWorker(extract_text_batch, paths, output_dir=self.extract_state["out_dir"])
        self.extract_worker = worker

        self.extract_start_btn.setEnabled(False)
        self.extract_stop_btn.setVisible(True)
        self.extract_stop_btn.setEnabled(True)
        self.extract_progress.setVisible(True)
        self.extract_progress.setRange(0, 100)
        self.extract_progress.setValue(0)
        set_status(self.extract_status, "⏳ 正在提取...", "warning")

        worker.progress.connect(self._on_extract_progress)
        worker.finished_ok.connect(self._on_extract_finished)
        worker.failed.connect(self._on_extract_failed)
        worker.cancelled.connect(self._on_extract_cancelled)
        worker.start()

    def _on_extract_progress(self, value):
        if isinstance(value, tuple):
            current, total = value
            fraction = current / total if total else 0
            self.extract_progress.setValue(int(fraction * 100))
            set_status(self.extract_status, f"⏳ 提取中 {current}/{total} ({fraction * 100:.1f}%)", "warning")

    def _reset_extract_buttons(self):
        self.extract_start_btn.setEnabled(True)
        self.extract_stop_btn.setVisible(False)
        self.extract_worker = None

    def _on_extract_finished(self, results):
        set_status(self.extract_status, f"✅ 提取完成，共 {len(results)} 个文件", "success")
        self._reset_extract_buttons()

    def _on_extract_failed(self, message):
        set_status(self.extract_status, f"❌ 失败: {message}", "error")
        self._reset_extract_buttons()

    def _on_extract_cancelled(self):
        set_status(self.extract_status, "⏹️ 已取消", "warning")
        self._reset_extract_buttons()
