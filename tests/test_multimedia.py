# tests/test_multimedia.py

import pytest
from pathlib import Path
from tools.multimedia.video import get_original_bitrate
from tools.utils.file import check_file

def test_check_file_raises_error_if_not_exists():
    """测试底层文件校验工具：文件不存在时应该抛出异常"""
    fake_path = Path("this_file_does_not_exist.mp4")
    
    with pytest.raises(FileNotFoundError):
        check_file(fake_path)

def test_get_original_bitrate_fallback():
    """测试容错机制：当传入一个不是视频的空文件时，是否能安全返回默认值"""
    # pytest 自带的 tmp_path fixture，用来生成临时文件，用完自动清理
    fake_video = Path("fake.mp4")
    fake_video.touch() # 创建一个 0 字节的空文件
    
    try:
        # 当 ffprobe 去读一个空文件时会解析失败，但我们期望函数不崩溃并返回默认值
        bitrate = get_original_bitrate(fake_video)
        assert bitrate == "2000k"
    finally:
        fake_video.unlink()