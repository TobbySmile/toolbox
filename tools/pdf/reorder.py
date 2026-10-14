# tools/pdf/reorder.py

import fitz
from pathlib import Path

def multi_move_pages(pdf_path: Path | str, output_path: Path | str, move_rules: list[tuple[int, int]]) -> Path:
    """
    [纯函数] 精确多点移动页码
    :param move_rules: 移动规则列表，元素为 (原始页码_0基, 目标位置_0基)
    """
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)

    doc = fitz.open(pdf_path)
    try:
        total_pages = doc.page_count
        
        # 1. 生成初始页码序列
        pages = list(range(total_pages))
        
        # 2. 遍历规则，抽出所有需要移动的页码
        items_to_insert = []
        for src, tgt in move_rules:
            if not (0 <= src < total_pages):
                raise ValueError(f"源页码 {src + 1} 超出范围！文档共 {total_pages} 页。")
            
            # 记录：(要插入的具体页, 目标位置)
            items_to_insert.append((src, tgt))
            # 从原序列中移除该页（防呆设计：如果已移除则跳过）
            if src in pages:
                pages.remove(src)
        
        # 3. 按照规则设定的目标位置，逐个精准插入
        for src, tgt in items_to_insert:
            # 防止目标位置越界
            safe_tgt = max(0, min(tgt, len(pages)))
            pages.insert(safe_tgt, src)
            
        # 4. 让 PyMuPDF 按新列表瞬间重组 PDF
        doc.select(pages)
        doc.save(output_path)
    finally:
        doc.close()

    return output_path