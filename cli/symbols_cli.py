# cli/symbols_cli.py

from tools.symbols import SYMBOLS

def run():
    print("\n🔣 符号工具")
    for category, symbols in SYMBOLS.items():
        print(f"\n{category}：")
        print(" ".join(symbols))