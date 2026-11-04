-- ============================================================
-- v5：站内通知表（二期①，用户 2026-11-04）
-- 幂等：可重复执行。仅新增表，不改既有表结构。
-- 执行：bash deploy/migrate.sh 或 psql -f migrate_v5.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS notification (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES user_account(id) ON DELETE CASCADE,
    type       VARCHAR NOT NULL,
    title      VARCHAR NOT NULL,
    body       TEXT,
    link       VARCHAR,
    read_at    TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_notification_user_id    ON notification (user_id);
CREATE INDEX IF NOT EXISTS ix_notification_type       ON notification (type);
CREATE INDEX IF NOT EXISTS ix_notification_created_at ON notification (created_at);
