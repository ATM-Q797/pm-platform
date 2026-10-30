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
