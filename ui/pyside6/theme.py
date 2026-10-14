# ui/pyside6/theme.py
#
# 统一视觉样式，让 PySide6 版本不再是"默认 Qt 控件堆出来的样子"，
# 尽量向 Flet 版本的 Material Design 观感靠拢：圆角按钮、强调色、
# 卡片式分区、跟 Flet 版一致的状态文字配色（成功绿/警告橙/错误红），
# 以及跟 Flet 版一致的字体（Microsoft YaHei UI）。
#
# v2 新增：深色模式样式表 + apply_theme_mode()，配合设置页的外观切换。
# 说明：Qt 的"系统跟随"没有 Flet 那样天然的 ThemeMode.SYSTEM 支持，
# 这里 "system" 简化处理为固定使用浅色样式表（多数桌面场景下这是更安全的默认值，
# 后续如果需要精确跟随系统深浅色，可以通过 QApplication.styleHints() 检测，
# 目前先保证"浅色/深色"两个明确选项能正常工作）。
#
# 用法：
#   from ui.pyside6.theme import apply_theme_mode, set_status, style_primary, style_stop
#   apply_theme_mode(app, "dark")              # 在 QApplication 上应用
#   set_status(self.img_status, "✅ 转换成功", "success")
#   style_primary(self.img_start_btn)          # 主操作按钮：强调色填充
#   style_stop(self.img_stop_btn)              # 停止按钮：红色调

ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
SUCCESS = "#16A34A"
WARNING = "#F97316"
ERROR = "#DC2626"
MUTED = "#6B7280"

STATUS_COLORS = {
    "info": MUTED,
    "success": SUCCESS,
    "warning": WARNING,
    "error": ERROR,
}

APP_FONT_FAMILY = "Microsoft YaHei UI"


def _base_stylesheet(bg: str, base: str, alt_base: str, text: str, mid: str, button_bg: str) -> str:
    return f"""
QWidget {{
    font-family: "{APP_FONT_FAMILY}", "Segoe UI", sans-serif;
    font-size: 14px;
    color: {text};
    background: {bg};
}}

QMainWindow {{
    background: {bg};
}}

QTabWidget::pane {{
    border: none;
    top: -1px;
}}

QTabBar::tab {{
    padding: 10px 18px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    color: {text};
}}

QTabBar::tab:selected {{
    background: rgba(37, 99, 235, 0.14);
    font-weight: bold;
}}

QTabBar::tab:hover {{
    background: rgba(37, 99, 235, 0.06);
}}

QPushButton {{
    padding: 8px 16px;
    border-radius: 6px;
    border: 1px solid {mid};
    background: {button_bg};
    color: {text};
}}

QPushButton:hover {{
    border-color: {ACCENT};
}}

QPushButton:disabled {{
    color: {mid};
}}

QPushButton#primaryButton {{
    background: {ACCENT};
    color: white;
    border: none;
    font-weight: bold;
}}

QPushButton#primaryButton:hover {{
    background: {ACCENT_HOVER};
}}

QPushButton#stopButton {{
    background: #FEE2E2;
    color: #991B1B;
    border: 1px solid #FCA5A5;
    font-weight: bold;
}}

QPushButton#stopButton:hover {{
    background: #FECACA;
}}

QLineEdit, QComboBox, QSpinBox, QTextEdit {{
    padding: 6px 10px;
    border: 1px solid {mid};
    border-radius: 6px;
    background: {base};
    color: {text};
}}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {{
    border-color: {ACCENT};
}}

QProgressBar {{
    border: none;
    border-radius: 6px;
    background: {alt_base};
    min-height: 10px;
    max-height: 10px;
    text-align: center;
}}

QProgressBar::chunk {{
    border-radius: 6px;
    background: {ACCENT};
}}

QFrame#card {{
    border: 1px solid {mid};
    border-radius: 10px;
    background: {base};
}}

QListWidget {{
    border: 1px solid {mid};
    border-radius: 8px;
    padding: 4px;
    background: {base};
    color: {text};
}}

QScrollArea {{
    border: none;
    background: transparent;
}}

QRadioButton, QCheckBox {{
    color: {text};
    spacing: 6px;
}}
"""


APP_STYLESHEET = _base_stylesheet(
    bg="#F5F5F7", base="#FFFFFF", alt_base="#EDEDF0", text="#1A1A1A", mid="#D1D5DB", button_bg="#FFFFFF",
)

DARK_STYLESHEET = _base_stylesheet(
    bg="#17181C", base="#1F2126", alt_base="#2A2C33", text="#E5E7EB", mid="#3A3D45", button_bg="#25272E",
)

THEME_STYLESHEETS = {
    "light": APP_STYLESHEET,
    "dark": DARK_STYLESHEET,
    "system": APP_STYLESHEET,  # 简化处理，见文件头说明
}


def apply_theme_mode(app, mode: str) -> None:
    """mode: 'light' / 'dark' / 'system'"""
    app.setStyleSheet(THEME_STYLESHEETS.get(mode, APP_STYLESHEET))


def set_status(label, message: str, level: str = "info") -> None:
    """统一设置状态文字内容 + 颜色，level 取值：info / success / warning / error"""
    color = STATUS_COLORS.get(level, MUTED)
    label.setStyleSheet(f"color: {color};")
    label.setText(message)


def set_muted(label, text: str) -> None:
    """默认灰色提示文字，对应 Flet 的 ft.Colors.GREY_500"""
    label.setStyleSheet(f"color: {MUTED};")
    label.setText(text)


def style_primary(button) -> None:
    button.setObjectName("primaryButton")
    button.style().unpolish(button)
    button.style().polish(button)


def style_stop(button) -> None:
    button.setObjectName("stopButton")
    button.style().unpolish(button)
    button.style().polish(button)


def section_title_style(size: int = 20) -> str:
    return f"font-size: {size}px; font-weight: bold;"


def subsection_title_style(size: int = 16) -> str:
    return f"font-size: {size}px; font-weight: bold;"
