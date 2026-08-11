-- ============================================================
-- 智能终端研发项目管理平台 — 数据库建表脚本
-- 数据库: SQLite
-- 说明: 供开发者参考，实际开发中由 SQLAlchemy ORM 自动建表。
--       本文件作为表结构权威定义，用于校验 ORM 模型一致性。
-- ============================================================

-- ------------------------------------------------------------
-- 1. resource（资源/人员）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS resource (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    role        TEXT,                    -- 岗位：工业设计/结构设计/测试/项目管理
    department  TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 2. template（项目模板）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS template (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    category    TEXT NOT NULL,           -- 新需求研发/量产交付/定制改造
    description TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 3. template_phase（模板阶段定义）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS template_phase (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id             INTEGER NOT NULL REFERENCES template(id) ON DELETE CASCADE,
    phase_type              TEXT NOT NULL,       -- P1-P8
    name                    TEXT NOT NULL,       -- 显示名称
    sequence                INTEGER NOT NULL,   -- 模板内顺序
    default_duration_days   INTEGER DEFAULT 7,
    default_assignee_role   TEXT,
    UNIQUE(template_id, sequence),
    UNIQUE(template_id, phase_type, name)
);

-- ------------------------------------------------------------
-- 4. template_dependency（模板依赖关系定义）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS template_dependency (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id     INTEGER NOT NULL REFERENCES template(id) ON DELETE CASCADE,
    from_phase_type TEXT NOT NULL,
    to_phase_type   TEXT NOT NULL,
    from_seq        INTEGER,   -- 可选：用 sequence 精确定位（同 phase_type 多阶段时必需，如模板B的多个P8）
    to_seq          INTEGER,   -- 为空时按 from_phase_type/to_phase_type 取该类型第一个阶段
    type            TEXT NOT NULL DEFAULT 'FS',  -- FS/SS/FF/SF
    lag_days        INTEGER DEFAULT 0
);

-- ------------------------------------------------------------
-- 5. project（项目）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS project (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,             -- 项目编号
    category    TEXT NOT NULL,                     -- 新需求/量产/定制/改造
    name        TEXT NOT NULL,                     -- 项目名称
    owner       TEXT NOT NULL,                     -- 项目负责人
    market      TEXT NOT NULL,                     -- 销售区域（拉美区/西欧区/...）
    status      TEXT NOT NULL DEFAULT '未开始',     -- 未开始/进行中/已完成/已搁置
    priority    TEXT,                              -- 高/中/低
    plan_start  DATE,
    plan_end    DATE,
    template_id INTEGER REFERENCES template(id),
    remark      TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 6. phase（阶段实例）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS phase (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    phase_type    TEXT NOT NULL,                   -- P1-P8
    name          TEXT NOT NULL,                   -- 阶段显示名称
    sequence      INTEGER NOT NULL,                -- 项目内顺序
    plan_start    DATE,
    plan_end      DATE,
    actual_start  DATE,
    actual_end    DATE,
    status        TEXT NOT NULL DEFAULT '未开始',   -- 未开始/进行中/已完成/延期/已搁置
    progress      INTEGER DEFAULT 0,               -- 0-100
    rework_count  INTEGER DEFAULT 0,
    remark        TEXT
);

-- ------------------------------------------------------------
-- 7. phase_assignee（阶段-人员多对多关联）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS phase_assignee (
    phase_id     INTEGER NOT NULL REFERENCES phase(id) ON DELETE CASCADE,
    resource_id  INTEGER NOT NULL REFERENCES resource(id) ON DELETE CASCADE,
    PRIMARY KEY (phase_id, resource_id)
);

-- ------------------------------------------------------------
-- 8. dependency（项目阶段间的依赖关系实例）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dependency (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    from_phase_id  INTEGER NOT NULL REFERENCES phase(id) ON DELETE CASCADE,
    to_phase_id    INTEGER NOT NULL REFERENCES phase(id) ON DELETE CASCADE,
    type           TEXT NOT NULL DEFAULT 'FS',     -- FS/SS/FF/SF
    lag_days       INTEGER DEFAULT 0,
    UNIQUE(from_phase_id, to_phase_id)
);

-- ------------------------------------------------------------
-- 9. rework_log（返工日志）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rework_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    phase_id    INTEGER NOT NULL REFERENCES phase(id) ON DELETE CASCADE,
    from_status TEXT NOT NULL,
    to_status   TEXT NOT NULL,
    reason      TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 索引
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_phase_project ON phase(project_id);
CREATE INDEX IF NOT EXISTS idx_phase_status ON phase(status);
CREATE INDEX IF NOT EXISTS idx_phase_type ON phase(phase_type);
CREATE INDEX IF NOT EXISTS idx_project_status ON project(status);
CREATE INDEX IF NOT EXISTS idx_project_market ON project(market);
CREATE INDEX IF NOT EXISTS idx_project_category ON project(category);
CREATE INDEX IF NOT EXISTS idx_dependency_from ON dependency(from_phase_id);
CREATE INDEX IF NOT EXISTS idx_dependency_to ON dependency(to_phase_id);
CREATE INDEX IF NOT EXISTS idx_assignee_phase ON phase_assignee(phase_id);
CREATE INDEX IF NOT EXISTS idx_assignee_resource ON phase_assignee(resource_id);
CREATE INDEX IF NOT EXISTS idx_rework_phase ON rework_log(phase_id);
