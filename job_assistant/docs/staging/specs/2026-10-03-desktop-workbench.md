# 桌面工作台 v1.0 Spec

milestone: M1 (see docs/ROADMAP.md)

## 一、产品身份（差异化决策）

### 命名与品牌
- **产品名**："求职搭子"（xhs 体感词，比 RecruitOps 的"招聘运营"更贴近学生）
- **Logo**：暖橙色对话气泡 + "搭"字，不用蓝色方块字母
- **口号**："你的秋招搭子，从找岗位到拿 offer"
- **风格基调**：温暖、亲切、非工具感（区别于 RecruitOps 的冷蓝 SaaS 风）

### 与参考图 RecruitOps 的强制差异点（对抗性审查：防抄袭）
1. **配色**：主色 `#F97316`（橙）+ `#0F172A`（深石板）+ `#FAFAF9`（米白底），禁用蓝色主调
2. **布局**：顶部导航栏 + 卡片流首页（非左侧 sidebar + dashboard 模式）
3. **首页形态**：以"今日待办"为锚点的卡片流（非"统计卡片 + 表格"的仪表盘）
4. **功能命名**：用动词短语（"找岗位""对简历""跟投递""收通知"），不用名词模块名（"27届校招""求职助理""简历闪填"）
5. **视觉语言**：圆角更大（16px+）、字号更大（适配学生群近视友好）、留白更多
6. **不出现**：蓝色方块 Logo、左侧 sidebar 折叠、"R"字母图标、"RecruitOps"或近似名

### 首页设计（核心差异化）
RecruitOps 的流程是"抓取→评分→追踪→填写→邮件"的工具链式 + 仪表盘首页。
求职搭子改为"**岗位为中心**"的极简入口：

**默认首页 = 全部岗位列表（按更新时间倒序）**
- 用户登录第一眼就看到当前最新的所有招聘公司 + 岗位
- 顶部筛选栏（城市/学历/管培/分类/公司）+ 搜索框
- 每条岗位卡片：公司 / 岗位名 / 城市 / 学历 / 管培标签 / 截止日期 / 投递按钮
- 未上传简历时：列表按更新时间倒序，无匹配分数
- **上传简历 + LLM 解析后**：LLM 解析简历生成结构化画像（一次性），本地算法对全量岗位秒级评分，列表自动切换到"推荐岗位"视图

**推荐视图（简历解析后自动启用）**
- 默认只显示"推荐"+"超级推荐"两级岗位
- 评分等级定义（对齐现有 scorer.py）：
  - ≥75：🔥 强烈推荐（绿色高亮）
  - ≥55：✅ 推荐（蓝色徽章）
  - ≥35：➖ 可申请（灰色，默认隐藏，可展开"查看全部"）
  - <35：❌ 不建议（默认隐藏）
- 顶部 Tab 切换："全部岗位" / "🔥 强烈推荐(12)" / "✅ 推荐(28)" / "➖ 可申请(45)"
- 评分是本地算法计算（scorer.py），毫秒级，缓存到 SQLite，岗位更新时增量重算

**为什么这样设计（第一性原理）**
1. 用户买这个产品的第一诉求是"看岗位"，不是"看仪表盘"。岗位列表即首页，零认知成本。
2. 简历匹配的价值是"从 35000 个岗位里筛出最值得投的 40 个"。所以解析后默认只看推荐，降噪。
3. 不做"今日任务卡片流"——那是日程功能的衍生，留给 M2 邮箱追踪上线后再加。
4. 不做侧边栏导航——4 个核心页（岗位/简历/投递/设置）用顶部 Tab 足够。

## 二、架构决策

### 评分策略（复用现有算法体系，LLM 仅解析简历）
现有代码已有一整套成熟的匹配体系，桌面端直接复用，不重新设计：

**LLM 环节（一次性，仅在简历解析时调用）**
- resume_parser.py：简历文本 → DeepSeek → 结构化关键词(keywords) + 适配岗位方向(fit_directions)
- 单用户调用 1 次 LLM，成本 ≈ ¥0.05-0.10
- 结果缓存到本地 resume_cache/，简历未变不重算
- 用户编辑画像后可触发第二轮 supplement_from_edits（补充方向/技能），成本 ≈ ¥0.05

**算法评分环节（零 LLM 成本，本地毫秒级）**
- scorer.py：对全量 35,000 岗位跑 10 维加权评分
  - skill(0.10) 硬技能覆盖度 + Jaccard
  - hard_skill(0.15) 硬技能精确命中
  - cert(0.05) 证书匹配
  - education(0.15) 学历门槛
  - major(0.10) 专业大类匹配
  - city(0.05) 城市偏好
  - role(0.15) 方向对齐（fit_directions × 岗位树归属，含方向硬门槛）
  - soft_skill(0.05) 软技能命中
  - competitiveness(0.10) 候选人档位 vs 企业档位（冲刺/匹配/保底）
  - company_preference(0.10) 目标公司同行业/类型/地位加分
- 方向硬门槛：role < 40 时总分上限 45（防止方向错配靠泛技能刷分）
- 全量 35,000 岗位评分：本地 Python 计算，几秒内跑完，无需分批异步

**评分等级（对齐现有 scorer.py 定义）**
- ≥75：🔥 强烈推荐（绿色高亮）
- ≥55：✅ 推荐（蓝色徽章）
- ≥35：➖ 可申请（灰色，默认隐藏）
- <35：❌ 不建议（默认隐藏）

**评分缓存**
- 评分结果存 SQLite jobs.llm_score / llm_reason（字段名沿用，实际是算法分）
- 简历未变 + 岗位未更新 → 不重算
- 岗位更新 → 增量重算该岗位
- 简历重新解析 → 全量重算（本地秒级完成）

### 整体架构
```
桌面端（Tauri 2 + React）  ←→  云端 API（FastAPI）
├─ 本地 SQLite（岗位/简历/投递/日程）        ├─ DeepSeek LLM 代理
├─ 本地邮箱配置（IMAP 密码不出本机）         ├─ 飞书数据同步
├─ 本地简历文件                               ├─ 用户认证 + 订阅校验
└─ 通过 HTTPS 调云端 API                    └─ LLM 用量计费/限流
```

### 第一性原理决策
1. **敏感数据不出本机**：简历、邮箱 IMAP 授权码、投递记录全部存本地 SQLite。云端不接触这些。
2. **LLM Key 不出服务器**：DeepSeek API Key 只在云端，桌面端永远拿不到。桌面端通过 Bearer Token 调云端 `/llm/*` 接口。
3. **云端无状态**：云端不存储用户业务数据，只做：① 认证 ② LLM 代理 ③ 数据同步分发。可水平扩展。
4. **岗位数据同步而非爬取**：云端从飞书源表同步岗位数据库，桌面端从云端拉取增量更新到本地 SQLite。

### 数据所有权边界
| 数据 | 存哪 | 理由 |
|:---|:---|:---|
| 账号/密码 hash | 云端 | 认证需要 |
| 订阅状态 | 云端 | 防伪造 |
| LLM 用量计数 | 云端 | 计费/限流 |
| 岗位数据 | 本地（从云端同步） | 离线可查 + 大数据量不适合每次请求 |
| 简历文件 | 本地 | 高度敏感 |
| 简历解析结果 | 本地 | 衍生敏感数据 |
| 邮箱 IMAP 配置 | 本地 | 用户独有凭证 |
| 投递记录 | 本地 | 用户私有 |
| 日程 | 本地 | 用户私有 |

## 三、接口契约

### 桌面端 ↔ 云端 API

```
认证：
POST /auth/register     {email, password}          → {user_id, needs_verify}
POST /auth/verify-email {email, code}              → {token, user}
POST /auth/login        {email, password}           → {token, expires_at}
POST /auth/refresh      {token}                     → {token}

订阅：
GET  /subscription/status                           → {plan, expires_at, llm_quota, llm_used}
POST /subscription/activate  {code}                 → {plan, expires_at}

LLM 代理（所有请求需 Bearer Token + 订阅有效）：
POST /llm/parse-resume   {resume_text}              → {keywords, fit_directions}
POST /llm/supplement     {user_edited, resume_text}  → {fit_directions, hard_skills}
POST /llm/parse-email    {email_body}               → {type, company, time, location}  # M2

限流：每用户每日 LLM 调用上限 = 订阅档位配额，超出返回 429
注：岗位匹配评分不走 LLM，走本地算法（scorer.py）

数据同步：
GET  /sync/jobs?since={timestamp}&limit=500         → {jobs[], next_cursor}
GET  /sync/jobs/stats                                → {total, updated_at}
```

### 失败模式
| 失败 | 处理 |
|:---|:---|
| Token 失效 | 桌面端自动 refresh，失败则跳登录页 |
| 订阅过期 | LLM 接口返回 403；非 LLM 功能（浏览/筛选）仍可用，进入"只读模式" |
| LLM 调用超时 | 30s 超时，桌面端提示重试，不计费 |
| LLM 调用失败 | 不计费，返回 503，桌面端用本地缓存兜底 |
| 同步失败 | 本地 SQLite 旧数据可继续用，下次启动重试 |
| DeepSeek 余额不足 | 服务端告警，LLM 接口返回 503 + "服务繁忙" |
| 网络断开 | 本地数据全可用，只有 LLM/同步功能不可用 |

## 四、本地数据库 Schema（SQLite）

```sql
-- 用户配置（本机）
user_config (
  user_id, email, token_encrypted, subscription_plan, subscription_expires_at,
  llm_quota_today, llm_used_today, last_sync_at
)

-- 岗位数据（从云端同步）
jobs (
  job_id, company, title, category, city, requirements, jd_text,
  apply_url, deadline, source, graduation_match, is_mt,
  llm_score, llm_reason, updated_at, deleted
)

-- 简历
resumes (
  resume_id, file_path, raw_text, parsed_profile_json, created_at, is_active
)

-- 投递记录
applications (
  app_id, job_id, status, applied_at, updated_at, notes, source
  -- status: draft|applied|test|interview|offer|rejected
)

-- 邮箱配置
email_accounts (
  account_id, email_addr, imap_host, imap_port, password_encrypted, last_sync_at
)

-- 邮件解析结果
emails (
  email_id, account_id, subject, from, body, parsed_type, parsed_company,
  parsed_time, parsed_location, linked_app_id, received_at, status
)

-- 日程
schedules (
  event_id, source, title, event_time, location, company, job_id,
  related_email_id, status, notes
)
```

## 五、MVP 范围（M1）

只做能验证核心价值的最小集：

### M1 包含
1. **桌面端框架**：Tauri 2 + React + TypeScript + Tailwind
2. **认证流程**：邮箱注册 + 验证码 + 登录（用 Resend 发邮件）
3. **岗位同步**：从云端拉取飞书源表数据到本地 SQLite
4. **首页 = 全部岗位列表**：登录即看最新岗位，按更新时间倒序，无匹配分数
5. **岗位列表与筛选**：本地毫秒级筛选（城市/学历/管培/分类/公司）+ 搜索
6. **简历上传 + LLM 解析**：PDF/图片→文本→云端 LLM 解析→本地存储
7. **全量岗位评分 + 推荐视图**：简历解析后自动对全部岗位评分，首页切换到推荐 Tab（🔥超级推荐/✅推荐），默认只看推荐档
8. **投递记录**：手动记录投递 + Kanban 视图

### M1 不包含（deferred）
- 邮箱追踪（M2）
- 邮件→日程（M2）
- 网申辅助填写（M3 或不做）
- 多设备同步
- 移动端

### M1 验收测试
| 测试 | 通过标准 |
|:---|:---|
| 注册→登录→看到首页 | 全流程 < 30s，首页显示全部最新岗位 |
| 岗位同步 500 条 | < 10s |
| 筛选"上海+本科+管培" | < 100ms 本地 |
| 未上传简历时首页 | 看到全部岗位（按时间倒序），无评分，无推荐 Tab |
| 上传 PDF 简历→解析 | < 15s 返回结构化画像 |
| 简历解析后首页自动切换 | 自动显示推荐 Tab，只看 🔥超级推荐+✅推荐 岗位 |
| 全量评分耗时 | 35,000 岗位本地算法评分，秒级完成，无需等待 |
| 单用户 LLM 成本 | 简历解析 1 次 ≈ ¥0.05-0.10，不含算法评分（零 LLM） |
| 断网打开应用 | 能浏览本地岗位、投递记录，LLM 功能提示离线 |
| 订阅过期后打开 | 能浏览，点评分提示续费 |

## 六、技术栈

| 层 | 选型 | 理由 |
|:---|:---|:---|
| 桌面框架 | Tauri 2.0 | 安装包 ~40MB（含 Python sidecar），原生体验 |
| 前端 | React 18 + TypeScript | 生态最大 |
| UI | Tailwind CSS + Radix UI | 无样式组件库，定制自由度高 |
| 状态 | Zustand | 比 Redux 轻，适合中等规模 |
| 桌面本地数据库 | SQLite（rusqlite） | 已有 jobs.db，无缝迁移 |
| **评分引擎** | **Python sidecar**（PyOxidizer 打包） | 复用 scorer.py + 依赖，本地毫秒级评分 |
| 后端 | FastAPI（Python） | 直接 import 现有 llm_client/scorer/resume_parser |
| 用户存储 | SQLite（云端） | MVP 阶段够用，后期迁 PostgreSQL |
| 邮件发送 | Resend API | 免费版 100封/天，够验证码用 |
| LLM | DeepSeek（充值后） | 现有代码已对接 |
| 认证 | JWT（HS256） | 简单可靠 |

## 七、对抗性审查清单

| 风险 | 应对 |
|:---|:---|
| 用户分享账号给多人 | 单设备同时在线限制：同 token 同时只允许 1 个活跃会话，新登录踢旧 |
| 用户抓包逆向 API | LLM 接口加 rate limit（按用户/IP）；非订阅用户 403；不暴露 DeepSeek 原始接口 |
| LLM 成本失控 | LLM 仅用于简历解析（1 次 ≈ ¥0.05-0.10），评分全走本地算法零 LLM；每用户每日配额（订阅档位决定），超出 429；服务端全局熔断（日成本阈值）；单用户全流程 LLM 成本 ≈ ¥0.10 |
| DeepSeek 宕机 | 服务端保留 last_error 状态，桌面端用缓存评分兜底（旧分数 + "刷新失败"提示） |
| 简历解析质量差 | 解析后用户可编辑修正；本地存储修正版本，下次匹配用修正版 |
| 飞书源表停更 | 同步任务失败时保留本地旧数据，UI 标注"数据停止于 X 日" |
| 安装包被改 | Tauri 签名（dev 阶段自签，上线买代码签名证书 ¥500/年） |
| 用户数据丢失 | 本地 SQLite 自动备份（每周一份到 ~/.job_assistant/backups） |
| 邮箱授权码泄露 | 本机存储时用 OS keychain（Tauri keyring API），不明文落盘 |
| 抄袭嫌疑 | 配色/布局/命名/Logo 全部差异化（见第一节）；功能为通用求职场景，非 RecruitOps 独有 |

## 八、目录结构

```
job_workbench/                  # 新桌面端项目（独立于 job_assistant 后端）
├── src-tauri/                  # Tauri Rust 后端
│   ├── src/
│   │   ├── main.rs
│   │   ├── db.rs              # SQLite 操作
│   │   ├── sync.rs            # 数据同步
│   │   ├── sidecar.rs         # Python sidecar 进程管理（评分 IPC）
│   │   └── keychain.rs        # OS keychain
│   ├── bin/                   # PyOxidizer 打包的 Python 评分引擎
│   └── Cargo.toml
├── python-sidecar/            # 评分引擎 Python 源码（打包前）
│   ├── sidecar_server.py     # stdin/stdout JSON-RPC 服务
│   ├── scorer.py             # 复用现有
│   ├── keyword_normalizer.py # 复用现有
│   ├── job_tree.py           # 复用现有
│   ├── competitiveness.py    # 复用现有
│   └── job_db.py             # 复用现有（改为读本地 SQLite）
├── src/                        # React 前端
│   ├── pages/
│   │   ├── Jobs.tsx           # 首页=全部岗位列表+推荐视图
│   │   ├── Resume.tsx         # 简历上传与解析
│   │   ├── Applications.tsx   # 投递记录
│   │   ├── Login.tsx
│   │   └── Register.tsx
│   ├── components/
│   │   ├── JobCard.tsx
│   │   ├── MatchScore.tsx
│   │   └── ...
│   ├── stores/                # Zustand
│   ├── api/                   # 云端 API 调用
│   └── App.tsx
├── package.json
└── tauri.conf.json

job_api/                        # 云端 API（复用现有 job_assistant 代码）
├── main.py                     # FastAPI 入口
├── routers/
│   ├── auth.py
│   ├── llm.py                 # LLM 代理（import llm_client）
│   ├── sync.py
│   └── subscription.py
├── models/                    # 用户/订阅 数据模型
├── services/
│   ├── email_service.py       # Resend 邮件发送
│   └── llm_proxy.py          # DeepSeek 代理 + 限流
└── requirements.txt
```

## 九、与现有 job_assistant 代码的复用关系

| 现有文件 | 复用方式 |
|:---|:---|
| llm_client.py | job_api 直接 import，作为 LLM 代理底层 |
| scorer.py | job_api 直接 import，匹配评分核心 |
| resume_parser.py | job_api 直接 import |
| feishu_client.py | job_api 用于同步源表数据 |
| feishu_source.py | job_api 用于同步逻辑 |
| job_db.py | 桌面端 Rust 侧重写 SQLite schema（结构对齐） |
| job_tree.py | 桌面端前端 import JSON 即可 |
| config.py | job_api 复用（加新字段） |
| jobs.db | 数据源，迁移到云端 SQLite 后供同步 |

## Working notes

- 名称"求职搭子"为暂定，可调。备选："Offer搭子""秋招搭子""投递搭子"
- 首页 = 全部岗位列表，简历解析后切换到推荐 Tab，无冷启动空页面问题
- **关键技术决策已定：scorer.py 评分执行位置 = 选项 A（内嵌 Python sidecar）**
  - Tauri sidecar 打包 Python runtime + scorer.py + 依赖（keyword_normalizer/job_tree/competitiveness/job_db）
  - 评分在本地跑，毫秒级，可离线
  - 简历解析走云端 API（LLM Key 不出服务器），返回画像后传给本地 sidecar 评分
  - 安装包 ~40-50MB（含 Python runtime），可接受
- MVP 不做邮箱功能，但 SQLite schema 已预留 email_accounts/emails/schedules 表，避免 M2 时迁移
- Resend 免费版 100 封/天，若注册量超 100/天需升级（$20/月 5000 封）
- 代码签名证书先用自签，正式上线前买
- Tauri 2.0 还在 RC 阶段，若不稳定降级到 Tauri 1.x
- 待确认：是否需要做"游客模式"（不登录可浏览岗位但不能用 LLM）—— 倾向不做，强制注册转化更高
- 全量评分在简历解析完成后自动触发，本地算法秒级完成，无需进度条
