# tools/utils/cookie.py
#
# 设置页「Cookie 导入」功能的底层实现。
#
# v2 变更：Cookie 存储路径改用 tools.utils.paths.get_cookies_dir()，
# 不再用相对 __file__ 算出来的项目内路径。这直接关系到两件事：
#   1. 打包成单文件 exe 后，Cookie 目录不会因为 PyInstaller 每次重新
#      解压临时目录而丢失（详见 tools/utils/paths.py 的说明）
#   2. 给朋友用的打包版本，不会不小心把开发者自己的 cookies.txt 一起
#      打包进 exe 里——因为 PyInstaller 只会打包"随源码一起提交的文件"，
#      用户数据目录（%APPDATA%\万象阁\cookies\）在朋友的电脑上一开始
#      是空的，必须靠朋友自己在设置页导入，不会用到开发者本人的 Cookie

import shutil
from pathlib import Path

from tools.utils.paths import get_cookies_dir

# 平台 key -> (标准文件名, 中文展示名)
# 标准文件名需要和 tools/multimedia/downloader.py 中的 domain_mapping 完全对应
PLATFORM_INFO: dict[str, tuple[str, str]] = {
    "youtube": ("www.youtube.com_cookies.txt", "YouTube"),
    "bilibili": ("www.bilibili.com_cookies.txt", "B 站"),
    "douyin": ("www.douyin.com_cookies.txt", "抖音"),
    "xiaohongshu": ("www.xiaohongshu.com_cookies.txt", "小红书"),
    "twitter": ("twitter.com_cookies.txt", "X (Twitter)"),
}


def _looks_like_netscape_cookie(sample_text: str) -> bool:
    """粗略校验：Netscape cookie 文件通常以 # Netscape HTTP Cookie File 开头，
    或至少每行是多个 Tab 分隔字段。空文件/明显不是 cookie 的文件会被拒绝。"""
    if not sample_text.strip():
        return False
    if "netscape http cookie file" in sample_text.lower():
        return True
    for line in sample_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if len(line.split("\t")) >= 6:
            return True
    return False


def import_cookie(platform: str, source_path: str | Path) -> Path:
    """
    导入 Cookie 文件到持久化的用户数据目录，自动重命名，覆盖同平台旧文件。

    返回：落地后的目标路径
    """
    if platform not in PLATFORM_INFO:
        raise ValueError(f"不支持的平台: {platform}")

    source_path = Path(source_path)
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError(f"文件不存在: {source_path}")

    try:
        sample = source_path.read_text(encoding="utf-8", errors="ignore")[:4000]
    except Exception as ex:
        raise ValueError(f"无法读取文件: {ex}")

    if not _looks_like_netscape_cookie(sample):
        raise ValueError("这看起来不是有效的 Netscape 格式 cookies.txt，请确认导出方式正确")

    cookie_dir = get_cookies_dir()
    filename, _ = PLATFORM_INFO[platform]
    target_path = cookie_dir / filename

    shutil.copyfile(source_path, target_path)
    return target_path


def get_cookie_status() -> dict[str, bool]:
    """返回各平台 cookie 是否已导入（存在对应文件）"""
    cookie_dir = get_cookies_dir()
    return {
        key: (cookie_dir / filename).exists()
        for key, (filename, _) in PLATFORM_INFO.items()
    }


def remove_cookie(platform: str) -> bool:
    if platform not in PLATFORM_INFO:
        raise ValueError(f"不支持的平台: {platform}")
    filename, _ = PLATFORM_INFO[platform]
    target = get_cookies_dir() / filename
    if target.exists():
        target.unlink()
        return True
    return False
