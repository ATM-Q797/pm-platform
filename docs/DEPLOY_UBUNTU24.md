# 项目管理平台 — Ubuntu 24.04 内网云服务器部署指南（Docker 版）

> **版本**: v1.0 | **日期**: 2026-08-17
> **适用**: 公司内网云服务器 / Ubuntu 24.04 / Docker Compose 部署
> **替代**: `docs/内网部署操作指南.html`（旧版 SQLite 裸机方案已废弃，本项目现为 PostgreSQL + Docker 架构）

---

## 〇、部署架构

```
公司内网服务器 (Ubuntu 24.04)
│
├── Nginx 容器 (端口 80)          ← 同事浏览器访问 http://服务器IP
│     ├── 前端静态文件 (Vite 构建产物)
│     └── /api/* 反向代理 → backend:8000
│
├── backend 容器 (端口 8000, 仅容器内网)
│     └── Gunicorn + FastAPI + Uvicorn
│
└── db 容器 (PostgreSQL 16)
      └── 数据卷 pg_data（重启不丢，备份靠 pg_dump）
```

**端口说明**：对外只需开 **80**；8000/5432 只绑定容器内部与 127.0.0.1，不暴露公网。

---

## 一、准备清单

| 项目 | 说明 |
|------|------|
| 服务器 | Ubuntu 24.04，SSH 可登录，磁盘 ≥ 10GB（镜像+构建约 3GB） |
| 服务器 IP | 公司内网固定 IP（如 192.168.1.100）或云服务器内网 IP |
| 代码包 | 本仓库（含 deploy/ 目录） |
| 浏览器访问 | 内网任意机器浏览器，无需装任何客户端 |

---

## 二、第 1 步：安装 Docker（Ubuntu 24.04）

SSH 登录服务器后执行：

```bash
# 方式一：官方脚本（推荐，自动配置 apt 源）
curl -fsSL https://get.docker.com | sudo sh

# 方式二：Ubuntu 自带源（内网无法访问外网时用）
sudo apt update
sudo apt install -y docker.io docker-compose-v2

# 验证
docker --version          # 应显示 Docker version 26+ 
docker compose version    # 应显示 Docker Compose version v2.x

# 当前用户免 sudo 使用 docker（重新 SSH 登录后生效）
sudo usermod -aG docker $USER
```

> ⚠️ 云服务器厂商（阿里云/腾讯云等）若提供"安装 Docker"一键按钮也可用。
> 验证后**退出 SSH 重新登录**，使 docker 组权限生效。

---

## 三、第 2 步：获取代码

内网服务器通常无法直连 GitHub，二选一：

### 方式 A：服务器能访问 GitHub（或公司配置了代理）

```bash
cd /opt
git clone https://github.com/ATM-Q797/pm-platform.git
cd pm-platform
```

### 方式 B：本机打包上传（推荐，内网环境）

**本机（Windows）操作**：打包已提交的全部代码

```powershell
# 在项目目录打开 PowerShell，执行：
git archive --format=zip -o pm-platform.zip HEAD
```

> `git archive` 只打包**已提交**的文件（自动排除 node_modules/venv/dist）。若本地有未提交的改动，先 `git add -A` 再执行（或改用整目录打包）。

**上传到服务器**（本机 PowerShell）：

```powershell
scp pm-platform.zip 用户名@服务器IP:/opt/
```

**服务器上解压**：

```bash
cd /opt
sudo apt install -y unzip
unzip pm-platform.zip -d pm-platform
cd pm-platform
```

---

## 四、第 3 步：配置环境变量

```bash
cd /opt/pm-platform
cp deploy/.env.example deploy/.env
vim deploy/.env
```

**必须修改的三项**：

```ini
# 1. PostgreSQL 密码（改成强密码）
POSTGRES_PASSWORD=改成你自己的强密码

# 2. JWT 密钥（至少 32 字符随机串）— 生成方式：
#    openssl rand -hex 32   （服务器上执行，复制结果粘贴到这里）
JWT_SECRET_KEY=

# 3. CORS 白名单：填同事访问用的地址（IP 或域名）
CORS_ORIGINS=http://192.168.1.100
```

**确认这两项保持如下**（内网 HTTP 部署的关键，已修复过默认值）：

```ini
COOKIE_SECURE=false     # 必须 false！HTTP 部署下 true 会导致登录后跳回登录页
HTTP_PORT=80
```

> 其余项（WORKERS/TOKEN_EXPIRE_HOURS 等）保持默认即可。

---

## 五、第 4 步：一键部署

```bash
# 给脚本执行权限
chmod +x deploy/deploy.sh

# 执行部署（首次构建镜像约 3-10 分钟，取决于网络）
./deploy/deploy.sh
```

**脚本自动完成**：检查环境变量 → 检查 Docker → 构建镜像 → 启动三个容器 → 健康检查 → **首次自动初始化数据库**（建表 + 管理员账户 + 3 套项目模板种子）。

看到如下输出即成功：

```
  部署完成！
  访问地址:  http://localhost:80
  默认管理员账号: admin / admin123
```

> ⚠️ **镜像拉取失败**（公司内网无法访问 Docker Hub）时，配置镜像加速：
> 编辑 `/etc/docker/daemon.json`：
> ```json
> { "registry-mirrors": ["https://docker.m.daocloud.io", "https://dockerproxy.com"] }
> ```
> 然后 `sudo systemctl restart docker`，重新执行部署脚本。

---

## 六、第 5 步：验证部署

在**服务器上**先自测：

```bash
# 1. 三个容器都应 running
docker compose -f deploy/docker/docker-compose.yml --env-file deploy/.env ps

# 2. 后端健康检查
curl http://127.0.0.1:8000/health
# 期望: {"status":"ok","service":"pm-platform-api","env":"production","database":"ok"}

# 3. 前端页面
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:80
# 期望: 200

# 4. 登录接口
curl -s -X POST http://127.0.0.1:80/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
# 期望: 返回 user 信息（含 must_change_password）
```

然后**同事机器浏览器**访问 `http://服务器IP`：
1. 打开登录页 ✅
2. `admin / admin123` 登录 ✅
3. **立即修改密码**（首次登录强制）✅
4. 项目列表 → 甘特图 → 资源负载 全部正常 ✅

---

## 七、第 6 步（可选）：迁移本机现有数据

如果要把本机 PostgreSQL 里已有的 **17 个项目数据** 带过去：

### 7.1 本机导出

```powershell
# 本机 Windows（需已安装 PostgreSQL 客户端，或从 pgAdmin 的 bin 目录执行）
pg_dump -U postgres -h localhost -d pm_platform -F c -f pm_platform.dump
# 输入 postgres 用户密码（默认 postgres）
```

### 7.2 上传

```powershell
scp pm_platform.dump 用户名@服务器IP:/opt/
```

### 7.3 服务器恢复（先恢复数据库，再启动应用）

```bash
cd /opt/pm-platform/deploy/docker

# 1. 只启动数据库容器
docker compose --env-file ../.env up -d db

# 2. 等待数据库就绪后恢复数据（--clean 会清掉 init 产生的种子表再重建）
docker compose --env-file ../.env exec -T db \
  pg_restore -U pm_user -d pm_platform --clean --if-exists \
  < /opt/pm_platform.dump

# 3. 再启动后端和前端（deploy.sh 检测到已有数据表，会自动跳过 init_db）
cd /opt/pm-platform
./deploy/deploy.sh
```

> ⚠️ 如果已经跑过 `init_db.py`（有种子数据），pg_restore 的 `--clean` 会覆盖；若恢复报错，先 `docker compose down -v`（**会清空数据卷**）后从头按 7.3 顺序执行。

---

## 八、第 7 步：防火墙与安全

```bash
# 服务器本机防火墙：只放行 80
sudo ufw allow 80/tcp
sudo ufw enable
sudo ufw status

# 云服务器安全组：控制台放行 TCP 80（来源限制为公司内网段更安全）
```

**不需要开放** 8000/5432（compose 已配置仅绑定 127.0.0.1）。

**建议**：部署完成后修改 admin 密码，并在「用户管理」中为同事创建账号（不要共用 admin）。

---

## 九、日常运维

| 操作 | 命令（在 /opt/pm-platform 下） |
|------|------|
| 查看容器状态 | `docker compose -f deploy/docker/docker-compose.yml --env-file deploy/.env ps` |
| 查看日志（后端） | `docker compose -f deploy/docker/docker-compose.yml logs -f backend` |
| 重启服务 | `docker compose -f deploy/docker/docker-compose.yml restart` |
| 停止服务 | `docker compose -f deploy/docker/docker-compose.yml down` |
| **备份数据库** | `docker compose -f deploy/docker/docker-compose.yml exec db pg_dump -U pm_user -d pm_platform -F c > backup-$(date +%F).dump` |
| 恢复备份 | 同 7.3 节步骤（pg_restore --clean） |
| 更新代码 | `git pull`（或重新上传 zip）→ `./deploy/deploy.sh`（数据卷保留，不丢数据） |
| 开机自启 | Docker 服务 `sudo systemctl enable docker`；容器已配 `restart: unless-stopped` 自动拉起 |

---

## 十、常见问题排查

| 现象 | 原因与解决 |
|------|-----------|
| 登录后点击页面**跳回登录页** | `COOKIE_SECURE` 被设成了 true → 改 `deploy/.env` 为 `COOKIE_SECURE=false` → `./deploy/deploy.sh` 重新部署 |
| 浏览器打不开页面 | ① 服务器 `curl http://127.0.0.1:80` 测本机 ② `ufw status` ③ 云安全组放行 80 ④ 同事与服务器同网段 |
| 登录接口 502/404 | nginx 反代问题 → `docker compose logs nginx`；确认 backend 容器 running |
| 后端 500 / 数据库错误 | `docker compose logs backend`；`curl http://127.0.0.1:8000/health` 看 database 状态 |
| 镜像拉取失败 | 配置 daemon.json 镜像加速（见第 4 步） |
| 修改 .env 后不生效 | 环境变量在构建/启动时注入 → 改完必须重新 `./deploy/deploy.sh`（或至少 `docker compose up -d`） |
| Excel 导入报错 | 文件大小上限 20MB（nginx 已配置）；确认是 14 列模板格式 |
| 忘记 admin 密码 | `docker compose exec backend python -c "from app.database import SessionLocal; from app.models import User; from app.core.security import hash_password; db=SessionLocal(); u=db.query(User).filter_by(username='admin').first(); u.password_hash=hash_password('新密码'); u.must_change_password=False; db.commit(); print('OK')"` |

---

## 附：目录对照速查

```
/opt/pm-platform/
├── deploy/
│   ├── .env                  ← 你的配置（.env.example 复制而来）
│   ├── deploy.sh             ← 一键部署脚本
│   ├── docker/
│   │   ├── docker-compose.yml
│   │   ├── Dockerfile.backend
│   │   └── Dockerfile.frontend
│   └── nginx/nginx.conf      ← 反向代理 + 静态托管
├── backend/                  ← 后端源码（打进镜像）
├── frontend/                 ← 前端源码（构建进镜像）
└── docs/                     ← 文档
```

> 🦞 | 2026-08-17
