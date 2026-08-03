@echo off
REM 一键启动前后端开发服务（Windows）
REM
REM 用法：双击 start.bat 或在命令行执行 start.bat
REM 首次运行自动：创建 venv -> pip install -> npm install -> init_db.py
REM 之后直接启动：后端 :8000 + 前端 :5173
REM 关闭本窗口或按 Ctrl+C 停止所有服务。

setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "BACKEND=%ROOT%\backend"
set "FRONTEND=%ROOT%\frontend"

echo ==================================================
echo   智能终端研发项目管理平台 - 一键启动
echo ==================================================

REM ---------- 后端虚拟环境 ----------
echo.
echo [1/4] 检查后端虚拟环境...
if not exist "%BACKEND%\venv\Scripts\python.exe" (
    echo   首次运行，创建虚拟环境...
    python -m venv "%BACKEND%\venv"
)

echo [2/4] 检查后端依赖...
"%BACKEND%\venv\Scripts\python.exe" -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo   安装后端依赖...
    "%BACKEND%\venv\Scripts\python.exe" -m pip install -q -r "%BACKEND%\requirements.txt"
) else (
    echo   后端依赖已就绪
)

REM ---------- 前端依赖 ----------
echo [3/4] 检查前端依赖...
if not exist "%FRONTEND%\node_modules" (
    echo   首次运行，安装前端依赖...
    pushd "%FRONTEND%"
    call npm install
    popd
) else (
    echo   前端依赖已就绪
)

REM ---------- 启动服务 ----------
echo [4/4] 启动服务...
echo.
echo   后端 API:  http://localhost:8000
echo   API 文档:  http://localhost:8000/docs
echo   前端应用:  http://localhost:5173
echo.
echo   关闭本窗口停止所有服务
echo ==================================================
echo.

REM 启动后端（新窗口）
start "PM-Platform 后端" cmd /c "cd /d "%BACKEND%" && "%BACKEND%\venv\Scripts\uvicorn.exe" app.main:app --reload --host 0.0.0.0 --port 8000"

REM 启动前端（新窗口）
start "PM-Platform 前端" cmd /c "cd /d "%FRONTEND%" && npm run dev"

echo 两个服务已在独立窗口启动。
echo 关闭对应窗口即可停止服务。
echo.
pause
