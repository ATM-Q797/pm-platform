# update.sh 防嵌套改进 — 设计文档

> **版本**: v1.2 | **日期**: 2026-08-31
> **类型**: 部署脚本健壮性小改进（非业务功能）
> **评审**: 2026-08-31 设计评审通过（处置 1-4 采纳）；代码评审通过（无 🔴，🟡#1/#2 与 🔵#3 处置已并入 v1.2）

---

## 一、需求（用户故事）

> 作为平台运维人员，我希望 `deploy/update.sh` 能自动识别 `scp -r` 产生的 `dist/dist/` 嵌套目录，
> 从而在每次版本更新时**前端真正更新生效**（而非静默复制旧文件），且任何上传异常时**不产生半更新状态**。

## 二、问题陈述

**现象**：裸机部署时，本机 `scp -r frontend\dist root@服务器:/tmp/pm-dist` 存在经典陷阱——**目标目录 `/tmp/pm-dist` 已存在时，scp 会把 `dist` 作为子目录复制进去**，实际产物是 `/tmp/pm-dist/dist/`，而 `/tmp/pm-dist/index.html` 仍是旧文件。

**后果**：`deploy/update.sh` 执行 `cp -r "$DIST_DIR"/* /var/www/pm-platform/` 时复制的是**旧文件**，前端"更新无效"（2026-08-31 实况：服务器 `/tmp/pm-dist` 里 index.html 是 8/26 旧 hash，排查 3 轮才定位到嵌套）。

**现状**：update.sh 只检查 `$DIST_DIR` 存在（`deploy/update.sh:24-26`），不检查嵌套。

## 三、解决方案

在 `deploy/update.sh` 的输入检查段（`# 0. 检查输入文件`，24-26 行之后）追加**嵌套检测 + 完整性守卫**（评审处置 #2、代码评审 🟡#1/#2）：

```bash
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
```

**行为**：
- 正常场景（`/tmp/pm-dist` 内容 = dist 文件）：`$DIST_DIR/dist` 不存在 → 不变，走原逻辑
- 嵌套且完整（`index.html` + `assets/` 非空）：自动改用子目录 → 复制到站点的是**新文件**
- 嵌套但不完整（scp 中断/残缺）：**不切换**，回退平铺旧文件并输出警告（"陈旧但不损坏"）
- 最终源（无论平铺还是嵌套）缺 `index.html`：**在备份/后端更新之前明确报错退出**，避免"新后端 + 半新前端"混合状态
- 无网络、无交互、幂等（重复执行 `scp -r` 会合并进同一 `dist` 目录，不会二次嵌套）

## 四、受影响文件

| 文件 | 改动 |
|------|------|
| `deploy/update.sh` | 输入检查段追加嵌套检测 + 守卫（唯一代码改动） |
| `docs/DEPLOY_BARE_METAL.md` | ① 4.1 上传步骤补一行提示"若 `/tmp/pm-dist` 已存在先 `rm -rf /tmp/pm-dist`"（评审处置 #4，根治源头）；② 删除 2.3 节笔误行 `scp -r C:\pm-platform.zip 2>nul   # 忽略` |

**不改动**：migrate.sh、业务代码、前端、其他部署文件。

## 五、测试映射（评审处置 #1）

| 用例 | 类型 | 输入 | 预期输出 |
|------|------|------|----------|
| T1 嵌套且完整 | 边界 | `/tmp/pm-dist/dist/index.html` + `dist/assets/` 非空（内容 new），平铺为 old | 输出"检测到嵌套目录，改用…"；站点 index.html = new |
| T2 平铺正常 | 正常 | `/tmp/pm-dist/index.html` 存在，无 dist 子目录 | 行为与现状一致；站点 index.html = 平铺内容 |
| T3 嵌套不完整 | 错误 | `/tmp/pm-dist/dist/` 有 index.html 但无 assets/（模拟 scp 中断） | 输出"[警告]…仍使用平铺文件"；站点 = 平铺旧内容；脚本不中断（🟡#1） |
| T3b 源目录整体残缺 | 错误 | 平铺与嵌套均缺 index.html | 输出"[错误] 前端产物不完整…"；**exit 1，备份/后端更新不执行**（🟡#2） |
| T4 语法 | 错误 | `bash -n deploy/update.sh` | 退出码 0 |
| T5 实机验证 | 正常 | 服务器模拟 T1/T2 两种目录结构各跑一次 | 站点 hash 与源一致（见下） |

**实机 hash 验证命令**（评审处置 #3）：
```bash
md5sum /var/www/pm-platform/index.html /tmp/pm-dist/dist/index.html
# 两值一致 = 复制正确；嵌套场景下应与 /tmp/pm-dist/dist/index.html 相同
```

## 六、风险与对策

| 风险 | 对策 |
|------|------|
| 误判：用户故意在 /tmp/pm-dist 下放 dist 子目录作为正式内容 | 极低概率；且守卫要求 index.html + assets 均存在才切换，完整性有保障 |
| 嵌套 dist 残缺导致半更新 | 守卫不切换 + 警告；最终源硬校验失败则 exit 1（不触碰备份/后端）——"陈旧但不损坏"或"明确失败"（代码评审 🟡#1/#2） |
| 改动影响其他流程 | 仅 update.sh 单文件 + 指南两行文字，不触碰业务链路 |

## 七、checklist（评审处置 #1）

- [ ] T1-T5 测试用例全部通过（含实机验证）
- [ ] `bash -n deploy/update.sh` 通过
- [ ] 指南笔误行删除、rm -rf 提示已补充
- [ ] 代码评审 🟡#1/#2、🔵#3（备份时间戳加秒）处置完成

---

> 🦞 | 2026-08-31
