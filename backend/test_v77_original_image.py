# -*- coding: utf-8 -*-
"""v7.7 冒烟：商品原图保留——导入存原图(image_original)+缩略图(image_url)；
生成货盘/重新下载嵌原图（xlsx 内 media 尺寸≈原图）；列表接口不带原图；旧商品（无原图）回退缩略图。"""
import io, json, os, sys, base64, sqlite3, zipfile, urllib.request, urllib.parse
from PIL import Image as PILImage
from openpyxl import load_workbook

BASE = "http://127.0.0.1:8000"
DB = r"E:\WorkBuddyData\WorkBuddy\2026-08-23-11-00-35\ai-huopan-demo\data\huopan.db"
P, F = [], []


def check(n, ok, d=""):
    (P if ok else F).append(n)
    print(("  PASS  " if ok else "  FAIL  ") + n + ("" if ok else "  " + str(d)))


def http(method, path, token=None, data=None, form=False, raw_ret=False):
    req = urllib.request.Request(BASE + path, method=method)
    if token: req.add_header("Authorization", "Bearer " + token)
    if data is not None:
        if form:
            req.data = urllib.parse.urlencode(data).encode(); req.add_header("Content-Type", "application/x-www-form-urlencoded")
        else:
            req.data = json.dumps(data).encode(); req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=120) as r:
        b = r.read(); ct = r.headers.get("Content-Type", "")
        if raw_ret: return r.status, b
        return r.status, (json.loads(b) if "json" in ct else b)


def make_png(size, color):
    """生成纯色 PNG bytes（噪点让体积真实）。"""
    img = PILImage.new("RGB", (size, size), color)
    for x in range(0, size, 7):
        for y in range(0, size, 7):
            img.putpixel((x, y), (255, 255, 255))
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return buf.getvalue()


st, lg = http("POST", "/api/auth/login", data={"username": "admin", "password": "admin123"}, form=True)
TOKEN = lg["access_token"]
check("登录", st == 200 and TOKEN)

# ── 造数：A 商品带原图 800px（约几百KB）+ 256px 缩略图；B 商品只有缩略图（旧数据形态）
orig_bytes = make_png(800, (200, 60, 60))
thumb_bytes = make_png(256, (200, 60, 60))
du = lambda b, m="image/png": "data:%s;base64,%s" % (m, base64.b64encode(b).decode("ascii"))
con = sqlite3.connect(DB)
con.execute("DELETE FROM product WHERE sku IN ('v77A', 'v77B')")
con.execute(
    "INSERT INTO product (sku, name, merchant, image_url, image_original, cost_price, shipping_fee, category) VALUES (?,?,?,?,?,?,?,?)",
    ("v77A", "v77原图商品", "v77测试", du(thumb_bytes), du(orig_bytes), 59.9, 5, "测试"))
con.execute(
    "INSERT INTO product (sku, name, merchant, image_url, image_original, cost_price, shipping_fee, category) VALUES (?,?,?,?,?,?,?,?)",
    ("v77B", "v77旧商品", "v77测试", du(thumb_bytes), None, 120, 0, "测试"))
con.commit()
pa = con.execute("SELECT id FROM product WHERE sku='v77A'").fetchone()[0]
pb = con.execute("SELECT id FROM product WHERE sku='v77B'").fetchone()[0]
con.close()
check("造数完成 A(id=%d) B(id=%d)" % (pa, pb), True)

# ── 1. 列表接口不带 image_original（payload 轻）
st, lst = http("GET", "/api/product/list", TOKEN)
rowA = [r for r in lst["rows"] if r["sku"] == "v77A"][0]
check("列表不含 image_original 键", "image_original" not in rowA)
check("列表 image_url 仍是缩略图", rowA["image_url"] == du(thumb_bytes))

# ── 2. 生成公域货盘（A+B）→ xlsx 内嵌图：A=原图、B=缩略图
st, plans0 = http("GET", "/api/plan/list", TOKEN)
for p in [x for x in plans0 if x["name"] == "v77原图冒烟"]:
    http("DELETE", "/api/plan/%d" % p["id"], TOKEN)
items = [
    {"product_id": pa, "sku": "v77A", "name": "v77原图商品", "image_url": du(thumb_bytes),
     "cost_price": 59.9, "shipping_fee": 5, "sale_price": 129, "pricing_mode": "price", "commission_cut": 0},
    {"product_id": pb, "sku": "v77B", "name": "v77旧商品", "image_url": du(thumb_bytes),
     "cost_price": 120, "shipping_fee": 0, "sale_price": 260, "pricing_mode": "price", "commission_cut": 0},
]
st, xls = http("POST", "/api/plan/generate", TOKEN, data={
    "name": "v77原图冒烟", "plan_type": "public", "commission_cut": 0, "cost_mode": "daifa", "items": items}, raw_ret=True)
check("生成货盘成功", st == 200 and len(xls) > 5000, "len=%d" % len(xls))

zf = zipfile.ZipFile(io.BytesIO(xls))
media = [n for n in zf.namelist() if n.startswith("xl/media/")]
check("xlsx 内嵌 2 张图", len(media) == 2, str(media))
sizes = sorted(zf.getinfo(m).file_size for m in media)
# A 原图 800px 应明显大于 B 缩略图 256px
check("嵌图为原图(A=%dB≈原图%dB)" % (sizes[1], len(orig_bytes)), abs(sizes[1] - len(orig_bytes)) < len(orig_bytes) * 0.5, str(sizes))
check("B 回退缩略图(%dB)" % sizes[0], sizes[0] < len(orig_bytes) * 0.5, str(sizes))
wsv = load_workbook(io.BytesIO(xls)).active
check("公域 8 列表头不变", [c.value for c in wsv[1]] == ["序号", "产品名称", "产品图片", "规格", "机制", "卖点", "销售价", "佣金"])

# ── 3. 重新下载也嵌原图
st, plans = http("GET", "/api/plan/list", TOKEN)
pid = [p for p in plans if p["name"] == "v77原图冒烟"][0]["id"]
st, xls2 = http("GET", "/api/plan/%d/download" % pid, TOKEN, raw_ret=True)
zf2 = zipfile.ZipFile(io.BytesIO(xls2))
media2 = [n for n in zf2.namelist() if n.startswith("xl/media/")]
sizes2 = sorted(zf2.getinfo(m).file_size for m in media2)
check("重下嵌原图(A=%dB)" % sizes2[1], abs(sizes2[1] - len(orig_bytes)) < len(orig_bytes) * 0.5, str(sizes2))

# ── 4. 回归：私域生成不受影响（嵌图同样原图）
st, xpri = http("POST", "/api/plan/generate", TOKEN, data={
    "name": "v77原图冒烟私域", "plan_type": "private", "tax_rate": 0.09, "items": items}, raw_ret=True)
zfp = zipfile.ZipFile(io.BytesIO(xpri))
mediap = [n for n in zfp.namelist() if n.startswith("xl/media/")]
sizesp = sorted(zfp.getinfo(m).file_size for m in mediap)
check("私域嵌原图(%dB)" % sizesp[1], len(sizesp) == 2 and abs(sizesp[1] - len(orig_bytes)) < len(orig_bytes) * 0.5, str(sizesp))

# ── 清理
for nm in ("v77原图冒烟", "v77原图冒烟私域"):
    st, plans = http("GET", "/api/plan/list", TOKEN)
    for p in [x for x in plans if x["name"] == nm]:
        http("DELETE", "/api/plan/%d" % p["id"], TOKEN)
con = sqlite3.connect(DB)
con.execute("DELETE FROM product WHERE sku IN ('v77A','v77B')")
con.commit(); con.close()
check("清理", True)
print(f"\n==== v7.7 冒烟: {len(P)} PASS / {len(F)} FAIL ====")
if F:
    [print("  FAILED:", x) for x in F]; sys.exit(1)
