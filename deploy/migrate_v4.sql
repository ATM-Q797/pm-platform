-- ============================================================
-- PM 平台数据库迁移 v4 — 项目分析：每日状态快照表（PROJECT_ANALYSIS §3.1）
-- ============================================================
-- 变更内容：
--   新增 status_snapshots——每日一行（snapshot_date 唯一，幂等约束）；
--   metrics 存原子计数 JSON（比率/差分在查询时计算，未来加图不改历史结构）
--
-- 幂等：CREATE TABLE IF NOT EXISTS，重复执行无副作用
-- 语法：服务器 PostgreSQL（JSONB/TIMESTAMPTZ/SERIAL）；
--       本地 SQLite 由应用层 create_all 自动建表（SQLAlchemy JSON 类型），不执行本脚本
--
-- 执行方式（服务器 PG，docker db 容器）：
--   docker compose -f deploy/docker/docker-compose.yml --env-file deploy/.env \
--     exec -T db psql -U $POSTGRES_USER -d $POSTGRES_DB -f - < deploy/migrate_v4.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS status_snapshots (
    id            SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL UNIQUE,
    metrics       JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
