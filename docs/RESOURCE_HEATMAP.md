# 资源负载「热力矩阵」视图 — 设计文档

> **版本**: v1.2 | **日期**: 2026-08-27 | **状态**: 待评审（评审处置 1-10 已并入）
> **需求**: 项目增多后资源负载甘特（192 行）翻页/滚动难直观判断员工负载——需要"谁忙/谁闲/谁撞车"一眼可读的预览形态
> **方案基础**: 用户选定方案 A（员工 × 时间负载热力矩阵），双 Tab 保留甘特

---

## 一、形态总览

```
┌────────────────────────────────────────────────────────────┐
│ [热力图] [甘特]        ← 双 Tab（默认热力图）               │
│                                                             │
│  时间窗口: [4周] [12周] [24周] [全部]   粒度: [周] [月]     │
│  今日  ▏                                              2026-11 │
│  人员(负载↓)   W1   W2   W3   W4   W5   W6   W7   W8   负载 │
│  张三          ░░   ░░   ██   ██   ░░   ░░   ░░   ░░   2并行│
│  李四          ██   ███  ██   ░░   ░░   ░░   ░░   ░░   3并行│
│  王五          ░░   ░░   ░░   ████ ████ ░░   ░░   ░░   2并行│
│  赵六          ░░   ░░   ░░   ░░   ░░   ░░   ░░   ░░   1并行│
│  (无负载人员折叠在底部"空闲"区)                              │
└────────────────────────────────────────────────────────────┘
```

- **Y 轴** = 人员（按负载峰值降序；空闲人员折叠到尾部"空闲"区）
- **X 轴** = 时间周期（周/月两档粒度；窗口 4/12/24 周/全部，今日竖线标记）
- **格子值** = 该人员该周期内**相交的活跃阶段数**（忙碌度代理：计划窗口与周期相交 && 阶段非已完成/已搁置 && 所属项目非搁置；精确"同时活跃"由行尾 peak_parallel 给出——评审处置 #5）
- **颜色分级**：
  | 活跃数 | 深色主题 | 浅色主题 |
  |---|---|---|
  | 0 | 透明（空） | 透明（空） |
  | 1 | `rgba(0,212,255,0.25)` | `rgba(3,105,161,0.18)` |
  | 2 | `rgba(0,212,255,0.55)` | `rgba(3,105,161,0.40)` |
  | 3+ | `#ff4d6d` 红（高负载） | `#e11d48` 红（高负载） |

  > ⚠ 角标语义（评审处置 #4）：**⚠ = 该格内包含 detect_conflicts 真实冲突阶段**（任意格值都显示，与红色独立）；**红色 = 格值 ≥3 的高负载**（可能含顺序阶段非真并行）。两者独立。
- **行尾负载列**：峰值并行数（最多同时几个阶段）+ 该周期活跃阶段总数
- **交互**：hover 格子 → tooltip 列出该周期该人员的活跃阶段（项目·阶段·起止·状态，含冲突标红）；**点击格子 → 右侧 Drawer 弹窗**：列出该周期该人员的活跃阶段简要信息（项目/阶段/计划起止/状态/冲突标记），点击任一阶段 → 跳该阶段所在项目详情页（用户决策 4）

---

## 二、数据与计算（后端，不写库）

### 2.1 新端点 `GET /api/resources/heatmap`

参数：
```
weeks: int = 12        # 时间窗口（周数），0=全部（从最早数据日期起到今天）
granularity: str = 'week'   # 'week' | 'month'（非法值 400）
```

响应：
```json
{
  "start_date": "2026-08-27",
  "end_date": "2026-11-18",
  "granularity": "week",
  "columns": ["2026-08-31", "2026-09-07", ...],   // 每周期起始日
  "people": [
    {
      "resource_id": 3, "name": "张三", "role": "结构工程师",
      "peak_parallel": 2,            // 窗口内最大同时活跃数
      "active_phases": 5,            // 窗口内活跃阶段总数
      "cells": [0, 0, 2, 2, 1, 0, 0, 0, 0, 0, 0, 0],
      "cell_phases": [null, null, [{"phase_id": 11, "project_name": "A", "phase_name": "P5 结构设计", "start": "...", "end": "...", "conflict": false}, ...], ...]
    }
  ],
  "idle_people": [{"resource_id": 9, "name": "赵六", ...}]  // 窗口内零负载
}
```

### 2.2 计算规则（纯函数 `build_heatmap(db, weeks, granularity)`，放 `backend/app/services/resource_heatmap.py`）

1. 取全部人员（Resource）+ 各自阶段（PhaseAssignee → Phase → Project）
2. 过滤活跃阶段：**与 PROJECT_SHELVE §2.5 完全一致**（`status not in (已完成, 已搁置)` 且 `project.status not in (搁置, 已搁置)` 双 key）——细节以 SHELVE 为准，此处不重复展开（评审处置 #7）
3. 缺日期过滤：**无任何日期（无 plan 且无 actual）的阶段不占格**；**仅实际日期的阶段用 actual_start/actual_end 计入**；**半开区间（只有开始或只有结束）不占格**（评审处置 #5——避免缺失边界导致区间爆炸）
4. 周期切片：**weeks 始终定义窗口长度，granularity 只影响桶大小**（24 周 + 月 → ~6 桶）（评审处置 #8）；桶对齐规则：**周粒度 = 周一为桶首**（评审处置 #10）；`start_date` 所在周**包含**在当前窗口首个桶内（阶段活动在本周必须可见——评审处置 #2）；阶段与桶相交（`plan_start <= 桶末 && plan_end >= 桶初`）→ 该桶活跃数 +1
5. `peak_parallel` = 该人员窗口内任意时刻最大并行数（用阶段起止做扫描线，跨桶连续计算，非桶内取整）
6. 冲突标记：复用 `resource_conflicts.detect_conflicts` 的冲突阶段 id 集，`cell_phases[].conflict` 标红
7. 排序：`peak_parallel` 降序 → `active_phases` 降序；零负载入 `idle_people`（按名称排序，评审处置 #11）

### 2.3 权限

与现有 `/all/workload` 一致（登录即可查看）。

---

## 三、前端实现

### 3.1 文件改动

| 文件 | 改动 |
|------|------|
| `frontend/src/api/resources.ts` | +`getHeatmap(params)` |
| `frontend/src/components/Resource/HeatmapView.tsx`（新） | 热力图主体：Segmented 粒度/窗口、CSS Grid 渲染、tooltip（antd Tooltip）、点击跳转 |
| `frontend/src/pages/ResourcePage.tsx` | 顶部 Tab（热力图\|甘特），默认热力图；甘特视图包原 ResourceView |
| `frontend/src/styles/resourceHeatmap.css`（新） | 矩阵样式（颜色分级变量、今日线、⚠ 角标、行负载列） |
| `backend/app/routers/resources.py` | +`GET /heatmap`（注册在 `/{resource_id}/workload` 之前，静态路径优先） |
| `backend/app/services/resource_heatmap.py`（新） | `build_heatmap` 纯函数 |
| `backend/tests/test_heatmap.py`（新） | 计算用例 |

### 3.2 渲染与性能

- 纯 CSS Grid：`grid-template-columns: 200px repeat(N, 1fr)`；行数 = 人员数（≤30），列 ≤ 52（全部周）→ DOM ≤ 1600 格，无性能压力（无 Canvas、无 blur——沿用 `pm-no-blur`）
- 今日列：表头竖线标记（`var(--gantt-today-color)`），复用 todayMarker 视觉语言
- 空负载人员折叠在「空闲区」：整块一行提示 + 可展开

### 3.3 交互

- Tooltip：格子 hover → 活跃阶段列表（最多显示 6 条 + "等 N 个"），冲突阶段红字 + ⚠
- **点击格子 → 右侧 Drawer**（用户决策 4）：
  - 标题：`张三 · 2026-09-07 当周活跃阶段`（月粒度显示「当月」，评审处置 #9）
  - 内容：该周期活跃阶段简要列表（项目名 · 阶段名 · 计划起止 · 状态 Tag · 冲突⚠ 标红），每条可点击
  - 点击条目 → `navigate('/projects/{project_id}')` 关闭 Drawer
  - 空列表（理论不发生）显示"该时段无活跃阶段"
- 行 hover：高亮整行（便于对列）

---

## 四、测试用例（backend/tests/test_heatmap.py）

| # | 场景 | 预期 |
|---|------|------|
| 1 | 单人 2 阶段同周重叠 | cells 该周=2，peak_parallel=2 |
| 1b | 单人 2 阶段同周**不重叠**（上半周/下半周） | cells 该周=2（相交计数），**peak_parallel=1**（评审处置 #5） |
| 2 | 阶段跨 3 周（10.1-10.21） | 每周桶 +1 |
| 3 | 已完成/阶段已搁置 | 不计入任何桶 |
| 4 | 项目状态=搁置（含旧值已搁置，评审处置 #7） | 该阶段不计入 |
| 4b | 仅实际日期阶段（无计划日期） | 用 actual_start/actual_end 计入（评审处置 #4） |
| 5 | 无任何日期阶段（无 plan 且无 actual） | 不占格 |
| 6 | 窗口 4/12/24 周边界截断 | 桶数与 start/end 正确 |
| 7 | granularity=month | 桶按月聚合 |
| 8 | 零负载人员 | 进 idle_people |
| 9 | 排序 | peak_parallel 降序 |
| 10 | 冲突阶段 | cell_phases[].conflict=true |
| 11 | 非法 granularity（如 'day'） | 400（评审处置 #8） |
| 12 | weeks 为负数 | 400 |
| 13 | weeks=0（全部） | 窗口从数据最早日期起到今天，桶数正确 |
| 14 | 半开区间阶段（仅 plan_start 无 end） | 不占格（评审处置 #5） |
| 15 | 当前周活跃阶段 | start_date 所在周含在首桶，阶段可见（评审处置 #2） |

---

## 五、决策记录（用户已确认）

| # | 决策 | 结论 |
|---|------|------|
| 1 | 缺日期阶段（仅实际日期） | **计入**，用实际日期（actual_start/actual_end）；半开区间不占格 |
| 2 | 默认窗口 | **12 周**；0=全部（最早数据日期 → 今天） |
| 3 | 粒度 | 默认周；**窗口 ≥24 周前端自动切月**（Segmented 联动：≥24 周时月选项默认选中且周选项禁用提示，评审处置 #3）；weeks 恒为窗口长度，粒度只影响桶大小 |
| 4 | 点击格子 | **右侧 Drawer 弹窗**显示活跃阶段简要列表，点击阶段跳项目详情页 |

---

## 六、验收标准

- [ ] 热力图 20+ 人 × 52 周渲染流畅（CSS Grid，无滚动卡顿，无 blur）
- [ ] 颜色分级/冲突标红/今日线/行负载列符合 UI_TECH_STYLE 色板（深浅双主题）
- [ ] 与甘特 Tab 数据一致（同源：PhaseAssignee→Phase→Project）
- [ ] pytest 新用例全绿 + 回归
- [ ] 搁置/已完成排除语义与 PROJECT_SHELVE 一致
- [ ] **前端交互验证清单**（评审处置 #6）：① 默认进入热力图 Tab；② 切换窗口 4/12/24/全部；③ ≥24 周自动切月且周选项禁用提示；④ hover 格子 tooltip ≤6 条 + "等 N 个"；⑤ 点击格子 Drawer 打开/内容正确/空态文案；⑥ 点击阶段跳项目详情并关闭 Drawer；⑦ 行 hover 高亮；⑧ 空闲区折叠/展开；⑨ 深浅主题切换颜色正确；⑩ 甘特 Tab 仍可用（回归）
- [ ] 实施锚点校验（评审处置 #12）：`--gantt-today-color`、`pm-no-blur`、`todayMarker`、`detect_conflicts` 存在性——不存在则按本设计补充定义

> 评审通过后由 eng-coder 实施。
> 🦞 | 2026-08-27
