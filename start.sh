#!/usr/bin/env bash
# 一键启动前后端开发服务（macOS / Linux）
#
# 用法：
#   ./start.sh
#
# 首次运行会自动：创建 venv → pip install → npm install → init_db.py
# 之后直接启动：后端 :8000 + 前端 :5173
# Ctrl+C 同时关闭两个服务。
set -euo pipefail

# 项目根目录（脚本所在目录）
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

echo "=================================================="
echo "  智能终端研发项目管理平台 — 一键启动"
echo "=================================================="

# ---------- 后端环境准备 ----------
echo ""
echo "[1/4] 检查后端虚拟环境..."
if [ ! -d "$BACKEND/venv" ]; then
  echo "  首次运行，创建虚拟环境..."
  python3 -m venv "$BACKEND/venv"
fi

echo "[2/4] 检查后端依赖..."
# 检测 fastapi 是否已安装（比检查 requirements 改动更可靠）
if ! "$BACKEND/venv/bin/python" -c "import fastapi" 2>/dev/null; then
  echo "  安装后端依赖..."
  "$BACKEND/venv/bin/pip" install -q -r "$BACKEND/requirements.txt"
else
  echo "  后端依赖已就绪"
fi

# ---------- 前端依赖准备 ----------
echo "[3/4] 检查前端依赖..."
if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "  首次运行，安装前端依赖..."
  cd "$FRONTEND" && npm install && cd "$ROOT"
else
  echo "  前端依赖已就绪"
fi

# ---------- 启动服务 ----------
echo "[4/4] 启动服务..."
echo ""
echo "  后端 API:  http://localhost:8000"
echo "  API 文档:  http://localhost:8000/docs"
echo "  前端应用:  http://localhost:5173"
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo "=================================================="
echo ""

# 清理函数：Ctrl+C 时杀掉两个子进程
cleanup() {
  echo ""
  echo "正在停止服务..."
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
  wait $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
  echo "已停止。"
  exit 0
}
trap cleanup INT TERM

# 启动后端（后台）
cd "$BACKEND"
"$BACKEND/venv/bin/uvicorn" app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# 启动前端（后台）
cd "$FRONTEND"
npm run dev &
FRONTEND_PID=$!

# 等待子进程（任一退出则全部停止）
wait
