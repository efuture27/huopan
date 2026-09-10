# -*- coding: utf-8 -*-
"""端到端 HTTP 验证：登录 → 上传 WPS Excel → 验证响应"""
import io, json, time, urllib.request, uuid

BASE = "http://127.0.0.1:8000/api"
SRC = r"C:\Users\Administrator\Desktop\办公文件\云酥妃货盘表.xlsx"
OUT = r"E:\WorkBuddyData\WorkBuddy\2026-08-23-11-00-35\ai-huopan-demo\backend\_e2e_out.txt"
log = open(OUT, "w", encoding="utf-8")

def w(s): log.write(s + "\n"); log.flush()

# 1. 登录
fd = urllib.parse.urlencode({"username": "admin", "password": "admin123"}).encode()
r = urllib.request.urlopen(urllib.request.Request(BASE + "/auth/login", data=fd, method="POST"), timeout=10)
token = json.loads(r.read())["access_token"]
w("login ok, token len=%d" % len(token))

# 2. 上传（multipart）
boundary = uuid.uuid4().hex
with open(SRC, "rb") as f:
    payload = f.read()
w("file bytes=%d" % len(payload))
body = (
    ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"huopan.xlsx\"\r\n"
     "Content-Type: application/octet-stream\r\n\r\n" % boundary).encode()
    + payload
    + ("\r\n--%s--\r\n" % boundary).encode()
)
req = urllib.request.Request(
    BASE + "/product/upload", data=body, method="POST",
    headers={
        "Content-Type": "multipart/form-data; boundary=%s" % boundary,
        "Authorization": "Bearer " + token,
    },
)
t0 = time.time()
r = urllib.request.urlopen(req, timeout=300)
resp = json.loads(r.read())
w("upload resp=%s elapsed=%.1fs" % (json.dumps(resp, ensure_ascii=False), time.time() - t0))

# 3. 商品列表抽查
req = urllib.request.Request(BASE + "/product/list", headers={"Authorization": "Bearer " + token})
rows = json.loads(urllib.request.urlopen(req, timeout=30).read())["rows"]
with_img = [x for x in rows if x["image_url"]]
w("list total=%d with_image=%d" % (len(rows), len(with_img)))
if with_img:
    w("sample: sku=%s name=%s img_prefix=%s img_len=%d"
      % (with_img[0]["sku"], with_img[0]["name"], with_img[0]["image_url"][:40], len(with_img[0]["image_url"])))
w("DONE")
log.close()
