# -*- coding: utf-8 -*-
"""货盘助手 7.17 安装包 · 分发前准备

作用：清理 dist 里不该分发的东西，放进使用说明。
注意：安装版不需要预置数据库——程序首次启动会在用户选的数据目录里自动建库和账号。

    cd backend
    ./venv311/Scripts/python.exe _prep_installer_dist.py
"""
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist", "货盘助手")
OUTPUTS = os.path.join(HERE, "..", "outputs")

print("== 1. 清理运行期产物 ==")
# data 整个不要（数据库在数据目录里由程序自建，不放进 Program Files）
_data = os.path.join(DIST, "data")
if os.path.isdir(_data):
    _dst = os.path.join(os.environ.get("TEMP", HERE), "huopan_dist_data_%d" % int(os.times().elapsed))
    try:
        shutil.move(_data, _dst)
        print("   已移出 data/ ->", _dst)
    except OSError as e:
        print("   移出 data/ 失败：", e)

for f in [".env", "服务日志.log", "启动错误.log", "同事访问地址.txt", "创建桌面快捷方式.bat"]:
    p = os.path.join(DIST, f)
    if os.path.exists(p):
        os.remove(p)
        print("   已删除", f)

print("\n== 2. 放入使用说明 ==")
src = os.path.join(OUTPUTS, "使用说明_v7.17_安装版.txt")
with open(src, encoding="utf-8") as f:
    txt = f.read()
with open(os.path.join(DIST, "使用说明.txt"), "w", encoding="utf-8-sig") as f:
    f.write(txt)   # 带 BOM：记事本打开不乱码
print("   使用说明.txt 已就位（%d 字节）" % os.path.getsize(os.path.join(DIST, "使用说明.txt")))

print("\n== 3. 校验必需文件 ==")
# 注意：图标、前端等 datas 都在 _internal 下（onedir 的 _MEIPASS）
need = ["货盘助手.exe", "_internal", "使用说明.txt",
        os.path.join("_internal", "app_icon.ico"),
        os.path.join("_internal", "frontend", "index.html")]
ok = True
for n in need:
    p = os.path.join(DIST, n)
    exists = os.path.exists(p)
    ok = ok and exists
    print(f"   {'OK ' if exists else '缺失'} {n}")

print("\n== 最终目录 ==")
for f in sorted(os.listdir(DIST)):
    p = os.path.join(DIST, f)
    size = os.path.getsize(p) if os.path.isfile(p) else "-"
    print(f"   {f}  {size}")

if not ok:
    raise SystemExit("准备失败：缺少必需文件")
print("\n准备完成。")
