from fastapi import APIRouter
from .. import schemas

router = APIRouter(prefix="/api/profit", tags=["profit"])


@router.post("/calculate", response_model=schemas.ProfitCalcRes)
def calculate(req: schemas.ProfitCalcReq):
    """§6 利润计算：净利润 = 售价 - 成本 - 平台服务费 - 税费；利润率 = 净利润 ÷ 售价 × 100%。"""
    fee = round(req.sale_price * req.platform_fee_rate, 2)
    tax = round(req.sale_price * req.tax_rate, 2)
    profit = round(req.sale_price - req.cost - fee - tax, 2)
    rate = (profit / req.sale_price * 100) if req.sale_price > 0 else 0
    return schemas.ProfitCalcRes(
        platform_fee=fee,
        tax=tax,
        profit=profit,
        profit_rate=  round(rate, 2),
    )


@router.post("/price", response_model=schemas.PriceRes)
def price(req: schemas.PriceReq):
    """§6 按目标净利润率反推售价：售价 = 成本 ÷ (1 - 目标利润率 - 平台费率 - 税率)。"""
    denom = 1 - req.target_rate - req.platform_fee_rate - req.tax_rate
    sale = req.cost if denom <= 0 else req.cost / denom
    return schemas.PriceRes(sale_price=round(sale, 2))
