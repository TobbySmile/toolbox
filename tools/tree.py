# tools/tree.py

from pathlib import Path


def write_tree(input_path: Path, output_path: Path, max_depth: int | None = None):
    """
    生成目录树文本文件。

    参数:
        max_depth: 最大扫描深度；None 或 0 表示不限制（扫描全部文件/文件夹）。
            深度定义：input_path 本身视为第 0 层，其直接子项为第 1 层，以此类推。
    """

    def generate_tree(path: Path, prefix="", depth=1):

        lines = []

        try:
            contents = sorted(
                [
                    x for x in path.iterdir()
                    if not x.name.startswith(".")
                ],
                key=lambda x: (not x.is_dir(), x.name.lower())
            )

        except PermissionError:
            lines.append(f"{prefix}├── [权限拒绝]")
            return lines

        except OSError as e:
            lines.append(f"{prefix}├── [系统错误: {e}]")
            return lines

        for index, item in enumerate(contents):

            is_last = index == len(contents) - 1
            connector = "└── " if is_last else "├── "
            suffix = "/" if item.is_dir() else ""
            lines.append(f"{prefix}{connector}{item.name}{suffix}")

            if item.is_dir():
                extension = "    " if is_last else "│   "

                # 达到深度上限：不再递归展开，但提示一下这里还有内容被截断
                if max_depth and (depth + 1) > max_depth:
                    try:
                        has_children = any(True for _ in item.iterdir())
                    except OSError:
                        has_children = False
                    if has_children:
                        child_prefix = prefix + extension
                        lines.append(f"{child_prefix}└── ... (已达到扫描深度限制，未展开)")
                    continue

                lines.extend(
                    generate_tree(item, prefix + extension, depth + 1)
                )

        return lines

    depth_note = "全部层级" if not max_depth else f"{max_depth} 层"
    tree_lines = [
        "目录扫描报告",
        f"扫描路径: {input_path}",
        f"扫描深度: {depth_note}",
        "=" * 40,
        "",
        f"{input_path.name}/"
    ]

    tree_lines.extend(
        generate_tree(input_path)
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(tree_lines))
