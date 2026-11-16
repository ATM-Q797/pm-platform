# 科技感 UI 设计文档 —「深空驾驶舱」(Deep Space Console)

> **版本**: v1.1 | **日期**: 2026-08-26（2026-11-13 增补用户裁定注记） | **状态**: 已评审处置（2026-08-26 评审处置 + 2026-11-13 批 1 注记落档）
> **方案基础**: 五模型会诊（GLM/MiniMax/DeepSeek/Mimo/Kimi），**以 Kimi K3 方案为主**，融合共识要素
> **实施模型**: eng-coder 使用 `kimi:kimi-k3`
> **查证记录**: 一手来源 = 用户裁定与对照快照（各行出处列明）；公开来源未查证——材质参数为快照直取与既有 token 系推导，无外部规格面需核。

---

## 文档状态与权威性（2026-08-26 设计评审处置）

1. 本文档为平台**主题与视觉设计的唯一权威文档**：
   - **取代** `docs/UI_THEME_PLAN.md` 中的深色色板定义（§2.4）与 Header 方案（§2.3）——以本文档色值为准
   - `docs/UI_THEME_PLAN.md` 保留为主题基础设施（ThemeProvider / FOUC / 开关机制）的历史记录，仅作参考
2. **基础设施已实施完成**（commit `f1b4f96`）：ThemeProvider（`theme.tsx`）、`<html data-theme>`、index.html FOUC 脚本、`index.css` `:root`/`[data-theme]` 双变量板、gantt.css / resourceView.css 全文件变量化均已落地。本文档**仅在其上叠加视觉层**，不重复建设、不改变切换机制。
3. 甘特/资源负载：仅升级 `--gantt-*` 变量值与动画，结构零改动。

---

## 一、设计语言

### 1.1 核心要素（四件套）

| 要素 | 手法 |
|------|------|
| **液态玻璃** | L1 面板/L2 控件两档玻璃面材（`backdrop-filter: var(--glass-filter)` = blur 30px + saturate 1.9）+ 发丝亮边（`--glass-edge`）+ inset 顶光 1.5px + 底厚感；导航壳 Header 恒深玻璃条 `blur(16px)`（token 系见 §1.4） |
| **发光** | HDR 辉光（`--glass-glow` 白晕/深色蓝晕，随玻璃影栈 0 0 14px）作点缀；accent 面辉光 `--glass-glow-accent` |
| **极光地面** | html 画布层：线性渐变基底 + 三枚大半径径向光斑（`--ground-*`），玻璃面材透出地面即液态感（见 §1.3） |
| **渐变** | 主按钮/Logo 徽标底 `linear-gradient(135deg, #00d4ff, #7b61ff)`（accent 身份保留；徽标内芯 = 自绘三柱递升 SVG，白档三档透明度——用户 2026-11-14 ②）；数字走语义色（统计卡形制见 §三） |

### 1.2 色值体系

| 角色 | 深色（主战场） | 浅色（降饱和保证对比度） |
|------|----------------|--------------------------|
| 主色 Primary | `#00d4ff`（电青） | `#0369a1`（深青，正文级对比 ≥4.5:1） |
| 辅色 Accent | `#7b61ff`（星云紫） | `#6d5ae0`（仅作渐变点缀，不作文字色） |
| 成功 Success | `#22e58a` | `#16a34a` |
| 警告 Warning | `#fbbf24` | `#b45309`（对 .8 白容器面作文字 4.9:1；警示文字落容器面——落浅色 Layout 底仅 4.47:1，不作页面底色文字用） |
| 危险 Error | `#ff4d6d` | `#e11d48` |
| 背景 Layout | `#0a0e1a` | `#eef2f8` |
| 背景 Secondary（填报页项目字段栏） | `#182034` | `#fafafa` |
| 容器 Container | `rgba(20,27,45,.72)` | `rgba(255,255,255,.8)` |
| 边框 Border | `rgba(120,180,255,.15)` | `rgba(8,145,178,.15)` |
| 文字 Primary | `#e8ecf8` | `#0f172a` |
| 文字 Secondary | `#9aa3b8` | `#475569` |

> 对比度纪律：浅色模式任何**文字色**（含 Menu 选中、链接、Tag 文字）对比度 ≥ 4.5:1；**浮层壳 = 高不透明玻璃档**（Modal/Drawer 壳面材 `--glass-bg-shell` .92 档 + blur + 玻璃形制件，用户 2026-11-15 B 案、2026-11-16 不透字裁定），**下拉/Popover/Popconfirm 等文字密集小件沿实色 token**（见 §二）。

### 1.3 极光地面（L0 · html 画布层）

地面 = 线性渐变基底 + 三枚大半径径向光斑，fixed 画布层直绘——玻璃要有底衬才透出液态感（对快照轮实证）：

```css
/* index.css：--ground-base 基底 + --ground-glow-a/b/c 光斑（双模式） */
--ground-base: linear-gradient(180deg, #eef2f8, #e2e9f5); /* 深：(180deg,#0a0e1a,#060913) */
--ground-glow-a/b/c: 浅 rgba(59,111,214,.22)/rgba(123,97,255,.18)/rgba(0,180,216,.14)（浅色放量——大视口玻璃透底需地面承色）；
                    深 rgba(0,120,212,.22)/rgba(110,80,255,.18)/rgba(0,212,255,.10)
```

光斑位势：左上蓝 / 右上紫 / 下中青（大半径径向，等效 blur(70px)）。地面层不入浮层；`colorBgLayout: 'transparent'`（token 不得遮画布层）。

### 1.4 液态玻璃材质（L1 面板 / L2 控件 · glass.css）

材质基准 = 用户 2026-11-14 对照快照裁定（v4 快照 + 桌面「参考控件.gif」Apple 玻璃控件 HDR 光泽态）。token 住 `frontend/src/styles/glass.css`。新名三问逐名如下：

- 旧 --glass-bg/--glass-border/--glass-highlight：none found——上代玻璃拟态面/边，材质代际不同不复用。
- --glass-glow-accent：值直取 index.css --glow 发光色。
- press 顶暗影：值直取 neu.css --neu-soft-dark。
- pm-alert（danger-face 行所引徽标）：existing——frontend/src/index.css pm-alert 徽标段（UI批2 在册），本批仅换面值不改名。
- --glass-bg-shell：none found——浮层壳档与玻璃小面（--glass-bg-overlay，Tabs 胶囊面）分家成独立值（用户 2026-11-16 不透字裁定）；定义位 frontend/src/styles/glass.css 1 段；值唯一权威 = 本档 1.4 token 表。

token 面：

| token | 浅 | 深 | 出处 |
|---|---|---|---|
| `--glass-bg-panel` / `--glass-bg-control` | 白玻璃 .32 / .36 | 深空面材 rgba(20,27,45,.36/.4) | 快照「透明度 36–40%」档；浅色微调 .32/.36（大视口密度适配——玻璃透底更深，深色直取快照） |
| `--glass-bg-shell`（浮层壳档） | 白玻璃 .92 | 深空面材 rgba(20,27,45,.92) | 用户 2026-11-16 裁定（毛玻璃不透底字）——B 案浮层壳口径档值；落 glass.css 1 段 |
| `--glass-bg-overlay`（玻璃小面 .8 档） | 白玻璃 .8 | 深空面材 rgba(20,27,45,.8) | Tabs 选中/hover 胶囊面（8.8 用点）；同表格大面 .8 白 token 面先例；落 glass.css 1 段 |
| `--glass-filter` | blur(30px) saturate(1.9) | 同 | 快照直取 |
| `--glass-edge`（发丝亮边） | rgba(255,255,255,.8) | rgba(255,255,255,.24) | 快照白边取 .8 白档——纯白咬深字（对快照轮保留） |
| `--glass-sheen` / `--glass-thick` / `--glass-ring` | 顶光 rgba(255,255,255,.85) / 底缘透光 rgba(255,255,255,.35) / 内亮环 rgba(255,255,255,.35) | 顶光 .30 / 底缘透光 rgba(120,160,255,.10) / 内亮环 .10 | 快照影栈逐值直取——底缘为**透光**（玻璃底缘发亮，非暗影） |
| `--glass-glow` / `--glass-glow-accent` | 白晕 rgba(255,255,255,.55) / accent 档 | 蓝白晕 rgba(130,180,255,.22) / accent 档 | HDR 辉光快照直取（accent 色值直取 index.css --glow；accent 面经作用域换档） |
| `--glass-drop` / `--glass-drop-sm`（外落影） | 面板 0 8px 26px rgba(31,41,71,.12) / 控件 0 2px 6px 同 | 面板 0 10px 30px rgba(0,0,0,.4) / 控件 0 2px 6px rgba(0,0,0,.38) | 快照直取（影栈外落件，--glass-elev-* 引用） |
| `--glass-elev-raised/-control/-inset/-up/-press` | 影栈合成五态 | 同构双模式 | 外落影面板 0 8px 26px / 控件 0 2px 6px 快照直取；inset = 平玻璃（快照 input 无影，仅顶光+亮环）；press 顶暗影 = --neu-soft-dark 压入 |
| `--glass-danger-face` / `--glass-warning-face`（实色面档） | `#e11d48` / `#b45309` | 同值 | danger/warning 实色面（danger 钮 8.10 + pm-alert 徽标）；白字对红面 4.70:1、对警示面 5.02:1——深档原值（#ff4d6d/#fbbf24）作面 3.21/1.67:1 不过线，故双模式同值（用户 2026-11-15 乙裁定：语义红面同构，红底突出危险语义） |
| `--glass-bg-subtle`（微淡染底） | rgba(255,255,255,.03) | 同值 | 健康度淡染底等微淡面收编（原写死值） |

基材类 `.glass`（L1 面板 24px）/ `.pill`（L2 胶囊 999px）——后续单元取用；共享控件映射段号沿用 8.x（迁出后重挂于 frontend/src/styles/glass.css 3 段）。**三件对快照保留**：①亮边 .8 白档（防咬深字）②表格大面用容器 .8 白 token 面（保行文可读，非全透）③环比小字红绿语义色保留（8-1 环比语义）。状态三态（悬停微升/按压微陷/焦点光环）= docs/UI_REORG_PLAN.md 3.2 状态表的玻璃译法。

---

## 二、AntD Token 落地（main.tsx）

```tsx
token: {
  colorPrimary: isDark ? '#00d4ff' : '#0369a1',
  colorInfo:    isDark ? '#00d4ff' : '#0369a1',
  colorSuccess: isDark ? '#22e58a' : '#16a34a',
  colorError:   isDark ? '#ff4d6d' : '#e11d48',
  colorWarning: isDark ? '#fbbf24' : '#b45309',
  borderRadius: 10,
  controlHeight: 28, /* 控件高（v4 样张批准——用户「输入框高度缩减」；main.tsx 同值） */
  colorBgLayout: 'transparent', /* 地面渐变+极光由 index.css --ground-* 画布层直绘——玻璃透出地面（§1.3） */
  colorBgContainer: isDark ? 'rgba(20,27,45,.72)' : 'rgba(255,255,255,.8)',
  colorBorder:      isDark ? 'rgba(120,180,255,.15)' : 'rgba(8,145,178,.15)',
  boxShadowTertiary: '0 0 0 1px rgba(0,212,255,.08), 0 8px 24px rgba(0,0,0,.25)',
},
components: {
  Layout: { headerBg: 'transparent', headerHeight: 56, siderBg: 'transparent' },
  /* 选项卡 hover/selected 浅深归一（用户 2026-11-14 ①）：hover .10 双档 < selected .12 双档——浅色悬停可见度对齐深色，零新增动画 */
  Menu: {
    darkItemBg: 'transparent',
    itemSelectedBg: isDark ? 'rgba(0,212,255,.12)' : 'rgba(3,105,161,.12)',
    itemSelectedColor: isDark ? '#00d4ff' : '#0369a1',
    itemHoverBg: isDark ? 'rgba(0,212,255,.1)' : 'rgba(3,105,161,.1)',
    darkItemHoverBg: 'rgba(0,212,255,.1)',
    activeBarHeight: 3,
  },
  Card: { paddingLG: 20, colorBgContainer: isDark ? 'rgba(20,27,45,.55)' : 'rgba(255,255,255,.75)' },
  Table: { headerBg: isDark ? 'rgba(15,20,36,.65)' : 'rgba(240,246,252,.65)', rowHoverBg: isDark ? 'rgba(0,212,255,.06)' : 'rgba(3,105,161,.05)' },
  Tag: { borderRadiusSM: 4 },
  Segmented: { itemSelectedBg: isDark ? 'rgba(0,212,255,.15)' : 'rgba(3,105,161,.12)' },
  Tabs: { itemSelectedColor: isDark ? '#00d4ff' : '#0369a1' }, /* 8.8 玻璃凸起胶囊的 accent 文字色 */
  // 浮层壳 = 高不透明玻璃档（B 案，用户 2026-11-15；.92 不透底字 2026-11-16）：Modal/Drawer 壳面材 .92 档 --glass-bg-shell（blur/亮边/顶光由 glass.css 8.6 承）；
  // 下拉/Popover/Popconfirm 文字密集小件沿实色 token（Select/Dropdown 面板实色钉值）
  Modal:   { contentBg: isDark ? 'rgba(20,27,45,.8)' : 'rgba(255,255,255,.8)' },
  Drawer:  { colorBgElevated: isDark ? 'rgba(20,27,45,.8)' : 'rgba(255,255,255,.8)' },
  Popover: { colorBgElevated: isDark ? '#141b2d' : '#ffffff' },
  Select:   { colorBgContainer: isDark ? '#141b2d' : '#ffffff', colorBgElevated: isDark ? '#141b2d' : '#ffffff' }, /* 面板实色钉（防随全局漂） */
  Dropdown: { colorBgElevated: isDark ? '#141b2d' : '#ffffff' }, /* 面板实色钉 */
}
```

**新增 `frontend/src/styles/tech.css`**（index.css 之后 import）：承载网格/发光/动画效果类；玻璃材质层住 `frontend/src/styles/glass.css`（token 系/.glass/.pill/8.x 映射，唯一权威见 1.4）。**变量全部进现有 `:root` + `[data-theme='dark']`**，深浅切换机制零改动。

---

## 三、逐页改造清单

| 页面 | 文件 | 关键改动 |
|------|------|----------|
| **导航壳** | `App.tsx` + tech.css | Header 玻璃条（`headerBg: transparent` + CSS `backdrop-filter: blur(16px)` + 底部 1px 青色边 + sticky）；Logo 徽标 = 渐变方块底 + 自绘三柱递升 SVG 内芯（承载面 `App.tsx` 页头 `pm-logo-badge`）+ 发光；品牌字「项目管理中心」（用户 2026-11-14 ②+品牌统一裁定；字族同登录页标题档 = 'PingFang SC','HarmonyOS Sans SC','Microsoft YaHei UI','Segoe UI',system-ui，直取 `neu.css` 登录标题字族，系统栈零新增依赖）；Menu 选中渐变下划线（activeBarHeight 3 + CSS）+ hover/selected 浅深归一（§二 Menu token）；Avatar 加青色 glow |
| **看板** | `DashboardPage.tsx` | 6 卡语义圆点（7px）+ 语义色数字（26px/650 + tabular-nums）+ 环比小字（红绿语义）；「今日聚焦」玻璃面板；卡片 hover `translateY(-1px)` + 增辉 |
| **项目列表** | `ProjectListPage.tsx` | 表格 headerBg 玻璃化、行 hover 青色光晕；状态 Tag 加 `box-shadow: 0 0 6px currentColor` 微光；筛选栏包玻璃容器 |
| **详情+甘特** | `ProjectDetailPage.tsx` + `gantt.css` | 甘特只改变量值：`--gantt-active` 系改青蓝渐变（`linear-gradient(180deg,#00d4ff,#0090c8)`）；关键路径红框发光加强 + 2s 呼吸动画；今日线加 glow；依赖连线青色 |
| **资源负载** | `ResourcePage.tsx` + `resourceView.css` | 复用变量；冲突 ⚠ 黄框发光动画 |
| **周报** | （无页面） | 2026-08-26 已整体移除（用户决定，待重新规划；`.report-markdown` 样式随页面删除，`phase.updated_at` 列保留） |
| **登录页** | `LoginPage.tsx` | **已由 docs/UI_REORG_PLAN.md 3.1 取代（2026-11-13 登录页旗舰重做）**：终态 = 恒深色星空壁纸 + 150 星恒动 Canvas（frontend/src/components/LoginStarfield.tsx）+ 拟态底栏一行；动效整体恒动豁免降级 |
| **我的任务** | `MyTasksPage.tsx` | 统计卡渐变数字；Progress 渐变 `{from:'#00d4ff', to:'#7b61ff'}` |
| **用户管理/审核** | 继承 token | 零改动自动生效 |

---

## 四、动效与性能红线

| 场景 | 实现 |
|------|------|
| 全局过渡 | 换肤过渡属性集以 docs/UI_REORG_PLAN.md 3.3「换肤过渡集」为准（0.25s；不全量 transition） |
| 卡片 hover | `translateY(-1px)` + 发光阴影 |
| 关键路径/冲突 | `@keyframes pulse` 呼吸（2s / 1.4s） |
| 加载 | Spin 换电青；首屏用 `Skeleton` |
| 页面切换 | Suspense fallback 渐变进度条 |
| 降级 | `@media (prefers-reduced-motion: reduce)` 关闭全部动画（**登录页除外**——2026-11-13 裁定：登录页动效整体恒动豁免降级，口径见 docs/UI_REORG_PLAN.md 3.3） |

**性能红线**：`backdrop-filter` 随液态玻璃面材用于 Header/面板/控件/登录卡；滚动容器卡（甘特/表格大滚动区）一律豁免——半透明底+高光线模拟（实测卡顿）；accent 实色渐变面摘除采样；表格行/列表项保持实色半透明。

---

## 五、实施批次

| 批次 | 内容 | 预计 |
|------|------|------|
| **P0** | index.css 变量换色 + main.tsx token + tech.css 网格/玻璃/发光 | 半天 |
| **P1** | 导航壳玻璃 + 看板 6 卡 + gantt.css 换肤与脉冲 | 1 天 |
| **P2** | 列表表格/Tag/筛选栏 + 登录页动效 + 资源负载 | 1 天 |
| **P3** | 我的任务 + 空状态/对比度微调 | 0.5 天 |

---

## 六、验收标准

- [ ] 深浅两模式全站走查：极光地面/玻璃质感/辉光点缀/渐变 accent 可见，无刺眼或不可读区域
- [ ] 甘特图：状态条青蓝渐变、关键路径红框呼吸、冲突黄框呼吸、今日线发光、连线青色（深浅均清晰）
- [ ] 看板 6 卡语义圆点+语义色数字；列表行 hover 青色光晕；登录页星空恒动（终态口径见 docs/UI_REORG_PLAN.md 3.1）
- [ ] `npm run build`（tsc -b）通过；`prefers-reduced-motion` 降级生效（登录页恒动豁免除外）
- [ ] 浅色模式文字对比度 ≥ 4.5:1（电青/紫不用作浅色文字；Menu 选中/链接/Tag 文字用 `#0369a1` 系）
- [ ] 主题切换/刷新记忆/无闪白（FOUC 脚本保留）无回归

### 测试用例（对应方法论的正常/边界/错误）

| 场景 | 输入 | 预期输出 |
|------|------|----------|
| 正常：深浅切换持久化 | 切深色 → 刷新页面 | 保持深色，无闪白 |
| 边界：首次访问跟随系统 | 清除 `pm-theme`，系统为深色 | 默认深色；切浅色后刷新 → 保持浅色 |
| 错误：localStorage 异常 | 禁用/清空 localStorage 后加载 | 默认浅色，无 JS 报错，FOUC 脚本容错 |
| 正常：甘特换肤 | 深色下打开详情页甘特 | 状态条渐变/关键路径呼吸/连线青色清晰可见 |
| 构建 | `npm run build` | tsc -b 零错误 |

---

## 七、涉及文件

```
frontend/src/main.tsx                    token 双套重写
frontend/src/index.css                   :root / [data-theme] 色值替换 + 新增变量
frontend/src/styles/tech.css（新）       网格/发光/动画效果类
frontend/src/styles/glass.css（新）      玻璃材质层（token 系/.glass/.pill/8.x 映射）
frontend/src/App.tsx                     导航壳玻璃化
frontend/src/pages/DashboardPage.tsx     看板 6 卡
frontend/src/pages/ProjectListPage.tsx   列表表格/筛选栏
frontend/src/pages/ProjectDetailPage.tsx 详情面板微调
frontend/src/components/Gantt/gantt.css  甘特变量换肤 + 动画
frontend/src/components/Resource/resourceView.css 资源负载
frontend/src/pages/LoginPage.tsx         登录页动效（终态形制见 docs/UI_REORG_PLAN.md 3.1）
frontend/src/pages/MyTasksPage.tsx       我的任务
```
（不涉及后端/数据库；不新增依赖）

---

> 评审通过后由 eng-coder（kimi:kimi-k3）按 P0→P3 实施。
> 🦞 | 2026-08-26

---

## 用户裁定注记（2026-11-13 · 批 1 随批落档）

1. **控件材质 = 液态玻璃**——控件表面材质层约定（D12 终态）：材质基底 = 液态玻璃（HDR 光泽态），拟态三态（悬停微升/按压微陷/焦点光环）保留为状态语言；形制与交互仍以 macOS 参照。本文档「设计语言」四件套中，发光/渐变降为点缀；照片背景（登录页）走半透明轻版面板 + 柔双影 + 微 blur，不依赖底色。原因：发光/渐变作大面积材质在浅色模式下对比度与质感均失分；玻璃面材靠地面承色才透出液态感。权威分界：材质值/面材/token 系唯一权威 = 本档 1.4；按钮三态/输入凹陷态与状态表唯一权威 = docs/UI_REORG_PLAN.md 3.2。
2. **主题切换过渡纪律**——用户 2026-11-13 裁定「浅色/深色主题切换要有过渡效果、不能生硬」。换肤过渡属性集唯一权威 = docs/UI_REORG_PLAN.md 3.3「换肤过渡集」（成员表与 View Transitions/降级条款均以该处为准，本文档不复述）。壁纸不随主题切换（登录页恒深色、换图机制不启用——口径见 docs/UI_REORG_PLAN.md 3.1）。原因：换肤瞬切在深浅大反差下刺眼，0.25s 淡变与既有动效节奏一致，color 不在过渡期会让文字先于表面跳变。

