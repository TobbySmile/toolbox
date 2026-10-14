# cli/downloader_cli.py

import re
from pathlib import Path
from tools.multimedia.downloader import parse_video_info, download_video, COOKIE_DIR
from cli.utils import get_output_dir, Menu


def _cli_progress_hook(d: dict):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    
    if d['status'] == 'downloading':
        p_str = ansi_escape.sub('', d.get('_percent_str', '')).replace('%', '').strip()
        speed = ansi_escape.sub('', d.get('_speed_str', '未知')).strip()
        eta = ansi_escape.sub('', d.get('_eta_str', '未知')).strip()
        
        print(f"\r⏳ 下载进度: {p_str}% | 速度: {speed} | 剩余时间: {eta}      ", end="", flush=True)
        
    elif d['status'] == 'finished':
        print("\n✅ 分片下载完成，正在合并音视频或处理缓存，请稍候...")


def handle_download():
    url = input("\n🔗 请输入视频链接: ").strip()
    if not url:
        return

    print("\n⏳ 正在抓取解析视频信息，请稍候...")
    try:
        title, formats = parse_video_info(url)
    except Exception as e:
        print(f"❌ 解析失败: {e}")
        return

    print(f"\n🎬 视频标题: {title}")
    print("-" * 40)
    for i, fmt in enumerate(formats):
        print(f"[{i + 1}] {fmt.display_name}")
    print("-" * 40)

    try:
        choice = int(input(f"请选择清晰度 (1-{len(formats)}): ").strip())
        selected_fmt = formats[choice - 1]
    except (ValueError, IndexError):
        print("❌ 无效选择，操作取消。")
        return

    use_aria2_input = input("\n🚀 是否启用 aria2c 多线程加速下载？(y/N): ").strip().lower()
    use_aria2 = use_aria2_input == 'y'
    threads = 4
    
    if use_aria2:
        t_input = input("请输入线程数 [默认4]: ").strip()
        if t_input.isdigit():
            threads = int(t_input)

    dummy_path = Path.cwd() / "Downloads" / "dummy.mp4"
    out_dir = get_output_dir(dummy_path)

    print("\n📥 任务准备就绪，开始下载...")
    try:
        final_file_path = download_video(
            video_format=selected_fmt,
            save_dir=out_dir,
            title=title,
            use_aria2=use_aria2,
            threads=threads,
            progress_hook=_cli_progress_hook
        )
        print(f"\n🎉 恭喜，下载完成！")
        print(f"📁 视频文件: {final_file_path.resolve()}")
    except Exception as e:
        print(f"\n❌ 下载过程中出错: {e}")


def handle_show_cookie_dir():
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n🍪 Cookie 存放目录：")
    print(f"📂 {COOKIE_DIR.resolve()}")
    txt_files = list(COOKIE_DIR.glob("*.txt"))
    if txt_files:
        print("\n✅ 当前已识别到以下凭证文件：")
        for f in txt_files:
            print(f"   - {f.name}")
    else:
        print("\n⚠️ 当前目录为空。")
        print("👉 请将导出的 B站 或其他网站的 cookies.txt 文件放置于此目录下。")
    input("\n[ 按回车键返回菜单... ]")


def run():
    menu = Menu("🌐 视频下载引擎 (yt-dlp)")
    menu.add("1", "下载网络视频", handle_download)
    menu.add("2", "查看/初始化 Cookie 凭证目录", handle_show_cookie_dir)
    menu.loop()