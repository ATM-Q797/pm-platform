' pm-platform dev backend - windowless launcher (hidden console, logs to api.log)
' launched via schtasks: wscript.exe run_api_hidden.vbs
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\1\Desktop\pm-platform\backend"
sh.Run "cmd /c venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >> api.log 2>&1", 0, False
