# tools/image/converter.py

from pathlib import Path
from typing import Callable, Optional
from PIL import Image

from tools.utils.file import (
    check_file,
    safe_output_path
)


SUPPORTED_FORMATS = [
    "png",
    "jpg",
    "jpeg",
    "webp",
    "bmp"
]


def convert_image(
    input_path: str,
    output_format: str,
    output_dir: str | Path = None
) -> str:
    """
    图片格式转换（单文件，速度很快，不提供中断/进度接口；
    批量场景请使用 batch_convert）
    """

    input_path = check_file(input_path)

    output_format = output_format.lower().replace(".", "")

    if output_format not in SUPPORTED_FORMATS:
        raise ValueError(f"不支持格式: {output_format}")

    if output_dir:
        output_dir = Path(output_dir)
    else:
        output_dir = input_path.parent

    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = safe_output_path(
        output_dir / f"{input_path.stem}.{output_format}"
    )

    with Image.open(input_path) as img:
        if output_format in ["jpg", "jpeg"]:
            if img.mode in ("RGBA", "LA"):
                background = Image.new("RGB", img.size, "white")
                background.paste(img, mask=img.getchannel("A"))
                img = background
            else:
                img = img.convert("RGB")

        img.save(output_path)

    return str(output_path)


def batch_convert(
    input_dir,
    output_format,
    output_dir=None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
):
    """
    批量图片转换。

    参数:
        progress_callback: callable(current: int, total: int) -> None，
            每转换完一张图片就回调一次
        cancel_check: callable() -> bool，每转换完一张图检测一次，
            返回 True 时立即停止，抛出 InterruptedError（此时已转换的文件保留）
    """

    input_dir = Path(input_dir)

    if not input_dir.exists():
        raise FileNotFoundError(f"目录不存在: {input_dir}")

    if output_dir:
        output_dir = Path(output_dir)
    else:
        output_dir = input_dir / "converted"

    output_dir.mkdir(parents=True, exist_ok=True)

    candidates = [
        f for f in input_dir.iterdir()
        if f.is_file() and f.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp", ".bmp"]
    ]

    total = len(candidates)
    results = []

    for i, image in enumerate(candidates, start=1):
        if cancel_check and cancel_check():
            raise InterruptedError(f"用户手动取消了批量转换（已完成 {i - 1}/{total} 张）")

        output = convert_image(image, output_format, output_dir)
        results.append(output)

        if progress_callback:
            progress_callback(i, total)

    return results
