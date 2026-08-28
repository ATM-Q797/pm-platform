# 专项项目页面 — 设计文档

> **版本**: v1.0 | **日期**: 2026-08-28 | **状态**: 待评审
> **需求**: 新增专项项目页面，重点监控指定创建的专项项目；阶段类型支持自定义；甘特悬浮显示备注
> **用户决策（2026-08-28）**:
> ① 专项标记 = **创建/编辑开关**（`is_special` 字段）
> ② 自定义阶段类型 = **仅专项项目放开**（普通项目保持标准阶段下拉——P1-P8 为决策时点表述，2026-08-28 同日重排为 P1-P9 + P71/P72，见 **PHASE_TYPES_V2**）
> ③ 专项列表可见性 = **仅 admin/manager**
> ④ 预警角标 = 全要
> ⑤ **专项项目不计入资源负载**（热力图 + 资源甘特 + 冲突检测三处排除）

---

## 一、数据层

`Project` 新增 `is_special: bool`（default false）：
- schema `ProjectCreate` / `ProjectUpdate` 支持
- 迁移：`migrate_v3.sql` 追加 `ALTER TABLE project ADD COLUMN IF NOT EXISTS is_special BOOLEAN DEFAULT FALSE`（本地 PG 同步执行；create_all 对新库自动）
- **导入接口分离（用户 2026-08-28 决策，评审 🔴 处置）**：专项项目**不走常规导入接口**——常规导入（全量重置/合并）完全不影响专项项目；专项项目走**独立的专项导入接口**（`POST /api/import/special`，仅 admin/manager，全量重置专项域）

## 二、资源负载排除（决策 ⑤，三处口径统一）

| 位置 | 处理 |
|------|------|
| `resource_heatmap.active_heatmap_phases` | 跳过 `project.is_special` 的阶段（不占格/不计 peak） |
| `resource_conflicts._active_phases` | 跳过 is_special（不参与冲突检测） |
| `routers/resources.py _workload_visible` | 跳过 is_special（资源甘特不显示） |

> 与 P8/搁置同类的全局排除——专项项目是独立监控对象，不占用资源负载统计。
> **推论**：专项项目没有资源冲突预警（已排除）——专项列表预警角标不含"资源冲突"（决策 ④ 中该项对专项无意义，见 §四）。

## 三、自定义阶段类型（决策 ②）

- `phase_type` 字段本身是自由文本——后端零改动可存任意值
- **前端限制在专项项目内放开**：
  - `PhaseEditor`：所属项目 `is_special` → 阶段类型 `Select` 切换为 **AutoComplete**（可自由输入；联想 = 该项目已用过的阶段类型 + 标准阶段建议——标准建议见 **PHASE_TYPES_V2 §五**（P1-P9 + P71/P72，2026-08-28 重排后 10 项））
  - 普通项目：保持标准阶段下拉（P1-P9 + P71/P72，随 PHASE_TYPES_V2 重排——**不再是 P1-P8**，评审处置：本文档 P1-P8 表述统一替换）
- **现有计算不受影响**（均不依赖 P 前缀）：
  - 甘特条颜色 = 按 `status`（task_class）
  - 关键路径 CPM = 按依赖
  - 看板延期/到期 = 按日期
  - 项目进度 = 阶段状态汇总

## 四、专项项目页面

### 4.1 列表页 `SpecialProjectsPage`（新菜单「专项项目」，仅 admin/manager 可见——决策 ③）

```
┌─────────────────────────────────────────────────────┐
│ [＋ 新建专项项目]  [筛选：状态]                       │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │
│ │ 专项A         │ │ 专项B         │ │ 专项C         │  │
│ │ 负责人·状态    │ │ 负责人·状态    │ │ 负责人·状态    │  │
│ │ 进度条 60%    │ │ 进度条 20%    │ │ 延期 🔴       │  │
│ │ 计划 8/1~9/30 │ │ 计划 9/1~10/1 │ │ 即将到期 🟡   │  │
│ └──────────────┘ └──────────────┘ └──────────────┘  │
└─────────────────────────────────────────────────────┘
```

- 卡片网格：名称 · 负责人 · 状态 · 阶段进度条 · 计划窗口
- **预警角标**（决策 ④ + 用户 2026-08-28 二轮确认，口径与 Dashboard 一致）：
  - 🔴 **延期**：`plan_end < today` 且项目未完成
  - 🟡 **即将到期**：`plan_end` 在 7 天内且未完成
  - ⚠️ **无阶段**：项目无任何阶段
  - （资源冲突角标不适用——专项已排除出资源负载，决策 ⑤ 推论；用户确认 A）
  - **优先级**（同时成立时只显示最高级，评审处置 #7）：延期 🔴 > 即将到期 🟡 > 无阶段 ⚠️
  - **边界（评审处置 #11）**：搁置/已完成项目不显示预警角标（与全局活跃口径一致）；`plan_end` 为空时不触发延期/即将到期
- 卡片点击 → 专项项目详情
- 新建/编辑：项目对话框 + 「专项项目」开关（决策 ①）

### 4.2 详情页（复用 `ProjectDetailPage`，is_special 模式——评审处置 #8 确定方案）

- 路由指向同一 `ProjectDetailPage` 组件（带 id），通过 `ProjectRead.is_special` 字段驱动模式切换：阶段类型 AutoComplete（§三）、甘特 tooltip 备注（§五）
- **权限（评审处置 #3：隔离管理一致性）**：专项项目的详情/甘特/阶段接口仅 admin/manager 可访问——`GET /api/projects/{id}`、`GET /api/projects/{id}/gantt`、阶段 CRUD 对 `is_special=true` 项目校验角色（非 admin/manager 403）；普通项目维持现有开放模式
- **项目级接口权限（评审处置 #10 补充）**：`PUT/PATCH/DELETE /api/projects/{id}`（含 is_special 开关切换）与 `POST /api/projects`（is_special=true 创建）仅 admin/manager——**校验以目标项目的 DB `is_special` 值为准**（非请求体标志，防止绕过）；**普通项目的更新/删除维持现有权限模式**（非本开关引入的收紧，评审处置：措辞明确）
- 状态/阶段列表/甘特与现有详情一致
- 阶段编辑器：阶段类型 AutoComplete（§三）
- 甘特：tooltip 显示备注（§五）

### 4.3 权限与隔离（用户 2026-08-28 二轮确认：专项项目从普通列表隐藏）

- 菜单/路由：仅 admin/manager 显示（与审核中心同模式）
- **普通项目列表 `GET /api/projects` 默认排除 `is_special=true`**（专项项目仅专项页可见，隔离管理——决策 B）
- 专项列表 `GET /api/projects/special`：仅 `is_special=true`，admin/manager；**注册在 `/{project_id}` 动态路由之前**（静态路径优先，FastAPI 按声明顺序匹配——沿用热力图 `/heatmap` 的既有约定；评审处置 #4）
- **所有项目列表入口统一排除 `is_special=true`**（评审处置 #4）：普通列表 / Dashboard 统计 / 看板 / 搜索走 `GET /api/projects` 者由该接口统一排除自动覆盖；其余独立聚合接口（如 dashboard 统计、报告模块若有独立列表查询）逐一加 `is_special=false` 过滤，实施时 grep 全部 Project 列表查询核对并补测试
- **专项项目详情/编辑接口同样受限**：`GET /api/projects/{id}`、gantt、阶段 CRUD 对 is_special 项目仅 admin/manager（§4.2）
- **Dashboard 统计口径与普通列表一致**：项目总数/延期/到期等**排除专项项目**（专项由专项页单独监控）
- 专项项目创建后不可见于普通列表；若需转为普通项目（取消开关）→ 在专项页编辑取消勾选后进入普通列表

## 五、甘特悬浮备注（全局）

- `GET /api/projects/{id}/gantt` 响应 task 增加 `remark` 字段（Phase.remark，已有字段）
- **资源甘特（`/all/workload`）同样补 remark**：`_phase_to_workload` 返回 `remark`——保证"所有甘特生效"（项目甘特/专项甘特/资源甘特）的验收可达成（评审处置 #5）
- `ganttConfig.tooltip_text`：`task.remark` 非空 → tooltip 追加 `📝 备注：{remark}`（**所有甘特生效**）
- PhaseEditor 备注编辑已存在（Form remark 字段），无需新增

## 五·B、导入接口分离（用户 2026-08-28 决策，评审 🔴 处置）

**常规导入接口（现有 `POST /api/imports`，全量/合并两模式）——专项项目完全隔离**：

| 常规导入路径 | 专项处理 |
|------|------|
| `import_parsed`（全量重置） | 删除范围改 `is_special=False`（专项保留，含其阶段/assignee）；**Resource 只删"专项未引用的行"**（`NOT IN (SELECT resource_id FROM phase_assignee pa JOIN phase ph ON pa.phase_id=ph.id JOIN project p ON ph.project_id=p.id WHERE p.is_special IS TRUE)`）——防止专项 assignees 断裂；报告注明"专项项目 N 个不受影响" |
| `import_merged`（合并） | 名称匹配/归一化查找排除 `is_special`（与专项同名 → 视为新建，不合并进专项） |
| `build_preview`（预览） | existing/同名对比/合并明细全部排除专项（专项不计入"将被清空"/matched/kept） |

**专项导入接口（新 `POST /api/import/special`，仅 admin/manager）**：
- 语义：**全量重置专项域**——删除全部 `is_special=true` 项目（级联），按文件重建（`is_special=True`）；常规项目完全不受影响
- 解析复用 `parse_workbook`，加 `special` 模式：**阶段类型列原样存储**（专项自定义类型不映射 P1-P8、不做兜底映射；旧格式无类型列 → phase_type 留空）
- 依赖：收尾 `_build_all_project_dependencies`（special_only）建 FS 串联（专项域内）
- 报告：复用最近报告槽位（专项导入后 GET /api/import/report 返回专项报告）
- 前端：专项页「导入专项数据」按钮（复用现有导入 Modal 流程：上传 → **`POST /api/import/special-preview`**（专项域口径预览：将清空 N 个专项项目、导入 M 个）→ 确认提交）
- **编号续编（实测 PG 复现修复）**：专项/常规项目各自全量重置时，对方域项目保留可能占用纯数字编号 `'1'..'N'`，直接沿用文件行号会撞唯一约束 `project.code`——两个导入入口都从"现有最大纯数字编号 + 1"续编（`_next_project_code`）

## 六、涉及文件

```
后端：
  backend/app/models/project.py          +is_special 列
  backend/app/schemas/project.py         ProjectCreate/Update/Read + is_special
  backend/app/routers/projects.py        +GET /api/projects/special（admin/manager）；
                                         普通列表排除 is_special；创建/更新支持；
                                         gantt 响应 + remark；
                                         详情/甘特/阶段接口对 is_special 项目限 admin/manager
  backend/app/routers/imports.py         +POST /api/import/special + /api/import/special-preview（admin/manager，全量重置专项域）
  backend/app/services/excel_importer.py 常规导入隔离专项（重置/合并/预览）+ special 解析模式 + import_special
  backend/app/routers/dashboard.py       统计排除 is_special（口径与普通列表一致）
  backend/app/routers/resources.py       _workload_visible 排除 is_special + _phase_to_workload 补 remark
  backend/app/services/resource_heatmap.py  active_heatmap_phases 排除 is_special
  backend/app/services/resource_conflicts.py _active_phases 排除 is_special
  backend/tests/test_special_project.py（新） 排除/权限/自定义类型/隔离/路由顺序用例
  deploy/migrate_v3.sql                  +is_special 列
前端：
  frontend/src/api/projects.ts           +listSpecialProjects + is_special 入参
  frontend/src/types/index.ts            Project + is_special；GanttTask/WorkloadItem + remark
  frontend/src/pages/SpecialProjectsPage.tsx（新）  列表 + 预警角标 + 新建/编辑
  frontend/src/pages/ProjectDetailPage.tsx          复用（is_special 模式：AutoComplete + 权限守卫）
  frontend/src/App.tsx                   菜单「专项项目」+ 路由（admin/manager）
  frontend/src/components/PhaseEditor/PhaseEditor.tsx  专项项目 → 阶段类型 AutoComplete
  frontend/src/components/Gantt/ganttConfig.ts         tooltip 备注
  frontend/src/components/Gantt/GanttChart.tsx        task 数据带 remark
文档（评审处置 #2：随变更一起更新，沿用 CONFLICT_MODEL_V2 惯例）：
  docs/RESOURCE_HEATMAP.md               §2.2 规则 2 补 is_special 排除（不占格/不计 peak）
  docs/CONFLICT_MODEL_V2.md              §2.1/2.2 过滤枚举补 is_special 排除
```

> 实施顺序（评审处置 #3 对齐）：专项功能在冲突模型 v2.2 与热力图**已实施代码之上**做同文件增量（active_heatmap_phases / _active_phases / _workload_visible 均为现存函数）——eng-coder 按"先加排除、再补 remark、最后前端"的顺序落地；**实施注意事项（评审处置 #9）**：先 grep `phase_type` 全部消费方（排序/导入映射/甘特色）确认无 `P\d+` 前缀依赖，再放开自定义类型。

## 七、测试用例

| # | 场景 | 预期 |
|---|------|------|
| 1 | 专项项目阶段 | 热力图不占格、资源甘特不显示、冲突不报（三处排除） |
| 2 | 专项项目阶段类型自由文本（如"电磁兼容测试"） | 保存成功、甘特正常显示 |
| 3 | 普通项目阶段类型自定义 | **前端验证项**（PhaseEditor 下拉限制；后端不强制）——列入前端交互验证清单，非后端 pytest |
| 4 | 专项列表接口 | admin/manager 200；engineer/viewer 403；**`/special` 不被 `/{project_id}` 吞掉**（路由顺序） |
| 5 | gantt 响应 remark | 阶段有备注 → task.remark 携带（项目甘特 + /all/workload 资源甘特） |
| 6 | 预警口径 | 延期/即将到期/无阶段角标正确（无资源冲突角标） |
| 7 | 创建/更新 is_special | 开关生效、列表正确过滤 |
| 8 | 普通列表与 Dashboard 隔离 | is_special=true 项目不出现在普通列表与 Dashboard 统计（决策 B） |
| 9 | 详情/阶段接口权限（评审处置 #3） | 非 admin/manager 访问专项项目详情/甘特/阶段 → 403；普通项目不受影响 |
| 10 | 列表聚合排除（评审处置 #4） | 看板/搜索（走 GET /api/projects）无专项；独立聚合接口逐一核对 |
| 11 | 项目级接口权限（评审处置 #10） | 非 admin/manager 更新/删除专项项目、创建 is_special=true → 403 |
| 12 | 角标边界（评审处置 #11） | 搁置/已完成专项无角标；plan_end 为空无延期/到期角标；多条件同时 → 只显最高优先级 |
| 13 | 常规导入隔离（评审 🔴 处置） | 常规全量导入后专项项目（含阶段/assignee/Resource）原样保留；常规合并导入与专项同名 → 不合并（新建常规项目）；常规预览不含专项 |
| 14 | 专项导入 | 全量重置专项域（旧专项删除、按文件重建 is_special=True）；阶段类型自由文本直存；常规项目不受影响；非 admin/manager 403 |

## 八、验收标准

- [ ] 专项项目创建/编辑（开关）、列表（仅 admin/manager）、详情（仅 admin/manager）、预警角标
- [ ] 专项项目阶段类型可自由输入（AutoComplete 联想）；普通项目 P1-P9 + P71/P72 标准下拉（随 PHASE_TYPES_V2 重排）
- [ ] 专项项目完全退出资源负载三处（热力/甘特/冲突）与所有列表聚合（评审处置 #4）
- [ ] 甘特悬浮显示备注（全局）
- [ ] 前端交互验证（评审处置 #9）：① 菜单「专项项目」仅 admin/manager 可见；② 卡片角标渲染与优先级正确；③ 专项详情阶段类型 AutoComplete 联想（历史类型 + 标准阶段建议 P1-P9/P71/P72）；④ 甘特 hover 显示 📝 备注；⑤ 非 admin 直接访问专项路由 → 403 提示
- [ ] pytest 全绿 + tsc/build 零错误；迁移脚本含 is_special

> 评审通过后由 eng-coder 实施。
> 🦞 | 2026-08-28
