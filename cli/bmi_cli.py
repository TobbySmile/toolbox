# cli/bmi_cli.py

from tools.bmi import calculate_bmi, get_bmi_status

def run():
    print("\n📊 BMI计算器")

    try:
        height_cm = float(input("请输入身高（cm）："))
    except ValueError:
        print("❌ 请输入有效数字")
        return

    try:
        weight_kg = float(input("请输入体重（kg）："))
    except ValueError:
        print("❌ 请输入有效数字")
        return

    bmi = calculate_bmi(height_cm, weight_kg)
    status = get_bmi_status(bmi)

    print(f"\n📊 你的BMI：{bmi} | {status}")