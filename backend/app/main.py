import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from .database import engine, Base, get_db
from . import models
from .seed import seed_admin, seed_worker
from .routers import auth, config, product, profit, plan, merchant_fee
from .config import FRONTEND_DIR, DATA_DIR

app = FastAPI(title="货盘助手 API", version="1.0")

# 开发期放开 CORS；生产建议收敛为前端域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(config.router)
app.include_router(product.router)
app.include_router(merchant_fee.router)
app.include_router(profit.router)
app.include_router(plan.router)


def _auto_backup():
    """自动备份数据库：每天一份（当天已有则跳过），保留最近 14 份。"""
    import glob
    import os
    import sqlite3
    from datetime import datetime

    db_path = os.path.join(DATA_DIR, "huopan.db")
    if not os.path.exists(db_path):
        return
    backup_dir = os.path.join(DATA_DIR, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    if glob.glob(os.path.join(backup_dir, f"huopan_{today}_*.db")):
        return  # 今天已备份过，跳过
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(backup_dir, f"huopan_{ts}.db")
    try:
        src = sqlite3.connect(db_path)
        dst_conn = sqlite3.connect(dst)
        src.backup(dst_conn)
        dst_conn.close()
        src.close()
        print(f"[auto-backup] OK -> {dst}")
    except Exception as e:
        print(f"[auto-backup] FAILED: {e}")
        return
    # 只保留最近 14 份备份
    files = sorted(glob.glob(os.path.join(backup_dir, "huopan_*.db")), reverse=True)
    for old in files[14:]:
        try:
            os.remove(old)
        except Exception:
            pass


def _backup_loop():
    """后台守护线程：每 24 小时触发一次备份（当天已备过则自动跳过）。"""
    import threading
    import time

    while True:
        time.sleep(24 * 3600)
        try:
            _auto_backup()
        except Exception:
            pass


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    _auto_backup()  # 启动时立即备份（当天首次）
    threading.Thread(target=_backup_loop, daemon=True).start()  # 之后每 24h 定时备份
    # 轻量迁移：SQLite 旧库补 merchant / shipping_fee 列（create_all 不会给已有表加列）
    with engine.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(product)"))]
        if "merchant" not in cols:
            conn.execute(text("ALTER TABLE product ADD COLUMN merchant VARCHAR(128)"))
            conn.commit()
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(product)"))]
        if "shipping_fee" not in cols:
            conn.execute(text("ALTER TABLE product ADD COLUMN shipping_fee NUMERIC(12,2) DEFAULT 0"))
            conn.commit()
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(product)"))]
        if "remote_fee" not in cols:
            conn.execute(text("ALTER TABLE product ADD COLUMN remote_fee NUMERIC(12,2) DEFAULT 0"))
            conn.commit()
        # product_plan 快照列：佣金下调 / 成本模式 / 标题（历史货盘预览与重新下载用）
        pcols = [r[1] for r in conn.execute(text("PRAGMA table_info(product_plan)"))]
        if "commission_cut" not in pcols:
            conn.execute(text("ALTER TABLE product_plan ADD COLUMN commission_cut FLOAT DEFAULT 0"))
            conn.commit()
        pcols = [r[1] for r in conn.execute(text("PRAGMA table_info(product_plan)"))]
        if "cost_mode" not in pcols:
            conn.execute(text("ALTER TABLE product_plan ADD COLUMN cost_mode VARCHAR(16) DEFAULT 'daifa'"))
            conn.commit()
        pcols = [r[1] for r in conn.execute(text("PRAGMA table_info(product_plan)"))]
        if "title" not in pcols:
            conn.execute(text("ALTER TABLE product_plan ADD COLUMN title VARCHAR(255)"))
            conn.commit()
        # v7：商品库新字段（私域 22 列货盘所需的上传信息）
        v7_product_cols = {
            "product_type": "VARCHAR(64)",
            "ingredients": "TEXT",
            "spec": "VARCHAR(128)",
            "stock": "VARCHAR(64)",
            "origin": "VARCHAR(128)",
            "lead_time": "VARCHAR(64)",
            "shelf_life": "VARCHAR(64)",
            "after_sales": "VARCHAR(64)",
            "market_price": "VARCHAR(64)",
            "excluded_regions": "VARCHAR(128)",
        }
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(product)"))]
        for col, ddl in v7_product_cols.items():
            if col not in cols:
                conn.execute(text(f"ALTER TABLE product ADD COLUMN {col} {ddl}"))
        # v7.7：商品原图（不压缩）。列表接口不返回该字段，仅生成货盘嵌图时使用。
        if "image_original" not in cols:
            conn.execute(text("ALTER TABLE product ADD COLUMN image_original TEXT"))
        # v7：货盘类型（public=公域 7 列 / private=私域 22 列）+ 税率快照
        pcols = [r[1] for r in conn.execute(text("PRAGMA table_info(product_plan)"))]
        if "plan_type" not in pcols:
            conn.execute(text("ALTER TABLE product_plan ADD COLUMN plan_type VARCHAR(16) DEFAULT 'public'"))
        if "tax_rate" not in pcols:
            conn.execute(text("ALTER TABLE product_plan ADD COLUMN tax_rate FLOAT DEFAULT 0"))
        # v7.10：公域平台服务费费率快照（导出佣金需扣平台费/税费）
        if "fee_rate" not in pcols:
            conn.execute(text("ALTER TABLE product_plan ADD COLUMN fee_rate FLOAT DEFAULT 0"))
        # v7.2：货盘明细记录私域一件代发价上浮百分点（重新下载/预览还原）
        icols = [r[1] for r in conn.execute(text("PRAGMA table_info(product_plan_item)"))]
        if "markup_pct" not in icols:
            conn.execute(text("ALTER TABLE product_plan_item ADD COLUMN markup_pct FLOAT DEFAULT 0"))
        # v7.4：货盘明细记录公域逐商品佣金下调百分点。
        # 列不加 DEFAULT（旧行保持 NULL），随后用 plan 级 commission_cut 回填，
        # 保证历史公域货盘「重新下载」的佣金与生成时完全一致。
        if "commission_cut" not in icols:
            conn.execute(text("ALTER TABLE product_plan_item ADD COLUMN commission_cut FLOAT"))
            conn.execute(text(
                "UPDATE product_plan_item SET commission_cut = "
                "(SELECT p.commission_cut FROM product_plan p WHERE p.id = product_plan_item.plan_id) "
                "WHERE commission_cut IS NULL"
            ))
        conn.commit()
    db = next(get_db())
    try:
        seed_admin(db)
        seed_worker(db)
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"status": "ok"}


# 托管前端静态资源（本地安装版：前端随程序分发，同源访问免 CORS）
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
