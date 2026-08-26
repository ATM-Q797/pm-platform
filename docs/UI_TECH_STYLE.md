# 科技感 UI 设计文档 —「深空驾驶舱」(Deep Space Console)

> **版本**: v1.0 | **日期**: 2026-08-26 | **状态**: 待评审
> **方案基础**: 五模型会诊（GLM/MiniMax/DeepSeek/Mimo/Kimi），**以 Kimi K3 方案为主**，融合共识要素
> **实施模型**: eng-coder 使用 `kimi:kimi-k3`

---

## 一、设计语言

### 1.1 核心要素（四件套）

| 要素 | 手法 |
|------|------|
| **玻璃拟态** | 卡片/Header/Modal `backdrop-filter: blur(12px)` + 半透明底 + `1px` 微光边框（`rgba(120,180,255,.18)`）+ 顶部 `1px` 高光线（`inset 0 1px 0 rgba(255,255,255,.08)`） |
| **发光** | 关键元素 `box-shadow: 0 0 12px rgba(0,212,255,.35)`；hover 加强至 `.5` |
| **网格纹理** | `colorBgLayout` 上叠 32px 极淡网格线 + 顶部径向渐变晕（紫光） |
| **渐变** | 主按钮/Logo/标题 `linear-gradient(135deg, #00d4ff, #7b61ff)`；大数字 `tabular-nums` + `background-clip: text` 渐变字 |

### 1.2 色值体系

| 角色 | 深色（主战场） | 浅色（降饱和保证对比度） |
|------|----------------|--------------------------|
| 主色 Primary | `#00d4ff`（电青） | `#0891b2` |
| 辅色 Accent | `#7b61ff`（星云紫） | `#6d5ae0` |
| 成功 Success | `#22e58a` | `#16a34a` |
| 警告 Warning | `#fbbf24` | `#d97706` |
| 危险 Error | `#ff4d6d` | `#e11d48` |
| 背景 Layout | `#0a0e1a` | `#eef2f8` |
| 容器 Container | `rgba(20,27,45,.72)` | `rgba(255,255,255,.8)` |
| 边框 Border | `rgba(120,180,255,.15)` | `rgba(8,145,178,.15)` |
| 文字 Primary | `#e8ecf8` | `#0f172a` |
| 文字 Secondary | `#9aa3b8` | `#475569` |

### 1.3 网格纹理（body 背景）

```css
background-image:
  linear-gradient(rgba(0,212,255,.04) 1px, transparent 1px),
  linear-gradient(90deg, rgba(0,212,255,.04) 1px, transparent 1px),
  radial-gradient(ellipse at 20% 0%, rgba(123,97,255,.12), transparent 50%);
background-size: 32px 32px, 32px 32px, 100% 100%;
```
浅色：网格 `rgba(8,145,178,.05)`、晕 `rgba(109,90,224,.08)`。

---

## 二、AntD Token 落地（main.tsx）

```tsx
token: {
  colorPrimary: isDark ? '#00d4ff' : '#0891b2',
  colorInfo:    isDark ? '#00d4ff' : '#0891b2',
  colorSuccess: isDark ? '#22e58a' : '#16a34a',
  colorError:   isDark ? '#ff4d6d' : '#e11d48',
  colorWarning: isDark ? '#fbbf24' : '#d97706',
  borderRadius: 10,
  colorBgLayout:    isDark ? '#0a0e1a' : '#eef2f8',
  colorBgContainer: isDark ? 'rgba(20,27,45,.72)' : 'rgba(255,255,255,.8)',
  colorBorder:      isDark ? 'rgba(120,180,255,.15)' : 'rgba(8,145,178,.15)',
  boxShadowTertiary: '0 0 0 1px rgba(0,212,255,.08), 0 8px 24px rgba(0,0,0,.25)',
},
components: {
  Layout: { headerBg: 'transparent', headerHeight: 56, siderBg: 'transparent' },
  Menu: {
    darkItemBg: 'transparent',
    itemSelectedBg: 'rgba(0,212,255,.12)',
    itemSelectedColor: isDark ? '#00d4ff' : '#0891b2',
    activeBarHeight: 3,
  },
  Card: { paddingLG: 20, colorBgContainer: isDark ? 'rgba(20,27,45,.55)' : 'rgba(255,255,255,.75)' },
  Table: { headerBg: isDark ? 'rgba(15,20,36,.9)' : 'rgba(240,246,252,.9)', rowHoverBg: 'rgba(0,212,255,.06)' },
  Button: { primaryShadow: '0 0 12px rgba(0,212,255,.35)' },
  Tag: { borderRadiusSM: 4 },
  Segmented: { itemSelectedBg: 'rgba(0,212,255,.15)' },
}
```

**新增 `frontend/src/styles/tech.css`**（index.css 之后 import）：承载玻璃/网格/发光/动画效果类，**变量全部进现有 `:root` + `[data-theme='dark']`**，深浅切换机制零改动。

---

## 三、逐页改造清单

| 页面 | 文件 | 关键改动 |
|------|------|----------|
| **导航壳** | `App.tsx` + tech.css | Header 玻璃条（`headerBg: transparent` + CSS `backdrop-filter: blur(16px)` + 底部 1px 青色边 + sticky）；Logo 渐变方块 + 发光；Menu 选中渐变下划线（activeBarHeight 3 + CSS）；Avatar 加青色 glow |
| **看板** | `DashboardPage.tsx` | 6 卡顶部 3px 渐变条（每卡不同色相）；数值 32px 渐变字 + tabular-nums；「今日聚焦」左侧 3px 电青竖线 + 背景微光；卡片 hover `translateY(-3px)` + 发光 |
| **项目列表** | `ProjectListPage.tsx` | 表格 headerBg 玻璃化、行 hover 青色光晕；状态 Tag 加 `box-shadow: 0 0 6px currentColor` 微光；筛选栏包玻璃容器 |
| **详情+甘特** | `ProjectDetailPage.tsx` + `gantt.css` | 甘特只改变量值：`--gantt-active` 系改青蓝渐变（`linear-gradient(180deg,#00d4ff,#0090c8)`）；关键路径红框发光加强 + 2s 呼吸动画；今日线加 glow；依赖连线青色 |
| **资源负载** | `ResourcePage.tsx` + `resourceView.css` | 复用变量；冲突 ⚠ 黄框发光动画 |
| **周报** | `ReportPage.tsx` + index.css | 预览容器玻璃卡；h2 左侧 3px 渐变竖线；blockquote 左边框电青 |
| **登录页** | `LoginPage.tsx` | 保持 DeepSeek 风 + 动态网格背景（缓慢 background-position 动画）+ 输入框 focus 发光环 `0 0 0 2px rgba(0,212,255,.3)` |
| **我的任务** | `MyTasksPage.tsx` | 统计卡渐变数字；Progress 渐变 `{from:'#00d4ff', to:'#7b61ff'}` |
| **用户管理/审核** | 继承 token | 零改动自动生效 |

---

## 四、动效与性能红线

| 场景 | 实现 |
|------|------|
| 全局过渡 | 仅 `background-color/border-color/box-shadow` 0.25s（不全量 transition） |
| 卡片 hover | `translateY(-3px)` + 发光阴影 |
| 关键路径/冲突 | `@keyframes pulse` 呼吸（2s / 1.4s） |
| 加载 | Spin 换电青；首屏用 `Skeleton` |
| 页面切换 | Suspense fallback 渐变进度条 |
| 降级 | `@media (prefers-reduced-motion: reduce)` 关闭全部动画 |

**性能红线**：`backdrop-filter` 只用于 Header/卡片/登录卡/Modal；表格行/列表项用实色半透明（避免大面积 blur 掉帧）。

---

## 五、实施批次

| 批次 | 内容 | 预计 |
|------|------|------|
| **P0** | index.css 变量换色 + main.tsx token + tech.css 网格/玻璃/发光 | 半天 |
| **P1** | 导航壳玻璃 + 看板 6 卡 + gantt.css 换肤与脉冲 | 1 天 |
| **P2** | 列表表格/Tag/筛选栏 + 登录页动效 + 资源负载 | 1 天 |
| **P3** | 周报排版 + 我的任务 + 空状态/对比度微调 | 0.5 天 |

---

## 六、验收标准

- [ ] 深浅两模式全站走查：网格纹理/玻璃/发光/渐变可见，无刺眼或不可读区域
- [ ] 甘特图：状态条青蓝渐变、关键路径红框呼吸、冲突黄框呼吸、今日线发光、连线青色（深浅均清晰）
- [ ] 看板 6 卡渐变条 + 渐变数字；列表行 hover 青色光晕；登录页网格动画
- [ ] `npm run build`（tsc -b）通过；`prefers-reduced-motion` 降级生效
- [ ] 浅色模式文字对比度 ≥ 4.5:1（电青不用作浅色文字）
- [ ] 主题切换/刷新记忆/无闪白（FOUC 脚本保留）无回归

---

## 七、涉及文件

```
frontend/src/main.tsx                    token 双套重写
frontend/src/index.css                   :root / [data-theme] 色值替换 + 新增变量
frontend/src/styles/tech.css（新）       玻璃/网格/发光/动画效果类
frontend/src/App.tsx                     导航壳玻璃化
frontend/src/pages/DashboardPage.tsx     看板 6 卡
frontend/src/pages/ProjectListPage.tsx   列表表格/筛选栏
frontend/src/pages/ProjectDetailPage.tsx 详情面板微调
frontend/src/components/Gantt/gantt.css  甘特变量换肤 + 动画
frontend/src/components/Resource/resourceView.css 资源负载
frontend/src/pages/LoginPage.tsx         登录页动效
frontend/src/pages/ReportPage.tsx        周报容器
frontend/src/pages/MyTasksPage.tsx       我的任务
```
（不涉及后端/数据库；不新增依赖）

---

> 评审通过后由 eng-coder（kimi:kimi-k3）按 P0→P3 实施。
> 🦞 | 2026-08-26
