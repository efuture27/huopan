import json
import os
import urllib.request

# §4.5 卖点库（mock 回退用）
POOL = {
    "上衣": ["亲肤透气面料", "修身显瘦版型", "基础百搭易衬", "通勤休闲两宜"],
    "裤装": ["高腰显腿长", "垂感顺滑不塌", "舒适无束缚", "修饰腿型利落"],
    "裙装": ["优雅气质拉满", "A字显瘦遮肉", "仙女氛围感", "垂坠有型"],
    "外套": ["挺括有型", "防风保暖", "气质叠穿利器", "质感高级"],
    "其他": ["性价比之选", "当季热推", "细节考究", "易搭配"],
}


def _extract_json(text: str):
    """从模型返回文本中提取 JSON 对象（兼容带 ```json 包裹或夹杂文本的情况）。"""
    if not text:
        return None
    s = text.strip()
    # 去掉 markdown 代码块包裹
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
    # 截取首个 { 到末个 }
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(s[start:end + 1])
    except Exception:
        return None


def _llm_cfg():
    """运行时读取环境变量，支持前端热更新配置。"""
    return (
        os.environ.get("LLM_BASE_URL", "").strip(),
        os.environ.get("LLM_API_KEY", "").strip(),
        os.environ.get("LLM_MODEL", "deepseek-chat").strip(),
    )


def _call_llm(items, default_title):
    """调用 OpenAI 兼容接口（Ollama / DeepSeek / Qwen / GPT 等）。"""
    base_url, api_key, model = _llm_cfg()
    lines = []
    for it in items:
        c = float(it.get("cost_price") or 0)
        p = float(it.get("sale_price") or 0)
        rate = (p - c) / p * 100 if p > 0 else 0
        lines.append(
            f"- SKU:{it.get('sku')} | 名称:{it.get('name','')} | 分类:{it.get('category','其他')} "
            f"| 成本价:{c} | 售价:{p} | 利润率:{round(rate,1)}% | 备注:{it.get('remark','')}"
        )
    goods = "\n".join(lines)

    prompt = (
        "你是资深电商货盘文案专家。基于以下商品信息，生成一份货盘方案。\n"
        "请仅输出一个 JSON 对象，结构如下（不要输出任何额外文字）：\n"
        '{"title": "货盘标题（10字以内，含品类与卖点）",'
        ' "items": { "<SKU>": {"desc": "该商品的30字内场景化描述",'
        ' "selling_points": ["卖点1","卖点2","卖点3"]} } }\n'
        "商品列表：\n" + goods
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是电商货盘文案专家，严格按请求格式返回 JSON"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.8,
    }
    url = base_url.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + (api_key or "ollama"),
        },
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"]
    parsed = _extract_json(content)
    if not parsed:
        raise ValueError("模型返回无法解析为 JSON")

    title = parsed.get("title") or default_title
    items_out = parsed.get("items", {})
    descriptions = {}
    selling_points = {}
    for it in items:
        sku = it.get("sku")
        block = items_out.get(sku) or {}
        desc = block.get("desc") or block.get("description") or ""
        sp = block.get("selling_points") or []
        if isinstance(sp, str):
            sp = [sp]
        descriptions[sku] = desc
        selling_points[sku] = " / ".join(sp)
    return {"title": title, "descriptions": descriptions, "selling_points": selling_points}


def generate_plan_content(items, plan_name=None):
    """
    §4.5 AI 货盘内容生成。
    配置了 LLM_BASE_URL 时调用真实模型（OpenAI 兼容）；失败自动回退规则 mock。
    """
    cats = [it.get("category") or "其他" for it in items]
    default_title = plan_name or f"{cats[0] if cats else '商品'}精选货盘 · 共{len(items)}款"

    base_url, _, _ = _llm_cfg()
    if base_url:
        try:
            return _call_llm(items, default_title)
        except Exception as e:
            print("[ai] LLM 调用失败，回退 mock：", repr(e))

    # ---- 规则 mock 回退 ----
    descriptions = {}
    selling_points = {}
    for i, it in enumerate(items):
        pool = POOL.get(it.get("category") or "其他", POOL["其他"])
        pick = [pool[i % len(pool)], pool[(i + 1) % len(pool)], pool[(i + 2) % len(pool)]]
        name = it.get("name", "商品")
        descriptions[it.get("sku")] = (
            f"【{name}】{it.get('category', '')}精选单品，{pick[0]}，{pick[1]}，"
            f"适配多场景穿搭，是当季高性价比之选。"
        )
        selling_points[it.get("sku")] = " / ".join(pick)

    return {"title": default_title, "descriptions": descriptions, "selling_points": selling_points}
