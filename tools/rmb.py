# tools/rmb.py

def convert_rmb(amount: float) -> str:
    digits = "零壹贰叁肆伍陆柒捌玖"
    units = ["", "拾", "佰", "仟", "万", "拾", "佰", "仟", "亿", "拾", "佰"]
    
    if amount <= 0:
        raise ValueError("金额必须大于0")
    if amount > 10000000000:
        raise ValueError("金额不能超过100亿")

    # 分离整数和小数
    amount_str = f"{amount:.2f}"
    integer_str, decimal_str = amount_str.split(".")
    
    # 处理整数部分
    integer_part = ""
    integer_num = int(integer_str)
    
    if integer_num == 0:
        integer_part = "零"
    else:
        i = 0
        temp = integer_num
        parts = []
        while temp > 0:
            digit = temp % 10
            parts.append(digits[digit] + units[i])
            temp //= 10
            i += 1
        parts.reverse()
        integer_part = "".join(parts)
        
        # 处理连续零
        import re
        integer_part = re.sub(r"零[零拾佰仟]+", "零", integer_part)
        integer_part = re.sub(r"零+$", "", integer_part)
        integer_part = integer_part.replace("零万", "万")
        integer_part = integer_part.replace("零亿", "亿")

    # 处理小数部分
    jiao = int(decimal_str[0])
    fen = int(decimal_str[1])
    
    decimal_part = ""
    if jiao == 0 and fen == 0:
        decimal_part = "整"
    elif jiao == 0:
        decimal_part = f"零{digits[fen]}分"
    elif fen == 0:
        decimal_part = f"{digits[jiao]}角"
    else:
        decimal_part = f"{digits[jiao]}角{digits[fen]}分"

    return f"{integer_part}元{decimal_part}"