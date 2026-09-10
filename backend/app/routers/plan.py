import urllib.parse
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas, security
from ..services.excel import generate_plan_excel

router = APIRouter(prefix="/api/plan", tags=["plan"])


def _num(v, default=0):
    try:
        return float(v or default)
    except (TypeError, ValueError):
        return default


@router.post("/generate")
def generate(
    req: schemas.PlanGenerateReq,
    db: Session = Depends(get_db),
    user: str = Depends(security.get_current_user),
):
    """v7 生成货盘（两套独立形式，按 plan_type 二选一）：
    - 公域（7 列）：佣金 = 利润率(按 cost_mode 成本) − commission_cut，下限 0；
      落库 profit_rate = 最终佣金快照。
    - 私域（22 列）：一件代发价 = 成本价+代发费；含税价 = 不含税 × (1+税率)；
      落库 profit_rate = 毛利率（不含税，一件代发口径）快照。"""
    file_name = (req.name or "").strip() or "货盘"   # 下载文件名 / 落库
    plan_title = (req.title or "").strip()           # v7.1 主标题：非空时写 Excel 首行大标题
    plan_type = "private" if (req.plan_type or "").strip() == "private" else "public"
    tax_rate = min(max(0.0, _num(req.tax_rate)), 1.0)  # 税率小数（0~1），如 0.09 = 9%
    fee_rate = min(max(0.0, _num(req.fee_rate)), 1.0)  # v7.10 平台服务费费率小数（0~1），如 0.06 = 6%
    cost_mode = "collect" if (req.cost_mode or "").strip() == "collect" else "daifa"
    commission_cut = max(0.0, _num(req.commission_cut))

    items = [it.model_dump() for it in req.items]

    # v7.7：优先用商品库「原图」嵌货盘（image_original 不压缩）；无原图回退请求里的缩略图
    prod_ids = [it.get("product_id") for it in items if it.get("product_id")]
    orig_map = {}
    if prod_ids:
        orig_map = {pr.id: (pr.image_original or pr.image_url)
                    for pr in db.query(models.Product).filter(models.Product.id.in_(prod_ids)).all()}
    for it in items:
        oid = orig_map.get(it.get("product_id"))
        if oid:
            it["image_thumb"] = it.get("image_url")   # 缩略图留作嵌图失败回退
            it["image_url"] = oid

    plan = models.ProductPlan(
        name=file_name, creator=user, title=plan_title,
        commission_cut=commission_cut, cost_mode=cost_mode,
        plan_type=plan_type, tax_rate=tax_rate, fee_rate=fee_rate,
    )
    db.add(plan)
    db.flush()

    for it in items:
        cost = _num(it.get("cost_price"))
        fee = _num(it.get("shipping_fee"))
        sale = _num(it.get("sale_price"))
        if plan_type == "private":
            # 私域：毛利率（不含税，一件代发口径）
            profit = sale - (cost + fee)
            rate = (profit / sale * 100) if sale > 0 else 0
            stored_rate = round(rate, 2)
        else:
            # 公域：v7.10 最终佣金 = (售价 − 成本 − 平台费 − 税费)/售价 − 逐商品 commission_cut（下限 0）
            if cost_mode == "daifa":
                cost += fee
            # 平台费/税费按售价比例扣减，与前端利润测算口径保持一致
            profit = sale - cost - sale * fee_rate - sale * tax_rate
            rate = (profit / sale * 100) if sale > 0 else 0
            cut_i = max(0.0, _num(it.get("commission_cut")))
            stored_rate = round(max(0.0, rate - cut_i), 2)
        db.add(models.ProductPlanItem(
            plan_id=plan.id,
            product_id=it.get("product_id"),
            pricing_mode=it.get("pricing_mode", "price"),
            sale_price=sale,
            profit=profit,
            profit_rate=stored_rate,
            markup_pct=max(0.0, _num(it.get("markup_pct"))),
            commission_cut=max(0.0, _num(it.get("commission_cut"))),
        ))
    db.commit()

    buf = generate_plan_excel(
        items, plan_type=plan_type, tax_rate=tax_rate,
        commission_cut=commission_cut, cost_mode=cost_mode,
        fee_rate=fee_rate,
        title=plan_title,
    )
    fname = urllib.parse.quote(file_name + ".xlsx")
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fname}"},
    )


def _plan_out(p: models.ProductPlan, db: Session):
    """货盘列表项。"""
    rows = db.query(models.ProductPlanItem).filter_by(plan_id=p.id).count()
    return {
        "id": p.id,
        "name": p.name,
        "title": p.title or p.name,
        "creator": p.creator,
        "create_time": p.create_time.strftime("%Y-%m-%d %H:%M") if p.create_time else "",
        "rows": rows,
        "commission_cut": _num(p.commission_cut),
        "cost_mode": p.cost_mode or "daifa",
        "plan_type": p.plan_type or "public",
        "tax_rate": _num(p.tax_rate),
    }


@router.get("/list")
def list_plans(
    db: Session = Depends(get_db),
    user: str = Depends(security.get_current_user),
):
    """货盘列表（倒序，供文件管理 / 可视化预览）。"""
    plans = db.query(models.ProductPlan).order_by(models.ProductPlan.id.desc()).all()
    return [_plan_out(p, db) for p in plans]


def _item_out(item: models.ProductPlanItem, prod: models.Product | None, plan_type: str = "public"):
    """货盘商品明细（还原商品库信息），按 plan_type 返回不同指标：
    公域 → commission（最终佣金 %）；私域 → margin（毛利率 %，不含税快照）。
    集采价 = 成本价（出厂价，不上浮）；一件代发价 = (成本价+代发费)×(1+markup)。"""
    cost = float(prod.cost_price or 0) if prod else 0
    fee = float(prod.shipping_fee or 0) if prod else 0
    mk = max(0.0, float(getattr(item, "markup_pct", None) or 0)) / 100
    daifa = (cost + fee) * (1 + mk)
    out = {
        "id": item.id,
        "product_id": item.product_id,
        "sku": prod.sku if prod else "",
        "name": prod.name if prod else "",
        "spec": (getattr(prod, "spec", None) if prod else "") or "",
        "category": (prod.category if prod and prod.category else "其他"),
        "image_url": (prod.image_original or prod.image_url) if prod else None,  # v7.8 预览弹窗显示原图
        "merchant": prod.merchant if prod else "",
        "pricing_mode": item.pricing_mode,
        "sale_price": _num(item.sale_price),
        "profit": _num(item.profit),
        "markup_pct": round(mk * 100, 2),          # v7.2 上浮百分点
        "collect_price": round(cost, 2),            # 集采价（出厂价）
        "daifa_price": round(daifa, 2),             # 一件代发价（不含税，已上浮）
        "product_type": (getattr(prod, "product_type", None) if prod else "") or "",
        "stock": (getattr(prod, "stock", None) if prod else "") or "",
        "origin": (getattr(prod, "origin", None) if prod else "") or "",
        "market_price": (getattr(prod, "market_price", None) if prod else "") or "",
    }
    if (plan_type or "public") == "private":
        out["margin"] = _num(item.profit_rate)      # 毛利率 %（不含税快照）
    else:
        out["commission"] = _num(item.profit_rate)  # 最终佣金 %
    return out


@router.get("/{plan_id}")
def plan_detail(
    plan_id: int,
    db: Session = Depends(get_db),
    user: str = Depends(security.get_current_user),
):
    """货盘详情：头部 + 商品明细（含图片/商家），供可视化卡片墙预览。"""
    p = db.query(models.ProductPlan).get(plan_id)
    if not p:
        raise HTTPException(404, "货盘不存在")
    items = db.query(models.ProductPlanItem).filter_by(plan_id=plan_id).all()
    # 批量取商品库信息（含图片、商家）
    prod_ids = [i.product_id for i in items if i.product_id]
    prods = {pr.id: pr for pr in db.query(models.Product).filter(models.Product.id.in_(prod_ids)).all()} \
        if prod_ids else {}
    return {
        **_plan_out(p, db),
        "items": [_item_out(i, prods.get(i.product_id), p.plan_type or "public") for i in items],
    }


@router.get("/{plan_id}/download")
def plan_download(    plan_id: int,
    db: Session = Depends(get_db),
    user: str = Depends(security.get_current_user),
):
    """重新下载历史货盘 Excel（按存档快照还原生成）。"""
    p = db.query(models.ProductPlan).get(plan_id)
    if not p:
        raise HTTPException(404, "货盘不存在")
    items = db.query(models.ProductPlanItem).filter_by(plan_id=plan_id).all()
    prod_ids = [i.product_id for i in items if i.product_id]
    prods = {pr.id: pr for pr in db.query(models.Product).filter(models.Product.id.in_(prod_ids)).all()} \
        if prod_ids else {}
    raw_items = []
    for i in items:
        pr = prods.get(i.product_id)
        raw_items.append({
            "product_id": i.product_id,
            "sku": pr.sku if pr else "",
            "name": pr.name if pr else "",
            "category": pr.category if pr else "其他",
            "image_url": (pr.image_original or pr.image_url) if pr else None,  # v7.7 重新下载也嵌原图
            "image_thumb": pr.image_url if pr else None,
            "merchant": pr.merchant if pr else "",
            "cost_price": float(pr.cost_price or 0) if pr else 0,
            "shipping_fee": float(pr.shipping_fee or 0) if pr else 0,
            "sale_price": _num(i.sale_price),
            "pricing_mode": i.pricing_mode,
            "remark": (getattr(pr, "remark", None) if pr else "") or "",
            # v7 新字段快照还原（私域 22 列 / 公域规格列）
            "spec": (getattr(pr, "spec", None) if pr else "") or "",
            "product_type": (getattr(pr, "product_type", None) if pr else "") or "",
            "ingredients": (getattr(pr, "ingredients", None) if pr else "") or "",
            "stock": (getattr(pr, "stock", None) if pr else "") or "",
            "origin": (getattr(pr, "origin", None) if pr else "") or "",
            "lead_time": (getattr(pr, "lead_time", None) if pr else "") or "",
            "shelf_life": (getattr(pr, "shelf_life", None) if pr else "") or "",
            "after_sales": (getattr(pr, "after_sales", None) if pr else "") or "",
            "market_price": (getattr(pr, "market_price", None) if pr else "") or "",
            "excluded_regions": (getattr(pr, "excluded_regions", None) if pr else "") or "",
            # v7.2 私域上浮快照还原
            "markup_pct": max(0.0, float(getattr(i, "markup_pct", None) or 0)),
            # v7.4 公域逐商品佣金下调还原（历史行 NULL → 回退 plan 级 commission_cut）
            "commission_cut": round(
                float(i.commission_cut) if i.commission_cut is not None else _num(p.commission_cut), 2
            ),
        })
    buf = generate_plan_excel(
        raw_items,
        plan_type=p.plan_type or "public",
        tax_rate=_num(p.tax_rate),
        fee_rate=_num(getattr(p, "fee_rate", 0)),  # v7.10 重新下载也按原费率还原
        commission_cut=_num(p.commission_cut),
        cost_mode=p.cost_mode or "daifa",
        title=(p.title or "").strip(),
    )
    fname = urllib.parse.quote((p.name or "货盘") + ".xlsx")
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fname}"},
    )


@router.delete("/{plan_id}")
def plan_delete(
    plan_id: int,
    db: Session = Depends(get_db),
    user: str = Depends(security.get_current_user),
):
    """删除货盘记录（级联删除明细）。"""
    p = db.query(models.ProductPlan).get(plan_id)
    if not p:
        raise HTTPException(404, "货盘不存在")
    db.query(models.ProductPlanItem).filter_by(plan_id=plan_id).delete()
    db.delete(p)
    db.commit()
    return {"ok": True}
