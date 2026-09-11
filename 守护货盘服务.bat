@echo off
title Huopan Watchdog
rem ============================================================
rem  货盘助手 · 服务守护（需要时双击即可）
rem  每 60 秒检测 8000 端口，掉了就自动拉起服务。
rem  关闭本窗口即停止守护（不会停掉已运行的服务）。
rem  正常情况不用管：已注册计划任务「HuopanGuard」，
rem  开机自动运行 + 每 5 分钟自检一次。
rem ============================================================
cd /d "%~dp0"
"backend\venv2\Scripts\python.exe" huopan_guard.py --loop
pause
