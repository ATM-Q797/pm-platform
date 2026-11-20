#!/usr/bin/env bash
# ============================================================
# 智能终端研发项目管理平台 — 数据库定时备份脚本
# ============================================================
# 用法（一般由 crontab 调用，也可手动执行）：
#   ./deploy/backup.sh              # 日备（默认）
#   ./deploy/backup.sh --weekly     # 周备（另存 .env 副本）
#
# 设计（§2 批档）：
#   - pg_dump -Fc 在线逻辑备份（不停服、单文件压缩、一致性快照）
#   - 库在 docker 容器 docker-db-1（裸机混合生产形态），dump 经
#     docker exec 直落宿主机 /opt/backup/db/
#   - 每次备份后三查：PGDMP 魔数 / pg_restore --list 可读 / 大小阈值
#   - 周备附 deploy/.env 原样副本（chmod 600），防「卷损后取不出数据」
#   - 异机副本 rsync（未配置时明示跳过，不影响本机备份）
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
CONF_FILE="$SCRIPT_DIR/backup.conf"

# 可按需调整的默认值（env 可覆盖）
BACKUP_ROOT="${BACKUP_ROOT:-/opt/backup/db}"
LOG_FILE="${LOG_FILE:-/var/log/pm-backup.log}"
KEEP_DAILY="${KEEP_DAILY:-14}"
KEEP_WEEKLY="${KEEP_WEEKLY:-8}"
DB_CONTAINER="${DB_CONTAINER:-docker-db-1}"
MIN_DUMP_BYTES="${MIN_DUMP_BYTES:-1024}"

WEEKLY=0
[ "${1:-}" = "--weekly" ] && WEEKLY=1

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"; }

# ----------------------------------------------------------
# 0. 前置检查
# ----------------------------------------------------------
if [ ! -f "$ENV_FILE" ]; then
    echo "[错误] 未找到 $ENV_FILE（cp deploy/.env.example deploy/.env）" >&2
    exit 1
fi
mkdir -p "$BACKUP_ROOT"
touch "$LOG_FILE" 2>/dev/null || LOG_FILE="$BACKUP_ROOT/backup.log"   # 无权限写 /var/log 时降级到备份目录

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# ----------------------------------------------------------
# 1. 周日判定：周日走 weekly 保留通道（02:30 恰在 00:10 业务快照后）
# ----------------------------------------------------------
DOW=$(date +%u)   # 1=周一 … 7=周日
if [ "$DOW" = "7" ]; then
    WEEKLY=1
fi

TAG="daily"
[ "$WEEKLY" = "1" ] && TAG="weekly"

STAMP=$(date '+%Y-%m-%d-%H%M%S')
DUMP_FILE="$BACKUP_ROOT/pm_platform-$TAG-$STAMP.dump"

# ----------------------------------------------------------
# 2. 备份（docker exec 容器内 pg_dump，stdout 直落宿主机文件）
# ----------------------------------------------------------
log "开始备份 [$TAG] → $DUMP_FILE"
# pg_dump 不带 -f 时本就输出 stdout（postgres:16-alpine 实测 -f - 不可靠，2026-11-19）
docker exec "$DB_CONTAINER" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$DUMP_FILE"
chmod 600 "$DUMP_FILE"   # dump 含全部业务数据（人员/审计），与 .env 副本同权限口径

# ----------------------------------------------------------
# 3. 三查校验：非空+魔数 / pg_restore --list 可读 / 大小阈值
# ----------------------------------------------------------
SIZE=$(stat -c%s "$DUMP_FILE")
if [ "$SIZE" -lt "$MIN_DUMP_BYTES" ]; then
    log "[失败] 备份文件过小（$SIZE B < $MIN_DUMP_BYTES B），疑似空库或失败输出"
    rm -f "$DUMP_FILE"
    exit 1
fi

if [ "$(head -c 5 "$DUMP_FILE")" != "PGDMP" ]; then
    log "[失败] 文件魔数非 PGDMP，不是有效 pg_dump -Fc 归档"
    rm -f "$DUMP_FILE"
    exit 1
fi

if ! docker exec -i "$DB_CONTAINER" pg_restore --list < "$DUMP_FILE" > /dev/null 2>&1; then
    log "[失败] pg_restore --list 无法读取归档（TOC 损坏？）"
    rm -f "$DUMP_FILE"
    exit 1
fi

log "备份完成：$DUMP_FILE（$SIZE bytes）三查全过"

# ----------------------------------------------------------
# 4. 周备附加 .env 副本（仅权限 600）
# ----------------------------------------------------------
if [ "$WEEKLY" = "1" ]; then
    cp "$ENV_FILE" "$BACKUP_ROOT/env-$STAMP.env"
    chmod 600 "$BACKUP_ROOT/env-$STAMP.env"
    # .env 副本与对应周备同生命周期清理
    find "$BACKUP_ROOT" -name "env-*.env" -mtime +$((KEEP_WEEKLY * 7)) -delete
    log "周备附加 .env 副本：env-$STAMP.env"
fi

# ----------------------------------------------------------
# 5. 轮转清理
# ----------------------------------------------------------
find "$BACKUP_ROOT" -name "pm_platform-daily-*.dump" -mtime +$KEEP_DAILY -delete
find "$BACKUP_ROOT" -name "pm_platform-weekly-*.dump" -mtime +$((KEEP_WEEKLY * 7)) -delete

# ----------------------------------------------------------
# 6. 异机副本（未配置 backup.conf 时明示跳过——业务结果不变：
#    本机份已落盘并校验；配置后自动启用）
# ----------------------------------------------------------
if [ -f "$CONF_FILE" ]; then
    # shellcheck disable=SC1090
    source "$CONF_FILE"
    if [ -n "${REMOTE_TARGET:-}" ]; then
        log "推送异机副本 → $REMOTE_TARGET"
        # 参数数组化构造（评审轮次1 #2）：无引号展开会把 conf 里的字面引号切进参数，
        # 故非默认端口走专用 REMOTE_SSH_PORT，其余仅支持空格分隔的简单参数
        RSYNC_OPTS=()
        if [ -n "${REMOTE_SSH_PORT:-}" ]; then
            RSYNC_OPTS=(-e "ssh -p $REMOTE_SSH_PORT")
        fi
        read -r -a RSYNC_EXTRA <<< "${BACKUP_RSYNC_ARGS:-}"
        if rsync ${RSYNC_OPTS[@]+"${RSYNC_OPTS[@]}"} ${RSYNC_EXTRA[@]+"${RSYNC_EXTRA[@]}"} "$DUMP_FILE" "$REMOTE_TARGET/$TAG/"; then
            log "异机副本推送成功"
        else
            log "[警告] 异机副本推送失败（本机备份不受影响）"
        fi
        # 异机只留本机可见的推送日志；远端清理策略由远端自行配置
    else
        log "backup.conf 存在但 REMOTE_TARGET 为空，跳过异机副本"
    fi
else
    log "未配置 backup.conf，跳过异机副本（本机备份已就绪）"
fi
