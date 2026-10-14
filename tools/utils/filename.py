# tools/utils/filename.py

import re

def clean_filename(filename: str) -> str:
    """
    清理 Windows 等操作系统中的非法文件名字符
    """
    filename = re.sub(
        r'[\\/:\*?"<>|]',
        "_",
        filename
    )
    return filename.strip()