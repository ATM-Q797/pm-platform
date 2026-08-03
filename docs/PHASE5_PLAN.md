# Phase 5 规划：用户认证 + 权限管理 + 项目录入

> **版本**: v1.1 | **日期**: 2026-08-03
> **前置**: Phase 1-4 已完成（MVP 单人本地工具）
> **目标**: 升级为团队协作平台，支持用户登录、角色权限、项目录入与审核

## 修订记录（v1.1）

| 决策点 | 原方案 | 修订为 | 理由 |
|--------|--------|--------|------|
| 数据库 | SQLite + WAL | **PostgreSQL** | 团队协作多人并发写，SQLite 写锁全局串行会偶发 `database is locked`；PG 天然支持并发 |
| user/resource 关系 | 分离，resource.user_id 关联 | **一一对应** | 建 user 时自动关联同名 resource，分配负责人=分配给 user，逻辑统一 |
| Token 存储 | localStorage | **httpOnly Cookie** | 免疫 XSS 窃取，前端完全不接触 token |
| 5.1 范围 | 仅认证+用户管理 | **含创建项目表单** | 登录后最自然的下一步是建项目，避免 5.1 做完只能看不能建 |
| 阶段增删交互 | 甘特图右键菜单 | **编辑面板按钮 + 列表操作列** | 右键菜单与 dhtmlxGantt 拖拽冲突，实现成本高 |

**新增内容**：operation_log 审计日志表（§2.3）；PostgreSQL 迁移清单（§3.4）；Phase 5.0 迁移准备阶段。

---

## 一、角色定义（RBAC）

### 1.1 角色清单

| 角色 | 标识 | 对应谁 | 核心定位 |
|------|------|--------|----------|
| **超级管理员** | `admin` | 你（产品经理） | 全局管理：用户、项目、权限，兼产品规划 |
| **项目负责人** | `manager` | 项目经理 | 管理自己负责的项目全生命周期 |
| **工程师** | `engineer` | 执行层（设计/结构/测试等） | 更新分配给自己的阶段进度 |
| **观察者** | `viewer` | 领导、客户 | 只读查看，不改任何数据 |

> **注意**：超级管理员 = 产品经理（你），不是项目经理。项目经理 = 项目负责人角色。

### 1.2 权限矩阵

| 操作 | 超级管理员 | 项目负责人 | 工程师 | 观察者 |
|------|:---:|:---:|:---:|:---:|
| **查看所有项目/甘特图/资源负载** | ✅ | ✅ | ✅ | ✅ |
| **创建项目** | ✅ | ✅ | ❌ | ❌ |
| **编辑项目信息** | ✅ | 仅自己负责的 | ❌ | ❌ |
| **分配项目阶段负责人** | ✅ | 仅自己负责的 | ❌ | ❌ |
| **删除项目** | ✅ 直接删 | ⚠️ 需管理员审核 | ❌ | ❌ |
| **编辑阶段（进度/状态/日期）** | ✅ | 自己项目的 | **仅分配给自己的** | ❌ |
| **阶段返工** | ✅ | 自己项目的 | 仅自己的 | ❌ |
| **手动增删阶段** | ✅ | 自己项目的 | ❌ | ❌ |
| **Excel 导入** | ✅ | ❌ | ❌ | ❌ |
| **Excel 导出** | ✅ | ✅ | ❌ | ✅ |
| **管理用户（创建/改角色/禁用）** | ✅ | ❌ | ❌ | ❌ |
| **审核删除申请** | ✅ | ❌ | ❌ | ❌ |

### 1.3 项目删除审核流程

```
项目负责人点击"删除项目"
    │
    ▼
项目状态 → 待删除审核（soft delete，数据不丢）
    │
    ▼
超级管理员在"审核中心"看到申请
    │
    ├── 通过 → 真正删除项目（级联删除阶段/依赖）
    └── 拒绝 → 项目恢复为原状态，通知申请人
```

**数据模型**：project 表新增 `delete_requested` (bool) 和 `delete_requested_by` (user_id) 字段。

---

## 二、数据模型变更

### 2.1 新增表

#### user（用户）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK | |
| username | TEXT | NOT NULL UNIQUE | 登录名 |
| password_hash | TEXT | NOT NULL | bcrypt 加密 |
| name | TEXT | NOT NULL | 显示名（真实姓名） |
| role | TEXT | NOT NULL DEFAULT 'engineer' | admin/manager/engineer/viewer |
| is_active | BOOLEAN | DEFAULT TRUE | 是否启用（禁用后无法登录） |
| created_at | TIMESTAMP | DEFAULT now | |

#### project_delete_request（删除申请）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK | |
| project_id | INTEGER | FK → project.id | 被申请删除的项目 |
| requested_by | INTEGER | FK → user.id | 申请人（项目负责人） |
| reason | TEXT | | 删除原因 |
| status | TEXT | DEFAULT 'pending' | pending/approved/rejected |
| reviewed_by | INTEGER | FK → user.id | 审核人（管理员） |
| created_at | TIMESTAMP | DEFAULT now | |
| reviewed_at | TIMESTAMP | | 审核时间 |

### 2.2 现有表变更

#### project 表新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| managed_by | INTEGER | FK → user.id，项目负责人（替代 owner 文本字段，保留 owner 兼容） |
| created_by | INTEGER | FK → user.id，创建者 |

#### resource 表新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | INTEGER | FK → user.id，关联登录账户（一对一） |

> **resource 与 user 一一对应**（v1.1 修订）：建 user 时自动创建/关联同名 resource。分配阶段负责人（resource）= 分配给谁（user），权限判定统一。现有 27 个 resource 在迁移时按需补建 user 账户。

### 2.3 新增表（v1.1）

#### operation_log（操作日志，审计追溯）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK | |
| user_id | INTEGER | FK → user.id | 操作人 |
| action | TEXT | NOT NULL | 操作类型：create/update/delete/rework/login |
| table_name | TEXT | NOT NULL | 被改的表：project/phase/dependency 等 |
| record_id | INTEGER | | 被改记录的 id |
| old_value | TEXT | | 旧值（JSON）|
| new_value | TEXT | | 新值（JSON）|
| created_at | TIMESTAMP | DEFAULT now | |

> 所有写操作（创建/修改/删除/返工）记录一条日志，便于审计"谁在何时改了什么"。

---

## 三、技术方案

### 3.1 认证

| 项目 | 选型 | 理由 |
|------|------|------|
| 认证方式 | JWT Token | 无状态，局域网部署足够，后续上云也兼容 |
| 密码加密 | bcrypt (passlib) | 行业标准 |
| Token 存储 | **httpOnly Cookie**（v1.1 修订） | 免疫 XSS 窃取，前端完全不接触 token；后端 Set-Cookie 下发 |
| Cookie 配置 | httpOnly + SameSite=Lax + 24h | 前端 axios `withCredentials: true` 自动携带 |
| Token 有效期 | 24 小时 | 平衡安全与便捷 |

**后端依赖新增**：
```
python-jose[cryptography]   # JWT
passlib[bcrypt]             # 密码加密
python-multipart            # 已有（表单解析）
psycopg2-binary             # PostgreSQL 驱动（v1.1 新增）
```

**登录 API 设计**（v1.1）：
- `POST /api/auth/login`：校验账号密码 → 生成 JWT → `Set-Cookie: token=...; HttpOnly; SameSite=Lax; Max-Age=86400` → 返回用户信息
- `POST /api/auth/logout`：`Set-Cookie: token=; Max-Age=0` 清除 cookie
- `GET /api/auth/me`：从 cookie 读 token → 返回当前用户
- 前端 axios 实例设 `withCredentials: true`，所有请求自动带 cookie

### 3.2 权限控制实现

FastAPI Dependency 注入，三层粒度：

```python
# 1. 要求登录（任何认证用户）
get_current_user()

# 2. 要求特定角色
require_role("admin")          # 仅管理员
require_role("admin", "manager")  # 管理员或负责人

# 3. 要求资源所有权（负责人只能改自己的项目）
require_project_access(project_id)  # 管理员或该项目负责人
require_phase_access(phase_id)      # 管理员/项目负责人/该阶段分配的工程师
```

### 3.3 前端路由守卫

```
未登录 → /login
登录后按角色显示导航：
  admin    → 看板 / 项目 / 资源 / 用户管理 / 审核中心
  manager  → 看板 / 项目 / 资源 / 我的项目
  engineer → 看板 / 项目（只读）/ 我的任务
  viewer   → 看板 / 项目（只读）/ 资源（只读）
```

### 3.4 PostgreSQL 迁移清单（v1.1 新增）

Phase 5.0 的核心工作，从 SQLite 迁移到 PostgreSQL：

| 步骤 | 内容 |
|------|------|
| 1. 安装 | 本地安装 PostgreSQL（macOS 用 Postgres.app 或 brew） |
| 2. 建库 | `CREATE DATABASE pm_platform;` |
| 3. 改连接串 | `DATABASE_URL=postgresql://user:pass@localhost:5432/pm_platform` |
| 4. 驱动 | `pip install psycopg2-binary`，requirements.txt 加上 |
| 5. 方言适配 | SQLAlchemy 已屏蔽方言差异，检查 SQLite 特有语法（如 `INTEGER PRIMARY KEY AUTOINCREMENT` 改为 `SERIAL`） |
| 6. 建表 | `Base.metadata.create_all()` 在 PG 上重建所有表 |
| 7. 数据迁移 | 写脚本从 SQLite 导出 18 项目/57 阶段/27 人员/3 模板 → 导入 PG |
| 8. 验证 | 跑全部 40 个测试 + 前端全功能验证 |

> SQLite 的 `database.py` 里 `PRAGMA foreign_keys=ON` 和 `check_same_thread=False` 在 PG 下不需要，迁移时清理。

---

## 四、实施计划

### Phase 5.0：PostgreSQL 迁移准备（0.5 天，v1.1 新增）

**目标**：数据库从 SQLite 迁到 PostgreSQL，为团队协作打基础

| # | 任务 | 说明 |
|---|------|------|
| 1 | 安装 PostgreSQL | 本地装 PG，建库 pm_platform |
| 2 | 改 DATABASE_URL | database.py 连接串改 PG，清理 SQLite 特有配置 |
| 3 | 方言适配 | ORM 模型检查（AUTOINCREMENT→SERIAL 等） |
| 4 | 数据迁移脚本 | 从 SQLite 导出现有数据导入 PG |
| 5 | 全量验证 | 40 个测试全过 + 前端全功能 |

**验收标准**：
- [ ] PostgreSQL 启动，pm_platform 库就绪
- [ ] `Base.metadata.create_all()` 建表成功
- [ ] 现有 18 项目/57 阶段数据完整迁移到 PG
- [ ] pytest 40 个全过
- [ ] 前端看板/项目/甘特图/资源负载正常

### Phase 5.1：用户认证 + 用户管理 + 创建项目（第 1-1.5 周，v1.1 扩展）

**目标**：登录可用、能管用户、能从页面建项目

| # | 任务 | 说明 |
|---|------|------|
| 1 | user 模型 + resource 关联 | 新增 user 表，resource 加 user_id；建 user 时自动关联同名 resource |
| 2 | 登录/登出 API | `/api/auth/login` 校验密码 → Set-Cookie(httpOnly) 下发 JWT；`/logout` 清除；`/me` 返回当前用户 |
| 3 | 权限中间件 | FastAPI dependency：get_current_user / require_role（从 cookie 读 token） |
| 4 | 现有 API 加权限 | 所有写操作要求登录 + 按角色限制（先全量放开再逐个加，每步测前端） |
| 5 | 登录页面 | 前端登录表单 + axios withCredentials + 路由守卫（未登录跳 /login） |
| 6 | 用户管理页面 | 管理员创建用户、分配角色、启用/禁用、重置密码 |
| 7 | **创建项目表单**（v1.1 新增） | 编号/名称/类目/市场/负责人 + 模板选择器，管理员或负责人可创建，应用模板生成阶段+依赖 |
| 8 | 初始化管理员 | init_db.py 创建超级管理员账户（初始密码，首次登录强制改） |

**验收标准**：
- [ ] 超级管理员可登录，httpOnly Cookie 下发 JWT
- [ ] 未登录访问 API 返回 401
- [ ] 管理员可创建用户并分配角色（自动建 resource）
- [ ] 不同角色看到不同导航菜单
- [ ] **可从页面创建项目并应用模板，创建后跳转甘特图**（v1.1 新增）
- [ ] 现有功能（看板/项目/甘特图/资源）登录后正常使用

### Phase 5.2：项目编辑完善 + 阶段管理 + 权限细化（第 2 周，v1.1 调整）

**目标**：项目全生命周期可在页面内管理，权限按所有权细化

> 注：创建项目表单已并入 5.1，本阶段聚焦编辑、阶段管理、负责人分配。

| # | 任务 | 说明 |
|---|------|------|
| 1 | 项目编辑表单 | 管理员/负责人编辑项目信息（名称/类目/市场/周期等） |
| 2 | 阶段手动增删 | **编辑面板"添加阶段"按钮 + 项目列表操作列删除**（v1.1：不用右键菜单，避免与甘特图拖拽冲突） |
| 3 | 负责人分配 | 把阶段分配给具体工程师（resource 已关联 user，直接选人员） |
| 4 | 权限细化 | 负责人只能改自己的项目，工程师只能改分配给自己的阶段 |
| 5 | 项目列表操作列 | 编辑/删除按钮（按角色显示），替代纯点击进入 |

**验收标准**：
- [ ] 负责人可编辑自己项目的阶段（增删改）
- [ ] 工程师只能看到/改分配给自己的阶段
- [ ] 阶段可分配给具体工程师
- [ ] Excel 导入仍保留（批量场景）

### Phase 5.3：删除审核 + 工程师工作台（第 3 周）

**目标**：删除审批流程 + 工程师填报入口

| # | 任务 | 说明 |
|---|------|------|
| 1 | 删除申请 API | 负责人申请删除 → project 状态变更 |
| 2 | 审核中心页面 | 管理员查看/通过/拒绝删除申请 |
| 3 | 我的任务页面 | 工程师看分配给自己的阶段，按状态分组 |
| 4 | 进度填报 | 工程师更新进度/状态/实际日期 |
| 5 | 操作日志 | 记录关键操作（谁改了什么），审计追溯 |

**验收标准**：
- [ ] 负责人删除项目需管理员审核
- [ ] 管理员可在审核中心通过/拒绝
- [ ] 工程师有"我的任务"入口
- [ ] 工程师可填报进度并保存
- [ ] 关键操作有日志记录

---

## 五、后续演进（Phase 6+，本次不实现）

```
Phase 5（本次）        Phase 6              Phase 7
团队协作基础           智能化                平台化
─────────────         ─────────────         ─────────────
用户认证+权限          关键路径计算           微信/飞书集成
项目录入+审核          资源冲突检测           移动端
工程师填报             延期自动预警           数据看板/BI
                      周报自动生成           SQLite→PostgreSQL
```

---

## 六、风险与对策

| 风险 | 对策 |
|------|------|
| 现有 API 加权限后破坏前端 | 先全量放开，逐个 API 加权限，每步测前端 |
| resource 与 user 关联（v1.1 简化） | 一一对应：建 user 自动关联同名 resource，username 直接用中文姓名 |
| ~~SQLite 并发写入~~（v1.1 已解决） | ~~SQLite WAL~~ → Phase 5.0 已迁 PostgreSQL，天然支持并发 |
| 密码安全（局域网） | bcrypt 加密 + 初始密码统一，首次登录强制改密 |
| PostgreSQL 迁移数据丢失（v1.1 新增） | 迁移前备份 SQLite，迁移脚本校验行数一致，40 个测试验证 |
| Cookie 跨域（前后端分离）（v1.1 新增） | 开发期 vite proxy 同源，Cookie SameSite=Lax；生产部署同域名 |

---

> **本文档确认后即作为 Phase 5 开发依据。**
> v1.1 修订基于实施前评审决策，已锁定技术方向。
> 🦞 Phoebe | 2026-08-03
