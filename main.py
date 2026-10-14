# main.py

import sys

from cli import (
    bmi_cli,
    rmb_cli,
    password_cli,
    chinese_convert_cli,
    symbols_cli,
    tree_cli,
    wallpaper_cli,
    image_cli,
    multimedia_cli,
    downloader_cli,
    pdf_cli,
)


# 工具注册表
TOOLS = {
    "bmi": bmi_cli.run,
    "rmb": rmb_cli.run,
    "password": password_cli.run,
    "convert": chinese_convert_cli.run,
    "symbols": symbols_cli.run,
    "tree": tree_cli.run,
    "wallpaper": wallpaper_cli.run,
    "image": image_cli.run,
    "multimedia": multimedia_cli.run,
    "downloader": downloader_cli.run,
    "pdf": pdf_cli.run,
}


def print_help():
    """显示帮助信息"""
    print("\n🧰 Toolbox 工具箱")
    print("\n用法:")
    print("  tb <工具名>")

    print("\n可用工具:")

    for name in TOOLS:
        print(f"  - {name}")

    print("\n示例:")
    print("  tb bmi")
    print("  tb password")


def main():
    """
    Toolbox CLI入口
    """

    # 没有参数
    if len(sys.argv) < 2:
        print_help()
        return


    tool_name = sys.argv[1]


    # 查找工具
    tool = TOOLS.get(tool_name)


    if tool:
        tool()
    else:
        print(f"\n❌ 未知工具: {tool_name}")
        print_help()



if __name__ == "__main__":
    main()