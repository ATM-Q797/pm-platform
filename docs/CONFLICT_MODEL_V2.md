# 资源冲突模型重构 v2 — 人员并行视角 + 手动消除 + P8 排除

> **版本**: v1.0 | **日期**: 2026-08-27 | **状态**: 待评审
> **背景**: 热力图 ⚠ 误伤——许进权（共担 P5 结构设计，本人并行仅 1）因共同负责人张晓平撞车被标 ⚠；用户要求冲突按**人员工作并行情况**判定，并支持**手动消除**（并行任务多但工作量小的实际情况）
> **用户决策**: ① P8 交付仅排除冲突计算（热力图计数保留）；② ⚠ 阈值与 T4 并行规则同口径；③ 甘特冲突条也加消除入口

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

### 2.2 人员并行视角判定（决策 ②）

**口径统一**：热力图 ⚠ 与 T4 冲突报告**同规则**——某人某对阶段满足：
1. 重叠 ≥ 10 天
2. 重叠 ≥ 较短阶段工期 60%
3. **该人员**在重叠窗口内同时活跃阶段数 **≥4**（`_MAX_PARALLEL=3`，活跃 = 计划窗口与重叠区间相交；P8 已排除、已完成/已搁置跳过、搁置项目跳过——沿用现有过滤）

**实现**：
- `detect_conflicts` 保持 per-resource 结构不变（本就是按资源聚合）；**验证并行上限按资源正确生效**——张晓平案例预期：重叠窗口内活跃 2（486+503）≤3 → **不报**（若当前实现仍报 20 对含 486vs503，说明并行过滤存在实现偏差，实施时修复）
- 热力图 ⚠：`_conflict_phase_ids` 只收集**检测后剩余**冲突对成员——许进权不标 ✅
- **共担阶段并行计数**：每人 +1（系统无工作量占比数据，不做加权——文档记录为未来增强：模板加"占比"列后按占比加权）

### 2.3 手动消除冲突（决策 A：资源 × 冲突对）

**数据**：新表 `conflict_override`（评审处置 #1：建表方式 = 现有 SQLAlchemy 模式——models/__init__.py 注册 + `Base.metadata.create_all` 幂等建表；部署时并入 `deploy/migrate_v3.sql` 追加 CREATE TABLE IF NOT EXISTS；本设计**取代** PHASE6_DEV_PLAN.md"本阶段无表结构变更"约束——该约束仅指 T4 原阶段，不适用于本次 V2 重构）：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| resource_id | INTEGER FK | 消除者（哪个人的视角） |
| phase_a_id | INTEGER FK | 冲突对阶段 A |
| phase_b_id | INTEGER FK | 冲突对阶段 B |
| reason | TEXT | 消除原因（必填，如"并行任务多但工作量小"） |
| created_by | INTEGER FK | 操作人 |
| created_at | DATETIME | |

**约束**（评审处置 #3）：`UNIQUE(resource_id, phase_a_id, phase_b_id)`（a/b 归一化后）；FK 级联删除。

**规则**：
- 检测时：per-resource 冲突对**排除已 override 的 (resource, phase_a, phase_b)**（a/b 顺序归一化：小 id 在前）
- 粒度 = 资源 × 冲突对：只消除"某个人的实际工作量小"，不影响其他人对同一对的判定
- **可撤销**：override 记录可查（冲突报告页"已消除"区，仅 admin/manager 可见，决策 3）、可删（撤销后恢复报告）
- **错误语义**（评审处置 #3）：重复 override（同资源同对）→ 409；对当前不构成冲突的对 POST → 400；resource/phase id 不存在 → 404；DELETE 不存在的 override → 404；DELETE 权限与 POST 相同

**API**：
```
POST   /api/resources/conflicts/{resource_id}/override   body: {phase_a_id, phase_b_id, reason}
GET    /api/resources/conflicts/overrides                # 全部消除记录（仅 admin/manager，决策 3）
DELETE /api/resources/conflicts/overrides/{override_id}  # 撤销（权限同 POST）
```
权限（决策 1）：admin 全部资源；manager 仅**自己负责项目**涉及的资源×阶段对（`project.managed_by == user.id` 或 owner 匹配）；其他角色 403。

**热力图响应扩展**（评审处置 #2）：`cell_phases[].conflict` 之外增加 `conflict_detail` 对象（`phase_a_id`/`phase_b_id`、`partner_name`、`partner_phase_name`、`overlap_days`）——tooltip「与谁撞」与 Drawer 消除提交所需数据一次到位；无冲突时 null。

### 2.4 前端入口（决策 ③：甘特 + 热力图 + 报告）

| 入口 | 交互 |
|---|---|
| **热力图 Drawer** | 冲突阶段行显示"⚠ 冲突"红字 + 「消除」按钮（**仅 admin/manager 显示**，评审处置 #6）→ 原因弹窗 → 提交后 ⚠ 消失、格子变普通色 |
| **资源冲突报告**（T4 表格） | 每对冲突行加「消除」按钮 + 原因弹窗；页顶/页底"已消除记录"折叠区（可撤销） |
| **甘特冲突条**（ResourceView，决策 ③） | 黄框冲突条**点击弹消除确认 Modal**（原因输入 + 「查看阶段」次级入口，决策 2；仅 admin/manager 见消除按钮）——与现有"点击条跳阶段编辑"区分：冲突条优先弹消除；非冲突条维持原行为 |
| 热力图 tooltip | 冲突详情：「⚠ 与 张晓平·P5结构设计（乌兹别克…）重叠 24 天」——标明与谁撞 |

**⚠ 显示语义更新**（与 T4 同口径后）：
- 热力图 ⚠ = 该格含**该人员视角**冲突阶段（检测剩余对）
- 消除后：该资源该对不再标 ⚠；热力图格值（忙碌度）不变

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
frontend/src/components/Resource/HeatmapView.tsx  ⚠ 详情 tooltip + Drawer 消除按钮/原因弹窗
frontend/src/components/Resource/ResourceView.tsx 冲突条点击弹消除 Modal
frontend/src/pages/ResourcePage.tsx               冲突报告消除 + 已消除记录区
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
| 9 | 热力图 ⚠ | 消除后该资源格 ⚠ 消失、格值不变 |
| 10 | 权限 | 非 admin/manager 调用 override → 403 |

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
