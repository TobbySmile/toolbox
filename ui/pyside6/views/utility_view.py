# ui/pyside6/views/utility_view.py

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel, QPushButton,
    QFileDialog, QLineEdit, QTextEdit, QSlider, QCheckBox, QSpinBox,
    QMessageBox, QApplication,
)
from PySide6.QtCore import Qt, QTimer

from tools.password import generate_password
from tools.bmi import calculate_bmi, get_bmi_status
from tools.rmb import convert_rmb
from tools.chinese_convert import to_traditional, to_simplified
from tools.symbols import SYMBOLS
from tools.tree import write_tree
from tools.utils.paths import get_settings_path

from ui.pyside6.worker import TaskWorker
from ui.pyside6.widgets import DropArea, card, wrap_scrollable, FlowLayout, flash_button_feedback
from ui.pyside6.theme import set_status, set_muted, style_primary, section_title_style

SETTINGS_PATH = get_settings_path()


def _load_default_max_depth():
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return data.get("tree", {}).get("default_max_depth")
    except Exception:
        return None


def _copy_to_clipboard(text: str):
    QApplication.clipboard().setText(text)


def _flash_symbol_copied(button: QPushButton, duration_ms: int = 500):
    """
    符号表按钮点击复制后的反馈：符号表按钮又多又密，如果跟 flash_button_feedback
    一样换成"✅"文字，字符宽度一变，FlowLayout 里所有后续按钮的位置都要跟着
    重新排布，会有明显的抖动感。改成只闪一下背景色，不改文字、不影响布局。
    """
    if hasattr(button, "_symbol_flash_timer"):
        button._symbol_flash_timer.stop()
    else:
        button._symbol_flash_timer = QTimer(button)
        button._symbol_flash_timer.setSingleShot(True)
        button._symbol_flash_timer.timeout.connect(lambda: button.setStyleSheet("font-size: 20px;"))

    button.setStyleSheet("font-size: 20px; background-color: #16A34A; color: white;")
    button._symbol_flash_timer.start(duration_ms)


class UtilityView(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        tabs.addTab(wrap_scrollable(self._build_calc_tab()), "🧮 转换与计算")
        tabs.addTab(wrap_scrollable(self._build_symbols_tab()), "🔑 密码与符号")
        tabs.addTab(wrap_scrollable(self._build_tree_tab()), "🌳 系统与文件")

    # ==========================================================
    # Tab 1：BMI / 人民币大写 / 繁简转换
    # ==========================================================
    def _build_calc_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)

        # ---- BMI ----
        self.bmi_height_input = QLineEdit()
        self.bmi_height_input.setPlaceholderText("身高(cm)")
        self.bmi_weight_input = QLineEdit()
        self.bmi_weight_input.setPlaceholderText("体重(kg)")
        btn_bmi = QPushButton("计算")
        btn_bmi.clicked.connect(self._calc_bmi)
        self.bmi_result = QLabel("结果将显示于此")
        self.bmi_result.setStyleSheet("color: #2563EB; font-size: 15px;")

        # 输入框和按钮一行，结果单独一行显示——原来结果紧跟在按钮右边，
        # 输入框一多就显得很挤，分成两行留出呼吸空间
        bmi_input_row = QHBoxLayout()
        bmi_input_row.addWidget(self.bmi_height_input)
        bmi_input_row.addWidget(self.bmi_weight_input)
        bmi_input_row.addWidget(btn_bmi)
        bmi_result_row = QHBoxLayout()
        bmi_result_row.addWidget(self.bmi_result)
        bmi_result_row.addStretch()

        # ---- RMB ----
        self.rmb_input = QLineEdit()
        self.rmb_input.setPlaceholderText("输入金额 (如 1234.56)")
        btn_rmb = QPushButton("转换")
        btn_rmb.clicked.connect(self._calc_rmb)
        self.rmb_output = QLineEdit()
        self.rmb_output.setReadOnly(True)
        btn_rmb_copy = QPushButton("复制")
        btn_rmb_copy.clicked.connect(lambda: (_copy_to_clipboard(self.rmb_output.text()), flash_button_feedback(btn_rmb_copy)))

        rmb_row1 = QHBoxLayout()
        rmb_row1.addWidget(self.rmb_input)
        rmb_row1.addWidget(btn_rmb)
        rmb_row2 = QHBoxLayout()
        rmb_row2.addWidget(self.rmb_output)
        rmb_row2.addWidget(btn_rmb_copy)

        # ---- 繁简转换 ----
        self.zh_input = QTextEdit()
        self.zh_input.setPlaceholderText("输入中文文本")
        self.zh_input.setMaximumHeight(80)
        self.zh_output = QTextEdit()
        self.zh_output.setReadOnly(True)
        self.zh_output.setMaximumHeight(80)
        btn_traditional = QPushButton("转繁体")
        btn_traditional.clicked.connect(lambda: self._calc_zh("t"))
        btn_simplified = QPushButton("转简体")
        btn_simplified.clicked.connect(lambda: self._calc_zh("s"))
        btn_zh_copy = QPushButton("复制")
        btn_zh_copy.clicked.connect(lambda: (_copy_to_clipboard(self.zh_output.toPlainText()), flash_button_feedback(btn_zh_copy)))

        zh_btn_row = QHBoxLayout()
        zh_btn_row.addWidget(btn_traditional)
        zh_btn_row.addWidget(btn_simplified)
        zh_out_row = QHBoxLayout()
        zh_out_row.addWidget(self.zh_output)
        zh_out_row.addWidget(btn_zh_copy)

        outer.addWidget(card(QLabel("⚖️ BMI 计算"), bmi_input_row, bmi_result_row))
        outer.addWidget(card(QLabel("💴 人民币大写转换"), rmb_row1, rmb_row2))
        outer.addWidget(card(QLabel("🔄 繁简转换"), self.zh_input, zh_btn_row, zh_out_row))
        outer.addStretch()
        return widget

    def _calc_bmi(self):
        try:
            val = calculate_bmi(float(self.bmi_height_input.text()), float(self.bmi_weight_input.text()))
            status = get_bmi_status(val)
            self.bmi_result.setText(f"👉 BMI: {val} ({status})")
            self.bmi_result.setStyleSheet("color: #DC2626;" if status == "肥胖" else "color: #16A34A;")
        except Exception:
            self.bmi_result.setText("❌ 输入无效")
            self.bmi_result.setStyleSheet("color: #DC2626;")

    def _calc_rmb(self):
        try:
            self.rmb_output.setText(convert_rmb(float(self.rmb_input.text())))
        except Exception:
            QMessageBox.warning(self, "提示", "❌ 输入金额无效")

    def _calc_zh(self, mode: str):
        text = self.zh_input.toPlainText()
        if not text:
            return
        self.zh_output.setPlainText(to_traditional(text) if mode == "t" else to_simplified(text))

    # ==========================================================
    # Tab 2：密码生成 + 常用符号表
    # ==========================================================
    def _build_symbols_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)

        # ---- 密码生成 ----
        self.pwd_len_slider = QSlider(Qt.Orientation.Horizontal)
        self.pwd_len_slider.setRange(4, 32)
        self.pwd_len_slider.setValue(16)
        self.pwd_len_label = QLabel("16 位")
        self.pwd_len_slider.valueChanged.connect(lambda v: self.pwd_len_label.setText(f"{v} 位"))
        len_row = QHBoxLayout()
        len_row.addWidget(self.pwd_len_slider)
        len_row.addWidget(self.pwd_len_label)

        self.cb_num = QCheckBox("数字 0-9")
        self.cb_num.setChecked(True)
        self.cb_low = QCheckBox("小写字母 a-z")
        self.cb_low.setChecked(True)
        self.cb_up = QCheckBox("大写字母 A-Z")
        self.cb_up.setChecked(True)
        self.cb_sym = QCheckBox("特殊字符")
        self.cb_sym.setChecked(True)
        check_row = QHBoxLayout()
        for cb in (self.cb_num, self.cb_low, self.cb_up, self.cb_sym):
            check_row.addWidget(cb)

        btn_gen = QPushButton("生成密码")
        btn_gen.clicked.connect(self._gen_password)
        self.pwd_output = QLineEdit()
        self.pwd_output.setReadOnly(True)
        btn_pwd_copy = QPushButton("复制")
        btn_pwd_copy.clicked.connect(lambda: (_copy_to_clipboard(self.pwd_output.text()), flash_button_feedback(btn_pwd_copy)))
        pwd_row = QHBoxLayout()
        pwd_row.addWidget(btn_gen)
        pwd_row.addWidget(self.pwd_output)
        pwd_row.addWidget(btn_pwd_copy)

        outer.addWidget(card(QLabel("🔐 强密码生成"), len_row, check_row, pwd_row))

        # ---- 符号表（点击复制，自动换行）----
        symbol_sections = [QLabel("✨ 常用符号表 (点击即复制)")]
        for category, chars in SYMBOLS.items():
            cat_label = QLabel(f"📌 {category}")
            cat_label.setStyleSheet("color: #6B7280;")
            symbol_sections.append(cat_label)

            flow_widget = QWidget()
            flow = FlowLayout(flow_widget, h_spacing=8, v_spacing=8)
            for char in chars:
                btn = QPushButton(char)
                # 之前 30px 高、默认字号，符号本身很小的时候点击目标显得局促；
                # 加大尺寸和字号，点击区域也更好按
                btn.setFixedHeight(44)
                btn.setMinimumWidth(44)
                btn.setStyleSheet("font-size: 20px;")
                btn.clicked.connect(lambda checked=False, c=char, b=btn: (_copy_to_clipboard(c), _flash_symbol_copied(b)))
                flow.addWidget(btn)
            symbol_sections.append(flow_widget)

        outer.addWidget(card(*symbol_sections))
        outer.addStretch()
        return widget

    def _gen_password(self):
        try:
            pwd = generate_password(
                self.pwd_len_slider.value(),
                self.cb_num.isChecked(), self.cb_low.isChecked(),
                self.cb_up.isChecked(), self.cb_sym.isChecked(),
            )
            self.pwd_output.setText(pwd)
        except Exception as ex:
            QMessageBox.warning(self, "提示", str(ex))

    # ==========================================================
    # Tab 3：目录树生成（支持选定扫描深度）
    # ==========================================================
    def _build_tree_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)

        self.tree_state = {"scan_dir": None, "out_dir": None}

        title = QLabel("🌳 文件夹目录树生成")
        title.setStyleSheet(section_title_style())
        outer.addWidget(title)
        sub = QLabel()
        set_muted(sub, "一键扫描选定文件夹，在同级目录生成结构清晰的 txt 文本文件")
        outer.addWidget(sub)

        scan_drop = DropArea("📥 拖拽或点击选择要扫描的文件夹", self._on_scan_dir_selected, mode="folder")
        self.scan_dir_label = QLabel()
        set_muted(self.scan_dir_label, "未选择")

        out_row = QHBoxLayout()
        btn_out = QPushButton("选择输出文件夹")
        btn_out.clicked.connect(self._pick_tree_out_dir)
        self.tree_out_label = QLabel()
        set_muted(self.tree_out_label, "📁 默认输出至此文件夹同级目录")
        out_row.addWidget(btn_out)
        out_row.addWidget(self.tree_out_label)
        out_row.addStretch()

        default_depth = _load_default_max_depth()
        self.depth_check = QCheckBox("限制扫描深度")
        self.depth_check.setChecked(default_depth is not None)
        self.depth_spin = QSpinBox()
        self.depth_spin.setRange(1, 50)
        self.depth_spin.setValue(default_depth if default_depth else 2)
        self.depth_spin.setEnabled(default_depth is not None)
        self.depth_check.toggled.connect(self.depth_spin.setEnabled)
        depth_row = QHBoxLayout()
        depth_row.addWidget(self.depth_check)
        depth_row.addWidget(self.depth_spin)
        depth_row.addStretch()

        depth_hint = QLabel()
        set_muted(depth_hint, "默认不限制深度，扫描全部文件；开启后仅展开到指定层数")

        btn_generate = QPushButton("🚀 开始生成")
        style_primary(btn_generate)
        btn_generate.clicked.connect(self._start_tree)
        self.tree_status = QLabel("")
        self.tree_status.setWordWrap(True)

        outer.addWidget(card(
            scan_drop, self.scan_dir_label, out_row,
            depth_row, depth_hint, btn_generate, self.tree_status,
        ))
        outer.addStretch()
        return widget

    def _on_scan_dir_selected(self, paths: list[str]):
        self.tree_state["scan_dir"] = paths[0]
        self.scan_dir_label.setText(f"📁 {paths[0]}")

    def _pick_tree_out_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        if folder:
            self.tree_state["out_dir"] = folder
            self.tree_out_label.setText(f"📁 输出至: {folder}")

    def _start_tree(self):
        if not self.tree_state["scan_dir"]:
            QMessageBox.warning(self, "提示", "请先选择要扫描的目录")
            return

        max_depth = self.depth_spin.value() if self.depth_check.isChecked() else None

        target_path = Path(self.tree_state["scan_dir"])
        out_dir = Path(self.tree_state["out_dir"]) if self.tree_state["out_dir"] else target_path.parent
        out_file = out_dir / f"{target_path.name}_tree.txt"

        set_status(self.tree_status, "⏳ 正在扫描生成目录树...", "warning")
        worker = TaskWorker(write_tree, target_path, out_file, max_depth=max_depth)
        self.tree_worker = worker
        worker.finished_ok.connect(lambda _r: set_status(self.tree_status, f"✅ 生成成功！文件位于:\n{out_file}", "success"))
        worker.failed.connect(lambda m: set_status(self.tree_status, f"❌ 失败: {m}", "error"))
        worker.start()
