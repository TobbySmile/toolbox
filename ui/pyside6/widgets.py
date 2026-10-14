# ui/pyside6/widgets.py
#
# 跨视图复用的通用组件。
#
#   DropArea：拖拽和点击选择合并成一个交互面——整个区域本身就是可点击的
#     文件选择入口，不再需要在拖拽区域下面另外放一个"选择文件"按钮。
#   card() / wrap_scrollable()：卡片分区 + 滚动包装，各视图统一复用。
#   FlowLayout：Qt 没有原生的自动换行布局，符号表这种"一排 chip 按钮，
#     宽度不够自动换行"的场景需要自己实现，对应 Flet 的 ft.Row(wrap=True)。

from pathlib import Path

from PySide6.QtCore import Qt, QRect, QSize, QPoint, QTimer
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QPushButton, QFileDialog, QWidget,
    QScrollArea, QLayout, QSizePolicy, QProgressBar, QListWidget,
)


def flash_button_feedback(button: QPushButton, feedback_text: str = "✅ 已复制", duration_ms: int = 1200):
    """
    点击"复制"这类按钮后，短暂把按钮文字换成"已复制"提示，过一会儿自动
    换回来——对应 Flet 版点复制后弹一下 SnackBar 的效果。不用额外占地方
    的提示控件，直接复用按钮自己的文字位置，最省事也最不容易被忽略。

    如果按钮在提示还没消失之前又被再次点击，计时器会重新开始计时，
    不会出现"提示文字换回一半又被打断"的情况。
    """
    original_text = getattr(button, "_original_text", None)
    if original_text is None:
        original_text = button.text()
        button._original_text = original_text

    button.setText(feedback_text)
    button.setEnabled(False)

    def _restore():
        button.setText(button._original_text)
        button.setEnabled(True)

    # 用按钮自身作为计时器的 parent，按钮销毁时计时器也会跟着清理，
    # 同时保证同一个按钮多次点击只有最后一次计时生效
    if hasattr(button, "_flash_timer"):
        button._flash_timer.stop()
    else:
        button._flash_timer = QTimer(button)
        button._flash_timer.setSingleShot(True)
        button._flash_timer.timeout.connect(_restore)
    button._flash_timer.start(duration_ms)


def make_clear_button(list_widget: QListWidget, extra_clear=None, text: str = "🗑️ 清空列表") -> QPushButton:
    """
    生成一个"清空列表"按钮，统一处理"选完文件转换一次之后，
    下次再选文件时上次的残留还在列表里、删不掉"这个问题——
    每个用到可累加文件列表的地方都应该配一个这个按钮。

    extra_clear: 除了清空 QListWidget 本身，如果还有额外的 Python 状态
        （比如某个 list/dict）需要一起清空，通过这个回调传进来。
    """
    btn = QPushButton(text)

    def _on_clicked():
        list_widget.clear()
        if extra_clear:
            extra_clear()

    btn.clicked.connect(_on_clicked)
    return btn


class ProgressBar(QProgressBar):
    """
    统一的进度条组件。

    Bug 说明：主题样式表把 QProgressBar 的高度限制在 10px（min/max-height），
    但 QProgressBar 默认会在条内显示百分比文字——10px 的高度完全放不下这行字，
    文字会被上下顶满，看起来又挤又丑。而每个用到进度条的地方，旁边其实都已经
    有一个单独的状态 QLabel 在显示同样的百分比文字了（比如"⏳ 处理中... 45.2%"），
    条内文字纯属多余。所以这里直接把条内文字关掉，而不是加高进度条来"腾地方"
    给一段本来就是重复信息的文字。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setTextVisible(False)


class DropArea(QFrame):
    """
    统一的文件输入区域：拖拽和点击选择合并成一个交互面。

    mode:
        "file"    单文件
        "files"   多文件
        "folder"  文件夹
    accept_dirs:
        拖拽时是否接受文件夹（mode="folder" 时自动为 True）
    secondary_label / secondary_mode:
        可选的第二入口（比如图片 Tab 主入口是多选文件，
        再给一个"或选择整个文件夹"的次要链接按钮）
    """

    def __init__(
        self,
        hint_text: str,
        on_selected,
        mode: str = "files",
        file_filter: str = "",
        accept_dirs: bool = False,
        secondary_label: str | None = None,
        secondary_mode: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.on_selected = on_selected
        self.mode = mode
        self.file_filter = file_filter
        self.accept_dirs = accept_dirs or mode == "folder"

        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(76)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._set_idle_style()

        layout = QVBoxLayout(self)
        self.hint_label = QLabel(hint_text)
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        if secondary_label and secondary_mode:
            btn = QPushButton(secondary_label)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { border: none; color: #2563EB; background: transparent; padding: 2px; }"
                "QPushButton:hover { text-decoration: underline; }"
            )
            # 点击次要按钮时不应该再冒泡触发外层 DropArea 自己的点击逻辑，
            # Qt 子控件默认会吃掉这次点击事件，不会传给父级 mousePressEvent
            btn.clicked.connect(lambda: self._open_dialog(secondary_mode))
            layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _set_idle_style(self):
        self.setStyleSheet("""
            DropArea { border: 2px dashed palette(mid); border-radius: 8px; background: palette(alternate-base); }
        """)

    def _set_hover_style(self):
        self.setStyleSheet("""
            DropArea { border: 2px dashed #2563EB; border-radius: 8px; background: rgba(37, 99, 235, 0.08); }
        """)

    def set_hint(self, text: str):
        self.hint_label.setText(text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._open_dialog(self.mode)
        super().mousePressEvent(event)

    def _open_dialog(self, mode: str):
        if mode == "folder":
            folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
            if folder:
                self.on_selected([folder])
        elif mode == "file":
            file, _ = QFileDialog.getOpenFileName(self, "选择文件", "", self.file_filter)
            if file:
                self.on_selected([file])
        else:  # "files"
            files, _ = QFileDialog.getOpenFileNames(self, "选择文件", "", self.file_filter)
            if files:
                self.on_selected(files)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self._set_hover_style()
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._set_idle_style()

    def dropEvent(self, event):
        self._set_idle_style()
        paths = []
        for url in event.mimeData().urls():
            local_path = url.toLocalFile()
            if not local_path:
                continue
            p = Path(local_path)
            if p.is_dir():
                if self.accept_dirs:
                    paths.append(str(p))
            else:
                paths.append(str(p))
        if paths:
            self.on_selected(paths)
        event.acceptProposedAction()


def card(*widgets_or_layouts) -> QFrame:
    """卡片式分区容器，对应 Flet 版 ft.Container(padding=20, ...) 的视觉分隔效果"""
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(10)
    for item in widgets_or_layouts:
        if isinstance(item, QWidget):
            layout.addWidget(item)
        else:
            layout.addLayout(item)
    return frame


def wrap_scrollable(inner: QWidget) -> QWidget:
    """对应 Flet 版每个 Tab 内容外层的 scroll=ft.ScrollMode.AUTO"""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(inner)
    return scroll


class FlowLayout(QLayout):
    """
    自动换行的流式布局，对应 Flet 的 ft.Row(controls, wrap=True)。
    Qt 没有内置这个功能，这是社区里通用的标准实现手法
    （逐个摆放子控件，一行放不下就换行）。用于符号表这种
    "一排 chip 按钮，根据窗口宽度自动折行"的场景。
    """

    def __init__(self, parent=None, margin=0, h_spacing=6, v_spacing=6):
        super().__init__(parent)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        left, top, right, bottom = self.getContentsMargins()
        effective_rect = rect.adjusted(left, top, -right, -bottom)
        x, y = effective_rect.x(), effective_rect.y()
        line_height = 0

        for item in self._items:
            widget = item.widget()
            space_x, space_y = self._h_spacing, self._v_spacing
            next_x = x + item.sizeHint().width() + space_x

            if next_x - space_x > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y() + bottom
