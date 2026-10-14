# tools/pdf/convert.py

import fitz
from pathlib import Path

def pdf_to_images(pdf_path: Path | str, output_dir: Path | str, pages: list[int] = None, dpi: int = 300) -> list[Path]:
    """[纯函数] 将 PDF 转为图片"""
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    saved_images = []

    with fitz.open(pdf_path) as doc:
        # 如果 pages 为 None，则转换所有页
        target_pages = pages if pages is not None else list(range(doc.page_count))
        
        for p in target_pages:
            if 0 <= p < doc.page_count:
                page = doc[p]
                pix = page.get_pixmap(dpi=dpi)
                out_file = output_dir / f"{pdf_path.stem}_page_{p+1}.png"
                pix.save(str(out_file))
                saved_images.append(out_file)
                
    return saved_images

def images_to_pdf(image_paths: list[Path | str], output_path: Path | str) -> Path:
    """[纯函数] 将多张图片合成一个 PDF，保持图片原始比例"""
    output_path = Path(output_path)
    doc = fitz.open()

    try:
        for img_path in image_paths:
            # 打开图片文件
            img_doc = fitz.open(img_path)
            # 转换为 PDF 格式字节流
            pdf_bytes = img_doc.convert_to_pdf()
            # 加载为临时 PDF 文档
            pdf_doc = fitz.open("pdf", pdf_bytes)
            # 插入总文档
            doc.insert_pdf(pdf_doc)
            
            img_doc.close()
            pdf_doc.close()
            
        doc.save(output_path)
    finally:
        doc.close()
        
    return output_path