#!/usr/bin/env bash
# ============================================================
# PM 平台数据库迁移（裸机部署）
# ============================================================
# 用法：bash /opt/pm-platform/deploy/migrate.sh
# 说明：读取 deploy/.env 配置，连接 docker db 容器执行迁移（幂等）
# ============================================================
set -euo pipefail

cd /opt/pm-platform/backend

# 加载 .env 并拼出数据库连接串
set -a
source ../deploy/.env
set +a
export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:5432/${POSTGRES_DB}"

echo "== 执行数据库迁移 =="
./venv/bin/python migrate_v2.py
