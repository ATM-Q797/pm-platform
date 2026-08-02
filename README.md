# 智能终端研发项目管理平台

> 硬件研发项目管理平台 — 从 Excel 手工管理升级为结构化数据驱动。

## 快速开始

### 环境要求

| 组件 | 版本 | 验证命令 |
|------|------|---------|
| Python | ≥ 3.12 | `python3.12 --version` |
| Node.js | ≥ 18 | `node --version` |
| npm | ≥ 9 | `npm --version` |

### 一键启动（开发完成后）

```bash
cd ~/Desktop/pm-platform
./start.sh
```

浏览器打开 `http://localhost:5173` 即可使用。

### 手动启动（开发模式）

#### 1. 启动后端

```bash
cd ~/Desktop/pm-platform/backend

# 创建虚拟环境（首次）
python3.12 -m venv venv
source venv/bin/activate

# 安装依赖（首次）
pip install -r requirements.txt

# 初始化数据库 + 模板（首次）
python init_db.py

# 启动 API 服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

后端启动后：
- API 服务：`http://localhost:8000`
- Swagger 文档：`http://localhost:8000/docs`

#### 2. 启动前端

```bash
cd ~/Desktop/pm-platform/frontend

# 安装依赖（首次）
npm install

# 启动开发服务器
npm run dev
```

前端启动后：`http://localhost:5173`

## 项目文档

| 文档 | 说明 | 给谁看 |
|------|------|--------|
| [PROJECT_SPEC.md](docs/PROJECT_SPEC.md) | **完整项目规格书** — 需求、数据模型、API、前端规格 | **AI 编程工具 / 开发者** ⬅️ 主要看这个 |
| [DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md) | 开发计划 — 技术选型分析、4阶段路线图、风险 | 项目经理 / 决策者 |
| [schema.sql](docs/schema.sql) | 数据库建表 SQL（9张表） | 开发者参考 |
| [templates.json](docs/templates.json) | 3套项目模板种子数据 | init_db.py 导入用 |

## 给 AI 编程工具（ZCode）的指引

如果你使用 ZCode / Cursor / Claude Code 等 AI 编程工具开发本项目：

1. **先读 `docs/PROJECT_SPEC.md`** — 这是完整规格书，包含数据模型、API 设计、前端规格、开发任务拆解。
2. **按 Phase 顺序开发** — 规格书第七章定义了 4 个 Phase，每个 Phase 有明确的任务清单和验收标准。
3. **数据模型以 `docs/schema.sql` 为准** — 9 张表的字段定义和约束是权威定义。
4. **模板数据直接用 `docs/templates.json`** — `init_db.py` 读取此文件写入数据库。
5. **Excel 导入参考规格书第五章** — 包含源文件路径、清洗规则、阶段名映射表。

### 开发顺序建议

```
Phase 1: 后端数据层 + API（第1周）
  └─ 先跑通 init_db.py，再写 CRUD API

Phase 2: Excel 导入（第2周）
  └─ 先写解析器，再导入实际数据

Phase 3: 前端甘特图（第3周）
  └─ 先搭项目骨架，再集成 dhtmlxGantt

Phase 4: 资源视图 + 收尾（第4周）
  └─ 资源负载视图 + 首页看板 + 一键启动
```

## 技术栈

- **后端**: Python 3.12 + FastAPI + SQLAlchemy + SQLite
- **前端**: React 18 + TypeScript + Vite + Ant Design 5
- **甘特图**: dhtmlxGantt 社区版
- **Excel**: openpyxl + pandas

---

> 🦞 Phoebe | 2026-08-02
