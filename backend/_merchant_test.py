# -*- coding: utf-8 -*-
"""离线验证：商家识别（标题行 / 文件名兜底 / 商家列）"""
import sys, io

sys.path.insert(0, r"E:\WorkBuddyData\WorkBuddy\2026-08-23-11-00-35\ai-huopan-demo\backend")

out = io.StringIO()

from app.services.excel import parse_product_excel

# 用真实样本（表头不在第 1 行的 WPS 文件）+ 模拟文件名
path = r"C:\Users\Administrator\Desktop\办公文件\云酥妃货盘表.xlsx"
with open(path, "rb") as f:
    data = f.read()

# 场景1：真实文件 + 真实文件名
prods = parse_product_excel(data, "云酥妃货盘表.xlsx")
print("== 场景1 真实样本 ==", file=out)
print("total=%d" % len(prods), file=out)
if prods:
    m = prods[0].get("merchant")
    print("merchant[0]=%r" % m, file=out)
    ms = {p.get("merchant") for p in prods}
    print("distinct merchants=%r" % ms, file=out)

# 场景2：模拟云南鑫多多文件名兜底（标题行未命中关键词时走文件名）
prods2 = parse_product_excel(data, "云南鑫多多农业科技有限公司私域货盘（总）含税更新.xlsx")
print("== 场景2 文件名兜底 ==", file=out)
if prods2:
    print("merchant[0]=%r" % prods2[0].get("merchant"), file=out)

with open(r"E:\WorkBuddyData\WorkBuddy\2026-08-23-11-00-35\ai-huopan-demo\backend\_merchant_test.txt", "w", encoding="utf-8") as f:
    f.write(out.getvalue())
print("done")
