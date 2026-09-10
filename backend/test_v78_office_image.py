# v7.8 验证：Office Excel 普通浮动图片导入后，商品库/货盘详情/重新下载均带图
import io, json, urllib.request, urllib.parse, os
from openpyxl import load_workbook

BASE = "http://127.0.0.1:8000"
TOKEN = None

def http(method, path, data=None, files=None, raw=False):
    global TOKEN
    req = urllib.request.Request(BASE + path, method=method)
    if TOKEN:
        req.add_header("Authorization", "Bearer " + TOKEN)
    if files:
        boundary = "----WebKitFormBoundary7MA4YWxk"
        body = []
        for k, v in files.items():
            body.append(b"--" + boundary.encode())
            body.append(b'Content-Disposition: form-data; name="' + k.encode() + b'"; filename="' + os.path.basename(v).encode() + b'"')
            body.append(b"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            body.append(b"")
            with open(v, "rb") as f:
                body.append(f.read())
        body.append(b"--" + boundary.encode() + b"--")
        req.data = b"\r\n".join(body)
        req.add_header("Content-Type", "multipart/form-data; boundary=" + boundary)
    elif data is not None:
        if raw:
            req.data = urllib.parse.urlencode(data).encode()
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        else:
            req.data = json.dumps(data).encode()
            req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        b = r.read()
        ct = r.headers.get("Content-Type", "")
        return r.status, (json.loads(b) if "json" in ct else b)

def check(name, cond, detail=""):
    ok = bool(cond)
    print(("PASS" if ok else "FAIL") + " - " + name + (" " + str(detail) if detail else ""))
    return ok

# 1. 登录
st, lg = http("POST", "/api/auth/login", {"username": "admin", "password": "admin123"}, raw=True)
TOKEN = lg["access_token"]
print("login ok, token len", len(TOKEN))

# 2. 上传测试 xlsx
st, up = http("POST", "/api/product/upload", files={"file": r"C:\tmp\test_img.xlsx"})
check("上传成功", st == 200 and up.get("ok"), up)

# 3. 商品列表应有图片
st, pl = http("GET", "/api/product/list")
rows = pl.get("rows", [])
print("products:", len(rows))
for r in rows:
    print(" ", r["name"], "image_url len:", len(r["image_url"]) if r.get("image_url") else None)
has_img = any(bool(r.get("image_url")) for r in rows)
check("商品列表至少一张图", has_img, rows)

# 4. 生成公域货盘
img_row = next((r for r in rows if r.get("image_url")), None)
if not img_row:
    raise SystemExit("没有带图商品")
item = {
    "product_id": img_row["id"], "sku": img_row["sku"], "name": img_row["name"],
    "image_url": img_row["image_url"], "cost_price": img_row["cost_price"],
    "shipping_fee": img_row["shipping_fee"], "sale_price": 100, "pricing_mode": "price",
    "category": img_row["category"], "remark": img_row["remark"], "spec": img_row.get("spec", "")
}
st, xls = http("POST", "/api/plan/generate", {"name": "v78-office-img-test", "plan_type": "public", "commission_cut": 0, "cost_mode": "daifa", "items": [item]}, raw=False)
check("生成成功", st == 200 and len(xls) > 10000, (st, len(xls) if isinstance(xls, bytes) else type(xls)))

# 5. 货盘列表取 id
st, plans = http("GET", "/api/plan/list")
plan = next((p for p in plans if p["name"] == "v78-office-img-test"), None)
check("货盘列表有记录", plan is not None, plans)

if plan:
    # 6. 详情返回 image_url
    st, det = http("GET", "/api/plan/" + str(plan["id"]))
    it = det.get("items", [{}])[0]
    print("detail item image_url len:", len(it.get("image_url", "")) if it.get("image_url") else None)
    check("详情 item 有 image_url", bool(it.get("image_url")), it.get("image_url", "")[:50])

    # 7. 下载 Excel 检查图片嵌入
    req = urllib.request.Request(BASE + "/api/plan/" + str(plan["id"]) + "/download", headers={"Authorization": "Bearer " + TOKEN})
    with urllib.request.urlopen(req, timeout=60) as r:
        xls2 = r.read()
    wb = load_workbook(io.BytesIO(xls2))
    ws = wb.active
    has_xl_img = len(ws._images) > 0
    check("Excel 已嵌图片", has_xl_img, len(ws._images))

    # 8. 清理测试数据
    http("DELETE", "/api/plan/" + str(plan["id"]))

print("\n全部检查完成")
