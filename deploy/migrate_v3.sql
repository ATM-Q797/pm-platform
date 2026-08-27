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

-- ============================================================
-- CONFLICT_MODEL_V2 §2.3：冲突手动消除记录表（幂等建表）
-- 粒度 = 资源 × 冲突对（a/b 归一化小 id 在前）；FK 级联删除
-- 应用层 create_all 也会幂等建表，此 DDL 供手工迁移部署使用
-- ============================================================
CREATE TABLE IF NOT EXISTS conflict_override (
    id          INTEGER PRIMARY KEY,                       -- PG: SERIAL（由 ORM create_all 生成序列，此处手工建表用 INTEGER 兼容 SQLite）
    resource_id INTEGER NOT NULL REFERENCES resource(id) ON DELETE CASCADE,
    phase_a_id  INTEGER NOT NULL REFERENCES phase(id) ON DELETE CASCADE,
    phase_b_id  INTEGER NOT NULL REFERENCES phase(id) ON DELETE CASCADE,
    reason      TEXT    NOT NULL,
    created_by  INTEGER REFERENCES user_account(id) ON DELETE SET NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_conflict_override_pair
    ON conflict_override (resource_id, phase_a_id, phase_b_id);
CREATE INDEX IF NOT EXISTS ix_conflict_override_resource_id
    ON conflict_override (resource_id);
