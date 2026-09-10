from pydantic import BaseModel
from typing import Optional, List


# §6 利润计算请求 / 响应
class ProfitCalcReq(BaseModel):
    cost: float
    sale_price: float
    platform_fee_rate: float = 0.0  # 平台服务费费率（占售价比例，如 0.06 表示 6%）
    tax_rate: float = 0.0          # 税费率（占售价比例，如 0.01 表示 1%）


class ProfitCalcRes(BaseModel):
    platform_fee: float  # 平台服务费金额
    tax: float           # 税费金额
    profit: float        # 净利润 = 售价 - 成本 - 平台服务费 - 税费
    profit_rate: float   # 利润率 = 净利润 ÷ 售价 × 100%


# §,6 目标利润率反推售价
class PriceReq(BaseModel):
    cost: float
    target_rate: float  # 期望的最终净利润率（占售价比例，0~1）
    platform_fee_rate: float = 0.0
    tax_rate: float = 0.0


class PriceRes(BaseModel):
    sale_price: float


# §4.5 商品数据（由前端提交，含图片用于生成货盘）
class PlanItemIn(BaseModel):
    product_id: Optional[int] = None
    sku: str
    name: str
    image_url: Optional[str] = None
    cost_price: float
    shipping_fee: float = 0.0        # 一件代发快递费：cost_mode='daifa' 时叠加进成本
    sale_price: float
    pricing_mode: str = "price"  # 'price' | 'margin'
    category: Optional[str] = None
    merchant: Optional[str] = None  # 商家（内部留档，两套货盘均不再输出商家列）
    remark: Optional[str] = None    # 卖点介绍（私域货盘 V 列）
    # —— v7 新增：私域 22 列透传字段（公域仅用 spec） ——
    spec: Optional[str] = None                  # 规格（公域 D 列 / 私域 F 列）
    product_type: Optional[str] = None          # 产品类型（私域 B 列）
    ingredients: Optional[str] = None           # 配料表（私域 E 列）
    stock: Optional[str] = None                 # 库存数量（私域 O 列）
    origin: Optional[str] = None                # 发货地（私域 P 列）
    lead_time: Optional[str] = None             # 发货时效（私域 Q 列）
    shelf_life: Optional[str] = None            # 保质期（私域 R 列）
    after_sales: Optional[str] = None           # 售后期（私域 S 列）
    market_price: Optional[str] = None          # 市场价（线下/线上）（私域 T 列）
    excluded_regions: Optional[str] = None      # 不发货地区（私域 U 列）
    markup_pct: float = 0.0                     # v7.2 私域：一件代发价上浮百分点（每件独立，如 5=上浮5%）
    commission_cut: float = 0.0                 # v7.4 公域：逐商品佣金下调百分点（每件独立，如 3=下调3个点）


class PlanGenerateReq(BaseModel):
    name: str                     # 货盘文件名称：用于下载文件名 / 落库
    title: Optional[str] = None   # 货盘标题：为空时后端回退到 name（v7 两套模板均无大标题行）
    commission_cut: float = 0.0   # 佣金下调（百分点）：佣金 = 利润率 − 该值，下限 0（仅公域）
    cost_mode: str = "daifa"      # 成本模式：'collect'=集采(出厂价) | 'daifa'=一件代发(出厂价+代发费)（仅公域佣金用）
    plan_type: str = "public"     # v7 货盘类型：'public'=公域 7 列 | 'private'=私域 22 列
    tax_rate: float = 0.0         # v7 税率（小数，如 0.09 表示 9%；私域含税价 = 不含税 × (1+税率)）
    fee_rate: float = 0.0         # v7.10 平台服务费费率（小数，如 0.06 表示 6%；公域导出佣金扣减用）
    items: List[PlanItemIn]


# §5.5 商家偏远运费（商家级，多行文本；仅展示不参与佣金）
class MerchantFeeItem(BaseModel):
    merchant: str                 # 商家名（与商品 merchant 一致，精确匹配）
    fee_note: str = ""            # 偏远地区运费说明（支持多行 \n）


class MerchantFeeBatch(BaseModel):
    items: List[MerchantFeeItem]


# §5.1 商品输出
class ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    image_url: Optional[str] = None
    cost_price: float
    category: Optional[str] = None
    remark: Optional[str] = None
    spec: Optional[str] = None
    product_type: Optional[str] = None
    ingredients: Optional[str] = None
    stock: Optional[str] = None
    origin: Optional[str] = None
    lead_time: Optional[str] = None
    shelf_life: Optional[str] = None
    after_sales: Optional[str] = None
    market_price: Optional[str] = None
    excluded_regions: Optional[str] = None
    create_time: Optional[str] = None
