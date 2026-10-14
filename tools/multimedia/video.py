# tools/multimedia/video.py

import json
import subprocess
from pathlib import Path
from typing import Callable, Optional

from tools.utils.file import check_file, safe_output_path
from tools.utils.ffmpeg import get_duration_seconds, get_ffprobe_path, run_ffmpeg


CRF_PRESETS = {
    "1": ("高画质", "18"),
    "2": ("标准", "23"),
    "3": ("压缩", "28"),
}

# MP4 编码模式：
# compatible：优先兼容老旧设备
# standard：兼顾画质与现代设备兼容性
MP4_COMPATIBILITY_PRESETS = {
    "standard": {
        "label": "通用高画质",
        "profile": "high",
        "level": "4.1",
        "pix_fmt": "yuv420p",
        "audio_profile": "aac_low",
    },
    "compatible": {
        "label": "老旧设备兼容",
        "profile": "baseline",
        "level": "4.0",
        "pix_fmt": "yuv420p",
        "audio_profile": "aac_low",
    },
}


def get_original_bitrate(input_path: Path) -> str:
    """
    获取原始视频码率。

    优先使用项目自带的 FFprobe，
    找不到时由调用方使用默认码率。
    """
    ffprobe = get_ffprobe_path()

    if not ffprobe:
        return "2000k"

    cmd = [
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        str(input_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )

        data = json.loads(result.stdout)

        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                bitrate = stream.get("bit_rate")
                if bitrate:
                    return f"{int(bitrate) // 1000}k"

    except Exception:
        pass

    return "2000k"


def convert_to_mp4(
    input_path: str,
    crf: str = "23",
    output_dir=None,
    compatibility: str = "standard",
    progress_callback: Optional[Callable[[Optional[float]], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
):
    """
    转换为 MP4。

    compatibility:
        compatible：
            H.264 Baseline + Level 4.0 + YUV420P + AAC-LC
            优先兼容老旧数码设备。

        standard：
            H.264 High + Level 4.1 + YUV420P + AAC-LC
            兼顾画质、压缩效率和现代设备兼容性。
    """
    input_path = check_file(input_path)

    output_dir = Path(output_dir) if output_dir else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = safe_output_path(
        output_dir / f"{input_path.stem}_converted.mp4"
    )

    preset = MP4_COMPATIBILITY_PRESETS.get(
        compatibility,
        MP4_COMPATIBILITY_PRESETS["standard"],
    )

    bitrate = get_original_bitrate(input_path)
    duration = get_duration_seconds(input_path)

    args = [
        "-i", str(input_path),
        "-c:v", "libx264",
        "-profile:v", preset["profile"],
        "-level:v", preset["level"],
        "-pix_fmt", preset["pix_fmt"],
        "-crf", crf,
        "-maxrate", bitrate,
        "-bufsize", bitrate.replace("k", "") + "k",
        "-c:a", "aac",
        "-profile:a", preset["audio_profile"],
        "-movflags", "+faststart",
        str(output_path),
    ]

    run_ffmpeg(
        args,
        total_duration=duration,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
        label=f"转为MP4 · {input_path.name}",
    )

    return str(output_path)


def convert_to_gif(
    input_path: str,
    fps: int = 10,
    output_dir=None,
    progress_callback: Optional[Callable[[Optional[float]], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
):
    input_path = check_file(input_path)

    output_dir = Path(output_dir) if output_dir else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = safe_output_path(
        output_dir / f"{input_path.stem}.gif"
    )

    duration = get_duration_seconds(input_path)

    run_ffmpeg(
        [
            "-i", str(input_path),
            "-vf", f"fps={fps}",
            str(output_path),
        ],
        total_duration=duration,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
        label=f"转为GIF · {input_path.name}",
    )

    return str(output_path)


def extract_audio(
    input_path: str,
    output_dir=None,
    progress_callback: Optional[Callable[[Optional[float]], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
):
    input_path = check_file(input_path)

    output_dir = Path(output_dir) if output_dir else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = safe_output_path(
        output_dir / f"{input_path.stem}.aac"
    )

    duration = get_duration_seconds(input_path)

    run_ffmpeg(
        [
            "-i", str(input_path),
            "-vn",
            "-c:a", "aac",
            str(output_path),
        ],
        total_duration=duration,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
        label=f"提取音频 · {input_path.name}",
    )

    return str(output_path)


def extract_video(
    input_path: str,
    output_dir=None,
    progress_callback: Optional[Callable[[Optional[float]], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
):
    input_path = check_file(input_path)

    output_dir = Path(output_dir) if output_dir else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = safe_output_path(
        output_dir / f"{input_path.stem}_silent.mp4"
    )

    duration = get_duration_seconds(input_path)

    run_ffmpeg(
        [
            "-i", str(input_path),
            "-an",
            "-c:v", "copy",
            str(output_path),
        ],
        total_duration=duration,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
        label=f"提取画面 · {input_path.name}",
    )

    return str(output_path)