# cli/image_cli.py

from pathlib import Path
from tools.image.converter import convert_image, batch_convert
from cli.utils import get_output_dir

def run():
    print("\n🖼️ 图片转换器")

    try:
        input_path = input("请输入要转换的图片路径/文件夹: ").strip()
        output_format = input("请输入目标格式 (如 jpg, png, webp): ").strip()
        
        # 统一使用交互层函数询问输出路径
        out_dir = get_output_dir(input_path)

        path = Path(input_path)
        if path.is_file():
            # 传递 output_dir
            output_file = convert_image(input_path, output_format, output_dir=out_dir)
            print(f"✅ 转换成功: {output_file}")
            
        elif path.is_dir():
            # 传递 output_dir
            results = batch_convert(input_path, output_format, output_dir=out_dir)
            
            # 修复解包 Bug：results 实际上是成功转换的路径列表
            if not results:
                print("⚠️ 文件夹内没有找到支持转换的图片")
            else:
                for result in results:
                    print(f"✅ 转换成功: {result}")
        else:
            print("❌ 路径不存在，请检查后重试！")

    except Exception as e:
        print(f"❌ 程序错误: {type(e).__name__} - {e}")