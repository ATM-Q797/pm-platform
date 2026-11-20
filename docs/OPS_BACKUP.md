# 数据备份与恢复运维手册

> 适用：生产机 10.53.9.38（裸机混合形态：systemd pm-backend + Nginx + PostgreSQL in docker 容器 `docker-db-1`）
> 本手册为备份体系的操作事实源；批档 `docs/batches/数据备份-2026-11-19.md` 记录本轮实施过程（可整体丢弃）。

## 一、备份了什么、在哪

| 对象 | 位置 | 说明 |
|---|---|---|
| 数据库每日/每周备份 | `/opt/backup/db/pm_platform-{daily,weekly}-<时间戳>.dump` | `pg_dump -Fc` 压缩归档 |
| 配置副本（随周备） | `/opt/backup/db/env-<时间戳>.env` | `deploy/.env` 原样副本（含库密码与 JWT 密钥），权限 600 |
| 备份日志 | `/var/log/pm-backup.log` | 每次备份的三查结果与异机推送记录 |
| 异机副本 | `backup.conf` 里 `REMOTE_TARGET` 指向的机器 | 未配置时跳过（日志明示） |

**不需要备份**：代码与镜像（git 仓库可重建）、Excel 上传文件（导入即入库，不落盘）。

## 二、节奏与保留

- **每日 02:30** cron 自动执行 `deploy/backup.sh`（周日自动走 weekly 通道；避开既有 00:10 业务快照任务）。cron 行形如：

  ```bash
  30 2 * * * /opt/pm-platform/deploy/backup.sh >/dev/null 2>>/var/log/pm-backup.log
  ```

  脚本内 `tee -a` 已自写日志，cron 行**不要**对 stdout 再做 `>>` 重定向（否则每次运行日志成对重复；stderr 仍捕获进同一日志）
- 保留：日备 **14 份**，周备 **8 份**，`.env` 副本随周备同周期——超期自动清理
- 单份体积约 110 KB（2026-11-19 实测，库 11 MB 压缩后），稳态总占用 < 60 MB

## 三、日常操作

**手动备份一次**（改库前建议先手动备一份）：

```bash
ssh root@10.53.9.38
/opt/pm-platform/deploy/backup.sh          # 日备
/opt/pm-platform/deploy/backup.sh --weekly # 周备（附 .env 副本）
```

**配置异机副本**（目标机 IP/账号到位后一次性配置）：

```bash
ssh root@10.53.9.38
cd /opt/pm-platform/deploy
cp backup.conf.example backup.conf
vi backup.conf    # 填 REMOTE_TARGET="用户@目标IP:/备份目录"；非 22 端口填 REMOTE_SSH_PORT（如 "2222"）；额外参数 BACKUP_RSYNC_ARGS 按空格分隔（不支持带引号的整体参数）
```

另需在目标机为该用户配置 ssh 免密（`ssh-copy-id`），并确认目标机装有 rsync。配置后下一次备份自动生效，无需重启任何服务。

**校验最近一次备份**：

```bash
tail -5 /var/log/pm-backup.log        # 看三查结果
ls -lh /opt/backup/db | tail -5       # 看文件与体积
```

## 四、恢复

### 方式 A：脚本恢复（推荐）

```bash
ssh root@10.53.9.38
# 演练/抽查（恢复到临时库，不动生产）：
/opt/pm-platform/deploy/restore.sh /opt/backup/db/pm_platform-daily-<时间戳>.dump pm_platform_restore_test
# 真恢复（覆盖 = 整库替换：恢复前自动预检 dump；目标库已存在时断连+DROP+重建；需输入库名确认，自动停启后端并健康检查）：
/opt/pm-platform/deploy/restore.sh /opt/backup/db/pm_platform-daily-<时间戳>.dump pm_platform
```

### 方式 B：人工恢复（不依赖脚本，脚本丢失时照此执行）

```bash
ssh root@10.53.9.38
# 1.（仅生产库被删/卷损时）重建库：
docker exec docker-db-1 psql -U pm_user -d postgres -c 'CREATE DATABASE pm_platform OWNER pm_user'
# 2. 恢复（先把 dump 文件放进容器可读路径或用 stdin）：
docker exec -i docker-db-1 pg_restore -U pm_user -d pm_platform -1 --exit-on-error --no-owner --no-privileges < /opt/backup/db/<dump文件>
# 3. 重启后端并确认：
systemctl restart pm-backend
curl -s http://127.0.0.1:8000/health
# 4. 若 .env 也丢失：从最近 env-*.env 副本恢复（cp 到 /opt/pm-platform/deploy/.env，chmod 600），再重启 pm-backend
```

### 恢复演练（每季度一次）

```bash
/opt/pm-platform/deploy/restore.sh <最新dump> pm_platform_restore_test
docker exec docker-db-1 psql -U pm_user -d pm_platform -tAc "SELECT count(*) FROM pg_tables WHERE schemaname='public'; SELECT count(*) FROM project"
docker exec docker-db-1 psql -U pm_user -d pm_platform_restore_test -tAc "SELECT count(*) FROM pg_tables WHERE schemaname='public'; SELECT count(*) FROM project"
# 两边读数一致即演练通过；然后清理：
docker exec docker-db-1 psql -U pm_user -d postgres -c 'DROP DATABASE pm_platform_restore_test'
```

## 五、演练记录

| 日期 | dump | 结果 | 表数/项目数比对 |
|---|---|---|---|
| 2026-11-19 | pm_platform-daily-2026-11-19-165038.dump | 通过，临时库已清理 | 生产 19 表 / 86 项目 = 演练库 19 表 / 86 项目 |

## 六、底线须知

- **没演练过的备份不算备份**——每季度演练一次，记录追加到上表
- `/opt/backup/db` 与生产数据同机：宿主机整盘故障时仅剩**异机副本**——异机副本尽快配置到位
- `env-*.env` 含明文密码：不得外传；**异机副本只接收 dump，不含 .env**——库密码与 JWT 密钥请另在密码管理器等安全处留存一份，否则整盘故障后备份无法恢复（库密码丢失）且旧 token 全失效需重新登录
