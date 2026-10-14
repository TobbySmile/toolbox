# tools/utils/ffmpeg.py

"""
统一的 FFmpeg 调用封装。

支持：
1. 开发环境：
   - 优先使用项目 assets/ffmpeg/bin/ 下的 ffmpeg / ffprobe
   - 同时兼容旧目录：
       assets/ffmpeg/
       assets/
       ffmpeg/
       项目根目录
   - 最后回退到系统 PATH

2. Flet / PyInstaller 打包：
   - 支持 FLET_ASSETS_DIR
   - 支持 EXE 所在目录/assets/ffmpeg/bin
   - 支持 PyInstaller 的 _MEIPASS

3. FFmpeg 任务：
   - stdout / stderr 后台持续读取，避免管道阻塞
   - 实时进度回调
   - 终端实时日志与百分比
   - 支持取消
   - 支持精确进度 / 不定进度

4. yt-dlp：
   - 可通过 resolve_ffmpeg_bin_dir() 获取自带 FFmpeg 目录
"""

import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional


class FFmpegCancelled(Exception):
    """用户主动取消了 FFmpeg 任务。"""

    pass


# ============================================================
# 路径
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _exe_name(base: str) -> str:
    """根据当前系统返回可执行文件名。"""
    return f"{base}.exe" if platform.system() == "Windows" else base


def _get_resource_dir() -> Path:
    """
    获取程序资源目录。

    普通 Python：
        项目根目录

    Flet / PyInstaller：
        EXE 所在目录
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PROJECT_ROOT


def _bundled_ffmpeg_dir() -> Optional[Path]:
    """
    查找打包 / 项目自带的 FFmpeg bin 目录。

    优先级：
    1. FLET_ASSETS_DIR/ffmpeg/bin
    2. EXE目录/assets/ffmpeg/bin
    3. _MEIPASS/assets/ffmpeg/bin
    4. 项目根目录/assets/ffmpeg/bin

    找不到时返回 None。
    """
    resource_dir = _get_resource_dir()
    candidates: list[Path] = []

    assets_dir = os.environ.get("FLET_ASSETS_DIR")
    if assets_dir:
        candidates.append(Path(assets_dir) / "ffmpeg" / "bin")

    if getattr(sys, "frozen", False):
        candidates.append(resource_dir / "assets" / "ffmpeg" / "bin")

        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "assets" / "ffmpeg" / "bin")

    candidates.append(PROJECT_ROOT / "assets" / "ffmpeg" / "bin")

    for path in candidates:
        if path.is_dir():
            return path

    return None


def _ffmpeg_candidates(name: str) -> list[Path]:
    """
    返回 FFmpeg 可执行文件候选路径。

    第二版推荐目录：
        assets/ffmpeg/bin/

    同时兼容第一版可能使用的目录结构。
    """
    exe = _exe_name(name)
    resource_dir = _get_resource_dir()

    candidates = []

    # 推荐 / 打包目录
    bundled_dir = _bundled_ffmpeg_dir()
    if bundled_dir:
        candidates.append(bundled_dir / exe)

    # 第一版 / 旧项目目录兼容
    candidates.extend(
        [
            resource_dir / "assets" / "ffmpeg" / exe,
            resource_dir / "assets" / exe,
            resource_dir / "ffmpeg" / exe,
            resource_dir / exe,
        ]
    )

    # 去重，同时保持搜索顺序
    result: list[Path] = []
    seen: set[Path] = set()

    for path in candidates:
        path = path.resolve()
        if path not in seen:
            seen.add(path)
            result.append(path)

    return result


def _find_executable(name: str) -> Optional[str]:
    """
    查找 FFmpeg / FFprobe。

    优先项目自带版本，最后使用系统 PATH。
    """
    for path in _ffmpeg_candidates(name):
        if path.is_file():
            return str(path)

    return shutil.which(name)


def get_ffmpeg_path() -> Optional[str]:
    """返回 FFmpeg 完整路径，找不到时返回 None。"""
    return _find_executable("ffmpeg")


def get_ffprobe_path() -> Optional[str]:
    """返回 FFprobe 完整路径，找不到时返回 None。"""
    return _find_executable("ffprobe")


def resolve_ffmpeg_path() -> str:
    """
    返回可执行的 FFmpeg 路径。

    找不到项目自带 / 系统 PATH 时返回 'ffmpeg'，
    交给后续检查或 subprocess 自己处理。
    """
    return get_ffmpeg_path() or "ffmpeg"


def resolve_ffprobe_path() -> str:
    """同 resolve_ffmpeg_path()，用于 FFprobe。"""
    return get_ffprobe_path() or "ffprobe"


def resolve_ffmpeg_bin_dir() -> Optional[str]:
    """
    返回自带 FFmpeg 的 bin 目录。

    用于 yt-dlp：
        ffmpeg_location=resolve_ffmpeg_bin_dir()

    找不到自带版本时返回 None。
    """
    bundled_dir = _bundled_ffmpeg_dir()

    if bundled_dir and (
        (bundled_dir / _exe_name("ffmpeg")).is_file()
        or (bundled_dir / _exe_name("ffprobe")).is_file()
    ):
        return str(bundled_dir)

    return None


def check_ffmpeg_available() -> bool:
    """检查 FFmpeg 是否可用。"""
    path = get_ffmpeg_path()
    return bool(path and (Path(path).exists() if Path(path).is_absolute() else shutil.which(path)))


def check_ffprobe_available() -> bool:
    """检查 FFprobe 是否可用。"""
    path = get_ffprobe_path()
    return bool(path and (Path(path).exists() if Path(path).is_absolute() else shutil.which(path)))


# ============================================================
# FFprobe
# ============================================================

def get_duration_seconds(input_path: Path | str) -> Optional[float]:
    """
    使用 FFprobe 读取媒体总时长（秒）。

    读取失败时返回 None。
    """
    ffprobe = get_ffprobe_path()

    if not ffprobe:
        return None

    cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(input_path)]

    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=creationflags
        )
        value = result.stdout.strip()
        return float(value) if value else None

    except Exception:
        return None


# ============================================================
# FFmpeg 进度解析
# ============================================================

_PROGRESS_TIME_MS_RE = re.compile(r"^out_time_ms=(\d+)")
_PROGRESS_TIME_US_RE = re.compile(r"^out_time_us=(\d+)")

# 回调 / 终端刷新最多每 100ms 一次
_MIN_CALLBACK_INTERVAL = 0.1

# 主循环最长等待时间
# 也就是取消检测最长约 150ms 一次
_POLL_INTERVAL = 0.15


# ============================================================
# FFmpeg 执行
# ============================================================

def run_ffmpeg(
    args: list[str],
    total_duration: Optional[float] = None,
    progress_callback: Optional[Callable[[Optional[float]], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    label: str = "FFmpeg",
    print_to_console: bool = True,
) -> bool:
    """
    执行一次 FFmpeg 任务。

    参数：
        args:
            FFmpeg 参数列表。
            不需要传入 ffmpeg.exe，也不需要传 -y。

        total_duration:
            总时长（秒）。
            提供时可计算 0~1 精确进度。

        progress_callback:
            callback(fraction)
            fraction:
                0.0 ~ 1.0
                或 None（无法计算百分比时）

            回调始终运行在调用 run_ffmpeg() 的线程中。

        cancel_check:
            callback() -> bool
            返回 True 时终止 FFmpeg。

        label:
            终端任务名称。

        print_to_console:
            是否实时打印 FFmpeg 日志与进度。

    返回：
        True

    异常：
        FFmpegCancelled
        RuntimeError
    """

    # --------------------------------------------------------
    # 检查 FFmpeg
    # --------------------------------------------------------

    ffmpeg = get_ffmpeg_path()

    if not ffmpeg:
        raise RuntimeError(
            "未检测到 FFmpeg。\n"
            "请确认：\n"
            "1. assets/ffmpeg/bin/ffmpeg.exe 存在；或\n"
            "2. assets/ffmpeg/ffmpeg.exe 存在；或\n"
            "3. FFmpeg 已加入系统 PATH。"
        )

    # --------------------------------------------------------
    # 构造命令
    # --------------------------------------------------------

    cmd = [ffmpeg, "-y", "-nostats", "-progress", "pipe:1"] + args

    if print_to_console:
        print(f"\n[{label}] 开始执行: {' '.join(cmd)}", flush=True)

    # --------------------------------------------------------
    # 启动进程
    # --------------------------------------------------------

    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=creationflags,
    )

    stdout_queue: queue.Queue = queue.Queue()
    stderr_chunks: list[str] = []

    # --------------------------------------------------------
    # stdout 后台读取
    # --------------------------------------------------------

    def _pump_stdout():
        """
        持续读取 FFmpeg stdout。

        -progress pipe:1 会把进度信息写入 stdout。
        """
        try:
            if process.stdout is None:
                return

            for line in process.stdout:
                stdout_queue.put(line)

        except Exception:
            pass

        finally:
            stdout_queue.put(None)

    # --------------------------------------------------------
    # stderr 后台读取
    # --------------------------------------------------------

    def _pump_stderr():
        """
        持续读取 FFmpeg stderr。

        防止 stderr 管道写满导致 FFmpeg 阻塞。
        """
        try:
            if process.stderr is None:
                return

            for line in process.stderr:
                stderr_chunks.append(line)

                if print_to_console:
                    sys.stdout.write(f"[{label}] {line}")

                    if not line.endswith("\n"):
                        sys.stdout.write("\n")

                    sys.stdout.flush()

        except Exception:
            pass

    stdout_thread = threading.Thread(target=_pump_stdout, daemon=True)
    stderr_thread = threading.Thread(target=_pump_stderr, daemon=True)

    stdout_thread.start()
    stderr_thread.start()

    # --------------------------------------------------------
    # 状态
    # --------------------------------------------------------

    cancelled = False
    stdout_done = False
    last_report = 0.0

    # ========================================================
    # 主循环
    # ========================================================

    try:
        while True:
            # ------------------------------------------------
            # 检查取消
            # ------------------------------------------------

            if cancel_check and cancel_check():
                cancelled = True
                break

            # ------------------------------------------------
            # FFmpeg 已退出 + stdout 已读完
            # ------------------------------------------------

            if process.poll() is not None and stdout_done:
                break

            # ------------------------------------------------
            # 读取进度
            # ------------------------------------------------

            try:
                line = stdout_queue.get(timeout=_POLL_INTERVAL)
            except queue.Empty:
                continue

            # ------------------------------------------------
            # stdout EOF
            # ------------------------------------------------

            if line is None:
                stdout_done = True
                continue

            line = line.strip()
            now = time.monotonic()

            # ------------------------------------------------
            # out_time_ms / out_time_us
            # ------------------------------------------------

            match = _PROGRESS_TIME_MS_RE.match(line) or _PROGRESS_TIME_US_RE.match(line)

            if match and total_duration and total_duration > 0:
                if now - last_report > _MIN_CALLBACK_INTERVAL:
                    current_seconds = int(match.group(1)) / 1_000_000
                    fraction = max(0.0, min(current_seconds / total_duration, 1.0))

                    if progress_callback:
                        progress_callback(fraction)

                    if print_to_console:
                        sys.stdout.write(f"\r[{label}] 进度: {fraction * 100:5.1f}%")
                        sys.stdout.flush()

                    last_report = now

            # ------------------------------------------------
            # FFmpeg 完成
            # ------------------------------------------------

            elif line == "progress=end":
                if progress_callback:
                    progress_callback(1.0)

                if print_to_console:
                    sys.stdout.write(f"\r[{label}] 进度: 100.0%\n")
                    sys.stdout.flush()

            # ------------------------------------------------
            # 无法计算百分比
            # ------------------------------------------------

            elif (
                (line.startswith("out_time_ms=") or line.startswith("out_time_us="))
                and not total_duration
            ):
                if now - last_report > _MIN_CALLBACK_INTERVAL:
                    if progress_callback:
                        progress_callback(None)

                    if print_to_console:
                        sys.stdout.write(f"\r[{label}] 处理中...")
                        sys.stdout.flush()

                    last_report = now

    # ========================================================
    # 清理
    # ========================================================

    finally:
        # ----------------------------------------------------
        # 取消
        # ----------------------------------------------------

        if cancelled:
            process.terminate()

            try:
                process.wait(timeout=3)

            except subprocess.TimeoutExpired:
                process.kill()

                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass

        # ----------------------------------------------------
        # 正常结束
        # ----------------------------------------------------

        else:
            process.wait()

        # ----------------------------------------------------
        # 等待读取线程
        # ----------------------------------------------------

        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)

        # ----------------------------------------------------
        # 关闭管道
        # ----------------------------------------------------

        if process.stdout:
            process.stdout.close()

        if process.stderr:
            process.stderr.close()

    # ========================================================
    # 任务结束
    # ========================================================

    if print_to_console:
        print(flush=True)

    # --------------------------------------------------------
    # 用户取消
    # --------------------------------------------------------

    if cancelled:
        if print_to_console:
            print(f"[{label}] ⏹️ 已被用户取消", flush=True)

        raise FFmpegCancelled("用户手动取消了任务")

    # --------------------------------------------------------
    # FFmpeg 执行失败
    # --------------------------------------------------------

    if process.returncode != 0:
        err_text = "".join(stderr_chunks)[-2000:]

        if print_to_console:
            print(
                f"[{label}] ❌ 执行失败，退出码 {process.returncode}",
                flush=True,
            )

        raise RuntimeError(err_text or "ffmpeg 执行失败")

    # --------------------------------------------------------
    # 成功
    # --------------------------------------------------------

    if print_to_console:
        print(f"[{label}] ✅ 完成", flush=True)

    return True