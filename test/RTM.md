# RTM — 需求追溯矩阵（集成测试）

> 用途：每个集成用例一行——组件交互 ∥ 断言的业务结果 ∥ 入口 ∥ 溯源需求。
> 维护规则：按批次增量维护；某行被后续变更破坏/冗余时同步修订或删除。用例实现随各批次（单元测试随批次存档；集成用例在 `test/`）。

| 行 | 组件交互 | 断言业务结果 | 入口 | 溯源需求 | 批次 |
|---|---|---|---|---|---|
| RT-1 | ReportPage → POST /api/report/projects → Project/Phase 落库 | 新建后列表出现新项目，编号=纯数字递增，阶段 sequence=行序 | 填报页新建弹窗 | 设计方案 §二/§3.2/§九-2；模板说明 1/3/4/5/11 | 信息填报一期 |
| RT-2 | 填报页阶段明细表格（ReportPage PhaseDetailTable）→ PATCH /api/report/phases/{id} | 落库生效；无权字段返回 403 且附字段名 | 填报页阶段明细 | 设计方案 §3.2/§六；模板说明 7/9/10 | 信息填报一期 |
| RT-3 | 阶段负责人改计划时间 → POST change-requests → 负责人 review 批准 | Phase.plan_* 更新为新值 + operation_log 一条；驳回则原值不动 | 填报页 + Tab2 | 设计方案 §四；模板说明 6 | 信息填报一期 |
| RT-4 | 负责人直改已有一 pending 申请的阶段计划时间 | 申请自动 rejected，comment="负责人已直接改期" | 填报页 | 设计方案 §四边界规则 | 信息填报一期 |
| RT-5 | reporter 登录 → 打既有任意 /api/* 接口 | 全部 403（封锁矩阵：projects/phases/resources/users/imports/audit/analysis…） | 直敲 API | 设计方案 §3.1（过渡期角色隔离） | 信息填报一期 |
| RT-6 | reporter 登录 → 前端任意非 /report 路由 | 重定向 /report，导航仅一项 | 浏览器地址栏 | 设计方案 §3.1（过渡期角色隔离） | 信息填报一期 |
| RT-7 | 项目列表页卡片标题 Segmented（全部项目 / 我的关注）→ GET /api/projects 的 is_favorite 过滤 → Table 列集裁剪 | 关注视图仅显示已关注项目、无「序号」列、底栏「共 N 个关注项目」；视图内取消关注后该行即时移出且计数同步减；刷新后仍停留在原视图 | 项目列表页 · 卡片标题 Segmented | 批次 §4 用户 2026-11-04 批复：副板块「我的关注」显示关注项目、不显示序号 | 我的关注副板块 |
| RT-8 | 列表 health 随行字段 / GET /api/projects/{id}/health / dashboard stats.risk_projects 三处同一 assess_health 规则灯 | 同一项目三处档位与主因短语一致；无计划日期项目显「未评估」不冒充绿；据置项目列表显「—」、详情区隐藏、不上风险清单；风险分析弹窗红/黄 2 分板块行点击跳详情 | 项目列表健康度列 · 项目详情健康度区 · 看板风险分析弹窗 | docs/PHASE8_PLAN.md §二验收（三处档位与短语一致）；批档 §2 | 健康度评级（规则灯） |
| RT-9 | projects.update_project / phases.update_phase / report.patch_report_phase / report_service.apply_change_proposal / phases.rework 五入口 → change_events.record_* → data_change_events 落行 → GET /api/data-change-events 查询 → 详情页时间线渲染 | 白名单字段改动可查到一条事件（who/when/old→new/source 四要素齐全）；审批路径 old=提案快照（非批准时现值）；删项目/删用户后事件行保留（SET NULL+冗余名可读）；非白名单字段（is_special/remark/template_id/sequence/assignees）零事件；端点未登录 401、登录可按 project_id/phase_id/field/source 过滤；详情页「变更时间线」区渲染事件行、空态显示「暂无变更记录（自上线日起记录）」 | 项目详情页/列表编辑弹窗 · 填报页阶段明细 · 填报页 Tab2 审批 · 阶段返工入口 | docs/PHASE8_PLAN.md §九（方案 B 落库+三期）；§2.7 防火墙 | 过程事件地基 |
