# Phase 6 开发执行计划

> **版本**: v1.0 | **日期**: 2026-08-13
> **依据**: `docs/PHASE6_PLAN.md`（功能规划）→ 本文档拆解为可执行任务
> **前置**: Phase 1-5 已完成并部署（认证/权限/审核/部署）

---

## 一、总体策略

| 维度 | 决策 | 理由 |
|------|------|------|
| **优先级** | 6.1 关键路径 > 6.2 资源冲突 > 6.3 看板增强 > 6.4 周报 | 价值/成本比排序；前两者后端算法独立、风险最小 |
| **依赖类型** | CPM 第一版只处理 FS，SS/FF/SF 按 FS 近似 | 实际场景 FS 占 90%+（规划风险对策同此） |
| **延期标记** | **计算式标记**（不写库）：`plan_end < 今天 && status ∉ {已完成,已搁置}` 即视为实际延期 | 避免"自动改状态"污染数据、不可逆（对规划的方案 A 修正） |
| **关键路径总工期** | 在**项目详情页**展示本项目关键路径工期，不塞进全局看板 | 对单项目更有意义；看板只做延期/到期/冲突计数 |
| **新依赖** | 仅新增 `jinja2`（后端周报）+ `react-markdown`（前端预览）；**不引入图表库** | 趋势图降级为文本列表，避免 antd-charts 大包（vendor 已 1.2MB） |
| **测试** | CPM 算法与冲突检测必须配单元测试（纯函数，易测） | 项目已有 pytest 基础设施 |

---

## 二、任务拆解

### T1 关键路径算法后端（CPM）

**文件**：`backend/app/services/critical_path.py`（新）+ `backend/app/routers/projects.py`（挂端点）+ `backend/app/schemas/project.py`（响应模型）+ `backend/tests/test_critical_path.py`（新）

**接口**：`GET /api/projects/{id}/critical-path`

**返回**：
```json
{
  "critical_phase_ids": [3, 5, 7],
  "total_duration": 45,
  "path": ["P1 需求评估", "P5 结构设计", "P7 联调测试"]
}
```

**算法**：
1. 收集项目所有阶段 + 依赖（FS 为主，SS/FF/SF 按 FS 近似）
2. 无日期阶段（plan_start/plan_end 均空）跳过计算（不参与关键路径）
3. 单日工期兜底：`end - start < 1` 按 1 天（复用 gantt_service._diff_days 模式）
4. 拓扑排序 → 正向求 ES/EF（取所有前驱的 EF 最大值 + 自身工期）→ 反向求 LS/LF（取所有后继的 LS 最小值 - 自身工期）
5. **总时差 = 0** 的阶段标记 critical；无依赖的项目：所有阶段都是关键路径
6. 多终点：对无后继的阶段统一从虚拟终点反向计算

**单元测试**：
- 链式依赖（A→B→C）：B 是关键路径，C 总时差 0
- 并行分支（A→B、A→C，B 长）：C 有浮动，B critical
- 无依赖项目：全部 critical
- 有阶段缺日期：跳过不报错
- 总工期正确性（最长路径天数）

---

### T2 甘特图关键路径高亮

**文件**：`frontend/src/components/Gantt/ganttConfig.ts`（task_class）+ `frontend/src/components/Gantt/gantt.css`（样式）+ `frontend/src/components/Gantt/GanttChart.tsx`（开关 + 数据获取）

**实现**：
1. GanttChart 加载甘特数据时并行请求 `critical-path` 接口，得到 `critical_phase_ids`
2. `ganttConfig.ts` 的 task_class 逻辑：`criticalIds.has(task.id)` → 追加 `gantt-task-critical`
3. CSS：
   ```css
   .gantt-task-critical { border: 3px solid #ff4d4f; box-shadow: 0 0 6px rgba(255,77,79,0.3); }
   ```
4. 工具栏新增「关键路径」Switch/Segmented（默认关），关闭时不请求/不渲染

**样式优先级**：与返工橙色边框共存时 → **critical 优先**（红色覆盖橙色，CSS 后声明 + `!important` 可选）

**验收**：开关切换即时生效；关键路径红色粗边醒目；与返工阶段共存显示正常

---

### T3 项目详情页关键路径工期

**文件**：`frontend/src/pages/ProjectDetailPage.tsx`

**实现**：详情页 Descriptions 增加"关键路径工期：X 天"（复用 T1 接口，随页面加载）

**验收**：详情页显示本项目关键路径总工期与路径阶段列表

---

### T4 资源冲突检测后端

**文件**：`backend/app/services/resource_conflicts.py`（新）+ `backend/app/routers/resources.py`（挂端点）+ `backend/tests/test_conflicts.py`（新）

**接口**：`GET /api/resources/conflicts`

**返回**：
```json
[
  {
    "resource_id": 5,
    "resource_name": "李四",
    "conflicts": [
      {
        "phase_a_id": 12, "phase_a_name": "结构设计", "project_a_id": 1, "project_a_name": "终端A",
        "phase_b_id": 34, "phase_b_name": "样机打样", "project_b_id": 2, "project_b_name": "终端B",
        "overlap_days": 5
      }
    ]
  }
]
```

**规则**（照规划 + 修正；2026-08-25 两轮优化：深度阈值 + 并行上限）：
1. 按 assignee 分组，取所有 assigned 阶段
2. **重叠判定用严格 `<`**：`max(start_a, start_b) < min(end_a, end_b)`（背靠背不视为冲突）
3. 同项目的两个阶段**不算冲突**（正常分工）
4. plan_start/plan_end 任一为 null → 跳过
5. 状态为 已完成/已搁置 → 跳过
6. 同一对阶段只报一次（避免 a/b 正反重复）
7. **深度阈值**：重叠天数 ≥ 10 天 **且** ≥ 较短阶段工期的 60%（同时满足）
8. **并行上限**：重叠窗口内该资源同时活跃的阶段数 ≤ 3 视为正常并行，不报冲突（≥4 才报）

**单元测试**：重叠/背靠背不冲突/同项目不冲突/缺日期跳过/已搁置跳过/去重/浅重叠不冲突/深度排序/并行≤3不报/并行≥4报

---

### T5 看板增强后端（延期/到期/冲突计数）

**文件**：`backend/app/routers/dashboard.py` + `backend/app/schemas/dashboard.py`

**扩展 `GET /api/dashboard/stats` 新增字段**：
- `delayed_phases`: [{ phase_id, phase_name, project_id, project_name, overdue_days }]（阶段级实际延期，计算式）
- `due_soon_phases`: [{ phase_id, phase_name, project_id, project_name, days_left }]（未来 7 天内到期且未完成）
- `due_soon_count`: int
- `conflict_count`: int（复用 T4 检测逻辑，统计冲突对数）

**注意**：现有 `delayed_projects`（项目级延期）保留不动，新增阶段级列表并存

**验收**：接口返回字段齐全；与 T4 冲突数一致

---

### T6 首页看板前端扩展

**文件**：`frontend/src/pages/DashboardPage.tsx` + `frontend/src/types/index.ts`

**实现**：
1. 卡片区 2×4 布局：原有 4 卡 + 新增「🟡 即将到期 N」「⚠️ 资源冲突 N」「🔴 阶段延期 N」
2. 新增卡片点击 → Drawer/Modal 展示明细列表（阶段名/项目名/超期天数），点击条目跳转对应项目甘特图
3. 趋势图**降级**：不引入图表库，延期列表按周聚合为简单文本/表格

**验收**：首页四类预警齐全；点击可看明细；跳转正常

---

> ⚠️ **2026-08-26：T7/T8 周报功能已整体移除**（用户决定：当前无实际用途，构思好后再开发）。
> 前端页面/导航/路由、后端 reports 路由与 weekly_report 服务已删除；
> `phase.updated_at` 列**保留**（onupdate 自动维护，未来周报复用无需迁移）。
> 本节内容仅作历史记录。

**文件**：`backend/app/services/weekly_report.py`（新）+ `backend/app/routers/reports.py`（新）+ `backend/requirements.txt`（+jinja2）+ `backend/tests/test_weekly_report.py`（新）

**接口**：`POST /api/reports/weekly`，body `{ project_ids?: number[] }`（不传 = 全部）

**内容**（照规划模板）：
1. 📊 整体进度概览（阶段总数/已完成/进行中/未开始/延期 + 完成率）
2. ⚠️ 风险预警（延期阶段 + 即将到期，均用计算式规则）
3. ✅ 本周完成（status 变为已完成 且 updated_at 在本周内——**先确认 operation_log 覆盖度，不足则用 Phase.updated_at 近似**）
4. 🔄 进行中（含进度 %）
5. 📅 下周计划（未开始且 plan_start 在下周）

**返回**：`{ markdown, plain_text, generated_at }`

**单元测试**：空项目列表/单项目/全部项目/无延期数据时模板不报错

---

### T8 周报前端页面

**文件**：`frontend/src/pages/ReportPage.tsx`（新）+ `frontend/src/App.tsx`（路由+导航）+ `frontend/package.json`（+react-markdown）

**实现**：
1. 导航新增「周报」入口（admin/manager 可见，与「审核中心」同级）
2. 页面：项目多选 Select（含"全部"）→「生成本周周报」→ react-markdown 预览
3. 底部：「复制 Markdown」「复制纯文本」按钮（navigator.clipboard）
4. 权限：路由守卫 + 后端 require_role("admin", "manager")

**验收**：管理员/负责人可见入口；工程师不可见；生成/预览/复制全流程可用

---

### T9 资源视图冲突标记（收尾，可选）

**文件**：`frontend/src/components/Resource/ResourceView.tsx` + `gantt.css`

**实现**：ResourceView 加载 conflicts 数据 → 冲突阶段的甘特条加黄色边框 + ⚠ 角标 + tooltip（"与 XX 项目·XX 阶段重叠 N 天"）

**验收**：资源视图中冲突阶段有黄色标记；hover 显示详情

---

## 三、实施顺序（两周）

```
第 1 周（T1→T4，后端为主）
  T1 关键路径 CPM + 测试 ───────┐
  T2 甘特图高亮 + 开关          ├─ 交付点 1：甘特图关键路径可视化
  T3 详情页工期显示             │
  T4 冲突检测 + 测试            ─┘（并行无依赖）

第 2 周（T5→T9，看板 + 周报）
  T5 看板后端扩展 ───────┐
  T6 首页卡片 + 明细      ├─ 交付点 2：看板预警完整
  T7 周报后端 + 测试      ─┐
  T8 周报页面              ├─ 交付点 3：周报可用
  T9 资源视图标记（收尾）  ─┘
```

**依赖关系**：T2 依赖 T1；T6 依赖 T5；T5 依赖 T4（复用冲突计数）；T3 依赖 T1；其余独立

---

## 四、验收标准汇总

- [ ] 甘特图可切换显示/隐藏关键路径（红色粗边），项目详情显示关键路径工期
- [ ] `/api/resources/conflicts` 返回准确重叠信息（背靠背不算、同项目不算）
- [ ] 首页显示阶段延期数、即将到期数、资源冲突数，可展开明细并跳转
- [ ] 周报可生成 Markdown 并一键复制，含概览/完成/进行中/延期/下周计划
- [ ] 新增算法均有 pytest 单元测试；全量 pytest + tsc + build 通过

---

## 五、风险与对策

| 风险 | 对策 |
|------|------|
| CPM 对 SS/FF/SF 依赖处理不准 | 第一版按 FS 近似，文档标注限制；实际数据 FS 占绝对多数 |
| 自动延期标记污染数据 | 不写库，全部计算式标记（本计划的核心修正） |
| 周报"本周完成"依赖日志覆盖 | 先核查 operation_log；不足则用 Phase.updated_at 近似，文档注明口径 |
| 关键路径与返工边框冲突 | CSS 优先级：critical > rework |
| 新依赖体积（react-markdown） | 按需 import + 代码分包（Vite 自动），不引入图表库 |
| 线上环境（已部署 v5）被开发影响 | 开发全程本地跑；部署版本不受影响，Phase 6 成熟后统一部署 |

---

## 六、开发约束（工作流规则）

1. **推送约束**：Phase 6 期间所有提交仅本地 `git commit`，**禁止 push 到 GitHub**，直到用户明确下达"上传"指令
2. 每个 T 任务完成时本地提交一次（提交信息带任务号，如 `feat(T1): 关键路径CPM算法`），方便回滚与审查
3. 涉及数据库的改动需评估迁移（本阶段**无表结构变更**，纯计算逻辑）
4. 每完成一个交付点（1/2/3）跑全量验证：pytest + tsc + build + 冒烟

---

> 🦞 | 2026-08-13
