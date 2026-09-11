# -*- coding: utf-8 -*-
"""货盘助手 · 一键构建 Windows 安装包

做四件事：
  1. 确保 .iss / .isl 带 UTF-8 BOM（Inno 认 BOM，否则中文乱码）
  2. PyInstaller 打 onedir 程序目录（venv311：唯一带 tkinter 的环境）
  3. _prep_installer_dist.py 清理 dist、放入使用说明
  4. 调 ISCC.exe 编译出 货盘助手_安装程序_vX.exe

用法（在 backend 目录下）：
    ./venv311/Scripts/python.exe build_installer.py

依赖：Inno Setup 6（winget install --id JRSoftware.InnoSetup -e）
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INSTALLER = os.path.join(HERE, "installer")
ISS = os.path.join(INSTALLER, "货盘助手.iss")
DIST = os.path.join(HERE, "dist", "货盘助手")
PY = os.path.join(HERE, "venv311", "Scripts", "python.exe")

# ISCC.exe 常见位置
ISCC_CANDIDATES = [
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
]


def ensure_bom(path):
    raw = open(path, "rb").read()
    if not raw.startswith(b"\xef\xbb\xbf"):
        open(path, "wb").write(b"\xef\xbb\xbf" + raw)
        print("   加 BOM:", os.path.basename(path))
    else:
        print("   BOM 完好:", os.path.basename(path))


def find_iscc():
    for p in ISCC_CANDIDATES:
        if p and os.path.isfile(p):
            return p
    # 兜底：从注册表找 Inno Setup 的安装目录
    try:
        import winreg
        for hive, key in [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"),
                          (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1")]:
            try:
                with winreg.OpenKey(hive, key) as k:
                    loc = winreg.QueryValueEx(k, "InstallLocation")[0]
                p = os.path.join(loc, "ISCC.exe")
                if os.path.isfile(p):
                    return p
            except OSError:
                continue
    except ImportError:
        pass
    return None


def run(cmd, cwd, desc, tail=8):
    print(f"\n--- {desc} ---")
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    for line in out.splitlines()[-tail:]:
        print("   ", line)
    if r.returncode != 0:
        print("\n!! 失败，完整输出：")
        print(out[-3000:])
        raise SystemExit(r.returncode)
    return out


def main():
    if not os.path.isfile(PY):
        raise SystemExit(f"找不到打包用 Python：{PY}（需要 venv311，只有它带 tkinter）")

    print("== 1. 检查 Inno 脚本编码 ==")
    ensure_bom(ISS)
    ensure_bom(os.path.join(INSTALLER, "Languages", "ChineseSimplified.isl"))

    print("== 2. PyInstaller 打包程序目录 ==")
    env = dict(os.environ, PYTHONPATH="")
    r = subprocess.run([PY, "-m", "PyInstaller", "--clean", "--noconfirm", "货盘助手.spec"],
                       cwd=HERE, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print((r.stdout or "")[-3000:], (r.stderr or "")[-1500:])
        raise SystemExit("PyInstaller 打包失败")
    print("   完成")

    print("== 3. 分发前准备 ==")
    run([PY, "_prep_installer_dist.py"], cwd=HERE, desc="清理 dist + 放入使用说明", tail=12)

    print("== 4. 编译安装包 ==")
    iscc = find_iscc()
    if not iscc:
        raise SystemExit("找不到 ISCC.exe。请先安装 Inno Setup 6：\n"
                         "  winget install --id JRSoftware.InnoSetup -e "
                         "--accept-package-agreements --accept-source-agreements")
    print("   使用:", iscc)
    out = run([iscc, ISS], cwd=INSTALLER, desc="ISCC 编译", tail=4)

    # 从 ISCC 输出里取产物名，兜底按 .iss 里的约定拼
    exe_path = os.path.join(ROOT, "货盘助手_安装程序_v7.17.exe")
    for line in out.splitlines():
        if "Resulting Setup program filename is" in line:
            cand = line.split("is:", 1)[-1].strip()
            if os.path.isfile(cand):
                exe_path = cand
    if not os.path.isfile(exe_path):
        raise SystemExit("编译似乎成功但找不到产物")

    size = os.path.getsize(exe_path) / 1024 / 1024
    print(f"\n===== 构建完成 =====")
    print(f"   安装包：{exe_path}")
    print(f"   大小  ：{size:.1f} MB")
    print("\n   验证建议：")
    print('     .\\venv311\\Scripts\\python.exe _verify_install.py        （装完后核验安装痕迹）')
    print('     .\\venv311\\Scripts\\python.exe _verify_installed_run.py  （装完后跑运行时验证）')


if __name__ == "__main__":
    main()
