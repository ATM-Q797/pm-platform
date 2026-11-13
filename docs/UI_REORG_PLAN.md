# UI 优化方案 v4（拟态控件 · macOS 交互 · 深浅双模式）

> 主题归属：本文档是「UI 交互与信息架构」主题的唯一权威文档——管控件形制与材质、交互、页面结构、入口、词表、状态呈现。
> 三层关系：**形制与交互 = macOS 参照；表面材质 = 拟态（Neumorphism，用户 2026-11-13 给样裁定）；色板 = 深空双模式**。视觉机制基线仍以 docs/UI_TECH_STYLE.md 为唯一权威，其设计语言中发光/渐变降为点缀、玻璃拟态退守特定场景、换肤过渡属性集扩写（见 3.3）——三项均属用户裁定增补，批 1 随批在该文档落注记；过渡纪律以本档 3.3 为准。
> 状态：v4 待审阅（2026-11-13）。
> 最近先例：frontend/src/pages/LoginPage.tsx（改造前登录页——标题文本/登录逻辑/校验消息沿用）· frontend/src/styles/tech.css（双 token/过渡节奏现状）· docs/UI_TECH_STYLE.md（双套 token/FOUC/降级纪律）——对齐：主题机制与降级纪律零改、登录逻辑零动；偏离：控件材质凸起式拟态、登录形制去卡片（用户 2026-11-13 裁定与给样）。
> 查证记录：公开来源文档未查证——形制取用户原话、材质取用户给样，分档/srcset 选档/cover 为通行常识；如实记「未查证」。

## 〇、用户方向（2026-11-12 / 2026-11-13）

- 界面控件优化 + 交互优化，参照 macOS 的 UI 与交互。
- 登录页做成 macOS 登录屏式：一张大高清图 + 登录控件浮于壁纸（去卡片、底栏一行，2026-11-13 定）；登录界面效果做**缩放动态**。
- 样式与 UI 统一化；进入后的界面同样优化。
- 方案须含**浅色与深色双模式预案**；壁纸深浅两版成对（主题 = 星空苍穹），切换保持一致性。
- 壁纸由用户在生图平台生成（本方案交付生图提示词）。
- 分辨率随用户屏幕而异——按业界网页通行做法适配（见 3.1）。
- **控件表面材质参考用户所给 neumorphism 按钮样例（neu-button），结合实际情况适配（2026-11-13）**。
- **浅色/深色主题切换要有过渡效果、不能生硬（2026-11-13）**。
- **登录页形制再调（2026-11-13，参照 macOS 锁屏图）**：标题改真毛玻璃字面（渐变半透明字，无底板）；输入框改平玻璃态（半透明 + blur + 微光边），按钮保留凸起拟态。
- **登录页形制再调二（2026-11-13）**：顶部**不显示时间与日期**，只留「项目管理中心」（顶部居中、字号加大加粗）；两个输入框高度压至只比字体略大、圆角更圆润；底栏整行下移、控件间距加宽。
- **登录页借鉴星空登录页教程（2026-11-13，用户给 CSDN 链接）**：采纳动态星空层/按钮涟漪/密码显隐眼三件；注册 Tab/记住我/忘记密码不采纳（系统无注册流、无重置流、token 机制）。
- 词表、信息架构、数据状态三线：按本方案既有建议执行（D1-D8 已裁定）。

## 一、现状地图

导航壳（frontend/src/App.tsx）：顶部玻璃条 Header（Logo + 水平菜单按角色过滤 + 主题开关 + 通知铃 + 用户下拉）。

| 页面 | 路由 | 角色可见 | 备注 |
|---|---|---|---|
| 登录 | /login | 全部 | 按角色跳默认页（本方案旗舰改造对象） |
| 看板 | / | admin/viewer 默认页 | manager/engineer 重定向项目列表 |
| 项目列表 | /projects | admin/manager/engineer/viewer | viewer 无操作列、无导入导出 |
| 项目详情 | /projects/:id | 全部登录（专项另限） | 甘特 + 趋势 + 变更时间线 |
| 资源负载 | /resources | admin/manager | 三视图（热力图/甘特/效率分析） |
| 团队效率 | 内嵌资源负载第三 Tab | admin/manager | 去壳后维持 Tab（已裁定） |
| 专项项目 | /special-projects | admin/manager | 卡片网格 |
| 审核中心 | /admin-center | admin | 内嵌用户管理 + 审核中心（命名统一后） |
| 信息填报 | /report | admin/manager/engineer/reporter | reporter 默认页 |
| 我的任务 | /my-tasks | manager/engineer | 菜单露出（已裁定） |
| 过程审计 | P3 新页 | admin/manager/engineer | 实施毕（评审 pass），控件随本方案受控 |

事实坐标来自 2026-11-12 全站盘点；实施批逐项对码复核。

## 二、问题清单（30 项归 5 域）

B 域（入口与动作形态 5 项）与 D 域（组件形态规范缺失 8 项）共 13 项 = 主线一直接输入；A/C/E 三域归主线二。明细坐标见 2026-11-12 全站盘点记录（台账 #14 evidence）。

| 域 | 条数 | 归属 |
|---|---|---|
| A 信息架构与导航 | 5 | 主线二（已裁定项 + 随三期） |
| B 入口与动作形态 | 5 | 主线一 |
| C 词表与口径 | 7 | 主线二（一期快赢） |
| D 组件形态规范缺失 | 8 | 主线一 |
| E 数据状态与错误处理 | 5 | 主线二（错误态分离随主线一反馈细则） |

## 三、主线一：拟态控件与交互优化

### 3.1 登录页（旗舰，第一批）

形制 = macOS 登录屏形制（用户 2026-11-13 裁定：**去卡片**，控件直接浮于壁纸）：

- **登录页恒深色 + 星空恒动（2026-11-13 裁定）**：登录页只挂深色版（换肤只在进入平台后，App 头部开关不受影响）；星空恒动、Ken Burns 恒动（特例豁免 reduced-motion 降级，理由已入批档）；流星已移除。
- 全屏壁纸大图（深色版，恒定）+ 遮罩层（深色暗纱，文字对比度 ≥ 4.5:1）。
- **动态星空层**（2026-11-13 借鉴 CSDN 星空登录页教程）：Canvas 星点随机闪烁（150 颗），叠在壁纸之上；`pointer-events: none` 不拦鼠标；**恒动豁免降级**（主体视觉特例）。
- 顶部居中只留「项目管理中心」**毛玻璃字体**标题：圆润字族、**加大加粗**（clamp 32-48px、font-weight 700、宽字距）；毛玻璃质感 = 渐变半透明字面（background-clip:text）+ 光晕 + 投影，**无容器底板**；**不显示时间与日期**。
- **无登录卡**：登录行直接浮于壁纸、靠底部一行横排，从左到右 = 用户名输入框 → 密码输入框（右侧**显隐眼**切明/密文，不参与提交）→ 登录按钮（**圆形向右箭头**，置于密码框右侧）。**主题切换钮不在登录页**——换肤只在进入平台后（App 头部开关）。
- 输入框做小做窄（容纳约 10 字符宽）+ **平玻璃态**（半透明 + backdrop blur + 微光边 + 无内影）+ **高度压至只比字体略大**（高 34px、字号 14px）+ **圆角更圆润**（14px）；按钮圆形与输入框同高（34px）、走**凸起拟态**（3.2 拟态规范，保留）；**底栏整行下移至近底**（行底距 5vh、底部居中）+ **控件间距加宽**（32px）。
- 裁剪原则：无关机/重启钮、无系统时钟栏、无多用户切换——任务纯粹是登录。

**缩放动态（Ken Burns · 恒动）**：

- 壁纸层慢速缩放：scale 1.00 ↔ 1.10 往复，周期 24s，缓动 ease-in-out；只用 transform（GPU 合成，零重排）。
- 图层基础尺寸放大 ≥112%（scale 最小值仍盖满视口，不露边）。
- **恒动豁免**：不设 reduced-motion 降级（与星空同批裁定——动效即登录页主体视觉；Ken Burns 不再列入降级清单）。

**深浅双壁纸（一致性要求）**：

- 深色版 = 深空星穹夜景；浅色版 = 晨曦/高调星穹。两版**同构图同星点布局**——主题切换只换光线与色调，不跳构图。
- 随 data-theme 切换：`<picture>` 双 source 或 CSS 变量换图，切换过渡 0.25s（与主题切换同节奏）。
- 壁纸素材由用户在生图平台生成（星空苍穹主题），生图提示词见「七」。

**分辨率适配（业界通行做法）**：

| 环节 | 做法 |
|---|---|
| 生成端 | 单张 16:9、平台最高分辨率输出（≥3840×2160，理想 5K/8K）；深浅两版同 seed 同构图 |
| 分发端 | 自缩放出多档：1920 / 2560 / 3840 宽（可选 5120）；格式 AVIF/WebP 优先 + JPEG 兜底 |
| 选档端 | `<img srcset+sizes>` 或 image-set()/媒体查询；按视口宽度选档，devicePixelRatio 2 的屏自动上一档（Retina 常规做法） |
| 呈现端 | `background-size: cover` + 焦点锚定（center 45% 附近）——任意屏宽/超宽/竖屏均裁切不拉伸；登录控件行叠放区（画面下中部）生成时即留低细节区 |
| 兜底 | 垫底渐变色与主题色一致（图未达/加载失败不露白；复现=阻断图片请求见垫底渐变；「图未达」=壁纸由用户生成未回的现状）；遮罩层始终压对比度 |
| 动效层 | 超尺寸图层（106%+）上做 scale 动画，避免缩放露边 |

**保留不动**：FOUC 防闪白脚本、主题双套机制（light/dark 双 token 板——登录页除外，登录页恒深色）、按角色跳默认页、首次强制改密流。
**定样**：登录页底栏控件即 3.2 拟态规范的第一次全量落地（输入凹陷/圆形按钮三态/焦点光环/间距节奏）。

**批 1 验收清单**：

- 遮罩对比度（底栏文字/标题 ≥ 4.5:1）· 图层 ≥112% 不露边
- Ken Burns 24s 往复 scale 1.00↔1.10（恒动豁免降级）· 星空 150 星恒动闪烁（恒动豁免）
- 涟漪点击点扩散且 0.6s 消散 · 显隐眼切明/密文不参与提交
- 空输入/登录失败：输入框摇头、**无红字**；失败时密码框摇头 + 错误浮字按钮右侧渐现渐隐（不弹顶部）
- 换肤（平台内）0.25s 无瞬切 · 登录逻辑零回归（提交/loading/按角色跳转与改造前一致）
- 实跑检查 = tsc -b + vite build + 双主题实拍比对（纯视觉层、业务结果未变，增量结论见「集成测试设计」）

**错误/空字段反馈落点**：

- 空输入/输入错误：**输入框摇头示意**（左右抖动，macOS 同款），不显示文字提示
- 登录失败：密码框摇头 + **错误浮字**按钮右侧渐现渐隐（毛玻璃浮牌、3.5s 自动消散），不弹顶部消息
- loading = 箭头钮转圈 + 禁用（防双提交）；点击时箭头从左滑入回弹（0.45s，cubic-bezier(0.34, 1.56, 0.64, 1)）

**新名三问**（住哪 · 原文名 · 归谁）：

| 新名 | 三问作答 |
|---|---|
| 标题「项目管理中心」文本 + 毛玻璃形制 | 文本：existing（改造前登录页标题即此文本）；毛玻璃形制：none found（新视觉处理，归 frontend/src/styles/neu.css） |
| 登录行深浅切换按钮 | existing but unusable：主题开关在 App.tsx Header（登录后壳渲染），登录页无壳 ⇒ 页面内自带切换钮，复用 useTheme().toggle（机制零新） |
| .neu-button/.neu-input/.neu-icon-btn 与 --neu-* token | none found（拟态层新命名，单归 frontend/src/styles/neu.css） |

### 3.2 控件材质：拟态（Neumorphism）· 双模式同形制

基准样 = 用户 2026-11-13 给样（**凸起式**：145deg 渐变面 + 外双影大软对），按实际情况六条适配后落地：

1. **双模式 token 化**：所有影色/渐变面色写死值改 CSS 变量，light/dark 各一套（样例 #f0f0f0/#cacaca/#a8a8a8/#ffffff 是浅色单态）。
2. **中性灰微冷调**：贴深空色系（浅色面微冷灰、深色面深空冷灰），不与星空主题打架。
3. **凸起为基态**：基态外双影凸起 + 渐变面；hover 增凸（影对放大）；active 压入（翻转内双影 + translateY(1px)）——拟态自然三态。
4. **过渡收口**：`transition: all` 禁用（性能反模式）；组件状态过渡（hover/active）只挂 box-shadow/transform，换肤淡变由 3.3 换肤过渡集承担——两组并存、职责分开。
5. **焦点可访问性**：样例 :focus 去 outline 换影调，对键盘用户不够醒目——改 :focus-visible 主题色光环 2px（影调变化保留）。
6. **对比度纪律**：文字色随 token 走，浅色 ≥ 4.5:1（UI_TECH_STYLE 既有纪律）。

Token 与按钮基准实现：

```css
/* 拟态 token（双模式；渐变面 + 外双影——用户 11-13 二次给样） */
:root, [data-theme='light'] {
  --neu-grad-a: #f0f0f0;
  --neu-grad-b: #cacaca;
  --neu-shadow-dark: #a8a8a8;
  --neu-shadow-light: #ffffff;
  --neu-text: #3d434d;          /* 对比度 ≥ 4.5:1 */
}
[data-theme='dark'] {
  --neu-grad-a: #2e3339;        /* 深空冷灰 */
  --neu-grad-b: #21252b;
  --neu-shadow-dark: #12151a;
  --neu-shadow-light: #3a4048;
  --neu-text: #d7dce4;
}

/* 按钮：胶囊凸起 + 三态 + 键盘光环 */
.neu-button {
  border-radius: 49px;
  background: linear-gradient(145deg, var(--neu-grad-a), var(--neu-grad-b));
  box-shadow: 12px 12px 23px var(--neu-shadow-dark),
             -12px -12px 23px var(--neu-shadow-light);
  color: var(--neu-text);
  border: none;
  transition: box-shadow 0.25s ease-in-out, transform 0.25s ease-in-out,
    background 0.25s ease-in-out, color 0.25s ease-in-out;
}
.neu-button:hover {            /* 增凸：影对放大 */
  box-shadow: 15px 15px 28px var(--neu-shadow-dark),
             -15px -15px 28px var(--neu-shadow-light);
}
.neu-button:active {           /* 压入：翻转内双影 */
  box-shadow: inset 6px 6px 12px var(--neu-shadow-dark),
              inset -6px -6px 12px var(--neu-shadow-light);
  transform: translateY(1px);
}
.neu-button:focus-visible {    /* 键盘光环不丢 */
  outline: 2px solid var(--accent, #00d4ff);
  outline-offset: 2px;
}
```

**状态表**：

| 状态 | 形态 |
|---|---|
| 基态 | 凸起：145deg 渐变面 + 外双影 12px/23px 对 |
| 悬停 | 增凸：影对放大（15px/28px） |
| 按压 | 压入：翻转内双影 6px/12px + translateY(1px) |
| 焦点 | :focus-visible 主题色光环 2px + 影调变化 |
| 禁用 | 影调压平 + opacity 0.55 |

**适用面**：

- 按钮（胶囊 49px）、Segmented、统计卡、抽屉/弹窗表面（实色上做拟态——与「浮层用实色 token」纪律相容）。
- 输入框 = **凹陷态**：反向渐变面（145deg 反序）+ 内双影 6px/12px + 圆角 12px；聚焦时外光环 + 内影收窄——用于全站表单（批 2-3）；登录页输入框走 3.1 的平玻璃态（照片背景上的变体）。
- 按钮胶囊 49px（用户给样值）优先于 macOS 8px；输入框/卡片用 12-16px 中圆角。

**不适用面**：

- 照片背景（登录页壁纸上）：拟态依赖底面色，改**拟态轻版**——半透明面板 + 柔双影 + 微 blur，不依赖底色。
- 浮层内文字对比区照旧实色 token（docs/UI_TECH_STYLE.md「浮层（Modal/Drawer/Popover）用实色 token」）。

### 3.3 交互细则

- 动效节奏与降级纪律沿用 UI_TECH_STYLE（0.25s + prefers-reduced-motion 降级）；过渡属性集以「换肤过渡集」为准（见下）。
- 微交互：按钮按压下沉（拟态三态自带）、卡片悬停升起 1px、弹窗开合 0.2s 滑入、Segmented 切换滑块过渡。
- 按钮涟漪（登录页）：点击点扩散波纹、0.6s 消散自动清理；**登录页动效整体恒动**（2026-11-13 裁定——星空/壁纸缩放/涟漪/摇头/浮字/箭头均不设 reduced-motion 降级，用户环境系统级减动效不吞登录页动效；平台内其余动效仍守降级纪律）。
- 登录壁纸缩放动态（见 3.1）。
- **主题切换过渡（2026-11-13 裁定：不能生硬）——换肤过渡集以此为准**：
  - 换肤过渡集：background-color / background（渐变面同构换色）/ border-color / box-shadow / color 各 0.25s——点切换键后各表面/文字/影调（含拟态双影）同步淡变，无瞬切；组件状态过渡（hover/active）另由 3.2 的 box-shadow/transform 承担，两组并存。
  - 增强：支持 View Transitions API 的浏览器以 document.startViewTransition 包住换肤做整页交叉淡变；不支持自动回落基线。
  - 壁纸换图与 token 切换同节奏 0.25s（3.1 双壁纸淡变，与主题同步）。
  - 图表（ECharts）随主题重绘时配色淡入 0.25s，不瞬切。
  - prefers-reduced-motion → 直接切换（降级纪律优先于过渡）。
- 键盘：Esc 关弹窗、Enter 提交表单、Tab 焦点序可见（:focus-visible 光环保证）。
- 反馈：操作成功消息提示、加载失败显式错误态 + 重试（问题 #25/#26 一并治）。
- 甘特拖拽/手柄/右键删线交互不改（已定型）。

### 3.4 进入后的界面范围

- 全站按 3.2 拟态规范替换：看板/列表/详情/填报/审核/资源/专项/我的任务/过程审计；**深浅两模式逐页对表验收**，含切换过渡验收（点切换键 0.25s 平滑淡变、无闪烁无跳变）。
- 导航结构不动（IA 已裁定）；macOS 式侧边栏导航属另一次结构改造，需要时另立批再议。

## 四、主线二：其余三线（已裁定按建议执行）

- 词表五套收敛单源（问题 #11-#17）：类目以列表页四选项为准、状态色全局模块含「延期」、市场 MARKET_OPTION_ITEMS、审批动词统一「通过/拒绝」、星标 tooltip 去「置顶」。
- 信息架构（已裁定）：「我的任务」菜单露出（依据 docs/PHASE5_PLAN.md「engineer → 看板 / 项目（只读）/ 我的任务」）；不建「我的项目」独立页（文档同步改注）；双入口保留、形态统一；团队效率去页面壳维持 Tab；菜单统一「审核中心」。
- 数据状态（问题 #27-#29）：角色状态单源下发、api 补 favorites 封装、错误对象统一。
- Skeleton 落地看板/详情/列表首屏（约定原文 docs/UI_TECH_STYLE.md「首屏用 `Skeleton`」，已裁定落地）。

## 五、已定决策（2026-11-12 / 11-13）

| # | 决策点 | 裁定 |
|---|---|---|
| D1 | 「我的任务」孤儿页 | A 菜单露出（按规划） |
| D2 | manager「我的项目」 | B 不建独立页，语义并入列表视图（文档同步改注） |
| D3 | 触发采集/数据刷新双入口 | A 保留双入口统一形态 |
| D4 | 导出入口（看板+列表） | A 保留双入口同形态 |
| D5 | 团队效率归位 | A 去页面壳维持 Tab |
| D6 | 「审核管理中心」命名 | A 统一「审核中心」 |
| D7 | P3 过程审计页导航归组 | 随主线二信息架构批处理 |
| D8 | 首屏 Skeleton | A 看板/详情/列表首屏落地 |
| D9 | 主题气质档位 | 已定（11-13）：**深浅双模式预案**——深色 = 深空星穹、浅色 = 晨曦星穹；沿用既有双套 token/FOUC 机制 |
| D10 | 登录页壁纸素材 | 已定（11-13）：**B 用户自生成**（星空苍穹，深浅同构图成对）——本方案交付生图提示词（见「七」）+ 多档分辨率适配（见 3.1） |
| D11 | 控件表面材质 | 已定（11-13）：**拟态 Neumorphism**（用户给样 neu-button），六条适配落地（见 3.2）——形制/交互仍 macOS 参照；UI_TECH_STYLE 发光/渐变降为点缀、玻璃退守轻版场景，该裁定注记随批 1 落该文档 |

## 六、排期（重排）

- 批 1（旗舰）：登录页 macOS 化——缩放动态 + 深浅双壁纸接入 + 分辨率多档 + **拟态规范首落地**（含 UI_TECH_STYLE 裁定注记）。
- 批 1 受影响文件（均不跨级——函数级 300/500 与文件级 500/800 拆审线未触，无需拆分）：
  - frontend/src/pages/LoginPage.tsx（视觉层重写）· frontend/src/styles/neu.css（新）· frontend/src/components/LoginStarfield.tsx（新，动态星空层）
  - frontend/src/theme.tsx（仅换肤函数）· frontend/src/styles/tech.css（过渡行）· docs/UI_TECH_STYLE.md（裁定注记）
  - frontend/public/wallpapers/（新资产 14 档）· frontend/src/main.tsx（+1 样式 import）· scripts/gen_wallpapers.py（新，构建期）
- 批 2-3：拟态控件全站替换（3.2 表逐行，共享组件 + 替换；错误态分离在此批；深浅两态对表）。
- 批 4：交互细则（3.3——微交互/键盘/反馈）。
- 批 5：主线二（词表快赢 + IA 裁定项 + 数据状态收敛）。
- 每批批档走「设计 → 评审 → 您批 → 实施」；台账 #14 为主行。
- 与 P3 衔接：过程审计页控件随批 2-3 统一替换。

## 七、生图提示词（交付用户，供生图平台使用）

使用要领：

- 同一构图出两版：先出深色版，记录 seed；浅色版用同一 seed / 垫图重绘，仅替换光线与色调描述（保证切换不跳构图）。
- 比例 16:9；以平台最高分辨率输出（≥3840×2160），回来由前端分档缩放（1920/2560/3840）。
- 构图硬要求：银河星带在画面上三分之一；**画面下中部留平整低细节区**（登录控件行叠放处）；无文字、无水印、无人物、无建筑。

深色版（English）：

```text
Ultra-wide cinematic wallpaper, starry cosmos sky over a dark horizon: deep indigo-to-black gradient sky, luminous Milky Way band arcing across the upper third, fine dense starfield, subtle teal and violet nebula glow, soft cosmic dust, realistic astrophotography, minimal calm composition with a smooth uncluttered dark area across the lower center for UI overlay, no text, no watermark, no people, no buildings, 16:9, 4K high resolution, dark theme
```

浅色版（English）：

```text
Ultra-wide cinematic wallpaper, the same starry cosmos sky in dawn light: pale blue-to-warm-white gradient sky, Milky Way band fading into bright morning haze, stars softly visible through a luminous high-key atmosphere, pastel nebula tones in pearl blue and soft rose, airy and serene, same composition and star layout as the dark version, clean uncluttered light area across the lower center for UI overlay, no text, no watermark, no people, no buildings, 16:9, 4K high resolution, light theme
```

深色版（中文）：

```text
星空苍穹主题超宽壁纸：深空夜景，靛蓝至黑的渐变夜空，银河星带横贯画面上三分之一，细密星点，青紫色星云微光，柔和宇宙尘埃，写实天文摄影质感；构图极简沉静，画面下中部留出平整低细节暗区（供界面叠加）；无文字、无水印、无人物、无建筑；16:9，4K 高分辨率，深色主题版
```

浅色版（中文）：

```text
与深色版同一构图、同一星点布局的晨光版：淡蓝至暖白渐变天空，银河融进明亮晨霭，高调通透大气中星点柔现，珠光蓝与浅玫瑰色星云；画面下中部留出平整低细节亮区；无文字、无水印、无人物、无建筑；16:9，4K 高分辨率，浅色主题版
```

图片回来后的验收点：两版并排比对构图是否一致（星带位置/地平线/留白区）；下中部控件区无高亮星团干扰；浅色版底栏文字在半透明面板上的可读性；放大 100% 无明显压缩伪影。

## 八、集成测试设计（RTM 增量）

起点 = test/RTM.md。本方案为视觉/交互层改造，业务可观察结果一律不改——登录认证结果 / 按角色跳转 / 首次强制改密 / 审批 / 导出等均未触碰（批 1 实证：handleSubmit 逐字未动、校验消息原文保留、跳转调用零改动）。

| 维度 | 结论 |
|---|---|
| 破坏行 | 无——RT-5 / RT-6 / RT-12 等以「登录 →」为入口的行为行断言业务结果（403 封锁 / 重定向 / 菜单守卫），登录形制改造不改这些结果，实跑读数见批档 |
| 冗余行 | 无 |
| 缺行 | 无——纯视觉形制不产生新业务可观察结果，不需新增行 |
| 交互—业务结果—入口—需求 | 登录行提交 → 认证结果与角色跳转 → /login 入口 → 既有行 RT-5/RT-6/RT-12（视觉形制变化不改该四元组） |

批 2-5 若出现业务可观察变化（如词表口径影响状态呈现），先在 test/RTM.md 定行号再写用例，增量按上表口径逐批判。