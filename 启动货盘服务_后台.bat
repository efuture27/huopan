@echo off
set "ROOT=E:\WorkBuddyData\WorkBuddy\2026-08-23-11-00-35\ai-huopan-demo"
set "PYTHONPATH=%ROOT%\backend"
set "SERVER_HOST=0.0.0.0"
start "Huopan_Service" /min cmd /c ""%ROOT%\backend\venv2\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> "%ROOT%\server_svc.log" 2>&1"
