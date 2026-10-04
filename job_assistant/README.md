# Offer搭子 — 桌面工作台

> Tauri 2 桌面端 + FastAPI 云端 API 的求职管理工具：岗位浏览、简历管理、投递追踪、AI 评分。

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

执行 `make help` 可查看完整命令列表与说明。

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

## 目录结构

```
job_assistant/
├── job_workbench/          # 桌面端
│   ├── src/                # React 应用
│   │   ├── pages/          # 页面占位 (Jobs/Resume/Applications/Login)
│   │   ├── api/            # API client
│   │   └── stores/        # Zustand stores
│   └── src-tauri/          # Tauri 原生壳
├── job_api/                # 云端 API
│   ├── main.py             # FastAPI 入口
│   └── config.py           # Pydantic Settings
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
