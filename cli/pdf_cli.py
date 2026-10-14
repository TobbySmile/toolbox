# cli/pdf_cli.py

from pathlib import Path
from cli.utils import get_output_dir, Menu
from tools.utils.file import check_file

from tools.pdf.merge import merge_pdfs
from tools.pdf.split import split_pdf
from tools.pdf.convert import pdf_to_images, images_to_pdf
from tools.pdf.extract import extract_text
from tools.pdf.reorder import multi_move_pages

def _parse_page_ranges(range_str: str) -> list[int]:
    """解析页码输入，支持 1,3,5-7 格式，返回 0 索引的列表"""
    if not range_str.strip() or range_str.strip().lower() == 'all':
        return None
        
    pages = set()
    for part in range_str.split(','):
        part = part.strip()
        if not part: continue
        
        if '-' in part:
            start, end = part.split('-', 1)
            # 将 1-3 转换为 0,1,2
            pages.update(range(int(start) - 1, int(end)))
        else:
            pages.add(int(part) - 1)
            
    return sorted(list(pages))

def handle_merge():
    files_str = input("📄 请输入要合并的 PDF 路径 (用逗号分隔，按顺序): ").strip()
    paths = [check_file(x.strip()) for x in files_str.split(",") if x.strip()]
    if not paths:
        raise ValueError("未输入任何有效路径")
        
    out_dir = get_output_dir(paths[0])
    default_out = out_dir / "merged_output.pdf"
    
    print("\n⏳ 正在合并，请稍候...")
    res = merge_pdfs(paths, default_out)
    print(f"✅ 合并完成: {res}")

def handle_split():
    file = input("📄 原始 PDF 路径: ").strip()
    check_file(file)
    
    pages_str = input("🔢 请输入提取页码 (如: 1,3,5-7): ").strip()
    pages = _parse_page_ranges(pages_str)
    if not pages:
        raise ValueError("无效的页码输入")
        
    out_dir = get_output_dir(file)
    default_out = out_dir / f"{Path(file).stem}_extracted.pdf"
    
    print("\n⏳ 正在提取，请稍候...")
    res = split_pdf(file, default_out, pages)
    print(f"✅ 提取完成: {res}")

def handle_pdf_to_image():
    file = input("📄 PDF 路径: ").strip()
    check_file(file)
    
    pages_str = input("🔢 请输入转换页码 (如 1,3-5，直接回车转换所有页): ").strip()
    pages = _parse_page_ranges(pages_str)
    
    out_dir = get_output_dir(file)
    target_dir = out_dir / f"{Path(file).stem}_images"
    
    print("\n⏳ 正在转换，请稍候...")
    res = pdf_to_images(file, target_dir, pages)
    print(f"✅ 成功提取 {len(res)} 张图片至: {target_dir}")

def handle_image_to_pdf():
    files_str = input("🖼️ 请输入要合并的图片路径 (用逗号分隔): ").strip()
    paths = [check_file(x.strip()) for x in files_str.split(",") if x.strip()]
    if not paths:
        raise ValueError("未输入任何有效路径")
        
    out_dir = get_output_dir(paths[0])
    default_out = out_dir / "images_merged.pdf"
    
    print("\n⏳ 正在生成 PDF，请稍候...")
    res = images_to_pdf(paths, default_out)
    print(f"✅ 生成完成: {res}")

def handle_extract_text():
    file = input("📄 PDF 路径: ").strip()
    check_file(file)
    
    out_dir = get_output_dir(file)
    default_out = out_dir / f"{Path(file).stem}_text.txt"
    
    print("\n⏳ 正在提取文本，请稍候...")
    res = extract_text(file, default_out)
    print(f"✅ 提取完成: {res}")

def _parse_move_rules(rule_str: str) -> list[tuple[int, int]]:
    """解析高级移动规则，支持 8>2 或 50-54>21"""
    rules = []
    # 替换中文逗号防止输入法错误
    for part in rule_str.replace('，', ',').split(','):
        part = part.strip()
        if not part: continue
        
        # 自动识别多种连接符
        separator = None
        for sep in ['->', '>', ':', '：']:
            if sep in part:
                separator = sep
                break
                
        if not separator:
            raise ValueError(f"规则需包含目标位置，如 8>2。解析失败部分: '{part}'")
            
        src_str, tgt_str = part.split(separator, 1)
        tgt = int(tgt_str.strip()) - 1  # 转换目标位置为程序 0 索引
        src_str = src_str.strip()
        
        # 处理连续批量页面，如 50-54>21
        if '-' in src_str:
            s_start, s_end = src_str.split('-', 1)
            for s in range(int(s_start.strip()), int(s_end.strip()) + 1):
                rules.append((s - 1, tgt))
                tgt += 1  # 目标位置自动+1，保证批量页面排在一起
        else:
            # 处理单页，如 8>2
            rules.append((int(src_str) - 1, tgt))
            
    return rules

def handle_reorder_pages():
    file = input("📄 PDF 路径: ").strip()
    check_file(file)
    
    print("\n💡 语法提示: 来源>目标。例如 8>2 表示把第8页移到第2页。")
    print("💡 多条规则用逗号分隔: 8>2, 7>4")
    print("💡 甚至支持批量插入: 50-54>21")
    
    rule_str = input("🔢 请输入移动规则: ").strip()
    
    try:
        rules = _parse_move_rules(rule_str)
    except Exception as e:
        raise ValueError(f"规则解析失败: {e}")
        
    if not rules:
        raise ValueError("未输入有效规则")
        
    out_dir = get_output_dir(file)
    default_out = out_dir / f"{Path(file).stem}_reordered.pdf"
    
    print("\n⏳ 正在重新排版，请稍候...")
    res = multi_move_pages(file, default_out, rules)
    print(f"✅ 排版调整完成: {res}")

def run():
    menu = Menu("📑 PDF 处理工具箱")
    
    menu.add("1", "合并多个 PDF", handle_merge)
    menu.add("2", "提取/拆分 PDF 页码", handle_split)
    menu.add("3", "PDF 转图片", handle_pdf_to_image)
    menu.add("4", "图片转 PDF", handle_image_to_pdf)
    menu.add("5", "提取 PDF 全文文本", handle_extract_text)
    menu.add("6", "调整 PDF 页面顺序", handle_reorder_pages)
    
    menu.loop()