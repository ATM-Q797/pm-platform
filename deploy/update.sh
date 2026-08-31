#!/usr/bin/env bash
# ============================================================
# PM 平台一键更新（裸机部署）— 不丢失数据
# ============================================================
# 前置条件（本机已上传）：
#   /opt/pm-platform.zip   ← git archive 打包的最新代码
#   /tmp/pm-dist/          ← npm run build 的最新前端产物
#
# 用法：bash /opt/pm-platform/deploy/update.sh
# 数据安全：本脚本不触碰数据库（数据在 docker pg_data 卷 / PostgreSQL 中）
# ============================================================
set -euo pipefail

FRONT_DIR=/var/www/pm-platform
PROJECT_DIR=/opt/pm-platform
CODE_ZIP=/opt/pm-platform.zip
DIST_DIR=/tmp/pm-dist
BACKUP_DIR=/opt/backup

echo "=================================================="
echo "  PM 平台更新（裸机部署）"
echo "=================================================="

# 0. 检查输入文件
[ -f "$CODE_ZIP" ] || { echo "[错误] 未找到代码包: $CODE_ZIP（请先 scp 上传）"; exit 1; }
[ -d "$DIST_DIR" ] || { echo "[错误] 未找到前端产物: $DIST_DIR（请先 scp 上传）"; exit 1; }

# scp -r 嵌套防御：目标目录已存在时 dist 会被复制成 dist/dist/ 子目录
if [ -d "$DIST_DIR/dist" ]; then
    # 完整性：index.html + assets 目录均需存在（防止 scp 中断时误切换残缺前端）——代码评审 🟡#1
    if [ -f "$DIST_DIR/dist/index.html" ] && [ -n "$(ls -A "$DIST_DIR/dist/assets" 2>/dev/null)" ]; then
        echo "    检测到嵌套目录，改用 $DIST_DIR/dist"
        DIST_DIR="$DIST_DIR/dist"
    else
        echo "    [警告] 检测到嵌套目录但内容不完整（缺 index.html 或 assets），仍使用 $DIST_DIR 平铺文件"
    fi
fi

# 最终源目录硬校验：不完整则明确失败退出，绝不带残缺源进入 cp（代码评审 🟡#2）
if [ ! -f "$DIST_DIR/index.html" ]; then
    echo "[错误] 前端产物不完整（$DIST_DIR 缺 index.html），请重新上传 dist 后再更新"
    exit 1
fi

# 1. 备份当前版本（回滚保障）
mkdir -p "$BACKUP_DIR"
cp -f "$CODE_ZIP" "$BACKUP_DIR/code-prev-$(date +%F-%H%M%S).zip"
rm -rf "${FRONT_DIR}.bak"
cp -r "$FRONT_DIR" "${FRONT_DIR}.bak"
echo "[1/4] 已备份当前版本 → $BACKUP_DIR / ${FRONT_DIR}.bak"

# 2. 更新后端代码（.env / venv 不在 zip 里，配置与依赖保留）
cd /opt
unzip -o "$CODE_ZIP" -d "$PROJECT_DIR"
echo "[2/4] 后端代码已更新"

# 3. 更新前端 + 修复权限（700 会导致 assets 404）
cp -r "$DIST_DIR"/* "$FRONT_DIR"/
chmod -R a+rX "$FRONT_DIR"
echo "[3/4] 前端已更新"

# 4. 重启后端 + 健康检查
sudo systemctl restart pm-backend
sleep 2
if curl -sf http://127.0.0.1:8000/health > /dev/null; then
    echo "[4/4] 后端健康 ✅"
else
    echo "[4/4] 后端异常 ⚠️  查看: journalctl -u pm-backend -n 50"
fi

echo ""
echo "=================================================="
echo "  更新完成！"
echo ""
echo "  回滚方法："
echo "    后端: unzip -o $BACKUP_DIR/code-prev-*.zip -d $PROJECT_DIR && sudo systemctl restart pm-backend"
echo "    前端: cp -r ${FRONT_DIR}.bak/* $FRONT_DIR/"
echo ""
echo "  数据库迁移：若本次发布说明要求迁移，执行:"
echo "    bash $PROJECT_DIR/deploy/migrate.sh"
echo "=================================================="
