# cli/wallpaper_cli.py

from pathlib import Path
from tools.wallpaper import download_wallpapers



def run():

    print("\n🖼️ 必应壁纸下载器")


    try:

        region_count = int(
            input(
                "请输入地区数量(1-8)[默认3]: "
            )
            or 3
        )


        day_count = int(
            input(
                "请输入天数(1-8)[默认8]: "
            )
            or 8
        )


        default_path = (
            Path.home()
            /
            "Desktop"
            /
            "BingWallpapers"
        )


        save_dir = input(
            f"请输入保存路径[{default_path}]: "
        ).strip()


        if save_dir:

            save_dir = Path(
                save_dir
            )

        else:

            save_dir = default_path



        download_wallpapers(
            region_count,
            day_count,
            save_dir,
            on_log=print
        )


    except ValueError:

        print(
            "❌ 输入必须是数字"
        )


    except Exception as e:

        print(
            f"❌ 程序错误: {e}"
        )