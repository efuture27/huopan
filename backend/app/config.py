import os
import sys

# ---- 路径解析（安装版：程序文件在安装目录（只读），数据在用户目录）----
def _exe_dir():
    # 打包后 sys.executable 为 exe 路径；源码运行时用项目根目录
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # app/config.py -> 上两级为项目根
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _meipass():
    return getattr(sys, "_MEIPASS", None)


def _local_appdata():
    """用户级目录，普通账号一定可写。"""
    return os.getenv("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")


def _writable(d):
    """探测目录是否可写（不存在则尝试创建，失败即不可用）。"""
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".write_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


# EXE_DIR：程序所在目录。安装到 Program Files 时为只读，只放程序文件，不写任何数据
EXE_DIR = _exe_dir()

# 用户级配置目录：安装向导写入的「数据目录指针」、安装版的配置都放这里
USER_DIR = os.path.join(_local_appdata(), "货盘助手")
DATA_DIR_FILE = os.path.join(USER_DIR, "data_dir.txt")

# 程序目录的 .env（安装包自带/绿色版手放）。必须在解析配置前加载
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(EXE_DIR, ".env"))
except Exception:
    pass


def _is_installed_copy():
    """这份副本是不是「安装版」——由安装程序放在程序目录的标记文件决定。

    关键：绝不能靠「data_dir.txt 存在」来判断。那个文件在用户目录里，
    是机器级的；如果拿它当依据，绿色版/源码运行会被安装版的指针劫持，
    数据目录会被悄悄换掉。
    """
    return os.path.isfile(os.path.join(EXE_DIR, "install_mode.txt"))


def _resolve_data_dir():
    """数据目录解析顺序：
    1. 环境变量 HUOPAN_DATA_DIR / 程序旁 .env —— 便携版、测试、高级用户
    2. 安装版：安装向导选的位置（%LOCALAPPDATA%\\货盘助手\\data_dir.txt）
    3. 安装版但没选过：%LOCALAPPDATA%\\货盘助手\\data
    4. 绿色版 / 源码运行：程序目录旁的 data（保持 v7.x 原有行为）
    最外层还有可写性兜底。
    """
    env_dir = (os.getenv("HUOPAN_DATA_DIR") or "").strip().strip('"')
    if env_dir:
        return os.path.abspath(os.path.expandvars(os.path.expanduser(env_dir))), "env"

    if _is_installed_copy():
        try:
            with open(DATA_DIR_FILE, encoding="utf-8-sig") as f:
                chosen = f.read().strip().strip('"')
            if chosen:
                return os.path.abspath(os.path.expandvars(os.path.expanduser(chosen))), "installer"
        except OSError:
            pass
        return os.path.join(USER_DIR, "data"), "user"

    # 绿色版 / 源码运行：数据始终在程序旁边的 data
    return os.path.join(EXE_DIR, "data"), "portable"


DATA_DIR, DATA_DIR_SOURCE = _resolve_data_dir()

# 兜底：目标目录写不进去（如用户选了只读盘）就退回用户目录，绝不静默失败
if not _writable(DATA_DIR):
    _fallback = os.path.join(USER_DIR, "data")
    if os.path.abspath(_fallback) != os.path.abspath(DATA_DIR):
        DATA_DIR, DATA_DIR_SOURCE = _fallback, "fallback"
    os.makedirs(DATA_DIR, exist_ok=True)
else:
    os.makedirs(DATA_DIR, exist_ok=True)

# 数据目录下的 .env（安装版：程序目录只读，用户配置写这里），优先级高于程序目录
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(DATA_DIR, ".env"), override=True)
except Exception:
    pass

# 运行日志也放数据目录（Program Files 下写不进去）
LOG_FILE = os.path.join(DATA_DIR, "服务日志.log")

# 数据目录来源（写进日志，便于排查「数据到底在哪」）
DATA_DIR_HINT = {
    "env": "环境变量 HUOPAN_DATA_DIR 指定",
    "installer": "安装时选择的数据目录",
    "portable": "绿色版：程序目录旁的 data",
    "user": "安装版默认：用户目录",
    "fallback": "原目录不可写，已自动退回用户目录",
}.get(DATA_DIR_SOURCE, DATA_DIR_SOURCE)

# FRONTEND_DIR：只读静态资源。打包后在 _MEIPASS/frontend，源码在 项目根/frontend
FRONTEND_DIR = os.path.join(_meipass() or EXE_DIR, "frontend")

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

APP_VERSION = "7.17"

SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))
