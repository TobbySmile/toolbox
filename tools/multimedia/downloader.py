# tools/multimedia/downloader.py

import re
import requests
from pathlib import Path
from http import cookiejar
from urllib.parse import unquote
from dataclasses import dataclass
from typing import Any, Callable, Optional

import yt_dlp

from tools.utils.filename import clean_filename
from tools.utils.paths import get_cookies_dir
from tools.utils.ffmpeg import resolve_ffmpeg_bin_dir


COOKIE_DIR = get_cookies_dir()

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.7727.56 Safari/537.36"
)

DOMAIN_MAPPING = {
    "bilibili.com": ("www.bilibili.com_cookies.txt", "https://www.bilibili.com/"),
    "youtube.com": ("www.youtube.com_cookies.txt", ""),
    "youtu.be": ("www.youtube.com_cookies.txt", ""),
    "douyin.com": ("www.douyin.com_cookies.txt", "https://www.douyin.com/"),
    "xiaohongshu.com": ("www.xiaohongshu.com_cookies.txt", "https://www.xiaohongshu.com/"),
    "xhslink.com": ("www.xiaohongshu.com_cookies.txt", "https://www.xiaohongshu.com/"),
    "twitter.com": ("twitter.com_cookies.txt", "https://twitter.com/"),
    "x.com": ("twitter.com_cookies.txt", "https://x.com/"),
    "t.me": ("t.me_cookies.txt", "https://t.me/"),
}


@dataclass
class VideoFormat:
    display_name: str
    url: str
    height: int
    ydl_opts: dict[str, Any]


class DownloadCancelled(Exception):
    """用户主动取消下载。"""

    pass


# ============================================================
# 通用 Cookie / yt-dlp
# ============================================================

def _get_cookie_info(video_url: str) -> tuple[Optional[Path], str]:
    for domain, (filename, referer) in DOMAIN_MAPPING.items():
        if domain in video_url:
            return COOKIE_DIR / filename, referer
    return None, ""


def _build_ydl_opts(
    referer: str = "",
    cookie_path: Optional[Path] = None,
    skip_download: bool = True,
) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "skip_download": skip_download,
        "quiet": True,
        "noplaylist": True,
        "ignoreerrors": False,
        "js_runtimes": {"node": {}},
        "remote_components": {"ejs:github"},
        "http_headers": {"User-Agent": UA},
    }

    if referer:
        opts["http_headers"]["Referer"] = referer

    if cookie_path and cookie_path.exists():
        opts["cookiefile"] = str(cookie_path)

    bin_dir = resolve_ffmpeg_bin_dir()
    if bin_dir:
        opts["ffmpeg_location"] = bin_dir

    return opts


def _extract_generic(
    video_url: str,
    referer: str = "",
    cookie_path: Optional[Path] = None,
) -> dict[str, Any]:
    with yt_dlp.YoutubeDL(_build_ydl_opts(referer, cookie_path)) as ydl:
        return ydl.extract_info(video_url, download=False)


# ============================================================
# 视频格式
# ============================================================

def _codec_tag(vcodec: str) -> str:
    vcodec = vcodec.lower()

    if "hev1" in vcodec or "h265" in vcodec:
        return "【高压缩】"
    if "av01" in vcodec:
        return "【新技术/高画质】"
    if "vp9" in vcodec:
        return "【高性价比】"
    if "avc1" in vcodec or "h264" in vcodec:
        return "【兼容性最好】"
    return "【其他格式】"


def _build_formats(
    info: dict[str, Any],
    video_url: str,
    referer: str,
    cookie_path: Optional[Path],
) -> tuple[str, list[VideoFormat]]:
    bundles: list[VideoFormat] = []
    bin_dir = resolve_ffmpeg_bin_dir()

    for f in info.get("formats", []):
        if not f.get("height") or f.get("vcodec") == "none":
            continue

        vcodec = f.get("vcodec", "").lower()
        tag = _codec_tag(vcodec)
        size = f.get("filesize") or f.get("filesize_approx")
        size_str = f"{size / (1024 * 1024):.1f}MB" if size else "未知大小"
        short_codec = vcodec.split(".", 1)[0] if "." in vcodec else vcodec
        fmt_id = f["format_id"]
        final_fmt = f"{fmt_id}+bestaudio[ext=m4a]/best" if "兼容性" in tag else f"{fmt_id}+bestaudio/best"
        display = f"{tag} {f['height']}P - {f.get('ext')} [{short_codec}] ({size_str})"

        opts: dict[str, Any] = {
            "format": final_fmt,
            "http_headers": {"User-Agent": UA, "Referer": referer},
            "js_runtimes": {"node": {}},
            "remote_components": {"ejs:github"},
        }

        if cookie_path and cookie_path.exists():
            opts["cookiefile"] = str(cookie_path)

        if bin_dir:
            opts["ffmpeg_location"] = bin_dir

        bundles.append(VideoFormat(display, video_url, f["height"], opts))

    bundles.sort(key=lambda x: x.height, reverse=True)
    return info.get("title", "未知标题"), bundles


# ============================================================
# 通用站点
# ============================================================

def _handle_generic(video_url: str) -> tuple[str, list[VideoFormat]]:
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)

    cookie_path, referer = _get_cookie_info(video_url)
    cookie_exists = bool(cookie_path and cookie_path.exists())
    errors: list[str] = []

    # 1. 有 Cookie：优先使用登录态
    if cookie_exists:
        try:
            info = _extract_generic(video_url, referer, cookie_path)

            if not info:
                raise RuntimeError("Cookie 解析未返回视频信息")

            title, formats = _build_formats(info, video_url, referer, cookie_path)
            if formats:
                return title, formats

            raise RuntimeError("Cookie 解析成功，但未找到可用视频格式")

        except Exception as ex:
            errors.append(f"Cookie 解析失败: {ex}")

    # 2. 无 Cookie / Cookie 失败：匿名解析
    try:
        info = _extract_generic(video_url, referer)

        if not info:
            raise RuntimeError("匿名解析未返回视频信息")

        title, formats = _build_formats(info, video_url, referer, None)
        if formats:
            return title, formats

        raise RuntimeError("匿名解析成功，但未找到可用视频格式")

    except Exception as ex:
        errors.append(f"匿名解析失败: {ex}")

    # 3. 两种方式都失败
    if cookie_exists:
        raise RuntimeError(
            "使用本地 Cookie 和匿名方式都无法解析该视频。\n"
            "Cookie 可能已过期，或当前视频存在登录 / 会员 / 访问限制。\n\n"
            + "\n".join(errors)
        )

    raise RuntimeError(
        "无法匿名解析该视频。\n"
        "如果该视频需要登录、会员权限或存在反爬限制，"
        "请在「设置 → Cookie 导入」中导入对应网站的 Cookie 后重试。\n\n"
        + "\n".join(errors)
    )


# ============================================================
# 91porn
# ============================================================

def _request_91porn(
    video_url: str,
    cookie_file: Optional[Path] = None,
) -> str:
    session = requests.Session()

    if cookie_file and cookie_file.exists():
        cj = cookiejar.MozillaCookieJar(str(cookie_file))
        cj.load(ignore_discard=True, ignore_expires=True)
        session.cookies = cj

    response = session.get(
        video_url,
        headers={
            "User-Agent": UA,
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.91porn.com/",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.text


def _parse_91porn_html(
    html: str,
) -> tuple[str, list[VideoFormat]]:
    match = re.search(r'strencode2\("(.+?)"\)', html)

    if not match:
        raise RuntimeError("无法提取视频数据，请检查 Cookie 或页面是否有效")

    decoded = unquote(match.group(1))
    url_match = re.search(r"src='(.+?)'", decoded)

    if not url_match:
        raise RuntimeError("直链解析失败")

    title = "91视频"
    title_match = re.search(
        r'<h4 class="login_register_header".*?>(.*?)</h4>',
        html,
        re.S,
    )

    if title_match:
        title = re.sub(r"\s+", "_", re.sub(r"<.*?>", "", title_match.group(1).strip())).strip("_ ")

    bin_dir = resolve_ffmpeg_bin_dir()
    opts: dict[str, Any] = {
        "format": "best",
        "http_headers": {"User-Agent": UA, "Referer": "https://www.91porn.com/"},
    }

    if bin_dir:
        opts["ffmpeg_location"] = bin_dir

    return title, [
        VideoFormat(
            display_name="【原画】直接下载 [H.264]",
            url=url_match.group(1),
            height=1080,
            ydl_opts=opts,
        )
    ]


def _handle_91porn(video_url: str) -> tuple[str, list[VideoFormat]]:
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)

    cookie_file = COOKIE_DIR / "www.91porn.com_cookies.txt"
    cookie_exists = cookie_file.exists()
    errors: list[str] = []

    # 1. 有 Cookie：优先登录态
    if cookie_exists:
        try:
            html = _request_91porn(video_url, cookie_file)
            title, formats = _parse_91porn_html(html)

            if formats:
                return title, formats

            raise RuntimeError("Cookie 解析成功，但未找到视频格式")

        except Exception as ex:
            errors.append(f"Cookie 解析失败: {ex}")

    # 2. 无 Cookie / Cookie 失败：匿名
    try:
        html = _request_91porn(video_url)
        title, formats = _parse_91porn_html(html)

        if formats:
            return title, formats

        raise RuntimeError("匿名解析成功，但未找到视频格式")

    except Exception as ex:
        errors.append(f"匿名解析失败: {ex}")

    # 3. 两种方式都失败
    if cookie_exists:
        raise RuntimeError(
            "使用 Cookie 和匿名方式都无法解析该视频。\n"
            "Cookie 可能已过期，或当前视频不可访问。\n\n"
            + "\n".join(errors)
        )

    raise RuntimeError(
        "无法解析该视频。\n"
        "如果当前视频需要登录或存在访问限制，"
        "请在「设置 → Cookie 导入」中导入 Cookie 后重试。\n\n"
        + "\n".join(errors)
    )


# ============================================================
# 对外解析接口
# ============================================================

def parse_video_info(video_url: str) -> tuple[str, list[VideoFormat]]:
    """
    解析视频链接，返回清理后的标题和可用格式列表。

    有 Cookie：
        优先使用 Cookie。

    Cookie 失败：
        自动降级匿名解析。
    """
    title, formats = (
        _handle_91porn(video_url)
        if "91porn.com" in video_url
        else _handle_generic(video_url)
    )

    if not formats:
        raise ValueError("未找到可用的视频格式")

    return clean_filename(title), formats


# ============================================================
# 下载
# ============================================================

def download_video(
    video_format: VideoFormat,
    save_dir: Path | str,
    title: str,
    use_aria2: bool = False,
    threads: int = 4,
    progress_hook: Optional[Callable[[dict], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Path:
    """
    执行视频下载。

    progress_hook：
        只负责汇报下载进度。

    cancel_check：
        只负责判断是否取消。

    返回：
        实际生成的视频文件路径。
    """
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = video_format.ydl_opts.copy()
    ydl_opts.update({
        "outtmpl": str(save_dir / f"{title}.%(ext)s"),
        "noplaylist": True,
        "merge_output_format": "mp4",
        "retries": 20,
        "fragment_retries": 20,
        "socket_timeout": 30,
    })

    def _combined_hook(data: dict):
        if cancel_check and cancel_check():
            raise DownloadCancelled("用户手动取消了下载")
        if progress_hook:
            progress_hook(data)

    if progress_hook or cancel_check:
        ydl_opts["progress_hooks"] = [_combined_hook]

    if use_aria2:
        ydl_opts["external_downloader"] = "aria2c"
        ydl_opts["external_downloader_args"] = {
            "aria2c": [
                "-x", str(threads), "-s", str(threads), "-k", "1M",
                "--check-certificate=false", "--file-allocation=none",
            ]
        }

    files_before = set(save_dir.iterdir())

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_format.url])

    except DownloadCancelled:
        raise

    except yt_dlp.utils.DownloadError as ex:
        if cancel_check and cancel_check():
            raise DownloadCancelled("用户手动取消了下载") from ex
        raise

    files_after = set(save_dir.iterdir())
    new_files = files_after - files_before

    # 优先返回这次下载产生的新文件
    if new_files:
        media_files = [
            f for f in new_files
            if f.is_file() and f.suffix.lower() not in {".part", ".ytdl"}
        ]
        if media_files:
            return max(media_files, key=lambda f: f.stat().st_mtime)

    # 下载目录中寻找标题匹配的最终文件
    matched_files = [
        f for f in save_dir.iterdir()
        if f.is_file() and f.stem.startswith(title) and f.suffix.lower() not in {".part", ".ytdl"}
    ]

    if matched_files:
        return max(matched_files, key=lambda f: f.stat().st_mtime)

    raise FileNotFoundError(f"下载完成，但未找到生成的视频文件：{save_dir}")