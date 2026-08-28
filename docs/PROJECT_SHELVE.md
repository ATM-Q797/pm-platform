# 项目「搁置」状态 — 改名 + 看板/冲突排除

> **版本**: v1.1 | **日期**: 2026-08-27 | **状态**: 待评审（评审处置 1/2/3/4 已并入，🟡#2 决策已落定）
> **需求**: 项目主进度增加「搁置」状态（假完成态），看板不报警、退出资源冲突检测
> **用户决策**: ① 状态名「已搁置」→「搁置」；② 搁置项目的阶段退出资源冲突检测

---

## 一、范围界定

**改名只作用于「项目级」状态**（用户需求是"项目主进度"）：

| 层级 | 处理 |
|------|------|
| 项目状态 | 「已搁置」→「**搁置**」✅ 本次改动 |
| 阶段状态 | 「已搁置」**保持不变**（甘特 blocked 色/阶段编辑器/Excel 模板下拉均不动） |

「搁置」语义 = **假完成**：项目不再参与任何进度报警、不占资源。

---

## 二、改动清单

### 2.1 状态名替换（项目级）

| 文件 | 改动 |
|------|------|
| `backend/app/models/project.py:32` | 注释 已搁置→搁置 |
| `backend/app/schemas/project.py:20` | 注释同步 |
| `frontend/src/types/index.ts:18` | 注释同步 |
| `frontend/src/pages/ProjectListPage.tsx:20,451,582` | STATUS_COLOR key、筛选 options（两处：筛选条+编辑弹窗） |
| `frontend/src/pages/ProjectDetailPage.tsx:15` | STATUS_COLOR key |

**存量数据兼容**：库里可能已有 `status='已搁置'` 的项目——
- 数据迁移：`UPDATE project SET status='搁置' WHERE status='已搁置'`（migrate_v3，本地 SQLite + 服务器 PG）
- 前端兜底：STATUS_COLOR/筛选**双 key 兼容**（`已搁置` 与 `搁置` 同色同选项），迁移未跑的环境也不显示无色 Tag

### 2.2 看板报警排除（搁置项目 = 不报警）

`backend/app/routers/dashboard.py`：
- 延期阶段（约 103 行）、即将到期阶段（约 126 行）：查询** join 项目**，排除 `Project.status == '搁置'` 的阶段的（现有 `_ACTIVE_STATUSES` 只过滤了项目级延期；阶段级报警需补项目 join）
- 项目级延期/统计已排除（`_ACTIVE_STATUSES = 未开始/进行中` 不含搁置），不改

### 2.3 资源冲突退出（用户决策 ②）

`backend/app/services/resource_conflicts.py`：
- 跳过**所属项目状态为「搁置」（含旧值「已搁置」，双 key 兼容——评审处置 #7）**的阶段（`_active_phases` 或 detect_conflicts 内 join Project 判断）
- 现有 `_SKIP_STATUSES = (已完成, 已搁置)` 是**阶段级**跳过，保留不动

### 2.5 资源负载视图（评审处置 #3：「不占资源」语义完整化）

`backend/app/routers/resources.py`（`/all/workload` 与 `/{resource_id}/workload`）：
- **排除所属项目状态为「搁置」（含旧值「已搁置」）的阶段**——搁置项目不占用任何资源负载统计（甘特/热力/负载口径一致）
- 阶段级「已搁置」保持原有跳过逻辑（`_SKIP_STATUSES`）

### 2.4 迁移脚本

`deploy/migrate_v3.sql`（或并入现有 migrate 机制）：
```sql
UPDATE project SET status='搁置' WHERE status='已搁置';
```
本地 SQLite 同步执行一次；服务器随部署执行。

---

## 三、测试用例

| # | 场景 | 预期 |
|---|------|------|
| 1 | 项目状态='搁置'，其阶段 plan_end<今天 | delayed_phases 不含该阶段（join 排除） |
| 2 | 项目状态='搁置'，其阶段 7 天内到期 | due_soon_phases 不含该阶段 |
| 3 | 搁置项目的阶段与其他阶段重叠（深度冲突） | 不产生冲突对（加入排除） |
| 4 | 阶段级已搁置（原行为） | 仍跳过（回归，_SKIP_STATUSES 不变） |
| 5 | 项目更新接口传 status='搁置' | 保存成功；传'已搁置'不校验通过（或兼容？——见决策点） |
| 6 | 迁移后旧值 | '已搁置' 数据变 '搁置'；前端 Tag 正常显示 |

---

## 四、决策记录（评审处置后已定）

| # | 决策 | 结论 |
|---|------|------|
| 1 | 项目更新接口接受旧值「已搁置」吗？ | ~~接受并归一化~~ → **2026-08-28 起不再接受**：库中旧值已全部迁移（本地库实测 0 条），兼容移除，非法值（含「已搁置」）一律 422——用户决策"彻底清理" |
| 2 | 阶段级「已搁置」改名吗？ | **不改**（与 §一 范围界定一致；阶段级是阶段自身状态，保留） |
| 3 | 现有资源甘特视图如何处理搁置项目？ | **排除**（§2.5，评审处置 #3——搁置不占资源，甘特/热力/负载口径统一） |
| 4 | 后端过滤键 | ~~双 key~~ → **单 key（「搁置」）**（2026-08-28 随决策 1 一并收敛：dashboard/conflicts/heatmap 三处 `_SHELVED_PROJECT_STATUSES` 移除旧值） |
| 5 | 前端双 key 兼容 | **移除**（2026-08-28：STATUS_COLOR/筛选/编辑 options 均只剩「搁置」；后端对源码的静态契约测试同步反转） |

---

## 五、涉及文件汇总

```
backend/app/models/project.py          注释
backend/app/schemas/project.py         注释 + 状态归一化（决策点 1）
backend/app/routers/dashboard.py       阶段级报警 join 排除搁置项目
backend/app/services/resource_conflicts.py  跳过搁置项目阶段
backend/tests/test_dashboard_ext.py    用例 1/2
backend/tests/test_conflicts.py        用例 3/4
backend/tests/test_shelve_status.py（新） 用例 5/6 + 迁移
deploy/migrate_v3.sql（新）            数据迁移
frontend/src/types/index.ts            注释
frontend/src/pages/ProjectListPage.tsx 双 key 兼容 + options
frontend/src/pages/ProjectDetailPage.tsx 双 key 兼容
```

---

## 六、验收标准

- [ ] 前端：列表/详情状态显示「搁置」，筛选/编辑可选；旧值「已搁置」Tag 不无色
- [ ] 看板：搁置项目的延期阶段、到期阶段**不报警**
- [ ] 资源冲突：搁置项目阶段**不产生冲突对**
- [ ] 阶段级「已搁置」行为完全不变（回归）
- [ ] pytest 全绿；迁移脚本本地+PG 可执行

> 评审通过后由 eng-coder 实施。
> 🦞 | 2026-08-27
