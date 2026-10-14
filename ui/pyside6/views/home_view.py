# ui/pyside6/views/home_view.py

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from tools.utils.paths import get_assets_dir
from ui.pyside6.theme import MUTED

# 用 tools.utils.paths.get_assets_dir() 而不是自己拿 __file__ 现算路径——
# 后者在 PyInstaller 打包后会指向临时解压目录，跟之前 config/settings.json
# 踩过的坑是同一类问题，详见 tools/utils/paths.py 里的说明
ICON_PATH = get_assets_dir() / "icon.png"


class HomeView(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if ICON_PATH.exists():
            pixmap = QPixmap(str(ICON_PATH))
            icon_label.setPixmap(
                pixmap.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
        else:
            # 找不到自定义图标时退回 emoji，不至于首页留白
            icon_label.setText("📚")
            icon_label.setStyleSheet("font-size: 64px;")

        title = QLabel("万象阁")
        title.setStyleSheet("font-size: 32px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("极简、私密、高效的本地化数字工具空间")
        subtitle.setStyleSheet(f"font-size: 16px; color: {MUTED};")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hint = QLabel("请在左侧导航栏选择需要使用的功能模块 👈")
        hint.setStyleSheet("font-size: 14px; font-style: italic;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for w in (icon_label, title, subtitle, hint):
            layout.addWidget(w)
