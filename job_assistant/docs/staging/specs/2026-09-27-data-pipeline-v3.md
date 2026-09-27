# 数据管线 V3 重构 Spec — 飞书源表驱动的三表架构

**日期**: 2026-09-27
**状态**: 待评审
**里程碑**: M3（数据管线重构）
**前置**: 废弃 company_crawler.py 爬虫逻辑，job_db.py 单表重构为三表

---

## 0. 已确认决策（用户 2026-09-27）

| # | 决策 | 说明 |
|---|------|------|
| 1 | 三表架构 | companies / announcements / positions |
| 2 | 只做校招 | 移除实习/社招条线，简化角色逻辑 |
| 3 | 首次全量 + 每日增量 | 首次同步公司+分析岗位一次完成，之后只处理每日新增/变更记录 |
| 4 | Playwright 抓微信 | 用 Playwright 抓取公众号正文，尽量全覆盖 |
| 5 | 届数聚焦 25-27 | 过滤秋招+提前批+春招+补招+补录后，应届集中在 25-27 届 |
| 6 | 行业/公司类型归一化 | 原始分类过杂且有重合，聚合为"不少不多"的大类，便于与学生配置匹配 |

---

## 1. 第一性原则分析

### 1.1 系统本质
飞书源表（人工维护、10150 条公告）是**唯一权威数据源**。系统不是爬虫系统，而是 **ETL + 匹配引擎**：
- ETL：飞书源表 → 归一化清洗 → LLM 拆岗 → 结构化岗位库
- 匹配引擎：学生画像 × 岗位库 → 评分排序 → 分发

### 1.2 三表设计的本质
飞书源表一条记录 = 一个**招聘公告**（公司 + 招聘类型 + 网申链接）。一个公告常含多个岗位（如"XX集团2027秋招"含产品/运营/技术等多个岗位）。

学生匹配的粒度是**岗位**，不是公告。因此：
- `companies`：公司维度去重（1 家公司 1 行），存行业/性质等稳定属性
- `announcements`：公告维度（1 条源表记录 = 1 行），存招聘类型/届数/网申链接/截止日期
- `positions`：岗位维度（1 条公告 → N 个岗位），LLM 从公告正文拆出，匹配在此粒度进行

### 1.3 LLM 的唯一职责
把"公告正文"→"结构化岗位列表"。这是非结构化→结构化转换，LLM 最擅长。LLM **不负责**发现公司、不负责匹配评分（匹配评分仍由 scorer.py 的规则+轻量 LLM 完成）。

### 1.4 Playwright 的定位
公告正文来源之一。源表"网申公告"链接可能是：官网公告页、公众号文章、PDF。Playwright 用于渲染 JS + 绕过部分反爬，是"正文获取器"，**不是数据源发现器**。

---

## 2. 对抗性审查

| 风险 | 等级 | 场景 | 防御措施 |
|------|------|------|----------|
| LLM 成本失控 | 🔴高 | 10150 条公告 × 首次全量分析 | 缓存（公告 URL hash → 结果）；增量（只分析新/变更）；并发限速；失败重试上限 3 次；降级（标题即岗位名） |
| Playwright 不稳定 | 🔴高 | 微信反爬/文章删除/JS 渲染失败/超时 | 超时 30s；重试 2 次；降级 requests 静态抓取；抓取内容缓存；抓取失败不阻塞，记录待重试 |
| 飞书 API 限流 | 🟡中 | 10150 条分页拉取 | 分页（每页 500）；last_modified_time 增量；请求间隔 0.3s |
| 届数解析歧义 | 🟡中 | "25-27届"/"2025/2026/2027届"/"应届"/"class of 2027" | 正则 + LLM 辅助；默认范围 25-27；匹配用范围 [min,max] 而非精确值 |
| 增量同步遗漏 | 🟡中 | last_modified_time 批量编辑异常 | 每周一次全量校验（记录数对比 + 差异告警） |
| 归一化映射失效 | 🟢低 | 源表新增行业/公司类型 | 未知值归"其他"+ 告警；映射表可配置（常量集中管理） |
| 匹配冷启动延迟 | 🟡中 | 首次全量 LLM 分析耗时长 | 分批异步处理；分析完一批即可匹配，无需等全部完成 |

---

## 3. 三表 Schema

### 3.1 companies（公司表）
公司维度，1 家公司 1 行，存稳定属性。

```sql
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,          -- 公司名（归一化后）
    name_raw TEXT,                      -- 源表原始公司名（留档）
    industry TEXT,                      -- 归一化行业（12 大类之一）
    industry_raw TEXT,                  -- 原始行业值
    company_type TEXT,                  -- 归一化公司性质（5 大类之一）
    company_type_raw TEXT,              -- 原始性质值
    first_seen TEXT NOT NULL,           -- 首次出现时间
    last_updated TEXT NOT NULL          -- 最后更新时间
);
CREATE INDEX IF NOT EXISTS idx_co_name ON companies(name);
CREATE INDEX IF NOT EXISTS idx_co_industry ON companies(industry);
CREATE INDEX IF NOT EXISTS idx_co_type ON companies(company_type);
```

### 3.2 announcements（招聘公告表）
公告维度，1 条飞书源表记录 = 1 行。

```sql
CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feishu_record_id TEXT UNIQUE NOT NULL,  -- 飞书记录 ID（增量同步主键）
    company_id INTEGER NOT NULL,            -- 关联 companies.id
    company_name TEXT NOT NULL,             -- 冗余公司名（查询便利）
    announcement_title TEXT,                -- 招聘岗位（源表字段，常为公告标题）
    recruit_type TEXT,                      -- 招聘类型（秋招/秋招提前批/春招/春招补招/春招补录）
    recruit_target TEXT,                    -- 招聘对象原文（如"2025-2027届"）
    min_grade INTEGER,                      -- 解析后最小届数（如 25）
    max_grade INTEGER,                      -- 解析后最大届数（如 27）
    industry_raw TEXT,                      -- 源表行业（冗余，归一化在 companies）
    company_type_raw TEXT,                  -- 源表性质（冗余）
    location TEXT,                          -- 工作地点
    education_req TEXT,                     -- 学历要求
    apply_url TEXT,                         -- 网申链接（投递入口）
    announcement_url TEXT,                 -- 网申公告链接（LLM 抓取入口）
    deadline TEXT,                          -- 投递截止日期
    publish_time TEXT,                      -- 发布时间
    crawl_status TEXT DEFAULT 'pending',    -- pending/success/failed/skipped
    crawl_time TEXT,                        -- 正文抓取时间
    llm_status TEXT DEFAULT 'pending',      -- pending/success/failed/skipped
    llm_time TEXT,                          -- LLM 分析时间
    llm_cache_hash TEXT,                    -- 公告 URL hash（LLM 结果缓存键）
    positions_count INTEGER DEFAULT 0,      -- 拆出的岗位数
    last_modified TEXT NOT NULL,            -- 飞书 last_modified_time（增量同步依据）
    synced_at TEXT NOT NULL,                -- 本次同步时间
    FOREIGN KEY (company_id) REFERENCES companies(id)
);
CREATE INDEX IF NOT EXISTS idx_ann_company ON announcements(company_id);
CREATE INDEX IF NOT EXISTS idx_ann_type ON announcements(recruit_type);
CREATE INDEX IF NOT EXISTS idx_ann_grade ON announcements(min_grade, max_grade);
CREATE INDEX IF NOT EXISTS idx_ann_llm_status ON announcements(llm_status);
CREATE INDEX IF NOT EXISTS idx_ann_modified ON announcements(last_modified);
```

### 3.3 positions（岗位表）
岗位维度，LLM 从公告正文拆出，匹配在此粒度。

```sql
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    announcement_id INTEGER NOT NULL,       -- 关联 announcements.id
    company_id INTEGER NOT NULL,            -- 关联 companies.id
    company_name TEXT NOT NULL,             -- 冗余
    position_title TEXT NOT NULL,           -- 岗位标题（LLM 拆出）
    department TEXT,                        -- 部门/条线
    location TEXT,                          -- 岗位地点
    education_req TEXT,                     -- 学历要求
    major_req TEXT,                         -- 专业要求
    jd_summary TEXT,                        -- JD 摘要（LLM 生成）
    is_management_trainee INTEGER DEFAULT 0,-- 管培标记
    difficulty TEXT,                        -- 难度评估
    apply_url TEXT,                         -- 投递链接
    source_url TEXT,                        -- 公告链接（冗余）
    dedup_hash TEXT UNIQUE,                 -- company+position_title+location 去重
    status TEXT DEFAULT '在招',             -- 在招/已关闭
    created_at TEXT NOT NULL,
    FOREIGN KEY (announcement_id) REFERENCES announcements(id),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);
CREATE INDEX IF NOT EXISTS idx_pos_company ON positions(company_id);
CREATE INDEX IF NOT EXISTS idx_pos_ann ON positions(announcement_id);
CREATE INDEX IF NOT EXISTS idx_pos_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_pos_mt ON positions(is_management_trainee);
```

---

## 4. 归一化映射

### 4.1 行业归一化（源表 ~259 类 → 12 大类）

> "不少不多"原则：够区分学生求职方向，又不至于过细难匹配。学生配置时从这 12 类里选。

| 大类 | 典型原始值（关键词匹配） |
|------|--------------------------|
| 互联网/科技 | 互联网、信息技术、软件、人工智能、电子商务、智能硬件、SaaS、云计算 |
| 金融 | 银行、证券、基金、保险、信托、租赁、PE/VC、期货、消费金融、资产管理 |
| 咨询/专业服务 | 咨询、会计师事务所、审计、税务、法律、人力资源、市场调研 |
| 消费/零售/快消 | 快消、零售、食品饮料、服装鞋帽、商超、母婴、化妆品 |
| 制造/工业 | 制造、汽车、机械、电子、半导体、新能源、化工、材料、装备 |
| 房地产/建筑 | 房地产、建筑、建材、物业、家居、装饰 |
| 医疗/医药/健康 | 医药、医疗器械、生物技术、医疗服务、养老健康 |
| 教育/培训 | 教育、培训、在线教育、职业教育、出版 |
| 传媒/文娱/游戏 | 传媒、影视、游戏、文化、体育、动漫、直播 |
| 交通/物流 | 物流、快递、航空、航运、铁路、供应链 |
| 能源/公用事业 | 能源、电力、燃气、水务、环保、矿产 |
| 政府/事业单位 | 政府、事业单位、央企、国企、公共管理 |

未命中 → "其他"（并记录告警，便于后续补充映射）。

### 4.2 公司类型归一化（源表 ~19 类 → 5 大类）

| 大类 | 典型原始值 |
|------|------------|
| 民企 | 民营企业、私营企业、股份制企业、民企、股份公司 |
| 国央企 | 国企、央企、国有控股、国有独资、国资 |
| 外企 | 外资、外商独资、外资企业、跨国公司 |
| 事业单位/政府 | 事业单位、政府机关、社会团体、机关单位 |
| 其他 | 合资、混合所有制、未分类、其他 |

### 4.3 招聘类型过滤（只保留校招）

只保留以下 5 类，其余丢弃：
`秋招`、`秋招提前批`、`春招`、`春招补招`、`春招补录`

### 4.4 届数范围解析

源表"招聘对象"字段 → 解析为 `min_grade` / `max_grade`（届数后两位，如 25 = 2025 届）。

| 原文示例 | min_grade | max_grade |
|----------|-----------|-----------|
| 2027届 | 27 | 27 |
| 2025-2027届 | 25 | 27 |
| 25-27届 | 25 | 27 |
| 应届毕业生 | 25 | 27（默认） |
| class of 2027 | 27 | 27 |
| 2026/2027届 | 26 | 27 |
| 空/无法解析 | 25 | 27（默认兜底） |

匹配逻辑：`user.graduation_year(25/26/27) ∈ [min_grade, max_grade]`

---

## 5. 数据管线流程

```
飞书源表 (每日更新)
    │
    ▼  feishu_source.py — 增量同步
    │   ├─ 按 last_modified_time 拉取新增/变更记录
    │   ├─ 过滤招聘类型（只留 5 类校招）
    │   ├─ 行业归一化（→12 类）+ 写 companies 表
    │   ├─ 公司类型归一化（→5 类）+ 更新 companies
    │   ├─ 届数范围解析（→ min/max_grade）
    │   └─ 写 announcements 表（crawl_status=pending, llm_status=pending）
    │
    ▼  content_fetcher.py — 正文抓取（Playwright）
    │   ├─ 取 announcements WHERE crawl_status='pending'
    │   ├─ Playwright 渲染 announcement_url → 正文文本
    │   │   ├─ 微信公众号文章（JS 渲染）
    │   │   ├─ 官网公告页
    │   │   └─ PDF（requests 下载 + 文本提取）
    │   ├─ 超时 30s + 重试 2 次
    │   ├─ 降级：requests 静态抓取
    │   ├─ 抓取内容缓存（URL hash → 文本文件）
    │   └─ 更新 crawl_status=success/failed
    │
    ▼  llm_enricher.py — LLM 岗位拆分
    │   ├─ 取 announcements WHERE crawl_status='success' AND llm_status='pending'
    │   ├─ 查缓存（llm_cache_hash 命中则跳过）
    │   ├─ DeepSeek 调用：公告正文 → 岗位列表 JSON
    │   │   ├─ position_title / department / location
    │   │   ├─ education_req / major_req
    │   │   ├─ jd_summary（100 字内）
    │   │   ├─ is_management_trainee / difficulty
    │   │   └─ apply_url 校验
    │   ├─ 并发限速 + 重试上限 3 次
    │   ├─ 降级：标题即岗位名（positions_count=1）
    │   └─ 写 positions 表 + 更新 llm_status
    │
    ▼  user_matcher.py — 用户匹配分发（已重构）
        ├─ 取 positions WHERE status='在招'，JOIN announcements + companies
        ├─ 规则预筛：届数∈[min,max] + 行业 + 公司类型 + 城市 + 专业关键词
        ├─ AI 评分：score_job（保留现有 scorer 逻辑）
        └─ 每公司限 N → 写用户飞书表 + 推送
```

---

## 6. 文件计划

| 文件 | 动作 | 职责 |
|------|------|------|
| `job_db.py` | **重构** | 三表建表 + CRUD（替换单表 jobs） |
| `feishu_source.py` | **新建** | 飞书源表增量同步 + 归一化 |
| `content_fetcher.py` | **新建** | Playwright 正文抓取 + 降级 + 缓存 |
| `llm_enricher.py` | **新建** | LLM 岗位拆分 + 缓存 + 降级 |
| `normalizer.py` | **新建** | 行业/公司类型/届数归一化映射（集中常量） |
| `user_matcher.py` | **重构** | 从 positions 表 JOIN 读取，移除角色分支 |
| `daily_runner.py` | **重构** | 移除社招/实习分支，集成新管线 |
| `company_crawler.py` | **废弃** | 删除或归档（不再自己爬公司） |
| `collector.py` | **废弃** | 删除（飞书源表替代搜索引擎采集） |
| `models.py` | **修改** | 移除 role 字段（只校招），简化 UserProfile |
| `config.py` | **修改** | 新增飞书源表 app_token/table_id 配置 |

---

## 7. 已决策（用户 2026-09-27 确认）

1. **行业 12 大类** ✅ 合适
2. **公司类型 5 大类** ✅ 合适
3. **首次 LLM 执行** ✅ 先试跑 100 条验证效果，确认后再全量
4. **归一化映射维护** ✅ 配置文件可编辑（JSON/YAML），无需改代码即可调整
5. **Playwright 部署** 待确认：容器环境 Chromium 依赖 + headless 配置（实施时验证）

---

## 8. 实施顺序

1. `normalizer.py` + 映射配置文件（JSON）— 行业/公司类型/届数归一化
2. `job_db.py` 重构 — 三表建表 + CRUD
3. `feishu_source.py` — 飞书源表增量同步 + 归一化写入
4. `content_fetcher.py` — Playwright 正文抓取 + 降级 + 缓存
5. `llm_enricher.py` — LLM 岗位拆分 + 缓存 + 降级（先试跑 100 条）
6. `user_matcher.py` 重构 — 从 positions 表 JOIN 读取
7. `daily_runner.py` 重构 — 集成新管线，移除社招/实习分支
8. 废弃 `company_crawler.py` / `collector.py`
