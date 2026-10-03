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
