# -*- coding: utf-8 -*-
"""桌面版 exe 冒烟测试：登录 + 各核心接口
用法：python _smoke_desktop.py [base_url]   默认 http://127.0.0.1:8088
"""
import json
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8088").rstrip("/")
PASS = FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {extra}")


def call(method, path, token=None, raw=False, data=None, ctype=None):
    headers = {}
    if token:
        headers["Authorization"] = "Bearer " + token
    if ctype:
        headers["Content-Type"] = ctype
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read()
            return r.status, body if raw else json.loads(body or b"{}")
    except urllib.error.HTTPError as e:
        body = e.read()
        if raw:
            return e.code, body
        try:
            return e.code, json.loads(body or b"{}")
        except Exception:
            return e.code, {"detail": body[:200].decode("utf-8", "ignore")}
    except Exception as e:  # noqa: BLE001
        return 0, {"detail": str(e)}


def login(u, p):
    body = f"username={u}&password={p}".encode()
    st, d = call("POST", "/api/auth/login", data=body, ctype="application/x-www-form-urlencoded")
    return (d or {}).get("access_token"), (d or {}).get("role")


print("== 桌面版冒烟测试 ==", BASE)
st, d = call("GET", "/api/health")
check("健康检查 /api/health", st == 200 and d.get("status") == "ok", str(d))

st, blob = call("GET", "/", raw=True)
check("首页 HTML 可访问（前端已打包）", st == 200 and b"<html" in blob.lower(), f"status={st}")

tok, role = login("admin", "admin123")
check("admin 登录", bool(tok) and role == "admin", f"role={role}")
tok2, role2 = login("huopan", "huopan123")
check("同事账号登录", bool(tok2) and role2 == "user", f"role={role2}")

st, d = call("GET", "/api/product/list", token=tok)
check("商品列表接口", st == 200 and "rows" in d, str(d)[:80])

st, d = call("GET", "/api/product/uploads", token=tok)
check("上传文件管理接口（v7.13）", st == 200 and "rows" in d, str(d)[:80])

st, blob = call("GET", "/api/product/template", token=tok, raw=True)
check("下载 18 列模板（openpyxl 可用）", st == 200 and blob[:2] == b"PK", f"status={st}")

st, d = call("GET", "/api/plan/list", token=tok)
check("货盘列表接口", st == 200, str(d)[:80])

st, d = call("POST", "/api/product/upload", token=tok2)
check("普通账号上传被拦截（403）", st == 403, f"status={st}")

print(f"\n结果: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
