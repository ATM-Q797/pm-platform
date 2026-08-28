# 资源冲突模型重构 v2.1 — 按甘特条（阶段）消除 + 入口统一 + 报告转审核中心

> **版本**: v2.2 | **日期**: 2026-08-28 | **状态**: 已实施（`968af83`/`18e89fc`/`02a00b4` 本地已部署）（用户 2026-08-28 四项决策）
> **背景**: 热力图 ⚠ 误伤（共担者连带）已修复；用户进一步明确消除语义与入口
> **用户决策（2026-08-28）**:
> ① 消除目标 = **阶段（甘特条）**，不是冲突对——"点击消除该甘特条的冲突即表示该甘特条所对应的阶段风险低、**不计入项目并行计算逻辑**"
> ② 未消除的甘特条继续按并行逻辑计算（并行 >3 显示冲突，直到消除某条把并行数降下来）
> ③ 消除入口**统一在资源负载甘特图**；Dashboard / 热力图**不再提供消除接口**；消除后所有视图同步
> ④ 冲突报告 + 消除记录**转移到审核中心**（ReviewPage 新 Tab）

---

## 一、现状问题（实测确认）

- 冲突对 `486 vs 503`：乌兹别克 P5（张晓平/黎平）↔ 阿联酋 P5（张晓平/许进权/宋海波），重叠 24 天
- **撞车者是张晓平**（两人共同负责人）；许进权本人并行仅 1 个阶段 → 热力图 ⚠ 误伤
- 根因：⚠ 标记 = 冲突对**成员阶段**（阶段级），未按人员视角过滤

---

## 二、改造方案

### 2.1 P8 交付排除冲突（决策 ①）

`backend/app/services/resource_conflicts.py`：
- 检测时跳过 `phase.phase_type == 'P8'` 的阶段（不参与冲突对生成）
- **热力图计数保留**：P8 阶段仍占格（忙碌度），仅 ⚠ 不标
- **专项项目阶段同样排除**（`project.is_special=true` 不参与冲突检测——SPECIAL_PROJECT §二：专项项目是独立监控对象，不占用资源负载统计，三处口径统一）

### 2.2 人员并行视角判定（决策 ②）

**口径统一**：热力图 ⚠ 与 T4 冲突报告**同规则**——某人某对阶段满足：
1. 重叠 ≥ 10 天
2. 重叠 ≥ 较短阶段工期 60%
3. **该人员**在重叠窗口内同时活跃阶段数 **≥4**（`_MAX_PARALLEL=3`，活跃 = 计划窗口与重叠区间相交；P8 已排除、已完成/已搁置跳过、搁置项目跳过、**专项项目跳过**——沿用现有过滤，SPECIAL_PROJECT §二）

**实现**：
- `detect_conflicts` 保持 per-resource 结构不变（本就是按资源聚合）；**验证并行上限按资源正确生效**——张晓平案例预期：重叠窗口内活跃 2（486+503）≤3 → **不报**（若当前实现仍报 20 对含 486vs503，说明并行过滤存在实现偏差，实施时修复）
- 热力图 ⚠：`_conflict_phase_ids` 只收集**检测后剩余**冲突对成员——许进权不标 ✅
- **共担阶段并行计数**：每人 +1（系统无工作量占比数据，不做加权——文档记录为未来增强：模板加"占比"列后按占比加权）

### 2.3 手动消除冲突（v2.2 语义：**抑制冲突警告，负载照显**）

**数据**：表 `conflict_override`（粒度 = 资源 × 阶段）：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| resource_id | INTEGER FK | 消除者（哪个人的视角） |
| phase_id | INTEGER FK | 被消除的阶段（甘特条） |
| reason | TEXT | 消除原因（必填，如"并行不影响实际负荷"） |
| created_by | INTEGER FK | 操作人 |
| created_at | DATETIME | |

**约束**：`UNIQUE(resource_id, phase_id)`；FK 级联删除。
**迁移**：新表由 create_all 自动创建（本地已重建；服务器部署时执行 migrate_v3.sql 含建表 DDL，幂等）。

**规则（用户 2026-08-28 最终语义）**：
- 消除 = **管理者确认该并行不影响此人的实际工作负荷**（负载均衡说明）
- 检测时：该阶段从该资源的**并行判定中豁免**（不参与冲突对生成与并行计数）——其冲突警告消失；未消除阶段继续按并行逻辑计算
- **热力图仍显示实际并行数**：被消除阶段**照常占格、照常计 peak**——"并行 4 但无冲突警告"= 已确认该并行可承受，便于持续观察真实负载
- **可撤销**：override 记录在审核中心可见、可删（撤销后该阶段恢复冲突判定）

**API**：
```
POST   /api/resources/conflicts/{resource_id}/override   body: {phase_id, reason}
GET    /api/resources/conflicts/overrides                # 全部消除记录（审核中心，仅 admin/manager）
DELETE /api/resources/conflicts/overrides/{override_id}  # 撤销（权限同 POST）
```
权限：admin 全部资源；manager 仅**自己负责项目**涉及的资源×阶段对（`project.managed_by == user.id` 或 owner 匹配）；其他角色 403。
错误语义：重复消除同阶段 → 409；该阶段当前不冲突/不属于该资源 → 400；id 不存在 → 404；reason 缺失 → 422。

**热力图响应扩展**（评审处置 #2）：`cell_phases[].conflict` 之外增加 `conflict_detail` 对象（`phase_a_id`/`phase_b_id`、`partner_name`、`partner_phase_name`、`overlap_days`）——tooltip「与谁撞」与 Drawer 消除提交所需数据一次到位；无冲突时 null。

### 2.4 前端入口（决策 ③ 最终语义：**消除入口唯一 = 资源负载甘特图**）

> 用户 2026-08-28 最终确认：Dashboard / 热力图**只读**（不做消除接口）；冲突报告 + 已消除记录迁至审核中心「资源冲突」Tab（决策 ④）。本表为 v2.1 实施后的一致性描述（2026-08-28 评审处置 #1 对齐）。

| 入口 | 交互 |
|---|---|
| **甘特冲突条**（ResourceView，唯一消除入口） | 黄框冲突条**点击弹消除确认 Modal**（原因输入 + 「查看阶段」次级入口，决策 2；仅 admin/manager 见消除按钮）——与现有"点击条跳阶段编辑"区分：冲突条优先弹消除；非冲突条维持原行为 |
| **热力图 Drawer**（只读） | 冲突阶段行显示"⚠ 冲突"红字 + 冲突详情（与谁撞）；**无消除按钮**（决策 ③） |
| **资源冲突报告**（审核中心「资源冲突」Tab） | 只读报告表格（每对冲突：重叠天数/双方/消除入口提示）；**已消除记录**列表（可撤销） |
| 热力图 tooltip | 冲突详情：「⚠ 与 张晓平·P5结构设计（乌兹别克…）重叠 24 天」——标明与谁撞 |

**⚠ 显示语义更新**（与 T4 同口径后）：
- 热力图 ⚠ = 该格含**该人员视角**冲突阶段（检测剩余对）
- 消除后：该资源该对不再标 ⚠；热力图格值（忙碌度）不变（v2.2：被消除阶段仍占格、仍计 peak）

---

## 三、涉及文件

```
backend/app/models/conflict_override.py（新）    + models/__init__.py 注册
backend/app/services/resource_conflicts.py       P8 排除 + override 排除 + 并行验证修复
backend/app/services/resource_heatmap.py         ⚠ 语义不变（自动跟随检测结果）+ tooltip 冲突详情数据
backend/app/routers/resources.py                 +override 3 端点 + conflicts 响应带详情
backend/tests/test_conflicts.py                  回归 + 新用例
backend/tests/test_conflict_override.py（新）    消除/撤销/粒度用例
backend/tests/test_heatmap.py                    许进权不再标 ⚠ 用例
frontend/src/api/resources.ts                    +override API
frontend/src/components/Resource/HeatmapView.tsx  ⚠ 详情 tooltip（只读，无消除按钮——决策 ③）
frontend/src/components/Resource/ResourceView.tsx 冲突条点击弹消除 Modal
frontend/src/pages/ReviewPage.tsx                 新增「资源冲突」Tab：冲突报告（只读）+ 已消除记录（可撤销，决策 ④）
frontend/src/pages/ResourcePage.tsx               移除冲突报告/已消除记录区（迁审核中心）+ conflictVersion 同步
frontend/src/pages/DashboardPage.tsx              移除消除按钮（只读）+ conflict-changed 同步刷新
frontend/src/styles/resourceHeatmap.css           ⚠ 样式微调
docs/RESOURCE_HEATMAP.md                          ⚠ 语义段落更新
```

## 四、测试用例

| # | 场景 | 预期 |
|---|------|------|
| 1 | P8 阶段与 P5 重叠 | 不产生冲突对；热力图 P8 仍占格 |
| 2 | 许进权（共担者，本人并行 1） | 无 ⚠（回归用户案例） |
| 3 | 张晓平 486+503 重叠 24 天（**实测更正**：重叠窗口 08-07~08-31 内实际活跃 4 个阶段——#478 埃塞/#486 乌兹/#498 尼日利亚/#503 阿联酋，非设计初版假设的 2 个） | **报冲突**（活跃 4 ≥ 4，T4 上限）——并行过滤按资源生效的判定依据：若某对窗口内活跃 <4 则不报 |
| 4 | 某资源并行 4 阶段重叠 | 报冲突对 |
| 5 | override 后 | 该资源该对不再报；其他资源同对仍报 |
| 6 | override 撤销后 | 恢复报告 |
| 7 | override 原因必填 | 缺 reason → 422 |
| 8 | a/b 顺序归一化 | (a,b) 与 (b,a) 视为同一对 |
| 9 | 热力图 ⚠ | 消除后该资源格 ⚠ 消失、格值不变（v2.2：被消除阶段仍占格、仍计 peak） |
| 10 | 权限 | 非 admin/manager 调用 override → 403 |
| 11 | 重复消除同一阶段（评审处置 #6） | 409（UNIQUE(resource_id, phase_id)） |
| 12 | 删除不存在的 override 记录（评审处置 #6） | 404 |

## 五、决策记录（用户已确认）

| # | 决策 | 结论 |
|---|------|------|
| 1 | override 权限 | **admin 全部 + manager 仅自己负责项目的冲突对**（与项目编辑权限一致） |
| 2 | 甘特冲突条点击 | 弹「消除冲突」Modal，**Modal 内提供「查看阶段」次级入口**（消除 + 详情两不误） |
| 3 | 已消除记录可见性 | **仅 admin/manager 可见**（只读，防滥用；其他角色看不到消除痕迹） |

---

## 六、验收标准

- [ ] pytest 全绿（新增 + 回归，含 146 现有）
- [ ] 前端 tsc + build 零错误
- [ ] 许进权热力图无 ⚠；张晓平冲突按 T4 规则判定
- [ ] P8 参与热力计数但不参与冲突
- [ ] 消除后热力图 ⚠ 消失、冲突报告该对消失、甘特冲突条不再黄框；撤销恢复
- [ ] 甘特冲突条点击弹消除 Modal，非冲突条行为不变

> 评审通过后由 eng-coder 实施。
> **权威声明（评审处置 #4）**：本文档**取代并扩展** `PHASE6_DEV_PLAN.md` §T4（冲突检测规则）与 §T9（资源视图冲突标记）的对应描述——冲突规则以本文档为准，实施后如需更新 dev plan 再同步。
> 🦞 | 2026-08-27
