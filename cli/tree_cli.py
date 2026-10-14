# cli/tree_cli.py

from tools.tree import write_tree
from pathlib import Path


def run():
    target_input = input("请输入要扫描的文件夹路径: ").strip()

    input_path = Path(target_input)

    if not input_path.exists() or not input_path.is_dir():
        print(f"❌ 错误: 路径 '{input_path}' 不存在或不是一个文件夹。")
        return


    target_output = input(
        "请输入目录结构树保存文件路径 (直接回车保存到桌面 tree.txt): "
    ).strip()


    if not target_output:
        output_path = Path.home() / "Desktop" / "tree.txt"
    else:
        output_path = Path(target_output)


    print(f"🔍 正在扫描: {input_path}")
    print(f"💾 正在写入: {output_path}")


    write_tree(input_path, output_path)
    print("\n✅ 成功！")
    print(f"📄 文件已保存至: {output_path}")