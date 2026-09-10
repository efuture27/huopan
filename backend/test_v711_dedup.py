# -*- coding: utf-8 -*-
"""v7.11 导入去重保护冒烟：验证 parse_product_excel 按 (name, sku) 去重合并。"""
import io
import sys

sys.path.insert(0, r"E:\WorkBuddyData\WorkBuddy\2026-08-23-11-00-35\ai-huopan-demo\backend")
from openpyxl import Workbook
from app.services.excel import parse_product_excel

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}  -> {detail}")


def make_xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(["产品名称", "机制", "成本价（出厂价）", "代发费", "卖点介绍"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# 1. 完全相同的两行 → 去重为 1 条
data = make_xlsx([
    ["云南普洱袋泡茶", "3盒装", 59.9, 5, "先涩后甘"],
    ["云南普洱袋泡茶", "3盒装", 59.9, 5, "先涩后甘"],
])
prods = parse_product_excel(data, "测试.xlsx")
check("完全重复两行→1条", len(prods) == 1, f"len={len(prods)}")

# 2. 空壳行 + 有效行（同名同 sku，合并单元格展开典型场景）→ 合并为 1 条且取非零成本
data = make_xlsx([
    ["云南普洱袋泡茶", "3盒装", None, None, ""],
    ["云南普洱袋泡茶", "3盒装", 59.9, 5, "先涩后甘"],
])
prods = parse_product_excel(data, "测试.xlsx")
check("空壳+有效行→1条", len(prods) == 1, f"len={len(prods)}")
check("合并后成本=59.9", len(prods) == 1 and abs(prods[0]["cost_price"] - 59.9) < 0.001,
      str(prods[0]["cost_price"] if prods else None))
check("合并后代发费=5", len(prods) == 1 and abs(prods[0]["shipping_fee"] - 5) < 0.001,
      str(prods[0]["shipping_fee"] if prods else None))
check("合并后卖点补全", len(prods) == 1 and prods[0]["remark"] == "先涩后甘",
      str(prods[0]["remark"] if prods else None))

# 3. 同名不同 SKU → 保留 2 条（不同规格，不误删）
data = make_xlsx([
    ["云南普洱袋泡茶", "3盒装", 59.9, 5, "先涩后甘"],
    ["云南普洱袋泡茶", "5盒装", 89.9, 5, "先涩后甘"],
])
prods = parse_product_excel(data, "测试.xlsx")
check("同名不同SKU→保留2条", len(prods) == 2, f"len={len(prods)}")

# 4. 三行：有效行在前、空壳行在后 → 仍 1 条且不被空壳覆盖
data = make_xlsx([
    ["云南普洱袋泡茶", "3盒装", 59.9, 5, "先涩后甘"],
    ["云南普洱袋泡茶", "3盒装", None, None, ""],
])
prods = parse_product_excel(data, "测试.xlsx")
check("有效行在前不被覆盖", len(prods) == 1 and abs(prods[0]["cost_price"] - 59.9) < 0.001,
      f"len={len(prods)} cost={prods[0]['cost_price'] if prods else None}")

print(f"\n===== {PASS} PASS / {FAIL} FAIL =====")
sys.exit(1 if FAIL else 0)
