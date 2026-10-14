# tools/utils/file.py

from pathlib import Path

from tools.utils.filename import clean_filename


def check_file(path: str | Path) -> Path:
    """
    检查文件是否存在

    返回:
        Path对象
    """
    file_path = Path(path).resolve()

    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    return file_path


def safe_output_path(path: str | Path) -> Path:
    """
    防止输出文件覆盖

    自动生成:
    test.jpg
    ↓
    test(1).jpg
    """
    path = Path(path)

    # 清理文件名
    clean_name = clean_filename(path.name)
    path = path.parent / clean_name

    if not path.exists():
        return path

    index = 1

    while True:
        # 修改点：将 f"{path.stem}_{index}{path.suffix}" 改为 f"{path.stem}({index}){path.suffix}"
        new_path = path.parent / f"{path.stem}({index}){path.suffix}"

        if not new_path.exists():
            return new_path

        index += 1