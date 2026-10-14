# tools/transfer/receiver.py

import threading
import uvicorn
import aiofiles
import secrets
from queue import Queue
from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pathlib import Path

from tools.network.node import NodeIdentity
from tools.utils.file import safe_output_path
from tools.utils.filename import clean_filename


# ==========================================
# 传输配置
# ==========================================

class TransferConfig:
    """
    闪传配置

    save_dir 保持为可变的类属性（而不是模块级常量），
    这样 transfer_view.py 里的"修改保存目录"按钮
    可以在运行时直接改 TransferConfig.save_dir，
    不需要重启服务或改动 receiver.py。

    默认走 Desktop，和设计文档 & 旧版本保持一致。
    Path.cwd() 不能用作默认值：它等于"启动进程时的工作目录"，
    打包成桌面 exe 后这个目录不可预测，且可能没有写权限。
    """
    save_dir = Path.home() / "Desktop"


# ==========================================
# 共享状态与 Token
# ==========================================

class WebShare:
    token = ""
    # 电脑要发给手机的数据
    pc_text = ""
    pc_files_map = {}  # 结构: {"filename.jpg": "C:/absolute/path/to/file.jpg"}

    @classmethod
    def clear_pc_files(cls):
        """清空当前分享给手机的文件列表（不影响原始文件本身）"""
        cls.pc_files_map.clear()

    @classmethod
    def remove_pc_file(cls, filename: str) -> bool:
        """从分享列表中移除单个文件"""
        if filename in cls.pc_files_map:
            del cls.pc_files_map[filename]
            return True
        return False


# ==========================================
# 手机 -> 电脑 的事件队列
# ==========================================
#
# /text 和 /upload 接口运行在 uvicorn 自己的线程/事件循环里，
# 不受 Flet 管理，这里不直接碰 Flet 控件、不调 page.update()。
# 只把事件塞进线程安全的 Queue，真正的 UI 更新逻辑放在
# transfer_view.py 里，用 page.run_task 起一个异步轮询任务
# 定期检查这个队列并统一调用 page.update()。
event_queue: Queue = Queue()

app = FastAPI()


def verify_token(token: str):
    # secrets.compare_digest 做恒定时间比较，避免时序侧信道
    # （局域网场景风险很低，但零成本可以顺手做）
    if not WebShare.token or not secrets.compare_digest(token, WebShare.token):
        raise HTTPException(status_code=403, detail="无效或过期的 Token")


# ==========================================
# 手机端 H5 网页（AJAX 异步提交）
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>⚡ 万象传送阵 - {hostname}</title>
    <style>
        body {{ font-family: system-ui, sans-serif; padding: 15px; background: #f5f5f7; margin: 0; color: #333; }}
        .header {{ text-align: center; margin-bottom: 20px; }}
        .card {{ background: white; padding: 20px; border-radius: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-bottom: 20px; }}
        h3 {{ margin-top: 0; font-size: 18px; }}
        textarea, input[type="file"] {{ width: 100%; box-sizing: border-box; margin-bottom: 10px; padding: 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 16px; }}
        button {{ width: 100%; padding: 14px; border: none; border-radius: 8px; background: #007aff; color: white; font-size: 16px; font-weight: bold; cursor: pointer; }}
        button:disabled {{ background: #999; }}
        .download-btn {{ background: #34c759; margin-bottom: 10px; display: block; text-align: center; text-decoration: none; padding: 12px; border-radius: 8px; color: white; font-weight: bold; }}
        .text-box-wrap {{ position: relative; }}
        .copy-icon-btn {{
            position: absolute; top: 8px; right: 8px;
            width: auto; padding: 5px 10px;
            font-size: 12px; font-weight: normal;
            border-radius: 6px; background: #8e8e93;
        }}
        .status {{ text-align: center; font-size: 14px; margin-top: 10px; color: #666; }}
    </style>
</head>
<body>
    <div class="header"><h2>⚡ 万象传送阵</h2><p>已连接至: {hostname}</p></div>

    <div class="card">
        <h3>📥 接收自电脑</h3>
        <p style="font-size:14px; color:#666;">最新文本:</p>
        <div class="text-box-wrap">
            <div id="pc-text" style="background:#f2f2f7; padding:12px 60px 12px 12px; border-radius:8px; word-break:break-all; min-height:20px;">暂无内容</div>
            <button class="copy-icon-btn" onclick="copyPcText()">复制</button>
        </div>
        <div id="copyStatus" class="status"></div>
        <p style="font-size:14px; color:#666; margin-top:15px;">电脑分享的文件:</p>
        <div id="pc-files">暂无文件</div>
    </div>

    <div class="card">
        <h3>📝 发送文本到电脑</h3>
        <textarea id="textContent" rows="3" placeholder="输入要发给电脑的内容..."></textarea>
        <button id="textBtn" onclick="sendText()">发送文本</button>
        <div id="textStatus" class="status"></div>
    </div>

    <div class="card">
        <h3>📁 发送文件到电脑</h3>
        <input type="file" id="fileInput" multiple>
        <button id="fileBtn" onclick="sendFile()">上传文件</button>
        <div id="fileStatus" class="status"></div>
    </div>

    <script>
        const TOKEN = new URLSearchParams(window.location.search).get('token');

        function copyPcText() {{
            let text = document.getElementById('pc-text').innerText;
            let statusEl = document.getElementById('copyStatus');
            if (!text || text === '暂无内容') {{
                statusEl.innerText = '暂无内容可复制';
                setTimeout(() => statusEl.innerText = '', 1500);
                return;
            }}
            // 局域网走的是 http（非安全上下文），navigator.clipboard 用不了，
            // 用 textarea + execCommand('copy') 做兼容方案
            let textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();
            try {{
                document.execCommand('copy');
                statusEl.innerText = '✅ 已复制';
            }} catch (e) {{
                statusEl.innerText = '❌ 复制失败，请长按文本手动选择';
            }}
            document.body.removeChild(textarea);
            setTimeout(() => statusEl.innerText = '', 1500);
        }}

        async function poll() {{
            try {{
                let res = await fetch('/api/pull?token=' + TOKEN);
                if(res.status === 403) return;
                let data = await res.json();

                document.getElementById('pc-text').innerText = data.text ? data.text : "暂无内容";

                let fileDiv = document.getElementById('pc-files');
                if(data.files.length > 0) {{
                    fileDiv.innerHTML = "";
                    data.files.forEach(f => {{
                        let a = document.createElement('a');
                        a.href = '/download/' + encodeURIComponent(f) + '?token=' + TOKEN;
                        a.className = 'download-btn';
                        a.innerText = '⬇️ 下载: ' + f;
                        fileDiv.appendChild(a);
                    }});
                }} else {{
                    fileDiv.innerHTML = "暂无文件";
                }}
            }} catch(e) {{}}
        }}
        setInterval(poll, 2000);
        poll();

        async function sendText() {{
            let content = document.getElementById('textContent').value;
            if(!content) return;
            let btn = document.getElementById('textBtn');
            let status = document.getElementById('textStatus');
            btn.disabled = true; status.innerText = "发送中...";

            let fd = new FormData(); fd.append('content', content);
            try {{
                await fetch('/text?token=' + TOKEN, {{method: 'POST', body: fd}});
                status.innerText = "✅ 发送成功";
                document.getElementById('textContent').value = "";
            }} catch(e) {{ status.innerText = "❌ 发送失败"; }}
            btn.disabled = false; setTimeout(() => status.innerText="", 2000);
        }}

        async function sendFile() {{
            let input = document.getElementById('fileInput');
            if(input.files.length === 0) return;
            let btn = document.getElementById('fileBtn');
            let status = document.getElementById('fileStatus');
            btn.disabled = true; status.innerText = "上传中, 请勿关闭页面...";

            let fd = new FormData();
            for(let i=0; i<input.files.length; i++) fd.append('files', input.files[i]);

            try {{
                await fetch('/upload?token=' + TOKEN, {{method: 'POST', body: fd}});
                status.innerText = "✅ 上传成功";
                input.value = "";
            }} catch(e) {{ status.innerText = "❌ 上传失败"; }}
            btn.disabled = false; setTimeout(() => status.innerText="", 3000);
        }}
    </script>
</body>
</html>
"""


@app.get("/")
async def home(token: str = Query(...)):
    verify_token(token)
    return HTMLResponse(content=HTML_TEMPLATE.format(hostname=NodeIdentity.get_hostname()))


@app.get("/api/pull")
async def pull_data(token: str = Query(...)):
    verify_token(token)
    return JSONResponse({"text": WebShare.pc_text, "files": list(WebShare.pc_files_map.keys())})


@app.get("/download/{filename}")
async def download_file(filename: str, token: str = Query(...)):
    verify_token(token)
    real_path = WebShare.pc_files_map.get(filename)
    if real_path and Path(real_path).exists():
        return FileResponse(real_path, filename=filename)
    raise HTTPException(status_code=404, detail="文件不存在")


@app.post("/text")
async def receive_text(content: str = Form(...), token: str = Query(...)):
    verify_token(token)
    content = content.strip()
    if content:
        event_queue.put({"type": "text", "data": content})
    return {"status": "ok"}


@app.post("/upload")
async def receive_files(files: list[UploadFile] = File(...), token: str = Query(...)):
    verify_token(token)
    TransferConfig.save_dir.mkdir(parents=True, exist_ok=True)

    for file in files:
        filename = clean_filename(file.filename)
        # 防覆盖机制
        target = safe_output_path(TransferConfig.save_dir / filename)

        # 异步分块写入
        async with aiofiles.open(target, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                await buffer.write(chunk)

        event_queue.put({"type": "file", "data": str(target)})

    return {"status": "ok"}


class ReceiverNode:
    """本地服务器管理"""

    def __init__(self, port=8000):
        self.port = port
        self.config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="error")
        self.server = uvicorn.Server(self.config)
        self.thread = None

    def start_listening(self) -> str:
        # 启动时生成全新 Token，并清空上一次会话遗留的分享文件列表
        WebShare.token = secrets.token_urlsafe(12)
        WebShare.clear_pc_files()
        WebShare.pc_text = ""

        if not (self.thread and self.thread.is_alive()):
            self.server.should_exit = False
            self.thread = threading.Thread(target=self.server.run, daemon=True)
            self.thread.start()

        return WebShare.token

    def stop_listening(self):
        WebShare.token = ""  # 清除 token 使后续请求失效
        if self.server:
            self.server.should_exit = True
        if self.thread:
            self.thread.join(timeout=3)
