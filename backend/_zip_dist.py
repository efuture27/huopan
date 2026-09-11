# -*- coding: utf-8 -*-
"""把 dist/货盘助手 打包成可分发的 zip（顶层目录「货盘助手/」）"""
import os
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(HERE, "dist", "货盘助手")
OUT = os.path.join(ROOT, "货盘助手-桌面版-v7.14.zip")
TOP = "货盘助手"

# 排除项：运行时产物（注意：不能排除名为 webview 的目录，_internal/webview 是 pywebview 的包数据）
EXCLUDE_DIRS = {"__pycache__"}
EXCLUDE_FILES = {".env"}

total = 0
count = 0
t0 = time.time()
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for base, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if f in EXCLUDE_FILES:
                continue
            full = os.path.join(base, f)
            rel = os.path.relpath(full, SRC)
            z.write(full, os.path.join(TOP, rel))
            total += os.path.getsize(full)
            count += 1

size = os.path.getsize(OUT)
print(f"文件数: {count}")
print(f"原始大小: {total/1024/1024:.1f} MB")
print(f"压缩后:   {size/1024/1024:.1f} MB  ({size/1024/1024*100/max(total/1024/1024,0.01):.0f}%)")
print(f"耗时: {time.time()-t0:.0f}s")
print("输出:", OUT)

# 校验：能打开、条目数一致、exe 在
with zipfile.ZipFile(OUT) as z:
    bad = z.testzip()
    print("完整性校验:", "OK" if bad is None else f"损坏 -> {bad}")
    names = z.namelist()
    print("条目数:", len(names))
    print("含 exe:", f"{TOP}/货盘助手.exe" in names)
    print("含说明:", f"{TOP}/使用说明.txt" in names)
    print("含库:", f"{TOP}/data/huopan.db" in names)
