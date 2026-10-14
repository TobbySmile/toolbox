# ui/flet_ui/views/utility_view.py

import asyncio
import json
from pathlib import Path

import flet as ft

# 导入你的纯函数
from tools.password import generate_password
from tools.bmi import calculate_bmi, get_bmi_status
from tools.rmb import convert_rmb
from tools.chinese_convert import to_traditional, to_simplified
from tools.symbols import SYMBOLS
from tools.tree import write_tree


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.json"


def _load_default_max_depth():
    try:
        data = json.loads(
            SETTINGS_PATH.read_text(encoding="utf-8")
        )
        return data.get("tree", {}).get("default_max_depth")
    except Exception:
        return None


def create_view(page: ft.Page) -> ft.Control:
    clipboard = ft.Clipboard()
    page.services.append(clipboard)

    async def copy_text(text):
        await clipboard.set(text)
        show_snack(f"已复制: {text}")

    def handle_copy(text):
        page.run_task(copy_text, text)

    def show_snack(
        msg,
        color=ft.Colors.GREEN_500,
    ):
        page.overlay.append(
            ft.SnackBar(
                ft.Text(msg),
                open=True,
                bgcolor=color,
            )
        )
        page.update()

    # =====================================================
    # Tab 1: 转换与计算 (BMI, RMB, 繁简)
    # =====================================================
    bmi_h = ft.TextField(
        label="身高(cm)",
        dense=True,
        expand=1,
    )

    bmi_w = ft.TextField(
        label="体重(kg)",
        dense=True,
        expand=1,
    )

    bmi_res = ft.Text(
        "结果将显示于此",
        color=ft.Colors.BLUE,
    )

    def calc_bmi(e):
        try:
            val = calculate_bmi(
                float(bmi_h.value),
                float(bmi_w.value),
            )
            status = get_bmi_status(val)

            bmi_res.value = f"👉 BMI: {val} ({status})"
            bmi_res.color = (
                ft.Colors.RED
                if status == "肥胖"
                else ft.Colors.GREEN
            )

        except Exception:
            bmi_res.value = "❌ 输入无效"
            bmi_res.color = ft.Colors.RED

        page.update()

    rmb_in = ft.TextField(
        label="输入金额 (如 1234.56)",
        dense=True,
        expand=True,
    )

    rmb_out = ft.TextField(
        label="大写结果",
        read_only=True,
        expand=True,
        dense=True,
    )

    def calc_rmb(e):
        try:
            rmb_out.value = convert_rmb(
                float(rmb_in.value)
            )
        except Exception:
            show_snack(
                "❌ 输入金额无效",
                ft.Colors.RED,
            )

        page.update()

    zh_in = ft.TextField(
        label="输入中文文本",
        multiline=True,
        min_lines=2,
        expand=True,
    )

    zh_out = ft.TextField(
        label="转换结果",
        read_only=True,
        multiline=True,
        min_lines=2,
        expand=True,
    )

    def calc_zh(mode):
        if not zh_in.value:
            return

        zh_out.value = (
            to_traditional(zh_in.value)
            if mode == "t"
            else to_simplified(zh_in.value)
        )

        page.update()

    calc_content = ft.Container(
        padding=20,
        content=ft.Column([
            ft.Text(
                "⚖️ BMI 计算",
                weight=ft.FontWeight.BOLD,
            ),
            ft.Row([
                bmi_h,
                bmi_w,
                ft.ElevatedButton(
                    "计算",
                    on_click=calc_bmi,
                ),
                bmi_res,
            ]),
            ft.Divider(),
            ft.Text(
                "💴 人民币大写转换",
                weight=ft.FontWeight.BOLD,
            ),
            ft.Row([
                rmb_in,
                ft.ElevatedButton(
                    "转换",
                    on_click=calc_rmb,
                ),
            ]),
            ft.Row([
                rmb_out,
                ft.IconButton(
                    ft.Icons.COPY,
                    on_click=lambda e: handle_copy(
                        rmb_out.value
                    ),
                ),
            ]),
            ft.Divider(),
            ft.Text(
                "🔄 繁简转换",
                weight=ft.FontWeight.BOLD,
            ),
            zh_in,
            ft.Row([
                ft.ElevatedButton(
                    "转繁体",
                    on_click=lambda e: calc_zh("t"),
                ),
                ft.ElevatedButton(
                    "转简体",
                    on_click=lambda e: calc_zh("s"),
                ),
            ]),
            ft.Row([
                zh_out,
                ft.IconButton(
                    ft.Icons.COPY,
                    on_click=lambda e: handle_copy(
                        zh_out.value
                    ),
                ),
            ]),
        ], scroll=ft.ScrollMode.AUTO),
    )

    # =====================================================
    # Tab 2: 密码与符号
    # =====================================================
    pwd_len = ft.Slider(
        min=4,
        max=32,
        divisions=28,
        value=16,
        label="{value} 位",
    )

    cb_num = ft.Checkbox(
        "数字 0-9",
        value=True,
    )
    cb_low = ft.Checkbox(
        "小写字母 a-z",
        value=True,
    )
    cb_up = ft.Checkbox(
        "大写字母 A-Z",
        value=True,
    )
    cb_sym = ft.Checkbox(
        "特殊字符",
        value=True,
    )

    pwd_out = ft.TextField(
        read_only=True,
        expand=True,
        dense=True,
    )

    def gen_pwd(e):
        try:
            pwd_out.value = generate_password(
                int(pwd_len.value),
                cb_num.value,
                cb_low.value,
                cb_up.value,
                cb_sym.value,
            )
        except Exception as ex:
            show_snack(
                str(ex),
                ft.Colors.RED,
            )

        page.update()

    symbol_sections = []

    for category, chars in SYMBOLS.items():
        chips = [
            ft.Chip(
                label=ft.Text(char, size=18),
                on_click=lambda e, c=char: handle_copy(c),
            )
            for char in chars
        ]

        symbol_sections.append(
            ft.Column([
                ft.Text(
                    f"📌 {category}",
                    color=ft.Colors.BLUE_GREY_500,
                ),
                ft.Row(
                    chips,
                    wrap=True,
                ),
            ])
        )

    symbol_content = ft.Container(
        padding=20,
        content=ft.Column([
            ft.Text(
                "🔐 强密码生成",
                weight=ft.FontWeight.BOLD,
            ),
            pwd_len,
            ft.Row([
                cb_num,
                cb_low,
                cb_up,
                cb_sym,
            ]),
            ft.Row([
                ft.ElevatedButton(
                    "生成密码",
                    on_click=gen_pwd,
                ),
                pwd_out,
                ft.IconButton(
                    ft.Icons.COPY,
                    on_click=lambda e: handle_copy(
                        pwd_out.value
                    ),
                ),
            ]),
            ft.Divider(),
            ft.Text(
                "✨ 常用符号表 (点击即复制)",
                weight=ft.FontWeight.BOLD,
            ),
            *symbol_sections,
        ], scroll=ft.ScrollMode.AUTO),
    )

    # =====================================================
    # Tab 3: 系统与文件
    # =====================================================
    tree_picker = ft.FilePicker()
    page.services.append(tree_picker)

    default_depth = _load_default_max_depth()

    tree_state = {
        "scan_dir": None,
        "out_dir": None,
    }

    tree_scan_txt = ft.Text(
        "未选择",
        color=ft.Colors.GREY_500,
    )

    tree_out_txt = ft.Text(
        "📁 默认输出至此文件夹同级目录",
        color=ft.Colors.GREY_500,
    )

    tree_status = ft.Text("", size=14)

    tree_depth_switch = ft.Switch(
        label="限制扫描深度",
        value=default_depth is not None,
    )

    tree_depth_input = ft.TextField(
        label="最大深度（层）",
        width=160,
        dense=True,
        value=str(default_depth) if default_depth else "2",
        disabled=default_depth is None,
    )

    def on_depth_switch_change(e):
        tree_depth_input.disabled = not tree_depth_switch.value
        page.update()

    tree_depth_switch.on_change = on_depth_switch_change

    async def on_pick_tree_dir(e):
        path = await tree_picker.get_directory_path()

        if path:
            tree_state["scan_dir"] = path
            tree_scan_txt.value = f"📁 {path}"
            page.update()

    async def on_pick_tree_out_dir(e):
        path = await tree_picker.get_directory_path()

        if path:
            tree_state["out_dir"] = path
            tree_out_txt.value = f"📁 输出至: {path}"
            page.update()

    def run_tree(e):
        if not tree_state["scan_dir"]:
            show_snack(
                "请先选择要扫描的目录",
                ft.Colors.RED,
            )
            return

        max_depth = None

        if tree_depth_switch.value:
            try:
                max_depth = int(tree_depth_input.value)

                if max_depth < 1:
                    raise ValueError

            except ValueError:
                show_snack(
                    "❌ 扫描深度必须是大于 0 的整数",
                    ft.Colors.RED,
                )
                return

        tree_status.value = "⏳ 正在扫描生成目录树..."
        tree_status.color = ft.Colors.ORANGE
        page.update()

        async def _task():
            try:
                target_path = Path(
                    tree_state["scan_dir"]
                )

                if tree_state["out_dir"]:
                    out_dir = Path(tree_state["out_dir"])
                else:
                    out_dir = target_path.parent

                out_file = (
                    out_dir
                    / f"{target_path.name}_tree.txt"
                )

                await asyncio.to_thread(
                    write_tree,
                    target_path,
                    out_file,
                    max_depth=max_depth,
                )

                tree_status.value = (
                    f"✅ 生成成功！文件位于:\n{out_file}"
                )
                tree_status.color = ft.Colors.GREEN

            except Exception as ex:
                tree_status.value = f"❌ 失败: {ex}"
                tree_status.color = ft.Colors.RED

            finally:
                page.update()

        page.run_task(_task)

    system_content = ft.Container(
        padding=20,
        content=ft.Column([
            ft.Text(
                "🌳 文件夹目录树生成",
                weight=ft.FontWeight.BOLD,
            ),
            ft.Text(
                "一键扫描选定文件夹，在同级目录生成结构清晰的 txt 文本文件。",
                color=ft.Colors.GREY_500,
            ),
            ft.Divider(),
            ft.Row([
                ft.ElevatedButton(
                    "选择要扫描的文件夹",
                    icon=ft.Icons.FOLDER_OPEN,
                    on_click=lambda e: page.run_task(
                        on_pick_tree_dir,
                        e,
                    ),
                ),
                tree_scan_txt,
            ]),
            ft.Row([
                ft.ElevatedButton(
                    "选择输出文件夹",
                    icon=ft.Icons.FOLDER,
                    on_click=lambda e: page.run_task(
                        on_pick_tree_out_dir,
                        e,
                    ),
                ),
                tree_out_txt,
            ]),
            ft.Container(height=10),
            ft.Row([
                tree_depth_switch,
                tree_depth_input,
            ]),
            ft.Text(
                "默认不限制深度，扫描全部文件；开启后仅展开到指定层数，更深的内容会被折叠标注",
                size=12,
                color=ft.Colors.GREY_500,
            ),
            ft.Container(height=10),
            ft.ElevatedButton(
                "🚀 开始生成",
                icon=ft.Icons.ACCOUNT_TREE,
                on_click=run_tree,
            ),
            tree_status,
        ]),
    )

    return ft.Tabs(
        length=3,
        selected_index=0,
        expand=True,
        content=ft.Column(
            expand=True,
            controls=[
                ft.TabBar(tabs=[
                    ft.Tab(
                        icon=ft.Icons.CALCULATE_OUTLINED,
                        label="转换与计算",
                    ),
                    ft.Tab(
                        icon=ft.Icons.PASSWORD,
                        label="密码与符号",
                    ),
                    ft.Tab(
                        icon=ft.Icons.ACCOUNT_TREE_OUTLINED,
                        label="系统与文件",
                    ),
                ]),
                ft.TabBarView(
                    expand=True,
                    controls=[
                        calc_content,
                        symbol_content,
                        system_content,
                    ],
                ),
            ],
        ),
    )