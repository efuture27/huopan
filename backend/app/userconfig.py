"""v7.17 用户级配置存储 + 货盘导出目录解析。

为什么单独一个模块：
- 安装版里程序目录（C:\\Program Files）**只读**，任何用户级配置只能写数据目录；
- LLM 配置、导出目录配置都属于「跟着数据走」的用户配置，统一收在这里，避免各路由各写一份。

配置落地在 `{DATA_DIR}/.env`（app.config 以 override 方式加载，优先级高于程序目录的 .env）。
"""
import os
import ctypes
import sys

from .config import DATA_DIR

ENV_PATH = os.path.join(DATA_DIR, ".env")

# 导出目录相关配置键
K_OUTPUT_DIR = "HUOPAN_OUTPUT_DIR"     # 货盘 Excel 保存目录（空 = 用默认目录）
K_OUTPUT_SAVE = "HUOPAN_OUTPUT_SAVE"   # "1"/"0"：生成后是否自动保存到该目录

# 默认目录名（在用户「文档」下）
DEFAULT_SUBDIR = "货盘助手导出"


def read_env() -> dict:
    """读取数据目录下的 .env（轻量解析，不依赖 dotenv）。

    注意：python-dotenv 的 `set_key` 默认会给值**加引号**（`KEY='value'`），
    所以这里必须剥掉外层引号，否则读出来会带引号（曾把 `''` 当成真实目录名）。
    """
    cfg = {}
    if not os.path.exists(ENV_PATH):
        return cfg
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                    v = v[1:-1]
                cfg[k.strip()] = v
    except OSError:
        pass
    return cfg


def read_env_value(key: str, default: str = "") -> str:
    """读配置：**进程环境变量优先**，其次 .env（与 LLM 配置口径一致）。"""
    v = os.environ.get(key)
    if v is not None and v != "":
        return v
    return read_env().get(key, default)


def write_env_value(key: str, value: str):
    """写 .env 并热更新到当前进程环境变量（即时生效，无需重启）。

    写空值 = **删掉这一项**（也清掉环境变量），语义是「回到默认」，
    比留一行空值更干净。写入时显式要求不加引号，避免 `KEY=''` 这种读出来带引号的坑。
    """
    value = "" if value is None else str(value)
    if value == "":
        os.environ.pop(key, None)
        if os.path.exists(ENV_PATH):
            try:
                from dotenv import unset_key
                unset_key(ENV_PATH, key)
                return
            except Exception:
                pass
            _write_env_fallback(key, None)
        return

    os.environ[key] = value
    try:
        from dotenv import set_key
        if not os.path.exists(ENV_PATH):
            # set_key 不会自动建文件，先落一个空文件
            with open(ENV_PATH, "a", encoding="utf-8"):
                pass
        try:
            set_key(ENV_PATH, key, value, quote_mode="never")
        except TypeError:
            # 老版本 python-dotenv 不支持 quote_mode
            set_key(ENV_PATH, key, value)
    except Exception:
        _write_env_fallback(key, value)


def _write_env_fallback(key: str, value):
    """dotenv 不可用时的兜底：按 key=value 覆写；value 为 None 表示删除该行。"""
    lines, found = [], False
    if os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            lines = []
    out = []
    for line in lines:
        if line.strip().startswith(key + "="):
            found = True
            if value is not None:
                out.append(f"{key}={value}")
            continue
        out.append(line)
    if not found and value is not None:
        out.append(f"{key}={value}")
    try:
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + ("\n" if out else ""))
    except OSError:
        pass


# ---------------------------------------------------------------- 目录解析

def cap_drive(p: str) -> str:
    """把小写盘符规范成大写：`e:\\Users\\...` → `E:\\Users\\...`。

    注册表里的「文档」目录常写成小写盘符，功能上无碍（Windows 不区分大小写），
    但这个路径会显示在界面上、也会被用户复制去资源管理器，大写更符合习惯。
    """
    p = p or ""
    if len(p) >= 2 and p[1] == ":" and p[0].isalpha() and p[0].islower():
        return p[0].upper() + p[1:]
    return p


def documents_dir() -> str:
    """取用户「文档」目录，尊重 Windows 的文件夹重定向（比如被改到 E 盘）。

    直接用 ~/Documents 在重定向过的机器上会指向一个不存在的空目录 —— 用户这台机器
    「下载」就被改到了 E 盘，所以这里走注册表读真实路径。
    """
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            )
            try:
                val, _ = winreg.QueryValueEx(key, "Personal")
            finally:
                winreg.CloseKey(key)
            val = os.path.expandvars(str(val))
            if val and os.path.isabs(val):
                return cap_drive(val)
        except Exception:
            pass
        # 兜底：走系统 API（SHGetKnownFolderPath）
        try:
            buf = ctypes.create_unicode_buffer(260)
            # FOLDERID_Documents = {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
            guid = ctypes.create_unicode_buffer("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}")
            if ctypes.windll.shell32.SHGetKnownFolderPath(guid, 0, None, ctypes.byref(buf)) == 0:
                return cap_drive(buf.value)
        except Exception:
            pass
    return cap_drive(os.path.join(os.path.expanduser("~"), "Documents"))


def default_output_dir() -> str:
    """默认导出目录：{文档}\\货盘助手导出。"""
    return os.path.join(documents_dir(), DEFAULT_SUBDIR)


def output_dir() -> str:
    """当前生效的导出目录（未配置则用默认目录）。

    读出来的值也过一遍 `cap_drive`：老配置里可能存着小写盘符（`e:\\...`），
    避免同一个目录因为大小写不同而在界面上显示成两种样子。
    """
    stored = (read_env_value(K_OUTPUT_DIR, "") or "").strip()
    return cap_drive(stored) if stored else default_output_dir()


def output_save_enabled() -> bool:
    """生成后是否自动保存到导出目录（默认开启）。"""
    v = (read_env_value(K_OUTPUT_SAVE, "1") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def set_output_dir(path: str):
    write_env_value(K_OUTPUT_DIR, cap_drive((path or "").strip()))


def set_output_save(enabled: bool):
    write_env_value(K_OUTPUT_SAVE, "1" if enabled else "0")
