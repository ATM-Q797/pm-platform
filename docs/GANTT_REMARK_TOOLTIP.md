# 甘特条悬停备注浮窗 — 设计文档

> **版本**: v1.5 | **日期**: 2026-08-31（v1.5：代码评审处置——🟡 拖拽平移中抑制浮窗（panning 标志）、🔵 ResourceView 注释同步、🔵 时序注释措辞弱化；v1.4：评审处置 1-6；v1.3：延迟 1000→50ms；v1.2：资源视图隔离机制更正）
> **状态**: 设计评审通过（处置 1-6 全部采纳）
> **需求决策**: ① 浮窗仅显示备注文本（不加其他字段）；② 备注为空/纯空白不显示浮窗；③ 仅项目甘特图（资源负载视图不加）

---

## 一、需求（用户故事）

> 作为项目经理，我在项目甘特图中把鼠标悬停在某个阶段的甘特条上（约 50ms 即触发）后，希望看到该阶段的**备注**浮窗（目前进展备注原文），移开鼠标即消失——不用逐个点开阶段编辑器查看进展说明。

## 二、方案

### 2.1 技术选型

使用 dhtmlxGantt **官方 tooltip 扩展**（非自绘 div）：
- 内置悬停延迟配置（`tooltip_timeout`）正好满足"悬停即显示"
- 内置移出自动隐藏、跟随鼠标定位
- 与 smart_rendering / 甘特重绘机制天然兼容（自绘 div 在甘特重绘时会残留/错位，是历史踩坑点）

### 2.2 后端（数据通路）

甘特接口目前不返回备注，需打通：

> **实施注记（v1.2）**：实施时发现两处改动已在库中存在（SPECIAL_PROJECT §五 时期落地，`test_special_project.py::test_5_gantt_remark_carried` 覆盖）——本次仅验证通过，未重复改动。

| 文件 | 改动 |
|------|------|
| `backend/app/schemas/project.py` | `GanttTask` 增加 `remark: str \| None = None` |
| `backend/app/services/gantt_service.py` | 阶段行 task 传入 `remark=ph.remark`（项目行不传） |

### 2.3 前端（显示逻辑）

| 文件 | 改动 |
|------|------|
| `frontend/src/components/Gantt/ganttConfig.ts` | `applyGanttConfig` 中：① `gantt.plugins({ tooltip: true })`；② `gantt.config.tooltip_timeout = 50`（悬停 50ms 即显示）；③ `gantt.templates.tooltip_text`：`task.type === 'task'` 且备注**有效**（`typeof task.remark === 'string' && task.remark.trim() !== ''`，评审处置 #1）→ 返回 **HTML 转义后的备注原文**（评审处置 #2/#3：转义 `& < > " '`；**仅空值判断用 `trim()`，显示用 `escapeHtml(task.remark)` 原文，保留首尾空白**；配合 `pre-wrap` 保留换行）；否则返回 `false`（不显示）。**type 取值说明（处置 #5）**：项目甘特图项目行 `type='project'`、阶段行 `type='task'`（见 gantt_service.build_gantt）；type 判断与备注有效性判断双保险 |
| `frontend/src/components/Gantt/gantt.css` | `.gantt_tooltip` 样式：最大宽度 320px、`white-space: pre-wrap`（保留备注换行）、`overflow-wrap: break-word`（超长备注自动断行，处置 #6）、圆角/阴影，**用现有主题 CSS 变量适配深色/浅色模式**（背景 `--gantt-tooltip-bg`、文字 `--gantt-tooltip-text`、边框 `--border-light`、阴影 `--card-shadow`） |

**关键行为规则**：
1. 仅 `type === 'task'`（阶段行）且备注有效 → 显示浮窗；项目行永不显示
2. 备注为 null / 空串 / **纯空白**（`trim()` 后为空）→ 不显示浮窗（评审处置 #1）
3. 备注中的 HTML 特殊字符按字面显示（转义，不解析为标签）（评审处置 #2）
4. 悬停延迟 50ms（用户 v1.3 要求：1000ms → 50ms）；鼠标移出甘特条浮窗自动消失
5. **共享 gantt 实例说明**：GanttChart 与 ResourceView 共用 dhtmlxGantt 全局实例，`plugins/tooltip_timeout` 为全局设置。**资源视图隔离机制（处置 #2 锚定不变式）**：workload 接口实际**有** `remark` 字段（`WorkloadItem.remark`，schemas/project.py），且 ResourceView 会给阶段 task 注入 `remark` **和 `resource_id`**（ResourceView.tsx 注入处已加注释锚定此不变式：`resource_id` 是 tooltip 浮窗的资源视图隔离标记，项目甘特 task 无此字段，删除注入会导致验收 6 回归）；`tooltip_text` 用 **`task.resource_id != null` 拦截**资源视图。**已知约束（审计修订）**：该守卫按"字段存在"无条件拦截——当前架构项目甘特 task 无 `resource_id`，验收 1-9b 不受影响；若未来引入该字段需细化守卫（见验收 3d）

### 2.4 转义实现约定

前端在 `ganttConfig.ts` 内定义局部 `escapeHtml(text: string): string` 工具函数（替换 `& < > " '` 五个字符），`tooltip_text` 中返回 **`escapeHtml(task.remark)`**（仅空值判断用 `task.remark.trim()`，显示保留原文首尾空白，处置 #3）。不引入第三方库。

### 2.5 不做的事

- 不改资源负载视图（用户决策 ③）
- 不在浮窗中显示状态/进度/日期等其他字段（用户决策 ①）
- 不加"备注为空显示占位"（用户决策 ②）

## 三、验收标准

| # | 场景 | 预期 |
|---|------|------|
| 1 | 悬停**有备注**的阶段甘特条（约 50ms） | 浮窗显示备注原文（保留换行） |
| 2 | 鼠标移出甘特条 | 浮窗立即消失 |
| 3 | 悬停**备注为空**（null/空串）的阶段甘特条 ≥1 秒 | 不出现浮窗 |
| 3b | 悬停**备注为纯空白**（如空格串）的阶段甘特条（约 50ms） | 不出现浮窗（评审处置 #1） |
| 3c | 备注含 HTML 特殊字符（如 `<div>测试 & </div>`）| 浮窗按**字面文本**显示，不被解析为标签（评审处置 #2） |
| 3d | **已知架构约束（处置 #2 修订）**：`resource_id != null` 守卫按"字段存在"无条件拦截（不区分视图来源）；当前架构下项目甘特 task 不传 `resource_id`（gantt_service 不注入），故验收 1-9b 均不受影响。**若未来项目甘特数据引入 `resource_id` 字段，需同步细化守卫**（改用显式视图标记，如 ResourceView 的任务特征），届时本验收生效 |
| 3e | 备注首尾含空白/换行（如 `"  备注内容\n"`） | 显示**原文**，首尾空白与换行保留（处置 #3） |
| 4 | 悬停项目行（顶层） | 不出现浮窗 |
| 5 | 专项项目详情页甘特图 | 同样生效（同一组件） |
| 6 | 资源负载视图悬停 | 不出现备注浮窗 |
| 7 | 深色模式 / 浅色模式 | 浮窗背景 `--gantt-tooltip-bg`、文字 `--gantt-tooltip-text`、边框 `--border-light`、阴影 `--card-shadow` 四变量在两种模式下均有定义且对比度可读（处置 #4） |
| 8 | `tsc --noEmit` + `npm run build` | 零错误 |
| 8b | 超长备注（如 500 字无空格） | 浮窗内自动断行（`overflow-wrap: break-word`），不超出 320px（处置 #6） |
| 9 | 既有甘特功能回归 | 拖拽平移、关键路径开关、返工标记、今日标记不受影响 |
| 9b | 拖动甘特条 / 拖拽平移时间轴过程中 | 无浮窗残留或闪现（评审处置 #6） |

## 四、风险与对策

| 风险 | 对策 |
|------|------|
| tooltip_text 返回空串时 dhtmlxGantt 仍渲染空框 | 实施时验证；若发生，改用 `gantt.attachEvent("onBeforeTooltip")` 返回 false 拦截（备选路径，eng-coder 实施说明中已列） |
| tooltip 插件与 smart_rendering 冲突（浮窗错位/残留） | 官方扩展与 smart_rendering 兼容；实施时按验收 1/2 实测，异常则上报 |
| **拖拽平移时浮窗闪现（v1.5 处置）**：50ms 延迟下指针扫过任务条即触发，而平移中 `dx ≤ 3px` 时不滚动、dhtmlx 不隐藏浮窗 | panUtils 增加平移中标志（mousedown 置位，mouseup / 离开容器清除），`tooltip_text` 开头检查该标志返回 false——平移全程抑制浮窗（验收 9b） |
| 全局 plugins 设置影响资源视图 | 见 §2.3 行为规则 5（resource_id 拦截隔离，v1.2 修订）+ 验收 6 实测 |
| 深色主题下浮窗白底刺眼 | 用主题 CSS 变量着色（验收 7） |
| 备注含 HTML 标签破坏浮窗结构 | HTML 转义（§2.3，评审处置 #2） |

## 五、测试映射（METHODOLOGY 三路径）

| 类型 | 用例 |
|------|------|
| 正常 | 验收 1（有备注显示）、5（专项页生效）、3c（特殊字符字面显示） |
| 边界 | 验收 3（空备注）、3b（纯空白）、4（项目行）、7（双主题） |
| 错误/回归 | 验收 8（编译零错误）、9（既有功能回归）、9b（拖拽无残留）、6（资源视图隔离） |

## 六、checklist 登记（评审处置 #3）

- [x] 决策 ① 浮窗仅备注文本 → 本文档 §2.5
- [x] 决策 ② 空/纯空白不显示 → 本文档 §2.3 规则 2 + 验收 3/3b
- [x] 决策 ③ 仅项目甘特图 → 本文档 §2.5 + 验收 6

## 七、文档归属说明（评审处置 #4/#5）

- 本文档合并需求/设计/测试映射三部分（团队既有惯例，内容齐全即可，不拆分）
- `docs/design/README.md` 文档地图不存在——创建文档地图作为后续独立事项（不阻塞本设计）

---

> 🦞 | 2026-08-31
