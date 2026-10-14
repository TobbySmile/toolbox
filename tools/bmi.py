# tools/bmi.py

def calculate_bmi(height_cm, weight_kg):
    height_m = height_cm / 100
    bmi = weight_kg / (height_m * height_m)
    return round(bmi, 1)

def get_bmi_status(bmi):
    if bmi < 18.5:
        status = "偏瘦"
    elif 18.5 <= bmi <= 23.9:
        status = "正常"
    elif 24 <= bmi <= 27.9:
        status = "偏胖"
    elif bmi >= 28:
        status = "肥胖"
    return status