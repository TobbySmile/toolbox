# cli/chinese_convert_cli.py

from tools.chinese_convert import to_simplified, to_traditional

def run():
    print("\n🔄 繁简转换")
    choice = input("请选择转换方向：\n1. 简体 → 繁体\n2. 繁体 → 简体\n请选择 (1/2)：")

    try:
        if choice == "1":
            text = input("请输入要转换的简体中文：")
            print(to_traditional(text))
        elif choice == "2":
            text = input("请输入要转换的繁体中文：")
            print(to_simplified(text))
        else:
            print("无效选择！")
    except Exception as e:
        print(f"转换过程中发生错误：{e}")