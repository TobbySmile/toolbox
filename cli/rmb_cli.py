# cli/rmb_cli.py

from tools.rmb import convert_rmb

def run():
    print("\n📊 人民币大写转换")

    try:
        amount = float(input("请输入数字："))
        print(f"\n📊 人民币{convert_rmb(amount)}")
    except ValueError as e:
        print(f"❌ {e}")