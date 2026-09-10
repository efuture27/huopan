# -*- coding: utf-8 -*-
"""离线验证：WPS 内嵌图片解析（云酥妃货盘表.xlsx 样本）"""
import sys, time, json, io

sys.stdout = io.open(r"E:\WorkBuddyData\WorkBuddy\2026-08-23-11-00-35\ai-huopan-demo\backend\_test_out.txt", "w", encoding="utf-8")
sys.path.insert(0, r"E:\WorkBuddyData\WorkBuddy\2026-08-23-11-00-35\ai-huopan-demo\backend")

t0 = time.time()
from app.services.excel import parse_product_excel

SRC = r"C:\Users\Administrator\Desktop\办公文件\云酥妃货盘表.xlsx"
with open(SRC, "rb") as f:
    data = f.read()
print("read: %.1fs, %d bytes" % (time.time() - t0, len(data)))

t1 = time.time()
prods = parse_product_excel(data)
print("parse: %.1fs" % (time.time() - t1))

with_img = [p for p in prods if p["image_url"]]
print("total=%d with_image=%d" % (len(prods), len(with_img)))

if with_img:
    u = with_img[0]["image_url"]
    print("sample image_url prefix:", u[:50], "... len=%d" % len(u))
    sizes = [len(p["image_url"]) for p in with_img]
    print("img data-url len min/avg/max: %d / %d / %d" % (min(sizes), sum(sizes) // len(sizes), max(sizes)))
    print("first with-image row:", json.dumps(
        {k: (v[:36] + "..." if isinstance(v, str) and len(v) > 36 else v) for k, v in with_img[0].items()},
        ensure_ascii=False))

if prods:
    print("first row:", json.dumps(
        {k: (v[:36] + "..." if isinstance(v, str) and len(v) > 36 else v) for k, v in prods[0].items()},
        ensure_ascii=False))
