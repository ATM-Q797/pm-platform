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

-- ============================================================
-- 8-3：项目快照表（PHASE8_PLAN §三 方案 A + 存储口径③，用户 2026-11-04/11-10 批复）
-- 追加语义：只新增表/索引/函数，不触碰上方 data_change_events 任何结构。
-- 幂等：全部 DDL 带 IF NOT EXISTS / CREATE OR REPLACE，重跑仅补建缺失对象。
-- ============================================================

CREATE TABLE IF NOT EXISTS project_snapshots (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER REFERENCES project(id) ON DELETE SET NULL,
    -- 不用 CASCADE：删项目要能追溯（用户裁定），行保留、编号/名称冗余在行内
    snapshot_date   DATE NOT NULL,
    metrics         JSONB NOT NULL,
    -- 快照时点定格的 metrics（plan_cum_pct / actual_cum_pct / delayed_phases / conflict_pairs）
    project_code    VARCHAR,
    project_name    VARCHAR,
    -- 冗余身份字段：项目删除（project_id SET NULL）后按编号仍可查历史曲线
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_project_snapshots_project_date UNIQUE (project_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS ix_ps_project_id   ON project_snapshots (project_id);
CREATE INDEX IF NOT EXISTS ix_ps_snapshot_date ON project_snapshots (snapshot_date);
CREATE INDEX IF NOT EXISTS ix_ps_created_at   ON project_snapshots (created_at);
-- by-code 追溯查询（project_id 为 NULL 的被删项目按编号寻址）用的函数索引
CREATE INDEX IF NOT EXISTS ix_ps_project_code ON project_snapshots (project_code);

-- ------------------------------------------------------------
-- 分层降采样维护函数（口径③：90 天内日粒度 → 2 年内周粒度（周一锚点）→ 2 年以上月粒度（月初）；
-- 保留策略：日粒度留 90 天、周粒度留 2 年、月粒度永久。幂等可重跑，crontab 周任务执行）
-- 粒度标记记在 metrics._granularity（day/week/month），读侧按它识别行粒度。
-- 被删项目（project_id 已 SET NULL）的行不聚合不删除——项目删除后不再产生新行，
-- 行数以该项目存续期为上界，冻结保留即可追溯（PHASE8_PLAN §3.3 追溯设计）。
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION maintain_project_snapshots()
RETURNS INTEGER AS $$
DECLARE
    moved_weeks  INTEGER;
    moved_months INTEGER;
    deleted_rows INTEGER;
BEGIN
    -- 1) 90 天前的日行（在办项目）→ 聚合为周行（周一锚点），每周取周内最后一个快照的 metrics 作代表。
    --    ON CONFLICT 走 (project_id, snapshot_date) 唯一约束 → 重跑幂等。
    WITH week_src AS (
        SELECT project_id, project_code, project_name,
               (snapshot_date - (extract(isodow FROM snapshot_date)::int - 1))::date AS week_start,
               max(snapshot_date) AS last_day
        FROM project_snapshots
        WHERE metrics->>'_granularity' = 'day'
          AND project_id IS NOT NULL
          AND snapshot_date < CURRENT_DATE - INTERVAL '90 days'
        GROUP BY project_id, project_code, project_name, week_start
    ), upsert_week AS (
        INSERT INTO project_snapshots (project_id, snapshot_date, metrics, project_code, project_name)
        SELECT ws.project_id, ws.week_start,
               jsonb_build_object('_granularity', 'week') || ps.metrics,
               ws.project_code, ws.project_name
        FROM week_src ws
        JOIN project_snapshots ps
          ON ps.project_id = ws.project_id
         AND ps.snapshot_date = ws.last_day
         AND ps.metrics->>'_granularity' = 'day'
        ON CONFLICT (project_id, snapshot_date) DO UPDATE
            SET metrics = EXCLUDED.metrics,
                project_code = EXCLUDED.project_code,
                project_name = EXCLUDED.project_name
        RETURNING 1
    )
    SELECT count(*) INTO moved_weeks FROM upsert_week;

    -- 2) 2 年前的周行/日行（在办项目）→ 聚合为月行（月初锚点），每月取最后一个快照作代表
    WITH month_src AS (
        SELECT project_id, project_code, project_name,
               date_trunc('month', snapshot_date)::date AS month_start,
               max(snapshot_date) AS last_day
        FROM project_snapshots
        WHERE metrics->>'_granularity' IN ('day', 'week')
          AND project_id IS NOT NULL
          AND snapshot_date < CURRENT_DATE - INTERVAL '2 years'
        GROUP BY project_id, project_code, project_name, month_start
    ), upsert_month AS (
        INSERT INTO project_snapshots (project_id, snapshot_date, metrics, project_code, project_name)
        SELECT ms.project_id, ms.month_start,
               jsonb_build_object('_granularity', 'month') || ps.metrics,
               ms.project_code, ms.project_name
        FROM month_src ms
        JOIN project_snapshots ps
          ON ps.project_id = ms.project_id
         AND ps.snapshot_date = ms.last_day
         AND ps.metrics->>'_granularity' IN ('day', 'week')
        ON CONFLICT (project_id, snapshot_date) DO UPDATE
            SET metrics = EXCLUDED.metrics,
                project_code = EXCLUDED.project_code,
                project_name = EXCLUDED.project_name
        RETURNING 1
    )
    SELECT count(*) INTO moved_months FROM upsert_month;

    -- 3) 删除已上卷的源行（project_id 非空者已被上方 CTE 全量覆盖）：
    --    日行 < 90 天 → 周行已带其数据；周/日行 < 2 年 → 月行已带其数据。
    DELETE FROM project_snapshots
    WHERE metrics->>'_granularity' = 'day'
      AND project_id IS NOT NULL
      AND snapshot_date < CURRENT_DATE - INTERVAL '90 days';
    GET DIAGNOSTICS deleted_rows = ROW_COUNT;

    DELETE FROM project_snapshots
    WHERE metrics->>'_granularity' IN ('day', 'week')
      AND project_id IS NOT NULL
      AND snapshot_date < CURRENT_DATE - INTERVAL '2 years';
    GET DIAGNOSTICS deleted_rows = deleted_rows + ROW_COUNT;

    RETURN moved_weeks + moved_months + deleted_rows;
END;
$$ LANGUAGE plpgsql;
