# tests/test_downloader.py

import pytest
from tools.utils.filename import clean_filename
from tools.multimedia.downloader import VideoFormat

def test_clean_filename():
    """测试非法字符清洗是否有效"""
    assert clean_filename("【B站】我的视频: 真的很棒|测试") == "【B站】我的视频_ 真的很棒_测试"
    assert clean_filename('文件"名"<测试>?') == "文件_名__测试__"
    assert clean_filename("正常名字") == "正常名字"

def test_video_format_dataclass():
    """测试 Dataclass 实例化是否正确"""
    fmt = VideoFormat(
        display_name="【测试】1080P",
        url="http://test.com/video",
        height=1080,
        ydl_opts={"format": "best"}
    )
    assert fmt.height == 1080
    assert fmt.ydl_opts["format"] == "best"