# 货盘助手 · 全栈 DEMO（技术设计文档 V1.0 对齐）

按《货盘助手技术设计文档 V1.0》落地：**Vue3 + Element Plus 前端 + FastAPI(Python) 后端 + PostgreSQL + Docker Compose**，5 个 API 真实可用，商品库/货盘落库。

## 目录结构

```
ai-huopan-demo/
├── backend/                 # FastAPI 后端（§3.2 / §4 / §5 / §6）
│   ├── app/
│   │   ├── main.py          # 应用入口、CORS、启动建表+种子
│   │   ├── config.py        # 配置（DATABASE_URL / JWT / LLM）
│   │   ├── database.py      # SQLAlchemy engine + Session
│   │   ├── models.py        # product / app_user / product_plan / product_plan_item（§5）
│   │   ├── schemas.py       # Pydantic 请求响应（§6）
│   │   ├── security.py      # JWT + BCrypt（§8）
│   │   ├── seed.py          # 种子管理员 + 示例商品库
│   │   ├── routers/         # auth / product / profit / plan
│   │   └── services/        # excel(解析+生成) / ai(文案 mock+LLM 替换点)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                # Vue3 + Element Plus 联调版（CDN 免构建）
│   ├── index.html           # 调用真实后端 5 个 API + JWT 登录
│   └── nginx.conf           # 静态托管 + /api 反向代理到 backend
├── docker-compose.yml       # postgres + backend + frontend
├── .env.example
├── index-vue.html           # 之前的纯前端 mock DEMO（保留对照）
└── index.html               # 更早的原生 JS DEMO（保留对照）
```

## 五个 API（§6 已落地）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/login` | JWT 登录（OAuth2 表单：username/password） |
| POST | `/api/product/upload` | 上传商品库 Excel（openpyxl 解析 → 写 `product` 表） |
| GET  | `/api/product/list` | 商品列表 |
| POST | `/api/product/sample` | 初始化示例商品库（便于一键体验） |
| POST | `/api/profit/calculate` | 利润计算 `{cost,sale_price}` → `{profit,profit_rate}` |
| POST | `/api/profit/price` | 反推售价 `{cost,target_rate}` → `{sale_price}` |
| POST | `/api/plan/generate` | 生成货盘：计算利润 → AI 文案 → openpyxl 生成含图 Excel → 落库 |

> 利润公式（§4.3）：利润 = 售价 − 成本；利润率 = 利润 ÷ 售价 × 100%；反推售价 = 成本 ÷ (1 − 目标利润率)。
> 颜色规则（§4.4）：绿 ≥50% / 黄 30–50% / 红 <30%（前端 el-tag）。

## 一键启动（Docker）

```bash
cd ai-huopan-demo
cp .env.example .env          # 按需修改 JWT_SECRET 等
docker compose up --build
```

- 前端：http://localhost:8080 （nginx 同源代理 `/api` 到后端，免 CORS）
- 后端 API 文档：http://localhost:8000/docs
- 默认账号：`admin / admin123`（BCrypt 加密，启动自动种子）

## 本地开发（不依赖 Docker）

```bash
# 1) 准备 Postgres 并建库 huopan（或设置 DATABASE_URL 指向已有库）
# 2) 启动后端
cd ai-huopan-demo/backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 3) 前端：用任意静态服务器打开 frontend/index.html，例如
cd ai-huopan-demo/frontend
python -m http.server 8080
# 浏览器访问 http://localhost:8080
```

> 若以 `file://` 直接打开 `frontend/index.html`，前端会自动回退到 `http://localhost:8000/api`，但需后端放开 CORS（已默认 `allow_origins=["*"]`）。

## 接真实 AI 文案（§3.5）

`backend/app/services/ai.py` 当前为分类+卖点库规则 mock。配置环境变量后切换为真实 LLM：

```bash
LLM_API_KEY=sk-xxxx
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

只需在 `generate_plan_content()` 内补一段 LLM 调用，保持返回结构
`{title, descriptions:{sku:...}, selling_points:{sku:...}}` 即可，其余流程不变。

## 本地安装版（可分发 exe，数据存本机）

给团队里**不懂 Docker / 不会装 Python** 的人用：打包成一个文件夹，双击 exe 即可，数据落在程序目录的 `data/huopan.db`（本地 SQLite），发给别人各自独立。

> **已构建好的成品**：`ai-huopan-demo/货盘助手-本地版.zip`（约 33MB，含 exe + 依赖 + 使用说明.txt），解压后双击 `货盘助手.exe` 即用。已实测双击可启动服务、登录 `admin/admin123`、利润计算(119/59.8%)、反推售价(200)、生成含图货盘 xlsx 全部正常。

### 你（开发者）怎么构建

```bash
cd ai-huopan-demo/backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
python build.py            # 产物在 dist/货盘助手/
```

- 默认 **onedir**（一个文件夹）：`dist/货盘助手/货盘助手.exe` + `_internal` + `frontend/`。
- 想要**单个 exe**：`set ONE_FILE=1 && python build.py`（启动时会解压到临时目录，稍慢）。
- 构建用 `--windowed`：运行时不弹黑色控制台，出错用弹窗提示。

### 别人（使用者）怎么用

1. 你把这整个 `dist/货盘助手/` 文件夹压缩发给同事；
2. 同事解压，**双击 `货盘助手.exe`**；
3. 自动启动本地服务并打开浏览器（http://127.0.0.1:8000），即可使用；
4. 数据都在解压目录的 `data/` 里，**随文件夹走**，换电脑拷走即可。

> 端口默认 8000；若被占用，在 exe 同目录放 `.env` 写 `SERVER_PORT=8088` 即可改。
> 接真实 AI 文案：在 exe 同目录放 `.env`，填 `LLM_API_KEY / LLM_BASE_URL / LLM_MODEL`。

### 目录变化（相对 Docker 版）

```
backend/
├── launcher.py      # 本地启动器：起 uvicorn + 开浏览器 + 错误弹窗
├── build.py         # PyInstaller 打包脚本
frontend/
├── index.html       # 已改为引用本地 vendor/（离线可用）
└── vendor/          # Vue / Element Plus / icons / locale / ExcelJS 本地内置
```

> 数据库主键用 `BigInteger().with_variant(Integer,"sqlite")`：PostgreSQL 用 BIGINT（对齐 §5），本地 SQLite 用 INTEGER 以支持自增。

## 说明

- 文档 §4.1 的 Excel 图片列：`image_url` 支持 http(s) 链接或 data URL；为空时前端展示用占位图，后端生成货盘时按 `image_url` 嵌入真实图片。
- 用户表物理名 `app_user`（规避 PostgreSQL 保留字 `user`，逻辑仍为文档 §5.2 的 user 表）。
- 认证（§8 JWT+BCrypt）已默认开启；演示环境前端自动预填 admin 凭证。
