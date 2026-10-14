# tools/pdf/split.py

import fitz
from pathlib import Path

def split_pdf(pdf_path: Path | str, output_path: Path | str, pages: list[int]) -> Path:
    """
    [纯函数] 提取指定页码，生成新的 PDF
    :param pages: 基于 0 的页码索引列表，例如 [0, 2, 4] 代表第 1, 3, 5 页
    """
    output_path = Path(output_path)
    result_doc = fitz.open()
    
    try:
        with fitz.open(pdf_path) as doc:
            for p in pages:
                # 确保页码在合法范围内
                if 0 <= p < doc.page_count:
                    result_doc.insert_pdf(doc, from_page=p, to_page=p)
        result_doc.save(output_path)
    finally:
        result_doc.close()
        
    return output_path