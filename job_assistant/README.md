# Offer搭子 — 桌面工作台

> Tauri 2 桌面端 + FastAPI 云端 API 的求职管理工具：岗位浏览、简历管理、投递追踪、AI 评分。

## 架构(V4 简化版)

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ 飞书秋招源表     │ ──→ │  中心化数据管线  │ ──→ │ 飞书「27届校招  │
│ (SOURCE_APP_*)  │     │  (daily_runner) │     │  汇总表」总表   │
└─────────────────┘     │  - 源表同步      │     │ (MASTER_APP_*)  │
                        │  - 正文抓取      │     └─────────────────┘
                        │  - LLM 拆岗      │            ↑ 只读视图
                        └────────┬─────────┘
                                 │
                                 ↓
                        ┌──────────────────┐     ┌─────────────────┐
                        │  job_api (FastAPI)│ ←── │  job_workbench  │
                        │  /api/v1/*        │     │  Tauri 桌面端    │
                        │  - auth (JWT)     │     │  - 注册/登录     │
                        │  - 简历解析        │     │  - 上传简历      │
                        │  - 岗位匹配        │     │  - 看岗位        │
                        │  - 邮件/日程       │     │  - 投递追踪      │
                        │  - 投递/简历 CRUD  │     │                 │
                        └──────────────────┘     └─────────────────┘
```

**飞书侧职责已收敛为两个**:读取源表 + 回写「27届校招汇总表」总表。原飞书机器人 / 用户分发 / 日报推送 / WxPusher 链路已下线。

## 子项目

| 目录 | 说明 | 技术栈 |
|------|------|--------|
| [`job_workbench/`](./job_workbench) | 桌面客户端 | Tauri 2 + React 18 + TypeScript + Tailwind + Zustand |
| [`job_api/`](./job_api) | 云端 API 服务 | FastAPI + Pydantic + JWT |

## 开发命令

根目录提供 `Makefile`，常用命令：

```bash
make help        # 列出所有命令
make dev-app     # 启动桌面端开发 (Tauri + Vite)
make dev-api     # 启动云端 API (uvicorn 热重载)
make build-app   # 构建桌面端生产包
make build-api   # 构建 API 分发包
make test        # 运行所有测试
make lint        # 运行 lint 检查
```

## 快速开始

### 桌面端 (job_workbench)

```bash
cd job_workbench
npm install
cp ../job_api/.env.example .env.local  # 按需配置 API 地址
npm run tauri:dev
```

### 云端 API (job_api)

```bash
cd job_api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 填入密钥
uvicorn main:app --reload --port 8000
```

### 中心化数据管线(部署侧)

```bash
# 每日 8:00 增量同步源表 → 抓正文 → 拆岗 → 回写总表
bash scripts/daily_update.sh

# 每周一 3:00 全量校验源表
python3 -c "from feishu_source import FeishuSourceSync; FeishuSourceSync().sync(full=True)"
```

详见 `scripts/crontab.example`。

## 目录结构

```
job_assistant/
├── job_workbench/              # 桌面端
│   ├── src/
│   │   ├── pages/              # Jobs/Resume/Applications/Email/Schedules/AutoFill/Login/Register
│   │   ├── components/         # ResumeUploader/RecruitmentCard/KanbanBoard/AuthGuard 等
│   │   ├── api/                # API client (auth/llm/...)
│   │   └── stores/             # Zustand stores (authStore/resumeStore/...)
│   └── src-tauri/              # Tauri 原生壳
├── job_api/                    # 云端 API
│   ├── main.py                 # FastAPI 入口
│   ├── routers/                # auth/llm/emails/schedules/resume_profiles/applications/...
│   ├── services/               # jwt_service/imap_service/schedule_service/job_matcher_adapter/...
│   └── config.py               # Pydantic Settings
├── feishu_source.py            # 飞书源表同步
├── feishu_master_tables.py     # 飞书「27届校招汇总表」总表回写
├── content_fetcher.py          # 招聘公告正文抓取
├── llm_enricher.py             # LLM 岗位拆分
├── daily_runner.py             # 中心化管线执行器(run_daily_pipeline)
├── llm_client.py               # DeepSeek 客户端(简历解析 + 图片 OCR)
├── scripts/
│   ├── daily_update.sh         # 每日管线启动脚本
│   └── crontab.example         # cron 配置示例
├── Makefile
├── README.md
├── CHANGELOG.md
└── .gitignore
```

## 主题

暖橙色主题（主色 `#F97316`，深石板 `#0F172A`，米白底 `#FAFAF9`，圆角 16px+）。
颜色通过 CSS 变量注入，Tailwind 在 `theme.extend` 中映射。

## 许可证

私有项目，未公开发布。
