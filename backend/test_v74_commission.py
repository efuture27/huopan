# -*- coding: utf-8 -*-
"""v7.4 冒烟：公域「逐商品佣金下调%」—— 每件 cut 不同 → Excel 佣金/落库快照/详情/重新下载全链路一致；
不传商品级 cut 时回退 plan 级 commission_cut；私域不受影响。"""
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
st, plans0 = http("GET", "/api/plan/list", TOKEN)
for p in [x for x in plans0 if x["name"] in ("v74冒烟-逐件cut", "v74私域回归")]:
    http("DELETE", f"/api/plan/{p['id']}", TOKEN)

# 公域两商品，逐商品 cut 不同（cost_mode 默认 daifa：成本口径=成本+代发费）：
# A(DB id1) cost59.9+fee5=64.9, 售129 → 利润率=(129-64.9)/129*100=49.69%；cut=3 → 佣金46.7%
# B(DB id2) cost120+fee0=120,  售260 → 利润率=(260-120)/260*100=53.85%；cut=10 → 佣金43.8%
ITEMS_PUB = [
    {"product_id": 1, "sku": "3盒装", "name": "云南普洱袋泡茶", "cost_price": 59.9, "shipping_fee": 5, "sale_price": 129, "commission_cut": 3},
    {"product_id": 2, "sku": "1盒装", "name": "石斛冻干粉", "cost_price": 120, "shipping_fee": 0, "sale_price": 260, "commission_cut": 10},
]
rateA = (129 - 64.9) / 129 * 100
rateB = (260 - 120) / 260 * 100

st, xls = http("POST", "/api/plan/generate", TOKEN, {
    "name": "v74冒烟-逐件cut", "plan_type": "public", "commission_cut": 0, "items": ITEMS_PUB})
ws = load_workbook(io.BytesIO(xls)).active
check("公域表头 row1", ws.cell(1, 1).value == "序号" and ws.cell(1, 8).value == "佣金")
check("A 佣金=利润率-3", abs(float(str(ws.cell(2, 8).value).replace('%', '')) - (rateA - 3)) < 0.1, ws.cell(2, 8).value)
check("B 佣金=利润率-10", abs(float(str(ws.cell(3, 8).value).replace('%', '')) - (rateB - 10)) < 0.1, ws.cell(3, 8).value)

# 落库快照 + 详情
st, plans = http("GET", "/api/plan/list", TOKEN)
pid = [p for p in plans if p["name"] == "v74冒烟-逐件cut"][0]["id"]
check("货盘已落库", pid is not None)
st, det = http("GET", f"/api/plan/{pid}", TOKEN)
its = {i["sku"]: i for i in det.get("items", [])}
check("详情A 佣金=46.7", abs(float(its["3盒装"]["commission"]) - (rateA - 3)) < 0.1, its["3盒装"]["commission"])
check("详情B 佣金=43.8", abs(float(its["1盒装"]["commission"]) - (rateB - 10)) < 0.1, its["1盒装"]["commission"])

# 重新下载还原逐商品 cut
st, xls2 = http("GET", f"/api/plan/{pid}/download", TOKEN)
ws2 = load_workbook(io.BytesIO(xls2)).active
check("重下A 佣金一致", abs(float(str(ws2.cell(2, 8).value).replace('%', '')) - (rateA - 3)) < 0.1, ws2.cell(2, 8).value)
check("重下B 佣金一致", abs(float(str(ws2.cell(3, 8).value).replace('%', '')) - (rateB - 10)) < 0.1, ws2.cell(3, 8).value)

# 优先级：商品级 cut 永远优先（未点「应用到全部」时商品级=0，即使 plan 级=2 也不套用——顶部输入只是批量填充源）
ITEMS_FALLBACK = [
    {"product_id": 1, "sku": "3盒装", "name": "云南普洱袋泡茶", "cost_price": 59.9, "shipping_fee": 5, "sale_price": 129},
]
st, xls3 = http("POST", "/api/plan/generate", TOKEN, {
    "name": "v74冒烟-逐件cut", "plan_type": "public", "commission_cut": 2, "items": ITEMS_FALLBACK})
ws3 = load_workbook(io.BytesIO(xls3)).active
check("商品级0优先于plan级2", abs(float(str(ws3.cell(2, 8).value).replace('%', '')) - rateA) < 0.1, ws3.cell(2, 8).value)

# 佣金下限 0：cut 99 → 佣金 0%
ITEMS_NEG = [
    {"product_id": 1, "sku": "3盒装", "name": "云南普洱袋泡茶", "cost_price": 59.9, "shipping_fee": 5, "sale_price": 129, "commission_cut": 99},
]
st, xls4 = http("POST", "/api/plan/generate", TOKEN, {
    "name": "v74冒烟-逐件cut", "plan_type": "public", "commission_cut": 0, "items": ITEMS_NEG})
ws4 = load_workbook(io.BytesIO(xls4)).active
check("超调佣金下限0", abs(float(str(ws4.cell(2, 8).value).replace('%', ''))) < 0.05, ws4.cell(2, 8).value)

# 私域不受影响（commission_cut 字段不干扰私域价格）
ITEMS_PRI = [
    {"product_id": 1, "sku": "3盒装", "name": "云南普洱袋泡茶", "cost_price": 59.9, "shipping_fee": 5,
     "sale_price": 129, "markup_pct": 5, "commission_cut": 3},
]
st, xpri = http("POST", "/api/plan/generate", TOKEN, {
    "name": "v74私域回归", "plan_type": "private", "tax_rate": 0.09, "items": ITEMS_PRI})
wsp = load_workbook(io.BytesIO(xpri)).active
check("私域一件代发价仍=68.15", abs(float(wsp.cell(2, 9).value) - 64.9 * 1.05) < 0.01, wsp.cell(2, 9).value)

# 清理
st, plans = http("GET", "/api/plan/list", TOKEN)
for p in [x for x in plans if x["name"] in ("v74冒烟-逐件cut", "v74私域回归")]:
    http("DELETE", f"/api/plan/{p['id']}", TOKEN)
check("清理", True)
print(f"\n==== v7.4 冒烟: {len(P)} PASS / {len(F)} FAIL ====")
if F:
    [print("  FAILED:", x) for x in F]; raise SystemExit(1)
