# 项目分析功能 — 趋势快照与看板分析弹窗 设计文档

> **版本**: v1.0 | **日期**: 2026-10-26 | **状态**: 已批准（2026-10-26 用户裁定，随裁定修订后实施）
> **需求来源**: `docs/需求-分析功能与共享表更新-2026-10-16.md` 需求 1（历史趋势分析——状态快照机制）

最近先例：`docs/OPTIMIZATION_PLAN.md` §2.2（user_favorite 先例——本地 SQLite 由 create_all 自动建表、生产 PG 用幂等迁移 SQL，本功能同法）；统计口径沿用 `backend/app/routers/dashboard.py`（延期/到期/冲突）与 `backend/app/services/resource_heatmap.py`（峰值并行/活跃人员）。
调研证据：已查需求文档（指标论证与排除项）、PHASE6_DEV_PLAN §T5（看板口径）、dashboard.py / resource_heatmap.py / resource_conflicts.py 实现；2026-10-26 生产库实测确认 created_at 不可用（全库为导入时间）、返工 0 条——排除项据此定案。

## 一、用户裁定（2026-10-26，约束性）

1. **专项项目暂不纳入统计范围**——本功能全部指标排除 `project.is_special = true` 的项目。
2. **不新增页面**——看板页新增「项目分析」按钮，点击即分析、弹窗展示。
3. **支持导出 PDF**。
4. 其余按 2026-10-26 提案执行：M1 快照机制 + M2 趋势弹窗、ECharts 图表、`migrate_v4.sql`、crontab 触发、无历史回填。

> 口径注记：裁定 1 与看板"项目状态分布含专项"的全量口径**有意不同**（分析功能排除专项）；延期/到期/冲突/并行类指标与看板天然同口径（dashboard 及资源服务本就排除专项与搁置）。

## 二、指标与口径

快照存**原子计数**（JSON），比率/差分在查询时计算——未来加图不改历史快照结构。

| 指标（metrics 键） | 口径 | 来源 |
|---|---|---|
| projects_total / projects_by_status{进行中,已完成,搁置,未开始} | 排除专项的项目计数（裁定 1） | Project |
| delayed_projects / delayed_phases / delayed_days_p50 / p90 | plan_end < 今天 且状态 ∉{已完成,搁置} 且项目未搁置且非专项；p50/p90 取逾期天数分位 | dashboard 同口径 |
| due_soon_phases | plan_end ∈ [今天, +7]，排除同上 | dashboard 同口径 |
| conflict_pairs | 复用 `resource_conflicts.detect_conflicts`（P8/P9/P71/P72 排除族、专项/搁置排除已内含） | 资源服务 |
| active_people / peak_parallel_top3_avg | 热力图口径（`resource_heatmap` 已排除专项/搁置）；top3 均值 = 峰值并行前 3 人均值 | 热力图服务 |
| open_phases | 未完成阶段数（状态 ∉{已完成,搁置}，排除专项项目） | Phase |
| completed_phases_total | 累计已完成阶段数（排除专项）→ 周差分得"每周完成阶段数" | Phase |
| shelved_total | 累计搁置项目数 → 周差分近似"转搁置项目数" | Project |

**排除项（定案）**：每期新增项目数（created_at 为导入时间，数据不可用）；里程碑达成率（actual_end 覆盖 66%）、返工率（全库 0 条）、平均项目完成度（口径易误读）——均不纳入。

## 三、技术方案

### 3.1 数据模型（`deploy/migrate_v4.sql`，幂等；本地 SQLite 由 create_all 建表）

```sql
CREATE TABLE IF NOT EXISTS status_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL UNIQUE,
    metrics JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

模型 `backend/app/models/status_snapshot.py`：`StatusSnapshot(id, snapshot_date Unique, metrics JSON, created_at)`（SQLAlchemy JSON 类型 SQLite/PG 通吃）。

### 3.2 后端

- **dashboard.py 最小重构**：`get_dashboard_stats` 的统计主体抽取为模块级纯函数 `build_dashboard_stats(db)`，路由行为不变（存量 test_dashboard_ext 必须全绿）；看板与快照共用 → 同口径单一来源。
- **services/snapshot.py**：`collect_metrics(db)`（= build_dashboard_stats + §二扩展指标）；`create_today_if_absent(db)`（幂等：当日已有即跳过）。
- **jobs/snapshot.py**：独立 CLI（`python -m app.jobs.snapshot`，自建 SessionLocal）——crontab 入口，绕开 HTTP 鉴权与 gunicorn 多 worker 重复执行问题。
- **routers/analysis.py**：
  - `POST /api/analysis/snapshots/run`（admin，手动触发/部署日建基线；幂等：首次 201 建行、同日 200 skipped）
  - `GET /api/analysis/trend?days=30|90|180`（登录即可，与看板一致）——返回日级点位 + 周级聚合（周一锚点；差分查询时算）

### 3.3 前端

- `DashboardPage.tsx` 头部操作区新增「项目分析」按钮 → `src/components/Analysis/AnalysisModal.tsx`。
- Modal（~960px）：顶部 30/90/180 天 Segmented + 三 Tab（交付健康 / 规模与吞吐 / 资源）；ECharts **按需引入**（`echarts/core` + LineChart/Grid/Tooltip/Legend，不引封装库），动态 import 分包；快照不足时显示空态提示。
- **导出 PDF**：html2canvas + jspdf（均动态 import），将弹窗内容渲染为 PDF 下载，文件名 `项目分析-YYYYMMDD.pdf`。
- `src/api/analysis.ts` + `src/types/index.ts` 类型同步。

### 3.4 定时（服务器 crontab，部署时由父级安装）

```
10 0 * * * cd /opt/pm-platform/backend && ./venv/bin/python -m app.jobs.snapshot >> /opt/pm-platform/logs/snapshot.log 2>&1
```

## 四、验收标准

1. `pytest` 全绿（基线 199 passed / 7 skipped + 新增 `tests/test_snapshot.py`）。
2. `cd frontend && npm run build` 通过（tsc 无错）。
3. `migrate_v4.sql` 服务器执行成功且幂等（重复执行无错）。
4. `POST /api/analysis/snapshots/run`：首次建行、同日再调 skipped；`status_snapshots` 当日恰 1 行。
5. 单测断言：专项项目不计入任何指标；搁置项目延期不计入；trend 差分/周聚合正确。
6. 看板页出现「项目分析」按钮 → 弹窗三 Tab 出图 → 导出 PDF 生成文件。
7. 服务器 `crontab -l` 含快照任务行（部署时安装；部署当日手动触发首次快照作基线）。
8. 生产核验：快照的 延期阶段/7天到期/冲突对 三项与看板当日数字一致（这三项与看板同口径）。

## 五、不做的事（范围外）

维度统计页、健康度评分（二期）；共享表直连更新（需求 2，等用户对 Grist / OnlyOffice+Nextcloud 选型）；历史回填；通知推送；里程碑/返工指标。
