# -*- coding: utf-8 -*-
"""v7 端到端验证：上传 18 列商品库 → 生成公域/私域两套货盘 → openpyxl 读回校验 → 重新下载 → 清空历史货盘。
仅用于开发环境验证，不影响生产数据（验证结束清空本次生成的货盘）。"""
import io
import json
import base64
import urllib.request
import urllib.error
import uuid

from openpyxl import Workbook, load_workbook
from PIL import Image

BASE = "http://127.0.0.1:8000"
PASSED = []
FAILED = []


def check(name, cond, detail=""):
    if cond:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(f"{name} {detail}")
        print(f"  FAIL  {name}  {detail}")


def http(method, path, token=None, data=None, headers=None, raw=None):
    req = urllib.request.Request(BASE + path, method=method)
    hdrs = dict(headers or {})
    if token:
        hdrs["Authorization"] = "Bearer " + token
    if raw is not None:
        hdrs["Content-Type"] = "application/json"
        req.data = json.dumps(data).encode() if isinstance(data, dict) else data
    elif data is not None:
        req.data = urllib.parse.urlencode(data).encode()
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    for k, v in hdrs.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
        ct = r.headers.get("Content-Type", "")
        return r.status, (json.loads(body) if "json" in ct else body)


import urllib.parse
from http.client import HTTPException as _HE  # noqa


def multipart_upload(path, token, field, filename, filebytes, extra=None):
    boundary = "----wb" + uuid.uuid4().hex
    buf = io.BytesIO()
    for k, v in (extra or {}).items():
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    buf.write(f"--{boundary}\r\n".encode())
    buf.write(f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode())
    buf.write(b"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n")
    buf.write(filebytes)
    buf.write(f"\r\n--{boundary}--\r\n".encode())
    req = urllib.request.Request(BASE + path, method="POST", data=buf.getvalue())
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, json.loads(r.read())


# ---------- 0. 造测试图片（红方块 PNG → data URL） ----------
img = Image.new("RGB", (80, 80), (220, 38, 38))
ib = io.BytesIO()
img.save(ib, format="PNG")
IMG_URL = "data:image/png;base64," + base64.b64encode(ib.getvalue()).decode()

# ---------- 1. 登录 ----------
print("== 1. 登录 ==")
st, login = http("POST", "/api/auth/login", data={"username": "admin", "password": "admin123"})
TOKEN = login["access_token"]
check("登录成功", st == 200 and TOKEN)

# ---------- 2. 构造 18 列上传表（含示例行 + 说明行，验证跳过逻辑） ----------
print("== 2. 上传 18 列商品库 ==")
wb = Workbook()
ws = wb.active
headers = ["产品名称", "产品图片", "规格", "机制", "成本价（出厂价）", "代发费",
           "商家", "分类", "产品类型", "配料表", "库存数量", "发货地", "发货时效",
           "保质期", "售后期", "市场价", "不发货地区", "卖点介绍"]
ws.append(headers)
ws.append(["示例商品（上传前删除本行）", "", "1x1", "1盒", 1, 0, "示例商家", "测试", "", "", "", "", "", "", "", "", "", ""])  # 应被跳过
ws.append(["云南普洱袋泡茶", IMG_URL, "12g×10袋/盒", "3盒装", 59.9, 5,
           "鑫多多农业", "茶饮", "袋泡茶", "普洱茶、滇橄榄、茉莉", 1000,
           "云南昆明", "48小时内发货", "12个月", "7天", "99/79", "新疆西藏", "先涩后甘·解腻回甘"])
ws.append(["石斛冻干粉", "", "3g×20瓶", "1盒装", 120, 0,
           "鑫多多农业", "滋补", "冻干粉", "铁皮石斛", 500,
           "云南普洱", "72小时内发货", "18个月", "7天", "299/259", "青海宁夏", "低温冻干锁鲜"])
xbuf = io.BytesIO()
wb.save(xbuf)
st, up = multipart_upload("/api/product/upload", TOKEN, "file", "v7test.xlsx", xbuf.getvalue(), {"merchant": ""})
check("上传成功", st == 200 and up.get("inserted") == 2, str(up))

st, plist = http("GET", "/api/product/list", token=TOKEN)
rows = {r["name"]: r for r in plist["rows"]}
a = rows.get("云南普洱袋泡茶")
b = rows.get("石斛冻干粉")
check("商品数=2（示例行被跳过）", len(plist["rows"]) == 2, f"n={len(plist['rows'])}")
check("A 规格解析", a and a["spec"] == "12g×10袋/盒", str(a and a["spec"]))
check("A 机制=sku", a and a["sku"] == "3盒装", str(a and a["sku"]))
check("A 成本价（出厂价）列", a and abs(a["cost_price"] - 59.9) < 0.001, str(a and a["cost_price"]))
check("A 新字段齐全", a and a["product_type"] == "袋泡茶" and a["origin"] == "云南昆明"
      and a["lead_time"] == "48小时内发货" and a["shelf_life"] == "12个月"
      and a["after_sales"] == "7天" and a["market_price"] == "99/79"
      and a["excluded_regions"] == "新疆西藏" and a["ingredients"].startswith("普洱茶")
      and a["remark"] == "先涩后甘·解腻回甘" and a["stock"] == "1000")
check("A 图片 data URL", a and str(a["image_url"]).startswith("data:image/png"))
check("B 解析", b and b["spec"] == "3g×20瓶" and b["cost_price"] == 120 and b["shipping_fee"] == 0)

# ---------- 3. 生成公域货盘（7 列） ----------
print("== 3. 生成公域货盘 ==")
def item_of(r, sale):
    return {"product_id": r["id"], "sku": r["sku"], "name": r["name"], "image_url": r["image_url"],
            "cost_price": r["cost_price"], "shipping_fee": r["shipping_fee"], "sale_price": sale,
            "pricing_mode": "price", "category": r["category"], "remark": r["remark"],
            "spec": r["spec"], "product_type": r["product_type"], "ingredients": r["ingredients"],
            "stock": r["stock"], "origin": r["origin"], "lead_time": r["lead_time"],
            "shelf_life": r["shelf_life"], "after_sales": r["after_sales"],
            "market_price": r["market_price"], "excluded_regions": r["excluded_regions"]}

pub_items = [item_of(a, 99), item_of(b, 199)]
# v7.4：佣金下调改为逐商品快照（前端「应用到全部」会把 plan 级值填进每件 items）
for it in pub_items: it["commission_cut"] = 3
st, pub_x = http("POST", "/api/plan/generate", token=TOKEN, raw=True,
                 data={"name": "v7公域验证货盘", "commission_cut": 3, "cost_mode": "daifa",
                       "plan_type": "public", "tax_rate": 0, "items": pub_items})
check("公域生成下载", st == 200 and len(pub_x) > 5000)

wbv = load_workbook(io.BytesIO(pub_x))
wsv = wbv.active
check("公域 sheet 名", wsv.title == "公域货盘", wsv.title)
hdr = [c.value for c in wsv[1]]
check("公域 8 列表头", hdr == ["序号", "产品名称", "产品图片", "规格", "机制", "卖点", "销售价", "佣金"], str(hdr))
c1 = wsv.cell(1, 1)
# openpyxl 回读 6 位色值会带 00/FF alpha 前缀，比较后 6 位
check("公域紫底白字", str(c1.fill.fgColor.rgb)[-6:] == "8B5CF6" and str(c1.font.color.rgb)[-6:] == "FFFFFF",
      f"{c1.fill.fgColor.rgb}/{c1.font.color.rgb}")
check("公域表头行高48", wsv.row_dimensions[1].height == 48, str(wsv.row_dimensions[1].height))
check("公域序号列宽9", wsv.column_dimensions["A"].width == 9, str(wsv.column_dimensions["A"].width))
row2 = [c.value for c in wsv[2]]
check("公域行1内容", row2[0] == 1 and row2[1] == "云南普洱袋泡茶" and row2[3] == "12g×10袋/盒"
      and row2[4] == "3盒装" and row2[5] == "先涩后甘·解腻回甘" and abs(row2[6] - 99) < 0.001, str(row2))
# 佣金: (99-64.9)/99*100=34.4444-3=31.4444 -> 31.4%
check("公域佣金计算", row2[7] == "31.4%", str(row2[7]))
row3 = [c.value for c in wsv[3]]
check("公域佣金计算 B", row3[7] == "36.7%", str(row3[7]))
check("公域图片内嵌", len(wsv._images) == 1, f"n={len(wsv._images)}")  # 仅商品 A 有图
check("公域无大标题行/分组行", wsv.max_row == 3, f"max_row={wsv.max_row}")

# ---------- 4. 生成私域货盘（22 列，税率 9%） ----------
print("== 4. 生成私域货盘 ==")
st, pri_x = http("POST", "/api/plan/generate", token=TOKEN, raw=True,
                 data={"name": "v7私域验证货盘", "commission_cut": 0, "cost_mode": "daifa",
                       "plan_type": "private", "tax_rate": 0.09, "items": pub_items})
check("私域生成下载", st == 200 and len(pri_x) > 5000)

wbv = load_workbook(io.BytesIO(pri_x))
wsv = wbv.active
check("私域 sheet 名", wsv.title == "私域货盘", wsv.title)
hdr = [c.value for c in wsv[1]]
EXP = ["序号", "产品类型", "产品名称", "产品图片", "配料表", "规格", "机制",
       "直播价", "一件代发价", "一件代发价（含税）", "毛利率（不含税）", "毛利率（含税）",
       "集采价", "集采价（含税）", "库存数量", "发货地", "发货时效", "保质期",
       "售后期", "市场价（线下/线上）", "不发货地区", "卖点介绍"]
check("私域 22 列表头", hdr == EXP, str(hdr))
yellow = {2, 3, 4, 5, 6, 7, 16, 17, 18, 19, 22}
y_ok = all(str(wsv.cell(1, i).fill.fgColor.rgb)[-6:] == "FFFF00" for i in yellow)
check("私域标黄列", y_ok)
row2 = [c.value for c in wsv[2]]
# A: daifa=64.9 tax=70.74 m1=34.4% m2=28.5% collect=59.9 collect_tax=65.29
check("私域行1价格体系", row2[7] == 99 and row2[8] == 64.9 and row2[9] == 70.74
      and row2[12] == 59.9 and row2[13] == 65.29, str(row2[7:14]))
check("私域行1毛利率", row2[10] == "34.4%" and row2[11] == "28.5%", f"{row2[10]}/{row2[11]}")
check("私域行1履约字段", row2[1] == "袋泡茶" and row2[4] == "普洱茶、滇橄榄、茉莉"
      and row2[5] == "12g×10袋/盒" and row2[6] == "3盒装" and row2[14] == "1000"
      and row2[15] == "云南昆明" and row2[16] == "48小时内发货" and row2[17] == "12个月"
      and row2[18] == "7天" and row2[19] == "99/79" and row2[20] == "新疆西藏"
      and row2[21] == "先涩后甘·解腻回甘", str(row2[14:22]))
row3 = [c.value for c in wsv[3]]
check("私域行2价格体系", row3[7] == 199 and row3[8] == 120 and row3[9] == 130.8
      and row3[10] == "39.7%" and row3[11] == "34.3%" and row3[12] == 120 and row3[13] == 130.8,
      str(row3[7:14]))
check("私域表头行高55", wsv.row_dimensions[1].height == 55, str(wsv.row_dimensions[1].height))
check("私域图片内嵌", len(wsv._images) == 1, f"n={len(wsv._images)}")  # 仅商品 A 有图
check("私域无大标题行", wsv.max_row == 3, f"max_row={wsv.max_row}")

# ---------- 5. 货盘列表/重新下载 ----------
print("== 5. 货盘列表与重新下载 ==")
st, plans = http("GET", "/api/plan/list", token=TOKEN)
by_name = {p["name"]: p for p in plans}
pp = by_name.get("v7公域验证货盘")
pr = by_name.get("v7私域验证货盘")
check("列表带 plan_type", pp and pp["plan_type"] == "public" and pr and pr["plan_type"] == "private", str(plans)[:200])
check("列表带税率", pr and abs(pr["tax_rate"] - 0.09) < 1e-6, str(pr and pr["tax_rate"]))
st, det = http("GET", f"/api/plan/{pr['id']}", token=TOKEN)
it0 = det["items"][0]
check("私域详情字段", it0["margin"] == 34.44 and it0["daifa_price"] == 64.9 and it0["collect_price"] == 59.9
      and it0["spec"] == "12g×10袋/盒", f"margin={it0.get('margin')}")
st, dl = http("GET", f"/api/plan/{pr['id']}/download", token=TOKEN)
wbv = load_workbook(io.BytesIO(dl))
wsv = wbv.active
check("重新下载=私域 22 列", wsv.title == "私域货盘" and wsv.max_column == 22, f"{wsv.title}/{wsv.max_column}")
row2 = [c.value for c in wsv[2]]
check("重新下载价格快照", row2[8] == 64.9 and row2[9] == 70.74 and row2[10] == "34.4%", str(row2[7:14]))
st, dl = http("GET", f"/api/plan/{pp['id']}/download", token=TOKEN)
wbv = load_workbook(io.BytesIO(dl))
wsv = wbv.active
check("重新下载=公域 8 列", wsv.title == "公域货盘" and wsv.max_column == 8, f"{wsv.title}/{wsv.max_column}")

# ---------- 6. 模板端点 ----------
print("== 6. 18 列导入模板 ==")
st, tpl = http("GET", "/api/product/template", token=TOKEN)
wbv = load_workbook(io.BytesIO(tpl))
wsv = wbv.active
hdr = [c.value for c in wsv[2]]
check("模板 18 列", len([h for h in hdr if h]) == 18 and hdr[0] == "产品名称" and hdr[4] == "成本价（出厂价）", str(hdr))
check("模板必填黄标", str(wsv.cell(2, 1).fill.fgColor.rgb)[-6:] == "FFFF00"
      and str(wsv.cell(2, 7).fill.fgColor.rgb)[-6:] in ("000000", "FFFFFF"), "")

# ---------- 7. 清空历史货盘（用户确认删除） ----------
print("== 7. 清空历史货盘 ==")
cleared = 0
for p in plans:
    st, _ = http("DELETE", f"/api/plan/{p['id']}", token=TOKEN)
    if st == 200:
        cleared += 1
st, plans = http("GET", "/api/plan/list", token=TOKEN)
check("历史货盘清空", len(plans) == 0, f"剩余 {len(plans)}，删除 {cleared}")

print("\n======== 结果 ========")
print(f"PASS: {len(PASSED)}  FAIL: {len(FAILED)}")
for f in FAILED:
    print("  FAILED:", f)
raise SystemExit(1 if FAILED else 0)
