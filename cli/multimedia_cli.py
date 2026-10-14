# cli/multimedia_cli.py

from pathlib import Path
from tools.multimedia.video import (
    convert_to_mp4, convert_to_gif, extract_audio, extract_video
)
from tools.multimedia.merge import (
    merge_video_audio, replace_audio, concat_videos
)
from cli.utils import get_output_dir, Menu


def handle_convert_mp4():
    file = input("视频路径: ").strip()
    out_dir = get_output_dir(file)
    print(f"✅ 完成: {convert_to_mp4(file, output_dir=out_dir)}")

def handle_convert_gif():
    file = input("视频路径: ").strip()
    out_dir = get_output_dir(file)
    print(f"✅ 完成: {convert_to_gif(file, output_dir=out_dir)}")

def handle_extract_audio():
    file = input("视频路径: ").strip()
    print("默认输出 AAC 音频")
    out_dir = get_output_dir(file)
    print(f"✅ 完成: {extract_audio(file, output_dir=out_dir)}")

def handle_extract_video():
    file = input("视频路径: ").strip()
    out_dir = get_output_dir(file)
    print(f"✅ 完成: {extract_video(file, output_dir=out_dir)}")

def handle_merge():
    video = input("视频: ").strip()
    audio = input("音频: ").strip()
    out_dir = get_output_dir(video)
    default_out = Path(out_dir) / f"{Path(video).stem}_merged.mp4"
    print(f"✅ 完成: {merge_video_audio(video, audio, default_out)}")

def handle_replace_audio():
    a = input("视频A (取画面): ").strip()
    b = input("音频/视频B (取声音): ").strip()
    out_dir = get_output_dir(a)
    default_out = Path(out_dir) / f"{Path(a).stem}_replaced.mp4"
    print(f"✅ 完成: {replace_audio(a, b, default_out)}")

def handle_concat():
    files = input("视频路径(逗号分隔): ").strip()
    paths = [x.strip() for x in files.split(",") if x.strip()]
    if not paths:
        raise ValueError("未输入任何有效路径")
        
    out_dir = get_output_dir(paths[0])
    default_out = Path(out_dir) / "concat_output.mp4"
    print(f"✅ 完成: {concat_videos(paths, default_out)}")


def run():
    # 彻底告别 while True 和 if/elif，通过 Menu 引擎组装
    menu = Menu("🎬 多媒体工具")
    
    menu.add("1", "视频转MP4", handle_convert_mp4)
    menu.add("2", "视频转GIF", handle_convert_gif)
    menu.add("3", "提取视频音频(AAC)", handle_extract_audio)
    menu.add("4", "提取视频画面", handle_extract_video)
    
    menu.add("5", "视频+音频合并", handle_merge)
    menu.add("6", "视频A画面+B声音", handle_replace_audio)
    menu.add("7", "视频拼接", handle_concat)
    
    menu.loop()