from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import io
import os
import re
import time
import urllib.parse
from .. import config
from ..database import get_db
from .. import models, security
from ..services.excel import parse_product_excel
from ..seed import seed_sample_products

router = APIRouter(prefix="/api/product", tags=["product"])


def serialize_product(r):
    return {
        "id": r.id,
        "sku": r.sku,
        "name": r.name,
        "merchant": r.merchant,
        "image_url": r.image_url,
        "cost_price": float(r.cost_price or 0),
        "shipping_fee": float(r.shipping_fee or 0) if r.shipping_fee is not None else 0.0,
        "category": r.category,
        "remark": r.remark,
        # v7 新增字段（私域 22 列货盘 / 公域规格列）
        "spec": getattr(r, "spec", None),
        "product_type": getattr(r, "product_type", None),
        "ingredients": getattr(r, "ingredients", None),
        "stock": getattr(r, "stock", None),
        "origin": getattr(r, "origin", None),
        "lead_time": getattr(r, "lead_time", None),
        "shelf_life": getattr(r, "shelf_life", None),
        "after_sales": getattr(r, "after_sales", None),
        "market_price": getattr(r, "market_price", None),
        "excluded_regions": getattr(r, "excluded_regions", None),
        "create_time": r.create_time.isoformat() if r.create_time else None,
    }


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    merchant: str = Form(default=""),
    db: Session = Depends(get_db),
    user: str = Depends(security.require_admin),
):
    """§6 上传商品库 Excel → openpyxl 解析 → 写 PostgreSQL product 表。
    商家优先级：手动填写（merchant 表单字段）> Excel「商家」列 > 标题行/文件名自动识别。
    仅管理员可上传（商品库为团队共享数据，由管理员统一维护）。"""
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls 文件")
    data = await file.read()
    # 线程池执行解析：大文件（100MB+）openpyxl 解析耗时 15-60s，避免阻塞事件循环
    try:
        prods = await run_in_threadpool(parse_product_excel, data, file.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析失败：{e}")
    if not prods:
        raise HTTPException(status_code=400, detail="未解析到有效商品，请检查表头字段")
    manual_merchant = (merchant or "").strip()
    if manual_merchant:
        for p in prods:
            p["merchant"] = manual_merchant
    final_merchant = (prods[0].get("merchant") or "").strip()
    # 替换式上传：同一事务内清空旧商品再插入，失败整体回滚
    try:
        db.query(models.Product).delete()
        for p in prods:
            db.add(models.Product(**p))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"写入数据库失败：{e}")
    # v7.13 存档原文件到 data/uploads/ + 写上传记录（先落盘，再在同一事务写记录）
    save_path = None
    try:
        ts = time.strftime("%Y%m%d_%H%M%S")
        safe_name = re.sub(r"[\\/:*?\"<>|]", "_", file.filename)
        save_path = os.path.join(config.UPLOAD_DIR, f"{ts}_{safe_name}")
        with open(save_path, "wb") as f:
            f.write(data)
        db.query(models.UploadedFile).update({models.UploadedFile.is_active: 0})
        db.add(models.UploadedFile(
            filename=file.filename, merchant=final_merchant or None,
            product_count=len(prods), file_size=len(data), file_path=save_path,
            is_active=1, uploaded_by=user,
        ))
        db.commit()
    except Exception:
        db.rollback()
        if save_path and os.path.exists(save_path):
            try: os.remove(save_path)
            except OSError: pass
    return {"ok": True, "inserted": len(prods), "merchant": final_merchant or "未识别"}


# ---- v7.13 上传文件管理 ----

def serialize_upload(r):
    return {
        "id": r.id,
        "filename": r.filename,
        "merchant": r.merchant,
        "product_count": r.product_count or 0,
        "file_size": r.file_size or 0,
        "is_active": bool(r.is_active),
        "uploaded_by": r.uploaded_by,
        "create_time": r.create_time.strftime("%Y-%m-%d %H:%M") if r.create_time else None,
    }


@router.get("/uploads")
def list_uploads(
    db: Session = Depends(get_db),
    user: str = Depends(security.get_current_user),
):
    """上传文件历史（所有人可看；恢复/删除仅管理员）。"""
    rows = db.query(models.UploadedFile).order_by(models.UploadedFile.id.desc()).all()
    return {"rows": [serialize_upload(r) for r in rows]}


@router.get("/uploads/{fid}/download")
def download_upload(
    fid: int,
    db: Session = Depends(get_db),
    user: str = Depends(security.get_current_user),
):
    rec = db.query(models.UploadedFile).filter_by(id=fid).first()
    if not rec:
        raise HTTPException(status_code=404, detail="记录不存在")
    if not rec.file_path or not os.path.exists(rec.file_path):
        raise HTTPException(status_code=404, detail="原文件已丢失，无法下载")
    return FileResponse(rec.file_path, filename=rec.filename,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def _load_file_into_products(data: bytes, filename: str, db: Session) -> str:
    """解析 Excel 并替换式写入商品库（上传/恢复共用）；失败抛 HTTPException，不动现有商品。"""
    try:
        prods = parse_product_excel(data, filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析失败：{e}")
    if not prods:
        raise HTTPException(status_code=400, detail="未解析到有效商品，请检查表头字段")
    try:
        db.query(models.Product).delete()
        for p in prods:
            db.add(models.Product(**p))
        db.query(models.UploadedFile).update({models.UploadedFile.is_active: 0})
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"写入数据库失败：{e}")
    return (prods[0].get("merchant") or "").strip()


@router.post("/uploads/{fid}/restore")
def restore_upload(
    fid: int,
    db: Session = Depends(get_db),
    user: str = Depends(security.require_admin),
):
    """v7.13 恢复：把某次上传的原文件重新载入商品库（替换现有商品），并标记为当前使用。"""
    rec = db.query(models.UploadedFile).filter_by(id=fid).first()
    if not rec:
        raise HTTPException(status_code=404, detail="记录不存在")
    if not rec.file_path or not os.path.exists(rec.file_path):
        raise HTTPException(status_code=404, detail="原文件已丢失，无法恢复")
    with open(rec.file_path, "rb") as f:
        data = f.read()
    merchant = _load_file_into_products(data, rec.filename, db)
    rec.is_active = 1
    db.commit()
    return {"ok": True, "inserted": rec.product_count, "merchant": merchant or rec.merchant or "未识别"}


@router.delete("/uploads/{fid}")
def delete_upload(
    fid: int,
    db: Session = Depends(get_db),
    user: str = Depends(security.require_admin),
):
    rec = db.query(models.UploadedFile).filter_by(id=fid).first()
    if not rec:
        raise HTTPException(status_code=404, detail="记录不存在")
    if rec.file_path and os.path.exists(rec.file_path):
        try: os.remove(rec.file_path)
        except OSError: pass
    db.delete(rec)
    db.commit()
    return {"ok": True}


@router.get("/list")
def list_products(
    merchant: str = "",
    db: Session = Depends(get_db),
    user: str = Depends(security.get_current_user),
):
    """§6 商品列表（可按商家筛选，返回去重商家清单便于前端下拉）。"""
    q = db.query(models.Product)
    m = (merchant or "").strip()
    if m:
        q = q.filter(models.Product.merchant == m)
    rows = q.order_by(models.Product.id.desc()).all()
    all_merchants = [
        r[0] for r in db.query(models.Product.merchant).filter(models.Product.merchant.isnot(None)).distinct().all()
        if r[0]
    ]
    return {"rows": [serialize_product(r) for r in rows], "merchants": sorted(all_merchants)}


@router.post("/sample")
def sample(
    db: Session = Depends(get_db),
    user: str = Depends(security.get_current_user),
):
    """初始化示例商品库（便于一键体验），返回新增条数。"""
    n = seed_sample_products(db)
    return {"ok": True, "inserted": n}


@router.get("/template")
def template(user: str = Depends(security.get_current_user)):
    """下载商品库导入模板（v7 18 列：6 必填标黄 + 12 选填，附示例行与填写说明）。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "商品库模板"
    # (列名, 是否必填) —— 必填 6 项：产品名称/产品图片/规格/机制/成本价/代发费
    headers = [
        ("产品名称", True), ("产品图片", True), ("规格", True), ("机制", True),
        ("成本价（出厂价）", True), ("代发费", True),
        ("商家", False), ("分类", False), ("产品类型", False), ("配料表", False),
        ("库存数量", False), ("发货地", False), ("发货时效", False), ("保质期", False),
        ("售后期", False), ("市场价", False), ("不发货地区", False), ("卖点介绍", False),
    ]
    ncol = len(headers)
    ws.append(["商品库导入模板（标黄=必填，其余选填；上传前请删除本说明行和示例行）"] + [""] * (ncol - 1))
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    t = ws.cell(1, 1)
    t.font = Font(bold=True, size=11, color="7C3AED")
    t.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 22
    # 表头行（第 2 行）：必填黄底
    ws.append([h for h, _ in headers])
    bottom = Border(bottom=Side(style="thin", color="D9D2F5"))
    for i, (_, req) in enumerate(headers, start=1):
        c = ws.cell(2, i)
        c.font = Font(bold=True)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if req:
            c.fill = PatternFill("solid", fgColor="FFFF00")
        c.border = bottom
    ws.row_dimensions[2].height = 24
    # 示例行（第 3 行）：解析端会自动跳过名称以「示例」开头的行
    ws.append([
        "示例商品（上传前删除本行）", "可填图片URL，留空自动生成占位图", "12g×10袋/盒", "3盒装",
        59.9, 5, "某某食品有限公司", "袋泡茶", "袋泡茶", "普洱茶、滇橄榄、茉莉",
        1000, "云南昆明", "48小时内发货", "12个月", "7天", "99/79", "新疆西藏", "先涩后甘·解腻回甘",
    ])
    ws.freeze_panes = "A3"
    widths = [24, 18, 14, 10, 16, 8, 20, 10, 10, 22, 10, 12, 14, 10, 8, 12, 12, 22]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = urllib.parse.quote("商品库导入模板.xlsx")
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fname}"},
    )
