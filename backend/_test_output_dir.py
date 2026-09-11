"""v7.17 保存位置功能冒烟测试：生成 → 落盘 → 列表可见 → 重下覆盖 → 清理。

可用环境变量：
  HUOPAN_TEST_BASE  接口前缀（默认 http://127.0.0.1:8000/api，安装版验证时指到别的端口）
  HUOPAN_TEST_DIR   先改成这个自定义目录再测，结束时恢复默认
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = os.environ.get("HUOPAN_TEST_BASE", "http://127.0.0.1:8000/api").rstrip("/")
CUSTOM_DIR = (os.environ.get("HUOPAN_TEST_DIR") or "").strip()


def req(path, method="GET", body=None, token=None, raw=False):
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    # 绕过系统代理（local bypass 在沙箱里可能不生效）
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(r, timeout=30) as resp:
        if raw:
            return resp.headers, resp.read()
        return json.loads(resp.read().decode())


ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [OK] {name} {extra}")
    else:
        fail += 1
        print(f"  [FAIL] {name} {extra}")


# 1. 登录
fd = urllib.parse.urlencode({"username": "admin", "password": "admin123"}).encode()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(urllib.request.Request(
        BASE + "/auth/login", data=fd,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST"), timeout=20) as resp:
    tok = json.loads(resp.read().decode())["access_token"]
print("登录 OK")

# 2. 读导出配置
cfg = req("/output", token=tok)
print(f"接口 = {BASE}")
print(f"导出目录 = {cfg['dir']}  enabled={cfg['enabled']} is_local={cfg['is_local']}")
check("默认目录指向用户文档下的子目录", "Documents" in cfg["dir"] and cfg["dir"].endswith("货盘助手导出"), cfg["dir"])
check("默认开启自动保存", cfg["enabled"] is True)
check("本机请求标记 is_local", cfg["is_local"] is True)

# 2b. 可选：先切到自定义目录
if CUSTOM_DIR:
    cfg = req("/output", method="POST", body={"enabled": True, "dir": CUSTOM_DIR}, token=tok)
    print(f"已切到自定义目录 = {cfg['dir']}")
    check("自定义目录设置生效且被创建", os.path.normcase(cfg["dir"]) == os.path.normcase(CUSTOM_DIR) and os.path.isdir(CUSTOM_DIR), cfg["dir"])

# 3. 生成一个测试货盘
name = "冒烟测试_保存位置"
payload = {
    "name": name,
    "title": "",
    "commission_cut": 0,
    "cost_mode": "daifa",
    "plan_type": "public",
    "tax_rate": 0.09,
    "fee_rate": 0.06,
    "items": [{
        "product_id": None, "sku": "1瓶", "name": "测试商品A", "image_url": None,
        "cost_price": 10, "shipping_fee": 2, "sale_price": 39.9, "pricing_mode": "price",
        "category": "测试", "remark": "", "merchant": "测试商家", "markup_pct": 0, "commission_cut": 0,
    }],
}
h, blob = req("/plan/generate", method="POST", body=payload, token=tok, raw=True)
saved = urllib.parse.unquote(h.get("X-Saved-Path") or "")
print(f"响应头 X-Saved-Path = {saved}")
check("生成返回 Excel 字节流", len(blob) > 4000, f"{len(blob)} bytes")
check("响应头带回落盘路径", bool(saved))
check("文件确实落到磁盘", bool(saved) and os.path.isfile(saved), saved)
if saved and os.path.isfile(saved):
    check("落盘文件大小与下载流一致", os.path.getsize(saved) == len(blob),
          f"{os.path.getsize(saved)} vs {len(blob)}")

# 4. 列表里能看到保存位置
plans = req("/plan/list", token=tok)
rec = next((p for p in plans if p["name"] == name), None)
check("货盘记录已入库", rec is not None)
if rec:
    check("列表返回 saved_path", rec.get("saved_path") == saved, rec.get("saved_path"))
    check("saved_exists=True", rec.get("saved_exists") is True)

    # 5. 重新下载 → 应覆盖同一个文件，不产生 (1)
    time.sleep(1.1)
    before = os.path.getmtime(saved) if os.path.isfile(saved) else 0
    h2, blob2 = req(f"/plan/{rec['id']}/download", token=tok, raw=True)
    saved2 = urllib.parse.unquote(h2.get("X-Saved-Path") or "")
    check("重新下载也返回同一路径", saved2 == saved, saved2)
    check("重新下载是原地覆盖（mtime 变了）", os.path.getmtime(saved) > before)
    import glob
    dupes = glob.glob(os.path.join(os.path.dirname(saved), "冒烟测试_保存位置 (*).xlsx"))
    check("没有堆出 (1)(2) 副本", len(dupes) == 0, str(dupes))

# 6. 同名再生成一次 → 应自动加 (1)
h3, _ = req("/plan/generate", method="POST", body=payload, token=tok, raw=True)
saved3 = urllib.parse.unquote(h3.get("X-Saved-Path") or "")
check("重复文件名自动加 (1)", saved3 != saved and "(1)" in saved3, saved3)

# 7. 清理测试产物
for p in {saved, saved3}:
    try:
        if p and os.path.isfile(p):
            os.remove(p)
    except OSError as e:
        print("  清理文件失败:", e)
for p in req("/plan/list", token=tok):
    if p["name"] == name:
        req(f"/plan/{p['id']}", method="DELETE", token=tok)
left = [p for p in req("/plan/list", token=tok) if p["name"] == name]
check("测试货盘记录已清理", not left)

if CUSTOM_DIR:
    cfg = req("/output", method="POST", body={"enabled": True, "dir": ""}, token=tok)
    check("测试后已恢复默认目录", cfg["is_default"] is True, cfg["dir"])

print(f"\n结果：{ok} 通过 / {fail} 失败")
sys.exit(1 if fail else 0)
