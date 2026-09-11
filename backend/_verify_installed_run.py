# -*- coding: utf-8 -*-
"""验证「已安装」的货盘助手（C:\\Program Files\\货盘助手）真实运行行为。

三个场景：
  A. 正常启动：自建服务 + 数据落在用户目录（不在 Program Files）+ 接口冒烟 + 窗口截图
  B. 端口被「别的程序」占用：能识别出来并自动改用备用端口
  C. 数据目录不可写：自动回退到用户目录，程序不崩

用法：venv311/Scripts/python.exe _verify_installed_run.py
"""
import ctypes
import ctypes.wintypes as wt
import http.server
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request

APP = "货盘助手"
INSTALL = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), APP)
EXE = os.path.join(INSTALL, APP + ".exe")
LA = os.path.join(os.environ.get("LOCALAPPDATA", ""), APP)
DATA = os.path.join(LA, "data")
PTR = os.path.join(LA, "data_dir.txt")
HERE = os.path.dirname(os.path.abspath(__file__))
SHOT = os.path.join(HERE, "_ui_shot_installed.png")

results = []


def check(name, ok, extra=""):
    results.append((name, bool(ok)))
    print(f"  {'OK  ' if ok else 'FAIL'} {name}" + (f"  -> {extra}" if extra else ""))


def port_open(port, timeout=0.5):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def get_json(url, timeout=20, token=None, tries=3):
    """回环地址请求不走系统代理；首次冷启动（Defender 扫描 + 建库）可能较慢，带重试。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url)
            if token:
                req.add_header("Authorization", "Bearer " + token)
            with opener.open(req, timeout=timeout) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, {}
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3)
    raise last


def wait_port(port, secs=40):
    for _ in range(int(secs / 0.5)):
        if port_open(port):
            return True
        time.sleep(0.5)
    return False


def set_env_port(port, data_dir=None):
    d = data_dir or DATA
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, ".env"), "w", encoding="utf-8") as f:
        f.write("SERVER_PORT=%d\n" % port)


def kill_app():
    subprocess.run(["taskkill", "/F", "/IM", APP + ".exe"], capture_output=True)
    time.sleep(2)


def find_windows(keyword=APP):
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
                          "w": rect.right - rect.left, "h": rect.bottom - rect.top})
        return True

    cb_ref = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)(cb)
    user32.EnumWindows(cb_ref, 0)
    return found


def capture_window(hwnd, path):
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
    u32.PrintWindow(hwnd, mdc, 2)

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


def tail_log(path, n=800):
    try:
        return open(path, encoding="utf-8", errors="replace").read()[-n:]
    except OSError:
        return "(无日志)"


# ============================ 场景 A ============================
def scenario_a():
    print("\n" + "=" * 60)
    print("场景 A：正常启动（自建服务 + 数据落在用户目录）")
    print("=" * 60)
    kill_app()
    PORT = 8123
    set_env_port(PORT)
    log = os.path.join(DATA, "服务日志.log")
    if os.path.exists(log):
        os.remove(log)

    proc = subprocess.Popen([EXE], cwd=INSTALL)
    ok = wait_port(PORT)
    check("服务在 %d 端口启动" % PORT, ok)
    if not ok:
        return None
    time.sleep(16)      # 等窗口 + WebView2 渲染

    check("进程存活", proc.poll() is None)

    try:
        st, h = get_json(f"http://127.0.0.1:{PORT}/api/health")
        check("/api/health 可用且标识为 huopan", h.get("app") == "huopan",
              str(h))
    except Exception as e:  # noqa: BLE001
        check("/api/health 可用且标识为 huopan", False, str(e))

    # 登录 + 主要接口
    token = None
    try:
        import urllib.parse
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        body = urllib.parse.urlencode({"username": "admin", "password": "admin123"}).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/auth/login", data=body)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with opener.open(req, timeout=20) as r:
            token = json.loads(r.read())["access_token"]
        check("admin 登录成功（新库自动建号）", bool(token))
    except Exception as e:  # noqa: BLE001
        check("admin 登录成功（新库自动建号）", False, str(e))

    if token:
        for name, path in [("商品列表", "/api/product/list"),
                           ("上传文件管理", "/api/product/uploads"),
                           ("货盘列表", "/api/plan/list")]:
            try:
                st, d = get_json(f"http://127.0.0.1:{PORT}{path}", token=token)
                check(f"接口 {name}", st == 200, f"HTTP {st}")
            except Exception as e:  # noqa: BLE001
                check(f"接口 {name}", False, str(e))
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/product/template")
            req.add_header("Authorization", "Bearer " + token)
            with opener.open(req, timeout=20) as r:
                data = r.read()
                ct = r.headers.get("Content-Type", "")
            check("下载 18 列导入模板", len(data) > 3000 and "spreadsheet" in ct,
                  f"{len(data)} 字节")
        except Exception as e:  # noqa: BLE001
            check("下载 18 列导入模板", False, str(e))

    # 数据落位
    check("数据库建在用户目录", os.path.isfile(os.path.join(DATA, "huopan.db")), DATA)
    check("上传存档目录已建", os.path.isdir(os.path.join(DATA, "uploads")))
    check("同事访问地址.txt 在数据目录", os.path.isfile(os.path.join(DATA, "同事访问地址.txt")))
    check("服务日志.log 在数据目录", os.path.isfile(log))
    check("Program Files 下没有生成 data 目录",
          not os.path.isdir(os.path.join(INSTALL, "data")))
    check("Program Files 下没有生成日志/地址文件",
          not os.path.exists(os.path.join(INSTALL, "服务日志.log"))
          and not os.path.exists(os.path.join(INSTALL, "同事访问地址.txt")))

    # 窗口
    wins = find_windows()
    for w in wins:
        print("      窗口:", w["title"], "|", w["cls"], "|", w["w"], "x", w["h"])
    forms = [w for w in wins if w["cls"].startswith("WindowsForms")]
    check("弹出的是应用窗口（WindowsForms，不是浏览器）", bool(forms))
    if wins:
        big = max(wins, key=lambda x: x["w"] * x["h"])
        try:
            print("      抓图:", capture_window(big["hwnd"], SHOT))
            check("窗口截图成功", os.path.isfile(SHOT))
        except Exception as e:  # noqa: BLE001
            check("窗口截图成功", False, str(e))

    print("  ---- 服务日志尾部 ----")
    print("      " + tail_log(log, 500).replace("\n", "\n      "))
    kill_app()
    return PORT


# ============================ 场景 B ============================
def scenario_b():
    print("\n" + "=" * 60)
    print("场景 B：8001 被「别的程序」占用 → 应自动改用备用端口")
    print("=" * 60)

    class Dummy(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"status":"ok","note":"not huopan"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 8001), Dummy)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(1)
    check("已占用 8001（模拟别的程序）", port_open(8001))

    kill_app()
    set_env_port(8001)
    log = os.path.join(DATA, "服务日志.log")
    if os.path.exists(log):
        os.remove(log)

    proc = subprocess.Popen([EXE], cwd=INSTALL)
    ok = wait_port(8002, secs=45)
    check("自动改用 8002 并启动成功", ok)
    if ok:
        try:
            st, h = get_json("http://127.0.0.1:8002/api/health", timeout=8)
            check("8002 上确实是货盘助手", h.get("app") == "huopan", str(h))
        except Exception as e:  # noqa: BLE001
            check("8002 上确实是货盘助手", False, str(e))
    print("      ---- 服务日志尾部 ----")
    print("      " + tail_log(log, 400).replace("\n", "\n      "))
    kill_app()
    srv.shutdown()


# ============================ 场景 C ============================
def scenario_c():
    print("\n" + "=" * 60)
    print("场景 C：数据目录不可写 → 应自动回退，程序不崩")
    print("=" * 60)
    kill_app()
    old = ""
    if os.path.isfile(PTR):
        old = open(PTR, encoding="utf-8-sig").read()
    set_env_port(8125)                       # 回退后用的目录里指定端口
    with open(PTR, "w", encoding="utf-8") as f:
        f.write(r"Z:\这个盘不存在\货盘数据")     # 不可写
    log = os.path.join(DATA, "服务日志.log")
    if os.path.exists(log):
        os.remove(log)

    proc = subprocess.Popen([EXE], cwd=INSTALL)
    ok = wait_port(8125, secs=45)
    check("回退到用户目录后服务正常启动", ok)
    check("进程未崩溃", proc.poll() is None)

    txt = tail_log(log, 900)
    print("      ---- 服务日志尾部 ----")
    print("      " + txt.replace("\n", "\n      "))
    check("日志里记录了实际使用的数据目录", DATA in txt or "数据目录" in txt)
    check("仍写入用户目录（未误写到 Program Files）",
          os.path.isfile(os.path.join(DATA, "huopan.db")))

    kill_app()
    with open(PTR, "w", encoding="utf-8") as f:
        f.write(old or DATA)                 # 还原
    print("      已还原 data_dir.txt ->", (old or DATA).strip())


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    check("安装好的 exe 存在", os.path.isfile(EXE), EXE)
    # 可只跑某个场景： _verify_installed_run.py a / b / c
    only = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if only in ("", "a"):
        scenario_a()
    if only in ("", "b"):
        scenario_b()
    if only in ("", "c"):
        scenario_c()

    ok_n = sum(1 for _, o in results if o)
    print(f"\n===== 运行验证：{ok_n}/{len(results)} 项通过 =====")
    bad = [n for n, o in results if not o]
    if bad:
        print("未通过：", "、".join(bad))
        raise SystemExit(1)
    print("已安装版本运行行为全部符合预期。")


if __name__ == "__main__":
    main()
