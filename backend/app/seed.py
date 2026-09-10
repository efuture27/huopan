from . import models, security

# 示例商品库（与前端 DEMO 一致，便于一键体验）
SAMPLE = [
    ("A001", "针织开衫", 80, "上衣"),
    ("A003", "雪纺衬衫", 55, "上衣"),
    ("A007", "纯棉T恤", 35, "上衣"),
    ("A002", "亚麻裤", 65, "裤装"),
    ("A008", "高腰阔腿裤", 75, "裤装"),
    ("A004", "百褶半裙", 70, "裙装"),
    ("A006", "牛仔连衣裙", 95, "裙装"),
    ("A005", "风衣外套", 120, "外套"),
]


def seed_admin(db):
    """§5.2 启动种子管理员（admin / admin123，BCrypt 加密）。"""
    if db.query(models.User).count() == 0:
        db.add(models.User(
            username="admin",
            password=security.hash_password("admin123"),
            role="admin",
            status=1,
        ))
        db.commit()


def seed_worker(db):
    """团队成员账号（huopan / huopan123，普通角色，仅查看与使用、不可上传商品库）。"""
    if not db.query(models.User).filter(models.User.username == "huopan").first():
        db.add(models.User(
            username="huopan",
            password=security.hash_password("huopan123"),
            role="user",
            status=1,
        ))
        db.commit()


def seed_sample_products(db):
    """初始化示例商品库，已存在则跳过。返回新增条数。"""
    existing = {u.sku for u in db.query(models.Product).all()}
    added = 0
    for sku, name, cost, cat in SAMPLE:
        if sku in existing:
            continue
        db.add(models.Product(
            sku=sku, name=name, cost_price=cost,
            category=cat, remark="示例数据", image_url=None,
        ))
        added += 1
    if added:
        db.commit()
    return added
