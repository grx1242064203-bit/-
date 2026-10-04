# Offer搭子 · UI 设计系统（Crextio Glass 玻璃拟态）

> 版本：v2.0 | 更新日期：2026-10-04
> 设计语言：iPhone 式透明感 / 现代毛玻璃拟态（Glassmorphism）
> 参考基准：Crextio HR Management Dashboard 系列设计稿

---

## 一、设计哲学

Offer搭子的视觉系统围绕三个核心原则：

1. **透明感（Transparency）**：所有承载内容的面板均为半透明白色玻璃，透出底层暖色渐变背景，营造轻盈、通透的 iPhone 式观感，拒绝厚重的实心白卡片。
2. **温暖亲切（Warm & Friendly）**：以暖奶油黄为主色，搭配奶油→暖金的渐变背景，区别于冷蓝 SaaS 的工具感，贴近学生用户的情感预期。
3. **现代克制（Modern & Restrained）**：大圆角、药丸形控件、柔和暖阴影、充足留白，信息层级靠透明度与间距而非粗边框区分。

---

## 二、色彩体系

### 2.1 主色（暖奶油黄）

| Token | 值 | 用途 |
|-------|-----|------|
| `--color-primary` | `#FFD23F` | 主按钮、选中态、高亮、强调标签 |
| `--color-primary-dark` | `#F5B800` | 按钮 hover、深色强调文字 |
| `--color-primary-light` | `#FFF4C2` | 浅黄底、渐变终点 |
| `--color-primary-soft` | `rgba(255, 210, 63, 0.18)` | 透明黄底（标签、激活态覆盖） |

### 2.2 深色（导航激活）

| Token | 值 | 用途 |
|-------|-----|------|
| `--color-ink` | `#1F1F1F` | 导航激活药丸背景、深色卡片 |
| `--color-ink-soft` | `#3D3D3D` | 深色次级文字 |

### 2.3 语义色

| Token | 值 | 用途 |
|-------|-----|------|
| `--color-success` | `#34D399` | 已录用、成功态 |
| `--color-success-soft` | `rgba(52,211,153,0.16)` | 成功底 |
| `--color-warning` | `#FBBF24` | 面试中、待处理 |
| `--color-danger` | `#F87171` | 已拒绝、错误 |
| `--color-danger-soft` | `rgba(248,113,113,0.16)` | 危险底 |

### 2.4 文本色阶（暖灰）

| Token | 值 | 用途 |
|-------|-----|------|
| `--color-text` | `#1F1F1F` | 主标题、正文 |
| `--color-text-muted` | `#7A7A7A` | 次级说明、标签 |
| `--color-text-faint` | `#B0B0B0` | 占位符、弱提示 |

---

## 三、玻璃拟态核心令牌（Glassmorphism）

这是本系统最核心的视觉特征。所有卡片、表格、面板必须使用以下令牌，禁止使用实心白底。

| Token | 值 | 说明 |
|-------|-----|------|
| `--glass-bg` | `rgba(255,255,255,0.55)` | 标准玻璃底（表格、卡片） |
| `--glass-bg-strong` | `rgba(255,255,255,0.72)` | 强玻璃底（顶栏、需高对比区域） |
| `--glass-bg-soft` | `rgba(255,255,255,0.35)` | 弱玻璃底（内嵌容器、次要卡片） |
| `--glass-border` | `rgba(255,255,255,0.65)` | 玻璃边框 |
| `--glass-border-soft` | `rgba(255,255,255,0.4)` | 弱玻璃边框 |
| `--glass-blur` | `24px` | 背景模糊半径 |
| `--glass-saturate` | `180%` | 背景饱和度增强 |

### 玻璃组件类

```css
.glass {
  background: rgba(255,255,255,0.55);
  backdrop-filter: blur(24px) saturate(180%);
  -webkit-backdrop-filter: blur(24px) saturate(180%);
  border: 1px solid rgba(255,255,255,0.65);
}
.glass-strong { background: rgba(255,255,255,0.72); /* blur 32px */ }
.glass-soft   { background: rgba(255,255,255,0.35); }
```

**使用规则**：
- 主内容卡片（表格、统计卡、看板列）→ `.glass`
- 顶部导航栏、需更高对比度的容器 → `.glass-strong`
- 内嵌子卡片、次要面板 → `.glass-soft`
- 输入框背景 → `bg-white/40 backdrop-blur-sm`（保持玻璃感但确保可读）

---

## 四、背景与 App 窗口

### 4.1 页面底色
`html, body { background-color: #E8E4DC }` — 中性暖灰，衬托 app 窗口。

### 4.2 App 窗口（核心容器）

| Token | 值 |
|-------|-----|
| `--app-bg-gradient` | `linear-gradient(135deg, #FDFBF3 0%, #FAF4E0 45%, #FBEEB5 100%)` |
| `--app-radius` | `30px` |
| `--app-shadow` | `0 40px 90px -30px rgba(60,50,20,0.28), 0 10px 30px -10px rgba(60,50,20,0.12)` |
| `--app-border` | `1px solid rgba(255,255,255,0.5)` |

App 窗口是一个大圆角矩形，内部承载暖色渐变背景，所有玻璃卡片浮于其上。

**CSS 类**：`.app-window`

---

## 五、圆角与阴影

### 圆角

| Token | 值 | 用途 |
|-------|-----|------|
| `--radius-xs` | `8px` | 小标签、小徽章 |
| `--radius-sm` | `12px` | 输入框、小按钮 |
| `--radius-md` | `16px` | 卡片 |
| `--radius-lg` | `22px` | 大卡片、统计卡 |
| `--radius-pill` | `9999px` | 药丸按钮、标签、导航项 |

### 阴影（暖色调，禁用冷灰阴影）

| Token | 值 |
|-------|-----|
| `--shadow-sm` | `0 2px 10px -2px rgba(60,50,20,0.06)` |
| `--shadow-md` | `0 12px 30px -10px rgba(60,50,20,0.12)` |
| `--shadow-lg` | `0 24px 50px -16px rgba(60,50,20,0.18)` |

---

## 六、组件规范

### 6.1 顶部导航栏
- 容器：`.glass-strong`，高 64px，底部分隔线 `border-b border-white/40`
- 胶囊导航：`.glass-soft` 圆角药丸容器，内边距 4px
- 激活项：`bg-ink text-white`（深炭灰药丸）
- 非激活项：`text-text-muted`，hover 变 `text-text`
- 用户信息、退出按钮：`.glass-soft` 药丸

### 6.2 按钮
- **主按钮**：`bg-primary text-ink` 药丸形，hover `bg-primary-dark`
- **次按钮**：`.glass-soft` 药丸形，文字 `text-text-muted` hover `text-text`
- **收藏/标签按钮**：`border border-white/60 bg-white/30` 药丸形

### 6.3 输入框 / 选择框
- `border border-white/60 bg-white/40 backdrop-blur-sm` 圆角药丸/12px
- focus：`ring-2 ring-primary/30`

### 6.4 表格
- 容器：`.glass` 圆角，`overflow-hidden`
- 表头：`bg-white/30 backdrop-blur-md`，文字 `text-text-muted` 12px
- 行：`divide-y divide-black/5`，hover `bg-primary-soft/50`

### 6.5 看板列
- 容器：`.glass` + 状态色底（`columnBg`）叠加
- 表头：`rounded-pill` + 状态色浅底
- 卡片：`.glass-soft` 圆角，hover 上浮 `-translate-y-0.5`

### 6.6 统计卡
- 默认：`.glass` 圆角，软阴影
- 高亮卡：`bg-gradient-to-br from-primary to-primary-light`（实心黄渐变，作为视觉锚点）

---

## 七、看板状态配色

| 状态 | 列底叠加 | 表头底 | 强调色 |
|------|----------|--------|--------|
| ⭐ 收藏 | （无） | `bg-white/40` | `text-text-muted` |
| 📮 已投递 | `bg-primary-soft/50` | `bg-primary-soft` | `text-ink` |
| 💬 面试中 | `bg-warning/12` | `bg-warning/20` | `text-ink` |
| 🎉 已录用 | `bg-success-soft` | `bg-success/18` | `text-success` |
| ❌ 已拒绝 | `bg-danger-soft` | `bg-danger/12` | `text-danger` |

---

## 八、字体与排版

- **字体族**：`-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif`
- **页面标题**：24px / 700 / `text-text`
- **卡片标题**：14px / 600 / `text-text`
- **正文**：14px / 400 / `text-text`
- **次级说明**：12-13px / `text-text-muted`
- **字间距**：表格表头 `letter-spacing: 0.02em`

---

## 九、动效

- 页面入场：`animate-fade-in`（0.3s ease-out，Y 轴 6px → 0）
- 卡片 hover：`hover:-translate-y-0.5 hover:shadow-md`
- 按钮过渡：`transition-all` 0.2s
- 加载：`animate-spin` 0.8s

---

## 十、实现位置

- 设计令牌与玻璃类：[`job_workbench/src/index.css`](../job_workbench/src/index.css)
- Tailwind 颜色/圆角/阴影映射：[`job_workbench/tailwind.config.ts`](../job_workbench/tailwind.config.ts)
- 页面实现：[`job_workbench/src/pages/`](../job_workbench/src/pages/) 与 [`job_workbench/src/components/`](../job_workbench/src/components/)

---

## 十一、变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-09 | 深空蓝 + 暖橙 + 深色侧边栏 |
| v2.0 | 2026-10-03 | Crextio 暖奶油黄主题 + 顶部胶囊导航 |
| v2.1 | 2026-10-04 | **玻璃拟态升级**：半透明卡片 + 渐变背景 + app 窗口，iPhone 式透明感 |
