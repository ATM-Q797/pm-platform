#!/usr/bin/env bash
# ============================================================
# 智能终端研发项目管理平台 — 数据库恢复脚本
# ============================================================
# 用法：
#   ./deploy/restore.sh <dump文件> <目标库名>
#
# 示例：
#   ./deploy/restore.sh /opt/backup/db/pm_platform-daily-2026-11-19-023000.dump pm_platform
#   ./deploy/restore.sh /opt/backup/db/pm_platform-daily-xxx.dump pm_platform_restore_test   # 演练
#
# 设计（§2 批档）：
#   - 目标库显式传参，不设默认——杜绝误覆盖生产库
#   - 覆盖 = 整库替换：目标库已存在时断连 → DROP → 重建
#     （pg_restore 无 --clean 时向已存在的非空库恢复必然冲突回滚——评审轮次1 #1；
#      整库替换而非 --clean，防新旧对象混杂出脏数据）
#   - 目标为 pm_platform（生产库）时：先输入确认，再停 pm-backend——
#     连接池占着库 DROP 必失败；且后端崩溃重启会 create_all 空表与恢复冲突，
#     必须先停再动库
#   - pg_restore -1 --exit-on-error：单事务原子恢复，任何一步失败整体回滚
#   - 恢复生产库后自动重启 pm-backend 并做健康检查
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
BACKEND_SVC="${BACKEND_SVC:-pm-backend}"

if [ $# -ne 2 ]; then
    echo "用法: $0 <dump文件> <目标库名>" >&2
    echo "示例: $0 /opt/backup/db/pm_platform-daily-xxx.dump pm_platform" >&2
    exit 1
fi

DUMP_FILE="$1"
TARGET_DB="$2"

[ -f "$DUMP_FILE" ] || { echo "[错误] dump 文件不存在: $DUMP_FILE" >&2; exit 1; }

# 库名合法性（防注入/防误操作：仅字母数字下划线，字母或下划线开头）
if ! [[ "$TARGET_DB" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "[错误] 库名不合法（仅允许字母/数字/下划线）: $TARGET_DB" >&2
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "[错误] 未找到 $ENV_FILE" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# 默认值在 source .env 之后取（与 backup.sh 一致，.env 可覆盖）
DB_CONTAINER="${DB_CONTAINER:-docker-db-1}"

# ----------------------------------------------------------
# dump 预检（PGDMP 魔数 + pg_restore --list 可读）——坏份在任何破坏性动作
# （确认/停服/DROP）之前拒绝（评审轮次3 #8：防「旧库已 DROP、恢复又失败」）
# ----------------------------------------------------------
DUMP_MAGIC="$(head -c 5 "$DUMP_FILE" 2>/dev/null || true)"
if [ "$DUMP_MAGIC" != "PGDMP" ]; then
    echo "[错误] dump 预检失败：文件头非 PGDMP（可能损坏或非 -Fc 归档）: $DUMP_FILE" >&2
    exit 1
fi
if ! docker exec -i "$DB_CONTAINER" pg_restore --list < "$DUMP_FILE" > /dev/null 2>&1; then
    echo "[错误] dump 预检失败：pg_restore --list 无法读取（归档损坏）: $DUMP_FILE" >&2
    exit 1
fi
echo "dump 预检通过: $DUMP_FILE"

IS_PROD=0
if [ "$TARGET_DB" = "${POSTGRES_DB:-pm_platform}" ]; then
    IS_PROD=1
fi

# ----------------------------------------------------------
# 生产库确认（防误操作；取消则后端不受任何影响）
# ----------------------------------------------------------
if [ "$IS_PROD" = "1" ]; then
    echo "⚠️  目标是生产库 [$TARGET_DB]，恢复将覆盖其全部数据！"
    if ! read -r -p "确认恢复请输入库别名 [${TARGET_DB}]: " CONFIRM; then
        echo "已取消（未收到确认输入）"
        exit 1
    fi
    [ "$CONFIRM" = "$TARGET_DB" ] || { echo "已取消"; exit 1; }
fi

# ----------------------------------------------------------
# 生产库：先停后端再动库
# （连接池占库 → DROP 必失败；后端崩溃重启会 create_all 空表与恢复冲突）
# ----------------------------------------------------------
if [ "$IS_PROD" = "1" ]; then
    echo "停止后端服务 $BACKEND_SVC ..."
    systemctl stop "$BACKEND_SVC"
fi

# ----------------------------------------------------------
# 覆盖语义：已存在 → 断连 + DROP 再重建；不存在 → 直接创建
# ----------------------------------------------------------
if docker exec "$DB_CONTAINER" psql -U "$POSTGRES_USER" -d postgres -tAc \
     "SELECT 1 FROM pg_database WHERE datname='$TARGET_DB'" | grep -q 1; then
    echo "目标库已存在，覆盖 = 断连后 DROP 再重建: $TARGET_DB"
    docker exec "$DB_CONTAINER" psql -U "$POSTGRES_USER" -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$TARGET_DB' AND pid <> pg_backend_pid()" > /dev/null
    docker exec "$DB_CONTAINER" psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE \"$TARGET_DB\""
fi

echo "创建目标库: $TARGET_DB"
docker exec "$DB_CONTAINER" psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE \"$TARGET_DB\" OWNER \"$POSTGRES_USER\""

# ----------------------------------------------------------
# 单事务原子恢复
# ----------------------------------------------------------
echo "开始恢复 $DUMP_FILE → $TARGET_DB ..."
docker exec -i "$DB_CONTAINER" pg_restore -U "$POSTGRES_USER" -d "$TARGET_DB" \
    -1 --exit-on-error --no-owner --no-privileges < "$DUMP_FILE"
echo "恢复完成。"

# ----------------------------------------------------------
# 生产库：重启后端 + 健康检查
# ----------------------------------------------------------
if [ "$IS_PROD" = "1" ]; then
    echo "重启后端服务 $BACKEND_SVC ..."
    systemctl start "$BACKEND_SVC"
    for i in $(seq 1 15); do
        if curl -sf http://127.0.0.1:8000/health > /dev/null 2>&1; then
            echo "后端健康检查通过"
            exit 0
        fi
        sleep 2
    done
    echo "[警告] 后端健康检查未通过，请查: journalctl -u $BACKEND_SVC -n 50" >&2
    exit 1
fi
