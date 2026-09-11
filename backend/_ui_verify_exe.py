# -*- coding: utf-8 -*-
"""验证打包后的 exe：是否弹出「应用窗口」（而非回退浏览器模式）+ 服务是否可用 + 抓窗口图。

用法：venv311/Scripts/python.exe _ui_verify_exe.py
"""
import ctypes
import ctypes.wintypes as wt
import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist", "货盘助手")
EXE = os.path.join(DIST, "货盘助手.exe")
PORT = 8088
SHOT = os.path.join(HERE, "_ui_shot_exe.png")


def port_open(port, timeout=0.5):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def find_windows(keyword="货盘助手"):
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
            found.append({"hwnd": hwnd, "title": title, "cls": cls.value,
                          "w": rect.right - rect.left, "h": rect.bottom - rect.top,
                          "x": rect.left, "y": rect.top})
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    cb_ref = WNDENUMPROC(cb)
    user32.EnumWindows(cb_ref, 0)
    return found


def capture_window(hwnd, path):
    """PrintWindow 抓指定窗口内容（可抓被遮挡的窗口）。"""
    u32, g32 = ctypes.windll.user32, ctypes.windll.gdi32
    rect = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return "窗口尺寸异常"
    hdc = u32.GetWindowDC(hwnd)
    mdc = g32.CreateCompatibleDC(hdc)
    bmp = g32.CreateCompatibleBitmap(hdc, w, h)
    g32.SelectObject(mdc, bmp)
    u32.PrintWindow(hwnd, mdc, 2)          # PW_RENDERFULLCONTENT

    class BMIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                    ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                    ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                    ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]

    class BMI(ctypes.Structure):
        _fields_ = [("bmiHeader", BMIH), ("bmiColors", wt.DWORD * 3)]

    bi = BMI()
    bi.bmiHeader.biSize = ctypes.sizeof(BMIH)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    g32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)

    from PIL import Image
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    img.save(path)
    g32.DeleteObject(bmp)
    g32.DeleteDC(mdc)
    u32.ReleaseDC(hwnd, hdc)
    return f"已保存 {img.size}"


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

    print("== exe:", EXE, os.path.exists(EXE))
    # 用 8088 测试端口，避免和线上 8000 打架
    with open(os.path.join(DIST, ".env"), "w", encoding="utf-8") as f:
        f.write("SERVER_PORT=%d\n" % PORT)
    log = os.path.join(DIST, "服务日志.log")
    if os.path.exists(log):
        os.remove(log)

    print("== 启动 exe ==")
    proc = subprocess.Popen([EXE], cwd=DIST)

    ok = False
    for _ in range(80):
        if port_open(PORT):
            ok = True
            break
        time.sleep(0.5)
    print("端口 %d 就绪: %s" % (PORT, ok))
    time.sleep(18)      # 等窗口 + WebView2 渲染

    print("进程存活:", proc.poll() is None)
    wins = find_windows()
    for w in wins:
        print("   窗口:", w)
    forms = [w for w in wins if w["cls"].startswith("WindowsForms") or w["cls"] == "TkTopLevel"]
    print("应用窗口存在:", bool(forms), "| pywebview 窗口:",
          any(w["cls"].startswith("WindowsForms") for w in wins))

    if wins:
        big = max(wins, key=lambda x: x["w"] * x["h"])
        try:
            print("抓窗口图:", capture_window(big["hwnd"], SHOT))
        except Exception as e:  # noqa: BLE001
            print("抓图失败:", e)

    print("data/webview 已建:", os.path.isdir(os.path.join(DIST, "data", "webview")))
    print("说话文件 同事访问地址.txt:", os.path.exists(os.path.join(DIST, "同事访问地址.txt")))

    print("== 关闭窗口 ==")
    if forms:
        ctypes.windll.user32.PostMessageW(forms[0]["hwnd"], 0x0010, 0, 0)
        time.sleep(5)
        print("进程存活(应 True):", proc.poll() is None)
        print("端口仍监听(应 True):", port_open(PORT))

    print("== 强制关闭 ==")
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    time.sleep(1)
    print("残留监听:", port_open(PORT))

    if os.path.exists(log):
        print("---- 服务日志.log（尾部）----")
        print(open(log, encoding="utf-8", errors="replace").read()[-1200:])


if __name__ == "__main__":
    main()
