# 智能终端研发项目管理平台

> 硬件研发项目管理平台 — 从 Excel 手工管理升级为结构化数据驱动。

## 快速开始

### 环境要求

| 组件 | 版本 | 验证命令 |
|------|------|---------|
| Python | ≥ 3.12 | `python3.12 --version` |
| Node.js | ≥ 18 | `node --version` |
| npm | ≥ 9 | `npm --version` |

### 一键启动

**macOS / Linux：**
```bash
cd ~/Desktop/pm-platform
./start.sh
```

**Windows：**
```bat
cd %USERPROFILE%\Desktop\pm-platform
start.bat
```

首次运行会自动创建虚拟环境、安装依赖。浏览器打开 `http://localhost:5173` 即可使用。

### 手动启动（开发模式）

#### 1. 启动后端

```bash
cd ~/Desktop/pm-platform/backend

# 创建虚拟环境（首次）
python3 -m venv venv
source venv/bin/activate      # macOS/Linux
# venv\Scripts\activate        # Windows

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

## 功能概览

| 模块 | 功能 | 入口 |
|------|------|------|
| 📊 首页看板 | 项目/阶段状态分布、延期预警、返工统计 | `/`（默认首页） |
| 📋 项目列表 | 项目表格、状态/市场/类目筛选、Excel 导入导出 | `/projects` |
| 📅 项目甘特图 | dhtmlxGantt 甘特图、依赖连线、拖拽改期、阶段编辑、今天标记、空白处拖动平移 | 点击项目进入 `/projects/:id` |
| 👥 资源负载 | 每人一行，显示参与的所有项目/阶段，跨项目负载一目了然 | `/resources` |
| 🔄 Excel 导入 | 全量导入，自动清洗（日期/人名/阶段名映射）、生成校验报告 | 项目列表页"导入 Excel" |
| 📤 Excel 导出 | 导出当前所有数据，格式与导入对齐 | 项目列表页"导出 Excel" |

## 技术栈

- **后端**: Python 3.12 + FastAPI + SQLAlchemy + PostgreSQL
- **前端**: React 19 + TypeScript + Vite + Ant Design 6
- **甘特图**: dhtmlxGantt 社区版
- **Excel**: openpyxl + pandas
- **部署**: Docker + Nginx + Gunicorn

## 生产部署

### 环境要求

| 组件 | 版本 | 说明 |
|------|------|------|
| Docker | ≥ 24 | 容器运行时 |
| Docker Compose | ≥ 2.0 | 容器编排 |
| 服务器 | 2核4G+ | 推荐 Ubuntu 22.04 |

### 快速部署（Docker）

```bash
# 1. 克隆仓库
git clone https://github.com/ATM-Q797/pm-platform.git
cd pm-platform

# 2. 配置环境变量
cp deploy/.env.example deploy/.env
vim deploy/.env  # 填写 JWT_SECRET_KEY、POSTGRES_PASSWORD 等必填项

# 3. 一键部署
chmod +x deploy/deploy.sh
./deploy/deploy.sh
```

部署完成后访问 `http://your-server-ip` 即可使用。默认管理员账号：`admin / admin123`。

### 环境变量说明

| 变量 | 必填 | 说明 |
|------|------|------|
| `JWT_SECRET_KEY` | 是 | JWT 签名密钥（≥32字符），`python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `POSTGRES_PASSWORD` | 是 | 数据库密码 |
| `CORS_ORIGINS` | 是 | 前端域名，逗号分隔，如 `https://pm.example.com` |
| `COOKIE_SECURE` | 否 | HTTPS 环境设为 `true`，默认 `false` |
| `WORKERS` | 否 | 后端 worker 数，默认 4 |

### HTTPS 配置

1. 获取 SSL 证书（推荐 Let's Encrypt）
2. 将证书放入 `deploy/docker/ssl/` 目录
3. 编辑 `deploy/nginx/nginx.conf`，取消 HTTPS server 块的注释
4. 编辑 `deploy/docker/docker-compose.yml`，取消 SSL 证书挂载的注释
5. 设置 `COOKIE_SECURE=true`
6. `docker compose restart nginx backend`

### 数据库备份

```bash
# 备份
docker compose exec db pg_dump -U pm_user pm_platform > backup_$(date +%Y%m%d).sql

# 恢复
cat backup.sql | docker compose exec -T db psql -U pm_user pm_platform
```

---

> Phoebe | 2026-08-02
