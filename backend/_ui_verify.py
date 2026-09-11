# -*- coding: utf-8 -*-
"""桌面端应用窗口验证：同一次调用内「启动 → 找窗口 → 截图 → 关闭」。

用法：venv311/Scripts/python.exe _ui_verify.py
产出：_ui_shot.png（窗口截图）、_ui_verify_out.log（启动日志）
"""
import ctypes
import ctypes.wintypes as wt
import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8088
PY = os.path.join(HERE, "venv311", "Scripts", "python.exe")
SHOT = os.path.join(HERE, "_ui_shot.png")
LOG = os.path.join(HERE, "_ui_verify_out.log")


def port_open(port, timeout=0.5):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def find_windows(keyword):
    """枚举可见顶层窗口，返回标题含关键字的窗口信息。"""
    user32 = ctypes.windll.user32
    found = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value
        if keyword in title:
            rect = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            found.append({
                "hwnd": hwnd, "title": title, "cls": cls.value,
                "w": rect.right - rect.left, "h": rect.bottom - rect.top,
                "x": rect.left, "y": rect.top,
            })
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    cb_ref = WNDENUMPROC(cb)     # 保持引用，避免回调被回收
    user32.EnumWindows(cb_ref, 0)
    return found


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

    env = os.environ.copy()
    env["SERVER_PORT"] = str(PORT)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    print("== 启动 launcher.py（端口 %d）==" % PORT)
    logf = open(LOG, "w", encoding="utf-8")
    proc = subprocess.Popen([PY, os.path.join(HERE, "launcher.py")],
                            cwd=HERE, env=env, stdout=logf, stderr=subprocess.STDOUT)

    ok_port = False
    for _ in range(60):
        if port_open(PORT):
            ok_port = True
            break
        time.sleep(0.5)
    print("端口 %d 就绪: %s" % (PORT, ok_port))

    time.sleep(16)   # 等 WebView2 初始化 + 页面加载

    print("进程存活:", proc.poll() is None)
    wins = find_windows("货盘助手")
    print("找到窗口:", len(wins))
    for w in wins:
        print("   ", w)

    # 截图（优先截窗口区域）
    try:
        from PIL import ImageGrab
        if wins:
            w = max(wins, key=lambda x: x["w"] * x["h"])
            box = (max(w["x"], 0), max(w["y"], 0), max(w["x"], 0) + w["w"], max(w["y"], 0) + w["h"])
            img = ImageGrab.grab(bbox=box)
        else:
            img = ImageGrab.grab()
        if img.width > 1400:
            img = img.resize((img.width // 2, img.height // 2))
        img.save(SHOT)
        print("截图已存:", SHOT, img.size)
    except Exception as e:  # noqa: BLE001
        print("截图失败:", e)

    # ---- 关闭窗口 → 应隐藏到托盘、进程与端口保留 ----
    print("== 测试关闭窗口（应收进托盘，服务继续）==")
    real = [w for w in wins if w["cls"].startswith("WindowsForms")]
    if real:
        big = max(real, key=lambda x: x["w"] * x["h"])
        print("向主窗口发 WM_CLOSE:", big["hwnd"], big["cls"])
        ctypes.windll.user32.PostMessageW(big["hwnd"], 0x0010, 0, 0)   # WM_CLOSE
        time.sleep(5)
        print("进程存活(应 True):", proc.poll() is None)
        print("端口仍监听(应 True):", port_open(PORT))
        vis = [w for w in find_windows("货盘助手") if w["cls"].startswith("WindowsForms")]
        print("WinForms 可见窗口(应 0):", len(vis))
    else:
        print("未找到 WinForms 主窗口，跳过")

    print("== 强制关闭 ==")
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                   capture_output=True)
    logf.close()
    time.sleep(1)
    print("残留监听:", port_open(PORT))
    print("---- 启动日志 ----")
    print(open(LOG, encoding="utf-8", errors="replace").read()[-1500:])


if __name__ == "__main__":
    main()
