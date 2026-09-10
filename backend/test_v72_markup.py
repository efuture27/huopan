# -*- coding: utf-8 -*-
"""v7.2 冒烟：私域「一件代发价上调%」—— 直播价不变，一件代发价/含税/毛利率联动，集采不变，可重新下载还原。"""
import io, json
import urllib.request, urllib.parse
from openpyxl import load_workbook

BASE = "http://127.0.0.1:8000"
P, F = [], []


def check(n, ok, d=""):
    (P if ok else F).append(n)
    print(("  PASS  " if ok else "  FAIL  ") + n + ("" if ok else "  " + str(d)))


def http(method, path, token=None, data=None, form=False):
    req = urllib.request.Request(BASE + path, method=method)
    if token: req.add_header("Authorization", "Bearer " + token)
    if data is not None:
        if form:
            req.data = urllib.parse.urlencode(data).encode(); req.add_header("Content-Type", "application/x-www-form-urlencoded")
        else:
            req.data = json.dumps(data).encode(); req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        b = r.read(); ct = r.headers.get("Content-Type", "")
        return r.status, (json.loads(b) if "json" in ct else b)


st, lg = http("POST", "/api/auth/login", data={"username": "admin", "password": "admin123"}, form=True)
TOKEN = lg["access_token"]
check("登录", st == 200 and TOKEN)
# 清掉历史同名货盘（避免上次中断残留干扰）
st, plans0 = http("GET", "/api/plan/list", TOKEN)
for p in [x for x in plans0 if x["name"] in ("v72冒烟-上浮", "v72公域回归")]:
    http("DELETE", f"/api/plan/{p['id']}", TOKEN)

# 两个商品，不同上浮：A(DB id1 云南普洱 cost59.9+fee5) 上浮5%；B(DB id2 石斛 cost120+fee0) 上浮0%
ITEMS = [
    {"product_id": 1, "sku": "3盒装", "name": "云南普洱袋泡茶", "cost_price": 59.9, "shipping_fee": 5, "sale_price": 129, "markup_pct": 5},
    {"product_id": 2, "sku": "1盒装", "name": "石斛冻干粉", "cost_price": 120, "shipping_fee": 0, "sale_price": 260, "markup_pct": 0},
]
# 期望：A base=64.9 → 上浮5%=68.145；B base=120 → 30→120
st, xls = http("POST", "/api/plan/generate", TOKEN, {
    "name": "v72冒烟-上浮", "plan_type": "private", "tax_rate": 0.09, "title": "上浮测试", "items": ITEMS})
ws = load_workbook(io.BytesIO(xls)).active
def rowv(r, col):  # 表头在 row2（有标题）
    return ws.cell(r, col).value
# 第3行=商品A
check("A 一件代发价=68.15", abs(float(rowv(3, 9)) - 64.9 * 1.05) < 0.01, rowv(3, 9))
check("A 含税=74.28", abs(float(rowv(3, 10)) - 64.9 * 1.05 * 1.09) < 0.01, rowv(3, 10))
exp_m1 = (129 - 64.9 * 1.05) / 129 * 100
check("A 毛利率不含税", abs(float(str(rowv(3, 11)).replace('%', '')) - exp_m1) < 0.1, rowv(3, 11))
check("A 集采价=59.9 不变", abs(float(rowv(3, 13)) - 59.9) < 0.01, rowv(3, 13))
check("A 直播价=129 不变", abs(float(rowv(3, 8)) - 129.0) < 1e-6, rowv(3, 8))
# 第4行=商品B（无上浮）
check("B 一件代发价=120", abs(float(rowv(4, 9)) - 120.0) < 0.01, rowv(4, 9))
check("B 集采价=120", abs(float(rowv(4, 13)) - 120.0) < 0.01, rowv(4, 13))

# 详情预览 daifa_price 反映上浮（真实 DB 商品按 sku 取）
st, plans = http("GET", "/api/plan/list", TOKEN)
pid = [p for p in plans if p["name"] == "v72冒烟-上浮"]
pid = pid[0]["id"] if pid else None
check("货盘已落库", pid is not None)
st, det = http("GET", f"/api/plan/{pid}", TOKEN)
its = det.get("items", [])
a = [i for i in its if i["sku"] == "3盒装"]
b = [i for i in its if i["sku"] == "1盒装"]
check("详情含真实商品", len(a) == 1 and len(b) == 1, (len(a), len(b)))
a = a[0]; b = b[0]
check("详情A markup=5", a.get("markup_pct") == 5.0, a.get("markup_pct"))
check("详情A daifa_price=68.15", abs(float(a.get("daifa_price", 0)) - 64.9 * 1.05) < 0.02, a.get("daifa_price"))
check("详情B daifa_price=120", abs(float(b.get("daifa_price", 0)) - 120.0) < 0.01, b.get("daifa_price"))

# 重新下载还原上浮
st, xls2 = http("GET", f"/api/plan/{pid}/download", TOKEN)
ws2 = load_workbook(io.BytesIO(xls2)).active
check("重下A 一件代发价=68.15", abs(float(ws2.cell(3, 9).value) - 64.9 * 1.05) < 0.02, ws2.cell(3, 9).value)
check("重下A 毛利率", abs(float(str(ws2.cell(3, 11).value).replace('%', '')) - exp_m1) < 0.1, ws2.cell(3, 11).value)

# 公域不受影响（不传 markup 也不崩）
st, xpub = http("POST", "/api/plan/generate", TOKEN, {
    "name": "v72公域回归", "plan_type": "public", "commission_cut": 0, "items": ITEMS})
wsp = load_workbook(io.BytesIO(xpub)).active
check("公域仍正常(row1表头)", wsp.cell(1, 1).value == "序号")

# 清理
for nm in ("v72冒烟-上浮", "v72公域回归"):
    st, plans = http("GET", "/api/plan/list", TOKEN)
    for p in [x for x in plans if x["name"] == nm]:
        http("DELETE", f"/api/plan/{p['id']}", TOKEN)
check("清理", True)
print(f"\n==== v7.2 冒烟: {len(P)} PASS / {len(F)} FAIL ====")
if F:
    [print("  FAILED:", x) for x in F]; raise SystemExit(1)
