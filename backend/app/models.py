from sqlalchemy import Column, BigInteger, String, Text, Numeric, DateTime, Integer, ForeignKey, Float
from sqlalchemy.sql import func
from .database import Base

# 主键类型：PostgreSQL 用 BIGINT（对齐设计文档 §5），SQLite 用 INTEGER 以支持自增
PKType = BigInteger().with_variant(Integer, "sqlite")


# §5.1 商品表 product
class Product(Base):
    __tablename__ = "product"
    id = Column(PKType, primary_key=True, autoincrement=True)
    sku = Column(String(64), index=True)
    name = Column(String(255))
    merchant = Column(String(128), nullable=True)  # 商家/供应商名称
    image_url = Column(Text, nullable=True)
    image_original = Column(Text, nullable=True)  # v7.7 原图 data URL（不压缩）；列表接口不返回，仅生成货盘嵌图用
    cost_price = Column(Numeric(12, 2), default=0)   # 集采成本（出厂价/合计单价）
    shipping_fee = Column(Numeric(12, 2), default=0)  # 一件代发快递费（0=无拆分）
    remote_fee = Column(Numeric(12, 2), default=0)     # 偏远地区加收运费（商家级，同商家统一值；仅展示不参与佣金）
    category = Column(String(64), nullable=True)
    remark = Column(Text, nullable=True)               # 卖点介绍（私域货盘 V 列）
    # —— v7 新增：私域 22 列货盘所需的上传字段 ——
    product_type = Column(String(64), nullable=True)    # 产品类型（袋泡茶/冻干粉等）
    ingredients = Column(Text, nullable=True)           # 配料表
    spec = Column(String(128), nullable=True)           # 规格（如 12g×10袋/盒）
    stock = Column(String(64), nullable=True)           # 库存数量（兼容带单位文本）
    origin = Column(String(128), nullable=True)         # 发货地（如 云南昆明）
    lead_time = Column(String(64), nullable=True)       # 发货时效（如 48小时内发货）
    shelf_life = Column(String(64), nullable=True)      # 保质期（如 12个月）
    after_sales = Column(String(64), nullable=True)     # 售后期（如 7天）
    market_price = Column(String(64), nullable=True)    # 市场价（线下/线上）
    excluded_regions = Column(String(128), nullable=True)  # 不发货地区（如 新疆西藏）
    create_time = Column(DateTime, server_default=func.now())


# §5.2 用户表 user（PostgreSQL 保留字规避，物理表名 app_user）
class User(Base):
    __tablename__ = "app_user"
    id = Column(PKType, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, index=True)
    password = Column(String(255))  # bcrypt 哈希
    role = Column(String(32), default="user")
    status = Column(Integer, default=1)  # 1=启用 0=禁用


# §5.3 货盘记录表 product_plan
class ProductPlan(Base):
    __tablename__ = "product_plan"
    id = Column(PKType, primary_key=True, autoincrement=True)
    name = Column(String(255))
    creator = Column(String(64), nullable=True)
    title = Column(String(255), nullable=True)          # Excel 内部标题（生成时快照）
    commission_cut = Column(Float, default=0)           # 佣金下调百分点（生成时快照）
    cost_mode = Column(String(16), default="daifa")     # 成本口径快照：'collect' | 'daifa'
    plan_type = Column(String(16), default="public")    # v7 货盘类型：'public'=公域7列 | 'private'=私域22列
    tax_rate = Column(Float, default=0)                 # v7 税率快照（私域含税价 = 不含税 × (1+税率)，如 0.09）
    fee_rate = Column(Float, default=0)                 # v7.10 公域平台服务费费率快照（占售价比例，如 0.06）
    create_time = Column(DateTime, server_default=func.now())


# §5.4 货盘商品明细表 product_plan_item
class ProductPlanItem(Base):
    __tablename__ = "product_plan_item"
    id = Column(PKType, primary_key=True, autoincrement=True)
    plan_id = Column(PKType, ForeignKey("product_plan.id", ondelete="CASCADE"))
    product_id = Column(PKType, nullable=True)
    pricing_mode = Column(String(16))  # 'price' | 'margin'
    sale_price = Column(Numeric(12, 2), default=0)
    profit = Column(Numeric(12, 2), default=0)
    profit_rate = Column(Numeric(8, 2), default=0)
    markup_pct = Column(Float, default=0)   # v7.2 私域：一件代发价上浮百分点（每件可不同，5=上浮5%）
    commission_cut = Column(Float, nullable=True)  # v7.4 公域：逐商品佣金下调百分点（每件可不同；历史行为 NULL → 回填 plan 级值）


# §5.5 商家偏远运费表 merchant_fee（商家级，多行文本规则；仅展示不参与佣金）
class MerchantFee(Base):
    __tablename__ = "merchant_fee"
    id = Column(PKType, primary_key=True, autoincrement=True)
    merchant = Column(String(128), unique=True, index=True)  # 商家名（与 product.merchant 一致）
    fee_note = Column(Text, nullable=True)                   # 偏远地区运费说明（可多行）
    create_time = Column(DateTime, server_default=func.now())
    update_time = Column(DateTime, server_default=func.now(), onupdate=func.now())


# §5.6 上传文件记录表 uploaded_file（v7.13 上传文件管理：存档上传的成本货盘 Excel 原件）
class UploadedFile(Base):
    __tablename__ = "uploaded_file"
    id = Column(PKType, primary_key=True, autoincrement=True)
    filename = Column(String(255))                      # 原始文件名
    merchant = Column(String(128), nullable=True)       # 识别到的商家
    product_count = Column(Integer, default=0)          # 本次载入商品数
    file_size = Column(Integer, default=0)              # 文件大小（字节）
    file_path = Column(String(512))                     # 磁盘存储绝对路径（data/uploads/）
    is_active = Column(Integer, default=0)              # 1=当前商品库来源（最近一次上传/恢复）
    uploaded_by = Column(String(64), nullable=True)     # 上传人
    create_time = Column(DateTime, server_default=func.now())
