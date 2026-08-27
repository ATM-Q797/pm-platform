-- ============================================================
-- PM 平台数据库迁移 v3 — 项目状态改名（PROJECT_SHELVE §2.4）
-- ============================================================
-- 变更内容：
--   项目状态「已搁置」改名为「搁置」（阶段级「已搁置」不变，不在本脚本范围）
--   应用层双 key 兼容旧值，本迁移把存量数据统一到新值
--
-- 幂等：WHERE 限定旧值，重复执行无副作用（无「已搁置」项目时更新 0 行）
-- 语法：本地 SQLite 与服务器 PostgreSQL 通用
--
-- 执行方式：
--   服务器（PG，docker db 容器）：
--     docker compose -f deploy/docker/docker-compose.yml --env-file deploy/.env \
--       exec -T db psql -U $POSTGRES_USER -d $POSTGRES_DB -f - < deploy/migrate_v3.sql
--   本地（SQLite）：
--     sqlite3 backend/pm_platform.db < deploy/migrate_v3.sql
-- ============================================================

UPDATE project SET status = '搁置' WHERE status = '已搁置';
