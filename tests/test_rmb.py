# tests/test_rmb.py

import pytest
from tools.rmb import convert_rmb

def test_convert_rmb():
    # 测试整数部分
    assert convert_rmb(123456789) == "壹亿贰仟叁佰肆拾伍万陆仟柒佰捌拾玖元整"
    assert convert_rmb(1001) == "壹仟零壹元整"
    assert convert_rmb(1000000) == "壹佰万元整"

    # 测试小数部分
    assert convert_rmb(123.45) == "壹佰贰拾叁元肆角伍分"
    assert convert_rmb(0.99) == "零元玖角玖分"
    assert convert_rmb(0.01) == "零元零壹分"

    # 测试零
    with pytest.raises(ValueError):
        convert_rmb(0)

    # 测试负数
    with pytest.raises(ValueError):
        convert_rmb(-123.45)

    # 测试1000亿
    with pytest.raises(ValueError):
        convert_rmb(100000000000)