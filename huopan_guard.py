# -*- coding: utf-8 -*-
"""货盘助手 · 服务守护

用法：
  python huopan_guard.py          单次检查：8000 端口不通就拉起 uvicorn（供计划任务每 5 分钟调用）
  python huopan_guard.py --loop   持续守护：每 60 秒检查一次（供手动双击/登录启动）

端口已通时不做任何事，因此重复调用不会重复启动。
"""
import os
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(ROOT, "backend")
PY = os.path.join(BACKEND, "venv2", "Scripts", "python.exe")
LOG = os.path.join(ROOT, "server_watchdog.log")
PORT = 8000

# DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP —— 脱离父进程独立存活
FLAGS = 0x00000008 | 0x00000200


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg + "\n")
    except OSError:
        pass


def port_up():
    s = socket.socket()
    s.settimeout(2)
    try:
        return s.connect_ex(("127.0.0.1", PORT)) == 0
    finally:
        s.close()


def start_service():
    env = dict(os.environ, PYTHONPATH=BACKEND, SERVER_HOST="0.0.0.0")
    subprocess.Popen(
        [PY, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(PORT)],
        cwd=BACKEND, env=env, creationflags=FLAGS, close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=open(os.path.join(ROOT, "server_svc.log"), "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )
    log("port %d DOWN -> uvicorn started" % PORT)


def main():
    loop = "--loop" in sys.argv
    while True:
        if not port_up():
            start_service()
        else:
            log("check ok, service running")
        if not loop:
            break
        time.sleep(60)


if __name__ == "__main__":
    main()
