"""货盘助手 —— 本地启动器

双击 exe（或 python launcher.py）即：
  1. 在 127.0.0.1:8000 启动 FastAPI（uvicorn）
  2. 自动打开浏览器访问前端
  3. 数据写入程序目录下的 data/huopan.db（本机 SQLite）
"""
import sys
import time
import threading
import webbrowser

from app.main import app
from app.config import SERVER_HOST, SERVER_PORT


def _open_browser():
    # 等服务器起来再开浏览器
    time.sleep(2.5)
    try:
        webbrowser.open(f"http://{SERVER_HOST}:{SERVER_PORT}/")
    except Exception:
        pass


def _show_error(msg: str):
    try:
        import tkinter as tk
        import tkinter.messagebox as mb
        root = tk.Tk()
        root.withdraw()
        mb.showerror("货盘助手", msg)
    except Exception:
        print(msg)


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    try:
        import uvicorn
        uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="info")
    except OSError as e:
        # 端口被占用等
        _show_error(f"无法启动服务（端口 {SERVER_PORT} 可能已被占用）：\n{e}")
        time.sleep(6)
    except Exception as e:  # noqa: BLE001
        _show_error(f"启动失败：\n{e}")
        time.sleep(6)
