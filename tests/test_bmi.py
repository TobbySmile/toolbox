# tests/test_bmi.py

import pytest
from tools.bmi import calculate_bmi, get_bmi_status

def test_normal():
    # 测试正常体重
    # 175cm 70kg，BMI应该是22.9，状态应该是"正常"
    assert calculate_bmi(175, 70) == 22.9
    assert get_bmi_status(22.9) == "正常"

def test_thin():
    # 测试偏瘦
    # 175cm 50kg，BMI应该是16.3，状态应该是"偏瘦"
    assert calculate_bmi(175, 50) == 16.3
    assert get_bmi_status(16.3) == "偏瘦"

def test_overweight():
    # 测试偏胖
    # 175cm 85kg，BMI应该是27.8，状态应该是"偏胖"
    assert calculate_bmi(175, 85) == 27.8
    assert get_bmi_status(27.8) == "偏胖"

def test_obese():
    # 测试肥胖
    # 175cm 100kg，BMI应该是32.7，状态应该是"肥胖"
    assert calculate_bmi(175, 100) == 32.7
    assert get_bmi_status(32.7) == "肥胖"

def test_boundary_thin_to_normal():
    # 18.4应该是偏瘦
    assert get_bmi_status(18.4) == "偏瘦"
    # 18.5应该是正常
    assert get_bmi_status(18.5) == "正常"

def test_boundary_normal_to_overweight():
    # 23.9应该是正常
    assert get_bmi_status(23.9) == "正常"
    # 24.0应该是偏胖
    assert get_bmi_status(24.0) == "偏胖"

def test_boundary_overweight_to_obese():
    # 27.9应该是偏胖
    assert get_bmi_status(27.9) == "偏胖"
    # 28.0应该是肥胖
    assert get_bmi_status(28.0) == "肥胖"

def test_zero_height():
    with pytest.raises(ZeroDivisionError):
        calculate_bmi(0, 70)