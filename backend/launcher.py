# -*- coding: utf-8 -*-
"""货盘助手 · 桌面端启动器（安装版 / 应用窗口版）

双击「货盘助手.exe」后：
  1. 确定可用端口（若 8000 已被别的程序占用，自动改用 8001~8010）
  2. 后台启动本地服务（默认绑定 0.0.0.0，同一局域网的同事也能访问）
  3. 直接弹出**应用窗口**，界面就在窗口里（不再打开系统浏览器）
  4. 关闭窗口 = 收进托盘继续后台运行（同事不断线）；托盘菜单可复制同事地址、完全退出
  5. 若端口上已经是货盘助手（/api/health 返回 app=huopan），直接复用，退出时不停掉它
  6. 若本机 WebView2 不可用，自动回退为「控制窗口 + 浏览器」模式

数据（数据库、上传原件、日志）放在用户可写目录，位置由 app.config 决定：
  安装版默认 %LOCALAPPDATA%\\货盘助手\\data（可在安装向导里改）。
"""
import os
import socket
import sys
import threading
import time
import webbrowser

from app.config import DATA_DIR, LOG_FILE, SERVER_PORT

# 桌面端默认绑定全网段（0.0.0.0），这样同一局域网的同事也能访问；
# 如在 .env 里显式写了 SERVER_HOST 则以 .env 为准。
BIND_HOST = os.getenv("SERVER_HOST", "0.0.0.0")

APP_TITLE = "货盘助手"
# 8000 被别的程序占用时依次尝试的备用端口
PORT_CANDIDATES = [SERVER_PORT] + [p for p in range(8001, 8011)]

_own_server = False   # 是否是本进程启动的服务
_window = None        # pywebview 窗口
_tray = None          # 托盘图标
_active_port = SERVER_PORT   # 实际使用的端口，启动时确定


def _port():
    return _active_port


def _local_url():
    return f"http://127.0.0.1:{_active_port}"


def _lan_url():
    return f"http://{_lan_ip()}:{_active_port}"


# ---------------- 工具函数 ----------------
def _data_dir():
    """数据目录（安装版在用户目录，绿色版在程序旁）——由 app.config 统一决定。"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except OSError:
        pass
    return DATA_DIR


def _res(name):
    """打包后资源在 _MEIPASS，源码运行取本目录"""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(base, name)
    return p if os.path.exists(p) else None


def _port_free(port):
    s = socket.socket()
    s.settimeout(0.5)
    try:
        return s.connect_ex(("127.0.0.1", port)) != 0
    finally:
        s.close()


def _is_huopan(port, timeout=0.8):
    """端口上跑的是不是货盘助手（避免 8000 被别的程序占用时连错服务）。"""
    try:
        import json
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=timeout) as r:
            data = json.loads(r.read() or b"{}")
        return data.get("app") == "huopan"
    except Exception:
        return False


def _lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _log(msg):
    """日志写数据目录（安装版的程序目录只读，写不进去）。"""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg + "\n")
    except OSError:
        pass


def _ensure_streams():
    """windowed 打包后 sys.stdout/stderr 为 None，有些库会因此报错，兜一个空流。"""
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            try:
                setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
            except OSError:
                pass


def _log_config():
    """uvicorn 日志写数据目录（windowed 下不能用默认配置：没有 stderr）。"""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
        "handlers": {"file": {"class": "logging.FileHandler", "filename": LOG_FILE,
                              "encoding": "utf-8", "formatter": "plain"}},
        "loggers": {
            "uvicorn": {"handlers": ["file"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["file"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["file"], "level": "INFO", "propagate": False},
        },
    }


def _copy_text(text):
    """不依赖第三方库写系统剪贴板（供托盘菜单用）。"""
    try:
        import ctypes
        CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        if not u32.OpenClipboard(None):
            return False
        try:
            u32.EmptyClipboard()
            buf = ctypes.create_unicode_buffer(text)
            size = ctypes.sizeof(buf)
            h = k32.GlobalAlloc(GMEM_MOVEABLE, size)
            p = k32.GlobalLock(h)
            ctypes.memmove(p, buf, size)
            k32.GlobalUnlock(h)
            u32.SetClipboardData(CF_UNICODETEXT, h)
            return True
        finally:
            u32.CloseClipboard()
    except Exception as e:  # noqa: BLE001
        _log(f"写剪贴板失败：{e}")
        return False


def _serve():
    """后台线程：跑 uvicorn"""
    global _own_server
    _ensure_streams()
    try:
        import logging
        import uvicorn
        from app.main import app
        _own_server = True
        logging.basicConfig(level=logging.INFO)   # 兜底，避免第三方库 basicConfig 报错
        uvicorn.run(app, host=BIND_HOST, port=_active_port,
                    log_config=_log_config(), log_level="info")
    except Exception as e:  # noqa: BLE001
        _log(f"服务启动失败：{e}")


def _write_lan_hint():
    """在数据目录写一份同事访问地址，方便直接发群（找不到托盘时的兜底）。"""
    try:
        txt = (f"货盘助手 · 同事访问地址\n"
               f"========================\n\n"
               f"把下面这个地址发给同事，对方用浏览器打开即可（不用装任何东西）：\n\n"
               f"    {_lan_url()}\n\n"
               f"登录账号：huopan / huopan123\n\n"
               f"（本文件每次启动会自动更新。本机自己用：{_local_url()}）\n")
        with open(os.path.join(_data_dir(), "同事访问地址.txt"), "w", encoding="utf-8-sig") as f:
            f.write(txt)
    except OSError:
        pass


def _choose_port():
    """确定实际使用端口。

    返回 "reuse"（端口上已是货盘助手，直接复用）/ "own"（本进程来启动服务）；
    没有可用端口时返回 None。
    """
    global _active_port
    if _is_huopan(SERVER_PORT):
        _active_port = SERVER_PORT
        _log(f"端口 {SERVER_PORT} 上已有货盘助手在运行，直接复用（本次退出不会停止它）")
        return "reuse"

    if _port_free(SERVER_PORT):
        _active_port = SERVER_PORT
        return "own"

    _log(f"端口 {SERVER_PORT} 被其他程序占用，尝试备用端口")
    for p in PORT_CANDIDATES[1:]:
        if _is_huopan(p):
            _active_port = p
            _log(f"备用端口 {p} 上已有货盘助手，直接复用")
            return "reuse"
        if _port_free(p):
            _active_port = p
            _log(f"已改用备用端口 {p}")
            return "own"

    _log("8000~8010 均不可用，无法启动服务")
    return None


def _fatal(title, msg):
    """致命错误：弹框告知用户（比静默退出好排查）。"""
    _log(f"{title}：{msg}")
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, title, 0x10)
    except Exception:
        pass


# ---------------- 退出 ----------------
def _shutdown(exit_code=0):
    try:
        if _tray is not None:
            _tray.stop()
    except Exception:
        pass
    try:
        if _window is not None:
            _window.destroy()
    except Exception:
        pass
    os._exit(exit_code)


def _notify(title, msg):
    if _tray is not None:
        try:
            _tray.notify(msg, title)
        except Exception:
            pass


def _show_window():
    """托盘菜单「打开界面」：有窗口就还原，没有（回退模式）就开浏览器。"""
    if _window is None:
        webbrowser.open(_local_url())
        return
    try:
        _window.show()
    except Exception:
        pass
    try:
        _window.restore()
    except Exception:
        pass


# ---------------- 托盘 ----------------
def _tray_image():
    from PIL import Image
    p = _res("app_icon.ico")
    if p:
        try:
            return Image.open(p)
        except Exception:
            pass
    return Image.new("RGBA", (64, 64), (124, 58, 237, 255))


def _start_tray():
    """启动托盘图标；失败只记日志，不影响主流程。"""
    global _tray
    try:
        import pystray
    except Exception as e:  # noqa: BLE001
        _log(f"托盘不可用（缺少 pystray）：{e}")
        return False

    def on_show(icon, item):
        _show_window()

    def on_copy(icon, item):
        addr = _lan_url()
        if _copy_text(addr):
            _notify("已复制同事访问地址", addr + "\n粘贴发到群里即可。")

    def on_folder(icon, item):
        try:
            os.startfile(_data_dir())
        except Exception:
            pass

    def on_quit(icon, item):
        _shutdown(0)

    try:
        menu = pystray.Menu(
            pystray.MenuItem("打开界面", on_show, default=True),
            pystray.MenuItem("复制同事访问地址", on_copy),
            pystray.MenuItem("打开数据文件夹", on_folder),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("停止服务并退出", on_quit),
        )
        _tray = pystray.Icon("huopan", _tray_image(), APP_TITLE, menu)
        threading.Thread(target=_tray.run, daemon=True).start()
        return True
    except Exception as e:  # noqa: BLE001
        _log(f"托盘启动失败：{e}")
        _tray = None
        return False


# ---------------- 应用窗口 ----------------
def _set_window_icon():
    ico = _res("app_icon.ico")
    if not ico or _window is None:
        return
    try:
        from System.Drawing import Icon as DotNetIcon   # noqa: N813 (pythonnet)
        native = _window.native
        if hasattr(native, "Icon"):
            native.Icon = DotNetIcon(ico)
    except Exception:
        pass


def _menu_copy_lan():
    addr = _lan_url()
    if _copy_text(addr):
        _notify("已复制同事访问地址", addr + "\n粘贴发到群里即可。")


def _menu_open_folder():
    try:
        os.startfile(_data_dir())
    except Exception:
        pass


def _menu_reload():
    try:
        if _window is not None:
            _window.evaluate_js("location.reload()")
    except Exception:
        pass


def _build_menu():
    """窗口顶部原生菜单（内容区保持纯界面，协作信息收在这里）。"""
    from webview.menu import Menu, MenuAction, MenuSeparator
    return [
        Menu("工具", [
            MenuAction("复制同事访问地址", _menu_copy_lan),
            MenuAction("打开数据文件夹", _menu_open_folder),
            MenuSeparator(),
            MenuAction("刷新界面", _menu_reload),
            MenuSeparator(),
            MenuAction("停止服务并退出", lambda: _shutdown(0)),
        ]),
    ]


def _run_app_window():
    """打开应用窗口（阻塞直到窗口全部关闭）。异常会抛给上层回退。"""
    global _window
    import webview

    try:
        menu = _build_menu()
    except Exception:  # noqa: BLE001
        menu = []

    _window = webview.create_window(
        APP_TITLE,
        _local_url(),
        width=1320, height=860,
        min_size=(900, 600),
        text_select=True,
        menu=menu,
    )

    def on_loaded():
        _set_window_icon()

    def on_closing():
        """关窗口 = 收进托盘继续跑（同事不断线）；没有托盘就真退出。"""
        if _tray is not None and _window is not None:
            try:
                _window.hide()
                _notify(APP_TITLE,
                        "程序仍在后台运行，同事可以继续访问。\n"
                        "要完全退出请右键托盘图标 →「停止服务并退出」。")
                return False
            except Exception:
                pass
        return True

    _window.events.loaded += on_loaded
    _window.events.closing += on_closing

    storage = os.path.join(_data_dir(), "webview")
    try:
        os.makedirs(storage, exist_ok=True)
    except OSError:
        storage = None

    start_kwargs = {"private_mode": False, "storage_path": storage, "debug": False}
    ico = _res("app_icon.ico")
    if ico:
        start_kwargs["icon"] = ico
    webview.start(**start_kwargs)
    # 走到这里说明窗口已关闭且没有托盘接管 → 正常退出
    _shutdown(0)


# ---------------- 回退模式（无 WebView2）：控制窗口 + 浏览器 ----------------
def _fallback_panel(already_running, ready, reason=""):
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("480x300")
    root.minsize(480, 300)
    root.configure(bg="#ffffff")
    ico = _res("app_icon.ico")
    if ico:
        try:
            root.iconbitmap(ico)
        except Exception:
            pass

    FS = ("Microsoft YaHei UI", 9)
    FB = ("Microsoft YaHei UI", 10, "bold")

    head = tk.Frame(root, bg="#7c3aed", height=52)
    head.pack(fill="x")
    head.pack_propagate(False)
    tk.Label(head, text="  货盘助手", bg="#7c3aed", fg="white",
             font=("Microsoft YaHei UI", 14, "bold")).pack(side="left", padx=6)
    status = tk.Label(head, text="● 服务运行中" if ready else "● 启动失败",
                      bg="#7c3aed", fg="white" if ready else "#fecaca", font=FS)
    status.pack(side="right", padx=12)

    body = tk.Frame(root, bg="#ffffff")
    body.pack(fill="both", expand=True, padx=18, pady=14)
    lan_url = _lan_url()

    def row(label, url, btn_text, cmd):
        f = tk.Frame(body, bg="#ffffff")
        f.pack(fill="x", pady=5)
        tk.Label(f, text=label, bg="#ffffff", fg="#606266", font=FS, width=10,
                 anchor="w").pack(side="left")
        tk.Label(f, text=url, bg="#ffffff", fg="#7c3aed", font=FB, anchor="w").pack(side="left")
        tk.Button(f, text=btn_text, font=FS, bg="#f3e8ff", fg="#6d28d9", relief="flat",
                  activebackground="#e9d5ff", cursor="hand2", command=cmd).pack(side="right")

    def copy_lan():
        root.clipboard_clear()
        root.clipboard_append(lan_url)
        root.update()
        status.config(text="● 地址已复制")

    row("本机访问", _local_url(), "打开", lambda: webbrowser.open(_local_url()))
    row("同事访问", lan_url, "复制", copy_lan)

    tk.Label(body, text="（本机未找到 WebView2，已回退为浏览器模式）" if reason else "",
             bg="#ffffff", fg="#e6a23c", font=FS, anchor="w").pack(fill="x", pady=(8, 0))
    tk.Label(body, text="提示：本窗口关掉会停止服务（同事将无法访问）；电脑睡眠时同事也会连不上。",
             bg="#fafafa", fg="#606266", font=FS, anchor="w", justify="left",
             wraplength=420, padx=10, pady=8).pack(fill="x", pady=(10, 0))

    foot = tk.Frame(root, bg="#ffffff")
    foot.pack(fill="x", padx=18, pady=(0, 14))

    def quit_app():
        if _own_server and not messagebox.askyesno(APP_TITLE, "停止服务并退出？\n退出后同事将无法访问。"):
            return
        root.destroy()
        os._exit(0)

    tk.Button(foot, text="打开界面", font=FB, bg="#7c3aed", fg="white", relief="flat", width=12,
              activebackground="#6d28d9", activeforeground="white", cursor="hand2",
              command=lambda: webbrowser.open(_local_url())).pack(side="left")
    tk.Button(foot, text="停止服务并退出", font=FS, bg="#fef2f2", fg="#dc2626", relief="flat",
              width=14, activebackground="#fee2e2", cursor="hand2",
              command=quit_app).pack(side="right")

    root.protocol("WM_DELETE_WINDOW", quit_app)
    root.after(800, lambda: webbrowser.open(_local_url()))
    root.mainloop()


# ---------------- 主流程 ----------------
def main():
    _ensure_streams()
    _log(f"启动：程序目录={os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))} 数据目录={DATA_DIR}")

    # 数据目录必须可写，否则直接告诉用户原因（安装版的头号坑）
    if not os.access(DATA_DIR, os.W_OK):
        _fatal(APP_TITLE, f"数据目录不可写：\n{DATA_DIR}\n\n"
                          f"请检查该目录权限，或删除文件\n"
                          f"{os.path.join(os.getenv('LOCALAPPDATA', ''), '货盘助手', 'data_dir.txt')}\n"
                          f"后重新运行。")
        return

    mode = _choose_port()
    if mode is None:
        _fatal(APP_TITLE, "端口 8000~8010 都被占用，无法启动服务。\n"
                          "请关闭占用端口的程序后重试，或在数据目录的 .env 里指定 SERVER_PORT。")
        return

    already = mode == "reuse"
    if not already:
        threading.Thread(target=_serve, daemon=True).start()
        for _ in range(120):        # 等就绪，最多 30 秒
            if not _port_free(_active_port):
                break
            time.sleep(0.25)
        ready = not _port_free(_active_port)
        if not ready:
            _log("服务 30 秒内未就绪：可能端口被占用或启动失败")
    else:
        ready = True

    _write_lan_hint()
    _start_tray()

    try:
        _run_app_window()
    except Exception as e:  # noqa: BLE001
        _log(f"应用窗口启动失败，回退浏览器模式：{e}")
        _fallback_panel(already, ready, reason=str(e))


if __name__ == "__main__":
    main()
