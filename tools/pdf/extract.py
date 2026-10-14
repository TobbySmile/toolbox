# tools/pdf/extract.py

import fitz
from pathlib import Path
from typing import Callable, Optional

from tools.utils.file import safe_output_path


def extract_text(pdf_path: Path | str, output_txt_path: Path | str) -> Path:
    """[纯函数] 提取单个 PDF 全文文本并保存为 TXT"""
    pdf_path = Path(pdf_path)
    output_txt_path = Path(output_txt_path)
    text_content = []

    with fitz.open(pdf_path) as doc:
        for page in doc:
            text_content.append(page.get_text())

    output_txt_path.write_text("\n\n".join(text_content), encoding="utf-8")
    return output_txt_path


def extract_text_batch(
    pdf_paths: list[Path | str],
    output_dir: Path | str = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> list[Path]:
    """
    批量提取多个 PDF 的全文文本，逐个生成同名 _text.txt。

    参数:
        pdf_paths: 多个 PDF 路径
        output_dir: 统一输出目录；为 None 时each 文件输出到自己所在目录
        progress_callback: callable(current: int, total: int) -> None
        cancel_check: callable() -> bool，每处理完一个文件检测一次，
            返回 True 时立即停止，抛出 InterruptedError（已完成的文件保留）

    返回: 生成的 txt 文件路径列表
    """
    total = len(pdf_paths)
    results = []

    for i, pdf_path in enumerate(pdf_paths, start=1):
        if cancel_check and cancel_check():
            raise InterruptedError(f"用户手动取消了批量提取（已完成 {i - 1}/{total} 个文件）")

        pdf_path = Path(pdf_path)
        target_dir = Path(output_dir) if output_dir else pdf_path.parent
        target_dir.mkdir(parents=True, exist_ok=True)

        out_path = safe_output_path(target_dir / f"{pdf_path.stem}_text.txt")
        extract_text(pdf_path, out_path)
        results.append(out_path)

        if progress_callback:
            progress_callback(i, total)

    return results
