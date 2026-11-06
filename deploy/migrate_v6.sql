-- ============================================================
-- v6：过程事件表（P1 过程事件地基，用户 2026-11-06 批复 PHASE8_PLAN §九 方案 B）
-- 幂等：可重复执行。仅新增表，不改既有表结构。
-- 执行：bash deploy/migrate.sh 或 psql -f migrate_v6.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS data_change_events (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER REFERENCES project(id) ON DELETE SET NULL,
    phase_id        INTEGER REFERENCES phase(id)   ON DELETE SET NULL,
    field           VARCHAR NOT NULL,
    old_value       TEXT,
    new_value       TEXT,
    source          VARCHAR NOT NULL,
    -- direct_edit | report_edit | approval | rework
    changed_by      INTEGER REFERENCES user_account(id) ON DELETE SET NULL,
    -- 冗余身份字段：删项目/删阶段/删用户后事件仍可读（追溯口径同 8-3）
    changed_by_name VARCHAR,
    project_name    VARCHAR,
    phase_name      VARCHAR,
    reason          TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_dce_project_id  ON data_change_events (project_id);
CREATE INDEX IF NOT EXISTS ix_dce_phase_id    ON data_change_events (phase_id);
CREATE INDEX IF NOT EXISTS ix_dce_field       ON data_change_events (field);
CREATE INDEX IF NOT EXISTS ix_dce_source      ON data_change_events (source);
CREATE INDEX IF NOT EXISTS ix_dce_created_at  ON data_change_events (created_at);
