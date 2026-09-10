# -*- coding: utf-8 -*-
"""v7.13 上传文件管理 冒烟测试"""
import io
import os
import sys
import json
import urllib.request

BASE = "http://127.0.0.1:8000"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from openpyxl import Workbook, load_workbook

PASS = 0
FAIL = 0
def check(name, cond, extra=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  [PASS] {name}")
    else: FAIL += 1; print(f"  [FAIL] {name} {extra}")

def req(method, path, token=None, data=None, raw=False, ctype=None):
    url = BASE + path
    headers = {}
    if token: headers["Authorization"] = "Bearer " + token
    if ctype: headers["Content-Type"] = ctype
    body = None
    if data is not None:
        body = data
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            content = resp.read()
            return resp.status, content if raw else json.loads(content)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")

# 1. 登录 admin
code, d = req("POST", "/api/auth/login",
              data="username=admin&password=admin123".encode(),
              )
# login 是 form —— 需要 x-www-form-urlencoded
r = urllib.request.Request(BASE + "/api/auth/login",
    data="username=admin&password=admin123".encode(),
    headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
with urllib.request.urlopen(r) as resp:
    d = json.loads(resp.read())
TOKEN = d["access_token"]
check("admin 登录", bool(TOKEN))

# 普通用户登录
r = urllib.request.Request(BASE + "/api/auth/login",
    data="username=huopan&password=huopan123".encode(),
    headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
with urllib.request.urlopen(r) as resp:
    d2 = json.loads(resp.read())
UTOKEN = d2["access_token"]
check("user 登录", bool(UTOKEN))

# 2. 构造测试 Excel
wb = Workbook(); ws = wb.active
ws.append(["测试商家成本货盘"])
ws.append(["产品名称", "产品图片", "规格", "机制", "成本价（出厂价）", "代发费", "商家", "分类"])
ws.append(["测试商品A", "", "12g*10袋", "3盒装", 59.9, 5, "测试商家", "袋泡茶"])
ws.append(["测试商品B", "", "200g", "1瓶", 39.0, 4, "测试商家", "饮品"])
buf = io.BytesIO(); wb.save(buf)
xlsx_bytes = buf.getvalue()

# 3. 上传（multipart）
boundary = "----v713test"
parts = []
parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"merchant\"\r\n\r\n测试商家\r\n".encode())
parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"v713测试成本表.xlsx\"\r\nContent-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n".encode() + xlsx_bytes + b"\r\n")
parts.append(f"--{boundary}--\r\n".encode())
body = b"".join(parts)
code, d = req("POST", "/api/product/upload", token=TOKEN, data=body, ctype="multipart/form-data; boundary=----v713test")
check("上传成功 200", code == 200, str(d))
check("上传返回 inserted=2", d.get("inserted") == 2, str(d))

# 4. 列表：有记录且 is_active
code, d = req("GET", "/api/product/uploads", token=TOKEN)
rows = d.get("rows", [])
check("上传记录列表非空", len(rows) >= 1, str(rows))
rec = rows[0] if rows else {}
check("记录文件名正确", rec.get("filename") == "v713测试成本表.xlsx", rec.get("filename", ""))
check("记录 is_active=True", rec.get("is_active") is True, str(rec))
check("记录商品数=2", rec.get("product_count") == 2, str(rec.get("product_count")))
check("记录含大小", (rec.get("file_size") or 0) > 0, str(rec.get("file_size")))
FID = rec.get("id")

# 5. 原文件已落盘 data/uploads/
import glob as _g
from app import config as _cfg
files = _g.glob(os.path.join(_cfg.UPLOAD_DIR, "*v713*"))
check("data/uploads 存在存档文件", len(files) >= 1, str(files))

# 6. 下载并与原件字节一致
code, blob = req("GET", f"/api/product/uploads/{FID}/download", token=TOKEN, raw=True)
check("下载 200", code == 200)
check("下载内容与原件一致", blob == xlsx_bytes, f"{len(blob)} vs {len(xlsx_bytes)}")

# 7. 再上传一份新文件（旧记录应变 is_active=False）
wb2 = Workbook(); ws2 = wb2.active
ws2.append(["第二份"])
ws2.append(["产品名称", "产品图片", "规格", "机制", "成本价（出厂价）", "代发费", "商家", "分类"])
ws2.append(["测试商品C", "", "500g", "2盒", 19.9, 3, "测试商家", "食材"])
buf2 = io.BytesIO(); wb2.save(buf2)
xlsx2 = buf2.getvalue()
parts = []
parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"merchant\"\r\n\r\n\r\n".encode())
parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"v713第二份.xlsx\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode() + xlsx2 + b"\r\n")
parts.append(f"--{boundary}--\r\n".encode())
code, d = req("POST", "/api/product/upload", token=TOKEN, data=b"".join(parts), ctype="multipart/form-data; boundary=----v713test")
check("第二次上传成功", code == 200, str(d))
code, d = req("GET", "/api/product/uploads", token=TOKEN)
rows = d.get("rows", [])
actives = [r_ for r_ in rows if r_.get("is_active")]
check("仅 1 条使用中", len(actives) == 1, str(len(actives)))
check("使用中为最新记录", actives and actives[0]["filename"] == "v713第二份.xlsx", str(actives))

# 8. 恢复第一份 → 商品库变回 2 个商品（A、B）
code, d = req("POST", f"/api/product/uploads/{FID}/restore", token=TOKEN)
check("恢复 200", code == 200, str(d))
check("恢复 inserted=2", d.get("inserted") == 2, str(d))
code, d = req("GET", "/api/product/list", token=TOKEN)
names = sorted(r_["name"] for r_ in d["rows"])
check("恢复后商品库=A,B", names == ["测试商品A", "测试商品B"], str(names))
code, d = req("GET", "/api/product/uploads", token=TOKEN)
rec1 = [r_ for r_ in d["rows"] if r_["id"] == FID]
check("恢复后记录1标记使用中", rec1 and rec1[0]["is_active"] is True, str(rec1))

# 9. 普通用户权限：user 可看列表/下载，恢复/删除 403
code, d = req("GET", "/api/product/uploads", token=UTOKEN)
check("user 可看列表", code == 200)
code, blob = req("GET", f"/api/product/uploads/{FID}/download", token=UTOKEN, raw=True)
check("user 可下载", code == 200)
code, d = req("POST", f"/api/product/uploads/{FID}/restore", token=UTOKEN)
check("user 恢复被拒 403", code == 403, str(code))
code, d = req("DELETE", f"/api/product/uploads/{FID}", token=UTOKEN)
check("user 删除被拒 403", code == 403, str(code))

# 10. 清理：删除两条测试记录（admin）
code, d = req("DELETE", f"/api/product/uploads/{FID}", token=TOKEN)
check("admin 删除记录1", code == 200, str(d))
code, d = req("GET", "/api/product/uploads", token=TOKEN)
left = [r_ for r_ in d.get("rows", []) if r_["filename"].startswith("v713")]
FID2 = left[0]["id"] if left else None
if FID2:
    code, d = req("DELETE", f"/api/product/uploads/{FID2}", token=TOKEN)
    check("admin 删除记录2", code == 200, str(d))
files_after = _g.glob(os.path.join(_cfg.UPLOAD_DIR, "*v713*"))
check("存档文件已随记录删除", len(files_after) == 0, str(files_after))

# 11. 恢复测试前商品库（删除遗留测试商品，避免污染）
import sqlite3
db_path = os.path.join(_cfg.DATA_DIR, "huopan.db")
conn = sqlite3.connect(db_path)
conn.execute("PRAGMA busy_timeout=5000")
conn.execute("DELETE FROM product WHERE name LIKE '测试商品%'")
conn.commit(); conn.close()
print("  [INFO] 已清理测试商品")

print(f"\n结果: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
