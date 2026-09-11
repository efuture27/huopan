# -*- coding: utf-8 -*-
"""核验安装痕迹：程序文件、注册表、快捷方式、防火墙、数据目录指针。

    cd backend && ./venv311/Scripts/python.exe _verify_install.py
或指定数据目录预期值：
    ./venv311/Scripts/python.exe _verify_install.py "D:\\货盘数据"
"""
import os
import sys
import winreg

APP = "货盘助手"
PF = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), APP)
LA = os.path.join(os.environ.get("LOCALAPPDATA", ""), APP)
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
STARTMENU = os.path.join(os.environ.get("APPDATA", ""),
                         r"Microsoft\Windows\Start Menu\Programs", APP)

expect_data = sys.argv[1] if len(sys.argv) > 1 else os.path.join(LA, "data")
results = []


def check(name, ok, extra=""):
    results.append((name, bool(ok), extra))
    print(f"  {'OK  ' if ok else 'FAIL'} {name}" + (f"  -> {extra}" if extra else ""))


print("== 1. 程序文件 ==")
check("安装目录存在", os.path.isdir(PF), PF)
check("主程序 货盘助手.exe", os.path.isfile(os.path.join(PF, "货盘助手.exe")))
check("运行时目录 _internal", os.path.isdir(os.path.join(PF, "_internal")))
check("前端已打包", os.path.isfile(os.path.join(PF, "_internal", "frontend", "index.html")))
check("使用说明.txt", os.path.isfile(os.path.join(PF, "使用说明.txt")))
check("卸载程序 unins000.exe", os.path.isfile(os.path.join(PF, "unins000.exe")))
check("程序目录内没有 data（数据不该在 Program Files）", not os.path.isdir(os.path.join(PF, "data")))
check("程序目录内没有 .env", not os.path.isfile(os.path.join(PF, ".env")))

print("\n== 2. 卸载项（设置 → 应用里能看到）==")
found = None
for hive, sub in [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                  (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                  (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")]:
    try:
        with winreg.OpenKey(hive, sub) as k:
            n = winreg.QueryInfoKey(k)[0]
            for i in range(n):
                name = winreg.EnumKey(k, i)
                try:
                    with winreg.OpenKey(hive, sub + "\\" + name) as sk:
                        dn = winreg.QueryValueEx(sk, "DisplayName")[0]
                        if APP in str(dn):
                            ver = winreg.QueryValueEx(sk, "DisplayVersion")[0]
                            found = (name, dn, ver)
                except OSError:
                    continue
    except OSError:
        continue
check("注册表卸载项存在", found, str(found))

print("\n== 3. 快捷方式 ==")
# 管理员安装（所有用户）时，桌面/开始菜单落在「公共」位置，不是当前用户的目录
PUBLIC_DESKTOP = os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Desktop")
COMMON_PROGRAMS = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                               r"Microsoft\Windows\Start Menu\Programs")
candidates_desk = [os.path.join(PUBLIC_DESKTOP, APP + ".lnk"),
                   os.path.join(DESKTOP, APP + ".lnk")]
hit = next((p for p in candidates_desk if os.path.isfile(p)), None)
check("桌面快捷方式", hit, hit or "、".join(candidates_desk))
groups = [os.path.join(COMMON_PROGRAMS, APP), os.path.join(STARTMENU)]
hit_g = next((p for p in groups if os.path.isdir(p)), None)
check("开始菜单程序组", hit_g, hit_g or "、".join(groups))
if hit_g:
    for f in sorted(os.listdir(hit_g)):
        print("        ", f)

print("\n== 4. 数据目录指针 ==")
ptr = os.path.join(LA, "data_dir.txt")
check("data_dir.txt 已写入", os.path.isfile(ptr), ptr)
if os.path.isfile(ptr):
    val = open(ptr, encoding="utf-8-sig").read().strip()
    print("         内容:", repr(val))
    check("指针内容符合预期", os.path.normcase(val) == os.path.normcase(expect_data),
          f"期望 {expect_data}")
try:
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\" + APP) as k:
        reg_val = winreg.QueryValueEx(k, "DataDir")[0]
    check("注册表 HKLM\\SOFTWARE\\货盘助手\\DataDir", True, reg_val)
except OSError as e:
    check("注册表 HKLM\\SOFTWARE\\货盘助手\\DataDir", False, str(e))

print("\n== 5. 开机自启（本次未勾选，应不存在）==")
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
        run_val = winreg.QueryValueEx(k, APP)[0]
    check("自启项未写入（预期未勾选）", False, f"意外存在: {run_val}")
except OSError:
    check("自启项未写入（预期未勾选）", True)

print("\n== 6. 防火墙规则 ==")
import subprocess


def run_text(args):
    """netsh 输出编码在不同环境下可能是 UTF-8 或 GBK，取能正确解出中文的那个。"""
    r = subprocess.run(args, capture_output=True)
    raw = r.stdout or b""
    for enc in ("utf-8", "gbk"):
        try:
            t = raw.decode(enc)
            if APP in t:
                return t
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


out = run_text(["netsh", "advfirewall", "firewall", "show", "rule", "name=" + APP])
has_rule = APP in out and ("允许" in out or "Allow" in out)
check("防火墙放行规则已添加", has_rule)
for line in out.splitlines():
    if any(t in line for t in ("规则名称", "Rule Name", "已启用", "Enabled", "操作", "Action", "程序", "Program")):
        print("        ", line.strip())

ok_n = sum(1 for _, o, _ in results if o)
print(f"\n== 结果：{ok_n}/{len(results)} 项通过 ==")
bad = [n for n, o, _ in results if not o]
if bad:
    print("未通过：", "、".join(bad))
    raise SystemExit(1)
print("安装痕迹全部符合预期。")
