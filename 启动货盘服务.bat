@echo off
chcp 65001 >nul
title 货盘助手 · 本地服务
set "ROOT=E:\WorkBuddyData\WorkBuddy\2026-08-23-11-00-35\ai-huopan-demo"
set "PY=%ROOT%\backend\venv2\Scripts\python.exe"
set "PYTHONPATH=%ROOT%\backend"
set "SERVER_HOST=0.0.0.0"

cd /d "%ROOT%\backend"
echo ============================================
echo  货盘助手 本地服务
echo  手机访问：http://本机局域网IP:8000/
echo  （本机IP 用 ipconfig 查「以太网」IPv4）
echo  关闭此窗口即停止服务
echo ============================================
"%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
