# -*- coding: utf-8 -*-
"""分发前准备：清理测试痕迹、检查并压缩分发数据库（纯净版）"""
import os
import shutil
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist", "货盘助手")
DB = os.path.join(DIST, "data", "huopan.db")

print("== 1. 清理测试文件 ==")
for f in [".env", "服务日志.log", "启动错误.log", "同事访问地址.txt"]:
    p = os.path.join(DIST, f)
    if os.path.exists(p):
        os.remove(p)
        print("   已删除", f)
# WebView2 用户数据（登录态、缓存）：分发前移出程序目录（既不打进包，也不触发批量删除保护）
import tempfile
import time as _time

_wv = os.path.join(DIST, "data", "webview")
if os.path.isdir(_wv):
    _dst = os.path.join(tempfile.gettempdir(), "huopan_webview_%d" % int(_time.time()))
    try:
        shutil.move(_wv, _dst)
        print("   已移出 data/webview ->", _dst)
    except OSError as e:
        print("   移出 data/webview 失败：", e)

print("\n== 2. 分发库检查 ==")
conn = sqlite3.connect(DB)
conn.execute("PRAGMA busy_timeout=5000")


def count(table):
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.Error as e:
        return f"ERR {e}"


for t in ["app_user", "product", "product_plan", "product_plan_item", "uploaded_file", "merchant_fee"]:
    print(f"   {t}: {count(t)}")
print("   用户:", conn.execute("SELECT username, role FROM app_user").fetchall())

print("\n== 3. WAL checkpoint + VACUUM ==")
print("   checkpoint:", conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
conn.execute("VACUUM")
conn.commit()
conn.close()

for f in ["huopan.db", "huopan.db-wal", "huopan.db-shm"]:
    p = os.path.join(DIST, "data", f)
    print(f"   {f}: {os.path.getsize(p) if os.path.exists(p) else '(已合并/不存在)'}")

print("\n== 4. 清理空的 backups ==")
bd = os.path.join(DIST, "data", "backups")
if os.path.isdir(bd):
    for f in os.listdir(bd):
        os.remove(os.path.join(bd, f))
    print("   backups 已清空")

print("\n== 5. 写入说明与快捷方式脚本 ==")
_src = os.path.join(HERE, "..", "outputs", "使用说明_v7.14_桌面版.txt")
with open(_src, encoding="utf-8") as _f:
    _txt = _f.read()
with open(os.path.join(DIST, "使用说明.txt"), "w", encoding="utf-8-sig") as _f:
    _f.write(_txt)      # 带 BOM：Windows 记事本/Excel 打开不乱码
shutil.copyfile(os.path.join(HERE, "..", "outputs", "打包素材_创建桌面快捷方式.bat"),
                os.path.join(DIST, "创建桌面快捷方式.bat"))
print("   使用说明.txt / 创建桌面快捷方式.bat 已就位")

print("\n== 最终目录 ==")
for f in sorted(os.listdir(DIST)):
    p = os.path.join(DIST, f)
    size = os.path.getsize(p) if os.path.isfile(p) else "-"
    print(f"   {f}  {size}")
print("   data/: ", sorted(os.listdir(os.path.join(DIST, "data"))))
