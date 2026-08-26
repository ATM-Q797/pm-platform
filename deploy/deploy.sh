#!/usr/bin/env bash
# ============================================================
# 智能终端研发项目管理平台 — 一键部署脚本
# ============================================================
# 用法：
#   1. 在服务器上克隆仓库
#   2. cd pm-platform
#   3. cp deploy/.env.example deploy/.env && vim deploy/.env
#   4. chmod +x deploy/deploy.sh && ./deploy/deploy.sh
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

echo "=================================================="
echo "  智能终端研发项目管理平台 — 部署"
echo "=================================================="

# ----------------------------------------------------------
# 1. 检查环境变量文件
# ----------------------------------------------------------
if [ ! -f "$ENV_FILE" ]; then
    echo ""
    echo "[错误] 未找到 deploy/.env 文件"
    echo "  请先执行: cp deploy/.env.example deploy/.env"
    echo "  然后编辑 deploy/.env 填写必要配置"
    exit 1
fi

# 检查必填变量
source "$ENV_FILE"
if [ -z "${JWT_SECRET_KEY:-}" ]; then
    echo ""
    echo "[错误] JWT_SECRET_KEY 未设置"
    echo "  生成方式: python3 -c \"import secrets; print(secrets.token_urlsafe(48))\""
    echo "  将结果填入 deploy/.env 的 JWT_SECRET_KEY 字段"
    exit 1
fi

if [ "${POSTGRES_PASSWORD:-}" = "CHANGE_ME_TO_A_STRONG_PASSWORD" ] || [ -z "${POSTGRES_PASSWORD:-}" ]; then
    echo ""
    echo "[错误] POSTGRES_PASSWORD 未设置或仍为默认值"
    echo "  请在 deploy/.env 中设置一个强密码"
    exit 1
fi

echo ""
echo "[1/4] 环境检查通过"

# ----------------------------------------------------------
# 2. 检查 Docker
# ----------------------------------------------------------
if ! command -v docker &> /dev/null; then
    echo ""
    echo "[错误] 未安装 Docker"
    echo "  安装方式: curl -fsSL https://get.docker.com | sh"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo ""
    echo "[错误] Docker Compose V2 未安装"
    echo "  请安装 Docker Compose 插件: https://docs.docker.com/compose/install/"
    exit 1
fi

echo "[2/4] Docker 环境就绪"

# ----------------------------------------------------------
# 3. 构建并启动
# ----------------------------------------------------------
# 离线部署（内网无外网）时镜像由外部机器构建后导入，
# 通过 PM_SKIP_BUILD=1 跳过构建步骤（例如: PM_SKIP_BUILD=1 ./deploy/deploy.sh）
echo "[3/4] 准备镜像..."
cd "$SCRIPT_DIR/docker"
if [ "${PM_SKIP_BUILD:-0}" = "1" ]; then
    echo "    PM_SKIP_BUILD=1，跳过镜像构建（使用已导入的镜像）"
elif [ "${PM_FORCE_BUILD:-0}" = "1" ]; then
    echo "    PM_FORCE_BUILD=1，强制重新构建镜像..."
    docker compose --env-file "$ENV_FILE" build --pull
elif docker image inspect pm-backend:latest > /dev/null 2>&1; then
    echo "    检测到本地已存在 pm-backend:latest，跳过构建（如需强制重建: PM_FORCE_BUILD=1）"
else
    echo "    构建 Docker 镜像（首次可能需要几分钟）..."
    docker compose --env-file "$ENV_FILE" build --pull
fi

echo ""
echo "[4/4] 启动服务..."
# --force-recreate：确保容器用最新镜像重建（compose 默认容器已存在时不重建，
# 会继续用旧镜像实例运行，导致"更新了还是旧版"）
docker compose --env-file "$ENV_FILE" up -d --force-recreate

# 等待后端就绪
echo ""
echo "等待后端服务启动..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:${BACKEND_PORT:-8000}/health > /dev/null 2>&1; then
        echo "后端服务已就绪"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "[警告] 后端服务启动超时，请检查日志: docker compose logs backend"
    fi
    sleep 2
done

# ----------------------------------------------------------
# 4. 初始化数据库（首次部署）
# ----------------------------------------------------------
echo ""
echo "检查是否需要初始化数据库..."
if docker compose exec -T db pg_isready -U "${POSTGRES_USER:-pm_user}" -d "${POSTGRES_DB:-pm_platform}" > /dev/null 2>&1; then
    # 检查表是否存在
    TABLE_COUNT=$(docker compose exec -T db psql -U "${POSTGRES_USER:-pm_user}" -d "${POSTGRES_DB:-pm_platform}" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null | tr -d ' ' || echo "0")
    if [ "$TABLE_COUNT" = "0" ]; then
        echo "首次部署，初始化数据库..."
        docker compose exec -T backend python init_db.py
        echo "数据库初始化完成"
    else
        echo "数据库已有 $TABLE_COUNT 张表，跳过初始化"
    fi
fi

# ----------------------------------------------------------
# 完成
# ----------------------------------------------------------
echo ""
echo "=================================================="
echo "  部署完成！"
echo "=================================================="
echo ""
echo "  访问地址:  http://localhost:${HTTP_PORT:-80}"
echo "  后端 API:  http://localhost:${BACKEND_PORT:-8000}"
echo "  API 文档:  http://localhost:${BACKEND_PORT:-8000}/docs"
echo "  健康检查:  http://localhost:${BACKEND_PORT:-8000}/health"
echo ""
echo "  默认管理员账号: admin / admin123"
echo "  [重要] 首次登录后请立即修改密码！"
echo ""
echo "  常用命令:"
echo "    查看日志:  docker compose logs -f"
echo "    停止服务:  docker compose down"
echo "    重启服务:  docker compose restart"
echo "    备份数据库: docker compose exec db pg_dump -U $POSTGRES_USER $POSTGRES_DB > backup.sql"
echo ""
