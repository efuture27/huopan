# -*- coding: utf-8 -*-
"""端到端验证：上传带 merchant → 落库 → 列表返回 merchant"""
import io, json, sys

sys.path.insert(0, r"E:\WorkBuddyData\WorkBuddy\2026-08-23-11-00-35\ai-huopan-demo\backend")
out = io.StringIO()

import requests

BASE = "http://127.0.0.1:8000/api"

# 登录
r = requests.post(BASE + "/auth/login", data={"username": "admin", "password": "admin123"}, timeout=15)
r.raise_for_status()
token = r.json()["access_token"]
H = {"Authorization": "Bearer " + token}
print("login OK", file=out)

# 上传（不填 merchant，测自动识别；文件名带商家）
path = r"C:\Users\Administrator\Desktop\办公文件\云酥妃货盘表.xlsx"
with open(path, "rb") as f:
    r = requests.post(BASE + "/product/upload",
                      headers=H,
                      files={"file": ("云南鑫多多农业科技有限公司私域货盘（总）含税更新.xlsx", f)},
                      timeout=300)
print("upload status=%s" % r.status_code, file=out)
print("upload resp=%s" % json.dumps(r.json(), ensure_ascii=False), file=out)

# 列表验证 merchant + merchants 清单
r = requests.get(BASE + "/product/list", headers=H, timeout=30)
d = r.json()
rows = d["rows"]
print("list rows=%d merchants=%r" % (len(rows), d.get("merchants")), file=out)
with_m = [x for x in rows if x.get("merchant")]
print("with_merchant=%d sample=%r" % (len(with_m), with_m[0]["merchant"] if with_m else None), file=out)

# 按商家筛选
r = requests.get(BASE + "/product/list", params={"merchant": "云南鑫多多农业科技有限公司私域"}, headers=H, timeout=30)
print("filter rows=%d" % len(r.json()["rows"]), file=out)

with open(r"E:\WorkBuddyData\WorkBuddy\2026-08-23-11-00-35\ai-huopan-demo\backend\_e2e_merchant.txt", "w", encoding="utf-8") as f:
    f.write(out.getvalue())
print("done")
