# 甘特条悬停备注浮窗 — 设计文档

> **版本**: v1.2 | **日期**: 2026-08-31（v1.2 实施修订：资源视图隔离机制更正，见 §2.3 规则 5）
> **状态**: 设计评审通过（处置 1-6 全部采纳）
> **需求决策**: ① 浮窗仅显示备注文本（不加其他字段）；② 备注为空/纯空白不显示浮窗；③ 仅项目甘特图（资源负载视图不加）

---

## 一、需求（用户故事）

> 作为项目经理，我在项目甘特图中把鼠标悬停在某个阶段的甘特条上**1 秒**后，希望看到该阶段的**备注**浮窗（目前进展备注原文），移开鼠标即消失——不用逐个点开阶段编辑器查看进展说明。

## 二、方案

### 2.1 技术选型

使用 dhtmlxGantt **官方 tooltip 扩展**（非自绘 div）：
- 内置悬停延迟配置（`tooltip_timeout`）正好满足"1 秒后显示"
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
| `frontend/src/components/Gantt/ganttConfig.ts` | `applyGanttConfig` 中：① `gantt.plugins({ tooltip: true })`；② `gantt.config.tooltip_timeout = 1000`（悬停 1 秒）；③ `gantt.templates.tooltip_text`：`task.type === 'task'` 且备注**有效**（`typeof task.remark === 'string' && task.remark.trim() !== ''`，评审处置 #1）→ 返回 **HTML 转义后的备注原文**（评审处置 #2：转义 `& < > " '`，配合 `pre-wrap` 保留换行）；否则返回 `false`（不显示） |
| `frontend/src/components/Gantt/gantt.css` | `.gantt_tooltip` 样式：最大宽度 320px、`white-space: pre-wrap`（保留备注换行）、圆角/阴影，**用现有主题 CSS 变量适配深色/浅色模式** |

**关键行为规则**：
1. 仅 `type === 'task'`（阶段行）且备注有效 → 显示浮窗；项目行永不显示
2. 备注为 null / 空串 / **纯空白**（`trim()` 后为空）→ 不显示浮窗（评审处置 #1）
3. 备注中的 HTML 特殊字符按字面显示（转义，不解析为标签）（评审处置 #2）
4. 悬停延迟 1000ms；鼠标移出甘特条浮窗自动消失
5. **共享 gantt 实例说明**：GanttChart 与 ResourceView 共用 dhtmlxGantt 全局实例，`plugins/tooltip_timeout` 为全局设置。**资源视图隔离机制（v1.2 实施修订）**：workload 接口实际**有** `remark` 字段（`WorkloadItem.remark`，schemas/project.py），且 ResourceView 会给阶段 task 注入 `remark`（ResourceView.tsx）——设计 v1.1 假设"无 remark 自然不显示"不成立；实际隔离靠 `tooltip_text` 中的 **`task.resource_id != null` 拦截**（ResourceView 给阶段 task 注入 `resource_id`，项目甘特 task 无此字段）。**删除该守卫会导致验收 6 回归**

### 2.4 转义实现约定

前端在 `ganttConfig.ts` 内定义局部 `escapeHtml(text: string): string` 工具函数（替换 `& < > " '` 五个字符），`tooltip_text` 中先 `escapeHtml(remark.trim())` 再返回。不引入第三方库。

### 2.5 不做的事

- 不改资源负载视图（用户决策 ③）
- 不在浮窗中显示状态/进度/日期等其他字段（用户决策 ①）
- 不加"备注为空显示占位"（用户决策 ②）

## 三、验收标准

| # | 场景 | 预期 |
|---|------|------|
| 1 | 悬停**有备注**的阶段甘特条 ≥1 秒 | 浮窗显示备注原文（保留换行） |
| 2 | 鼠标移出甘特条 | 浮窗立即消失 |
| 3 | 悬停**备注为空**（null/空串）的阶段甘特条 ≥1 秒 | 不出现浮窗 |
| 3b | 悬停**备注为纯空白**（如空格串）的阶段甘特条 ≥1 秒 | 不出现浮窗（评审处置 #1） |
| 3c | 备注含 HTML 特殊字符（如 `<div>测试 & </div>`）| 浮窗按**字面文本**显示，不被解析为标签（评审处置 #2） |
| 4 | 悬停项目行（顶层） | 不出现浮窗 |
| 5 | 专项项目详情页甘特图 | 同样生效（同一组件） |
| 6 | 资源负载视图悬停 | 不出现备注浮窗 |
| 7 | 深色模式 / 浅色模式 | 浮窗文字可读、样式协调 |
| 8 | `tsc --noEmit` + `npm run build` | 零错误 |
| 9 | 既有甘特功能回归 | 拖拽平移、关键路径开关、返工标记、今日标记不受影响 |
| 9b | 拖动甘特条 / 拖拽平移时间轴过程中 | 无浮窗残留或闪现（评审处置 #6） |

## 四、风险与对策

| 风险 | 对策 |
|------|------|
| tooltip_text 返回空串时 dhtmlxGantt 仍渲染空框 | 实施时验证；若发生，改用 `gantt.attachEvent("onBeforeTooltip")` 返回 false 拦截（备选路径，eng-coder 实施说明中已列） |
| tooltip 插件与 smart_rendering 冲突（浮窗错位/残留） | 官方扩展与 smart_rendering 兼容；实施时按验收 1/2 实测，异常则上报 |
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
