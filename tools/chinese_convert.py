# tools/chinese_convert.py

import opencc

def to_traditional(text: str) -> str:
    # 简体转繁体
    converter = opencc.OpenCC('s2t')
    return converter.convert(text)

def to_simplified(text: str) -> str:
    # 繁体转简体
    converter = opencc.OpenCC('t2s')
    return converter.convert(text)