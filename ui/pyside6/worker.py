# ui/pyside6/worker.py
#
# PySide6 版本的通用后台任务包装器。
#
# 对应 Flet 里 page.run_thread() + progress_callback/cancel_check 那一套模式，
# 但 tools/ 层完全不用改一行。不同的 tools 函数用的回调参数名并不统一——
# ffmpeg 系列用 progress_callback，视频下载用 progress_hook，
# 壁纸下载用 on_log + on_progress 两个——Worker 会用 inspect 自动探测
# 目标函数实际声明了哪些参数名，按需注入，调用方不用关心这些差异。
#
# 用法:
#   worker = TaskWorker(convert_to_mp4, video_path, output_dir=out_dir)
#   worker.progress.connect(self.on_progress)     # 接收 float/None/dict/(current,total)
#   worker.log.connect(self.on_log)               # 只有 on_log 类回调（壁纸下载）才会触发
#   worker.finished_ok.connect(self.on_finished)   # 接收函数的返回值
#   worker.failed.connect(self.on_failed)          # 接收错误信息字符串
#   worker.cancelled.connect(self.on_cancelled)    # 用户点了停止
#   worker.start()
#   ...
#   worker.cancel()  # 停止按钮调用这个

import inspect
import threading

from PySide6.QtCore import QThread, Signal

# 不同 tools 函数里"进度回调"参数可能叫这几个名字之一
_PROGRESS_PARAM_NAMES = ("progress_callback", "progress_hook", "on_progress")
_LOG_PARAM_NAMES = ("on_log",)


class TaskWorker(QThread):
    # progress 传出的值形态取决于被包装的函数：
    #   - 单个 float(0~1) 或 None：连续型进度（ffmpeg 系列：转码/合并/拼接/截取）
    #   - (current, total) 元组：计数型进度（图片批量转换、PDF 批量提取、壁纸下载）
    #   - dict：yt-dlp 风格的下载钩子数据（视频下载 progress_hook 收到的原始 data）
    # 由调用方（各个 View）根据自己包装的是哪个函数来解读，Worker 本身不关心
    progress = Signal(object)
    log = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self._cancel_event = threading.Event()

    def cancel(self):
        self._cancel_event.set()

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def _emit_progress(self, *cb_args):
        if len(cb_args) == 1:
            self.progress.emit(cb_args[0])
        else:
            self.progress.emit(tuple(cb_args))

    def _emit_log(self, message):
        self.log.emit(str(message))

    def run(self):
        call_kwargs = dict(self.kwargs)

        try:
            sig_params = inspect.signature(self.fn).parameters
        except (TypeError, ValueError):
            sig_params = {}

        for name in _PROGRESS_PARAM_NAMES:
            if name in sig_params and name not in call_kwargs:
                call_kwargs[name] = self._emit_progress

        for name in _LOG_PARAM_NAMES:
            if name in sig_params and name not in call_kwargs:
                call_kwargs[name] = self._emit_log

        if "cancel_check" in sig_params and "cancel_check" not in call_kwargs:
            call_kwargs["cancel_check"] = self._cancel_event.is_set

        try:
            result = self.fn(*self.args, **call_kwargs)
            self.finished_ok.emit(result)
        except Exception as ex:
            # FFmpegCancelled / DownloadCancelled / WallpaperCancelled / InterruptedError
            # 等各种"取消类"异常，统一按 _cancel_event 是否被设置来判断，
            # 不需要在这里挨个 import 每一种取消异常类型
            if self._cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.failed.emit(str(ex))
