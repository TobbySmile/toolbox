# tools/multimedia/merge.py

from pathlib import Path
from enum import Enum
from typing import Callable, Optional

from tools.utils.file import check_file, safe_output_path
from tools.utils.ffmpeg import run_ffmpeg, get_duration_seconds


class DurationMode(str, Enum):
    SHORTEST = "shortest"  # 最短时长
    LONGEST = "longest"    # 最长时长
    VIDEO = "video"        # 以画面长度为准
    AUDIO = "audio"        # 以音频长度为准


def _estimate_merge_duration(video_path: Path, audio_path: Path, duration_mode: str) -> Optional[float]:
    """根据合并模式估算输出时长，用来给进度条计算百分比"""
    v_dur = get_duration_seconds(video_path)
    a_dur = get_duration_seconds(audio_path)

    if duration_mode == DurationMode.VIDEO:
        return v_dur
    if duration_mode == DurationMode.AUDIO:
        return a_dur
    if duration_mode == DurationMode.SHORTEST:
        if v_dur and a_dur:
            return min(v_dur, a_dur)
        return v_dur or a_dur
    if duration_mode == DurationMode.LONGEST:
        if v_dur and a_dur:
            return max(v_dur, a_dur)
        return v_dur or a_dur
    return None


def merge_video_audio(
    video_path: str,
    audio_path: str,
    output_path: str,
    duration_mode: str = "shortest",
    progress_callback: Optional[Callable[[Optional[float]], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
):
    """
    无声合并：将无声视频（或忽略原声）与新音频组合。
    需要处理画面延长/滤镜时，才开启重编码。
    """
    video_path = check_file(video_path)
    audio_path = check_file(audio_path)
    output_path = safe_output_path(output_path)

    args = [
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v:0",
        "-map", "1:a:0",
    ]

    if duration_mode == DurationMode.SHORTEST:
        args.extend(["-c:v", "copy", "-c:a", "aac", "-shortest"])
    elif duration_mode == DurationMode.VIDEO:
        args.extend(["-c:v", "copy", "-c:a", "aac", "-af", "apad", "-shortest"])
    elif duration_mode == DurationMode.AUDIO:
        args.extend([
            "-vf", "tpad=stop_mode=clone:stop_duration=-1",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-shortest"
        ])
    elif duration_mode == DurationMode.LONGEST:
        args.extend(["-c:v", "copy", "-c:a", "aac", "-af", "apad"])
    else:
        raise ValueError(f"未知时长模式: {duration_mode}")

    args.append(str(output_path))

    total_duration = _estimate_merge_duration(video_path, audio_path, duration_mode)

    run_ffmpeg(
        args,
        total_duration=total_duration,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
        label=f"音视频合并 · {video_path.name}",
    )
    return str(output_path)


def replace_audio(
    video_path: str,
    audio_path: str,
    output_path: str,
    duration_mode: str = "shortest",
    progress_callback: Optional[Callable[[Optional[float]], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
):
    """
    替换原声：丢弃原视频音频，换上新音频。
    """
    return merge_video_audio(
        video_path, audio_path, output_path,
        duration_mode=duration_mode,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )


def concat_videos(
    video_paths: list[str],
    output_path: str,
    progress_callback: Optional[Callable[[Optional[float]], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
):
    """
    使用复杂滤镜解决不同分辨率、不同帧率视频拼接后花屏/卡顿的问题，
    统一缩放填充至 1920x1080, 30fps。
    """
    videos = [check_file(path) for path in video_paths]
    output_path = safe_output_path(output_path)

    args = []
    for v in videos:
        args.extend(["-i", str(v)])

    filter_complex = ""
    for i in range(len(videos)):
        filter_complex += f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}]; "

    for i in range(len(videos)):
        filter_complex += f"[v{i}][{i}:a]"
    filter_complex += f"concat=n={len(videos)}:v=1:a=1[v][a]"

    args.extend([
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-c:a", "aac",
        str(output_path)
    ])

    total_duration = 0.0
    for v in videos:
        d = get_duration_seconds(v)
        if d is None:
            total_duration = None
            break
        total_duration += d

    run_ffmpeg(
        args,
        total_duration=total_duration,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
        label=f"视频拼接 · {len(videos)}个文件",
    )
    return str(output_path)
