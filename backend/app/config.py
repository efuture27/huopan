import os
import sys

# ---- 路径解析（本地安装版：数据写在本机，前端随程序分发）----
def _exe_dir():
    # 打包后 sys.executable 为 exe 路径；源码运行时用项目根目录
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # app/config.py -> 上两级为项目根
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _meipass():
    return getattr(sys, "_MEIPASS", None)


# EXE_DIR：始终是可写的程序目录（数据、运行态文件都放这里）
EXE_DIR = _exe_dir()

# 支持在程序目录放置 .env 覆盖配置（如 LLM_API_KEY）。需在读取配置前加载
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(EXE_DIR, ".env"))
except Exception:
    pass

# FRONTEND_DIR：只读静态资源。打包后在 _MEIPASS/frontend，源码在 项目根/frontend
FRONTEND_DIR = os.path.join(_meipass() or EXE_DIR, "frontend")

# 数据目录：始终写在程序旁边（可写、持久），其他人拿到程序即有独立本地库
DATA_DIR = os.path.join(EXE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# v7.13 上传文件存档目录（成本货盘 Excel 原件，供上传文件管理下载/恢复）
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---- 配置（对齐技术设计文档 V1.0 §7/§8，均可通过环境变量或 .env 覆盖）----
# 默认使用本地 SQLite 文件；如需切换 Postgres，设置 DATABASE_URL 即可
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(DATA_DIR, 'huopan.db')}")
JWT_SECRET = os.getenv("JWT_SECRET", "local-dev-secret-change-me")
JWT_ALGORITHM = "HS256"
# v7.1：内网自用工具，token 默认 30 天有效（原 1440=1 天，隔天打开就弹「无效或过期的凭证」）
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "43200"))

# 可选：接真实 LLM（设计文档 §3.5 DeepSeek/Qwen/GPT）。为空则使用规则 mock（§4.5 同样可行）
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))
