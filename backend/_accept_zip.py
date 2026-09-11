# -*- coding: utf-8 -*-
"""交付验收：解压 zip 到临时目录 → 跑 exe → 检查应用窗口 + 冒烟 → 关闭 → 清理"""
import ctypes
import ctypes.wintypes as wt
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ZIP = os.path.join(os.path.dirname(HERE), "货盘助手-桌面版-v7.14.zip")
PORT = 8089


def find_win(keyword="货盘助手"):
    """枚举可见顶层窗口（只找 WinForms/Tk 这类应用窗口，排除 Ghost 等系统窗口）"""
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
        if keyword in buf.value:
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            if cls.value.startswith("WindowsForms") or cls.value == "TkTopLevel":
                rect = wt.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                found.append({"title": buf.value, "cls": cls.value,
                              "w": rect.right - rect.left, "h": rect.bottom - rect.top})
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    cb_ref = WNDENUMPROC(cb)
    user32.EnumWindows(cb_ref, 0)
    return found


tmp = tempfile.mkdtemp(prefix="huopan_accept_")
print("临时目录:", tmp)
with zipfile.ZipFile(ZIP) as z:
    z.extractall(tmp)
dist = os.path.join(tmp, "货盘助手")
print("解压完成，含:", sorted(os.listdir(dist))[:6])

# 模拟用户场景：全新环境，用非默认端口以便与线上服务共存
with open(os.path.join(dist, ".env"), "w", encoding="utf-8") as f:
    f.write(f"SERVER_PORT={PORT}\n")
# 删掉随包附带的库，验证首次运行能自建（新用户场景）
os.remove(os.path.join(dist, "data", "huopan.db"))
print("已删除随包数据库（验证首次运行自动建库）")


def port_up():
    s = socket.socket()
    s.settimeout(1)
    try:
        return s.connect_ex(("127.0.0.1", PORT)) == 0
    finally:
        s.close()


exe = os.path.join(dist, "货盘助手.exe")
p = subprocess.Popen([exe], cwd=dist)
ok = False
for _ in range(90):
    if port_up():
        ok = True
        break
    time.sleep(0.5)
print("服务就绪:", ok)
if not ok:
    subprocess.run(["taskkill", "/F", "/IM", "货盘助手.exe"], capture_output=True)
    sys.exit(1)

db = os.path.join(dist, "data", "huopan.db")
print("首次运行已建库:", os.path.exists(db))

time.sleep(18)   # 等窗口 + 页面渲染
wins = find_win()
print("应用窗口:", wins)
print("弹的是应用窗口(非浏览器):", bool(wins) and wins[0]["cls"].startswith("WindowsForms"))
print("生成了 同事访问地址.txt:", os.path.exists(os.path.join(dist, "同事访问地址.txt")))
print("WebView2 数据目录已建:", os.path.isdir(os.path.join(dist, "data", "webview")))

r = subprocess.run([sys.executable, os.path.join(HERE, "_smoke_desktop.py"),
                    "http://127.0.0.1:%d" % PORT],
                   capture_output=True, encoding="utf-8", errors="ignore", cwd=HERE)
print(r.stdout)
if (r.stderr or "").strip():
    print("[stderr]", r.stderr[-300:])

subprocess.run(["taskkill", "/F", "/IM", "货盘助手.exe"], capture_output=True)
time.sleep(1.5)
shutil.rmtree(tmp, ignore_errors=True)
print("已关闭并清理临时目录:", not os.path.exists(tmp))
