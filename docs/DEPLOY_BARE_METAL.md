# 项目管理平台 — 裸机部署指南（非 Docker）

> **版本**: v1.0 | **日期**: 2026-08-26
> **适用**: 公司内网 Ubuntu 24.04 服务器，无外网，不想维护 Docker 镜像
> **前置**: 服务器已有 Docker 部署的 db 容器（PostgreSQL，数据卷 pg_data）

---

## 一、架构

```
宿主机 (10.53.9.38, Ubuntu 24.04)
│
├── PostgreSQL：沿用 docker db 容器（数据卷 pg_data 不动！）
│     端口 127.0.0.1:5432 已映射到宿主机 ✅
│
├── 后端：系统 Python 3.12 venv + Gunicorn（systemd 托管）
│     监听 127.0.0.1:8000，直接连 localhost:5432
│
└── Nginx（系统 apt 安装）：监听 80
      ├── 前端静态文件 /var/www/pm-platform（本机构建的 dist）
      └── /api/* 反向代理 → 127.0.0.1:8000

停用 docker 的 backend/nginx 容器（保留 db 容器，随时可 start 回滚）
```

**与 Docker 方案的核心区别**：更新时只传**前端 dist（几 MB）+ 后端代码 zip（2 MB）+ 可选 wheels**，不需要构建/传输 1GB 镜像。

---

## 二、本机准备（Windows，一次性 + 每次更新重复）

### 2.1 后端依赖（二选一）

**① 服务器 pip 可联网（推荐，最简单）**：跳过下载 wheel，直接在服务器上执行 3.3 的在线安装。

**② 服务器无外网时**：在本机下载 Linux 版 wheel（约 100-150MB）：

```powershell
cd C:\Users\1\Desktop\pm-platform\backend

# 用 any python3.12 环境（本机 venv 即可）下载 Linux 版 wheel
venv\Scripts\python.exe -m pip download `
  --platform manylinux2014_x86_64 --python-version 3.12 `
  --implementation cp --abi cp312 --only-binary=:all: `
  -r requirements.txt -d C:\wheels

# 验证数量（应等于 requirements 的包 + 传递依赖，约 40+ 个文件）
dir C:\wheels | Measure-Object | Select-Object Count
```

> 若某个包报"找不到 wheel"（如只有源码包），单独处理：
> ```powershell
> venv\Scripts\python.exe -m pip download 包名 --platform manylinux2014_x86_64 --python-version 3.12 --implementation cp --abi cp312 -d C:\wheels
> ```
> 再不行就换用 `--no-deps` 手动补齐。

### 2.2 构建前端 dist

```powershell
cd C:\Users\1\Desktop\pm-platform\frontend
npm run build
# 产物：frontend/dist/（几 MB）
```

### 2.3 上传

```powershell
scp C:\pm-platform.zip root@10.53.9.38:/opt/            # 后端代码（git archive 打包）
scp -r frontend\dist root@10.53.9.38:/tmp/pm-dist       # 前端产物
# wheel 目录上传
scp -r C:\wheels root@10.53.9.38:/tmp/pm-wheels
```

> ⚠️ 若 `/tmp/pm-dist` 已存在，`scp -r` 会把 dist 复制成 `/tmp/pm-dist/dist/` 子目录（嵌套陷阱）。
> 上传前先在服务器执行 `rm -rf /tmp/pm-dist` 删除旧目录；`deploy/update.sh` 已内置嵌套自动识别（v1.1+）。

> 上传多个文件可用一条 scp：`scp C:\pm-platform.zip root@IP:/opt/` + `scp -r frontend\dist C:\wheels root@IP:/tmp/`（scp 多源到目录）

---

## 三、服务器搭建（一次性，约 20 分钟）

### 3.1 停用 docker 的 backend/nginx（保留 db！）

```bash
cd /opt/pm-platform
docker compose -f deploy/docker/docker-compose.yml --env-file deploy/.env stop backend nginx
# 确认 db 仍在运行
docker ps --format "table {{.Names}}\t{{.Status}}"
```

> `stop` 不删容器——随时 `docker compose start backend nginx` 即可整体回滚到 Docker 方案。

### 3.2 安装系统依赖

```bash
sudo apt install -y nginx python3.12-venv
```

### 3.3 后端环境（venv + 离线安装依赖）

```bash
# 解压最新代码（覆盖源码；venv 不在 zip 里，不受影响）
cd /opt && unzip -o /opt/pm-platform.zip -d /opt/pm-platform

# 建 venv 并安装依赖（二选一）
cd /opt/pm-platform/backend
python3.12 -m venv venv

# ① 服务器 pip 可联网（推荐）：
./venv/bin/pip install -r requirements.txt

# ② 离线安装（服务器无外网时）：
# ./venv/bin/pip install --no-index --find-links=/tmp/pm-wheels -r requirements.txt

# 验证
./venv/bin/python -c "import fastapi, sqlalchemy, psycopg2; print('依赖 OK')"
```

### 3.4 配置 systemd 服务

```bash
sudo tee /etc/systemd/system/pm-backend.service > /dev/null <<'EOF'
[Unit]
Description=PM Platform Backend
After=docker.service network-online.target
Wants=docker.service

[Service]
User=root
WorkingDirectory=/opt/pm-platform/backend
EnvironmentFile=/opt/pm-platform/deploy/.env
Environment=DATABASE_URL=postgresql://pm_user:你的密码@127.0.0.1:5432/pm_platform
Environment=BIND=127.0.0.1:8000
Environment=APP_ENV=production
ExecStart=/opt/pm-platform/backend/venv/bin/gunicorn app.main:app -c gunicorn_conf.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
```

> ⚠️ 把 `你的密码` 换成 deploy/.env 里的 POSTGRES_PASSWORD（与 db 容器一致）。
> DATABASE_URL 里密码同样**只能用字母数字**（含 @ 会解析错乱）。

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pm-backend
sudo systemctl status pm-backend    # 应显示 active (running)
```

### 3.5 配置 Nginx

```bash
# 前端目录
sudo mkdir -p /var/www/pm-platform
sudo cp -r /tmp/pm-dist/* /var/www/pm-platform/

# 站点配置
sudo tee /etc/nginx/sites-available/pm-platform > /dev/null <<'EOF'
server {
    listen 80 default_server;
    server_name _;

    root /var/www/pm-platform;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;
        client_max_body_size 20m;
    }
}
EOF

# 启用站点（移除默认站点避免端口冲突）
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -s /etc/nginx/sites-available/pm-platform /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl enable --now nginx
```

### 3.6 数据库迁移 + 验证

```bash
cd /opt/pm-platform/backend

# 迁移（设置与 systemd 相同的连接参数）
set -a && source ../deploy/.env && set +a
export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:5432/${POSTGRES_DB}"
./venv/bin/python migrate_v2.py

# 验证
curl -s http://127.0.0.1:8000/health
# 期望: {"status":"ok",...,"database":"ok"}

./venv/bin/python -c "from app.database import SessionLocal; from app.models import Project; db=SessionLocal(); print('项目数:', db.query(Project).count())"
```

浏览器访问 `http://10.53.9.38` → 新版本界面 + 数据完好。

---

## 四、日常更新流程（一键脚本，约 4 分钟）

> 更新脚本 `deploy/update.sh` 自动完成：备份当前版本 → 更新代码 → 更新前端（含权限修复）→ 重启后端 → 健康检查。
> **全程不触碰数据库**（数据在 docker pg_data 卷 / PostgreSQL 中，与代码更新完全隔离）。

### 4.1 本机：打包 + 构建 + 上传（约 3 分钟）

```powershell
cd C:\Users\1\Desktop\pm-platform

# ① 打包最新代码
git archive --format=zip -o C:\pm-platform.zip HEAD

# ② 构建前端
cd frontend && npm run build

# ③ 上传两个文件（zip 和 dist）
scp C:\pm-platform.zip root@10.53.9.38:/opt/
scp -r frontend\dist root@10.53.9.38:/tmp/pm-dist
```

> ⚠️ 若 `/tmp/pm-dist` 已存在，`scp -r` 会嵌套成 `/tmp/pm-dist/dist/`。上传前先在服务器执行 `rm -rf /tmp/pm-dist`（`update.sh` 已内置嵌套自动识别 v1.1+，双保险）。

### 4.2 服务器：一条命令完成更新（约 1 分钟）

```bash
bash /opt/pm-platform/deploy/update.sh
```

输出应为：
```
[1/4] 已备份当前版本 → /opt/backup / /var/www/pm-platform.bak
[2/4] 后端代码已更新
[3/4] 前端已更新
[4/4] 后端健康 ✅
```

### 4.3 数据库迁移（仅当发布说明标注"需迁移"时）

```bash
bash /opt/pm-platform/deploy/migrate.sh
```

> 迁移脚本自动读取 .env 配置连接数据库，幂等可重复执行。
> 不涉及模型变更的常规更新（改 UI、改接口逻辑）**不需要**执行此步。

### 4.4 验证

```bash
curl -s http://127.0.0.1:8000/health
```
浏览器访问 `http://10.53.9.38`（若界面旧，Ctrl+F5 强刷）。

### 4.5 数据安全说明

| 问 | 答 |
|---|---|
| 更新会丢数据吗？ | **不会**。数据库在 docker `pg_data` 卷里，更新只覆盖 `/opt/pm-platform` 代码目录和 `/var/www/pm-platform` 前端目录 |
| .env 配置会丢吗？ | 不会。`.env` 不在 zip 里（.gitignore 排除），unzip 不碰它 |
| venv 依赖会丢吗？ | 不会。`venv/` 不在 zip 里；仅当 `requirements.txt` 变更时才需手动 `pip install -r requirements.txt` |
| 建议的定期备份 | 每周一次：`docker compose -f deploy/docker/docker-compose.yml --env-file deploy/.env exec -T db pg_dump -U pm_user -d pm_platform -F c > /opt/backup/db-$(date +%F).dump` |

---

## 五、回滚方案

| 场景 | 操作 |
|------|------|
| 后端有问题 | `unzip -o /opt/backup/code-prev-*.zip -d /opt/pm-platform && sudo systemctl restart pm-backend` |
| 前端有问题 | `sudo cp -r /var/www/pm-platform.bak/* /var/www/pm-platform/` |
| 整体退回 Docker 方案 | `systemctl stop pm-backend nginx` → `docker compose start backend nginx`（旧容器/旧镜像还在） |

> `update.sh` 每次更新前自动生成备份（`/opt/backup/code-prev-<时间>.zip` + `/var/www/pm-platform.bak`），回滚无需任何准备。

数据始终在 pg_data 卷，任何回滚不涉及数据。

---

## 六、安全红线与提醒

- ❌ 不要 `docker compose down -v` / `docker volume rm pg_data`（数据全丢）
- ✅ `docker compose stop backend nginx` 是安全的（容器保留）
- systemd 服务里 DATABASE_URL 含明文密码 → 文件默认 root 可读即可，别改成 644
- 服务器 .env 不在 git 里（.gitignore 排除），unzip 覆盖不会丢配置
- 80 端口被 docker nginx 占用时，宿主机 nginx 起不来 → 先确认 3.1 已 stop

---

> 🦞 | 2026-08-26
