# tools/wallpaper.py

from pathlib import Path
from typing import Callable, Optional
import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


REGIONS = {
    "zh-CN": "中国",
    "en-US": "美国",
    "ja-JP": "日本",
    "en-AU": "澳大利亚",
    "en-GB": "英国",
    "de-DE": "德国",
    "fr-FR": "法国",
    "it-IT": "意大利"
}


MAX_FILENAME_LENGTH = 150


class WallpaperCancelled(Exception):
    """用户主动取消了壁纸下载任务"""
    pass


def create_session():
    """创建带重试机制的 requests Session"""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def clean_filename(filename: str) -> str:
    """清理 Windows 非法文件名字符，保留扩展名"""
    filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
    path = Path(filename)
    name = path.stem
    ext = path.suffix
    name = name[:MAX_FILENAME_LENGTH]
    return name + ext


def download_wallpapers(
    region_count: int,
    day_count: int,
    save_dir: Path,
    on_log: Optional[Callable[[str], None]] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
):
    """
    下载 Bing 壁纸

    参数:
        region_count: 下载地区数量
        day_count: 每个地区下载天数
        save_dir: 保存目录 (Path对象)
        on_log: 日志回调
        on_progress: 进度回调 (current, total)
        cancel_check: callable() -> bool，每处理完一张图检测一次，
            返回 True 时立即中止剩余任务，抛出 WallpaperCancelled
    """
    save_dir = Path(save_dir)
    session = create_session()

    target_regions = list(REGIONS.keys())[:region_count]
    downloaded_ids = set()

    total_tasks = region_count * day_count
    current_task = 0

    def log(message):
        if on_log:
            on_log(message)

    def progress(current, total):
        if on_progress:
            on_progress(current, total)

    def check_cancel():
        if cancel_check and cancel_check():
            raise WallpaperCancelled("用户手动取消了壁纸下载")

    log(f"🚀 开始任务：{region_count}个地区，{day_count}天壁纸")

    save_dir.mkdir(parents=True, exist_ok=True)

    for mkt in target_regions:
        check_cancel()

        region_name = REGIONS[mkt]
        log(f"🌍 正在获取 [{region_name}] 壁纸信息...")

        api_url = (
            "https://www.bing.com/"
            "HPImageArchive.aspx?"
            f"format=js&idx=0&n={day_count}&mkt={mkt}"
        )

        try:
            response = session.get(api_url, timeout=10)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            log(f"❌ 获取 [{region_name}] 失败: {e}")
            current_task += day_count
            progress(current_task, total_tasks)
            continue

        for img in data.get("images", []):
            check_cancel()

            current_task += 1
            img_url = img["url"]

            match = re.search(r"id=OHR\.(.+?)_", img_url)
            img_id = match.group(1) if match else img_url

            if img_id in downloaded_ids:
                log(f"⏭️ 重复跳过: {img_id}")
                progress(current_task, total_tasks)
                continue

            url_path = "https://www.bing.com" + img_url
            filename = f"{img['startdate']}_{img['copyright']}.jpg"
            filename = clean_filename(filename)
            file_path = save_dir / filename

            try:
                img_response = session.get(url_path, timeout=15)
                img_response.raise_for_status()
                with file_path.open("wb") as f:
                    f.write(img_response.content)
                downloaded_ids.add(img_id)
                log(f"✅ 下载成功: {filename}")
            except Exception as e:
                log(f"❌ 下载失败: {filename} | {e}")

            progress(current_task, total_tasks)

    log("🎉 全部任务完成！")
