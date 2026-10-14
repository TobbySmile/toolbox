# cli/utils.py

from pathlib import Path
import sys

def get_output_dir(input_file: str | Path) -> Path:
    """获取输出目录 (负责与用户交互)"""
    input_path = Path(input_file)
    default_dir = input_path.parent

    output_dir = input(f"请输入输出文件夹 [{default_dir}]: ").strip()

    if output_dir:
        return Path(output_dir)
    return default_dir


class Menu:
    """
    通用 CLI 菜单引擎
    封装了循环、用户输入校验和异常捕获
    """
    def __init__(self, title: str):
        self.title = title
        self.options = {}
        
    def add(self, key: str, desc: str, action: callable):
        """注册菜单项"""
        self.options[key] = (desc, action)
        
    def _exit_menu(self):
        """退出信号"""
        raise StopIteration()

    def loop(self):
        """启动菜单循环"""
        # 自动在最后追加退出选项
        self.options["0"] = ("返回", self._exit_menu)
        
        while True:
            print(f"\n{self.title}")
            print("-" * 20)
            
            for key, (desc, _) in self.options.items():
                if key == "0":
                    print() # 退出键前空一行
                print(f"{key}. {desc}")
            print("-" * 20)
            
            choice = input("请选择: ").strip()
            
            if choice not in self.options:
                print("❌ 无效选择，请重新输入")
                continue
                
            _, action = self.options[choice]
            
            try:
                action()
            except StopIteration:
                break
            except KeyboardInterrupt:
                print("\n⏹️ 已取消当前操作")
            except Exception as e:
                print(f"\n❌ 失败: {type(e).__name__} - {e}")