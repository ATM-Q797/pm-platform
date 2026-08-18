# 优化功能规划：导入预检（差异报告）+ 关注项目置顶

> **版本**: v1.0 | **日期**: 2026-08-18
> **状态**: 待确认，确认后作为开发依据（在 Phase 6 之前实施）

---

## 一、功能 A：导入数据先做差异报告，确认后才导入

### 1.1 背景与问题

当前 Excel 导入是**一次性全量重置**：上传文件 → 立即清空现有 17 个项目/54 阶段 → 导入新数据 → 返回报告。

**风险**：
- 文件选错/格式意外 → 现有数据瞬间被清空
- 导入结果（错误/警告）在**导入完成后**才看到，为时已晚
- 用户无法预览"将要发生什么"

**目标**：上传 → 生成差异报告（将删除什么、将导入什么、有什么问题）→ 用户确认 → 才真正执行导入。

### 1.2 方案设计

#### 后端：导入器重构为"解析 + 落库"两阶段

**现状**：`excel_importer.import_excel` 解析与写库耦合（边解析边 `db.add`，中途 `DELETE` 全量数据）。

**改造**：
| 函数 | 职责 |
|------|------|
| `parse_workbook(file_bytes) -> ParsedData`（新） | 纯解析：读工作簿 → 生成项目/阶段/资源的内存数据结构 + errors/warnings（**不碰数据库**） |
| `import_parsed(db, parsed) -> ImportReport`（新） | 全量重置 + 把解析结果落库（沿用现有写库逻辑） |
| `import_excel(db, file_bytes)`（保留） | `parse_workbook` + `import_parsed`，向后兼容 |

**新增 API**：

```
POST /api/import/preview        # 只解析 + 对比，不落库
```

**返回（ImportPreview schema）**：
```json
{
  "existing": { "projects": 17, "phases": 54, "resources": 27 },   // 将被清空的数据
  "incoming": { "projects": 2, "phases": 4 },                       // 文件将导入的数据
  "errors": [...],        // 解析错误（存在则禁止导入）
  "warnings": [...],      // 解析警告（允许导入，但需用户知情）
  "projects_preview": [   // 文件内项目概览（前 20 个）
    { "name": "XX项目", "market": "拉美区", "category": "新需求", "phases": 3 }
  ]
}
```

> `POST /api/import/excel` 保持不变（确认后执行），可加 `?confirm=true` 参数显式要求预览过（可选增强，防绕过）。

#### 前端：导入流程加"确认"环节

```
选择文件 → 调 /api/import/preview → 差异报告 Modal：
  ⚠️ 本次导入将【清空现有 17 个项目（54 阶段）】
  ✅ 文件包含 2 个项目 / 4 个阶段
  📋 项目预览列表（名称/市场/阶段数）
  ⚠️ 警告 N 条（可展开）
  ❌ 错误 N 条（存在则"确认导入"按钮置灰）
        ↓ 用户点【确认导入】
  POST /api/import/excel → 导入完成报告（现有 Modal 逻辑复用）
```

**交互细节**：
- 预览请求期间 loading；取消关闭不产生任何副作用
- 错误列表默认展开（红色），警告默认折叠
- 确认按钮文案：「确认导入并清空现有数据」（红色警告色）

### 1.3 边界与规则

- preview 与 confirm 之间数据可能变化：局域网低并发可接受；confirm 时仍以**当时**库为准（全量重置语义天然幂等）
- 文件解析失败（打不开/无数据 sheet）：preview 直接返回 errors，前端禁用确认
- 权限不变：仅 admin 可导入/预览（`require_role("admin")`）

### 1.4 验收标准

- [ ] 上传文件后**不立即导入**，先展示差异报告
- [ ] 报告含：现有数据将被清空的数量、文件将导入的数量、错误/警告明细、项目概览
- [ ] 有错误时确认按钮禁用；取消不产生任何数据库变更
- [ ] 确认后导入结果与现状一致（全量重置 + 报告）

---

## 二、功能 B：关注项目置顶

### 2.1 背景与需求

项目列表按 id 排序，关注的项目没有特殊标识。**需求**：项目列表提供"关注"按钮（星标），关注的项目**置顶显示**。

### 2.2 方案设计

#### 数据模型（新表，关注是用户级行为）

```
user_favorite
├── user_id    INTEGER FK → user_account.id   (复合主键)
├── project_id INTEGER FK → project.id        (复合主键)
└── created_at TIMESTAMP DEFAULT now           (关注时间，置顶排序用)
```

- 任何登录用户可关注**自己可见**的项目
- 每用户独立关注列表（管理员关注 ≠ 工程师关注）

**数据库迁移**：
- 本地/测试：`Base.metadata.create_all` 自动建表（SQLAlchemy 模型注册后）
- 生产 PG（已部署的服务器）：
```sql
CREATE TABLE IF NOT EXISTS user_favorite (
    user_id    INTEGER NOT NULL REFERENCES user_account(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, project_id)
);
```
- 服务器执行方式：`docker compose exec -T db psql -U pm_user -d pm_platform -c "..."`（或随下次代码更新由 init_db 幂等创建——init_db 的 create_all 会自动补建）

#### 后端 API

| 接口 | 说明 |
|------|------|
| `PUT /api/projects/{id}/favorite` | 关注（幂等） |
| `DELETE /api/projects/{id}/favorite` | 取消关注（幂等） |
| `GET /api/projects/favorites` | 我关注的 project_id 列表（用于前端初始化星标状态） |
| `GET /api/projects`（扩展） | 返回项增加 `is_favorite: bool`；**排序：关注优先（置顶）**，同组内按 id |

**列表排序**：`ORDER BY is_favorite DESC, Project.id`（后端统一排序，前端无需处理；关注置顶即时生效，刷新后保持）

**权限**：任意登录用户可操作；关注不改变现有可见性过滤逻辑

#### 前端

1. **项目列表表格新增「关注」列**：星标按钮
   - 未关注：`StarOutlined`（灰色，点击关注）
   - 已关注：`StarFilled`（黄色，点击取消）
   - 点击即调接口 + 本地状态更新 + 列表重排（或局部移动）
2. **项目详情页**：头部同样提供星标（可选增强，保持一致体验）
3. **排序实现**：优先后端排序（`is_favorite DESC`）；前端点击后可直接调 `load()` 重新拉取（数据量小，简单可靠）

### 2.3 边界与规则

- 关注表随项目删除级联清理（ON DELETE CASCADE）
- 用户被禁用/删除：关注记录级联清理
- 关注数量无限制；置顶组内顺序按 id（稳定）
- 工程师只看自己参与的项目——关注仅对其可见项目生效

### 2.4 验收标准

- [ ] 项目列表每行有星标，点击切换关注状态（即时反馈）
- [ ] 关注的项目在列表中置顶，刷新后保持
- [ ] 不同用户关注互不影响（数据隔离）
- [ ] 我的关注接口返回正确；项目详情页星标状态一致
- [ ] 生产 PG 迁移执行后无报错，旧数据不受影响

---

## 三、实施计划

### 任务拆解

| # | 任务 | 涉及文件 | 工作量 |
|---|------|----------|--------|
| A1 | 导入器重构：parse_workbook / import_parsed 两阶段 | `excel_importer.py` | 中 |
| A2 | POST /api/import/preview + ImportPreview schema | `imports.py`、`import_report.py` | 小 |
| A3 | 前端导入确认 Modal（预览 → 确认 → 导入） | `ProjectListPage.tsx`、`types/index.ts` | 中 |
| A4 | 导入预检单元测试（preview 不落库/错误阻断/与 import 结果一致） | `test_import.py` | 小 |
| B1 | user_favorite 模型 + 迁移 | `models/`、`init_db.py`（自动建表） | 小 |
| B2 | 关注 API（PUT/DELETE/GET favorites）+ 列表 is_favorite + 置顶排序 | `projects.py`、schemas | 中 |
| B3 | 前端星标列 + 置顶交互（列表 + 详情页） | `ProjectListPage.tsx`、`ProjectDetailPage.tsx` | 中 |
| B4 | 关注功能单元测试（幂等/隔离/排序/级联） | `test_api.py` | 小 |

### 实施顺序与依赖

```
A1 → A2 → A4（后端完成 + 测试）
        ↘ A3（前端确认流）
B1 → B2 → B4（后端完成 + 测试）
        ↘ B3（前端星标）
A 与 B 相互独立，可并行；每项完成跑全量 pytest + tsc + build
```

### 影响范围

- **A 涉及导入器核心**：重构后需全量回归导入测试（现有 12+ 导入测试必须全绿），确认无行为变化（preview 不写库、import 行为与现状一致）
- **B 涉及列表接口**：`ProjectRead` 增加 `is_favorite` 字段——前端类型同步更新；其他消费方（看板/资源视图）不受影响
- 生产服务器：功能完成并本地验证后，随下次部署一起上线（A 纯后端代码更新 + B 需执行一次建表迁移）

### 风险与对策

| 风险 | 对策 |
|------|------|
| 导入器重构引入回归 | 现有导入测试全覆盖 + 新增 preview 一致性测试 |
| preview 与确认间隔数据变化 | 全量重置语义幂等；确认时以当时库为准 |
| 关注表迁移遗漏（生产库） | init_db 的 create_all 幂等补建 + 部署指南补充迁移 SQL |
| 列表接口字段变更影响其他页面 | 新增字段为可选项（默认 false），前端类型同步 |

---

> 确认后按此规划实施（本地提交，待你指令统一推送）。
> 🦞 | 2026-08-18
