' pm-platform dev frontend - windowless launcher (hidden console, logs to web.log)
' launched via schtasks: wscript.exe run_web_hidden.vbs
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\1\Desktop\pm-platform\frontend"
sh.Run "cmd /c npm run dev >> ..\web.log 2>&1", 0, False
