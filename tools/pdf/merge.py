# tools/pdf/merge.py

import fitz
from pathlib import Path

def merge_pdfs(pdf_paths: list[Path | str], output_path: Path | str) -> Path:
    """[纯函数] 合并多个 PDF 文件"""
    output_path = Path(output_path)
    result_doc = fitz.open()
    
    try:
        for pdf in pdf_paths:
            with fitz.open(pdf) as doc:
                result_doc.insert_pdf(doc)
        result_doc.save(output_path)
    finally:
        result_doc.close()
        
    return output_path