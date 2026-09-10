"""PyInstaller 打包脚本：把 FastAPI 后端 + 前端静态资源打成可分发程序。

产物：
  dist/货盘助手/  （文件夹，内含 货盘助手.exe + _internal + frontend）
  把整个文件夹压缩发给别人，解压后双击 exe 即可使用，数据存于文件夹内 data/。

用法：
  python build.py
可选环境变量：
  APP_NAME   可执行文件名（默认「货盘助手」）
  ONE_FILE   设为 1 则打包成单个 exe（启动稍慢，每次解压到临时目录）
"""
import os
import sys

import PyInstaller.__main__

HERE = os.path.dirname(os.path.abspath(__file__))
APP_NAME = os.getenv("APP_NAME", "货盘助手")
ONE_FILE = os.getenv("ONE_FILE", "0") == "1"

cmd = [
    "launcher.py",
    "--name", APP_NAME,
    "--paths", HERE,
    "--add-data", os.path.join(HERE, "..", "frontend") + os.pathsep + "frontend",
    "--hidden-import", "jose",
    "--hidden-import", "jose.jwt",
    "--hidden-import", "passlib",
    "--hidden-import", "passlib.handlers.bcrypt",
    "--hidden-import", "bcrypt",
    "--hidden-import", "multipart",
    "--hidden-import", "email",
    "--hidden-import", "email.mime",
    "--hidden-import", "email.mime.text",
    "--collect-submodules", "uvicorn",
    "--collect-submodules", "sqlalchemy",
    "--collect-submodules", "openpyxl",
    "--collect-submodules", "PIL",
    "--clean",
    "--noconfirm",
]

if ONE_FILE:
    cmd.append("--onefile")
else:
    cmd.append("--onedir")

if sys.platform.startswith("win"):
    # 本地安装程序：隐藏控制台黑窗，错误通过弹窗提示
    cmd.append("--windowed")

PyInstaller.__main__.run(cmd)
print("\nBUILD_DONE ->", os.path.join(HERE, "dist", APP_NAME))
