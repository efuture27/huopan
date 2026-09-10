import urllib.request, urllib.parse, json, sys

BASE = "http://127.0.0.1:8000"

def post(path, data=None, headers=None, raw=None):
    url = BASE + path
    if raw is not None:
        req = urllib.request.Request(url, data=raw, headers=headers or {}, method="POST")
    else:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode() if data else None,
                                     headers=headers or {}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

def get(path, headers=None):
    req = urllib.request.Request(BASE + path, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

# 1. health
s, b = get("/api/health"); print("health:", s, b.decode())

# 2. login
s, b = post("/api/auth/login", data={"username": "admin", "password": "admin123"})
print("login:", s)
token = json.loads(b)["access_token"]
H = {"Authorization": "Bearer " + token}

# 3. sample
s, b = post("/api/product/sample", headers=H); print("sample:", s, b.decode())

# 4. list
s, b = get("/api/product/list", H); rows = json.loads(b)["rows"]; print("list:", s, "count=", len(rows))

# 5. calculate
s, b = post("/api/profit/calculate", raw=json.dumps({"cost":80,"sale_price":199}).encode(),
            headers={"Content-Type":"application/json"}); print("calc:", s, b.decode())

# 6. price
s, b = post("/api/profit/price", raw=json.dumps({"cost":80,"target_rate":0.6}).encode(),
            headers={"Content-Type":"application/json"}); print("price:", s, b.decode())

# 7. generate plan
items = [{"sku": r["sku"], "name": r["name"], "image_url": r.get("image_url") or "",
          "cost_price": float(r["cost_price"]), "sale_price": round(float(r["cost_price"])*2.5,2),
          "pricing_mode":"price", "category": r.get("category") or "其他"} for r in rows[:3]]
s, b = post("/api/plan/generate", raw=json.dumps({"name":"测试货盘","items":items}).encode(),
            headers={**H, "Content-Type":"application/json"}); 
print("generate:", s, "bytes=", len(b))
with open("test_plan_http.xlsx","wb") as f: f.write(b)

# 8. static index
s, b = get("/"); print("index:", s, "hasAppDiv=", ("id=\"app\"" in b.decode()))

print("HTTP_TEST_DONE")
