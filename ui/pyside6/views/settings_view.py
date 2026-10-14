# ui/pyside6/views/settings_view.py

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QRadioButton, QButtonGroup, QComboBox, QApplication, QMessageBox,
)

from tools.utils.ffmpeg import check_ffmpeg_available, check_ffprobe_available, get_ffmpeg_path, get_ffprobe_path
from tools.utils.cookie import PLATFORM_INFO, import_cookie, get_cookie_status, remove_cookie
from tools.utils.paths import get_settings_path
from tools.multimedia.video import MP4_COMPATIBILITY_PRESETS

from ui.pyside6.widgets import card, wrap_scrollable
from ui.pyside6.theme import apply_theme_mode, set_status, set_muted, section_title_style, subsection_title_style

SETTINGS_PATH = get_settings_path()


def _load_settings() -> dict:
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data.setdefault("appearance", {}).setdefault("theme_mode", "system")
    data.setdefault("tree", {}).setdefault("default_max_depth", None)
    data.setdefault("video", {}).setdefault("mp4_compatibility", "standard")
    return data


def _save_settings(data: dict):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class SettingsViewInner(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = _load_settings()
        layout = QVBoxLayout(self)

        title = QLabel("⚙️ 系统设置")
        title.setStyleSheet(section_title_style(24))
        layout.addWidget(title)

        layout.addWidget(self._build_appearance_section())
        layout.addWidget(self._build_video_section())
        layout.addWidget(self._build_dependency_section())
        layout.addWidget(self._build_cookie_section())
        layout.addStretch()

    # ==========================================================
    # 外观设置
    # ==========================================================
    def _build_appearance_section(self):
        title = QLabel("🎨 外观设置")
        title.setStyleSheet(subsection_title_style())

        current_mode = self.settings.get("appearance", {}).get("theme_mode", "system")

        self.radio_system = QRadioButton("跟随系统")
        self.radio_light = QRadioButton("浅色")
        self.radio_dark = QRadioButton("深色")

        group = QButtonGroup(self)
        for rb, mode in [(self.radio_system, "system"), (self.radio_light, "light"), (self.radio_dark, "dark")]:
            group.addButton(rb)
            rb.setChecked(mode == current_mode)
            rb.toggled.connect(lambda checked, m=mode: self._on_theme_changed(m) if checked else None)

        row = QHBoxLayout()
        row.addWidget(self.radio_system)
        row.addWidget(self.radio_light)
        row.addWidget(self.radio_dark)
        row.addStretch()

        return card(title, row)

    def _on_theme_changed(self, mode: str):
        apply_theme_mode(QApplication.instance(), mode)
        self.settings.setdefault("appearance", {})["theme_mode"] = mode
        _save_settings(self.settings)

    # ==========================================================
    # 视频设置（MP4 编码兼容性）
    # ==========================================================
    def _build_video_section(self):
        title = QLabel("🎬 视频设置")
        title.setStyleSheet(subsection_title_style())

        self.mp4_compat_combo = QComboBox()
        for key, preset in MP4_COMPATIBILITY_PRESETS.items():
            self.mp4_compat_combo.addItem(preset["label"], key)
        current = self.settings.get("video", {}).get("mp4_compatibility", "standard")
        idx = self.mp4_compat_combo.findData(current)
        if idx >= 0:
            self.mp4_compat_combo.setCurrentIndex(idx)
        self.mp4_compat_combo.currentIndexChanged.connect(self._on_mp4_compatibility_changed)

        hint = QLabel()
        set_muted(
            hint,
            "通用高画质：H.264 High + YUV420P + AAC-LC\n"
            "老旧设备兼容：H.264 Baseline + YUV420P + AAC-LC",
        )
        hint.setWordWrap(True)

        row = QHBoxLayout()
        row.addWidget(QLabel("MP4 编码模式:"))
        row.addWidget(self.mp4_compat_combo)
        row.addStretch()

        return card(title, row, hint)

    def _on_mp4_compatibility_changed(self):
        key = self.mp4_compat_combo.currentData()
        self.settings.setdefault("video", {})["mp4_compatibility"] = key
        _save_settings(self.settings)

    # ==========================================================
    # 外部依赖检测
    # ==========================================================
    def _build_dependency_section(self):
        header_row = QHBoxLayout()
        title = QLabel("🔧 外部依赖检测")
        title.setStyleSheet(subsection_title_style())
        btn_recheck = QPushButton("重新检测")
        btn_recheck.clicked.connect(self._recheck_dependencies)
        header_row.addWidget(title)
        header_row.addStretch()
        header_row.addWidget(btn_recheck)

        self.ffmpeg_label = QLabel()
        self.ffprobe_label = QLabel()
        self._refresh_dependency_labels()

        self.dependency_card = card(header_row, self.ffmpeg_label, self.ffprobe_label)
        return self.dependency_card

    def _refresh_dependency_labels(self):
        ffmpeg_path = get_ffmpeg_path()
        ffprobe_path = get_ffprobe_path()
        ffmpeg_ok = check_ffmpeg_available()
        ffprobe_ok = check_ffprobe_available()

        set_status(self.ffmpeg_label, self._dep_line("FFmpeg", ffmpeg_ok, ffmpeg_path,
            "已安装，音视频转换/合并/截取功能可用",
            "未检测到，请确认 assets/ffmpeg/bin 中存在 ffmpeg，或将 FFmpeg 加入系统 PATH"),
            "success" if ffmpeg_ok else "error")

        set_status(self.ffprobe_label, self._dep_line("FFprobe", ffprobe_ok, ffprobe_path,
            "已安装，可读取媒体时长以计算精确进度",
            "未检测到，媒体处理仍可运行，但进度条只能显示忙碌动画"),
            "success" if ffprobe_ok else "warning")

    @staticmethod
    def _dep_line(name: str, ok: bool, path, hint_ok: str, hint_fail: str) -> str:
        icon = "✅" if ok else "❌"
        if ok and path:
            path_str = str(path).lower()
            source = "程序内置" if ("assets\\ffmpeg\\bin\\" in path_str or "assets/ffmpeg/bin/" in path_str) else "系统 PATH"
            return f"{icon} {name}：{hint_ok}（来源：{source}）"
        return f"{icon} {name}：{hint_fail}"

    def _recheck_dependencies(self):
        self._refresh_dependency_labels()

    # ==========================================================
    # Cookie 导入
    # ==========================================================
    def _build_cookie_section(self):
        title = QLabel("🍪 Cookie 导入")
        title.setStyleSheet(subsection_title_style())
        hint = QLabel()
        set_muted(
            hint,
            "部分平台（会员内容 / 需要登录的视频）需要导入 Cookie 才能下载。"
            "使用浏览器插件导出 Netscape 格式的 cookies.txt，选择对应平台后导入，"
            "文件会自动复制并重命名为标准名称，无需手动改名。",
        )
        hint.setWordWrap(True)

        self.platform_combo = QComboBox()
        for key, (_, label) in PLATFORM_INFO.items():
            self.platform_combo.addItem(label, key)

        btn_import = QPushButton("选择 Cookie 文件导入")
        btn_import.clicked.connect(self._import_cookie)

        import_row = QHBoxLayout()
        import_row.addWidget(self.platform_combo)
        import_row.addWidget(btn_import)
        import_row.addStretch()

        self.cookie_import_status = QLabel("")
        self.cookie_import_status.setWordWrap(True)

        self.cookie_status_rows_container = QVBoxLayout()
        self._refresh_cookie_status()

        return card(title, hint, import_row, self.cookie_import_status, QLabel("导入状态:"), self.cookie_status_rows_container)

    def _refresh_cookie_status(self):
        # 清空旧的状态行
        while self.cookie_status_rows_container.count():
            item = self.cookie_status_rows_container.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        status = get_cookie_status()
        for key, (_, label) in PLATFORM_INFO.items():
            imported = status.get(key, False)
            row = QHBoxLayout()
            icon = QLabel("✅" if imported else "⭕")
            name_label = QLabel(label)
            state_label = QLabel("已导入" if imported else "未导入")
            set_status(state_label, "已导入" if imported else "未导入", "success" if imported else "info")
            btn_remove = QPushButton("移除")
            btn_remove.setEnabled(imported)
            btn_remove.clicked.connect(lambda checked=False, k=key: self._remove_cookie(k))

            row.addWidget(icon)
            row.addWidget(name_label, stretch=1)
            row.addWidget(state_label)
            row.addWidget(btn_remove)

            row_widget = QWidget()
            row_widget.setLayout(row)
            self.cookie_status_rows_container.addWidget(row_widget)

    def _import_cookie(self):
        file, _ = QFileDialog.getOpenFileName(self, "选择 Cookie 文件", "", "文本文件 (*.txt)")
        if not file:
            return
        platform_key = self.platform_combo.currentData()
        try:
            target = import_cookie(platform_key, file)
            set_status(self.cookie_import_status, f"✅ 已导入并重命名为: {target.name}", "success")
        except Exception as ex:
            set_status(self.cookie_import_status, f"❌ 导入失败: {ex}", "error")
        self._refresh_cookie_status()

    def _remove_cookie(self, platform_key: str):
        try:
            remove_cookie(platform_key)
            set_status(self.cookie_import_status, "✅ 已移除该平台的 Cookie", "success")
        except Exception as ex:
            set_status(self.cookie_import_status, f"❌ {ex}", "error")
        self._refresh_cookie_status()


def SettingsView():
    """外部统一用函数式入口，跟其他 View 的类命名习惯保持一致的调用方式；
    内部再套一层 QScrollArea，对应 Flet 版整页 scroll=AUTO"""
    return wrap_scrollable(SettingsViewInner())
