# tools/password.py

import secrets
import string

# 可用的字符集
digits = string.digits          # 0-9
lowercase = string.ascii_lowercase  # a-z
uppercase = string.ascii_uppercase  # A-Z
special = string.punctuation    # 特殊字符

def generate_password(length, use_digits, use_lower, use_upper, use_special):
    if length < 1:
        raise ValueError("密码长度至少为1")

    # 构建字符集
    char_set = ""
    if use_digits:
        char_set += digits
    if use_lower:
        char_set += lowercase
    if use_upper:
        char_set += uppercase
    if use_special:
        char_set += special

    if not char_set:
        raise ValueError("至少选择一种字符类型")

    # 生成密码
    password = ''.join(secrets.choice(char_set) for _ in range(length))
    return password