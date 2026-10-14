# tools/transfer/sender.py

from pathlib import Path

from tools.transfer.receiver import WebShare
from tools.utils.file import check_file


class SenderNode:
    """
    V1 模式：电脑是唯一服务器，不需要主动发 HTTP 请求。

    发送文本/文件本质上只是把数据写进 receiver.py 里的
    WebShare 共享状态，手机端通过 /api/pull 轮询自己读取。
    """

    # ======================================
    # 发送文本
    # ======================================

    @staticmethod
    def send_text(text: str) -> bool:
        if not text.strip():
            raise ValueError("发送内容不能为空")

        WebShare.pc_text = text.strip()
        return True

    # ======================================
    # 发送单个文件
    # ======================================

    @staticmethod
    def send_file(file_path) -> bool:
        file_path = check_file(file_path)

        # 保存真实物理路径的映射，供手机下载时按文件名查找
        WebShare.pc_files_map[file_path.name] = str(file_path.resolve())
        return True

    # ======================================
    # 批量发送多个文件
    # ======================================

    @staticmethod
    def send_files(file_paths: list) -> list[str]:
        """
        一次性分享多个文件到手机端。

        返回: 成功加入分享列表的文件名列表。
        单个文件校验失败不会中断整体流程，会跳过该文件继续处理其余文件，
        调用方可以对比传入数量与返回数量来判断是否有文件被跳过。
        """
        added_names = []
        for path in file_paths:
            try:
                resolved = check_file(path)
                WebShare.pc_files_map[resolved.name] = str(resolved.resolve())
                added_names.append(resolved.name)
            except Exception:
                # 单个文件失效（比如被移动/删除）不应影响其余文件的分享
                continue
        return added_names
