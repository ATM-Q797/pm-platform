@echo off
rem dev backend launcher - run via schtasks/wmic/double-click
rem log appended to api.log for troubleshooting
cd /d C:\Users\1\Desktop\pm-platform\backend
venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >> api.log 2>&1
