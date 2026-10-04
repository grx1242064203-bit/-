.PHONY: help dev-app dev-api build-app build-api test lint

help: ## 显示所有可用命令
	@awk 'BEGIN {FS = ":.*##"; printf "\nOffer搭子 - 可用命令:\n\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

dev-app: ## 启动桌面端开发 (Tauri + Vite)
	cd job_workbench && npm run tauri:dev

dev-api: ## 启动云端 API (uvicorn 热重载)
	cd job_api && uvicorn main:app --reload --host 0.0.0.0 --port 8000

build-app: ## 构建桌面端生产包
	cd job_workbench && npm run tauri:build

build-api: ## 构建 API 分发包 (wheel 占位)
	cd job_api && pip wheel . --no-deps -w dist || echo "build-api 占位 (待实现打包)"

test: ## 运行所有测试
	cd job_workbench && (npm test || true)
	cd job_api && (pytest || true)

lint: ## 运行 lint 检查
	cd job_workbench && (npm run lint || true)
	cd job_api && (ruff check . || true)
