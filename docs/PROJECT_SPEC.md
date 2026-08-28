# 智能终端研发项目管理平台 — 完整项目规格书

> **文档用途**: 供 AI 编程工具（ZCode / Cursor / Claude Code 等）直接作为开发输入  
> **版本**: v1.0 | **日期**: 2026-08-02  
> **项目代号**: PM-Platform  
> **项目路径**: `~/Desktop/pm-platform/`

---

## 一、项目概述

### 1.1 背景

硬件研发团队（20人），同时在管 15-18 个智能终端（金融自助设备）研发项目，交付周期 2 个月以内。现用 Excel 手工管理甘特图，存在数据不规范、依赖关系不直观、资源负载不可见、阶段依赖手工维护成本高等痛点。需建设中小型项目管理平台替代 Excel。

### 1.2 MVP 目标

单用户本地 Web 应用，实现：
- 项目全生命周期可视化（甘特图 + 依赖关系连线）
- 资源负载透明化（按人查看在做什么）
- 多项目全局视角（跨项目看风险和进度）
- 管理流程标准化（3 套项目模板，新建项目一键生成）
- 现有 18 个项目数据导入

### 1.3 技术栈

| 层 | 技术 | 版本/备注 |
|----|------|----------|
| 后端框架 | FastAPI | Python 3.12 |
| ORM | SQLAlchemy 2.0 | async 端推荐但不强制 |
| 数据库 | SQLite | 后续可迁移 PostgreSQL |
| 数据验证 | Pydantic v2 | |
| Excel 解析 | openpyxl + pandas | |
| 前端框架 | React 18 + TypeScript | |
| 构建工具 | Vite | |
| UI 组件库 | Ant Design 5 | |
| 甘特图 | dhtmlxGantt 社区版 (GPL) | 通过 npm `dhtmlx-gantt` 安装 |
| HTTP 客户端 | Axios | |
| ASGI 服务器 | uvicorn | |

### 1.4 项目目录结构

```
pm-platform/
├── docs/                          # 项目文档（当前目录）
│   ├── PROJECT_SPEC.md            # 本文件 — 完整规格书
│   ├── DEVELOPMENT_PLAN.md        # 开发计划文档
│   ├── schema.sql                 # 数据库建表 SQL（参考）
│   └── templates.json             # 3套模板数据（供导入）
├── backend/                       # FastAPI 后端
│   ├── venv/                      # Python 虚拟环境
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                # FastAPI 应用入口
│   │   ├── database.py            # 数据库连接与 session
│   │   ├── models/                # SQLAlchemy ORM 模型
│   │   │   ├── __init__.py
│   │   │   ├── project.py
│   │   │   ├── phase.py
│   │   │   ├── dependency.py
│   │   │   ├── resource.py
│   │   │   └── template.py
│   │   ├── schemas/               # Pydantic 请求/响应模型
│   │   │   ├── __init__.py
│   │   │   ├── project.py
│   │   │   ├── phase.py
│   │   │   ├── dependency.py
│   │   │   ├── resource.py
│   │   │   └── template.py
│   │   ├── routers/               # API 路由
│   │   │   ├── __init__.py
│   │   │   ├── projects.py
│   │   │   ├── phases.py
│   │   │   ├── dependencies.py
│   │   │   ├── resources.py
│   │   │   ├── templates.py
│   │   │   └── import.py          # Excel 导入接口
│   │   └── services/              # 业务逻辑
│   │       ├── __init__.py
│   │       ├── project_service.py
│   │       ├── phase_service.py
│   │       ├── template_service.py
│   │       └── excel_importer.py  # Excel 解析与导入
│   ├── tests/
│   │   ├── test_models.py
│   │   ├── test_api.py
│   │   └── test_import.py
│   ├── init_db.py                 # 建数据库初始化脚本
│   ├── requirements.txt
│   └── pm_platform.db             # SQLite 数据库文件（运行后生成）
├── frontend/                      # React 前端
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/                   # API 请求封装
│       │   ├── client.ts          # Axios 实例
│       │   ├── projects.ts
│       │   ├── phases.ts
│       │   └── resources.ts
│       ├── types/                 # TypeScript 类型定义
│       │   └── index.ts
│       ├── components/
│       │   ├── Gantt/
│       │   │   ├── GanttChart.tsx     # dhtmlxGantt 封装
│       │   │   └── GanttConfig.ts     # 甘特图配置
│       │   ├── ProjectList/
│       │   │   └── ProjectList.tsx
│       │   ├── ProjectDetail/
│       │   │   └── ProjectDetail.tsx
│       │   ├── PhaseEditor/
│       │   │   └── PhaseEditor.tsx    # 阶段编辑面板
│       │   └── ResourceView/
│       │       └── ResourceView.tsx   # 资源负载视图
│       ├── pages/
│       │   ├── Dashboard.tsx          # 首页看板
│       │   ├── ProjectListPage.tsx
│       │   ├── ProjectDetailPage.tsx
│       │   └── ResourcePage.tsx
│       └── utils/
│           └── date.ts                # 日期工具
├── start.sh                      # 一键启动脚本
└── README.md                     # 项目说明
```

### 1.5 端口与地址

| 服务 | 地址 |
|------|------|
| 前端 Dev Server | `http://localhost:5173` |
| 后端 API Server | `http://localhost:8000` |
| API 文档 (Swagger UI) | `http://localhost:8000/docs` |
| SQLite 数据库 | `backend/pm_platform.db` |

### 1.6 CORS 配置

后端需允许前端 `http://localhost:5173` 跨域访问。

---

## 二、数据模型

### 2.1 ER 关系总览

```
TEMPLATE 1───N TEMPLATE_PHASE
    │               │
    │ 1             │ (复制生成)
    │               ▼
PROJECT 1───N PHASE N───N DEPENDENCY
    │              │
    │              │ assignees (多对多 via PHASE_ASSIGNEE)
    │              │
    │              ▼
    │          RESOURCE
    │
    └─ (created_from_template_id)
```

### 2.2 表结构

#### 2.2.1 resource（资源/人员）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | |
| name | TEXT | NOT NULL UNIQUE | 姓名 |
| role | TEXT | | 岗位：工业设计/结构设计/测试/项目管理 |
| department | TEXT | | 部门 |
| created_at | TIMESTAMP | DEFAULT now | |

#### 2.2.2 project（项目）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | |
| code | TEXT | NOT NULL UNIQUE | 项目编号（如 `1`, `2-1`） |
| category | TEXT | NOT NULL | 类目：新需求/量产/定制/改造 |
| name | TEXT | NOT NULL | 项目名称 |
| owner | TEXT | NOT NULL | 项目负责人 |
| market | TEXT | NOT NULL | 销售区域：拉美区/西欧区/东欧区/中东区/亚太区/土耳其区/非洲区/北美区/OEM业务部 |
| status | TEXT | NOT NULL DEFAULT '未开始' | 未开始/进行中/已完成/已搁置 |
| priority | TEXT | | 高/中/低 |
| plan_start | DATE | | 计划开始日期 |
| plan_end | DATE | | 计划结束日期 |
| template_id | INTEGER | FK → template.id | 关联模板 |
| remark | TEXT | | 备注 |
| created_at | TIMESTAMP | DEFAULT now | |
| updated_at | TIMESTAMP | DEFAULT now | |

#### 2.2.3 phase（阶段实例）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | |
| project_id | INTEGER | FK → project.id, NOT NULL | |
| phase_type | TEXT | NOT NULL | 阶段类型代码，见 §2.3 |
| name | TEXT | NOT NULL | 阶段显示名称 |
| sequence | INTEGER | NOT NULL | 项目内顺序 (1,2,3...) |
| plan_start | DATE | | 计划开始 |
| plan_end | DATE | | 计划结束 |
| actual_start | DATE | | 实际开始 |
| actual_end | DATE | | 实际结束 |
| status | TEXT | NOT NULL DEFAULT '未开始' | 未开始/进行中/已完成/延期/已搁置 |
| progress | INTEGER | DEFAULT 0 | 进度 0-100 |
| rework_count | INTEGER | DEFAULT 0 | 返工次数 |
| remark | TEXT | | 备注 |

#### 2.2.4 rework_log（返工日志）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | |
| phase_id | INTEGER | FK → phase.id, NOT NULL | |
| from_status | TEXT | NOT NULL | 回退前状态 |
| to_status | TEXT | NOT NULL | 回退后状态 |
| reason | TEXT | NOT NULL | 返工原因 |
| created_at | TIMESTAMP | DEFAULT now | |

#### 2.2.5 phase_assignee（阶段-人员关联）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| phase_id | INTEGER | FK → phase.id | 复合 PK |
| resource_id | INTEGER | FK → resource.id | 复合 PK |

#### 2.2.6 dependency（依赖关系）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | |
| from_phase_id | INTEGER | FK → phase.id, NOT NULL | 前置阶段 |
| to_phase_id | INTEGER | FK → phase.id, NOT NULL | 后续阶段 |
| type | TEXT | NOT NULL DEFAULT 'FS' | FS/SS/FF/SF |
| lag_days | INTEGER | DEFAULT 0 | 延迟天数 |

#### 2.2.7 template（项目模板）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | |
| name | TEXT | NOT NULL UNIQUE | 模板名称 |
| category | TEXT | NOT NULL | 新需求研发/量产交付/定制改造 |
| description | TEXT | | |
| created_at | TIMESTAMP | DEFAULT now | |

#### 2.2.8 template_phase（模板阶段）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | |
| template_id | INTEGER | FK → template.id | |
| phase_type | TEXT | NOT NULL | 阶段类型代码 |
| name | TEXT | NOT NULL | 显示名称 |
| sequence | INTEGER | NOT NULL | 模板内顺序 |
| default_duration_days | INTEGER | DEFAULT 7 | 默认工期 |
| default_assignee_role | TEXT | | 默认负责岗位 |

#### 2.2.9 template_dependency（模板依赖）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | |
| template_id | INTEGER | FK → template.id | |
| from_phase_type | TEXT | NOT NULL | 前置阶段类型 |
| to_phase_type | TEXT | NOT NULL | 后续阶段类型 |
| type | TEXT | NOT NULL DEFAULT 'FS' | FS/SS/FF/SF |
| lag_days | INTEGER | DEFAULT 0 | 廦迟天数 |

### 2.3 标准阶段字典（phase_type 枚举；PHASE_TYPES_V2 §一 重排后）

| 代码 | 中文名 | 英文名 | 说明 |
|------|--------|--------|------|
| P1 | 需求评估 | requirement | 客户需求/招标要求分析 |
| P2 | 配置评估 | configuration | 硬件配置方案确认 |
| P3 | 模块选型 | selection | 核心模块/器件选型 |
| P4 | 工业设计 | industrial_design | 外观/造型设计 |
| P5 | 结构设计 | structure_design | 整机结构设计（含原"整机设计"） |
| P6 | 线缆设计 | cable_design | 线缆设计（新拆分环节） |
| P71 | 样机打样 | prototyping | 首版样机制作（子编号，原 P6） |
| P72 | 线缆打样 | cable_prototyping | 线缆打样（子编号，与样机打样同主位并行） |
| P8 | 联调测试 | testing | 功能/性能验证（原 P7） |
| P9 | 交付 | delivery | POC/投标/发货/量产保障（原 P8） |

> **历史兼容（决策 ③ 不迁移）**：存量阶段可能仍为旧值 `P6`（样机打样）/`P7`（联调测试）/`P8`（交付），显示保持原值；导入映射（§6.2）与排序按语义归一到新位（PHASE_TYPES_V2 §二/§三）。
> **重要**: phase_type 是标准枚举值，但实际项目的阶段名称可以是自定义文本（如"结构设计(第一版)"）。phase_type 用于匹配模板和依赖规则，name 用于显示。

---

## 三、项目模板定义

### 3.1 模板 A：招标/新品研发标准流程

**适用**: 银行招标项目、新品研发（覆盖国内大多数项目）

**阶段与默认依赖**:

```
P1 需求评估 ─┐
P2 配置评估 ─┼── SS(并行启动) ──→ P4 工业设计 ──FS──→ P5 结构设计 ──FS──→ P6 样机打样 ──FS──→ P7 联调测试 ──FS──→ P8 交付
P3 模块选型 ─┘
```

| from | to | type | lag | 默认工期 |
|------|----|------|-----|---------|
| P1 需求评估 | P4 工业设计 | SS | 0 | P1: 5天 |
| P2 配置评估 | P4 工业设计 | SS | 2 | P2: 5天 |
| P3 模块选型 | P4 工业设计 | SS | 3 | P3: 7天 |
| P4 工业设计 | P5 结构设计 | FS | 0 | P4: 7天 |
| P5 结构设计 | P6 样机打样 | FS | 0 | P5: 14天 |
| P6 样机打样 | P7 联调测试 | FS | 0 | P6: 15天 |
| P7 联调测试 | P8 交付 | FS | 0 | P7: 7天 |
| | | | | P8: 10天 |

### 3.2 模板 B：量产交付流程

**适用**: 海外量产项目（俄罗斯/越南/侧柜类）

```
结构设计 ──FS──→ 图纸归档 ──FS──→ BOM/激活 ──FS──→ 投料 ──FS──→ 首批生产保障 ──FS──→ 发货
```

### 3.3 模板 C：定制/改造流程

**适用**: 定制机、小批量改造项目

```
需求分析 ──FS──→ 工业设计(可选) ─FS──→ 结构设计 ─FS──→ 样机打样 ─FS──→ 测试 ─FS──→ 发货
```

### 3.4 返工机制

返工通过 **状态回退 + 返工日志** 实现（不是特殊依赖类型）：
1. 任意阶段可从 `进行中/已完成` 回退到 `未开始`
2. 每次回退写入 `rework_log`（原因、时间、回退路径）
3. `phase.rework_count` +1
4. 甘特图上 `rework_count > 0` 的阶段显示橙色标记
5. 所有返工记录永久保存用于复盘

---

## 四、API 设计

### 4.1 通用约定

- REST 风格，JSON 格式
- 日期格式：ISO 8601 (`YYYY-MM-DD`)
- 分页参数：`?page=1&page_size=20`
- 错误响应：`{ "detail": "错误描述" }`

### 4.2 API 端点清单

#### 项目

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/projects` | 项目列表（支持 ?status=&category=&market= 筛选） |
| GET | `/api/projects/{id}` | 项目详情（含 phases + dependencies） |
| POST | `/api/projects` | 创建项目 |
| PUT | `/api/projects/{id}` | 更新项目 |
| DELETE | `/api/projects/{id}` | 删除项目 |
| GET | `/api/projects/{id}/gantt` | 获取项目甘特图数据（dhtmlx 格式） |
| POST | `/api/projects/{id}/apply-template/{template_id}` | 从模板创建阶段+依赖 |

#### 阶段

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/projects/{project_id}/phases` | 阶段列表 |
| GET | `/api/phases/{id}` | 阶段详情 |
| POST | `/api/projects/{project_id}/phases` | 创建阶段 |
| PUT | `/api/phases/{id}` | 更新阶段 |
| DELETE | `/api/phases/{id}` | 删除阶段 |
| POST | `/api/phases/{id}/rework` | 阶段返工（回退状态+写日志） |

#### 依赖关系

| Method | Path | |
|--------|------|------|
| GET | `/api/projects/{project_id}/dependencies` | 依赖列表 |
| POST | `/api/projects/{project_id}/dependencies` | 创建依赖 |
| DELETE | `/api/dependencies/{id}` | 删除依赖 |

#### 资源/人员

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/resources` | 人员列表 |
| GET | `/api/resources/{id}/workload` | 某人负载（参与哪些项目/阶段） |
| POST | `/api/resources` | 创建人员 |
| PUT | `/api/resources/{id}` | 更新人员 |
| DELETE | `/api/resources/{id}` | 删除人员 |

#### 模板

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/templates` | 模板列表 |
| GET | `/api/templates/{id}` | 模板详情（含 phases + dependencies） |
| POST | `/api/templates` | 创建模板 |
| PUT | `/api/templates/{id}` | 更新模板 |
| DELETE | `/api/templates/{id}` | 删除模板 |

#### Excel 导入

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/import/excel` | 上传 Excel 文件并导入（multipart/form-data） |
| GET | `/api/import/report` | 获取最近一次导入的校验报告 |

### 4.3 示例：甘特图数据格式

`GET /api/projects/{id}/gantt` 返回 dhtmlxGantt 兼容格式：

```json
{
  "data": [
    {
      "id": 1,
      "text": "工行自提穿墙主柜TCM10-012",
      "start_date": "2026-07-01",
      "duration": 66,
      "progress": 0.45,
      "parent": 0,
      "type": "project",
      "open": true
    },
    {
      "id": 2,
      "text": "工业设计",
      "start_date": "2026-07-01",
      "end_date": "2026-07-04",
      "duration": 4,
      "progress": 1.0,
      "parent": 1,
      "type": "task",
      "rework_count": 0
    }
  ],
  "links": [
    { "id": 1, "source": 2, "target": 3, "type": "0", "lag": 0 }
  ]
}
```

> dhtmlxGantt link type 映射: `"0"`=FS, `"1"`=SS, `"2"`=FF, `"3"`=SF

### 4.4 示例：资源负载数据

`GET /api/resources/{id}/workload` 返回：

```json
{
  "resource": { "id": 1, "name": "曹俊杰", "role": "工业设计" },
  "workloads": [
    {
      "project_id": 1,
      "project_name": "工行自提穿墙主柜",
      "phase_id": 2,
      "phase_name": "工业设计",
      "plan_start": "2026-07-01",
      "period": ["2026-07-01", "2026-07-04"]
    }
  ]
}
```

---

## 五、Excel 导入规格

### 5.1 源文件

路径：`~/Desktop/整机项目进度及计划情况统计-0720.xlsx`  
Sheet：`项目情况统计-国内`（8个项目）、`项目情况统计-海外`（10个项目）

### 5.2 数据清洗规则

| 问题 | 处理方案 |
|------|---------|
| Excel 日期序列号（如 46199） | `datetime.date(1899,12,30) + timedelta(days=serial)` 转换为日期 |
| 文本日期（`2026/-/--`） | 标记为"待确认"，`plan_start`/`plan_end` 设为 NULL |
| 多人字段（空格分隔） | 正则 `[\s,，]+` 拆分 + trim，每人创建/匹配 RESOURCE |
| 空行 / 备注行 | 检测「项目编号 + 项目名称」同时为空 → 跳过 |
| 阶段名不一致 | 映射表（见下） |
| 单元格内换行（`\n`） | 清除换行，取第一行有效内容 |

### 5.3 阶段名映射表（PHASE_TYPES_V2 §二 重排后编号）

Excel 中的阶段名 → 标准 phase_type 映射：

```
「工业设计」       → P4 industrial_design
「结构设计」、「整机设计」 → P5 structure_design
「线缆设计」       → P6 cable_design（新环节）
「样机打样」       → P71 prototyping（原 P6）
「样机打样（1台）」 → P71 prototyping
「线缆打样」       → P72 cable_prototyping（新环节）
「联调测试」、「测试」、「测试与发货」 → P8 testing（原 P7）
「POC及投标」      → P9 delivery（原 P8）
「需求分析」、「需求评估」 → P1 requirement
「配置评估」       → P2 configuration
「模块选型」       → P3 selection
「直接投料」       → P9 delivery (量产)
「图纸归档」、「归档」 → P5 structure_design (后续阶段)
「BOM制作与激活」  → P9 delivery (量产)
「首批生产保障」   → P9 delivery (量产)
「投料」          → P9 delivery (量产)
「发货」          → P9 delivery
「归档（归档后再投料）」、「直接投料，BOM制作与激活」、「直接投料，激活时间」 → P9 delivery
```

### 5.4 导入流程

```
1. 解析两个 Sheet
2. 逐行读取：
   a. 项目编号无子编号（如 "1", "2"）→ 创建 Project
   b. 项目编号有子编号（如 "1-1", "2-3"）→ 创建 Phase（关联到父 Project）
3. 提取所有人名 → 创建/匹配 Resource → 写入 phase_assignee
4. 自动生成 Phase 之间的 FS 依赖（按 sequence 顺序）
5. 生成导入报告（成功/失败/警告）
```

### 5.5 导入校验报告格式

```json
{
  "total_rows": 50,
  "projects_imported": 18,
  "phases_imported": 62,
  "resources_created": 15,
  "errors": [
    { "row": 32, "field": "plan_end", "message": "无法解析日期 '2026/-/--', 已设为空" }
  ],
  "warnings": [
    { "row": 33, "field": "name", "message": "单元格包含换行符，已清除" }
  ]
}
```

---

## 六、前端规格

### 6.1 页面结构

```
App.tsx
├── Dashboard（首页看板）
│   ├── 项目状态分布（饼图/进度条）
│   ├── 延期预警列表
│   └── 返工统计
│
├── ProjectListPage（项目列表）
│   ├── 筛选：状态 / 类目 / 市场
│   └── 项目表格（点击进入详情）
│
├── ProjectDetailPage（项目详情）
│   ├── 项目基本信息（可编辑）
│   └── GanttChart（甘特图）
│       ├── 阶段进度条（颜色按状态）
│       ├── 依赖连线（FS/SS/FF/SF）
│       ├── 拖拽改期
│       ├── 点击阶段 → 弹出 PhaseEditor
│       └── rework_count>0 → 橙色标记
│
└── ResourcePage（资源负载）
    ├── 人员选择器
    └── 时间轴显示该人员参与的所有项目/阶段
```

### 6.2 dhtmlxGantt 配置要点

```javascript
// 核心配置方向（具体实现由开发者完成）
const ganttConfig = {
  // 时间轴尺度：支持日/周/月切换
  scale: ['day', 'week', 'month'],
  
  // 列定义（左侧任务列表）
  columns: [
    { name: 'text', label: '阶段', width: 200, tree: true },
    { name: 'assignees', label: '负责人', width: 120 },
    { name: 'start_date', label: '开始', width: 90, align: 'center' },
    { name: 'duration', label: '工期', width: 60, align: 'center' },
  ],
  
  // 甘特条颜色按状态
  task_class: {
    '已完成': 'task-done',
    '进行中': 'task-active',
    '未开始': 'task-pending',
    '延期': 'task-delayed',
    '已搁置': 'task-blocked',
  },
  
  // 依赖连线
  autoscheduling: true,        // 改父任务自动联动子任务
  auto_scheduling_strict: false, // 非严格模式（允许手动覆盖）
  
  // 拖拽
  drag_progress: true,
  drag_move: true,
  drag_resize: true,
  
  // 返工标记（自定义 task_class 规则）
  // rework_count > 0 时添加 'task-rework' class
  
  // 标记今天
  markers: [{ type: 'today' }],
  
  // 中文
  locale: gantt.locale.cn,
};
```

### 6.3 甘特条颜色方案

| 状态 | 背景色 | 说明 |
|------|--------|------|
| 已完成 | `#52c41a` (绿色) | |
| 进行中 | `#1890ff` (蓝色) | |
| 未开始 | `#d9d9d9` (灰色) | |
| 延期 | `#ff4d4f` (红色) | |
| 已搁置 | `#8c8c8c` (深灰) | |
| 返工(rework_count>0) | 橙色左边框 `#fa8c16` | 叠加在原状态颜色上 |

---

## 七、开发任务拆解（4 个 Phase）

### Phase 1：后端数据层 + API（第1周）

**任务清单**:
1. 创建 FastAPI 项目结构，配置虚拟环境
2. 安装依赖：fastapi, uvicorn, sqlalchemy, pydantic, openpyxl, pandas, python-multipart
3. 实现 SQLAlchemy ORM 模型（9 张表）
4. 实现 Pydantic schema（请求/响应模型）
5. 实现 CRUD API（项目/阶段/依赖/资源/模板）
6. 编写 `init_db.py`：建表 + 写入 3 套模板种子数据
7. 编写示例数据生成（1-2 个完整项目）
8. 配置 CORS

**验收标准**:
- [ ] `python init_db.py` 成功建库
- [ ] `uvicorn app.main:app --reload` 启动成功
- [ ] `localhost:8000/docs` 可访问 Swagger UI
- [ ] 所有 CRUD API 可用
- [ ] 3 套模板可查询

### Phase 2：Excel 导入（第2周）

**任务清单**:
1. 实现 `excel_importer.py`
2. 实现数据清洗逻辑（日期转换、人名拆分、空行跳过）
3. 实现阶段名 → phase_type 映射
4. 实现 `/api/import/excel` 接口
5. 导入实际 Excel 文件
6. 生成导入校验报告

**验收标准**:
- [ ] 18 个项目成功导入
- [ ] 日期序列号正确转换
- [ ] 多人字段正确拆分为独立人员
- [ ] 生成导入报告

### Phase 3：前端甘特图（第3周）

**任务清单**:
1. 初始化 React + Vite + TS 项目
2. 安装 antd, dhtmlx-gantt, axios, dayjs
3. 实现 API 封装层
4. 实现项目列表页
5. 封装 dhtmlxGantt React 组件
6. 实现甘特图数据加载（对接 `/api/projects/{id}/gantt`）
7. 宐视化依赖连线
8. 实现拖拽改期 + 自动联动
9. 实现阶段编辑面板
10. 实现返工标记显示

**验收标准**:
- [ ] 项目列表可浏览、筛选
- [ ] 甘特图正确渲染 18 个项目数据
- [ ] 依赖连线显示正确
- [ ] 拖拽改期可用
- [ ] 阶段编辑可保存

### Phase 4：资源视图 + 收尾（第4周）

**任务清单**:
1. 实现资源负载视图（按人查时间轴）
2. 实现多项目甘特图总览（叠加显示+筛选）
3. 实现首页看板（状态分布、延期预警、返工统计）
4. 实现 Excel 导出
5. 编写一键启动脚本 `start.sh`
6. 全量功能测试

**验收标准**:
- [ ] 可查询任意人员负载
- [ ] 多项目总览可用
- [ ] 首页看板展示关键指标
- [ ] 数据可导出 Excel
- [ ] 一键启动脚本可用

---

## 八、后续演进路径（不在本次 MVP 范围）

```
MVP (P1-P4)    →   Phase 5      →   Phase 6      →   Phase 7
单人使用           团队协作          智能化            平台化
                  用户认证          关键路径计算      微信/飞书集成
                  权限控制          资源冲突检测      移动端
                  团队填报          延期预警          数据看板/BI
                  通知推送          周报自动生成      多项目集管理
                  (SQLite→PostgreSQL)
```

---

> **本文档是完整的项目规格书，可直接交给 AI 编程工具作为开发输入。**  
> 配套文件：`schema.sql`（建表脚本）、`templates.json`（模板数据）  
> 🦞 Phoebe
