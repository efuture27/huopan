import io
import os
import re
import base64
import zipfile
import posixpath
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from openpyxl import load_workbook, Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from PIL import Image as PILImage

# 商品库 Excel 列名映射（对齐 §4.1 字段）
# 成本列优先级：一件代发价格 → 普票含税价 → 直播价 → 出厂价（云南鑫多多/古风实业等私域货盘常见命名）
# v7：sku 别名 = 机制（货盘「机制」列取 SKU 值）；「规格」独立为新字段 spec，不再归入 sku
COLUMN_MAP = [
    ("image_url", ["图片", "图片示例", "商品图片", "产品图片", "产品包装图",
                   "图片链接", "图片地址", "主图", "商品主图", "image", "image_url"]),
    ("sku", ["sku", "SKU", "货号", "编码", "机制", "售卖机制", "机制/sku"]),
    ("name", ["商品名称", "名称", "品名", "产品明细", "产品名", "产品名称", "name"]),
    ("merchant", ["商家", "商家名称", "供应商", "供货商", "厂家", "merchant", "supplier"]),
    ("cost_price", ["成本价", "成本", "成本价（出厂价）", "成本价(出厂价)", "一件代发价格", "一件代发价", "普票含税价", "直播价",
                    "合计单价", "合计单价（出厂价）", "出厂价", "cost_price", "cost"]),
    ("shipping_fee", ["代发费用", "快递代发费用", "代发费", "快递费", "一件代发费", "shipping_fee"]),
    ("daifa_total", ["合计", "代发合计", "一件代发总价"]),
    ("category", ["分类", "category", "类目"]),
    ("remark", ["备注", "remark", "卖点", "商品卖点", "卖点介绍", "描述", "商品描述"]),
    ("product_type", ["产品类型", "类型", "产品类别"]),
    ("ingredients", ["配料表", "配料", "成分表", "配料成分"]),
    ("spec", ["规格", "规格型号", "产品规格", "包装规格"]),
    ("stock", ["库存数量", "库存", "现货数量", "库存量"]),
    ("origin", ["发货地", "发货地区", "发货仓库", "仓库所在地", "产地"]),
    ("lead_time", ["发货时效", "发货时间", "发货周期"]),
    ("shelf_life", ["保质期", "保质期限"]),
    ("after_sales", ["售后期", "售后服务", "售后期限", "售后"]),
    ("market_price", ["市场价", "市场价（线下/线上）", "市场价(线下/线上)", "市场参考价", "日常价", "划线价"]),
    ("excluded_regions", ["不发货地区", "不发货区域", "禁发地区", "不发货省"]),
    ("seq", ["序号", "编号", "行号"]),
]


def _norm(h):
    return str(h).strip().lower()


# WPS 单元格内嵌图片公式：=DISPIMG("ID_XXX",1)
_DISPIMG_RE = re.compile(r'DISPIMG\s*\(\s*"([^"]+)"', re.IGNORECASE)


def _local_name(tag):
    """去掉 XML 命名空间前缀，返回 local name（兼容不同 WPS 版本的前缀写法）。"""
    return tag.split("}")[-1]


def _attribs_local(el):
    """把带命名空间的属性 key 归一化为 local name（r:embed → embed）。"""
    return {k.split("}")[-1]: v for k, v in el.attrib.items()}


def _compress_image(raw: bytes):
    """Pillow 压缩单图，返回 (bytes, mime)；失败返回 None。
    目标单图 ≤ ~30KB：thumbnail 256px；有透明通道走 PNG（超限再降色），
    无透明走 JPEG（quality 70，超限降 60）。导出端嵌图 54x54 有充足冗余。"""
    try:
        img = PILImage.open(io.BytesIO(raw))
        img.load()
        has_alpha = img.mode in ("RGBA", "LA", "P")
        if has_alpha:
            alpha = img.convert("RGBA").getchannel("A")
            has_alpha = alpha.getextrema()[0] < 255  # 实际存在透明像素
        img.thumbnail((256, 256), PILImage.LANCZOS)
        if has_alpha:
            img = img.convert("RGBA")
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            if buf.tell() > 30 * 1024:
                try:
                    img = img.quantize(colors=128, method=PILImage.FASTOCTREE)
                    buf = io.BytesIO()
                    img.save(buf, format="PNG", optimize=True)
                except Exception:
                    pass
            return buf.getvalue(), "image/png"
        img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70, optimize=True)
        if buf.tell() > 30 * 1024:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=60, optimize=True)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return None


def _extract_wps_images(data: bytes) -> dict:
    """提取 WPS 单元格内嵌图片（DISPIMG 机制）。
    解析链路：xl/cellimages.xml（ID→rId）→ xl/_rels/cellimages.xml.rels（rId→media 路径）
    → 读图片 bytes → 双份 data URL：original=原图不压缩（生成货盘嵌图用）、thumb=256px 压缩（列表展示用）。
    普通 Excel（无 cellimages.xml）或任何异常 → 返回 {}，不阻断商品解析。"""
    out = {}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
            if "xl/cellimages.xml" not in names:
                return {}
            # ① cellimages.xml：ID → rId
            root = ET.fromstring(zf.read("xl/cellimages.xml"))
            id2rid = {}
            for el in root.iter():
                if _local_name(el.tag) != "cellImage":
                    continue
                img_id, rid = None, None
                for sub in el.iter():
                    ln = _local_name(sub.tag)
                    if ln == "cNvPr" and sub.get("name"):
                        img_id = sub.get("name")
                    elif ln == "blip":
                        embed = _attribs_local(sub).get("embed")
                        if embed:
                            rid = embed
                if img_id and rid:
                    id2rid[img_id] = rid
            if not id2rid:
                return {}
            # ② rels：rId → zip 内 media 路径
            rid2path = {}
            for rel in ET.fromstring(zf.read("xl/_rels/cellimages.xml.rels")):
                if _local_name(rel.tag) != "Relationship":
                    continue
                if rel.get("TargetMode") == "External":
                    continue
                target = rel.get("Target") or ""
                path = posixpath.normpath("xl/" + target.lstrip("/"))
                rid2path[rel.get("Id")] = path
            # ③ 图片本体 → 双份 data URL（原图 + 压缩缩略图）
            for img_id, rid in id2rid.items():
                path = rid2path.get(rid)
                if not path or path not in names:
                    continue
                raw = zf.read(path)
                # 原图：仅当格式是 openpyxl 可嵌入的 PNG/JPEG/GIF/BMP 才保留，否则导出端无法嵌
                orig = None
                try:
                    fmt = PILImage.open(io.BytesIO(raw)).format or ""
                    if fmt.upper() in ("PNG", "JPEG", "GIF", "BMP"):
                        mime = "image/png" if fmt.upper() == "PNG" else (
                            "image/jpeg" if fmt.upper() == "JPEG" else
                            "image/gif" if fmt.upper() == "GIF" else "image/bmp")
                        orig = "data:%s;base64,%s" % (mime, base64.b64encode(raw).decode("ascii"))
                except Exception:
                    orig = None
                comp = _compress_image(raw)
                if comp:
                    b, mime = comp
                    thumb = "data:%s;base64,%s" % (mime, base64.b64encode(b).decode("ascii"))
                    out[img_id] = {"original": orig, "thumb": thumb}
                elif orig:
                    out[img_id] = {"original": orig, "thumb": orig}
    except Exception:
        return {}
    return out


def _cell_image_map(ws, img_col_0based):
    """提取 Office Excel 普通「插入图片」（浮动图片）并按锚点单元格定位。
    返回：{(row_0based, col_0based): {"thumb": thumb_data_url, "original": original_data_url}}
    仅取锚点左上角落在图片列（img_col_0based）的图片；异常时返回空 dict，不阻断解析。"""
    out = {}
    if img_col_0based is None:
        return out
    try:
        for img in ws._images:
            anchor = img.anchor
            from_col = getattr(getattr(anchor, "_from", None), "col", None)
            from_row = getattr(getattr(anchor, "_from", None), "row", None)
            if from_col is None or from_row is None or from_col != img_col_0based:
                continue
            ref = getattr(img, "ref", None)
            if not ref or not hasattr(ref, "read"):
                continue
            ref.seek(0)
            raw = ref.read()
            ref.seek(0)
            if not raw:
                continue
            # 原图 data URL（仅保留 openpyxl 可嵌入的格式，否则导出会失败）
            fmt = "png"
            try:
                pimg = PILImage.open(io.BytesIO(raw))
                fmt = (pimg.format or "PNG").lower()
            except Exception:
                pass
            if fmt not in ("png", "jpeg", "jpg", "gif", "bmp"):
                continue
            mime_map = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg",
                        "gif": "image/gif", "bmp": "image/bmp"}
            mime = mime_map.get(fmt, "image/png")
            orig = "data:%s;base64,%s" % (mime, base64.b64encode(raw).decode("ascii"))
            # 缩略图：256px 压缩，用于列表展示
            comp = _compress_image(raw)
            if comp:
                b, _ = comp
                thumb = "data:image/jpeg;base64,%s" % base64.b64encode(b).decode("ascii")
                out[(from_row, from_col)] = {"original": orig, "thumb": thumb}
            else:
                out[(from_row, from_col)] = {"original": orig, "thumb": orig}
    except Exception:
        pass
    return out


def _detect_header_row(ws):
    """在前 N 行内自动定位表头行：命中已知别名最多的行即视为表头。
    解决云南鑫多多等文件表头不在第 1 行（前有标题/副标题）的问题。"""
    max_scan = min(ws.max_row, 20)
    known = {a.lower() for _, aliases in COLUMN_MAP for a in aliases}
    best_row, best_hits = 1, -1
    for r in range(1, max_scan + 1):
        hits = 0
        for c in ws[r]:
            if c.value is not None and _norm(c.value) in known:
                hits += 1
        if hits > best_hits:
            best_hits, best_row = hits, r
    return best_row


# 商家识别关键词：标题行/文件名中命中即认为是商家/供应商名称
_MERCHANT_HINT_RE = re.compile(r"(公司|商行|供应链|供货|工厂|旗舰店|农业|贸易|商贸|食品|生物科技)")
# 文件名清理：去掉扩展名和「货盘/商品库」类后缀词
_FNAME_CLEAN_RE = re.compile(r"[\(（\[【].*?[\)）\]】]|\.xlsx?$|货盘表?|商品库|含税|更新|总$|报价$|报价单|价目表|产品目录|系列产品|目录$", re.IGNORECASE)
# 标题行（Excel 内）商家清理：只去尾部杂质词，保留公司名括号（如「古风（云南）实业」）
_TITLE_CLEAN_RE = re.compile(r"货盘表?|商品库|含税|更新|报价$|报价单|价目表|产品目录|系列产品|目录$|系列$")


def _detect_merchant(ws, header_row, filename=""):
    """三层商家识别（返回 "" 表示未识别）：
    ① 表头上方的标题行：命中公司/商行等关键词的长文本（如「云南鑫多多农业科技有限公司私域货盘」）
    ② 表头后第一行数据之外的副标题（部分表在表头上留有商家行）
    ③ 文件名兜底：去掉扩展名和「货盘/含税/更新」等词"""
    # ① 标题行
    for r in range(1, header_row):
        for c in ws[r]:
            v = c.value
            if isinstance(v, str):
                s = v.strip().replace("\n", "")
                if 4 <= len(s) <= 60 and _MERCHANT_HINT_RE.search(s):
                    prev = None
                    while prev != s:
                        prev = s
                        s = _TITLE_CLEAN_RE.sub("", s).strip()
                    if s:
                        return s
    # ③ 文件名兜底
    if filename:
        s = filename.strip()
        prev = None
        while prev != s:
            prev = s
            s = _FNAME_CLEAN_RE.sub("", s).strip()
        if 2 <= len(s) <= 60:
            return s
    return ""


def parse_product_excel(data: bytes, filename: str = ""):
    """§4.1 解析商品库 Excel（对应后端 openpyxl）。
    filename 用于商家兜底识别（文件名常含商家名）。"""
    wps_images = _extract_wps_images(data)  # WPS 内嵌图片 ID→data URL；普通 Excel 返回 {}
    wb = load_workbook(io.BytesIO(data), data_only=True)
    ws = wb.active
    # 合并单元格前向填充：WPS 报价表常按商品合并名称列（如 B4:B5），被合并单元格值为 None
    # 会导致多规格行被跳过；将左上角值复制到整个区域
    for rng in list(ws.merged_cells.ranges):
        top_left = ws.cell(rng.min_row, rng.min_col).value
        if top_left is None:
            continue
        ws.unmerge_cells(str(rng))
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                ws.cell(r, c).value = top_left
    header_row = _detect_header_row(ws)
    # 商家识别：标题行 → 文件名兜底（若 Excel 里有「商家」列则按行取值，优先于全局识别）
    detected_merchant = _detect_merchant(ws, header_row, filename)
    headers = [c.value for c in ws[header_row]]
    idx = {}
    for field, aliases in COLUMN_MAP:
        for i, h in enumerate(headers):
            if h is None:
                continue
            if _norm(h) in [a.lower() for a in aliases]:
                idx[field] = i
                break
    # 图片列兜底①：表头含「图」的列（其他字段别名均不含「图」，零误伤）
    if "image_url" not in idx:
        for i, h in enumerate(headers):
            if h is not None and "图" in _norm(h):
                idx["image_url"] = i
                break
    # 图片列兜底②：数据行里出现 DISPIMG 公式的列
    if "image_url" not in idx:
        for col in range(1, ws.max_column + 1):
            found = False
            for r in range(header_row + 1, min(header_row + 50, ws.max_row) + 1):
                v = ws.cell(r, col).value
                if isinstance(v, str) and "DISPIMG(" in v.upper():
                    idx["image_url"] = col - 1  # iter_rows 索引从 0 开始
                    found = True
                    break
            if found:
                break
    # Office Excel 普通浮动图片：按图片锚点定位到单元格，作为图片列兜底
    image_col = idx.get("image_url")
    cell_images = _cell_image_map(ws, image_col)
    products = []
    for row in ws.iter_rows(min_row=header_row + 1):
        vals = [c.value for c in row]
        rec = {f: (vals[i] if i < len(vals) else None) for f, i in idx.items()}
        name = str(rec.get("name") or "").strip()
        if not name:
            continue
        # 跳过模板自带的示例行 / 说明行（名称以「示例」开头或含删除提示）
        if name.startswith("示例") or "上传前删除" in name or "上传前请删除" in name:
            continue
        # SKU 缺失时回退：序号 / 名称派生，保证不丢数据
        sku = str(rec.get("sku") or "").strip()
        if not sku:
            seq = str(rec.get("seq") or "").strip()
            sku = seq or ("SKU-" + name)
        cost = rec.get("cost_price")
        try:
            cost = float(cost) if cost not in (None, "") else 0.0
        except (TypeError, ValueError):
            cost = 0.0
        # 代发费用：优先「代发费用」列；无该列时用「合计 − 成本价」兜底推导
        # （古风实业式报价表：合计 = 合计单价 + 代发费用）
        def _num(v):
            try:
                return float(v) if v not in (None, "") else 0.0
            except (TypeError, ValueError):
                return 0.0
        fee = _num(rec.get("shipping_fee"))
        if fee <= 0:
            total = _num(rec.get("daifa_total"))
            if total > cost > 0:
                fee = round(total - cost, 2)
        img = rec.get("image_url")
        img_original = None
        # Office Excel 浮动图片兜底：单元格值无有效图片时，取落在该单元格的图片
        row_0based = (row[0].row - 1) if row else None
        pair = cell_images.get((row_0based, image_col)) if (row_0based is not None and image_col is not None) else None
        if img is not None:
            s = str(img).strip()
            m = _DISPIMG_RE.search(s)
            if m:
                # WPS 内嵌图片：ID 命中清单 → 原图 + 压缩缩略图；未命中 → None
                pair = wps_images.get(m.group(1))
                if pair:
                    img = pair.get("thumb")
                    img_original = pair.get("original")
                else:
                    img = None
            elif not (s.startswith("data:") or s.startswith("http")):
                # 过滤其他非 URL/非 data 的内容；如果本行有 Office 浮动图片则 fallback
                img = None
        if not img and pair:
            img = pair.get("thumb")
            img_original = pair.get("original")
        # 商家：行内「商家/供应商」列优先，否则用全局识别结果
        merchant = str(rec.get("merchant") or "").strip() or detected_merchant

        def _clean_str(v):
            """文本字段清洗：None→""；Excel 数字 1000.0→"1000"（库存/市场价常带单位，保持字符串）。"""
            if v is None:
                return ""
            if isinstance(v, float) and v.is_integer():
                return str(int(v))
            return str(v).strip()

        products.append({
            "sku": sku,
            "name": name,
            "merchant": merchant or None,
            "image_url": str(img) if img else None,
            "image_original": img_original,
            "cost_price": cost,
            "shipping_fee": fee,
            "category": str(rec.get("category") or "其他").strip(),
            "remark": _clean_str(rec.get("remark")),
            # v7 新增字段（私域 22 列货盘 / 公域规格列）
            "product_type": _clean_str(rec.get("product_type")),
            "ingredients": _clean_str(rec.get("ingredients")),
            "spec": _clean_str(rec.get("spec")),
            "stock": _clean_str(rec.get("stock")),
            "origin": _clean_str(rec.get("origin")),
            "lead_time": _clean_str(rec.get("lead_time")),
            "shelf_life": _clean_str(rec.get("shelf_life")),
            "after_sales": _clean_str(rec.get("after_sales")),
            "market_price": _clean_str(rec.get("market_price")),
            "excluded_regions": _clean_str(rec.get("excluded_regions")),
        })
    # v7.11 去重保护：报价表常见「合并单元格展开」或「源表多行」，导致同名同 SKU 重复。
    # 按 (name, sku) 去重合并：完全相同的只留一条；空壳行与有效行合并为一条
    # （后续行的非空/非零字段补全到已有记录，不覆盖已有有效值）。
    dedup = {}
    order = []
    for p in products:
        key = (p["name"], p["sku"])
        if key not in dedup:
            dedup[key] = p
            order.append(key)
            continue
        prev = dedup[key]
        for f, v in p.items():
            if v in (None, "", 0, 0.0):
                continue
            if prev.get(f) in (None, "", 0, 0.0):
                prev[f] = v
    return [dedup[k] for k in order]


def _load_image_bytes(url):
    if not url:
        return None
    try:
        if url.startswith("data:"):
            _, b64 = url.split(",", 1)
            return base64.b64decode(b64)
        if url.startswith("http"):
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                return r.read()
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# v7：两套货盘 Excel 输出（列序/配色 1:1 复刻用户模板《公域货盘.xlsx》《私域货盘.xlsx》）
#   公域（7 列）：序号|产品名称|产品图片|规格|机制|销售价|佣金 —— 表头紫底白字，行高 48
#   私域（22 列）：完整报价表 —— 标黄列 FFFF00 / 价格体系列白底，表头行高 55
#   两套均：第 1 行直接是表头（无大标题行）、无商家分组、无运费规则行；图片 110px 内嵌
# ---------------------------------------------------------------------------

# 私域 22 列表头（与用户模板完全一致）
_PRIVATE_HEADERS = [
    "序号", "产品类型", "产品名称", "产品图片", "配料表", "规格", "机制",
    "直播价", "一件代发价", "一件代发价（含税）", "毛利率（不含税）", "毛利率（含税）",
    "集采价", "集采价（含税）", "库存数量", "发货地", "发货时效", "保质期",
    "售后期", "市场价（线下/线上）", "不发货地区", "卖点介绍",
]
# 私域标黄列（1-based）：产品类型/产品名称/产品图片/配料表/规格/机制/发货地/发货时效/保质期/售后期/卖点介绍
_PRIVATE_YELLOW_COLS = {2, 3, 4, 5, 6, 7, 16, 17, 18, 19, 22}
# 私域白底列（模板中 theme0 白色填充）：直播价/一件代发价含税/毛利率×2/集采价/集采价含税
_PRIVATE_WHITE_COLS = {8, 10, 11, 12, 13, 14}
# 私域列宽（模板显式列宽 + 未标注列的实用宽度）
_PRIVATE_WIDTHS = {1: 6, 2: 10, 3: 20, 4: 14, 5: 18, 6: 12, 7: 10, 8: 10,
                   9: 18.9, 10: 21.6, 11: 16.5, 12: 17.8, 13: 13.1, 14: 15.1,
                   15: 10, 16: 10, 17: 13, 18: 13.1, 19: 8, 20: 17.6, 21: 18.9, 22: 16.1}


def _put_product_image(ws, r_idx, col, img_bytes, tmp_files, size=110, fallback_bytes=None):
    """在指定单元格嵌入商品图片（默认 110px）；临时文件 save 后统一清理。
    v7.7：img_bytes 为原图（不压缩嵌入，放大不糊）；格式 openpyxl 不支持时回退 fallback_bytes（缩略图）。"""
    for data in (img_bytes, fallback_bytes):
        if not data:
            continue
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                tf.write(data)
                tmp = tf.name
            img = XLImage(tmp)
            img.width = size
            img.height = size
            ws.add_image(img, f"{get_column_letter(col)}{r_idx}")
            tmp_files.append(tmp)
            return
        except Exception:
            if tmp:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass


def _style_data_row(ws, r_idx, ncols, center_cols, border_color="E5E7EB"):
    """数据行统一细边框；指定列水平居中，其余左对齐自动换行。"""
    thin = Side(style="thin", color=border_color)
    for col in range(1, ncols + 1):
        cell = ws.cell(r_idx, col)
        cell.border = Border(top=thin, bottom=thin, left=thin, right=thin)
        if col in center_cols:
            cell.alignment = Alignment(horizontal="center", vertical="center")
        else:
            cell.alignment = Alignment(vertical="center", wrap_text=True)


def _save_workbook(wb, tmp_files):
    buf = io.BytesIO()
    try:
        wb.save(buf)
    finally:
        for tf in tmp_files:
            try:
                os.unlink(tf)
            except OSError:
                pass
    buf.seek(0)
    return buf


def _put_title_row(ws, ncols, text, font_color="000000"):
    """首行合并大标题（v7.1）：加粗 16 号居中，行高 34；表头由调用方写在下一行。"""
    ws.cell(1, 1, text)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    c = ws.cell(1, 1)
    c.font = Font(bold=True, size=16, color=font_color)
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 34


def _generate_public(items, commission_cut, cost_mode, fee_rate=0.0, tax_rate=0.0, title=""):
    """公域货盘（8 列，紫底表头）：v7.10 佣金 = (售价−成本−平台费−税费)/售价 − commission_cut，下限 0；
    v7.5 新增「卖点」列（取 remark，卖点介绍）。
    title 非空时首行写合并大标题，表头下移至第 2 行（freeze A3）。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "公域货盘"
    headers = ["序号", "产品名称", "产品图片", "规格", "机制", "卖点", "销售价", "佣金"]
    has_title = bool((title or "").strip())
    if has_title:
        _put_title_row(ws, len(headers), title.strip(), font_color="7C3AED")
    ws.append(headers)
    thin = Side(style="thin", color="D9D2F5")
    hrow = 2 if has_title else 1
    for c in ws[hrow]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="8B5CF6")
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = Border(top=thin, bottom=thin, left=thin, right=thin)
    ws.row_dimensions[hrow].height = 48
    ws.freeze_panes = f"A{hrow + 1}"

    tmp_files = []
    for i, it in enumerate(items, start=1):
        cost = float(it.get("cost_price") or 0)
        if cost_mode == "daifa":
            cost += float(it.get("shipping_fee") or 0)
        sale = float(it.get("sale_price") or 0)
        # v7.10：佣金基于扣减平台费、税费后的利润计算，与前端利润测算口径一致
        profit = sale - cost - sale * fee_rate - sale * tax_rate
        rate = (profit / sale * 100) if sale > 0 else 0
        # v7.4：逐商品佣金下调（每件可不同）；旧数据无商品级值 → 回退 plan 级 commission_cut
        cc = it.get("commission_cut")
        cut = float(cc) if cc is not None else float(commission_cut or 0)
        comm = max(0.0, rate - cut)
        remark = (it.get("remark") or "").strip()
        ws.append([i, it.get("name"), None, it.get("spec") or "", it.get("sku") or "",
                   remark, round(sale, 2), f"{comm:.1f}%"])
        r = ws.max_row
        ws.row_dimensions[r].height = 95 if len(remark) <= 22 else 130   # 卖点较多时加高行
        _style_data_row(ws, r, len(headers), center_cols={1, 3, 4, 5, 7, 8},
                        border_color="D9D2F5")
        _fb = it.get("image_thumb") if it.get("image_thumb") != it.get("image_url") else None
        _put_product_image(ws, r, 3, _load_image_bytes(it.get("image_url")), tmp_files,
                           fallback_bytes=_load_image_bytes(_fb))
    for col, w in {1: 9, 2: 26, 3: 14, 4: 13, 5: 13, 6: 34, 7: 11, 8: 10}.items():
        ws.column_dimensions[get_column_letter(col)].width = w
    return _save_workbook(wb, tmp_files)


def _generate_private(items, tax_rate, title=""):
    """私域货盘（22 列报价表）。
    价格体系（全部系统算）：集采价 = 成本价（出厂价）；一件代发价 = 成本价 + 代发费；
    含税价 = 不含税 × (1+tax_rate)；毛利率 = (直播价 − 一件代发价) / 直播价（一件代发口径）。
    title 非空时首行写合并大标题，表头下移至第 2 行（freeze A3）。"""
    tr = max(0.0, float(tax_rate or 0))
    wb = Workbook()
    ws = wb.active
    ws.title = "私域货盘"
    has_title = bool((title or "").strip())
    if has_title:
        _put_title_row(ws, len(_PRIVATE_HEADERS), title.strip(), font_color="000000")
    ws.append(_PRIVATE_HEADERS)
    yellow = PatternFill("solid", fgColor="FFFF00")
    white = PatternFill("solid", fgColor="FFFFFF")
    thin = Side(style="thin", color="E5E7EB")
    hrow = 2 if has_title else 1
    for idx, c in enumerate(ws[hrow], start=1):
        c.font = Font(bold=True, color="000000")
        if idx in _PRIVATE_YELLOW_COLS:
            c.fill = yellow
        elif idx in _PRIVATE_WHITE_COLS:
            c.fill = white
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = Border(top=thin, bottom=thin, left=thin, right=thin)
    ws.row_dimensions[hrow].height = 55
    ws.freeze_panes = f"A{hrow + 1}"

    tmp_files = []
    for i, it in enumerate(items, start=1):
        cost = float(it.get("cost_price") or 0)      # 集采价（出厂价，不含税）
        fee = float(it.get("shipping_fee") or 0)
        base = cost + fee                            # 一件代发成本（上浮前）
        mk = max(0.0, float(it.get("markup_pct") or 0)) / 100   # v7.2 上浮比例（5→0.05）
        daifa = base * (1 + mk)                      # 一件代发价（不含税，已上浮）
        daifa_tax = daifa * (1 + tr)                 # 一件代发价（含税）
        collect_tax = cost * (1 + tr)                # 集采价（含税）
        sale = float(it.get("sale_price") or 0)      # 直播价
        m1 = ((sale - daifa) / sale * 100) if sale > 0 else 0       # 毛利率（不含税）
        m2 = ((sale - daifa_tax) / sale * 100) if sale > 0 else 0   # 毛利率（含税）
        ws.append([
            i,
            it.get("product_type") or "",
            it.get("name"),
            None,
            it.get("ingredients") or "",
            it.get("spec") or "",
            it.get("sku") or "",
            round(sale, 2),
            round(daifa, 2),
            round(daifa_tax, 2),
            f"{m1:.1f}%",
            f"{m2:.1f}%",
            round(cost, 2),
            round(collect_tax, 2),
            it.get("stock") or "",
            it.get("origin") or "",
            it.get("lead_time") or "",
            it.get("shelf_life") or "",
            it.get("after_sales") or "",
            it.get("market_price") or "",
            it.get("excluded_regions") or "",
            it.get("remark") or "",
        ])
        r = ws.max_row
        ws.row_dimensions[r].height = 95
        _style_data_row(ws, r, 22, center_cols={1, 4, 7, 8, 9, 10, 11, 12, 13, 14, 15})
        _fb = it.get("image_thumb") if it.get("image_thumb") != it.get("image_url") else None
        _put_product_image(ws, r, 4, _load_image_bytes(it.get("image_url")), tmp_files,
                           fallback_bytes=_load_image_bytes(_fb))
    for col, w in _PRIVATE_WIDTHS.items():
        ws.column_dimensions[get_column_letter(col)].width = w
    return _save_workbook(wb, tmp_files)


def generate_plan_excel(items, plan_type="public", tax_rate=0.0, commission_cut=0.0, cost_mode="daifa", fee_rate=0.0, title=""):
    """v7 生成货盘 Excel——两套完全独立的形式，按 plan_type 二选一：
    - 'public'：公域货盘 7 列（表头紫底 8B5CF6，行高 48；v7.10 佣金 = (利润率−平台费−税费) − commission_cut）
    - 'private'：私域货盘 22 列报价表（标黄列 FFFF00，行高 55；价格体系全系统算，含税价按 tax_rate）
    title 非空时两套均首行写合并大标题（表头下移一行）；均无商家分组与运费规则行，图片 110px 内嵌。"""
    t = (title or "").strip()
    if (plan_type or "public").strip() == "private":
        return _generate_private(items, tax_rate, title=t)
    return _generate_public(items, commission_cut, cost_mode, fee_rate=fee_rate, tax_rate=tax_rate, title=t)
