# 校招情报助手

**面向应届毕业生的校招岗位智能匹配与推送系统。**

每日自动采集校招岗位 → AI 解析 25+ 维度 → 基于用户画像精准匹配 → 写入用户飞书多维表格 → 微信/飞书推送日报。

---

## 产品定位

- **校招专属**：只服务应届毕业生（秋招/春招/管培/实习）
- **中心化采集**：从飞书秋招汇总表（10000+ 条）统一采集，多用户共享
- **AI 结构化**：LLM 把招聘公告拆分为具体岗位，提取 25+ 匹配维度（技能/专业/学历/城市/证书等）
- **精准匹配**：规则预筛 + AI 评分，每公司最多推送 5 个最匹配岗位
- **飞书交付**：每人专属多维表格 + 日报文档 + 交互卡片推送

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        数据流水线（中心化）                        │
│                                                                  │
│  飞书秋招汇总表(10150条)                                          │
│        │                                                         │
│        ▼                                                         │
│  feishu_source.py ──→ announcements 表(原始招聘链接)              │
│        │                                                         │
│        ▼                                                         │
│  fetch_announcements.py(阶段一: Playwright 并发抓取)             │
│        │                                                         │
│        ▼                                                         │
│  fetch_results.jsonl(中间结果: 正文文字 + 图片URL)                │
│        │                                                         │
│        ▼                                                         │
│  analyze_daemon.py(阶段二: LLM 分析, tail -f 模式)               │
│        │                                                         │
│        ├──→ jobs 表(拆分出的具体岗位, 25+ 维度, 给用户)           │
│        └──→ companies 表(公司元数据)                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      用户每日任务（多用户分发）                     │
│                                                                  │
│  main.py daily                                                   │
│        │                                                         │
│        ├──→ user_matcher.py: 规则预筛 + AI 评分 + 每公司限5      │
│        ├──→ daily_runner.py: 写入飞书表 + 生成日报 + 推送         │
│        └──→ 飞书多维表格(每人专属) + 飞书卡片 + 微信推送          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 数据库设计（三表分离）

| 表 | 用途 | 数据来源 | 给谁看 |
|----|------|---------|--------|
| `companies` | 公司元数据（行业/类型/地点） | 飞书表归一化 | 后台 |
| `announcements` | 原始招聘链接 + 抓取/分析状态 | 飞书表导入 | 后台（中间表） |
| `jobs` | 具体岗位（25+ 匹配维度） | LLM 拆分公告 | **用户** |

**关键设计**：`announcements` 是后台中间表，`jobs` 才是给用户的最终岗位数据。两者分离避免口径混乱。

---

## 环境要求

- Python 3.10+
- 公网 HTTPS 地址（接收飞书回调，MVP 可用 ngrok）
- 飞书开发者账号（商店应用）
- DeepSeek API Key（LLM 分析 + 简历解析）
- Playwright + Chromium（微信公告抓取）

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入:
#   FEISHU_APP_ID / FEISHU_APP_SECRET
#   DEEPSEEK_API_KEY
#   DATA_DIR=/workspace/job_assistant/data
```

### 3. 初始化数据库

```bash
python3 -c "import job_db; job_db.init_db()"
```

### 4. 启动数据流水线（抓取 + LLM 分析）

```bash
# 方式一：两阶段并行（推荐）
python3 run_parallel.py

# 方式二：分阶段手动执行
python3 fetch_announcements.py --workers 5    # 阶段一：抓取
python3 analyze_announcements.py              # 阶段二：分析
```

### 5. 启动用户服务

```bash
# 飞书回调服务（接收安装事件）
python3 callback_server.py

# 每日定时任务
python3 main.py daily
```

---

## 项目结构

```
job_assistant/
├── config.py                  # 全局配置(环境变量注入)
├── models.py                  # 用户画像模型 + JSON 存储
├── schema.py                  # 飞书多维表格字段定义
├── job_db.py                  # 数据库(三表: companies/announcements/jobs)
├── feishu_source.py           # 飞书秋招汇总表同步 → announcements 表
├── fetch_announcements.py     # 阶段一: Playwright 并发抓取公告
├── job_detail_analyzer.py     # 公告内容 LLM 拆分(25+ 维度)
├── analyze_daemon.py          # 阶段二: 持续消费抓取结果,LLM 分析
├── analyze_announcements.py   # 阶段二: 一次性分析(抓取完成后用)
├── run_parallel.py            # 两阶段并行启动脚本
├── llm_client.py              # DeepSeek LLM 客户端(简历解析+JD分析)
├── user_matcher.py            # 用户-岗位匹配(规则预筛+AI评分)
├── scorer.py                  # 评分引擎(可解释评分)
├── collector.py               # JD 抓取工具(fetch_jd_by_source)
├── feishu_client.py           # 飞书 API(多维表格/文档/消息)
├── wxpusher_client.py         # 微信推送
├── onboarding.py              # 用户注册流程(建表+转所有权)
├── callback_server.py         # 飞书回调 + 用户配置 API
├── daily_runner.py            # 单用户每日任务
├── main.py                    # 多用户调度入口
├── monitor_panel.py           # 流水线监控面板(Web)
├── onboarding_page.html       # 用户配置页面
└── data/
    ├── jobs.db                # SQLite 数据库
    ├── users.json             # 用户配置
    └── hashes/                # 岗位去重哈希(每用户)
```

---

## 核心流程

### 数据流水线（每日自动执行）

1. **同步**：`feishu_source.py` 从飞书秋招汇总表拉取记录 → 写入 `announcements` 表
2. **抓取**：`fetch_announcements.py` 用 Playwright 并发抓取公告正文+图片 → 写入 `fetch_results.jsonl`
3. **分析**：`analyze_daemon.py` 持续消费 JSONL → LLM 拆分具体岗位 → 写入 `jobs` 表

### 用户每日任务

1. `main.py daily` 遍历活跃用户
2. `user_matcher.py` 从 `jobs` 表匹配岗位（规则预筛 → AI 评分 → 每公司限 5）
3. `daily_runner.py` 写入用户飞书多维表格 → 生成日报文档 → 飞书卡片 + 微信推送

---

## 完整文档

| 文档 | 内容 |
|------|------|
| [01-项目概述与架构设计](docs/01-项目概述与架构设计.md) | 系统全貌、架构决策、数据流 |
| [02-核心模块与数据模型](docs/02-核心模块与数据模型.md) | 模块详解、数据库 Schema、匹配算法 |
| [03-接口规范与配置说明](docs/03-接口规范与配置说明.md) | 环境变量、飞书 API、LLM Prompt |
| [05-部署运维 SOP](docs/05-部署运维SOP.md) | 部署步骤、流水线管理、故障排查 |
| [11-客户使用手册](docs/11-客户使用手册.md) | 用户操作指引 |
| [12-管理员运营 SOP](docs/12-管理员运营SOP.md) | 开户、配置、运维流程 |

---

## 关键技术决策

| 决策 | 原因 |
|------|------|
| 三表分离（companies/announcements/jobs） | 链接和岗位是不同实体，分离后统计口径清晰 |
| 两阶段流水线（抓取→分析解耦） | 抓取慢（Playwright），分析贵（LLM），解耦后可并行+独立重试 |
| JSONL 中间结果 | append-only 原子写入，支持断点续传和并发安全 |
| 中心化采集 + 按需分发 | 采集一次所有用户共享，避免重复抓取 |
| 规则预筛 + AI 评分 | 规则快速过滤 70% 不相关岗位，AI 只对候选集评分 |
| 每公司限 5 个岗位 | 避免单一公司刷屏，保证多样性 |
