# Changelog

All notable changes to this project will be documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] - 2026-10-03

### Added
- 初始化项目脚手架 (T1)
  - `job_workbench/`: Tauri 2 + React 18 + TypeScript + Tailwind + Zustand 桌面端骨架
    - 4 个页面占位 (Jobs / Resume / Applications / Login)
    - Zustand auth store 占位、API client 基类占位
    - 暖橙色主题 (主色 #F97316, 深石板 #0F172A, 米白底 #FAFAF9, 圆角 16px+)
    - Tauri 2 src-tauri 配置 (窗口 1200x800, 标题 "求职搭子")
  - `job_api/`: FastAPI 云端 API 骨架
    - `main.py` (FastAPI 入口 + /health + CORS)
    - `config.py` (Pydantic Settings, 含 DEEPSEEK_API_KEY/JWT_SECRET/JWT_ALG/JWT_EXPIRE_HOURS/RESEND_API_KEY/DATA_DIR/jobs.db)
    - `requirements.txt` + `.env.example` + `.gitignore`
  - 根目录: `README.md` / `CHANGELOG.md` / `.gitignore` / `Makefile` (help/dev-app/dev-api/build-app/build-api/test/lint)

## [0.2.0] - 2026-10-04

### Changed
- 产品改名："求职搭子" → "Offer搭子"
  - tauri.conf.json: productName + 窗口标题
  - App.tsx: 顶部导航 logo + 标题
  - main.py: FastAPI title
  - email_service.py: 邮件标题
- logo.png 更新为 1254×1254 PNG (272KB)

### Fixed
- 网申/公告链接打不开
  - 放宽 URL 校验，允许含中文/特殊字符
  - 无协议时自动补 https://
  - Tauri shell 插件改为动态 import，避免 Web 环境打包失败
- 数据同步停更
  - 增量游标从 last_modified_time 改为 apply_update（飞书 Bitable API 限制）
  - job_db.get_last_sync_time() 改为 MAX(apply_update)
  - sync_service.py 视图 last_updated/updated_at 均取 apply_update
- 后端测试失败
  - test_sync.py jobs 表 schema 从 13 列更新为 20 列（对齐 JOB_FIELDS）

### Added
- 非分类列文本搜索
  - ColumnFilter: 支持分类列（多选 IN）和文本列（关键词 LIKE 搜索）双模式
  - Companies.tsx / Jobs.tsx: 所有列均渲染 ColumnFilter
  - sync_service.py: get_companies / get_jobs_page 支持 **text_filters LIKE 搜索
  - sync.py: 路由接收 location/position_titles/title/major_required 等文本列参数
- 表格列宽优化
  - Companies.tsx: location 列宽 160px → 120px
  - Jobs.tsx: major_required 列宽 160px → 120px
- vite-env.d.ts: 添加 *.png/*.jpg/*.jpeg/*.svg/*.gif 模块声明
- tauri-plugin-shell 集成
  - Cargo.toml: tauri-plugin-shell = "2"
  - capabilities/default.json: shell:allow-open 权限
  - lib.rs: .plugin(tauri_plugin_shell::init())

### Verified
- tsc + vite build: 81 模块转换，无错误
- 后端测试: 32/32 passed
- 构建产物: index-BQ5Ihcp5.js (234KB) + plugin-shell chunk (3.56KB)
