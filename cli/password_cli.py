# cli/password_cli.py

from tools.password import generate_password

def run():
    print("\n🔐 密码生成器")

    try:
        count = int(input("请输入要生成的密码数量："))
        length = input("密码长度 [16]：").strip()
        length = int(length) if length else 16
        use_digits = input("是否使用数字？(y/n): ").strip().lower() == 'y'
        use_lower = input("是否使用小写字母？(y/n): ").strip().lower() == 'y'
        use_upper = input("是否使用大写字母？(y/n): ").strip().lower() == 'y'
        use_special = input("是否使用特殊字符？(y/n): ").strip().lower() == 'y'

        for i, _ in enumerate(range(count), 1):
            password = generate_password(length, use_digits, use_lower, use_upper, use_special)
            print(f"{i}. {password}")
    except ValueError as e:
        print(f"❌ {e}")